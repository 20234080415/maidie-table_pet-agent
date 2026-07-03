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
          <li><b>右键菜单：</b>打开设置、帮助、关于或退出。</li>
          <li><b>拖到屏幕边缘：</b>围栏开启时触发边界限制与回弹。</li>
        </ul>
        <h3>聊天能力</h3>
        <ul>
          <li>可以日常聊天，也可以回答技术问题。</li>
          <li>需要外部信息时，可以根据工具搜索信息。</li>
          <li>可以提示剪贴板发生变化，但不会自动处理内容。</li>
          <li>可结合屏幕、OCR 和 Window 感知理解当前上下文。</li>
        </ul>
        <h3>Agent 工具能力</h3>
        <ul>
          <li>Maidie 会根据输入判断是否需要调用工具。</li>
          <li>简单聊天直接回复；需要外部信息时调用搜索、时间、天气等工具。</li>
          <li>需要屏幕上下文时调用 OCR / Vision / Window 工具。</li>
        </ul>
        <h3>隐私说明</h3>
        <ul>
          <li>Maidie 默认不会主动读取用户文件。</li>
          <li>剪贴板变化只提示，不自动处理内容，除非用户确认。</li>
          <li>屏幕识别需要用户明确触发。</li>
          <li>API Key 保存在本地配置中。</li>
          <li>联网搜索工具通过配置启用。</li>
        </ul>
        <h3>常见问题</h3>
        <p><b>为什么 Maidie 没有回复？</b> 检查 Base URL、模型名称、API Key 和网络连接。</p>
        <p><b>为什么搜索失败？</b> 检查联网开关、Tavily Key 和网络状态。</p>
        <p><b>为什么关闭时控制台出现 KeyboardInterrupt？</b> 新版会统一停止计时器并安静退出；若仍出现，请附日志反馈。</p>
        <p><b>如何调整大小？</b> 使用鼠标滚轮，或右键菜单中的缩放操作。</p>
        <p><b>如何退出 Maidie？</b> 右键 Maidie，选择“退出 Maidie”。</p>
        """
