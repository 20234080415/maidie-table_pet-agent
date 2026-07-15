# 开发指南

## 项目结构

```text
maidie_desktop_pet/
├── main.py                     # 应用入口与依赖装配
├── start_maidie.bat            # Windows 快速启动
├── requirements.txt
├── ai/                         # 旧兼容 AI 客户端与路由
├── animation/                  # 图集与动画后端
├── assets/
│   ├── spritesheet.webp
│   ├── pet.json
│   └── actions/                # 外部动作素材与配置
├── config/                     # 本地配置（不要提交真实 Key）
├── core/
│   ├── brain/                  # 生产 Router、Planner、Executor、Synthesizer
│   ├── tools/                  # 结构化工具实现与注册表
│   ├── prompts/                # Router、人格、视觉与合成 Prompt
│   ├── session/                # AI 会话协调与轻量短期上下文
│   ├── awareness/              # 窗口、应用、鼠标和剪贴板感知
│   ├── vision/                 # Qwen VL、截图范围、视觉会话与本地 OCR
│   ├── experience/             # 情绪、注意力、对话和语音节奏
│   ├── proactive/              # 主动行为
│   ├── fence.py                # 围栏约束
│   ├── movement.py             # 移动计算
│   ├── pet.py                  # 中央协调器
│   └── state.py                # 状态机与优先级
├── input/                      # 手势、全局输入和缩放
├── memory/                     # SQLite 记忆实现与本地数据库
├── tools/                      # 动作素材导入脚本
├── ui/                         # 窗口、气泡、输入框、围栏和角色渲染
└── tests/                      # unittest 与 Qt offscreen 测试
```

## 架构约束

- 本仓库的完整协作与安全规则见根目录 [AGENTS.md](../AGENTS.md)；本文只保留开发入口和常用检查。
- 生产 AI 管线位于 `core/brain/*`；不要把新功能加入旧 `ai/router.py` 或 `core/agent/*` 编排层。
- 新 Agent 功能优先放在 `core/brain`、`core/tools`、`core/prompts` 和对应领域模块。
- `PetController` 保持协调器职责，不应成为业务逻辑集合。
- Router 只识别意图和实体；Planner 消费 RouterResult 并生成计划，不应重新猜意图。
- Executor 校验并执行计划；工具只返回结构化事实；Synthesizer 是唯一最终文本输出层。
- Planner 和模型参数不可信；系统写操作必须由执行层确认。
- 网络、OCR、文件扫描和模型调用不得阻塞 GUI 线程。
- 后台线程不得直接操作 QWidget、气泡、角色窗口或 QTimer。
- 每项行为改动都应增加或更新 unittest。

完整链路见[技术架构](TECHNICAL_OVERVIEW.md)，安全约束见[隐私与安全](PRIVACY_AND_SAFETY.md)。

## 核心链路阅读顺序

新开发者建议按下面的顺序阅读生产代码，先理解数据流，再进入具体实现：

1. `main.py`：应用启动、依赖构造与 Tool 注册。
2. `core/pet.py`：连接 UI、状态机、Movement、Memory 和 AI Session 的顶层协调器。
3. `core/session/ai_session.py`：请求提交、后台 Future、Qt 主线程回传和流式输出生命周期。
4. `core/brain/router.py` 与 `core/brain/llm_router.py`：统一 Agent 入口、意图识别和短期上下文解析。
5. `core/brain/planner.py`：把标准化 route 转换为结构化 Tool Plan。
6. `core/brain/executor.py` 与 `core/tools/`：二次校验计划参数、执行 Tool 并返回结构化事实。
7. `core/brain/synthesizer.py`、`core/personality/`：把事实转换为最终用户文本并统一 Maidie 人格。
8. `core/session/output_events.py`、`core/chat/`、`core/experience/`：把输出事件安全、平滑地呈现到桌宠交互层。

