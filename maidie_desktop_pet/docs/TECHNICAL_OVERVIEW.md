# Maidie 技术架构

本文描述当前生产 Agent 链路。用户功能见[功能说明](FEATURES.md)，线程和扩展约束见[开发指南](DEVELOPMENT.md)。

## 总体链路

```text
User / Proactive
  → PetController
  → BrainRouter / LLMIntentRouter
  → BrainPlanner
  → BrainExecutor / ToolRegistry
  → Synthesizer
  → MaidieStyle
  → PyQt UI / Animation
```

`PetController` 只协调会话、状态、移动和 UI，不重新实现路由、规划或工具逻辑。

## 组件职责

| 组件 | 职责 |
|---|---|
| `BrainRouter` | 串联路由、规划、执行和合成 |
| `LLMIntentRouter` | 输出结构化意图；失败时使用 `IntentClassifier` 降级 |
| `BrainPlanner` | 根据 RouterResult 生成结构化工具步骤 |
| `BrainExecutor` | 校验工具名和参数，通过 `ToolRegistry` 执行 |
| `ToolRegistry` | 注册并查找生产工具 |
| `Synthesizer` | 将工具事实变成唯一的用户可见回复 |
| `MaidieStyle` | 统一角色语气和响应字段 |

## LLMIntentRouter V2

Router 保留旧字段，并统一输出：

```json
{
  "intent": "task",
  "task_type": "time_delta",
  "entities": {
    "target_time_text": "5.40",
    "time_text": null,
    "event": "下课",
    "location": null,
    "query": null
  },
  "needs_tools": true,
  "confidence": 1.0,
  "reason": "deterministic time delta"
}
```

当前 `task_type` 包括：`none`、`time_now`、`time_delta`、`weather`、`search`、`memory`、`screen_understanding`、`calculation`、`file`、`app` 和 `unknown`。内部兼容路径还可能保留代码或系统任务标记。

高置信度的简单请求可由快速规则处理；其他输入交给 LLM。模型返回非法 JSON、空结果或异常时，仍使用旧正则分类器安全降级。

## 从倒计时问题到回复

输入：

```text
我5.40下课，现在还有多久下课
```

处理过程：

1. Router 输出 `intent=task`、`task_type=time_delta`，并提取 `target_time_text=5.40`、`event=下课`。
2. Planner 直接消费这些字段，生成 `time / delta_until` 计划，不重新猜测用户意图。
3. Executor 调用 `TimeTool.delta_until`；TimeTool 读取本机时间、解析目标时间并计算分钟差。
4. 工具返回 `now`、`target`、`remaining_minutes`、`remaining_text` 和 `event` 等结构化事实。
5. Synthesizer 依据事实生成 Maidie 的最终回复，不请求屏幕，也不让模型猜当前时间。

## Planner、Executor 与工具边界

Planner 优先使用 Router 的 `task_type/entities`：

- `time_now` → `time / now`
- `time_delta` → `time / delta_until`
- `weather` → `weather`
- `search` → `search`
- `screen_understanding` → 当前屏幕工具链

工具遵守 `type/raw/source` 数据契约，只返回事实或结构化错误。Planner 参数属于不可信输入；Executor 会检查允许列表，系统写操作还必须经过执行层确认。

当前工具包括 `TimeTool`、`WeatherTool`、`SearchTool`、`ScreenTool`、`MemoryTool`、`SystemTool` 和默认关闭的 `CodingAgentTool`。

## Coding Agent 只读链路

```text
code_task → BrainPlanner(coding_agent operation)
  → BrainExecutor(coding_agent 白名单)
  → CodingAgentTool(workspace 校验 + dry-run 校验)
  → subprocess(cwd=workspace.root, shell=False, timeout)
  → 结构化事实 → Synthesizer
```

