# 配置说明

## 千问视觉配置

在“性格与模型设置 → 千问视觉”中配置百炼 Workspace ID、API Key、`qwen3-vl-flash`、地域、压缩参数和缓存时间。设置保存后立即应用，环境变量优先于 JSON 中保存的值。

支持 `DASHSCOPE_API_KEY`、`DASHSCOPE_WORKSPACE_ID`、`QWEN_VL_MODEL`、`QWEN_VL_REGION`、`VISION_MAX_WIDTH`、`VISION_JPEG_QUALITY` 和 `VISION_CACHE_TTL_SECONDS`。完整示例见[千问视觉与屏幕理解](VISION.md)。

视觉 Key 在 `config/config.json` 中为本地明文；推荐使用环境变量，且不要提交真实配置。

Maidie 的本地配置位于 `config/config.json`。推荐优先通过设置界面修改；API Key 也可以通过环境变量提供。

## 设置界面

1. 启动 Maidie。
2. 右键角色，选择“性格与模型设置”。
3. 打开“模型与 API”。
4. 填写 Base URL、聊天模型、技术模型和 API Key。
5. 保存并立即应用。

Key 输入框使用密码显示。保存时留空会保留已有 Key，不会将其清除。

## 环境变量

仅对当前 PowerShell 会话生效：

```powershell
$env:DEEPSEEK_API_KEY = "你的 API Key"
python main.py
```

写入当前 Windows 用户环境变量：

```powershell
[Environment]::SetEnvironmentVariable(
  "DEEPSEEK_API_KEY",
  "你的 API Key",
  "User"
)
```

使用 DeepSeek provider 时，环境变量优先于 JSON 中保存的主 AI Key。

## 配置示例

```json
{
  "ai": {
    "provider": "deepseek",
    "api_key": "YOUR_API_KEY_HERE",
    "base_url": "https://api.deepseek.com",
    "model": "deepseek-v4-flash",
    "timeout": 30
  },
  "codex": {
    "api_key": "",
    "base_url": "https://api.deepseek.com",
    "model": "deepseek-v4-pro",
    "timeout": 90
  },
  "personality": {
    "preset": "gentle_tsundere",
    "custom_prompt": ""
  },
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
  },
  "network": {
    "enabled": false,
    "timeout": 10,
    "show_sources": true,
    "search_provider": "tavily",
    "search_api_key": ""
  },
  "proactive": {
    "enabled": false,
    "tick_seconds": 45,
    "cooldown_seconds": 900,
    "idle_trigger_seconds": 300,
    "coding_trigger_seconds": 7200,
    "random_chance": 0.05
  },
  "vision": {
    "enabled": false,
    "interval_seconds": 60
  }
}
```

## 字段说明

| 字段 | 说明 |
|---|---|
| `ai.provider` | `deepseek` 或自定义兼容接口标识 |
| `ai.api_key` | 聊天接口 Key；推荐使用环境变量 |
| `ai.base_url` | OpenAI Chat Completions 兼容地址，不以 `/` 结尾 |
| `ai.model` / `ai.timeout` | 聊天模型和超时秒数 |
| `codex.model` / `codex.timeout` | 技术问题使用的模型和超时秒数 |
| `personality.preset` | 人格预设 ID |
| `personality.custom_prompt` | 预设为 `custom` 时使用的自定义描述 |
| `movement.*` | 自主移动速度、阈值、加速度和光标追逐开关 |
| `window.*` | 启动尺寸、最小尺寸、置顶和透明度 |
| `fence.show_overlay` | 是否显示可移动、可缩放的围栏边框；默认开启 |
| `network.*` | 联网开关、超时、来源显示、provider 和搜索 Key |
| `proactive.*` | 主动行为开关、检查间隔、冷却和触发参数 |
| `vision.enabled` | 是否启用屏幕 OCR；默认关闭 |
| `vision.interval_seconds` | 后台屏幕理解间隔，限制为 30–600 秒 |

## 人格配置

内置预设包括：

| ID | 风格 |
|---|---|
| `gentle_tsundere` | 温柔傲娇 |
| `cheerful` | 元气活泼 |
| `healing` | 安静治愈 |
| `elegant_maid` | 优雅女仆 |
| `custom` | 自定义提示词 |

在设置界面保存后立即生效，无需重启。

## 联网查询

联网功能默认关闭。启用步骤：

1. 在设置界面打开“联网查询”。
2. 选择 Tavily，填写搜索 API Key。
3. 设置超时和是否展示来源。
4. 保存并立即应用。

网络异常、超时、缺少 Key 或没有结果时，工具返回结构化错误，不应导致程序退出。当前只实现 Tavily provider。

联网请求会向第三方服务发送当前问题和必要查询词。详情见[隐私与安全边界](PRIVACY_AND_SAFETY.md)。

## API Key 安全

`config/config.json` 中的 Key 是本地明文。不要提交、截图或分享含真实 Key 的配置；长期使用时优先采用环境变量。
