# Maidie Desktop Pet

## Agent Router V2（强制规划与防幻觉）

Agent Router V2 固定职责边界为：`Tool = 数据层`、`Planner = 决策层`、`Synthesizer/LLM = 唯一表达层`。

- 输入先分类为 `DIRECT_TOOL`、`DECISION_TASK` 或 `CHAT`；“适不适合、能不能、是否应该、建议、去不去、要不要”等决策词优先于天气/时间匹配。
- `DECISION_TASK` 强制进入 Planner，使用 `{goal, steps}` JSON；决策计划至少两步，最后一步为仅基于已有数据表达的 `llm`。
- WeatherTool、TimeTool 和 Search 只返回 `type/raw/source`，禁止返回面向用户的 `text` 或主观结论；Registry 与 Executor 还会剥离旧工具误带的 `text`。
- 天气事实必须来自 WeatherTool，时间事实必须来自 TimeTool。必需数据缺失时，在调用 LLM 前阻断并返回“不确定，需要查询。”
- 最终统一由 Synthesizer 输出 `text/emotion/action/state/source`，工具链回答的 `source` 为 `tool+llm`。

验收测试覆盖：“明天适合跑步吗”、“长沙明天天气怎么样”、“现在几点”、“要不要去健身”，以及必需数据缺失时禁止 LLM 猜测。

## Agent V2（桌面感知与主动行为）

Agent V2 使用固定链路：`Desktop Awareness → Proactive/Scheduler → Tools → Synthesizer → PyQt UI`。

- `core/awareness/` 根据全局鼠标样本计算速度和空闲时长，并通过 Windows API 只读获取前台窗口标题，分类为 coding、browser、chat、gaming 或 unknown；不会截屏或记录键盘内容。
- `core/proactive/` 每 30–60 秒观察一次上下文，支持久未活动、长时间编程和低概率陪伴触发；全局冷却默认 15 分钟，防止连续打扰。
- `core/tasks/` 支持 once、cron 和 condition 三类任务，任务保存在本地 `memory/scheduled_tasks.json`；天气条件只使用 WeatherTool 原始数据判断。
- 状态机新增 `watching` 与 `reminding`。观察时复用轻微 idle/眨眼反馈；提醒通过原有 SSE、气泡和 happy/shy/sleepy 动作反馈。
- 主动行为默认关闭，可在“性格与模型设置 → 主动行为”中开启，并设置 30–60 秒观察间隔和最短打扰间隔。
- 主动内容继续通过现有 Agent Router 与五字段输出协议；Tool 仍只返回数据，缺少必要事实时不允许 LLM 猜测。

## Agent V3（屏幕理解与半自动系统操作）

V3 链路为：`User/Proactive → Memory → Screen/App Awareness → Planner → Executor → Synthesizer → UI`。

- `core/vision/screen_reader.py` 按可配置间隔截屏，在内存中使用 pytesseract OCR，并输出屏幕文字、应用线索、语义场景与置信度。屏幕理解默认关闭，开启前由设置页明确授权；OCR 在本机完成，但相关文字可能随当前 Agent 任务发送给用户配置的 AI 服务。
- `core/awareness/app_tracker.py` 读取前台进程名和窗口标题，分类为 coding、browsing、chatting、gaming 或 unknown；剪贴板监听只观察 Windows 序列号变化，不读取内容。
- `core/tools/system_tools.py` 支持读取/搜索/创建文件、打开白名单应用、打开文件夹、切换窗口、截图和写剪贴板。读取文件、搜索文件和截图按只读能力处理；其余动作必须弹出确认框。
- `delete_file`、`execute_script` 和 `system_command` 被显式列为危险动作，当前版本即使确认也不会执行。
- Planner 的 system 步骤包含 `requires_confirmation`，Executor 负责真实执行并将纯数据结果交给 Synthesizer；Tool 不输出用户结论，五字段 AI 响应结构保持不变。
- 确认请求从后台执行线程回到 PyQt 主线程；默认按钮为“否”，超时自动拒绝，确认框不会展示待写入的文件内容或剪贴板正文。
- Proactive Engine 新增屏幕场景变化、频繁切换窗口和剪贴板变化触发，并继续受总冷却时间限制。

OCR 需要 Python 包 `pytesseract` 以及 Windows 上安装的 Tesseract OCR 程序；未安装或识别失败时只返回不可用状态，不会阻塞 Maidie 其他功能。

