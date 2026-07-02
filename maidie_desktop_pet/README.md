# Maidie Desktop Pet

Maidie 是一个常驻 Windows 桌面的二次元 AI 女仆桌宠，基于 Python + PyQt6 构建，支持透明置顶窗口、自然移动、鼠标互动、流式聊天、桌面感知和可扩展动作系统。

它既是轻量的桌面角色，也是一个具备明确安全边界的本地 AI Agent：模型负责理解与表达，工具负责提供事实，涉及系统写入的操作必须由用户确认。

## 千问视觉

Maidie 支持按需调用阿里云百炼 `qwen3-vl-flash` 理解屏幕。千问负责观察并提取结构化事实，DeepSeek 负责分析、解题和组织最终回答。普通聊天不会截图，也不会保存原始截图。

右键 Maidie，进入“性格与模型设置 → 千问视觉”，可配置 Workspace ID、API Key、模型、地域、图片压缩和短缓存。环境变量配置仍然优先。

### 基本用法

支持四种截图范围：

- 当前窗口：默认模式，例如“看当前窗口”“看看这个报错”。
- 全屏：例如“看一下全屏”“看看整个屏幕”。
- 鼠标附近：例如“看鼠标这块”“这个按钮是什么意思”。
- 手动框选：例如“我框选一下给你看”“选个区域”。拖拽完成后再调用视觉模型，按 Esc 或选区小于 `20 × 20` 会取消。

查看当前窗口中的报错、题目或页面：

```text
你看看我现在屏幕这个报错是什么意思
你看看我现在屏幕这个题怎么做
帮我看看当前窗口
```

模糊请求不会直接截图：

```text
这个怎么弄
帮我看看
这是啥情况
```

Maidie 会先询问是否查看当前屏幕；回复“对”“可以”“你看”等确认后才截图。

### 连续追问

视觉结果会形成最长约 120 秒的轻量会话。以下追问复用最近一次结构化结果，不重复截图或调用千问：

```text
那怎么办
我该改哪里
这个命令在哪输入
为什么会这样
还有别的方法吗
```

需要重新读取画面时说“重新看一下屏幕”“重新截图”“现在呢”或“刷新一下”。说“不用看了”或“清除上下文”会清除视觉会话和短缓存。

### 看鼠标附近

Maidie 能组合识别“鼠标/光标/指针 + 指向/附近/位置 + 看/分析/题目/报错”等自然表达，例如：

```text
看鼠标这块
请分析光标旁边的错误
能看看指针指向的题目吗
帮我看一下这个数学题，就在鼠标指着的区域
```

发送后 Maidie 会提示“三秒后截图”。请在这三秒内把鼠标移回目标区域；随后只截取鼠标附近约 `1000 × 800` 的范围。区域越界会自动调整，失败则回退到当前窗口。

### OCR 与千问的区别

- 本地 OCR：可选的定时桌面感知，使用 Tesseract，默认关闭。
- 千问视觉：仅在用户明确请求时截图，理解画面并输出结构化信息。
- DeepSeek：依据视觉信息推理并生成最终回复。

OCR 与千问视觉目前相互独立，不是彼此的自动降级方案。关闭 OCR 不影响按需视觉。

### 快速测试

打开记事本显示一道题或一段报错，然后说：

```text
你看看我现在屏幕这个题怎么做
```

自动化测试：

```powershell
python -m unittest tests.test_vision_session_followup tests.test_qwen_vision tests.test_settings -v
```

详细配置、隐私边界、日志字段和当前限制见[千问视觉与屏幕理解](docs/VISION.md)。

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
- [千问视觉与屏幕理解](docs/VISION.md)
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
