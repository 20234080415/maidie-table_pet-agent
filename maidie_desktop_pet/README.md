# Maidie Desktop Pet

Maidie 是一个运行在 Windows 桌面的 Python + PyQt6 AI 女仆桌宠，也是具备明确隐私与执行边界的本地桌面 Agent。

## 项目简介

Maidie 将透明置顶桌宠、动画与鼠标互动、流式聊天和结构化工具调用放在同一条生产链路中。模型负责理解与表达，工具负责提供时间、天气、搜索、屏幕和记忆等事实；涉及系统写入的操作必须再次确认。

## 当前能力

- 透明置顶窗口、角色动画、拖拽缩放、聊天气泡与围栏模式
- DeepSeek / OpenAI Chat Completions 兼容聊天接口
- `BrainRouter → Planner → Executor → ToolRegistry → Synthesizer` Agent 链路
- 当前时间、事件倒计时、天气、Tavily 搜索、本地 SQLite 记忆
- 按需调用 `qwen3-vl-flash` 理解当前窗口、全屏、鼠标附近或手动框选区域
- 可选本地 Tesseract OCR、桌面感知和默认关闭的主动行为
- 数据驱动的 WebP 动作扩展、Windows EXE 与安装包构建

## 快速启动

环境要求：Windows 10/11、Python 3.10+。

双击 `start_maidie.bat`，或手动运行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

## 基础配置

启动后右键 Maidie，打开“性格与模型设置”，配置聊天模型、技术模型、人格、Tavily 搜索和千问视觉。API Key 会以本地明文写入 `config/config.json`；推荐优先使用环境变量，且绝不能提交真实配置。

## 常用操作

- 双击角色或按 Enter / 空格：打开输入框
- 点击头顶或左右抚摸：摸头互动
- 点击脸颊：戳脸互动
- 拖动角色：移动 Maidie
- 右键角色：设置、围栏、帮助、关于与退出
- 明确说“看当前窗口”“看鼠标这块”或“我框选一下”：进入对应视觉范围

## Agent 架构

```text
User / Proactive
  → PetController
  → BrainRouter / LLMIntentRouter
  → BrainPlanner
  → BrainExecutor / ToolRegistry
  → Synthesizer → MaidieStyle
  → PyQt UI / Animation
```

工具只返回结构化事实，最终用户回复统一由 Synthesizer 生成。

## 结构化任务理解

Router 输出 `intent`、`task_type`、`entities`、`needs_tools`、`confidence` 和 `reason`。例如：

```text
我5.40下课，现在还有多久下课
```

会被识别为 `time_delta`，Planner 调用 `TimeTool.delta_until`。当前运行会话还会暂存“下课 → 5.40”，因此后续可直接问“还有多久下课”；该信息不会写入长期记忆。

## 测试

```powershell
python -m unittest discover -v
```

## Windows 打包

```powershell
.\build_exe.bat
.\build_installer.bat 0.1.0
```

EXE 输出到 `dist\Maidie\Maidie.exe`；安装包输出到 `dist\installer\Maidie-Setup.exe`。详细要求见[安装与启动](docs/SETUP.md)。

## 文档导航

- [功能说明](docs/FEATURES.md)
- [安装与启动](docs/SETUP.md)
- [配置说明](docs/CONFIG.md)
- [技术架构](docs/TECHNICAL_OVERVIEW.md)
- [千问视觉与屏幕理解](docs/VISION.md)
- [动作系统](docs/ACTIONS.md)
- [隐私与安全边界](docs/PRIVACY_AND_SAFETY.md)
- [开发指南](docs/DEVELOPMENT.md)

## 安全提醒

不要提交 `config/config.json`、`.env`、真实 API Key、`memory/*.db*`、私人截图或 `logs/`。任意 shell、文件删除和脚本执行始终被禁止。

## 项目状态

项目处于开发阶段，主要面向 Windows。当前搜索仅实现 Tavily；OCR 与按需千问视觉是两条独立链路；系统工具刻意限制写入与执行范围。
