from __future__ import annotations

from PyQt6.QtWidgets import QTextBrowser, QVBoxLayout, QWidget


class HelpPage(QWidget):
    """Product-facing help kept independent from editable settings."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.browser = QTextBrowser()
        self.browser.setObjectName("helpBrowser")
        self.browser.setOpenExternalLinks(True)
        self.browser.setHtml(self._content())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(self.browser)

    @staticmethod
    def _content() -> str:
        return """
        <h2>帮助与说明</h2>
        <h3>基础操作</h3>
        <ul>
          <li><b>左键点击：</b>与 Maidie 互动。</li>
          <li><b>左键拖动：</b>移动 Maidie。</li>
          <li><b>鼠标滚轮：</b>缩放角色窗口。</li>
          <li><b>右键菜单：</b>打开设置、围栏模式或退出。</li>
          <li><b>拖到屏幕边缘：</b>围栏开启时触发边界限制与回弹。</li>
        </ul>
        <h3>聊天能力</h3>
        <ul>
          <li>支持日常聊天、情绪陪伴和流式回复。</li>
          <li>技术问题会进入专用技术路由。</li>
          <li>天气、时间、搜索等事实可通过工具取得。</li>
          <li>剪贴板变化只用于提示是否需要帮助。</li>
          <li>屏幕、OCR 和窗口感知用于回答明确的桌面问题。</li>
        </ul>
        <h3>Agent 工具能力</h3>
        <ul>
          <li><b>时间与天气：</b>取得实时事实，不由模型猜测。</li>
          <li><b>联网搜索：</b>启用后检索当前问题并提供来源。</li>
          <li><b>屏幕理解：</b>按指定范围识别当前窗口、全屏或局部区域。</li>
          <li><b>记忆：</b>读取本地近期对话、事实和偏好。</li>
          <li><b>系统工具：</b>读取类操作受限，写操作需要明确确认。</li>
        </ul>
        <h3>隐私说明</h3>
        <ul>
          <li>Maidie 默认不会主动读取用户文件。</li>
          <li>剪贴板只在变化时提示，不自动读取或处理内容。</li>
          <li>屏幕识别需要用户明确触发；只有另行开启定时 OCR 后才会按设置运行。</li>
          <li>API Key 保存在本地配置中，建议优先使用环境变量。</li>
          <li>联网工具会明确标注来源和当前启用状态。</li>
        </ul>
        <h3>常见问题</h3>
        <p><b>无法聊天：</b>检查 Base URL、模型名称、API Key 和网络连接。</p>
        <p><b>屏幕识别不可用：</b>检查千问视觉配置；本地 OCR 还需要安装 Tesseract。</p>
        <p><b>动作没有播放：</b>动作可能处于冷却期，或素材配置尚未加载。</p>
        <p><b>如何退出：</b>右键 Maidie，选择“退出 Maidie”。</p>
        """