Maidie 是一个常驻 Windows 桌面的二次元 AI 女仆桌宠。项目使用 Python、PyQt6、
hatch-pet WebP 动画图集和 DeepSeek/OpenAI 兼容接口，具备透明置顶窗口、自然移动、
鼠标互动、流式聊天、技术问题路由、最近聊天、人格设置和可扩展动作系统。

## 当前功能

### 桌面窗口

- 无边框、透明背景、始终置顶。
- 默认尺寸 `160×190`，最小可缩至约 `36×43`。
- 支持窗口边缘、滚轮、右键菜单和右下角奶油白角标缩放。
- 右下角角标只在鼠标位于桌宠窗口范围内时显示。
- 角色始终保持原始宽高比，以原始 `192×208` 帧和高 DPI 画布重新渲染。
- 缩小后再次放大不会使用低清缓存。
- 气泡和输入框是独立跟随浮窗，会避开角色并跟随 Maidie 移动。

### 动画系统

- 主模型为 hatch-pet 标准 `1536×1872`、8 列 9 行 WebP 图集。
- 每格 `192×208`，动画速度不受窗口尺寸影响。
- 动作切换包含约 `160ms` 交叉过渡，减少突然跳帧。
- 支持通过 `assets/actions/actions.json` 加载额外动作条。
- 外部动作具备独立帧率、持续时间、冷却时间、优先级和触发条件。
- 待机时瞳孔跟随光标；眨眼帧、走路和其他动作不会错误应用眼球覆盖。

### 移动与自主行为

- 加速度、速度、目标点和屏幕边界由独立移动控制器管理。
- 低速自动切换 `walk`，高速自动切换 `run`，速度归零后进入 `idle`。
- 自动游走、目的性停顿、屏幕边缘避让。
- 偶尔靠近光标；可在配置中开启持续光标追逐。
- 自主停顿期间可能播放瞌睡动作。

### 鼠标与键盘互动

- 单击头顶：摸头反应，不调用 AI。
- 在头顶按住并左右来回滑动：识别为连续抚摸。
- 在头顶明显纵向移动或单向大幅移动：仍然拖动窗口。
- 单击脸颊：戳脸反应。
- 单击身体：调用 AI 进行自然回复。
- 向右拖动并松手：播放晕乎动作。
- 双击 Maidie，或按 `Enter`、空格：打开聊天输入框。
- 输入框按 `Esc`、失去焦点、发送完成或 10 秒无操作后自动收起。
- 输入过程中无操作计时会自动重置。

### AI 与聊天

- DeepSeek/OpenAI Chat Completions 兼容接口。
- SSE 流式回复，气泡会随分块实时更新。
- 日常交流走聊天模型；代码、报错、编译、SSH、Linux、调试和架构等内容走技术模型。
- Maidie 聊天默认最多两句话；技术模式允许较完整的说明。
- 所有最终回复统一规范化为五字段：

```json
{
  "text": "回复正文",
  "emotion": "idle|thinking|excited|sad",
  "action": "talk|thinking",
  "state": "talking|thinking",
  "source": "chat|codex"
}
```

`source: "codex"` 是项目内部保留的“技术路由”标签；当前默认技术模型仍由
DeepSeek 提供，不代表正在调用 OpenAI Codex。

### 人格与记忆

- 温柔傲娇、元气活泼、安静治愈、优雅女仆四种预设。
- 支持自定义人格描述，保存后立即生效。
- JSON 保存最近 10 条聊天。
- 右键可以查看或清除最近聊天。
- 已预留 SQLite、向量记忆和多角色扩展位置。

## 核心状态与优先级

中央状态机是唯一状态来源，状态只能通过 `PetController` 修改。

| 状态 | 用途 |
|---|---|
| `idle` | 待机、眨眼、视线跟随 |
| `walk` | 低速移动 |
| `run` | 高速移动 |
| `talking` | AI 回复或情绪表达 |
| `thinking` | AI 请求、等待用户输入 |
| `reacting` | 摸头、戳脸、拖动等互动 |
| `sleeping` | 瞌睡和休息行为 |

行为优先级从高到低：

1. 用户点击、摸头、戳脸、拖动。
2. 光标互动。
3. AI 思考和说话。
4. 自动游走、停顿和瞌睡。
5. 普通待机。

## 当前动画与触发方式

### 主图集动画

