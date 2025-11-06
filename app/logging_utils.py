from __future__ import annotations

import logging
import logging.handlers
import os
import re
import sys
import threading
from typing import Optional


def setup_logging(
    *,
    debug: bool | None = None,
    log_dir: str = "logs",
    filename: str = "app.log",
    log_to_console: bool | None = None,
    console_level: str | int | None = None,
) -> None:
    """初始化根日志：控制台输出 + 按大小滚动的文件日志。

    - debug: 是否启用 DEBUG 级别；默认当环境变量 LOG_LEVEL=DEBUG 时为 True
    - log_dir: 日志文件目录
    - filename: 日志文件名
    """
    if debug is None:
        debug = (os.getenv("LOG_LEVEL", "").upper() == "DEBUG")

    level = logging.DEBUG if debug else logging.INFO

    # 避免重复初始化：若已初始化，仅调整级别即可
    root = logging.getLogger()
    if getattr(root, "_seedlings_logging_initialized", False):
        root.setLevel(level)
        return

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)5s | %(threadName)s | %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # 控制台处理器（可选）
    ch = None
    if log_to_console is None:
    # 默认：非调试模式下在控制台显示 WARNING+，调试模式显示 DEBUG
        log_to_console = True
    if log_to_console:
        ch = logging.StreamHandler(sys.stdout)
    # 若显式提供 console_level 则按其解析
        if isinstance(console_level, str):
            lvl_map = {
                "CRITICAL": logging.CRITICAL,
                "ERROR": logging.ERROR,
                "WARNING": logging.WARNING,
                "INFO": logging.INFO,
                "DEBUG": logging.DEBUG,
            }
            ch_level = lvl_map.get(console_level.upper(), None)
        else:
            ch_level = console_level
        if ch_level is None:
            ch_level = logging.DEBUG if debug else logging.WARNING
        ch.setLevel(ch_level)
        ch.setFormatter(fmt)

    # 文件处理器（按大小滚动备份）
    try:
        os.makedirs(log_dir, exist_ok=True)
        fh: Optional[logging.Handler]
        fh = logging.handlers.RotatingFileHandler(
            os.path.join(log_dir, filename), maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        fh.setLevel(level)
        fh.setFormatter(fmt)
    except Exception:
        fh = None

    root.setLevel(level)
    if ch is not None:
        root.addHandler(ch)
    if fh is not None:
        root.addHandler(fh)

    # 标记已初始化
    setattr(root, "_seedlings_logging_initialized", True)

    # 静音冗余的第三方日志（即使在调试模式，这些输出也过于冗长）
    for noisy in ("comtypes", "comtypes.client", "pygrabber"):
        try:
            logging.getLogger(noisy).setLevel(logging.WARNING)
        except Exception:
            pass


def install_excepthook(show_dialog: bool = True) -> None:
    """安装全局异常钩子，避免未捕获异常导致程序直接崩溃。

    会记录带堆栈的异常日志，并（可选）弹出对话框提示。
    """
    import traceback

    def _hook(exc_type, exc, tb):
        logging.critical("Uncaught exception:", exc_info=(exc_type, exc, tb))
        if show_dialog:
            try:
                # 若可用 Qt 且应用实例已存在，则弹出简要错误对话框
                from PySide6.QtWidgets import QApplication, QMessageBox

                app = QApplication.instance()
                if app is not None:
                    msg = "\n".join(traceback.format_exception(exc_type, exc, tb)[-3:])
                    QMessageBox.critical(None, "程序出错了", f"发生未捕获异常，已记录日志：\n{msg}")
            except Exception:
                pass
    # 不调用默认 excepthook，避免进程被终止；
    # 但某些致命错误（如 Qt 内部断言）仍可能导致退出。

    sys.excepthook = _hook


def install_qt_message_logging() -> None:
    """将 Qt 消息（qDebug/qWarning/qCritical）重定向到 Python logging。"""
    try:
        from PySide6.QtCore import (QMessageLogContext, QtMsgType,
                                    qInstallMessageHandler)
    except Exception:
        return

    level_map = {
        QtMsgType.QtDebugMsg: logging.DEBUG,
        QtMsgType.QtInfoMsg: logging.INFO,
        QtMsgType.QtWarningMsg: logging.WARNING,
        QtMsgType.QtCriticalMsg: logging.ERROR,
        QtMsgType.QtFatalMsg: logging.CRITICAL,
    }

    def handler(msg_type: QtMsgType, context: QMessageLogContext, message: str) -> None:
        """ Qt 消息处理器 """
        level = level_map.get(msg_type, logging.INFO)
        logger = logging.getLogger("Qt")
    # 简化处理，避免依赖上下文中可能缺失的属性
        logger.log(level, message)

    try:
        qInstallMessageHandler(handler)
    except Exception:
        pass


def suppress_stderr_patterns(patterns: list[str]) -> None:
    """按模式过滤写入到进程级 stderr 的文本行。

    该实现工作在文件描述符层面（os.dup2），可以过滤绕过 Python logging 的
    原生库输出（如 libpng）。
    """
    try:
        import os

    # 预编译正则（忽略大小写的包含匹配）
        regs = [re.compile(re.escape(pat), re.IGNORECASE) for pat in patterns if pat]
        if not regs:
            return

    # 复制原始 stderr 的 fd，并创建管道
        orig_fd = os.dup(2)
        rfd, wfd = os.pipe()

    # 将 fd=2（stderr）重定向到管道写端
        os.dup2(wfd, 2)
        try:
            os.close(wfd)
        except Exception:
            pass

        def _reader() -> None:
            buf = b""
            # 使用原始 stderr 的缓冲 writer
            try:
                orig = os.fdopen(orig_fd, "wb", closefd=True)
            except Exception:
                orig = None
            while True:
                try:
                    chunk = os.read(rfd, 4096)
                    if not chunk:
                        break
                    buf += chunk
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        try:
                            text = line.decode("utf-8", errors="ignore")
                        except Exception:
                            text = ""
                        # 过滤匹配任一模式的行
                        drop = any(reg.search(text) for reg in regs)
                        if not drop and orig is not None:
                            orig.write(line + b"\n")
                            orig.flush()
                except Exception:
                    break
            # 刷新剩余缓冲区
            if buf and orig is not None:
                try:
                    orig.write(buf)
                    orig.flush()
                except Exception:
                    pass
            try:
                os.close(rfd)
            except Exception:
                pass

        t = threading.Thread(target=_reader, name="stderr-filter", daemon=True)
        t.start()
    except Exception:
    # 失败时静默处理，避免影响应用启动
        pass


def suppress_libpng_iccp_warning() -> None:
    """便捷封装：屏蔽常见的 libpng iCCP 警告刷屏。"""
    suppress_stderr_patterns(["libpng warning: iCCP: known incorrect sRGB profile"])
