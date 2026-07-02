# Maidie Desktop Pet

## 千问视觉

Maidie 支持按需调用阿里云百炼 `qwen3-vl-flash` 理解当前窗口或屏幕。只有“你看看我现在屏幕这个报错”等明确请求才会截图；模糊请求和普通聊天不会自动截图。视觉模型提取结构化事实，最终解释仍由 DeepSeek 生成。

右键 Maidie，进入“性格与模型设置 → 千问视觉”，可配置 Workspace ID、API Key、模型、地域、图片压缩和短缓存。环境变量配置仍然优先。

详细的触发规则、OCR 分工、测试方法、隐私说明和当前限制见[千问视觉与屏幕理解](docs/VISION.md)。

Maidie 是一个常驻 Windows 桌面的二次元 AI 女仆桌宠，基于 Python + PyQt6 构建，支持透明置顶窗口、自然移动、鼠标互动、流式聊天、桌面感知和可扩展动作系统。

它既是轻量的桌面角色，也是一个具备明确安全边界的本地 AI Agent：模型负责理解与表达，工具负责提供事实，涉及系统写入的操作必须由用户确认。

## 核心特性

- 透明、无边框、始终置顶的桌宠窗口
- Idle / Walk / Run / Thinking / Talking 等动画状态
- 点击、摸头、戳脸、拖拽和缩放互动
- SSE 流式聊天气泡与跟随式输入框
- DeepSeek / OpenAI Chat Completions 兼容接口
- LLM Router + Planner + Tool Executor + Synthesizer Agent 链路
- 屏幕 OCR、窗口感知、搜索、天气、时间和记忆工具
- 可移动、可缩放的围栏模式与自主移动
- 数据驱动的 WebP 动作条扩展系统

## 快速启动

环境要求：Windows 10/11、Python 3.10 或更高版本。

双击：

```text
start_maidie.bat
```

或手动运行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

完整安装步骤和 OCR 配置见[安装与启动](docs/SETUP.md)。

## API 配置

启动 Maidie 后，右键角色，打开：

```text
性格与模型设置 → 模型与 API
```

填写 Base URL、模型名称和 API Key 后保存即可。也可以使用环境变量：

```powershell
$env:DEEPSEEK_API_KEY = "你的 API Key"
python main.py
```

配置字段、人格和联网查询说明见[配置说明](docs/CONFIG.md)。

## 文档

- [安装与启动](docs/SETUP.md)
- [配置说明](docs/CONFIG.md)
- [功能说明](docs/FEATURES.md)
- [技术架构](docs/TECHNICAL_OVERVIEW.md)
- [动作系统](docs/ACTIONS.md)
- [隐私与安全边界](docs/PRIVACY_AND_SAFETY.md)
- [开发指南](docs/DEVELOPMENT.md)

## 测试

```powershell
python -m unittest discover -v
```

## 安全提醒

不要把真实 API Key、令牌、密码、含敏感信息的本地配置或 `memory/memories.db` 提交到公开仓库。

## 退出

右键 Maidie，选择“退出 Maidie”。
