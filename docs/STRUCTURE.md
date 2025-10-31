# 目录结构说明（儿童识物版）

目标：
- 提供稳定的 GUI 与 CLI 入口，简化使用与维护。

## 目录结构与入口说明

本项目采用模块化组织，核心分为 GUI、检测核心、语音与设备工具等部分。

顶层关键文件：
- `main.py`：统一入口，根据参数路由到 儿童识物 GUI/检测 CLI
- `pyproject.toml`：依赖与工具配置（uv 源、ruff 规则等）

核心目录结构：

```
app/
  kids_gui.py       # PySide6 GUI：打开图片/摄像头识物与播报
  kids_core.py      # 儿童识物核心逻辑与绘制

detection/
  core.py           # YOLOConfig/YOLODetector，摄像头枚举、推理与保存
  api.py            # 门面导出（供 GUI/CLI 统一调用）
  cli.py            # 命令行入口（python -m detection.cli）

voice/
  tts.py            # 本地 TTS（pyttsx3）
  tts_queue.py      # 播报队列与去重
  announce.py       # 数量播报工具

cor_io/
  camera_utils.py   # DirectShow 设备名称（pygrabber）
  device_utils.py   # 设备列表（CUDA/MPS/CPU）

models/             # 放置模型（例如 yolo11n.pt）
results/            # 运行输出（帧与 txt）
docs/STRUCTURE.md   # 本说明
```

可运行入口：
- GUI：`python .\main.py` 或 `python -m app.kids_gui`
- 检测 CLI：`python .\main.py detect ...` 或 `python -m detection.cli ...`

命令行与环境变量约定：
- 所有检测参数既可通过命令行提供，也可用 `COR_` 前缀环境变量覆盖默认值（命令行优先）。

输出组织：
- `results/frame_{id}_{ts}.jpg|.txt`：每帧可视化与 YOLO 标签（可选）

备注：
- Windows 下如需摄像头友好名称，请安装 `pygrabber`（DirectShow）。
- CUDA 使用请确保本机驱动与 `torch==2.5.1+cu121` 兼容；无需 CUDA 可改装 CPU 版 torch。


## 功能概述

主要能力：
- GUI 与 CLI 双入口（`main.py` 统一路由），即插即用完成实时目标检测。
- 支持摄像头与离线视频源；保存叠加检测框的图片与归一化 YOLO txt 标签。
- 自动/显式选择运行设备：CUDA、MPS 或 CPU；窗口内显示平滑处理后的 FPS。
- Windows 下显示“摄像头友好名”（DirectShow 枚举），便于快速选择正确设备。
- 面向儿童场景的语音播报：对“中心物体”进行播报，具备去重与去抖。

核心优势：
- 统一配置路径（命令行 + `COR_` 环境变量），GUI/CLI 共用；参数少而明确。
- 未指定推理尺寸时默认使用“原始帧尺寸”，尽量避免拉伸与比例失真。
- 帧率展示采用指数滑动平均平滑处理；摄像头读取失败有阈值保护。
- 摄像头枚举阶段临时抑制底层冗余日志，体验更友好。


## 系统方案与核心技术

系统方案：
- 路由与入口：`main.py` 统一分流到 GUI（`app.kids_gui`）或 CLI（`detection.cli`）。
- 检测核心：`detection/core.py` 提供 `YOLOConfig` 与 `YOLODetector`，负责设备选择、视频采集、YOLO 推理、绘制保存与 TTS 播报。
- 图形界面：`app/kids_gui.py` 使用 PySide6；UI 主线程渲染与交互，推理由定时器驱动避免卡顿。
- 语音播报：`voice/tts_queue.py` 管理播报队列并去重/去“包含词”；`voice/tts.py` 实现本地 TTS。
- 设备名称：`cor_io/camera_utils.py` 基于 DirectShow（pygrabber）枚举友好名；未安装时回退到 `Camera n`。

核心技术：
- 模型：Ultralytics YOLOv11（默认权重 `models/yolo/yolo11n.pt`）。
- 计算与加速：PyTorch/TorchVision，优先 CUDA，其次 Apple MPS，否则 CPU。
- 多媒体：OpenCV 负责采集、绘制、显示、存储。
- GUI：PySide6；TTS：pyttsx3（或兼容的本地 TTS 引擎）。


## 创新与人机工程细节

- 儿童友好：界面与参数尽量简洁；显示摄像头“友好名”；支持中心物体自动播报。
- 稳定体验：
  - FPS 平滑展示，避免读数抖动；
  - 摄像头打开/读取失败的连续阈值保护，快速失败；
  - 枚举阶段抑制冗余日志，减少噪声。
- 数据导出：每帧导出 YOLO txt（归一化坐标），便于复盘与再训练。


## 优化方案（可选实施）

性能与延迟：
- 模型层：启用 FP16（CUDA）；根据需求切换 YOLO 权重大小；可选导出 ONNX/TensorRT 以降低延迟（需验证）。
- 流水线层：采集/推理/显示三段异步化；控制相机缓冲（丢旧留新）降低端到端延迟；按需控制保存质量与频率。

稳定性与工程化：
- 摄像头热插拔与自动重试；结构化日志与更细粒度的错误码。
- 引入轻量跟踪（如 ByteTrack/StrongSORT）获得稳定目标 ID，提升播报节奏与体验。

可维护与发布：
- `pyproject.toml` 分组可选依赖（GUI/DirectShow/CUDA 等）；
- 提供一键打包（PyInstaller）与最小化运行时；
- `results/` 按 Session 分组，并提供清理脚本。


## 开源代码与组件使用情况说明

主要第三方组件（非完整列表）：
- Ultralytics YOLO（目标检测）
- PyTorch / TorchVision（模型计算与加速）
- OpenCV-Python（采集、图像处理、可视化）
- PySide6（桌面 GUI）
- pyttsx3（本地 TTS 播报）
- pygrabber（DirectShow 摄像头枚举，可选）

合规说明：
- 本项目遵循上述组件的各自开源许可；商用或分发请同时遵守上游许可与模型权重条款（含 Ultralytics 许可与数据/权重限制）。
- `models/yolo/yolo11n.pt` 等权重仅用于学习与测试，商用或再分发前需确认授权与条款。
- `models/vosk/` 目录为语音相关资源预留；当前版本默认使用本地 TTS 引擎，vosk 未启用。
- 二次打包/分发请保留第三方许可证与致谢。
