# Maidie 项目结构分析

## 分析状态

本次环境中没有可用的 Graphify Skill，PowerShell 也找不到 `graphify` 命令；仓库内
没有 Graphify 配置或既有输出。为避免安装来源和依赖不明确的软件，本报告采用手工
回退分析，依据 `main.py` 的依赖装配、`core/brain/` 生产链路、`ToolRegistry`、
主要 UI/行为/视觉/记忆模块和测试目录整理。它不是 Graphify CLI 的原生报告。

## 输出文件

- [`graph.json`](graph.json)：轻量节点与依赖边数据，适合脚本读取。
- [`graph.html`](graph.html)：无需构建工具即可打开的分层结构视图。
- `GRAPH_REPORT.md`：关键结构、风险和重新生成说明。

## 结构结论

```text
main.py
  ├─ UI: PetWindow → PetController
  ├─ Behavior: state / movement / experience / proactive
  ├─ Agent: BrainRouter → Planner → Executor → ToolRegistry → Synthesizer
  ├─ Tools: time / weather / search / screen / memory / system / coding_agent
  ├─ Vision: awareness → ScreenTool → VisionService → Qwen VL
  └─ Storage: ConversationMemory(SQLite) / TaskScheduler(JSON)
```

生产 Agent 的唯一入口是 `core/brain/BrainRouter`。`ai/router.py` 与
`core/agent/*` 属于兼容层，不应承载新生产编排。`PetController` 是 UI、会话、行为和
插件之间的中央协调点，因此新增业务逻辑应优先放入领域模块，避免继续扩大协调器。

工具边界清晰：Planner 只产生步骤，Executor 校验白名单并执行，工具只返回结构化
事实，Synthesizer 生成最终回复。Vision 与 Coding Agent 都复用该主链路，没有建立
第二套用户回答管线。

## 关注点

1. `PetController` 连接面较广，适合保持“协调器”定位并通过测试约束 Qt 主线程更新。
2. 生产与兼容 Agent 目录并存，文档和新增代码必须明确以 `core/brain/` 为准。
3. 系统工具包含需确认的有限写操作；Coding Agent 则是更严格的独立只读边界，两者
   不应混为一谈。
4. Live2D、主动行为、提醒闭环和部分 Vision 能力仍为实验性或部分完成，不能从目录
   存在推断为成熟功能。

## 重新生成

安装并确认可信的 Graphify 官方工具后，在项目根目录运行：

```powershell
graphify .
```

若工具生成 `graph.html`、`graph.json` 与 `GRAPH_REPORT.md`，应核对其格式和内容后
替换本目录中的手工回退产物，并更新本页的分析状态。仓库目前不固定 Graphify 版本，
也不新增运行时依赖。
