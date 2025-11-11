"""扶苗教学 GUI

功能
- 图片识物：打开图片 -> 识别 -> 在图上标注并播报
- 本地视频识物：打开视频 -> 实时识别并高亮中心物体，可自动播报当前中心物体
- 摄像头识物：选择摄像头 -> 开始 -> 实时识别并高亮中心物体，可自动播报当前中心物体

设计
- 大按钮与简洁布局，适合儿童与家长使用
- 仅暴露必要选项（摄像头选择、自动播报开关）
"""
from __future__ import annotations

import contextlib
import json
import logging
import os
import pathlib
import sys
import time
from pathlib import Path
from typing import Optional, cast

import cv2
import numpy as np
from PySide6.QtCore import QEvent, QObject, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPalette, QPen, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog,
                               QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                               QMessageBox, QProxyStyle, QPushButton,
                               QStatusBar, QStyle, QVBoxLayout, QWidget)

from detection.coco_intros_cn import get_intro_by_id
from detection.core import enumerate_cameras
from ss_io.camera_utils import get_directshow_device_names
from voice.tts_queue import TTSManager

from .logging_utils import (install_excepthook, install_qt_message_logging,
                            setup_logging, suppress_libpng_iccp_warning)
from .runtime_paths import prefer_local_weights
from .ss_core import SSConfig, SSDetector


def _bgr_to_qpix(img_bgr: np.ndarray) -> QPixmap:
    """将 BGR 图像转换为 QPixmap"""
    if img_bgr is None:
        return QPixmap()
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    bytes_per_line = 3 * w
    qim = QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(qim)


