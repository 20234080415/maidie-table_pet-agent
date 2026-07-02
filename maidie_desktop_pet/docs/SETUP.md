# 安装与启动

## 环境要求

- Windows 10 或 Windows 11
- Python 3.10 或更高版本
- 推荐使用独立虚拟环境
- 可选：Tesseract OCR 及中英文语言包

## 快速启动

双击项目目录中的：

```text
start_maidie.bat
```

脚本会在首次启动时创建 `.venv` 并安装 `requirements.txt` 中的依赖。

## 手动启动

在 `maidie_desktop_pet` 目录运行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

主要依赖：

- `PyQt6`：桌面窗口、动画和交互。
- `requests`：AI API、SSE 流和联网工具请求。
- `Pillow`：动作条导入和图像处理。
- `pytesseract`：可选的本地 OCR 调用。

## OCR 安装

OCR 默认关闭；不使用屏幕识别时无需安装 Tesseract。

Maidie 会自动识别默认安装路径：

```text
C:\Program Files\Tesseract-OCR\tesseract.exe
```

语言包目录应至少包含：

```text
C:\Program Files\Tesseract-OCR\tessdata\eng.traineddata
C:\Program Files\Tesseract-OCR\tessdata\chi_sim.traineddata
```

检查安装和语言包：

```powershell
& "C:\Program Files\Tesseract-OCR\tesseract.exe" --list-langs
```

启用 OCR 前，请阅读[隐私与安全边界](PRIVACY_AND_SAFETY.md)，再在设置界面开启屏幕理解。

## 打包 Windows EXE

先激活用于构建的 conda 或其他 Python 环境，然后运行：

```powershell
.\build_exe.bat
```

脚本会在当前环境安装 `requirements.txt` 和 `requirements-build.txt`，再通过 `maidie.spec` 构建。输出位于：

```text
dist\Maidie\Maidie.exe
```

这是 one-folder 发布包。复制或发布时必须保留整个 `dist\Maidie` 目录，不能只拿走 EXE。该结构便于后续增加动作、素材、文档和插件，也比 one-file 模式更容易排查资源问题。

构建包使用 `packaging/config.json`，其中不应出现真实 Key。首次运行后可在发布目录的 `config/config.json` 中配置，也可以使用环境变量。

## 启动问题排查

- 无法创建虚拟环境：确认 `python --version` 可用且版本不低于 3.10。
- 缺少模块：激活 `.venv` 后重新执行 `python -m pip install -r requirements.txt`。
- OCR 不可用：检查可执行文件路径和 `eng`、`chi_sim` 语言包。
- API 请求失败：检查 Base URL、模型名称和 Key，详见[配置说明](CONFIG.md)。
- 打包失败：确认当前环境为 Python 3.10+，并检查 PyInstaller 输出；不要只复制生成的 EXE。
