# Maidie Desktop Pet

Maidie 是一个使用 Python 与 PyQt6 构建的 Windows 桌面 AI 桌宠，也是一个仍在快速迭代中的桌面 Agent 学习项目。它把角色动画、聊天交互、屏幕理解和受控工具调用放进同一条 Agent 链路，并对本地文件、窗口和 Coding Agent 能力采用保守授权。

## 当前能力

- **桌宠 UI**：透明置顶窗口、拖拽缩放、右键菜单、围栏、帮助与设置页面。
- **动画与行为**：待机、行走、说话、思考、睡眠及数据驱动的摸头、戳脸、庆祝等动作；主动行为默认关闭。
- **Live2D Web 主后端（基础版）**：可扫描仓库外的 `*.model3.json`、选择模型，并在保存配置、重启后作为主桌宠启动；Sprite 仍为默认值，模型、WebEngine、Viewer 或 Runtime 不可用时自动回退 Sprite。运行时无缝热切换尚未实现。
- **聊天展示**：流式聊天气泡；长文本、搜索结果和 Coding Agent 分析可进入独立长内容面板。
- **Agent Pipeline**：生产链路为 `BrainRouter → BrainPlanner → BrainExecutor → ToolRegistry → Synthesizer`，并保留规则降级。
- **工具**：时间与倒计时、天气、Tavily 搜索、SQLite 记忆、屏幕理解、本地 OCR，以及受白名单和确认机制约束的文件、窗口与剪贴板操作。
- **CodingAgentTool**：可调用本机 OpenCode 或 Codex CLI，对指定 workspace 做只读项目分析、模块解释、修复建议、patch 预览和测试方案；提供实时日志、状态和取消操作。
- **Vision**：按需分析当前窗口、全屏、鼠标附近或手动框选区域；Qwen VL 输出结构化事实，最终回答仍由 Synthesizer 生成。
- **Memory / Persona**：SQLite 长期记忆、会话内短期上下文、人格预设与统一的 Maidie 表达层均已接入基础版本。

> “已接入”不等于“完全自动化”。提醒调度、主动行为、Vision 和部分桌面操作仍属于基础版或实验性能力，详见 [Roadmap](docs/ROADMAP.md)。

## 快速开始

环境要求：Windows 10/11、Python 3.10+。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

也可以双击 `start_maidie.bat`。首次启动后，右键 Maidie 打开“设置”，填写模型地址、模型名称和 API Key。真实密钥不得提交到 Git；优先使用 `DEEPSEEK_API_KEY`、`DASHSCOPE_API_KEY` 等环境变量。完整安装、OCR 和打包说明见 [SETUP.md](docs/SETUP.md)。

## 配置说明

用户配置位于 `config/config.json`，推荐通过设置界面修改。仓库只提供不含密钥的 `packaging/config.json` 默认模板。

| 分组 | 用途 |
|---|---|
| `ai` / `codex` | 聊天与技术模型、Base URL、模型名、超时 |
| `personality` | 人格预设与自定义描述 |
| `movement` / `window` / `fence` | 移动、窗口与围栏行为 |
| `network` | Tavily 搜索开关、超时和来源展示 |
| `vision` | 本地 OCR 与 Qwen VL 参数 |
| `workspace` | Coding Agent 唯一允许访问的项目根目录 |
| `coding_agent` | 开关、provider、命令、超时和强制 `dry_run` |
| `proactive` | 默认关闭的主动行为参数 |

字段、取值范围和安全默认值见 [CONFIG.md](docs/CONFIG.md)。

## 项目结构

```text
maidie_desktop_pet/
├── main.py                 # 应用入口
├── core/
│   ├── brain/              # Router / Planner / Executor / Synthesizer
│   ├── tools/              # 工具与 Tool Registry
│   ├── formatters/         # 工具结果的确定性格式化
│   ├── vision/             # 截图、Qwen VL、视觉会话
│   ├── prompts/            # 生产 Prompt
│   └── pet.py              # UI 与运行时协调器
├── ui/                     # 桌宠、气泡、长内容面板与设置
├── animation/ / assets/    # 动画运行时与素材
├── memory/                 # SQLite 记忆
├── docs/                   # 专题文档
└── tests/                  # unittest 与 Qt offscreen 测试
```

## Agent 架构

```text
User Input
  → Router / Intent
  → Planner
  → Tool Registry / Executor
  → Formatter（需要确定性结构时）
  → Synthesizer / Persona
  → UI Display
```