`CodingAgentTool` 支持 `analyze_project`、`explain_module`、`propose_fix`、`propose_patch` 和 `test_plan`。CLI 命令构造、只读限制、输出捕获与错误归一化均封装在工具内，Router 不包含 provider 逻辑。Executor 只新增 `coding_agent` 工具名，没有扩大 `SystemTool` 的操作集合。

设置页通过 `ConfigStore.public_settings()` 读取必要的非密钥字段，通过 `update_user_settings()` 统一规范化并原子保存。保存后 `PetController` 仅重新配置已注册的 `CodingAgentTool`，无需重启应用。配置校验函数不启动 CLI，只检查 workspace、provider、dry-run 和可执行命令。

OpenCode 安装由独立的 `CodingAgentInstaller` 处理。安装器只有 npm、Scoop、Chocolatey 三组固定参数列表，不接收任意命令或 workspace 路径；设置页在确认后把安装工作移至 `QThread`，完成后回到 Qt 主线程更新日志和控件。安装成功必须再次发现 `opencode` 才视为成功。

后台调用改由 `CodingAgentProcessRunner` 管理：`Popen(shell=False)` 固定 cwd，双读取线程逐行汇入最多 200 行缓冲；主循环处理总超时、无输出超时和取消。Windows 清理使用固定参数的 `taskkill /PID ... /T /F` 终止完整进程树。工具事件经 `PetController` 信号进入实时控制台，UI 更新始终回到 Qt 主线程；退出时控制器会取消活动任务。

## 短期上下文与长期记忆

`ShortTermTaskContext` 在当前 `LLMIntentRouter` 实例中保存轻量的“事件 → 时间表达”，例如“下课 → 5.40”。它用于解析“还有多久下课”等紧邻追问，仅在当前运行会话有效，不写入 SQLite。

长期事实、偏好和近期对话由本地 SQLite 记忆系统管理，两者职责不同。

## 视觉链路

```text
LLMIntentRouter / fast route
  → BrainPlanner → BrainExecutor → ScreenTool
  → VisionService → capture / JPEG preprocess
  → QwenVLClient(qwen3-vl-flash)
  → VisionContext
  → Synthesizer → MaidieStyle
```

Qwen VL 只提取屏幕摘要、可见文字、任务类型、重要区域和置信度等结构化视觉事实。最终分析与用户回复仍由 Synthesizer 生成，不建立第二套回答链路。

本地 OCR 与按需 Qwen VL 相互独立，不是自动降级关系。

## 并发与兼容边界

- 模型、网络、OCR、截图处理和文件扫描不得阻塞 Qt GUI 线程。
- 后台线程不得直接操作 `QWidget`、`QTimer`、气泡或角色窗口。
- 新 Agent 功能放在 `core/brain`、`core/tools`、`core/prompts` 等生产目录。
- `ai/router.py` 与 `core/agent/*` 主要用于兼容和旧测试，不承载新生产功能。

## 当前限制

- 搜索目前只实现 Tavily provider。
- 模糊自然语言仍可能依赖所配置 LLM 的结构化输出质量。
- 短期事件时间在应用重启后清除。
- OCR 质量取决于 Tesseract、语言包、缩放和画面清晰度。
- 系统工具不是任意 shell 或通用桌面自动化接口。
- Coding Agent 第一版只提供分析和 patch 预览；CLI 的只读隔离依赖 Codex sandbox 或 OpenCode 权限层，不提供自动应用修改。
## 屏幕问题求解闭环

用户明确要求查看屏幕时，生产链路为：

```text
BrainRouter -> BrainPlanner(screen + conditional search)
  -> ScreenTool -> VisionContext -> ProblemAnalyzer -> ProblemContext
  -> BrainExecutor(白名单校验，按需 SearchTool)
  -> Synthesizer(屏幕事实 + 搜索结果 + 记忆上下文)
```

`ProblemContext` 保存问题类型、可见文本、错误、代码片段、题目、应用上下文、
置信度及搜索决策。分析器和工具只返回结构化事实；最终用户话术仍只由
`Synthesizer` 生成。条件搜索没有扩大 Executor 的工具白名单。