```text
用户输入 / Proactive Event
  -> PetController
  -> AISessionCoordinator
  -> BrainRouter / LLMIntentRouter
  -> BrainPlanner
  -> BrainExecutor / ToolRegistry
  -> Synthesizer / MaidieStyle
  -> OutputEvent / ChatStreamer
  -> PyQt UI / Animation
```

Memory 的持久化实现位于根级 `memory/`，并不位于 `core/memory/`。核心管线通过
`core/tools/memory_tool.py`、`core/prompts/memory.py`、`BrainRouter` 的 Memory context 和
`PetController` 的异步抽取流程连接持久化层。短期任务事实由
`core/session/task_context.py` 管理，不应直接写入长期 Memory。

## 源代码注释与文档规范

- 注释使用中文，`Agent`、`Tool`、`Router`、`Planner`、`Executor`、`Synthesizer`、`Session` 等技术关键词保留英文。
- 每个 Python 模块应在顶部说明职责、在 Maidie 架构中的位置，以及依赖或服务的核心组件。
- Class docstring 应说明职责、生命周期、持有的状态，以及与其他组件的交互边界。
- 重要 Function docstring 应说明输入、返回值、核心步骤和主要调用场景；不要机械罗列显而易见的类型提示。
- 复杂逻辑优先解释设计原因、数据流、状态转换、异步回调、安全控制和异常降级，不要逐行翻译代码。
- Planner/LLM 产物必须视为不可信数据；涉及权限、文件、截图或系统操作的注释应明确最终校验边界。
- 后台任务相关注释应指出结果如何回到 Qt 主线程，以及取消、generation 或 request id 如何阻止陈旧回调。
- 修改实现时同步检查相邻注释和文档；过期注释比缺少注释更容易误导维护者。

以下注释没有维护价值，应避免：

```python
x = 1  # 给 x 赋值 1
result = tool.run(query)  # 调用 Tool
```

应说明代码本身无法直接表达的约束，例如：

```python
# Planner 参数只是数据，不能被视为用户授权；确认必须在 Executor/Tool 边界重新建立。
safe_params.pop("confirmed", None)
```

## Prompt 管理

- Router、人格、视觉、记忆和 Synthesizer Prompt 集中放在 `core/prompts/`。
- 不要在 Router、工具、UI 或 `PetController` 中散落大段系统提示词。
- Prompt 修改应增加结构化输出、非法 JSON 降级和旧接口兼容测试。
- `SettingsManager.personality_prompt()` 保持人格配置的兼容入口。

## 扩展接口

- 动画：实现 `AnimationBackend`，可接入 Live2D、Spine 或其他渲染器。
- 动作：使用 WebP 动作条和 `ActionRegistry`，详见[动作系统](ACTIONS.md)。
- AI：实现兼容客户端，或使用 OpenAI Chat Completions 兼容接口。
- 工具：继承工具基类并注册到 `ToolRegistry`；保持结构化输出。
- 搜索：为搜索服务增加新的 provider adapter。
- 插件：扩展 `core.plugins.Plugin`，监听有限的状态、点击、消息和配置事件。
- 感知：扩展 `AwarenessContext`，新敏感能力应默认关闭。
- 记忆：可在现有接口后增加向量检索，但需保留敏感信息过滤和本地边界。
- 输入输出：可增加 STT、TTS、口型同步和音效。

## 开发与验证流程

1. 使用 `rg`、现有测试和模块 docstring 确认真实生产调用路径，不根据文件名猜测职责。
2. 检查 `git status --short --branch`，区分本次修改与用户已有工作树内容。
3. 只修改目标模块；不要顺手重构无关子系统，也不要改变安全、隐私和线程边界。
4. 先运行目标测试，再运行语法、导入和完整测试检查。
5. 提交前使用明确路径 staging，并通过 `git diff --cached --name-only` 审核提交范围；不要使用 `git add .` 吞入本地文件。

在 Windows 上先确认实际 Python 解释器：

