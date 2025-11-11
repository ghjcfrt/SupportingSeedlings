"""检测 API 门面

统一导出核心类型与函数，供 GUI 与 CLI 调用：
- YOLOConfig: 参数配置
- YOLODetector: 核心检测器
- enumerate_cameras: 摄像头探测
- load_config_from_args: 从命令行参数构建配置
- main: 命令行入口

增强：在 CLI 入口初始化日志（读取根目录/CWD 的 config.json：LOG_LEVEL/LOG_TO_CONSOLE/LOG_CONSOLE_LEVEL），
确保打包为 exe 后也能在 logs/ 下落盘日志。
"""

from __future__ import annotations

import json
import pathlib
from typing import Optional

from app.logging_utils import setup_logging

from .core import (YOLOConfig, YOLODetector, enumerate_cameras,
                   load_config_from_args, main)

__all__ = [
    "YOLOConfig",
    "YOLODetector",
    "enumerate_cameras",
    "load_config_from_args",
    "main",
]


def _init_logging_from_config() -> None:
    """尝试从 config.json 初始化日志设置。

    查找顺序：CWD/config.json -> 项目根（本文件两级父目录）/config.json。
    解析键：LOG_LEVEL、LOG_TO_CONSOLE、LOG_CONSOLE_LEVEL。
    若未找到或解析失败，沿用默认设置（INFO，控制台按默认策略）。
    """
    debug_flag: Optional[bool] = None
    log_to_console: Optional[bool] = None
    console_level: Optional[str] = None
    try:
        candidates = [
            pathlib.Path.cwd() / "config.json",
            pathlib.Path(__file__).resolve().parents[1] / "config.json",
        ]
        for p in candidates:
            if p.exists() and p.is_file():
                with p.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                lvl = str(data.get("LOG_LEVEL") or data.get("log_level") or "").strip().upper()
                if lvl == "DEBUG":
                    debug_flag = True
                raw_console = data.get("LOG_TO_CONSOLE") or data.get("log_to_console")
                if isinstance(raw_console, bool):
                    log_to_console = raw_console
                elif isinstance(raw_console, str):
                    log_to_console = raw_console.strip().lower() in {"1", "true", "yes", "on"}
                raw_console_level = data.get("LOG_CONSOLE_LEVEL") or data.get("console_level")
                if isinstance(raw_console_level, str):
                    console_level = raw_console_level.strip().upper()
                break
    except Exception:
        # 静默失败，使用默认设置
        pass
    setup_logging(debug=debug_flag, log_to_console=log_to_console, console_level=console_level)

def cli_main(argv: list[str] | None = None) -> None:
    """命令行检测入口（带日志初始化）。"""
    _init_logging_from_config()
    from .core import main as _core_main

    _core_main(argv)
