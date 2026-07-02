from __future__ import annotations

import logging
from time import monotonic
from typing import Any, Callable
from uuid import uuid4

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from core.chat.chat_streamer import ChatStreamer
from core.performance import begin, finish
from core.session.thinking_feedback import ThinkingFeedbackPool


class AISessionCoordinator(QObject):
    """Owns one AI request and its paced streaming lifecycle."""

    _stream_delta_ready = pyqtSignal(str)

    def __init__(
        self,
        ai_router: Any,
        executor: Any,
        logger: logging.Logger,
        prepare_request: Callable[[str, bool], tuple[list[dict[str, Any]], str | None]],
        present_text: Callable[[str], None],
        result_received: Callable[[dict[str, str], bool, str | None], None],
        response_completed: Callable[[str, dict[str, str], str | None], None],
        sentence_completed: Callable[[str], None] | None = None,
        parent: QObject | None = None,
        thinking_feedback: Callable[[str], None] | None = None,
        feedback_pool: ThinkingFeedbackPool | None = None,
    ) -> None:
        super().__init__(parent)
        self.ai_router = ai_router
        self.executor = executor
        self.logger = logger
        self.prepare_request = prepare_request
        self.present_text = present_text
        self.result_received = result_received
        self.response_completed = response_completed
        self.thinking_feedback = thinking_feedback
        self.feedback_pool = feedback_pool or ThinkingFeedbackPool()
        self.busy = False
        self.pending_message = ""
        self.pending_source = "chat"
        self.pending_reaction: str | None = None
        self.pending_response: dict[str, str] | None = None
        self.pending_proactive = False
        self.future: Any | None = None
        self.request_id = ""
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(15)
        self.poll_timer.timeout.connect(self.poll_future)
        self.streamer = ChatStreamer(self)
        self.streamer.text_ready.connect(self.present_stream_text)
        if sentence_completed:
            self.streamer.sentence_finished.connect(sentence_completed)
        self.streamer.finished.connect(self.complete_stream_response)
        self._stream_delta_ready.connect(self.handle_stream_delta)

    def submit(self, message: str, proactive: bool = False) -> bool:
        message = message.strip()
        if not message or self.busy:
            return False
        self.busy = True
        self.pending_message = message
        self.pending_source = "chat"
        self.pending_response = None
        self.pending_proactive = proactive
        self.request_id = uuid4().hex
        submitted_at = monotonic()
        try:
            self.streamer.start()
            context, self.pending_reaction = self.prepare_request(message, proactive)
            if self.thinking_feedback:
                self.thinking_feedback(self.feedback_pool.choose(message))
            self.future = self.executor.submit(
                self._run_request, message, context, self.request_id, submitted_at
            )
            self.poll_timer.start()
            return True
        except Exception:
            self.busy = False
            self.logger.exception("AI session submission failed")
            return False

    def _run_request(self, message: str,
                     context: list[dict[str, Any]], request_id: str,
                     submitted_at: float) -> dict[str, str]:
        begin(request_id, message, submitted_at)
        try:
            return self.ai_router.ask_stream(
                message,
                context,
                lambda delta: self._stream_delta_ready.emit(delta),
            )
        finally:
            finish(self.logger, submitted_at)

    def poll_future(self) -> None:
        future = self.future
        if future is None or not future.done():
            return
        self.poll_timer.stop()
        self.future = None
        try:
            self.handle_result(future.result())
        except Exception as exc:
            self.logger.exception("AI request failed")
            self.handle_result({"error": str(exc)})

    def handle_stream_delta(self, delta: str) -> None:
        self.streamer.push_token(delta)

    def present_stream_text(self, fragment: str) -> None:
        self.present_text(fragment)

    def handle_result(self, result: dict[str, Any]) -> None:
        failed = "error" in result
        error_message = str(result["error"]) if failed else None
        if failed:
            result = {
                "text": "唔，脑内频道暂时断线了，请稍后再试。",
                "emotion": "sad",
                "action": "talk",
                "state": "talking",
                "source": self.pending_source,
            }
        response = {
            "text": str(result.get("text", "Maidie 在这里哦。")),
            "emotion": str(result.get("emotion", "idle")),
            "action": str(result.get("action", "talk")),
            "state": str(result.get("state", "talking")),
            "source": str(result.get("source", "chat")),
        }
        self.pending_response = response
        self.result_received(response, failed, error_message)
        if failed or not self.streamer.received_text:
            self.streamer.push_token(response["text"])
        self.streamer.finish()

    def complete_stream_response(self) -> None:
        response = self.pending_response
        if response is None:
            return
        self.busy = False
        self.response_completed(self.pending_message, response, self.pending_reaction)
        self.pending_reaction = None
        self.pending_response = None
        self.pending_proactive = False

    def shutdown(self) -> None:
        self.poll_timer.stop()