```powershell
python -c "import sys; print(sys.executable)"
```

本机使用 `maidie` conda 环境时，可显式运行：

```powershell
conda run -n maidie python -m compileall -q core
conda run -n maidie python -m unittest discover -v
```

纯注释或 docstring 修改也应运行 `compileall`；需要严格确认行为未改变时，可以在剥离
docstring 后比较修改前后的 Python AST，并继续运行完整测试。

## 测试

在 `maidie_desktop_pet` 目录运行：

```powershell
python -m compileall -q core
$env:QT_QPA_PLATFORM = "offscreen"
python -m unittest discover -v
```

测试覆盖包括：

- 状态优先级、锁定、方向和屏幕边界。
- `idle/walk/run` 速度切换和自主行为。
- 动作注册、触发、冷却、摸头和拖动手势。
- 流式分句、气泡增量显示、尺寸动画和背景可读性。
- Qt 主线程响应性和后台任务生命周期。
- LLM 路由、正则降级、Planner、Executor 和工具数据边界。
- Router V2 结构化字段、`time_now/time_delta`、时间格式和短期事件上下文。
- 时间、天气、搜索、屏幕、记忆和网络错误降级。
- 围栏 clamp、snapback、对话池、overlay 生命周期、移动和缩放。
- 配置默认值、保存行为和 API Key 隐藏。

Qt UI 测试使用 `QT_QPA_PLATFORM=offscreen`，不需要显示真实窗口。

## 提交前检查

1. 确认没有提交 `config/config.json` 中的真实 Key。
2. 确认没有提交 `memory/memories.db*`。
3. 运行完整 unittest。
4. 检查文档与当前默认配置一致。
5. 对 UI 改动同时检查高 DPI、焦点、鼠标穿透和关闭生命周期。
6. 检查 Prompt、配置示例和文档是否与当前结构化字段一致。
7. 运行 `git diff --check`，排除空白错误和冲突标记。
8. 使用 `git diff --cached --name-only` 核对 staged 文件，不要提交本地配置、数据库、日志、截图或模型资源。
9. 仅文档/注释改动也要执行语法检查和完整测试，确认 import、类型定义和测试发现未受影响。

## 维护打包配置

- `build_exe.bat` 使用当前激活的 Python/conda 环境，不依赖项目 `.venv`。
- `maidie.spec` 会递归收集 `assets/` 和 `docs/`，新增普通素材无需逐项登记。
- 新增运行时数据目录时，应在 `maidie.spec` 的 `datas` 中加入整个目录。
- 新增通过字符串动态导入的插件包时，应加入 `hiddenimports` 或使用 `collect_submodules`。
- 新增配置字段时，同时更新 `packaging/config.json`，但绝不能写入真实 Key。
- 发布前应从干净目录运行 `build_exe.bat`，启动 `dist/Maidie/Maidie.exe` 并检查动画、配置写入、日志和记忆数据库。
- `build_installer.bat [version]` 使用 `packaging/maidie.iss` 将 one-folder 产物封装为 Inno Setup 安装包。
- 安装包构建始终先重建 EXE，避免把旧的 `dist/Maidie` 误装进新版本。
- `packaging/maidie-icon.png` 是透明图标源，`packaging/maidie.ico` 是 EXE、安装器和快捷方式共用的多尺寸图标。
- 安装目录位于当前用户的 LocalAppData，确保配置、日志和记忆可写，同时避免请求管理员权限。
- `config/config.json` 使用 `onlyifdoesntexist` 和 `uninsneveruninstall`；修改安装规则时必须继续保护用户配置。

## 未来扩展方向

- Live2D 或 Spine 动画后端。
- TTS、STT、口型同步和音效。
- 更多搜索 provider 和工具插件。
- 受严格确认保护的更多桌面能力。
- 向量记忆和更清晰的记忆管理界面。
- 更完整的来源展示和可访问性支持。
