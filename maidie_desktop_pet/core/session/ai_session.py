"""管理 AI 请求从提交、后台执行到流式展示的完整生命周期。

``AISessionCoordinator`` 位于 ``PetController`` 与 ``BrainRouter`` 之间，使用外部
Executor 提交耗时工作，再通过 Qt signal/QTimer 把结果安全送回主线程并驱动 ChatStreamer。
"""

from __future__ import annotations

import logging
from time import monotonic
from typing import Any, Callable
from uuid import uuid4

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from core.chat.chat_streamer import ChatStreamer
from core.performance import begin, finish
from core.session.output_events import OutputEvent, OutputMode
from core.session.thinking_feedback import ThinkingFeedbackPool


class AISessionCoordinator(QObject):
    """拥有当前 AI 请求及其节奏化输出状态。

    实例通常与 ``PetController`` 同生命周期，但同一时刻只接受一个活动请求。
    generation/request_id 隔离取消前后的回调，sequence 保证 OutputEvent 顺序；后台
    Future 不直接操作 QWidget，而是经 Qt signal 和轮询回到主线程。
    """

    _stream_delta_ready = pyqtSignal(object)

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
        output_event: Callable[[dict[str, Any]], None] | None = None,
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
        self.output_event = output_event
        self.busy = False
        self.pending_message = ""
        self.pending_source = "chat"
        self.pending_reaction: str | None = None
        self.pending_response: dict[str, Any] | None = None
        self.pending_proactive = False
        self.future: Any | None = None
        self.request_id = ""
        self._request_generation = 0
        self._event_sequence = 0
        self._task_stream_received = False
        self._task_request_started = False
        self._current_tool = ""
        self._shutting_down = False
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(15)
        self.poll_timer.timeout.connect(self.poll_future)
        self.streamer = ChatStreamer(self)
        self.streamer.text_ready.connect(self.present_stream_text)
        if sentence_completed:
            self.streamer.sentence_finished.connect(sentence_completed)
        self.streamer.finished.connect(self.complete_stream_response)
        self._stream_delta_ready.connect(self._accept_stream_delta)

    def submit(self, message: str, proactive: bool = False) -> bool:
        """启动一次请求；已关闭、空输入或 busy 时返回 ``False``。

        入口先建立 request 身份和 UI 流状态，再把 Brain 调用提交给后台 Executor；
        提交异常会回滚 busy 状态，避免 Session 永久卡住。
        """
        if self._shutting_down:
            return False
        message = message.strip()
        if not message or self.busy:
            return False
        self.busy = True
        self.pending_message = message
        self.pending_source = "chat"
        self.pending_response = None
        self.pending_proactive = proactive
        self.request_id = uuid4().hex
        self._request_generation += 1
        self._event_sequence = 0
        self._task_stream_received = False
        self._task_request_started = False
        self._current_tool = ""
        # 同时捕获 generation 与 request_id，后续可拒绝取消前排队的回调。
        generation = self._request_generation
        request_id = self.request_id
        submitted_at = monotonic()
        try:
            self.streamer.start()
            context, self.pending_reaction = self.prepare_request(message, proactive)
            if self.thinking_feedback:
                self.thinking_feedback(self.feedback_pool.choose(message))
            self.future = self.executor.submit(
                self._run_request, message, context, request_id, submitted_at, generation
            )
            self.poll_timer.start()
            return True
        except Exception:
            self.busy = False
            self.logger.exception("AI session submission failed")
            return False

    def _run_request(self, message: str,
                     context: list[dict[str, Any]], request_id: str,
                     submitted_at: float, generation: int) -> dict[str, str]:
        begin(request_id, message, submitted_at)
        try:
            return self.ai_router.ask_stream(
                message,
                context,
                lambda event: self._stream_delta_ready.emit((request_id, generation, event)),
            )
        finally:
            finish(self.logger, submitted_at)

    def poll_future(self) -> None:
        if self._shutting_down:
            return
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
        if self._shutting_down:
            return
        self.accept_output_event(
            {"type": "token", "mode": OutputMode.CHAT_NATURAL.value,
             "content": str(delta), "source": self.pending_source},
            request_id=self.request_id,
            generation=self._request_generation,
        )

    def _accept_stream_delta(self, payload: object) -> None:
        if not isinstance(payload, tuple):
            return
        if len(payload) == 3:
            request_id, generation, event = payload
        elif len(payload) == 2:
            generation, event = payload
            request_id = self.request_id
        else:
            return
        raw = event if isinstance(event, dict) else {
            "type": "token", "mode": OutputMode.CHAT_NATURAL.value,
            "content": str(event), "source": self.pending_source,
        }
        self.accept_output_event(
            raw, request_id=str(request_id), generation=int(generation),
        )

    def accept_output_event(
        self, payload: dict[str, Any], *, request_id: str, generation: int,
    ) -> bool:
        """校验并转发当前请求的结构化输出事件。

        旧 generation 或错误 request_id 的事件会被丢弃，防止取消或快速重提后，
        后台迟到结果污染新的气泡和进度状态；返回值表示事件是否被当前 Session 接受。
        """
        if self._shutting_down:
            return False
        if generation != self._request_generation or request_id != self.request_id:
            return False
        self._event_sequence += 1
        event = OutputEvent.from_payload(
            payload, request_id=request_id, generation=generation,
            sequence=self._event_sequence,
        )
        if event.tool:
            self._current_tool = event.tool
        if event.type == "token" and event.mode is OutputMode.CHAT_NATURAL:
            self.streamer.push_token(event.content)
            return True
        if event.type == "token" and event.mode is OutputMode.TASK_STREAM:
            self._task_stream_received = True
            self._task_request_started = True
        elif event.mode is OutputMode.TASK_PROGRESS:
            self._task_request_started = True
        if self.output_event is not None:
            self.output_event(event.to_dict())
        return True

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
        for key in (
            "display_type", "short_text", "panel_title", "content",
            "panel_text", "full_text", "sources", "show_sources", "output_mode",
        ):
            if key in result:
                response[key] = result[key]
        mode = str(response.get("output_mode") or (
            OutputMode.TASK_STREAM.value if self._task_request_started
            else OutputMode.CHAT_NATURAL.value
        ))
        response["output_mode"] = mode
        self.pending_response = response
        self.result_received(response, failed, error_message)
        if mode == OutputMode.CHAT_NATURAL.value:
            if failed or not self.streamer.received_text:
                self.streamer.push_token(response["text"])
        elif not self._task_stream_received:
            self.accept_output_event(
                {"type": "token", "mode": OutputMode.TASK_STREAM.value,
                 "content": response["text"], "source": response["source"]},
                request_id=self.request_id, generation=self._request_generation,
            )
        self.streamer.finish()

    def complete_stream_response(self) -> None:
        """提交 complete 事件并原子清理当前请求的 Session 状态。"""
        response = self.pending_response
        if response is None:
            return
        self.accept_output_event(
            {"type": "complete",
             "mode": str(response.get("output_mode") or OutputMode.CHAT_NATURAL.value),
             "content": "", "source": str(response.get("source") or ""),
             "tool": self._current_tool, "phase": "completed"},
            request_id=self.request_id, generation=self._request_generation,
        )
        self.busy = False
        self.response_completed(self.pending_message, response, self.pending_reaction)
        self.pending_reaction = None
        self.pending_response = None
        self.pending_proactive = False
        self._task_stream_received = False
        self._task_request_started = False
        self._current_tool = ""

    def invalidate_current_request(self) -> None:
        """Discard an in-flight request and every callback captured before this call."""
        if self.request_id and not self._shutting_down and self.output_event is not None:
            self._event_sequence += 1
            self.output_event(OutputEvent(
                request_id=self.request_id,
                generation=self._request_generation,
                sequence=self._event_sequence,
                type="cancelled",
                mode=OutputMode.TASK_PROGRESS,
                content="",
                source="session",
                tool=self._current_tool,
                phase="cancelled",
            ).to_dict())
        self._request_generation += 1
        self.poll_timer.stop()
        self.streamer.stop()
        future = self.future
        self.future = None
        if future is not None:
            cancel = getattr(future, "cancel", None)
            if callable(cancel):
                cancel()
        self.busy = False
        self.pending_message = ""
        self.pending_source = "chat"
        self.pending_reaction = None
        self.pending_response = None
        self.pending_proactive = False
        self.request_id = ""
        self._event_sequence = 0
        self._task_stream_received = False
        self._task_request_started = False
        self._current_tool = ""

    def shutdown(self) -> None:
        """停止接受新请求，并使所有在途回调失效。"""
        if self._shutting_down:
            return
        self._shutting_down = True
        self.invalidate_current_request()