| 动画 | 用途 |
|---|---|
| `idle` | 待机与眨眼 |
| `walk-left/right` | 左右慢速移动 |
| `run-left/right` | 左右快速移动 |
| `thinking` | AI 工作中 |
| `talking` | 普通回复 |
| `waiting` | 等待用户输入 |
| `review` | 技术回复或审阅 |
| `failed` | 请求失败或低落 |
| `happy` | 开心跳跃 |
| `reacting` | 普通互动 |
| `sleeping` | 休息状态 |

### 外部动作条

| 动作 | 触发方式 | 冷却时间 |
|---|---|---:|
| `headpat` | 点击头顶或左右抚摸 | 850ms |
| `facepoke` | 点击脸颊 | 900ms |
| `shy` | 可爱、喜欢、漂亮、cute、love 等表达 | 5s |
| `celebrate` | 成功、完成、搞定、感谢、success 等表达 | 4s |
| `sleepy` | 自主行为偶发 | 30s |
| `dizzy-right` | 向右拖动超过阈值并松手 | 1.5s |

完整配置位于 `assets/actions/actions.json`。

## 安装与启动

### 环境要求

- Windows 10/11。
- Python 3.10 或更高版本。
- 推荐使用独立虚拟环境。

### 快速启动

双击：

```text
start_maidie.bat
```

脚本会在首次启动时创建 `.venv` 并安装依赖。

### 手动启动

```powershell
cd "C:\Users\85949\Desktop\桌宠\maidie\maidie_desktop_pet"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

主要依赖：

- `PyQt6`：桌面窗口与交互。
- `requests`：AI API 和 SSE 流式传输。
- `Pillow`：导入绿幕动作条时使用。

## 模型与 API 配置教程

### 方法一：使用右键设置界面（推荐）

1. 启动 Maidie。
2. 右键角色。
3. 选择“性格与模型设置”。
4. 打开“模型与 API”页。
5. 选择 DeepSeek 或其他 OpenAI 兼容接口。
6. 填写 Base URL、聊天模型、技术模型和 API Key。
7. 点击“保存并立即应用”。

Key 输入框使用密码模式。已有 Key 时留空会保留原值，不会清空配置。

### 方法二：使用环境变量（更安全）

仅对当前 PowerShell 窗口生效：

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

重新启动 Maidie 后生效。使用 DeepSeek 接口时，环境变量优先于 JSON 中保存的 Key。

### 方法三：编辑 config.json

配置文件路径：

```text
config/config.json
```

完整示例：

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
  }
}
```

### 配置字段说明

| 字段 | 说明 |
|---|---|
| `ai.provider` | `deepseek` 或自定义兼容接口标识 |
| `ai.api_key` | 聊天接口 Key；推荐使用环境变量 |
| `ai.base_url` | OpenAI Chat Completions 兼容地址，不要以 `/` 结尾 |
| `ai.model` | 日常聊天模型 |
| `ai.timeout` | 聊天请求超时秒数 |
| `codex.model` | 技术问题使用的模型 |
| `codex.timeout` | 技术请求超时秒数 |
| `personality.preset` | 人格预设 ID |
| `personality.custom_prompt` | 自定义人格；预设为 `custom` 时使用 |
| `movement.walk_speed` | 自动慢走目标速度 |
| `movement.run_speed` | 自动奔跑目标速度 |
| `movement.walk_threshold` | 超过该速度进入 `walk` |
| `movement.run_threshold` | 超过该速度进入 `run` |
| `movement.acceleration` | 加速度，越高启动和转向越快 |
| `movement.cursor_chase` | 是否允许持续跟随光标 |
| `window.width/height` | 启动尺寸 |
| `window.minimum_width/height` | 允许缩小的下限 |
| `window.always_on_top` | 是否始终置顶 |
| `window.opacity` | 整体窗口透明度，范围 `0.0–1.0` |

安全提示：`config.json` 中的 Key 是明文。不要把包含真实 Key 的配置提交到公开仓库、
截图或发送给他人；长期使用时优先选择环境变量。

## 性格配置

在右键“性格与模型设置”中选择：

| ID | 显示名称 |
|---|---|
| `gentle_tsundere` | 温柔傲娇 |
| `cheerful` | 元气活泼 |
| `healing` | 安静治愈 |
| `elegant_maid` | 优雅女仆 |
| `custom` | 自定义 |

选择“自定义”后，在文本框中描述希望的语气、亲密程度和表达习惯。设置会写入
`config/config.json` 并热更新，无需重启。

