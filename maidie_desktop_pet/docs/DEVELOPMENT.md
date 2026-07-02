# 开发指南

## 项目结构

```text
maidie_desktop_pet/
├── main.py                     # 应用入口与依赖装配
├── start_maidie.bat            # Windows 快速启动
├── requirements.txt
├── ai/                         # 旧兼容 AI 客户端与路由
├── animation/                  # 图集与动画后端
├── assets/
│   ├── spritesheet.webp
│   ├── pet.json
│   └── actions/                # 外部动作素材与配置
├── config/                     # 本地配置（不要提交真实 Key）
├── core/
│   ├── brain/                  # 生产 Router、Planner、Executor、Synthesizer
│   ├── tools/                  # 结构化工具实现与注册表
│   ├── awareness/              # 窗口、应用、鼠标和剪贴板感知
│   ├── vision/                 # 可选屏幕 OCR
│   ├── experience/             # 情绪、注意力、对话和语音节奏
│   ├── proactive/              # 主动行为
│   ├── fence.py                # 围栏约束
│   ├── movement.py             # 移动计算
│   ├── pet.py                  # 中央协调器
│   └── state.py                # 状态机与优先级
├── input/                      # 手势、全局输入和缩放
├── memory/                     # SQLite 记忆实现与本地数据库
├── tools/                      # 动作素材导入脚本
├── ui/                         # 窗口、气泡、输入框、围栏和角色渲染
└── tests/                      # unittest 与 Qt offscreen 测试
```

## 架构约束

- 生产 AI 管线位于 `core/brain/*`；不要把新功能加入旧 `ai/router.py` 或旧 Agent 编排层。
- `PetController` 保持协调器职责，不应成为业务逻辑集合。
- Router 不执行工具；Planner 不生成最终回复；工具只返回结构化数据；Synthesizer 负责最终文本。
- Planner 和模型参数不可信；系统写操作必须由执行层确认。
- 网络、OCR、文件扫描和模型调用不得阻塞 GUI 线程。
- 后台线程不得直接操作 QWidget、气泡、角色窗口或 QTimer。
- 每项行为改动都应增加或更新 unittest。

完整链路见[技术架构](TECHNICAL_OVERVIEW.md)，安全约束见[隐私与安全](PRIVACY_AND_SAFETY.md)。

## 扩展接口

- 动画：实现 `AnimationBackend`，可接入 Live2D、Spine 或其他渲染器。
- 动作：使用 WebP 动作条和 `ActionRegistry`，详见[动作系统](ACTIONS.md)。
- AI：实现兼容客户端，或使用 OpenAI Chat Completions 兼容接口。
- 工具：继承工具基类并注册到 `ToolRegistry`；保持结构化输出。
- 搜索：为搜索服务增加新的 provider adapter。
- 插件：扩展 `core.plugins.Plugin`，监听有限的状态、点击、消息和配置事件。
- 感知：扩展 `AwarenessContext`，新敏感能力应默认关闭。
- 记忆：可在现有接口后增加向量检索，但需保留敏感信息过滤和本地边界。
- 输入输出：可增加 STT、TTS、口型同步和音效。

## 测试

在 `maidie_desktop_pet` 目录运行：

```powershell
python -m unittest discover -v
```

测试覆盖包括：

- 状态优先级、锁定、方向和屏幕边界。
- `idle/walk/run` 速度切换和自主行为。
- 动作注册、触发、冷却、摸头和拖动手势。
- 流式分句、气泡增量显示、尺寸动画和背景可读性。
- Qt 主线程响应性和后台任务生命周期。
- LLM 路由、正则降级、Planner、Executor 和工具数据边界。
- 时间、天气、搜索、屏幕、记忆和网络错误降级。
- 围栏 clamp、snapback、对话池、overlay 生命周期、移动和缩放。
- 配置默认值、保存行为和 API Key 隐藏。

Qt UI 测试使用 `QT_QPA_PLATFORM=offscreen`，不需要显示真实窗口。

## 提交前检查

1. 确认没有提交 `config/config.json` 中的真实 Key。
2. 确认没有提交 `memory/memories.db*`。
3. 运行完整 unittest。
4. 检查文档与当前默认配置一致。
5. 对 UI 改动同时检查高 DPI、焦点、鼠标穿透和关闭生命周期。

## 维护打包配置

- `build_exe.bat` 使用当前激活的 Python/conda 环境，不依赖项目 `.venv`。
- `maidie.spec` 会递归收集 `assets/` 和 `docs/`，新增普通素材无需逐项登记。
- 新增运行时数据目录时，应在 `maidie.spec` 的 `datas` 中加入整个目录。
- 新增通过字符串动态导入的插件包时，应加入 `hiddenimports` 或使用 `collect_submodules`。
- 新增配置字段时，同时更新 `packaging/config.json`，但绝不能写入真实 Key。
- 发布前应从干净目录运行 `build_exe.bat`，启动 `dist/Maidie/Maidie.exe` 并检查动画、配置写入、日志和记忆数据库。

## 未来扩展方向

- Live2D 或 Spine 动画后端。
- TTS、STT、口型同步和音效。
- 更多搜索 provider 和工具插件。
- 受严格确认保护的更多桌面能力。
- 向量记忆和更清晰的记忆管理界面。
- 更完整的来源展示和可访问性支持。
