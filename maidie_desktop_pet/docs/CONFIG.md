# 配置说明

Maidie 的用户配置位于 `config/config.json`。优先通过右键菜单中的“设置”修改；程序保存时会原子替换配置文件，并在 Key 输入框留空时保留已有值。

> `config/config.json` 中的 API Key 是本地明文。推荐使用环境变量，绝不能提交真实配置、截图或分享含 Key 的文件。

## 顶层配置分组

| 分组 | 用途 |
|---|---|
| `ai` | 主聊天 provider、Base URL、模型、Key 和超时 |
| `codex` | 技术问题所用模型、地址、Key 和超时 |
| `personality` | 人格预设和自定义提示词 |
| `movement` | 行走、奔跑、加速度和光标追逐 |
| `window` | 窗口尺寸、最小尺寸、置顶和透明度 |
| `fence` | 围栏边框显示 |
| `animation` | Sprite / Live2D Web 主后端、外部模型根目录和已注册模型 |
| `network` | 联网开关、Tavily provider、Key、超时和来源显示 |
| `proactive` | 主动行为开关、检查间隔、冷却和触发参数 |
| `vision` | 本地 OCR 开关、Qwen VL、截图压缩、缓存和默认范围 |
| `workspace` | 本地 Coding Agent 唯一允许访问的工作区根目录 |
| `coding_agent` | 本地 OpenCode/Codex provider、命令、超时和 dry-run 开关 |

缺少较新的字段时，`ConfigStore` 会补入安全默认值。打包默认配置位于 `packaging/config.json`，其中不得包含真实 Key。

## 动画后端

```json
{
  "animation": {
    "backend": "sprite",
    "current_model_id": "",
    "live2d_model_root": "",
    "live2d_models": []
  }
}
```

`backend` 仅接受 `sprite` 或 `live2d_web`，缺失或非法值回退 `sprite`。模型根目录和注册项由“设置 → 动画 / Live2D”维护；打包默认配置不包含任何真实本地路径。保存 `live2d_web` 后需重启应用才会切换主桌宠；当前不做运行时热切换。启动时若当前模型、PyQt6-WebEngine、Viewer 或 Cubism Web Runtime 不可用，会记录具体原因并使用 Sprite。

## AI 与技术模型

```json
{
  "ai": {
    "provider": "deepseek",
    "api_key": "",
    "base_url": "https://api.deepseek.com",
    "model": "deepseek-v4-flash",
    "timeout": 30
  },
  "codex": {
    "api_key": "",
    "base_url": "https://api.deepseek.com",
    "model": "deepseek-v4-pro",
    "timeout": 90
  }
}
```

接口应兼容 OpenAI Chat Completions。主 AI Key 可由 `DEEPSEEK_API_KEY` 提供，环境变量优先于 JSON。

## 人格

```json
{
  "personality": {
    "preset": "gentle_tsundere",
    "custom_prompt": ""
  }
}
```

内置预设：`gentle_tsundere`、`cheerful`、`healing`、`elegant_maid`、`custom`。只有 `custom` 使用自定义描述。

## 移动、窗口和围栏

```json
{
  "movement": {
    "walk_speed": 70,
    "run_speed": 175,
    "walk_threshold": 4,
    "run_threshold": 105,
    "acceleration": 360,
    "cursor_chase": false
  },
  "window": {
    "width": 160,
    "height": 190,
    "minimum_width": 36,
    "minimum_height": 43,
    "always_on_top": true,
    "opacity": 1.0
  },
  "fence": {
    "show_overlay": true
  }
}
```

`fence.show_overlay` 只控制围栏边框是否显示，不改变围栏约束本身。

## Tavily 搜索

```json
{
  "network": {
    "enabled": false,
    "timeout": 10,
    "show_sources": true,
    "search_provider": "tavily",
    "search_api_key": ""
  }
}
```

联网默认关闭，当前只实现 Tavily provider。启用后，查询词会发送给第三方搜索服务。缺少 Key、超时、网络异常和空结果均返回结构化错误。

## 主动行为

```json
{
  "proactive": {
    "enabled": false,
    "tick_seconds": 45,
    "cooldown_seconds": 900,
    "idle_trigger_seconds": 300,
    "coding_trigger_seconds": 7200,
    "random_chance": 0.05
  }
}
```