- 工具层负责事实和结构化错误，不直接写用户话术。
- Formatter 负责稳定的结构化摘要，例如 Coding Agent 分析卡片。
- Synthesizer 负责最终自然语言、上下文和人格表达。
- UI 根据 `display_type` 选择小气泡、搜索结果或长内容面板。

完整职责与数据流见 [TECHNICAL_OVERVIEW.md](docs/TECHNICAL_OVERVIEW.md)。

从分层看，`ui/` 负责窗口与展示，`core/behavior.py`、`core/experience/` 与
`core/proactive/` 负责行为编排，`core/brain/` 负责 Agent 决策，`core/tools/`
负责受控能力，`memory/` 负责本地持久化，`core/vision/` 与
`core/awareness/` 负责按需屏幕上下文，Coding Agent 则通过独立只读适配层接入。
工具契约见 [TOOL_SYSTEM.md](docs/TOOL_SYSTEM.md)。项目代码结构已使用 Graphify
生成可交互图谱，产物与重新生成说明见 [docs/graph/](docs/graph/README.md)。

## CodingAgentTool 安全边界

- 默认关闭，且只允许配置的 `workspace.root`。
- 第一版强制 `dry_run=true`，只提供分析和建议。
- Codex CLI 使用 `--sandbox read-only`；OpenCode 显式拒绝 edit、bash、webfetch 和 workspace 外目录。
- 使用参数列表启动进程并设置 `shell=False`，不接受任意 shell 命令。
- 禁止安装依赖、写删文件、应用 patch、commit 或 push。
- 设置页里的 OpenCode 安装是独立、需用户确认的固定安装流程，不属于 CodingAgentTool 分析权限。
- 本 README 中的“commit / push”是用户对当前 Codex 维护会话的明确授权，不会改变 Maidie 应用内工具权限。

接入、状态机、输出结构和故障排查见 [CODING_AGENT_TOOL.md](docs/CODING_AGENT_TOOL.md)。

## 使用示例

```text
“帮我分析当前项目”
“检查 core/brain/planner.py 有没有问题”
“总结 README”
“看看我当前窗口”
“现在几点？离 5:40 下课还有多久？”
“提醒我几点上课”  # 提醒调度已接入基础组件，完整自然语言闭环仍在完善
```

## 已完成功能

- Windows 桌宠窗口、交互、动画、聊天气泡和长内容面板。
- Router / Planner / Executor / Tool Registry / Synthesizer 生产链路。
- 时间、天气、搜索、记忆、屏幕理解和受控系统工具的基础版本。
- Qwen VL 屏幕理解、视觉会话追问和高置信度报错的条件搜索。
- CodingAgentTool 的只读 OpenCode / Codex 接入、workspace 限制、实时控制台、取消与结构化分析展示。
- SQLite 记忆、人格 Prompt、体验层和 Windows 打包脚本。

## 未完成 / Roadmap

- 更完整、稳定的 LLM Router 与 Planner。
- 更强的 Vision API、window-aware Vision 和 OCR/Vision 协同。
- 更完善、可管理的长期 Memory。
- 更自然的动画、行为与主动交互系统。
- 更多适配不同工具结果的 UI 面板。
- 更细粒度、可审计的工具权限分级。
- 完整的自动任务、提醒创建与管理闭环。
- 更广的单元、集成和真实 Windows 环境测试覆盖。

详细状态与验收方向见 [ROADMAP.md](docs/ROADMAP.md)。

## 安全说明

Maidie 会接触屏幕、窗口、本地文件和第三方模型服务，因此默认采用最小权限：普通聊天不截图；视觉请求不自动扩大范围；写操作需要确认或直接禁止；Coding Agent 只读；日志与仓库不得包含真实密钥、私人截图、剪贴板正文或 `memory/*.db*`。

详见 [PRIVACY_AND_SAFETY.md](docs/PRIVACY_AND_SAFETY.md)。

## 开发状态

项目处于快速开发和学习阶段，主要面向 Windows。接口、配置和实验功能仍可能变化；生产 AI 链路以 `core/brain/*` 为准，`ai/router.py` 与 `core/agent/*` 主要保留兼容用途。

## 文档导航

完整目录见 [docs/README.md](docs/README.md)。开发时可运行：

```powershell
python -m unittest discover -v
```

项目暂未声明开源许可证；在许可证补充前，请勿默认将仓库内容视为可自由再分发。