class KidsWindow(QWidget):
    def __init__(self) -> None:
        """扶苗主窗口"""
        super().__init__()
        self.setWindowTitle("扶苗")
        self.resize(780, 610)

        # 维持窗口等比缩放（保持当前宽高比）
        self._maintain_aspect: bool = True
        self._in_aspect_resize: bool = False
        # 初始宽高比在 UI 初始化后设定

        # 检测器：固定图片尺寸为 640 以确保实时性
        # 模型路径：优先从可执行文件所在目录的 models/yolo 读取
        model_path = "models/yolo/yolo11n.pt"
        self._cfg = SSConfig(
            model_path=prefer_local_weights(model_path),
            conf=0.6,
            img_size=[640, 640],
            device="auto",
        )
        # 延后在事件循环启动后初始化检测器，避免阻塞 UI
        self._det: Optional[SSDetector] = None
        self._model_msg_box: QMessageBox | None = None

        # 摄像头 / 本地视频
        self._cap: Optional[cv2.VideoCapture] = None
        self._cap_is_file: bool = False  # True 表示当前 _cap 来自本地视频文件
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_timer)
        self._last_center_label: Optional[str] = None
        self._last_speak_t: float = 0.0
        # 最近一次检测结果缓存
        self._last_dets: list = []
        self._last_center_idx: Optional[int] = None

        # TTS
        from voice import tts as _tts_mod
        self._tts = TTSManager(tts_module=_tts_mod, dup_window=1.2)
        self._tts.start()

        # 播报介绍期间禁用“播报介绍”按钮的轮询守护
        self._intro_btn_guard = QTimer(self)
        self._intro_btn_guard.setInterval(120)
        self._intro_btn_guard.timeout.connect(self._poll_intro_busy)

    # UI
        self._build_ui()
        self._refresh_cameras()
        # 构建完成后，根据当前主题（调色板）应用一次自适应样式
        self._apply_theme_adaptive_styles()
        # 记录当前窗口宽高比（避免除零）
        try:
            w = max(1, int(self.width()))
            h = max(1, int(self.height()))
            self._aspect_ratio = w / h
        except Exception:
            self._aspect_ratio = 16 / 9

        # 在 UI 可见后异步准备模型与检测器
        try:
            # 相关操作较重，初始化期间禁用依赖检测的按钮
            with contextlib.suppress(Exception):
                self._btn_recognize.setEnabled(False)
            with contextlib.suppress(Exception):
                self._btn_cam_start.setEnabled(False)
            # 初始化运行状态与重试计时器
            self._init_running: bool = False
            self._prepare_checks_left: int = 10
            self._prepare_check_timer: QTimer | None = None
            QTimer.singleShot(0, self._start_detector_init)
        except Exception:
            pass

    # ---------- 异步初始化检测器 ----------
    class _InitWorker(QObject):
        finished = Signal(object, object)  # (det or None, error or None)

        def run(self, cfg: SSConfig):  # type: ignore[override]
            det = None
            err = None
            try:
                det = SSDetector(cfg)
            except Exception as e:  # noqa: BLE001
                err = e
            self.finished.emit(det, err)

    def _start_detector_init(self) -> None:
        abs_model = Path(self._cfg.model_path)
        show_threshold = 1_000_000  # 约 1MB 下限
        if (not abs_model.exists()) or abs_model.stat().st_size < show_threshold:
            self._model_msg_box = QMessageBox(self)
            self._model_msg_box.setWindowTitle("正在准备模型")
            self._model_msg_box.setText("正在下载或加载 YOLO 模型，请稍候…\n首次运行可能需要一点时间。")
            self._model_msg_box.setIcon(QMessageBox.Icon.Information)
            self._model_msg_box.setStandardButtons(QMessageBox.StandardButton.NoButton)
            self._model_msg_box.show()
            QApplication.processEvents()
        # 启动一次初始化工作
        self._start_init_worker()
        # 启动“准备状态”轮询与重试（改为单次定时自调度，避免某些环境下重复 QTimer 未触发问题）
        self._prepare_checks_left = 10
        self._prepare_polling = True
        # 可视化告知轮询已启动
        try:
            if self._model_msg_box is not None:
                self._model_msg_box.setText(
                    "正在下载或加载 YOLO 模型，请稍候…\n首次运行可能需要一点时间。\n(每 5 秒检查，剩余 %d 次)" % self._prepare_checks_left
                )
            if hasattr(self, "_status") and self._status is not None:
                self._status.showMessage(f"正在准备模型… 每5秒检查，剩余 {self._prepare_checks_left} 次", 3000)
            logging.debug("[prepare] poll start, remaining=%d", self._prepare_checks_left)
        except Exception:
            pass
        # 立即执行一次首次检查（10ms 后），后续由函数内部再约 5 秒自调度
        QTimer.singleShot(10, self._on_prepare_check)

    def _start_init_worker(self) -> None:
        """启动一次检测器初始化的后台任务（若未在运行）"""
        if getattr(self, "_init_running", False):
            return
        # 使用工作线程构建检测器，避免阻塞 UI 线程
        self._init_thread = QThread(self)  # type: ignore[attr-defined]
        self._init_worker = KidsWindow._InitWorker()  # type: ignore[attr-defined]
        self._init_worker.moveToThread(self._init_thread)
        self._init_thread.started.connect(lambda: self._init_worker.run(self._cfg))
        self._init_worker.finished.connect(self._on_detector_inited)
        self._init_worker.finished.connect(self._init_thread.quit)
        self._init_thread.finished.connect(self._init_worker.deleteLater)
        self._init_thread.finished.connect(self._init_thread.deleteLater)
        self._init_running = True
        self._init_thread.start()

    def _dismiss_model_box(self, reason: str = "") -> None:
        """安全关闭并销毁模型准备提示框，避免某些平台 close() 不生效残留。

        参数:
            reason: 打点日志原因描述，便于调试。"""
        box = getattr(self, "_model_msg_box", None)
        if box is None:
            return
        try:
            # 依次尝试多种方式，最大化关闭成功率
            box.done(0)
        except Exception:
            pass
        try:
            box.close()
        except Exception:
            pass
        try:
            box.hide()
        except Exception:
            pass
        try:
            box.deleteLater()
        except Exception:
            pass
        self._model_msg_box = None
        # 立即处理一次事件队列，帮助窗口实际消失
        try:
            QApplication.processEvents()
        except Exception:
            pass
        if reason:
            logging.debug("[prepare] model box dismissed: %s", reason)

    def _on_prepare_check(self) -> None:
        """每 5 秒检查一次是否已准备好；如未就绪尝试重启初始化；超过 10 次则退出程序。"""
        # 在显示前先递减剩余次数（首次触发后从 N->N-1）
        try:
            if getattr(self, "_det", None) is None:  # 仅在未完成时递减
                self._prepare_checks_left -= 1
        except Exception:
            self._prepare_checks_left = 0
        # 打点日志，便于确认轮询是否执行
        try:
            from datetime import datetime
            abs_model = Path(self._cfg.model_path)
            size = abs_model.stat().st_size if abs_model.exists() else 0
            logging.debug(
                "[prepare] %s tick: left=%s init_running=%s file=%s size=%s",
                datetime.now().isoformat(timespec='seconds'),
                getattr(self, "_prepare_checks_left", -1),
                getattr(self, "_init_running", False),
                abs_model.exists(),
                size,
            )
            # 若文件已完整，先行关闭提示框，避免“下载完成但对话框未关”的视觉滞留
            try:
                min_bytes = int(os.getenv("SS_MIN_MODEL_BYTES", "1000000"))
            except Exception:
                min_bytes = 1_000_000
            if abs_model.exists() and size >= min_bytes and self._model_msg_box:
                self._dismiss_model_box("file ready (size >= min)")
        except Exception:
            pass
        # 同步更新提示文案中的剩余次数
        try:
            if self._model_msg_box is not None and self._model_msg_box.isVisible():
                self._model_msg_box.setText(
                    "正在下载或加载 YOLO 模型，请稍候…\n首次运行可能需要一点时间。\n(每 5 秒检查，剩余 %d 次)" % max(getattr(self, "_prepare_checks_left", 0), 0)
                )
        except Exception:
            pass
        # 已就绪：停止轮询并关闭提示
        if getattr(self, "_det", None) is not None:
            logging.debug("[prepare] ready branch (_det is not None), stopping poll")
            self._dismiss_model_box("detector ready")
            self._prepare_polling = False
            return
        # 如果文件已经下载完成但 _det 仍为空，尝试主线程直接构造一次（规避线程偶发卡住）
        try:
            abs_model = Path(self._cfg.model_path)
            min_bytes = int(os.getenv("SS_MIN_MODEL_BYTES", "1000000"))
            if abs_model.exists() and abs_model.stat().st_size >= min_bytes:
                # 主线程快速尝试构造；失败则继续原重试逻辑
                from .ss_core import SSDetector as _InlineDet  # 延迟导入避免循环
                try:
                    det_inline = _InlineDet(self._cfg)
                except Exception:
                    det_inline = None
                else:
                    self._det = det_inline
                    self._dismiss_model_box("inline construct succeeded")
                    with contextlib.suppress(Exception):
                        self._btn_recognize.setEnabled(True)
                    with contextlib.suppress(Exception):
                        self._btn_cam_start.setEnabled(True)
                    self._prepare_polling = False
                    logging.debug("[prepare] inline construct succeeded; dialog closed; poll stopped")
                    return
        except Exception:
            pass
        # 未就绪：剩余重试次数检查
        if self._prepare_checks_left <= 0:
            # 超过重试次数：提示并退出
            self._dismiss_model_box("timeout")
            QMessageBox.critical(self, "超时退出", "模型长时间未准备就绪，程序将自动退出。\n请检查网络或稍后重试。")
            app = QApplication.instance()
            if app is not None:
                QTimer.singleShot(0, app.quit)
            return
        # 若未在初始化中，尝试重启一次初始化
        if not getattr(self, "_init_running", False):
            logging.debug("[prepare] restarting init worker")
            self._start_init_worker()
        # 安排下一次检查（5 秒后）
        if getattr(self, "_prepare_polling", True):
            logging.debug("[prepare] scheduling next check in 5s, remaining=%d", self._prepare_checks_left)
            QTimer.singleShot(5000, self._on_prepare_check)

    def _on_detector_inited(self, det: Optional[SSDetector], err: Optional[Exception]) -> None:
        # 关闭提示
        self._dismiss_model_box("worker finished")
        # 标记当前初始化周期结束
        self._init_running = False
        if err is not None or det is None:
            # 若仍有重试机会，保持静默，由定时器负责重启；否则显示错误（防护，通常走不到此分支）
            if getattr(self, "_prepare_checks_left", 0) > 0:
                return
            abs_model = Path(self._cfg.model_path)
            QMessageBox.critical(self, "模型加载失败", f"请检查网络或手动放置模型文件：\n{abs_model}\n\n错误：{err}")
            return
        # 成功：设置检测器并启用按钮
        self._det = det
        with contextlib.suppress(Exception):
            self._btn_recognize.setEnabled(True)
        with contextlib.suppress(Exception):
            self._btn_cam_start.setEnabled(True)
        # 成功后停止轮询（自调度无需显式停止）
        self._prepare_polling = False

    def _safe_speak(self, text: str) -> None:
        """安全地调用 TTS，避免异常导致界面崩溃。"""
        try:
            if self._tts:
                self._tts.speak(text)
        except Exception:
            # 静默失败，异常会通过全局日志捕获
            pass

    # ---------- UI ----------
    def _build_ui(self) -> None:
        """构建界面元素"""
        root = QVBoxLayout(self)
        self._status = QStatusBar()
        self._status.setSizeGripEnabled(False)
        root.addWidget(self._status)

        # 预览区
        self._preview = QLabel("在这里显示识别结果")
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setStyleSheet("QLabel { background: #202020; color: #C0C0C0; font-size: 16px; font-weight: 600; }")
        self._preview.setMinimumHeight(420)
        root.addWidget(self._preview, 1)

        # 按钮区
        row = QHBoxLayout()
        self._btn_open = QPushButton("打开图片/视频")
        self._btn_open.setMinimumHeight(40)
        self._btn_open.clicked.connect(self._on_open_image)
        self._btn_recognize = QPushButton("识别并播报")
        self._btn_recognize.setMinimumHeight(40)
        self._btn_recognize.clicked.connect(self._on_recognize_image)
        pic_group = QGroupBox("图片、视频识物")
        pic_group.setObjectName("picGroup")
        pic_vbox = QVBoxLayout(pic_group)
        pic_vbox.addWidget(self._btn_open)
        pic_vbox.addWidget(self._btn_recognize)

        cam_group = QGroupBox("摄像头识物")
        cam_group.setObjectName("camGroup")
        grid = QGridLayout(cam_group)
        self._cam_combo = QComboBox()
        self._btn_cam_refresh = QPushButton("刷新")
        self._btn_cam_refresh.clicked.connect(self._refresh_cameras)
        self._btn_cam_start = QPushButton("开始摄像头")
        self._btn_cam_start.clicked.connect(self._on_cam_start)
        self._btn_cam_stop = QPushButton("停止")
        self._btn_cam_stop.clicked.connect(self._on_cam_stop)
        self._auto_speak_chk = QCheckBox("自动播报中心物体")
        self._auto_speak_chk.setObjectName("autoSpeakChk")
        self._auto_speak_chk.setChecked(True)
        # 介绍播报控件
        self._auto_intro_chk = QCheckBox("自动播报介绍")
        self._auto_intro_chk.setObjectName("autoIntroChk")
        self._auto_intro_chk.setChecked(False)
        self._btn_speak_intro = QPushButton("播报介绍")
        self._btn_speak_intro.clicked.connect(self._on_speak_intro)

        # 记录原始样式，便于在暗色模式恢复
        try:
            self._orig_style_speak = self._auto_speak_chk.style()
            self._orig_style_intro = self._auto_intro_chk.style()
        except Exception:
            self._orig_style_speak = None
            self._orig_style_intro = None

        # 摄像头布局元素放入网格
        grid.addWidget(QLabel("摄像头:"), 0, 0)
        grid.addWidget(self._cam_combo, 0, 1)
        grid.addWidget(self._btn_cam_refresh, 0, 2)
        grid.addWidget(self._btn_cam_start, 1, 1)
        grid.addWidget(self._btn_cam_stop, 1, 2)

        # 播报设置区块
        announce_group = QGroupBox("播报设置")
        announce_group.setObjectName("announceGroup")
        announce_col = QVBoxLayout(announce_group)
        announce_col.setContentsMargins(8, 8, 8, 8)
        announce_col.setSpacing(8)
        # 为两个勾选框左侧添加 5px 空白
        row_speak = QHBoxLayout()
        row_speak.setContentsMargins(0, 0, 0, 0)
        row_speak.setSpacing(0)
        row_speak.addSpacing(5)
        row_speak.addWidget(self._auto_speak_chk)
        row_speak.addStretch(1)
        announce_col.addLayout(row_speak)

        row_intro = QHBoxLayout()
        row_intro.setContentsMargins(0, 0, 0, 0)
        row_intro.setSpacing(0)
        row_intro.addSpacing(5)
        row_intro.addWidget(self._auto_intro_chk)
        row_intro.addStretch(1)
        announce_col.addLayout(row_intro)
        announce_col.addWidget(self._btn_speak_intro)
        announce_col.addStretch(1)

        # 将分组加入行布局
        row.addWidget(pic_group, 1)
        row.addWidget(cam_group, 2)
        row.addWidget(announce_group, 1)

        # 扶苗助手分组：小游戏 / 心理助理 / 个性化推荐
        helper_group = QGroupBox("扶苗助手")
        helper_group.setObjectName("helperGroup")
        helper_col = QVBoxLayout(helper_group)
        self._btn_game = QPushButton("潜能开发小游戏")
        self._btn_game.clicked.connect(self._open_game_dialog)
        self._btn_advisor = QPushButton("心理助理")
        self._btn_advisor.clicked.connect(self._open_advisor_dialog)
        self._btn_reco = QPushButton("个性化推荐")
        self._btn_reco.clicked.connect(self._open_reco_dialog)
        helper_col.addWidget(self._btn_game)
        helper_col.addWidget(self._btn_advisor)
        helper_col.addWidget(self._btn_reco)
        row.addWidget(helper_group, 1)
        root.addLayout(row)

    # ---------- 主题自适应样式 ----------
    class _OutlineCheckBoxStyle(QProxyStyle):
        """为 QCheckBox 指示器添加细黑色描边，保留原生勾选绘制。"""
        def __init__(self, base=None, border_color: QColor | None = None, light_only: bool = True):
            super().__init__(base)
            self._border_color = border_color or QColor(0, 0, 0)
            self._light_only = bool(light_only)

        def drawPrimitive(self, element, option, painter, widget=None):
            # 先按原样绘制（包含勾选图标）
            super().drawPrimitive(element, option, painter, widget)
            if element == QStyle.PrimitiveElement.PE_IndicatorCheckBox and widget is not None:
                try:
                    pal = widget.palette()
                    bg = pal.window().color()
                    r, g, b = bg.red(), bg.green(), bg.blue()
                    luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
                    if (not self._light_only) or (luminance > 180):
                        painter.save()
                        pen = QPen(self._border_color)
                        pen.setWidth(1)
                        painter.setPen(pen)
                        # 稍微内缩 0.5~1px，避免覆盖系统绘制的外沿
                        rect = option.rect.adjusted(0, 0, -1, -1)
                        painter.drawRect(rect)
                        painter.restore()
                except Exception:
                    pass
    def _apply_theme_adaptive_styles(self) -> None:
        """根据窗口调色板亮度，为亮色/暗色主题应用不同样式。

        - 亮色：
          * 复选框指示器添加黑色描边，背景白，选中时以主题色填充
          * 预览区域背景浅色、文字深色
        - 暗色：
          * 恢复为默认（或暗色）样式
        """
        try:
            bg = self.palette().window().color()
            r, g, b = bg.red(), bg.green(), bg.blue()
            luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
            is_light = luminance > 180

            if is_light:
                # 亮色模式：分组标题向下移动 5px，且底色透明
                with contextlib.suppress(Exception):
                    self.setStyleSheet(
                        """
                        QGroupBox#picGroup::title { padding-left: 10px; background-color: transparent; }
                        QGroupBox#camGroup::title { padding-left: 10px; background-color: transparent; }
                        QGroupBox#announceGroup::title { padding-left: 10px; background-color: transparent; }
                        QGroupBox#helperGroup::title { padding-left: 10px; background-color: transparent; }
                        """
                    )
                # 使用代理样式为复选框指示器添加黑色描边，保留系统的勾选渲染
                try:
                    base_style = self._orig_style_speak or self._auto_speak_chk.style()
                    speak_style = KidsWindow._OutlineCheckBoxStyle(base=base_style, border_color=QColor(0, 0, 0))
                    self._auto_speak_chk.setStyle(speak_style)
                except Exception:
                    pass
                try:
                    base_style2 = self._orig_style_intro or self._auto_intro_chk.style()
                    intro_style = KidsWindow._OutlineCheckBoxStyle(base=base_style2, border_color=QColor(0, 0, 0))
                    self._auto_intro_chk.setStyle(intro_style)
                except Exception:
                    pass
                # 清空可能的样式表以避免覆盖系统绘制
                with contextlib.suppress(Exception):
                    self._auto_speak_chk.setStyleSheet("")
                with contextlib.suppress(Exception):
                    self._auto_intro_chk.setStyleSheet("")

                # 预览：浅底深字
                with contextlib.suppress(Exception):
                    self._preview.setStyleSheet(
                        "QLabel { background: #FAFAFA; color: #111111; font-size: 16px; font-weight: 600; border: 1px solid #000000; border-radius: 4px; }"
                    )
            else:
                # 暗色模式：恢复（移除分组标题的 5px 下移）
                with contextlib.suppress(Exception):
                    self.setStyleSheet("")
                # 暗色：恢复复选框原始样式（去掉代理描边）
                with contextlib.suppress(Exception):
                    if self._orig_style_speak is not None:
                        self._auto_speak_chk.setStyle(self._orig_style_speak)
                    else:
                        self._auto_speak_chk.setStyle(QApplication.style())
                with contextlib.suppress(Exception):
                    if self._orig_style_intro is not None:
                        self._auto_intro_chk.setStyle(self._orig_style_intro)
                    else:
                        self._auto_intro_chk.setStyle(QApplication.style())
                with contextlib.suppress(Exception):
                    self._auto_speak_chk.setStyleSheet("")
                with contextlib.suppress(Exception):
                    self._auto_intro_chk.setStyleSheet("")
                with contextlib.suppress(Exception):
                    self._preview.setStyleSheet(
                        "QLabel { background: #202020; color: #C0C0C0; font-size: 16px; font-weight: 600; }"
                    )
        except Exception:
            pass

    def changeEvent(self, event) -> None:
        """主题/调色板变化时，重新应用样式。"""
        super().changeEvent(event)
        try:
            if event.type() == QEvent.Type.PaletteChange:
                self._apply_theme_adaptive_styles()
        except Exception:
            pass

    def resizeEvent(self, e):
        """保持窗口等比缩放：尽量按照当前宽高比调整另一边尺寸。"""
        if getattr(self, "_maintain_aspect", False) and not getattr(self, "_in_aspect_resize", False):
            new_size = e.size()
            old_size = e.oldSize()
            w, h = new_size.width(), new_size.height()
            ratio = getattr(self, "_aspect_ratio", None)
            if not ratio or ratio <= 0:
                try:
                    ratio = max(1, self.width()) / max(1, self.height())
                except Exception:
                    ratio = 16 / 9
                self._aspect_ratio = ratio
            # 根据用户改变更明显的那个维度来回调另一个
            try:
                dw = abs(w - (old_size.width() if old_size.isValid() else w))
                dh = abs(h - (old_size.height() if old_size.isValid() else h))
            except Exception:
                dw, dh = 0, 0
            if dw >= dh:
                # 优先以宽度为基准
                h_target = int(round(w / ratio))
                if h_target != h:
                    self._in_aspect_resize = True
                    try:
                        self.resize(w, h_target)
                    finally:
                        self._in_aspect_resize = False
                        return
            else:
                # 以高度为基准
                w_target = int(round(h * ratio))
                if w_target != w:
                    self._in_aspect_resize = True
                    try:
                        self.resize(w_target, h)
                    finally:
                        self._in_aspect_resize = False
                        return
        # 默认行为
        super().resizeEvent(e)

    # ---------- 子对话框 ----------
    def _open_game_dialog(self) -> None:
        """ 打开小游戏对话框 """
        from .game_dialog import GameDialog
        recent = None
        if self._last_dets and self._last_center_idx is not None and 0 <= self._last_center_idx < len(self._last_dets):
            recent = self._last_dets[self._last_center_idx].label_cn
        dlg = GameDialog(self, recent_object=recent, tts=self._tts)
        dlg.exec()

    def _open_advisor_dialog(self) -> None:
        """ 打开心理助理对话框 """
        from .advisor_dialog import AdvisorDialog
        dlg = AdvisorDialog(self, tts=self._tts)
        dlg.exec()

    def _open_reco_dialog(self) -> None:
        """ 打开个性化推荐对话框 """
        from .recommend_dialog import RecommendDialog
        recent = None
        if self._last_dets and self._last_center_idx is not None and 0 <= self._last_center_idx < len(self._last_dets):
            recent = self._last_dets[self._last_center_idx].label_cn
        dlg = RecommendDialog(self, recent_object=recent, tts=self._tts)
        dlg.exec()

    # ---------- 事件 ----------
    def _start_intro_guard(self) -> None:
        """在即将播报“介绍”时禁用按钮，直到播报结束再自动恢复"""
        if hasattr(self, "_btn_speak_intro") and self._btn_speak_intro is not None:
            self._btn_speak_intro.setEnabled(False)
        if not self._intro_btn_guard.isActive():
            self._intro_btn_guard.start()

    def _poll_intro_busy(self) -> None:
        """轮询检查 TTS 播报状态以恢复“播报介绍”按钮"""
        # 只要 TTS 仍在播报，就保持按钮禁用；结束后恢复并停止轮询
        busy = False
        try:
            busy = bool(self._tts and self._tts.is_busy())
        except Exception:
            busy = False
        if not busy:
            if hasattr(self, "_btn_speak_intro") and self._btn_speak_intro is not None:
                self._btn_speak_intro.setEnabled(True)
            self._intro_btn_guard.stop()

    def _refresh_cameras(self) -> None:
        """刷新摄像头列表"""
        # 若摄像头正在使用，避免刷新以免底层枚举触发驱动错误
        if self._cap is not None:
            return
        self._cam_combo.clear()
        try:
            cams = enumerate_cameras(8)
        except Exception:
            cams = []
        if not cams:
            self._cam_combo.addItem("无可用摄像头")
            self._cam_combo.setEnabled(False)
            return
        self._cam_combo.setEnabled(True)
        # 使用 DirectShow 设备名称（Windows）
        names: list[str] = []
        try:
            names = get_directshow_device_names()
        except Exception:
            names = []
        for i, cam_idx in enumerate(cams):
            # 默认标签为索引
            label = f"Camera {cam_idx}"
            # 优先按真实索引匹配 DirectShow 名称，避免因可用性过滤导致的错位
            try:
                if 0 <= int(cam_idx) < len(names):
                    nm = names[int(cam_idx)].strip()
                    if nm:
                        label = f"{nm} (# {cam_idx})"
                # 若按索引未命中，退化为按当前枚举顺序尝试一次（兼容某些驱动返回顺序差异）
                elif i < len(names) and names[i].strip():
                    label = f"{names[i].strip()} (# {cam_idx})"
            except Exception:
                # 保底使用默认标签
                pass
            self._cam_combo.addItem(label, userData=cam_idx)

    def _on_open_image(self) -> None:
        """打开图片或本地视频文件

        需求变化：将“本地视频识别”和“本地图片识别”合并到该入口；
        若选择图片则仅加载并显示，点击“识别并播报”处理该图片；
        若选择视频则直接以定时器方式开启逐帧检测，复用“停止”按钮结束。
        """
        # 若已有摄像头/视频在运行，先停止
        if self._cap is not None:
            with contextlib.suppress(Exception):
                self._on_cam_stop()

        # 同时允许选择图片与视频格式
        file_filter = (
            "图片/视频 (*.jpg *.jpeg *.png *.bmp *.mp4 *.avi *.mkv *.mov *.wmv *.flv *.webm);;"
            "图片 (*.jpg *.jpeg *.png *.bmp);;"
            "视频 (*.mp4 *.avi *.mkv *.mov *.wmv *.flv *.webm);;"
            "所有文件 (*.*)"
        )
        path, _ = QFileDialog.getOpenFileName(self, "选择图片或视频", filter=file_filter)
        if not path:
            return

        # 尝试按图片读取；若失败则按视频打开
        self._last_image_path = path
        img = cv2.imread(path)
        if img is not None:
            # 打开的是图片
            self._last_image_bgr = img
            self._preview.setPixmap(
                _bgr_to_qpix(img).scaled(
                    self._preview.width(),
                    self._preview.height(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            self._status.showMessage(f"已打开图片: {path}")
            return

        # 尝试作为视频文件打开
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            QMessageBox.warning(self, "打开失败", "无法读取该文件（既不是图片也不是可打开的视频）")
            return
        # 作为视频启动定时器循环
        self._cap = cap
        self._cap_is_file = True
        self._last_center_label = None
        self._last_speak_t = 0.0
        # 使用 ~30fps 的tick；实际取决于 read() 成功率与模型速度
        self._timer.start(33)
        self._status.showMessage(f"已打开视频: {path}，点击‘停止’结束")

    def _on_recognize_image(self) -> None:
        """识别当前打开的图片并播报结果"""
        img = getattr(self, "_last_image_bgr", None)
        if img is None:
            QMessageBox.information(self, "提示", "请先打开一张图片")
            return
        if getattr(self, "_det", None) is None:
            QMessageBox.information(self, "提示", "模型正在准备，请稍候")
            return
        det = cast(SSDetector, self._det)
        dets, plotted = det.detect_frame(img)
        # 选择中心并高亮
        idx = det.pick_center_object(dets, plotted.shape)
        self._last_dets = dets
        self._last_center_idx = idx
        annotated = det.annotate_with_center(plotted, dets, idx)
        self._preview.setPixmap(
            _bgr_to_qpix(annotated).scaled(
                self._preview.width(),
                self._preview.height(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        # 播报：若有中心物体就播报该物体，否则播报前几类
        if idx is not None:
            label = dets[idx].label_cn
            self._safe_speak(f"这是{label}")
            if self._auto_intro_chk.isChecked():
                intro = get_intro_by_id(dets[idx].cls_id)
                if intro:
                    self._safe_speak(intro)
                    self._start_intro_guard()
        else:
            if dets:
                names = list(dict.fromkeys([d.label_cn for d in dets]))[:3]
                self._safe_speak("我找到了：" + "，".join(names))
            else:
                self._safe_speak("没有找到可以识别的物体")

    def _on_cam_start(self) -> None:
        """启动摄像头识物"""
        if getattr(self, "_det", None) is None:
            QMessageBox.information(self, "提示", "模型正在准备，请稍候")
            return
        if self._cap is not None:
            return
        idx = self._cam_combo.currentData()
        if idx is None:
            QMessageBox.information(self, "提示", "没有可用摄像头")
            return
        # Windows 使用 DirectShow 优先
        if sys.platform.startswith("win"):
            cap = cv2.VideoCapture(int(idx), cv2.CAP_DSHOW)
        else:
            cap = cv2.VideoCapture(int(idx))
        if not cap.isOpened():
            QMessageBox.critical(self, "错误", f"无法打开摄像头 {idx}")
            return
        self._cap = cap
        self._cap_is_file = False
        self._last_center_label = None
        self._last_speak_t = 0.0
        self._timer.start(33)
        self._status.showMessage("摄像头已启动，按‘停止’结束")
        # 摄像头开启时禁用刷新与设备选择
        with contextlib.suppress(Exception):
            self._btn_cam_refresh.setEnabled(False)
            self._cam_combo.setEnabled(False)

    def _on_cam_stop(self) -> None:
        """停止摄像头识物"""
        if self._cap is not None:
            try:
                self._timer.stop()
                self._cap.release()
            except Exception:
                pass
            self._cap = None
            self._cap_is_file = False
            self._status.showMessage("已停止摄像头")
            # 恢复刷新与设备选择
            with contextlib.suppress(Exception):
                self._btn_cam_refresh.setEnabled(True)
                self._cam_combo.setEnabled(True)

    def _on_speak_intro(self) -> None:
        """手动播报当前中心物体的简介"""
        dets = self._last_dets
        idx = self._last_center_idx if self._last_center_idx is not None else None
        if not dets:
            QMessageBox.information(self, "提示", "当前没有识别结果")
            return
        if idx is None or not (0 <= idx < len(dets)):
            # 若没有中心物体，就取第一个
            idx = 0
        intro = get_intro_by_id(dets[idx].cls_id)
        if intro:
            self._safe_speak(intro)
            self._start_intro_guard()
        else:
            QMessageBox.information(self, "提示", "该物体暂无简介")

    def _on_timer(self) -> None:
        """摄像头定时器回调：抓取一帧并处理显示与播报"""
        cap = self._cap
        if cap is None:
            return
        ok, frame = cap.read()
        if not ok or frame is None:
            # 本地视频文件在读到结尾时主动停止；摄像头则忽略一次失败
            if self._cap_is_file:
                with contextlib.suppress(Exception):
                    self._on_cam_stop()
                self._status.showMessage("视频播放结束")
            return
        # 推理
        det_opt = getattr(self, "_det", None)
        if det_opt is None:
            return
        det = cast(SSDetector, det_opt)
        dets, plotted = det.detect_frame(frame)
        idx = det.pick_center_object(dets, plotted.shape)
        self._last_dets = dets
        self._last_center_idx = idx
        annotated = det.annotate_with_center(plotted, dets, idx)
        self._preview.setPixmap(
            _bgr_to_qpix(annotated).scaled(
                self._preview.width(),
                self._preview.height(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

        # 自动播报（中心物体变化时 + 冷却 1.2s）
        if self._auto_speak_chk.isChecked() and idx is not None and 0 <= idx < len(dets):
            label = dets[idx].label_cn
            now = time.time()
            if label != self._last_center_label and (now - self._last_speak_t) > 1.2:
                self._safe_speak(f"这是{label}")
                if self._auto_intro_chk.isChecked():
                    intro = get_intro_by_id(dets[idx].cls_id)
                    if intro:
                        self._safe_speak(intro)
                        self._start_intro_guard()
                self._last_center_label = label
                self._last_speak_t = now

    def closeEvent(self, event) -> None:
        """窗口关闭事件处理：确保释放摄像头与停止 TTS"""
        try:
            self._on_cam_stop()
        finally:
            try:
                self._tts.stop()
            except Exception:
                pass
        return super().closeEvent(event)


def main() -> None:
    # 初始化日志与异常捕获，避免整体崩溃并记录错误
    # 从 config.json 读取 LOG_LEVEL/DEBUG 开关，或使用环境变量 LOG_LEVEL
    debug_flag = None
    log_to_console = None
    console_level = None
    # 优先安装 libpng iCCP 警告过滤，避免控制台刷屏
    try:
        suppress_libpng_iccp_warning()
    except Exception:
        pass
    try:
        candidates = [
            pathlib.Path.cwd() / "config.json",
            pathlib.Path(__file__).resolve().parents[1] / "config.json",
        ]
        for p in candidates:
            if p.exists() and p.is_file():
                with p.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                # 兼容大小写/不同字段名
                lvl = (
                    str(data.get("LOG_LEVEL") or data.get("log_level") or "").strip().upper()
                )
                if lvl == "DEBUG":
                    debug_flag = True
                    break
                if data.get("debug") is True:
                    debug_flag = True
                    # 不 break，继续看看是否设置了控制台日志
                # 读取控制台日志开关/级别
                raw_console = data.get("LOG_TO_CONSOLE") or data.get("log_to_console")
                if isinstance(raw_console, bool):
                    log_to_console = raw_console
                elif isinstance(raw_console, str):
                    log_to_console = raw_console.strip().lower() in {"1", "true", "yes", "on"}
                raw_console_level = data.get("LOG_CONSOLE_LEVEL") or data.get("console_level")
                if isinstance(raw_console_level, str):
                    console_level = raw_console_level.strip().upper()
    except Exception:
        debug_flag = None

    setup_logging(debug=debug_flag, log_to_console=log_to_console, console_level=console_level)
    install_excepthook(show_dialog=True)
    install_qt_message_logging()
    # 降低 OpenCV 的日志级别（若版本支持），进一步抑制三方库输出
    try:
        import cv2 as _cv2
        lvlmod = getattr(getattr(_cv2, "utils", None), "logging", None)
        if lvlmod is not None:
            try:
                lvl = getattr(lvlmod, "LOG_LEVEL_ERROR", None)
                if lvl is not None:
                    lvlmod.setLogLevel(lvl)
            except Exception:
                pass
    except Exception:
        pass

    app = QApplication(sys.argv)

    try:
        force_light = False
        if os.getenv("SS_FORCE_LIGHT", "").strip().lower() in {"1", "true", "yes", "on"}:
            force_light = True
        if not force_light and any(arg.strip().lower() == "--force-light" for arg in sys.argv[1:]):
            force_light = True
        if force_light:
            # 使用 Fusion 风格 + 浅色调色板
            try:
                app.setStyle("Fusion")
            except Exception:
                pass
            pal = QPalette()
            pal.setColor(QPalette.ColorRole.Window, QColor(255, 255, 255))
            pal.setColor(QPalette.ColorRole.WindowText, QColor(17, 17, 17))
            pal.setColor(QPalette.ColorRole.Base, QColor(250, 250, 250))
            pal.setColor(QPalette.ColorRole.AlternateBase, QColor(242, 242, 242))
            pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(255, 255, 220))
            pal.setColor(QPalette.ColorRole.ToolTipText, QColor(17, 17, 17))
            pal.setColor(QPalette.ColorRole.Text, QColor(17, 17, 17))
            pal.setColor(QPalette.ColorRole.Button, QColor(245, 245, 245))
            pal.setColor(QPalette.ColorRole.ButtonText, QColor(17, 17, 17))
            pal.setColor(QPalette.ColorRole.BrightText, QColor(255, 0, 0))
            pal.setColor(QPalette.ColorRole.Highlight, QColor(66, 133, 244))
            pal.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
            try:
                app.setPalette(pal)
            except Exception:
                pass
    except Exception:
        pass
    win = KidsWindow()
    win.show()
    try:
        rc = app.exec()
    except Exception:
        # 理论上不会到这里，保底记录
        import logging

        logging.exception("Qt event loop crashed")
        rc = 1
    sys.exit(rc)

if __name__ == "__main__":
    main()
