# 千问视觉与屏幕理解

Maidie 使用阿里云百炼的 `qwen3-vl-flash` 按需提取屏幕中的结构化事实。视觉模型不直接生成最终用户回复；Synthesizer（通常使用配置的 DeepSeek / 兼容模型）负责分析和表达。

## 调用方式

`QwenVLClient` 通过 OpenAI-compatible SDK 调用 DashScope / 百炼兼容接口：

```text
https://{WorkspaceId}.{Region}.maas.aliyuncs.com/compatible-mode/v1
```

视觉调用需要用户自己的 Workspace ID、API Key、区域和模型权限。

## 支持的截图范围

| 范围 | 说明 | 示例 |
|---|---|---|
| 当前窗口 | 读取当前外部活动窗口，不静默扩大为全屏 | “看当前窗口” |
| 全屏 | 用户明确要求后读取整个屏幕 | “看看整个屏幕” |
| 鼠标附近 | 延迟约三秒后读取鼠标附近区域 | “看鼠标这块” |
| 手动框选 | 用户拖拽选择区域；Esc 或过小选区取消 | “我框选一下给你看” |

普通聊天不截图。“帮我看看”“这个怎么弄”等模糊请求会先确认。

## 数据管线

```text
明确视觉请求
  → ScreenTool / VisionService
  → 按指定范围截图
  → 缩放与 JPEG 压缩
  → qwen3-vl-flash
  → VisionContext 结构化事实
  → Synthesizer / MaidieStyle
  → 最终回复
```

结构化事实可包含屏幕摘要、可见文字、任务类型、重要区域、建议查看位置和置信度。Qwen VL 的输出仍属于外部模型结果，Synthesizer 不应补全未观察到的内容。

## 配置

在“性格与模型设置 → 千问视觉”中配置 Workspace ID、API Key、模型、区域、最大图片宽度、JPEG 质量、缓存时间、默认范围和鼠标附近区域尺寸。

环境变量优先：

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

完整字段见[配置说明](CONFIG.md)。

## 缓存策略

- 相同截图范围的结构化结果默认短缓存 5 秒，可配置为 0–60 秒。
- 不同范围不共享缓存。
- 手动框选不使用缓存。
- “重新看”“重新截图”“现在呢”等刷新表达会请求新截图。
- 清除视觉上下文或更新视觉设置会清空缓存。
- 原始截图不进入永久缓存或本地记忆。

视觉会话还可在约 120 秒内复用最近的结构化结果处理“那怎么办”“我该改哪里”等追问；需要画面更新时应明确刷新。

## OCR 与 Qwen VL

| 能力 | 本地 OCR | Qwen VL |
|---|---|---|
| 默认状态 | 关闭 | 明确请求且配置可用时调用 |
| 处理位置 | 本机 Tesseract | 阿里云百炼 |
| 输入 | 屏幕截图 | 压缩截图和用户问题 |
| 输出 | 文字与基础上下文 | 结构化视觉事实 |
| 最终回答 | 不负责 | 不负责 |

两者不是自动降级关系。关闭 OCR 不会关闭按需视觉。

## 隐私边界

- 仅处理用户明确指定的范围，不因失败自动扩大截图范围。
- 截图会发送到第三方云服务；不要对敏感窗口触发视觉。
- 日志可记录范围、尺寸、JPEG 大小、任务类型、置信度和缓存命中，但不应记录 Key。
- API Key 在 JSON 中为本地明文，推荐环境变量。

详见[隐私与安全边界](PRIVACY_AND_SAFETY.md)。

## 测试

自动化测试：

```powershell
python -m unittest -v tests.test_qwen_vision tests.test_vision_scopes `
  tests.test_vision_session_followup tests.test_screen_pipeline_safety tests.test_settings
```

手动验证时，可打开记事本或 IDE 显示非敏感文本，再分别测试当前窗口、鼠标附近、全屏和手动框选。不要把真实 Key 或私人截图附到 issue。

## 当前限制

- 没有独立的本地图片文件选择器；“看图”指屏幕中正在显示的图片。
- OCR 与 Qwen VL 尚未组合成自动降级链路。
- 视觉结果受模型权限、配额、网络和画面清晰度影响。
