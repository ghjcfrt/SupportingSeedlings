from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from typing import Optional


def setup_logging(
    *,
    debug: bool | None = None,
    log_dir: str = "logs",
    filename: str = "app.log",
    log_to_console: bool | None = None,
    console_level: str | int | None = None,
) -> None:
    """Initialize root logging with console + rotating file handler.

    - debug: enable DEBUG level; default: True if env LOG_LEVEL=DEBUG
    - log_dir: directory to place log file
    - filename: log file name
    """
    if debug is None:
        debug = (os.getenv("LOG_LEVEL", "").upper() == "DEBUG")

    level = logging.DEBUG if debug else logging.INFO

    # Prevent duplicate handlers if called multiple times
    root = logging.getLogger()
    if getattr(root, "_seedlings_logging_initialized", False):
        root.setLevel(level)
        return

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)5s | %(threadName)s | %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Console handler (optional)
    ch = None
    if log_to_console is None:
        # default: show warnings+ on console when not debug, otherwise debug
        log_to_console = True
    if log_to_console:
        ch = logging.StreamHandler(sys.stdout)
        # parse console_level if provided
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

    # File handler (rotating by size)
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

    # Mark initialized
    setattr(root, "_seedlings_logging_initialized", True)

    # Quiet noisy third-party loggers when not in debug
    if not debug:
        for noisy in ("comtypes",):
            try:
                logging.getLogger(noisy).setLevel(logging.WARNING)
            except Exception:
                pass


def install_excepthook(show_dialog: bool = True) -> None:
    """Install a global exception hook to prevent hard crashes on uncaught exceptions.

    Logs the exception with stack trace and, optionally, shows a message box.
    """
    import traceback

    def _hook(exc_type, exc, tb):
        logging.critical("Uncaught exception:", exc_info=(exc_type, exc, tb))
        if show_dialog:
            try:
                # Show a minimal error dialog if Qt is available and app exists
                from PySide6.QtWidgets import QApplication, QMessageBox

                app = QApplication.instance()
                if app is not None:
                    msg = "\n".join(traceback.format_exception(exc_type, exc, tb)[-3:])
                    QMessageBox.critical(None, "程序出错了", f"发生未捕获异常，已记录日志：\n{msg}")
            except Exception:
                pass
        # Do NOT call the default excepthook to avoid terminating the process
        # However, some fatal errors (e.g., Qt internal assertions) may still terminate.

    sys.excepthook = _hook


def install_qt_message_logging() -> None:
    """Redirect Qt messages (qDebug/qWarning/qCritical) into Python logging."""
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
        level = level_map.get(msg_type, logging.INFO)
        logger = logging.getLogger("Qt")
        # Keep it simple to avoid relying on stubbed attributes
        logger.log(level, message)

    try:
        qInstallMessageHandler(handler)
    except Exception:
        pass
