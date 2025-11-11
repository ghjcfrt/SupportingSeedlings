# 打包与分发指南（PyInstaller / 凭据管理）

本文档介绍如何在本地将扶苗（SupportingSeedlings）打包为可分发的可执行文件（Windows 为例），以及在打包过程中如何安全管理讯飞 API 凭据与模型文件。

## 1. 选择打包方式

推荐使用 [PyInstaller](https://pyinstaller.org/)；仓库中已提供 `main.spec` 作为基础配置。也可以使用 nuitka / cx_Freeze 等其它方案，但需自行适配依赖与数据文件。

## 2. 依赖准备

1) 使用 uv 同步依赖：

```powershell
uv sync
```

2) 如需 CUDA，请确保安装的 torch 与系统驱动匹配；否则可使用 CPU 版。

## 3. 基本打包命令

最简打包（生成 dist/main.exe）：

```powershell
pyinstaller .\main.spec
```

若需临时测试（单文件、控制台模式）：

```powershell
pyinstaller -F -n SupportingSeedlings main.py
```

说明：
- `main.spec` 当前未显式收集模型权重与其它数据文件（如 `models/yolo/yolo11n.pt`）。首次运行时程序会尝试在本地目录加载；如需离线分发，可手动添加 datas。
- 若需要将 `models/yolo/yolo11n.pt` 打包进可执行，修改 spec：

```python
# 在 Analysis(...) 中添加，例如：
datas=[('models/yolo/yolo11n.pt', 'models/yolo')]
```

## 4. 凭据与配置文件处理

严禁将真实的 `XF_APPID / XF_API_KEY / XF_API_SECRET` 硬编码或打包进公共发行物。推荐以下方案：

方案 A（外部 JSON）：
- 在发行物旁放置 `config.json`（基于 `config_example.json`）。
- 用户自行填写凭据；程序启动时自动读取并写入环境变量。

方案 B（环境变量）：
- 不分发 `config.json`；在启动脚本或操作系统层设置环境变量。

方案 C（加密凭据，仅高级使用）：
- 使用外部安全存储（Windows Credential Manager / 环境变量注入脚本）在启动前注入。

在 spec 里避免将包含敏感值的 JSON 加入 `datas`。

## 5. 日志与调试

打包后若需要调试：
- 将 `LOG_LEVEL` 设为 `DEBUG`（放在发行物目录的 `config.json` 中）；
- 或在启动前设置环境变量：`$env:LOG_LEVEL="DEBUG"`。

若希望关闭控制台窗口（GUI 纯窗口体验）：
- 修改 spec 中的 `console=True` 为 `console=False`。

## 6. 模型与缓存管理

默认模型路径：`models/yolo/yolo11n.pt`。若模型较大或需要离线分发：
- 将权重文件放入发行包目录；
- 或在程序首次启动时下载（当前示例未包含自动下载逻辑，可在 `runtime_paths.py` 中扩展）。

缓存：程序会在当前工作目录优先查找权重；如需自定义路径，可扩展 `prefer_local_weights()`。

## 7. 体积优化建议

- 移除未使用的依赖（在 `pyproject.toml` 中精简）。
- 使用 PyInstaller 的 `--strip`（Linux/macOS）或 UPX（需自行下载并合法使用）。
- 将 GUI 资源（若后续添加图标/图片）按需压缩。

## 8. 常见问题

| 问题 | 可能原因 | 解决 | 
|------|----------|------|
| 运行时提示缺少 `websocket-client` | 打包时依赖未收集或环境混淆 | 确认 `pyproject.toml` 已含依赖并在干净虚拟环境打包 |
| 模型未找到 | 权重未被打包且运行目录无文件 | 将模型文件放入与 exe 同目录或在 spec 中加入 datas |
| 凭据缺失错误 | 未提供 config.json 或环境变量 | 按示例添加 `config.json` 或设置 XF_* 环境变量 |
| GUI 启动黑屏/闪退 | 缺少图形库或打包丢失 Qt 依赖 | 不要删除 PySide6 动态库；尝试不使用 `--onefile` 先确认 |

## 9. 发布清单建议

最小发行目录（示例）：

```
SupportingSeedlings/
	SupportingSeedlings.exe        # 主程序
	config.json                    # 用户自行填写/替换（不含真实密钥时可附带）
	models/                        # 权重目录（如含 yolo11n.pt）
	README_简要版.txt             # 简要使用说明（可基于主 README 截取）
```

可选附加：脚本 `start_gui.ps1` 设定环境变量后启动 GUI；脚本 `start_detect.ps1` 启动 CLI 检测（传入权重与摄像头索引）。

---

如需进一步的分发（例如创建 MSI 安装包或自动更新机制），可后续在此文档增补。

