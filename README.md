# SupportingSeedlings（SS）—— 扶苗（基于 YOLOv11）

SupportingSeedlings（简称 SS）是一个基于 Ultralytics YOLOv11 的实时目标检测小应用，提供图形界面与命令行两种使用方式，可将检测结果保存为图片与可选的 YOLO txt 标签。

## 简介

本项目支持：
- 实时检测摄像头/视频，保存可视化结果和可选 YOLO txt 标签到 `results/`
- Windows 下摄像头友好名称显示（DirectShow，可选依赖）


## 功能概述

主要功能：
- 图形界面（GUI）与命令行（CLI）双入口，开箱即用完成“实时目标检测”。
- 支持摄像头与离线视频流；可保存叠加检测框的图片与归一化 YOLO txt 标签。
- 自动/显式选择运行设备：CUDA、MPS 或 CPU；窗口内显示平滑处理后的 FPS。
- Windows 下可显示“摄像头友好名”（DirectShow 枚举），便于儿童或家长选择正确设备。
- 适配儿童场景的播报能力：可对画面中“中心物体”进行语音播报（去重、去抖）。

特色与核心优势：
- 即插即用的统一入口与简洁参数，兼顾“儿童可用性”和“开发者可配置性”。
- 推理尺寸在未指定时默认使用“原始帧尺寸”，尽量避免拉伸与比例失真。
- 帧率展示采用指数滑动平均法平滑处理，读数稳定、体验友好。
- 摄像头打开失败有连续计数与阈值保护，能快速失败并给出清晰提示。
- 环境变量前缀 SS_ 可覆盖默认值，方便集成与批处理；GUI 与 CLI 共用一套配置逻辑。


## 环境要求

- 操作系统：Windows 10/11 推荐（CLI 在 Linux/macOS 也可运行；MPS 需 macOS 支持）
- Python：3.11+
- GPU：可选；若使用 CUDA，请与 `torch==2.5.1+cu121` 和驱动版本匹配


## 安装

项目使用 `pyproject.toml` 与 [uv](https://docs.astral.sh/uv/) 管理依赖，推荐如下安装：

```powershell
# 安装 uv（若未安装）
python -m pip install -U uv

# 同步依赖（已配置 pytorch-cu121 源）
uv sync

# 验证
uv run python -V
```

说明：
- 若无需 CUDA，可改装 CPU 版 torch/torchvision（移除自定义索引，安装 CPU 轮子）。
- 只用 CLI 时，可跳过 GUI 依赖，但使用 `uv sync` 会按 `pyproject.toml` 全量安装。


## Windows 摄像头友好名称（DirectShow / pygrabber）

为在 Windows 下显示更友好的摄像头名称（而不是仅有的 `Camera n` 索引），项目提供 DirectShow 路径：

- DirectShow（pygrabber）：由 `ss_io/camera_utils.py` 枚举输入设备名称，依赖少、速度快。

说明：当前版本已移除基于 WMI（pywin32）的摄像头信息查询路径。

安装与验证（PowerShell）：

```powershell
# 安装/同步依赖
uv sync

# 自检：打印 DirectShow 设备名（pygrabber）
uv run python -c "from ss_io import get_directshow_device_names as g; print(g())"
```

注意事项：
- 顺序与索引：DirectShow 的枚举顺序与 OpenCV 的摄像头索引通常一致，但不保证 100% 对齐；发生不一致时，以能成功打开的索引为准。
- 虚拟摄像头：可能出现重复/虚拟设备（如会议软件虚拟摄像头）；可在系统设备管理器中禁用无关设备以简化列表。


## 快速开始

项目提供一个统一入口 `main.py`，以及可直接运行的模块入口。

1) 启动 GUI（PySide6）

```powershell
# 方式 A：统一入口
uv run python .\main.py

# 方式 B：直接运行模块
uv run python -m app.ss_gui
```

2) 命令行实时检测（YOLO）

```powershell
# 方式 A：统一入口
uv run python .\main.py detect --model models\yolo\yolo11n.pt --source 0 --conf 0.6 --save-txt

# 方式 B：直接运行模块
uv run python -m detection.cli --model models\yolo\yolo11n.pt --source 0 --conf 0.6 --save-txt
```

