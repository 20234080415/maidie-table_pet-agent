"""把 Session 接收的文本增量转成有节奏的句子播放。

``AISessionCoordinator`` 负责请求身份和线程安全，本类只复用 ``SpeechPlayer`` 的切分
与定时播放能力，并通过 Qt signal 把文本片段交给气泡层。
"""

from __future__ import annotations

from core.experience.speech_player import SpeechPlayer


class ChatStreamer(SpeechPlayer):
    """Backward-compatible name for the Experience Layer speech player."""
