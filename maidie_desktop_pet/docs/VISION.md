# 千问视觉与屏幕理解

Maidie 已接入阿里云百炼 `qwen3-vl-flash`，用于按需理解当前窗口或屏幕内容。视觉模型只负责观察和提取结构化事实，DeepSeek 仍然负责推理、解释和最终回答。

## 当前已经实现

- 明确请求才截图，例如“你看看我现在屏幕这个报错是什么意思”。
- 优先截取 Windows 当前活动窗口，失败时自动退回全屏截图。
- 截图在内存中按比例缩小，默认最大宽度为 1280，并编码为 JPEG。
- 通过阿里云百炼 OpenAI-compatible API 调用 `qwen3-vl-flash`。
- 提取屏幕摘要、可见文字、任务类型、重要区域、用户意图和置信度。
- 将结构化视觉结果交给 DeepSeek，由 Synthesizer 生成最终用户回复。
- 支持代码报错、屏幕题目、文档、网页、图片内容和软件界面操作提示。
- 结构化结果默认缓存 5 秒；缓存不永久保存截图。
- 配置缺失、截图失败、网络错误和模型错误均返回友好提示，不会使桌宠退出。
- 设置保存后立即更新视觉客户端并清空旧缓存，无需重启；首次安装新依赖后仍需重启进程。
- 统一支持当前窗口、全屏、鼠标附近和手动框选四种截图范围。
- 手动框选使用非阻塞半透明 Overlay，按 Esc 或选区过小会取消且不调用视觉模型。

## 触发规则

明确请求会进入视觉流程，例如：

```text
你看看我的屏幕里面有什么
你看看我现在屏幕这个报错什么意思
你看看我现在屏幕这个题怎么写
帮我看一下屏幕
当前窗口里是什么
```

“帮我看一下”“这个怎么弄”“这个题怎么写”等模糊请求不会直接截图。Maidie 会先询问：“你是想让我看当前屏幕吗？”普通聊天也不会触发截图。

## 配置

右键 Maidie，打开“性格与模型设置”，选择“千问视觉”标签页，填写 Workspace ID、API Key、模型、地域、图片最大宽度、JPEG 质量和短缓存时间。

Workspace ID 是业务空间地址中的主机名前缀。例如地址为 `https://llm-example.cn-beijing.maas.aliyuncs.com/compatible-mode/v1` 时，只填写 `llm-example`。

也可使用环境变量，环境变量优先于界面保存值：

```powershell
$env:DASHSCOPE_API_KEY = "你的百炼 API Key"
$env:DASHSCOPE_WORKSPACE_ID = "llm-example"
$env:QWEN_VL_MODEL = "qwen3-vl-flash"
$env:QWEN_VL_REGION = "cn-beijing"
$env:VISION_MAX_WIDTH = "1280"
$env:VISION_JPEG_QUALITY = "85"
$env:VISION_CACHE_TTL_SECONDS = "5"
python main.py
```

Base URL 自动拼接为 `https://{WorkspaceId}.{Region}.maas.aliyuncs.com/compatible-mode/v1`。

## OCR 与视觉模型的分工

| 能力 | 本地 OCR | 千问视觉 |
|---|---|---|
| 触发方式 | “主动行为”中的独立定时开关 | 用户明确要求看屏幕时 |
| 处理位置 | 本地 Tesseract | 阿里云百炼 |
| 主要职责 | 提取屏幕文字和基础上下文 | 理解画面并输出结构化视觉事实 |
| 最终回答 | 不负责 | 不负责，交给 DeepSeek |
| 是否互为降级 | 否 | 否 |

关闭定时 OCR 不会影响按需千问视觉。目前 OCR 不是千问视觉失败时的备用方案。

## 测试方法

1. 执行 `python -m pip install -r requirements.txt`。
2. 在“千问视觉”页保存 Workspace ID 和 API Key。
3. 打开记事本或 IDE，显示一段容易识别的文字或报错。
4. 对 Maidie 说：“你看看我现在屏幕这个报错是什么意思”。
5. 查看 `logs/maidie.log` 中的 `vision` 日志；它记录尺寸、JPEG 大小、`task_type`、`confidence` 和 `cache_hit`，不记录 API Key。

自动化测试：

```powershell
python -m unittest tests.test_qwen_vision tests.test_settings -v
```

## 当前限制

- 当前没有独立的本地图片文件选择器；“看图”指理解当前屏幕中显示的图片。
- OCR 与千问视觉尚未组合成自动降级链路。
- 短缓存按截图范围复用结构化结果，不保存原始截图。
- 百炼服务可用性、配额和模型权限由对应阿里云账号与业务空间决定。