窗口聚焦时按 `q`（或 `--exit-key` 指定）退出。


## 扶苗助手与讯飞接入（心理助理/个性化推荐）

- 潜能开发小游戏：在 GUI 里点击“扶苗助手 → 潜能开发小游戏”，包含口算、图文算式、数独等。
- 心理助理：支持连续对话，基于讯飞 Spark 模型。首次使用需配置凭据。
- 个性化内容推荐：基于讯飞生成结构化 JSON 推荐列表，支持“一键重新生成”。

配置讯飞凭据（两种方式）：

1) 通过 JSON 文件（推荐，便于本地开发）：

- 复制根目录 `config_example.json` 为 `config.json`，填入你的 APPID/API_KEY/API_SECRET 等。
- 代码会在需要时读取该文件并写入环境变量（也可手动在启动前调用）。

2) 通过环境变量（PowerShell）：

```powershell
$env:XF_APPID = "你的AppId"
$env:XF_API_KEY = "你的ApiKey"
$env:XF_API_SECRET = "你的ApiSecret"
# 可选：如需自定义域/地址
# $env:XF_URL = "wss://sparkcube-api.xf-yun.com/v1/customize"
# $env:XF_DOMAIN = "max"

# 运行 GUI
uv run python -m app.ss_gui
```

注意：若未配置凭据，打开“心理助理/个性化推荐”对话框时会提示缺少环境变量，并不会导致整个程序崩溃。


## 配置说明（config.json / 环境变量）

项目在两类功能中读取配置：
- 讯飞 Spark 接入：凭据与请求参数（见 integrations/xfyun_client.py）。
- 日志与对话字号/行距：GUI 与对话框显示（见 app/ss_gui.py、app/advisor_dialog.py、app/recommend_dialog.py）。

优先级与读取路径：
- 环境变量优先于文件；
- 若未设置 XF_* 环境变量，客户端会自动查找当前工作目录或项目根目录下的 `config.json` 并写入环境变量再使用；
- `LOG_*`、`CHAT_*` 仅从 `config.json` 读取（如需覆盖可直接编辑该文件）。

建议做法：复制根目录的 `config_example.json` 为 `config.json`，按需填写/调整。

支持的配置键一览：

| 键 | 作用 | 示例/默认 |
|---|---|---|
| XF_APPID | 讯飞 AppID | your_appid_here |
| XF_API_KEY | 讯飞 API Key | your_api_key_here |
| XF_API_SECRET | 讯飞 API Secret | your_api_secret_here |
| XF_URL | SparkCube WebSocket 地址 | wss://sparkcube-api.xf-yun.com/v1/customize |
| XF_DOMAIN | 模型域 | max |
| XF_TEMPERATURE | 采样温度，越大越发散 | 0.95 |
| XF_TOPK | 采样 top-k | 6 |
| XF_MAX_TOKENS | 最大输出 token 数 | 4096 |
| LOG_LEVEL | 全局日志级别（DEBUG/INFO/WARN/ERROR） | INFO |
| LOG_TO_CONSOLE | 是否输出到控制台 | true |
| LOG_CONSOLE_LEVEL | 控制台日志级别 | INFO |
| CHAT_FONT_SIZE | 对话/推荐框字号（px） | 16 |
| CHAT_LINE_HEIGHT | 对话/推荐框行距 | 1.7 |

额外环境变量：
- 图形主题：`SS_FORCE_LIGHT=1` 可强制使用浅色主题；
- 检测 CLI 运行参数可用 `SS_` 前缀覆盖，详见“环境变量覆盖（前缀 SS_）”。

安全提示：请勿将真实的 XF_* 凭据提交到公共仓库。`config.json` 建议仅保留在本地环境。


## 环境变量覆盖（前缀 SS_）

除命令行外，也可用环境变量覆盖默认值（命令行优先）：