## 联网查询

联网查询插件默认关闭，不会在用户无感知时发起网络请求。开启步骤：

1. 右键 Maidie，打开“性格与模型设置”。
2. 进入“联网查询”页，勾选联网开关。
3. 选择 Tavily，填写搜索 API Key，并按需设置超时和是否显示来源。
4. 点击“保存并立即应用”，无需重启。

开启后，包含“查一下”“搜索”“联网看看”“最新”“天气”“现在几点”或“官方文档”等意图的问题会先取得搜索摘要，再交给现有 AI 生成自然回答。网络超时、服务异常、没有 Key 或没有结果时，Maidie 会给出友好提示，不会退出程序。

隐私提示：联网时只会向所选第三方搜索服务发送当前用户问题和必要的查询关键词，不会自动上传最近聊天记录。搜索服务可能依据其自身隐私政策记录请求；如不接受，请保持联网开关关闭。搜索 API Key 以明文保存在本地 `config/config.json`，请勿提交到公开仓库。

## Agent 核心系统

Maidie 会先判断输入属于普通聊天、单一工具查询，还是需要拆解执行的任务。整体优先级为：

```text
Tool → Memory → LLM
```

- 普通聊天继续使用原有 chat/codex 路由。
- “现在几点”“天气”等单一查询直接使用确定性工具。
- “帮我查明天天气适不适合跑步”等组合任务会进入 Agent 流程。

任务流程为：读取长期记忆和最近聊天 → 判断意图 → Planner 生成严格 JSON 步骤 → 按顺序执行 time、weather、search 或 memory 工具 → 将步骤结果交给现有模型综合。Planner 只负责规划，不直接回答；工具也不会自行调用模型。模型不可用、计划格式无效或某一步失败时，会使用受限的本地计划或友好失败结果降级，不会导致桌宠退出。

任务执行期间 Maidie 使用现有 `thinking` 状态；成功后进入 `talking` 并触发开心反馈，失败时播放 `failed` 动画。最终 AI 回复仍保持 `text`、`emotion`、`action`、`state`、`source` 五字段格式。

## 记忆系统

Maidie 使用本地 SQLite 数据库保存最近对话和长期记忆。数据库位于：

```text
memory/memories.db
```

记忆分为三类：

- `chat`：最近 20 条对话，用于保持短期上下文。
- `fact`：名字、正在进行的项目等适合长期保留的用户信息。
- `preference`：喜欢的工具、表达方式和其他用户偏好，读取优先级较高。

每轮对话结束后，Maidie 会在后台使用当前聊天模型，从本轮“用户问题 + Maidie 回答”中提取事实和偏好。回答新问题前，会读取重要性最高的 20 条长期记忆并作为用户背景加入提示词；这不会改变界面或 AI 的五字段输出格式。没有配置可用的模型 API Key 时，聊天仍可保存，但不会执行长期记忆提取。

安全与隐私：API Key、密码、令牌、证件、银行卡、联系方式、住址和健康隐私等内容会被过滤，不写入数据库。记忆提取失败或数据库暂时不可用时会自动降级，不影响桌宠继续运行。右键菜单中的“清除记忆”会清除最近聊天以及长期事实和偏好。

`memory/memories.db`、`memory/memories.db-wal` 和 `memory/memories.db-shm` 已被 `.gitignore` 排除，不会随正常的 Git 提交推送到远程仓库。数据库仅保存在当前电脑上。

## 添加新动作

### 素材建议

- 单张横向绿幕动作条。
- 所有帧从左到右排列，宽度平均分割。
- 推荐 6–8 帧。
- 人物比例、基线、服装和视角保持一致。
- 背景使用纯绿色，避免阴影、文字、网格和跨帧元素。

### 导入动作条

```powershell
python tools/import_action_strip.py "输入动作.png" "assets/actions/action-name.webp" --frames 6
```

保留跳跃等纵向移动：

```powershell
python tools/import_action_strip.py "庆祝.png" "assets/actions/celebrate.webp" `
  --frames 6 --preserve-vertical
```

移除地面阴影或其他独立组件：

```powershell
python tools/import_action_strip.py "动作.png" "assets/actions/action-name.webp" `
  --frames 6 --largest-component
```

导入器会：

- 自动去绿和抑制绿边。
- 使用统一比例缩放所有帧。
- 输出标准 `192×208` 帧。
- 清除完全透明像素中的隐藏 RGB。
- 生成无损 WebP 动作条和 GIF 预览。

