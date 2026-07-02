# Maidie 技术架构

本文说明 Maidie 的生产 Agent 链路、模块职责和架构边界。界面能力见[功能说明](FEATURES.md)，权限边界见[隐私与安全](PRIVACY_AND_SAFETY.md)。

## 总体架构

```text
User / Proactive
  → PetController
  → BrainRouter / LLMIntentRouter
  → BrainPlanner
  → BrainExecutor / ToolRegistry
  → Synthesizer
  → PyQt UI / Animation
```

`PetController` 是状态、移动和 AI 会话的协调器，但不直接承担路由、规划、工具实现或最终文本合成。

## Maidie Core Brain V4

生产 AI 管线位于 `core/brain/*`：

| 组件 | 职责 |
|---|---|
| `BrainRouter` | 统一编排意图识别、规划、执行和合成 |
| `LLMIntentRouter` | 将输入分类为 `chat/task/screen/code_task/system_task` |
| `BrainPlanner` | 把非闲聊意图转换为结构化工具步骤 |
| `BrainExecutor` | 校验参数并通过 `ToolRegistry` 执行步骤 |
| `Synthesizer` | 基于工具事实生成唯一的用户可见最终文本 |
| `IntentClassifier` | 仅在 LLM 路由失败、超时或非法输出时作安全降级 |

正常聊天不执行工具。天气、时间、屏幕和其他事实任务必须先取得工具数据；Planner 和工具层不得直接生成最终回复。

## 意图与路由

- `chat`：日常交流、情绪陪伴和不要求外部事实的表达。
- `task`：时间、天气、搜索、记忆等事实任务。
- `screen`：当前屏幕、前台窗口和应用状态。
- `code_task`：代码、构建、调试、API 和技术文档问题。
- `system_task`：文件读取、搜索、截图或受控系统操作。

`LLMIntentRouter` 只返回 `intent/confidence/reason` JSON。若模型请求失败、超时、返回空内容或非法 JSON，系统才使用正则分类器兜底。

## Planner、Executor 与工具

Planner 生成结构化计划，例如：

```json
{
  "goal": "读取相关事实",
  "steps": [
    {
      "tool": "memory",
      "action": "读取相关偏好",
      "params": {"limit": 20}
    }
  ]
}
```

当前生产工具包括：

| 工具 | 事实来源 |
|---|---|
| `time` | 本机日期、时间和时区 |
| `weather` | 天气服务 |
| `search` | Tavily 搜索摘要与来源 |
| `screen` | OCR、应用和窗口跟踪 |
| `memory` | SQLite 近期聊天、事实和偏好 |
| `system` | 受控的本机读取与系统操作 |

工具只返回结构化 `type/raw/source` 数据。Planner 参数视为不可信输入；系统操作还会在执行层重新检查允许列表和确认要求。

## Synthesizer 与防幻觉

Synthesizer 是唯一允许生成最终用户文本的层。它必须：

- 只解释工具实际返回的事实；
- 数据缺失或工具失败时明确说明无法取得结果；
- 不猜测天气、时间、屏幕内容或搜索结果；
- 保持 Maidie 的角色语气，同时隐藏内部 Router、Planner 和工具链细节；
- 输出统一的文本、情绪、动作、状态和来源信息。

屏幕问题固定汇总 OCR、应用和窗口事实后再交给 Synthesizer。技术知识查询优先通过搜索获取资料，避免调用未注册的工具名称。

## 版本演进

| 阶段 | 主要能力 | 关键约束 |
|---|---|---|
| V1 | Planner、工具链、基础记忆 | 事实任务先规划再执行 |
| V2 | 鼠标/窗口感知、主动行为、定时任务 | 默认不主动打扰，全局冷却 |
| V3 | 屏幕 OCR、应用理解、受控系统操作 | OCR 默认关闭，写操作必须确认 |
| V4 | LLM-first 路由、统一 Brain 管线、Synthesizer | 工具只提供事实，最终文本统一合成 |

## 生产模块与兼容层

- `core/brain/*` 是当前生产 AI 架构，新功能应在这里实现。
- `ai/router.py` 是旧聊天/技术路由兼容模块，不应承载新功能。
- `core/agent/*` 中旧的 Agent 编排模块主要用于兼容和旧测试。
- `core/agent/confirmation.py` 中的 `ConfirmationBroker` 仍是生产安全基础设施，不属于废弃模块。
- `core/tools/*` 保存生产工具实现；工具通过 `ToolRegistry` 注册，不应直接塞入 Router。

## 并发与 UI 边界

网络、OCR、模型请求和文件扫描不得阻塞 GUI 线程。后台结果通过 Qt 主线程安全接收；后台线程不能直接操作 QWidget、气泡、角色窗口或 QTimer。

状态变化统一通过中央状态机和 `PetController` 协调。移动计算位于核心层，窗口、气泡、围栏边框和动画渲染保留在 UI 层。

## 当前限制

- 搜索目前只实现 Tavily provider。
- OCR 质量依赖 Tesseract、语言包、屏幕缩放和画面清晰度。
- `codex`、`opencode` 不是当前注册的独立生产工具；知识型技术问题使用搜索链路。
- 系统工具刻意限制任意写入和执行，不是通用桌面自动化框架。
- 尚未实现语音输入、TTS、Live2D、Spine 或云端多设备记忆同步。
