# 安装与启动

## 千问视觉依赖

千问视觉通过 `openai` Python SDK 调用阿里云百炼兼容接口。升级已有环境后需要重新安装依赖并重启 Maidie：

```powershell
python -m pip install -r requirements.txt
```

如果界面提示网络或模型服务失败，而日志中出现 `No module named 'openai'`，说明启动 Maidie 的 Python 环境尚未安装新依赖。应在同一个虚拟环境中执行安装和启动。配置与连通测试见[千问视觉与屏幕理解](VISION.md)。

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

## 构建安装包

正式发布建议在 one-folder 产物外再封装 Inno Setup 安装包。先安装 [Inno Setup 6](https://jrsoftware.org/isinfo.php)，然后运行：

```powershell
.\build_installer.bat 0.1.0
```

版本参数可省略，默认使用 `0.1.0`。脚本每次都会先调用 `build_exe.bat`，确保安装包包含最新代码，然后输出：

```text
dist\installer\Maidie-Setup.exe
```

安装包按当前用户安装到 `%LOCALAPPDATA%\Programs\Maidie`，无需管理员权限，并创建开始菜单快捷方式。桌面快捷方式由用户在安装界面选择。

升级安装不会覆盖用户已经修改的 `config\config.json`；卸载时也会保留配置和本地记忆数据库，避免误删用户数据。若 Inno Setup 安装在自定义位置，可设置：

```powershell
$env:INNO_SETUP_COMPILER = "D:\Tools\Inno Setup 6\ISCC.exe"
.\build_installer.bat 0.1.0
```

`packaging/maidie.ico` 同时用于应用 EXE、安装程序和快捷方式。透明图标源文件为 `packaging/maidie-icon.png`。

## 启动问题排查

- 无法创建虚拟环境：确认 `python --version` 可用且版本不低于 3.10。
- 缺少模块：激活 `.venv` 后重新执行 `python -m pip install -r requirements.txt`。
- OCR 不可用：检查可执行文件路径和 `eng`、`chi_sim` 语言包。
- API 请求失败：检查 Base URL、模型名称和 Key，详见[配置说明](CONFIG.md)。
- 打包失败：确认当前环境为 Python 3.10+，并检查 PyInstaller 输出；不要只复制生成的 EXE。
- 安装包失败：确认已安装 Inno Setup 6，或设置 `INNO_SETUP_COMPILER`。
