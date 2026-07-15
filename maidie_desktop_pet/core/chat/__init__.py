"""连接 Session 文本流与 PyQt 气泡展示的聊天组件。

SentenceSplitter 负责边界识别，ChatStreamer 负责节奏，BubbleController 负责 UI 门面；
三者都消费 Synthesizer 输出，不参与 Brain 推理。
"""

from core.chat.bubble_controller import BubbleController
from core.chat.chat_streamer import ChatStreamer
from core.chat.sentence_splitter import SentenceSplitter

__all__ = ["BubbleController", "ChatStreamer", "SentenceSplitter"]
