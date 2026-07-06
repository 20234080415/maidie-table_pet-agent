from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class ProblemContext:
    problem_type: str = "unknown"
    visible_text: str = ""
    error_message: str = ""
    code_snippet: str = ""
    question_text: str = ""
    app_context: str = ""
    confidence: float = 0.0
    needs_search: bool = False
    search_query: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProblemAnalyzer:
    """Derive problem facts from VisionContext without generating a reply."""

    SEARCH_CONFIDENCE = 0.65
    ERROR_LINE = re.compile(
        r"(?im)^(?P<error>(?:[\w.]*?(?:Error|Exception)|Traceback|fatal error)[^\r\n]*)$"
    )
    CODE_LINE = re.compile(
        r"(?m)^(?:\s*(?:>>>\s*)?(?:def |class |from |import |if |for |while |try:|"
        r"except |return |raise |print\(|[A-Za-z_]\w*\s*=).+)$"
    )
    QUESTION = re.compile(
        r"(?s)([^\r\n]*(?:请问|求解|证明|计算|选择题|填空题|怎么写|如何|为什么|"
        r"what|why|how|solve)[^\r\n]*(?:[？?]|$))", re.I,
    )

    def analyze(self, vision_context: Any) -> ProblemContext:
        data = (vision_context.to_dict() if hasattr(vision_context, "to_dict")
                else dict(vision_context or {}))
        visible = str(data.get("visible_text") or "").strip()
        summary = str(data.get("screen_summary") or "").strip()
        intent = str(data.get("user_intent_guess") or "").strip()
        task_type = str(data.get("task_type") or "unknown")
        confidence = self._confidence(data.get("confidence"))
        combined = "\n".join(part for part in (visible, summary, intent) if part)

        errors = [match.group("error").strip() for match in self.ERROR_LINE.finditer(combined)]
        error_message = errors[-1] if errors else ""
        code_snippet = "\n".join(
            match.group(0).strip() for match in list(self.CODE_LINE.finditer(visible))[:12]
        )
        question_match = self.QUESTION.search(visible)
        question_text = question_match.group(1).strip() if question_match else ""

        if error_message or task_type == "code_error":
            problem_type = "code_error"
        elif question_text or task_type in {"math_problem", "image_question"}:
            problem_type = "question"
            question_text = question_text or visible
        elif task_type == "ui_operation":
            problem_type = "ui_problem"
        elif task_type in {"document", "webpage", "general_screen"}:
            problem_type = task_type
        else:
            problem_type = "unknown"

        app_context = self._app_context(combined)
        needs_search = bool(confidence >= self.SEARCH_CONFIDENCE
                            and problem_type == "code_error" and error_message)
        search_query = self._search_query(error_message, app_context) if needs_search else ""
        return ProblemContext(problem_type, visible, error_message, code_snippet, question_text,
                              app_context, confidence, needs_search, search_query)

    @staticmethod
    def _app_context(text: str) -> str:
        found = []
        for label, pattern in (("VSCode", r"VS\s*Code|Visual Studio Code"),
                               ("Python", r"Python|\.py\b|Traceback"),
                               ("Terminal", r"terminal|PowerShell|cmd\.exe"),
                               ("Browser", r"Chrome|Edge|Firefox|browser")):
            if re.search(pattern, text, re.I):
                found.append(label)
        return ", ".join(found)

    @staticmethod
    def _search_query(error_message: str, app_context: str) -> str:
        return re.sub(r"\s+", " ", f"{app_context} {error_message}").strip()[:500]

    @staticmethod
    def _confidence(value: Any) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return 0.0
