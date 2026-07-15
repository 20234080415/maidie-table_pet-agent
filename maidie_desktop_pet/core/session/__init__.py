"""连接 Brain 异步请求与 PyQt 交互层的 Session API。

本包管理单次 AI 请求、短期任务上下文、思考反馈和 OutputEvent；它不判断意图，而是
保证后台结果按当前 request 生命周期安全地回到 UI 主线程。
"""

from core.session.ai_session import AISessionCoordinator
from core.session.thinking_feedback import ThinkingFeedbackPool

__all__ = ["AISessionCoordinator", "ThinkingFeedbackPool"]
from core.session.task_context import ShortTermTaskContext

__all__ = ["ShortTermTaskContext"]