- `SS_MODEL_PATH` → `--model`
- `SS_DEVICE` → `--device`
- `SS_SOURCE` → `--source`
- `SS_SAVE_DIR` → `--save-dir`
- `SS_SAVE_TXT` → `--save-txt`
- `SS_SELECT_CAMERA` → `--select-camera`
- `SS_MAX_CAM_INDEX` → `--max-cam`
- `SS_CONF` → `--conf`
- `SS_IMG_SIZE` → `--img-size`
- `SS_WINDOW_NAME` → `--window-name`
- `SS_TIMESTAMP_FMT` → `--timestamp-fmt`
- `SS_EXIT_KEY` → `--exit-key`
- `SS_SHOW_FPS` → `--no-fps`（布尔，命令行为“关闭”）
- `SS_QUIET_CV` → `--quiet-cv`
- `SS_CAM_FAIL_LIMIT` → `--cam-fail-limit`

摄像头枚举阶段日志抑制：`SS_SUPPRESS_ENUM_ERRORS=1`（默认开启）。

示例（PowerShell）：

```powershell
$env:SS_MODEL_PATH = ".\models\yolo\yolo11n.pt"
$env:SS_SOURCE = "0"
$env:SS_CONF = "0.45"
uv run python -m detection.cli --save-txt
```


## 目录结构（节选）

```
app/                # GUI 与核心
  ss_gui.py         # 扶苗 GUI（PySide6）
  ss_core.py        # 扶苗核心逻辑

detection/          # YOLO 检测核心与 CLI 封装
  core.py           # YOLOConfig/YOLODetector，摄像头枚举、保存、TTS 播报
  api.py            # 门面导出（供 GUI/CLI 复用）
  cli.py            # 命令行入口（python -m detection.cli）

voice/              # TTS 工具
  tts.py, tts_queue.py, announce.py

ss_io/              # 设备与摄像头名称工具
  camera_utils.py   # DirectShow 设备名称（pygrabber）

models/             # 放置模型（例如 models/yolo/yolo11n.pt）
results/            # 运行输出
docs/STRUCTURE.md   # 目录说明
main.py             # 统一入口（gui/detect 路由）
pyproject.toml      # 依赖与工具配置（uv、ruff 等）
```


## 设计与开发（系统方案 / 核心技术 / 创新创意）

系统方案概览：
- 统一路由：`main.py` 将启动命令路由到 GUI（`app.ss_gui`）或检测 CLI（`detection.cli`）。
- 检测核心：`detection/core.py` 内的 `YOLOConfig`/`YOLODetector` 负责设备选择、摄像头/视频读取、YOLO 推理、绘制保存与 TTS 播报。
- 图形界面：`app/ss_gui.py` 采用 PySide6；UI 主线程仅负责渲染与交互，推理通过定时器驱动，确保界面不“卡顿”。
- 语音播报：`voice/tts_queue.py` 维护播报队列，具备去重与“包含词”抑制，避免重复打断；`voice/tts.py` 使用本地 TTS（如 pyttsx3）。
- 设备与友好名：`ss_io/camera_utils.py` 通过 DirectShow（pygrabber）枚举摄像头名称；在缺省情况下回退到 `Camera n`。

核心技术选型：
- 目标检测：Ultralytics YOLOv11（Python API），默认权重位于 `models/yolo/yolo11n.pt`。
- 多媒体与可视化：OpenCV 负责采集、绘制、显示与存储。
- GUI：PySide6 提供跨平台桌面界面能力。
- TTS：本地化 TTS 引擎（pyttsx3 等），无需联网即可播报。
- 硬件加速：优先使用 CUDA；次选 Apple MPS；否则回落到 CPU。

创新与人机工程细节：
- 儿童友好交互：默认展示摄像头友好名称，UI 尽量少项、少干扰；可选“中心物体”自动播报。
- 体验稳定性：
  - FPS 平滑与摄像头打开失败阈值保护；
  - 枚举阶段临时抑制 OpenCV 低层日志，避免刷屏影响体验；
  - YOLO txt 逐帧导出，便于后续复盘与再训练。


## 技术实现与算法逻辑（简要）

- 检测核心：`detection/core.py`
  - 构造 `YOLOConfig`（支持命令行 + 环境变量 SS_ 前缀，命令行优先）
  - `YOLODetector` 加载 Ultralytics YOLO 模型，读取视频帧并推理
  - 绘制结果、叠加 FPS、保存每帧与可选 YOLO txt；统计类别并做语音播报
