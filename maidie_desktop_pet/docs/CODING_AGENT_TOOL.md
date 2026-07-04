# CodingAgentTool

`CodingAgentTool` 是 Maidie 对本机 OpenCode / Codex CLI 的只读适配器。它只负责分析事实，不负责修改项目，也没有扩大 `SystemTool` 权限。

## 支持范围

当前支持五类操作：

- `analyze_project`：项目概览与风险分析。
- `explain_module`：解释 workspace 内模块。
- `propose_fix`：提出修复建议。
- `propose_patch`：只返回 patch 预览，不应用修改。
- `test_plan`：生成测试方案。

调用结果会整理为 `summary`、`findings`、`suggested_changes`、`patch_preview` 和 `tests_suggested`。Formatter 把它们转成稳定的结果卡片，Synthesizer 只生成简短的人格化提示，完整内容由长内容面板展示。

## 执行链路

```text
code_task
  → BrainPlanner
  → BrainExecutor（工具白名单）
  → CodingAgentTool（workspace + dry-run 校验）
  → CodingAgentProcessRunner
  → OpenCode / Codex CLI
  → 结构化事实 → Formatter / Synthesizer → UI
```

进程使用 `workspace.root` 作为 `cwd`，以参数列表和 `shell=False` 启动。运行中会发送启动、输出、状态和结束事件；控制台保留最近 200 行，可取消任务，退出应用时会清理活动进程树。

## 安全边界

- `coding_agent.enabled` 默认是 `false`。
- `workspace.root` 必须是存在的目录；目标路径解析后必须仍在其中。
- `dry_run` 必须为 `true`，设置保存和运行时都会强制校验。
- provider 仅接受 `opencode` 或 `codex`。
- Codex 固定使用 `exec --sandbox read-only`。
- OpenCode 权限配置拒绝 `edit`、`bash`、`webfetch` 和 `external_directory`。
- Prompt 明确禁止创建、编辑、删除、安装、commit、push 和 shell 命令。
- 工具不接受任意命令行字符串，不读取或保存 CLI 凭据。

OpenCode 的安装入口是设置页中独立的、用户确认后的固定参数流程，仅支持已定义的 npm、Scoop 或 Chocolatey 安装命令。它不代表分析工具获得安装权限。

## 配置与使用

在“设置 → 工作区 / Coding Agent”中：

1. 选择项目根目录。
2. 选择 OpenCode 或 Codex，并确认命令可用。
3. 在可见终端中完成 CLI 自己的登录、模型配置或 `/init`。
4. 保存并启用 Coding Agent；`dry_run` 始终保持开启。

示例：

```text
帮我分析当前项目
解释 core/brain/router.py
为这个错误提出修复建议，但不要改文件
给我一个测试方案
```

## 状态与排障

UI 区分运行、等待配置、完成、失败、超时和取消。常见问题：

- `workspace_not_configured`：先选择有效项目目录。
- `cli_not_found`：安装 CLI 或填写可执行文件完整路径。
- `needs_setup`：在可见终端完成 provider / API Key 配置。
- OpenCode 看似无输出：TUI 可能在读取文件；以总超时、进程状态和 OpenCode 日志为准。
- 输出不是结构化 JSON：仍会保留为摘要，但卡片字段可能不完整。

当前限制：只读隔离依赖本地 CLI 的 sandbox / permission 实现；Maidie 额外使用 workspace、命令构造和 Prompt 做纵深防御，但不把该功能描述为通用安全沙箱。