然后在 `assets/actions/actions.json` 注册：

```json
{
  "action-name": {
    "file": "action-name.webp",
    "frames": 6,
    "interval": 150,
    "render_scale": 1.0,
    "loop": false,
    "duration_ms": 1100,
    "cooldown_ms": 1000,
    "priority": 80,
    "state": "reacting",
    "triggers": ["触发词"]
  }
}
```

动作元数据由 `ActionRegistry` 读取，不需要把关键词继续写进 `PetController`。

## 项目结构

```text
maidie_desktop_pet/
├── main.py                     # 程序入口与依赖装配
├── start_maidie.bat            # Windows 快速启动
├── requirements.txt
├── ai/
│   ├── client.py               # OpenAI 兼容接口与 SSE 流式请求
│   ├── router.py               # 日常聊天/技术请求路由
│   └── prompt.py               # Maidie 与技术模式提示词
├── animation/
│   ├── base.py                 # 动画后端接口
│   └── atlas.py                # 主图集与外部动作播放器
├── assets/
│   ├── spritesheet.webp        # hatch-pet 主图集
│   ├── pet.json
│   └── actions/                # 外部动作、预览和动作配置
├── config/
│   └── config.json             # 模型、人格、移动和窗口配置
├── core/
│   ├── actions.py              # 动作注册表、触发词与冷却
│   ├── behavior.py             # 自主行为规划
│   ├── movement.py             # 速度、加速度与边界
│   ├── pet.py                  # 唯一中央控制器
│   ├── settings.py             # 配置持久化与热更新
│   ├── state.py                # 状态机与行为优先级
│   └── plugins/                # 插件扩展接口
├── input/
│   ├── gesture.py              # 抚摸与拖动手势识别
│   ├── manager.py              # 全局光标追踪
│   └── resize.py               # 无边框窗口缩放
├── memory/
│   └── memory.py               # 最近 10 条 JSON 记忆
├── tools/
│   └── import_action_strip.py  # 动作条导入工具
├── ui/
│   ├── bubble.py               # 跟随式流消息气泡
│   ├── chat_input.py           # 跟随式聊天输入框
│   ├── dialogs.py              # 最近聊天、人格和模型设置
│   ├── resize_handle.py        # 奶油白缩放角标
│   ├── sprite.py               # 高 DPI 角色渲染与视线跟随
│   └── window.py               # 透明桌面窗口
└── tests/                       # 单元测试
```

## 扩展接口

- 动画：实现 `AnimationBackend` 可替换为 Live2D、Spine 或其他渲染器。
- AI：实现 `AIClient` 可接入其他 OpenAI 兼容模型或本地模型。
- 插件：继承 `core.plugins.Plugin`，监听状态、点击、消息和配置事件。
- 输入：可继续增加全局热键、STT 和摄像头输入。
- 输出：可增加 TTS、口型同步和音效。
- 记忆：可将 `ConversationMemory` 替换为 SQLite 或向量数据库。

## 测试

运行全部测试：

```powershell
python -m unittest discover -v
```

当前测试覆盖：

- 状态优先级与锁定。
- 速度驱动的 idle/walk/run 切换。
- 屏幕边界保护。
- AI 路由与五字段输出。
- 配置保存和 Key 隐藏。
- 动作关键词与冷却。
- 抚摸、拖动手势区分。
- Qt 图集加载、缩放、跟随浮窗和动作恢复的集成检查。

## 常见问题

### 填了 Key 仍然无法聊天

1. 在右键设置中确认 Base URL 和模型名称。
2. 检查 `logs/maidie.log`。
3. 确认当前模型支持 `/chat/completions` 和 SSE 流式返回。
4. 如果同时设置了 `DEEPSEEK_API_KEY`，环境变量会覆盖 JSON Key。

### 气泡或输入框没有跟随

重新启动 Maidie 以加载最新代码。二者现在都是独立浮窗，并在每次角色移动时重新锚定。

### 动作没有播放

确认动作文件存在于 `assets/actions/`，文件名、帧数与 `actions.json` 一致，并检查动作冷却时间。

### 缩放后角色模糊

程序始终从原始帧重新渲染，不会累积低清缓存。放大超过素材原生分辨率后出现的柔化，
属于源图分辨率限制；需要更清晰时应提供更高分辨率模型或升级 Live2D。

### 如何退出

右键 Maidie，选择“退出 Maidie”。
