# Tool 系统

Maidie 的生产工具位于 `core/tools/`，由 `main.py` 创建并注册到
`ToolRegistry`。当前注册项是时间、天气、Tavily 搜索、屏幕理解、SQLite
记忆、受控系统操作和默认关闭的 Coding Agent。

## 调用链

```text
用户输入
  → BrainRouter / LLMIntentRouter
  → BrainPlanner（生成结构化步骤）
  → BrainExecutor（工具名白名单与参数处理）
  → ToolRegistry（按名称查找工具）
  → Tool（返回 type / raw / source）
  → Synthesizer / Formatter
  → 气泡、搜索结果或长内容面板
```

`ToolRegistry` 只负责注册、查找和基础结果校验。生产多步计划由
`BrainExecutor` 执行；Planner 和模型给出的参数不视为授权，Executor 与具体工具
都必须再次校验。

## 数据契约

工具返回结构化字典：

```json
{
  "type": "time",
  "raw": {"...": "事实或结构化错误"},
  "source": "local"
}
```

工具层不得生成最终用户话术，`text` 字段会被 Registry 或 Executor 移除。
`Synthesizer` 是自然语言回复的唯一生产层；Coding Agent 等需要稳定布局的结果可先
经 Formatter 生成结构化卡片，再由 UI 根据 `display_type` 选择展示容器。

## 权限边界

- Executor 只接受显式白名单中的工具名。
- `SystemTool` 的读文件、搜索文件与截图属于只读操作；创建文件、打开应用或目录、
  切换窗口和写剪贴板需要确认。
- 删除文件、执行脚本和任意系统命令未实现，并被直接拒绝。
- 搜索、Vision 与 Coding Agent 均受各自配置开关约束；联网或截图不会因普通聊天
  自动开启。
- `CodingAgentTool` 还会校验 workspace 与强制 `dry_run=true`，详见
  [CODING_AGENT_TOOL.md](CODING_AGENT_TOOL.md)。

## 扩展工具

新增工具时应继承工具基类，保持 `type/raw/source` 契约，在 `main.py` 注册，并同步
更新 Planner、Executor 白名单、权限测试和文档。涉及写入、网络、截图或凭据的新能力
必须默认关闭或要求明确确认，且后台工作不得直接更新 Qt 控件。