主动行为默认关闭。`tick_seconds` 保存时限制在 30–60 秒；全局冷却用于避免频繁打扰。

## OCR 与 Qwen VL

```json
{
  "vision": {
    "enabled": false,
    "interval_seconds": 60,
    "workspace_id": "",
    "api_key": "",
    "model": "qwen3-vl-flash",
    "region": "cn-beijing",
    "max_width": 1280,
    "jpeg_quality": 85,
    "cache_ttl_seconds": 5,
    "default_scope": "active_window",
    "cursor_region_width": 1000,
    "cursor_region_height": 800
  }
}
```

- `vision.enabled` 和 `interval_seconds` 控制可选本地 OCR 桌面感知，默认关闭。
- 其余字段配置按需 Qwen VL。关闭 OCR 不影响用户明确触发视觉请求。
- `default_scope` 可为 `active_window`、`fullscreen` 或 `cursor_region`；手动框选每次都需用户操作，不能设为默认。
- 图片最大宽度限制为 320–4096，JPEG 质量为 40–100，缓存为 0–60 秒。

支持的视觉环境变量：

```powershell
$env:DASHSCOPE_API_KEY = "你的百炼 API Key"
$env:DASHSCOPE_WORKSPACE_ID = "你的 Workspace ID"
$env:QWEN_VL_MODEL = "qwen3-vl-flash"
$env:QWEN_VL_REGION = "cn-beijing"
$env:VISION_MAX_WIDTH = "1280"
$env:VISION_JPEG_QUALITY = "85"
$env:VISION_CACHE_TTL_SECONDS = "5"
python main.py
```

详情见[千问视觉与屏幕理解](VISION.md)。

## 本地 Coding Agent

```json
{
  "workspace": {
    "root": ""
  },
  "coding_agent": {
    "enabled": false,
    "provider": "opencode",
    "command": "opencode",
    "timeout_seconds": 120,
    "dry_run": true
  }
}
```

- `workspace.root` 必须是已存在目录；所有目标路径解析后仍须位于该目录内。
- `provider` 仅接受 `opencode` 或 `codex`；`command` 是可执行文件名或其完整路径，不接受 shell 命令串。
- `dry_run` 第一版必须为 `true`，设为 `false` 会被工具拒绝。
- 使用 Codex 时会强制 `--sandbox read-only`；使用 OpenCode 时会通过其权限配置拒绝编辑、shell 和网络抓取。
- 可在“设置 → 工作区 / Coding Agent”中选择项目目录、配置 provider、command 和超时，并在保存前测试配置可用性。
- “测试 Coding Agent”只验证目录和命令配置，不启动 CLI，也不会读取项目内容。
- 设置层会把非法 provider 回退为 `opencode`，把超时限制在 1–600 秒，并无条件把 `dry_run` 保存为 `true`。
- 页面可检测或在确认后安装 OpenCode。安装方式按 npm、Scoop、Chocolatey 顺序检测，默认优先 npm；安装超时为 300 秒。
- OpenCode 安装成功后仅把页面中的 provider/command 调整为 `opencode`，不会自动启用 Coding Agent。OpenCode 的模型 API Key 仍需用户自行配置。
- `idle_timeout_seconds` 默认 30 秒，供 Codex 等普通行输出进程判断静默超时；OpenCode 是 TUI 工作负载，运行时忽略该静默阈值，仅使用总超时、进程状态和 OpenCode 日志判断。
- “打开 OpenCode 配置/初始化”只负责在 `workspace.root` 中打开可见终端，用户自行执行 `/connect` 或 `/init`，Maidie 不读取凭据内容。

完整接入与排障说明见 [CodingAgentTool](CODING_AGENT_TOOL.md)。

## Key 与配置安全

- 设置页只以密码样式显示 Key，公开设置快照只暴露“是否已配置”。
- JSON 文件并未加密，环境变量只是减少 Key 落盘，不替代主机安全。
- 不要提交 `config/config.json`、`.env` 或任何真实凭据。
- 搜索、AI 与视觉服务分别受对应第三方隐私政策约束，详见[隐私与安全边界](PRIVACY_AND_SAFETY.md)。
