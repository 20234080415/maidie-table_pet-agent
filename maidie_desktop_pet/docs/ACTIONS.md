# 动作系统

Maidie 的额外动画采用数据驱动的 WebP 动作条。动作素材位于 `assets/actions/`，注册信息位于 `assets/actions/actions.json`。

## 当前外部动作

| 动作 | 常见触发 | 默认冷却 |
|---|---|---:|
| `headpat` | 点击头顶或左右抚摸 | 850ms |
| `facepoke` | 点击脸颊 | 900ms |
| `shy` | 可爱、喜欢、漂亮等表达 | 5s |
| `celebrate` | 成功、完成、感谢等表达 | 4s |
| `sleepy` | 自主行为偶发 | 30s |
| `dizzy-right` | 向右拖动超过阈值并松手 | 1.5s |

具体值以 `actions.json` 为准。

## 素材建议

- 使用单张横向动作条，所有帧从左到右排列并等宽。
- 推荐 6–8 帧；人物比例、基线、服装和视角保持一致。
- 建议使用纯绿背景，避免文字、网格、阴影和跨帧元素。
- 需要保留跳跃等纵向位移时，不要让导入过程逐帧重新对齐基线。

## 导入动作条

基础用法：

```powershell
python tools/import_action_strip.py "输入动作.png" "assets/actions/action-name.webp" --frames 6
```

保留纵向位移：

```powershell
python tools/import_action_strip.py "庆祝.png" "assets/actions/celebrate.webp" `
  --frames 6 --preserve-vertical
```

只保留最大主体、移除独立阴影或杂项：

```powershell
python tools/import_action_strip.py "动作.png" "assets/actions/action-name.webp" `
  --frames 6 --largest-component
```

导入器会抑制绿边、统一帧缩放、输出 `192×208` 帧组成的无损 WebP，并清理透明像素中的隐藏 RGB。开发时也可生成 GIF 预览检查节奏。

## 注册动作

在 `assets/actions/actions.json` 中加入：

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

| 字段 | 说明 |
|---|---|
| `file` | 相对于 `assets/actions/` 的素材文件 |
| `frames` | 动作条帧数 |
| `interval` | 帧间隔，单位毫秒 |
| `render_scale` | 相对角色画布的渲染比例 |
| `loop` | 是否循环播放 |
| `duration_ms` | 动作总持续时间 |
| `cooldown_ms` | 再次触发前的冷却时间 |
| `priority` | 与其他状态竞争时的优先级 |
| `state` | 播放期间使用的角色状态 |
| `triggers` | 文本触发关键词 |

元数据由 `ActionRegistry` 加载。新增动作应优先修改配置，不要把触发词继续硬编码进 `PetController`。

## 验证建议

- 检查素材文件名、帧数和配置一致。
- 检查透明边缘、人物比例、基线和循环接缝。
- 运行完整测试：`python -m unittest discover -v`。

