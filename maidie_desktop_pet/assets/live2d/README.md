# Live2D 本地模型

此目录只保存说明，不保存第三方 Live2D 模型。`*.moc3`、`*.model3.json`、动作、物理和表情等资源已被 `.gitignore` 排除。

可从 Live2D 官方 Sample Data 获取测试模型，或选择自己有权使用的模型。下载、展示和分发前，请确认对应模型、纹理、动作及角色形象的许可；官方 Sample 也不等于可任意再分发。

推荐把模型放在仓库外并解压，例如：

```text
C:\Users\85949\Desktop\桌宠\live2d模型
├── Hibiki\...\hibiki.model3.json
├── Hiyori\...\hiyori_free_t08.model3.json
└── ...
```

在 Maidie 的“设置 → 动画 / Live2D”中选择该根目录并扫描。程序只记录入口路径，不会把模型复制进仓库。

## 真实预览（实验性）

设置页的“预览模型”会打开独立窗口，不会替换主桌宠 Sprite。预览需要：

1. 可选依赖 PyQt6-WebEngine。
2. 经过许可审查的 PixiJS、Live2D Cubism Core 和兼容的 Cubism 4 Web 加载器。

仓库不附带这些 runtime 文件。放置位置和预期文件名见 [`viewer/vendor/README.md`](viewer/vendor/README.md)。缺失时预览窗口会显示明确错误，而不是报告模型加载成功。