- GUI：`app/ss_gui.py`
  - 简洁布局，支持打开图片与摄像头识物；可选自动播报中心物体与简介
  - 支持摄像头友好名（`ss_io.camera_utils`）、TTS 队列去抖


## 常见问题（FAQ）

1) CUDA/torch 报错？
- 使用 `--device cpu`；或安装与你驱动匹配的 CUDA 版 `torch/torchvision`。

2) 打不开摄像头或黑屏？
- 确认索引正确，尝试 0/1/2；关闭占用摄像头的软件；在 Windows 设备管理器检查设备。

3) GUI 启动失败（Qt 异常）？
- 确认安装 `PySide6`；无显示环境改用 CLI。

4) Windows 下无友好名称？
- 安装 `pygrabber`（DirectShow），否则显示 `Camera n`。


## 开源代码与组件使用情况说明

第三方组件（非完整列表）：
- Ultralytics YOLO（用于目标检测与权重管理）。
- PyTorch / TorchVision（模型计算与加速）。
- OpenCV-Python（视频采集、图像处理与可视化）。
- PySide6（桌面 GUI）。
- pyttsx3（本地 TTS 播报）。
- pygrabber（DirectShow 摄像头枚举，可选）。

使用与合规说明：
- 本项目仅封装与调用以上开源组件，遵循其各自开源许可；使用者在分发或商用时需同时遵守上游许可与模型权重条款（包括但不限于 Ultralytics 许可政策与相应权重/数据集许可）。
- `models/yolo/yolo11n.pt` 等权重文件用于学习与测试，请确保下载来源与用途合规；如需商用或二次分发，请查阅并遵守上游许可与条款。
- 仓库中预留了 `models/vosk/` 目录以存放语音相关模型资源；当前版本的 TTS 采用本地引擎（如 pyttsx3），vosk 资源为后续扩展预留，默认未启用。
- 如将本项目二次打包或分发，请在发行物中保留第三方许可证与致谢信息。


## 致谢

在此诚挚感谢以下开源项目、社区与工具，它们构成了 SupportingSeedlings 的基础生态：

### 核心模型与检测
- **Ultralytics YOLOv11**：高质量的目标检测框架与预训练权重支持。
- **PyTorch / TorchVision**：提供灵活的张量与加速后端（CUDA/MPS/CPU）。

### 图像与多媒体处理
- **OpenCV-Python**：摄像头与视频帧采集、绘制与编码保存。
- **NumPy**：高性能数组与数值运算支撑数据处理。

### GUI 与交互
- **PySide6 (Qt for Python)**：跨平台桌面界面开发能力。

### 语音与设备接入
- **pyttsx3**：本地文本转语音（TTS）引擎，免联网播报。
- **pygrabber (DirectShow)**：在 Windows 下枚举友好摄像头名称。
- **pywin32**：在部分 Windows 集成场景下的系统能力支持（现版本仅保留可选依赖）。

### 网络与对话接口
- **websocket-client**：与讯飞 Spark WebSocket 接口通信。

### 文档与格式
- **Markdown**：对话与推荐内容的渲染与格式支持。

### 构建与开发体验
- **uv**：高效的 Python 依赖与环境同步工具（在项目说明中推荐）。
- （潜在扩展）**Ruff / mypy 等质量工具**：若后续集成，将在代码质量与类型检查方面提供帮助。

### 预留与后续扩展
- **Vosk / 语音识别相关生态**：`models/vosk/` 目录为未来离线语音识别功能预留（当前版本未启用）。

### 社区与灵感
- 来自开源社区的 Issue、讨论与示例代码为本项目的设计优化提供了灵感与方向。

### 贡献者
欢迎通过 Issue / Pull Request 参与改进：如添加新游戏、改进检测策略、增强可访问性或扩展语音功能。未来可在此列出主要贡献者列表。

再次感谢以上项目与社区的支持。任何遗漏或需补充的致谢，欢迎反馈。

如有问题或建议，欢迎提交 Issue。

