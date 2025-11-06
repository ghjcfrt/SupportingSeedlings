""" 个性化内容推荐对话框（UI）。"""
from __future__ import annotations

import contextlib
import json
import logging
import re
from html import escape as _escape
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QFont, QTextBlockFormat, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QTextEdit, QVBoxLayout,
                               QWidget)

from recommend import Recommender, RecommendRequest


def _load_chat_style() -> tuple[int, float]:
    """从 config.json 读取聊天字号/行距，默认 (14, 1.6)。
    支持键：CHAT_FONT_SIZE（数字）、CHAT_LINE_HEIGHT（浮点）。
    搜索顺序：CWD/config.json -> 项目根（本文件两级父目录）/config.json。
    """
    default_size, default_lh = 14, 1.6
    candidates = [
        Path.cwd() / "config.json",
        Path(__file__).resolve().parents[1] / "config.json",
    ]
    for p in candidates:
        try:
            if p.exists():
                data = json.loads(p.read_text(encoding="utf-8"))
                fs = data.get("CHAT_FONT_SIZE") or data.get("chat_font_size")
                lh = data.get("CHAT_LINE_HEIGHT") or data.get("chat_line_height")
                size = int(fs) if fs is not None and str(fs).strip() != "" else default_size
                line_h = float(lh) if lh is not None and str(lh).strip() != "" else default_lh
                if size < 8 or size > 48:
                    size = default_size
                if line_h < 1.1 or line_h > 2.4:
                    line_h = default_lh
                return size, line_h
        except Exception:
            return default_size, default_lh
    return default_size, default_lh


class RecommendDialog(QDialog):
    """ 个性化内容推荐对话框（UI）。"""

    def __init__(self, parent: QWidget | None = None, *, recent_object: Optional[str] = None, tts=None) -> None:
        """ 初始化个性化内容推荐对话框 """
        super().__init__(parent)
        self.setWindowTitle("个性化内容推荐")
        self.setFixedSize(450, 350)
        self._tts = tts
        self._recent = recent_object
        self._rec: Recommender | None = None
        # 使用具体类型标注，便于类型检查识别自定义信号
        self._reco_thread: Optional["RecommendDialog._RecoWorker"] = None
        self._reco_worker: QWidget | None = None
        self._reco_timer: QTimer | None = None
        self._build_ui()

    class _RecoWorker(QThread):  # 使用 QThread 简化类型
        """ 推荐工作线程 """
        finished = Signal(list)
        failed = Signal(str)

        def __init__(self, rec: Recommender, req: RecommendRequest) -> None:
            """ 初始化推荐工作线程 """
            super().__init__()
            self._rec = rec
            self._req = req

        def run(self) -> None:
            """ 运行推荐任务 """
            try:
                items = self._rec.recommend(self._req)
                self.finished.emit(items)
            except Exception as e:
                logging.exception("RecommendDialog _RecoWorker failed")
                self.failed.emit(str(e))

    def _build_ui(self) -> None:
        """ 构建用户界面 """
        root = QVBoxLayout(self)
        form = QHBoxLayout()
        form.addWidget(QLabel("年龄:"))
        self._age = QComboBox()
        for a in range(3, 13):
            self._age.addItem(str(a))
        form.addWidget(self._age)
        form.addWidget(QLabel("层级:"))
        self._level = QComboBox()
        for lv in ["启蒙", "进阶", "挑战"]:
            self._level.addItem(lv)
        form.addWidget(self._level)
        root.addLayout(form)

        self._interests = QLineEdit()
        self._interests.setPlaceholderText("兴趣标签（逗号分隔）：动物, 车辆, 音乐, 自然, 数字, 颜色 …")
        root.addWidget(self._interests)

        if self._recent:
            hint = QLabel(f"最近识别：{self._recent}")
            hint.setAlignment(Qt.AlignmentFlag.AlignLeft)
            root.addWidget(hint)

        row_btn = QHBoxLayout()
        self._btn = QPushButton("生成推荐")
        self._btn.clicked.connect(self._on_reco)
        self._btn_regen = QPushButton("重新生成")
        self._btn_regen.clicked.connect(self._on_reco)
        self._btn_cancel = QPushButton("取消")
        self._btn_cancel.setEnabled(False)
        self._btn_cancel.clicked.connect(self._on_reco_cancel)
        row_btn.addWidget(self._btn)
        row_btn.addWidget(self._btn_regen)
        row_btn.addWidget(self._btn_cancel)
        root.addLayout(row_btn)

        self._out = QTextEdit()
        self._out.setReadOnly(True)
        try:
            fs, lh = _load_chat_style()
            self._out.document().setDefaultStyleSheet(
                f"body, p, div {{ font-size:{fs}px; line-height:{lh}; }}"
            )
            try:
                df = QFont()
                df.setPixelSize(fs)
                self._out.document().setDefaultFont(df)
            except Exception:
                pass
        except Exception:
            pass
        root.addWidget(self._out)

        try:
            disclaim_fs2 = max(10, int(fs) - 2)
        except Exception:
            disclaim_fs2 = 12
        self._reco_disclaimer = QLabel(
            "免责声明：推荐内容仅供参考，请家长结合实际情况判断；如涉及安全、健康等问题，请咨询专业人士。"
        )
        self._reco_disclaimer.setWordWrap(True)
        try:
            f2 = QFont()
            f2.setPixelSize(disclaim_fs2)
            self._reco_disclaimer.setFont(f2)
        except Exception:
            pass
        self._reco_disclaimer.setStyleSheet("color:#666;")
        self._reco_disclaimer.setContentsMargins(2, 6, 2, 0)
        root.addWidget(self._reco_disclaimer)

    def _insert_out_line(self, prefix: str, text: str) -> None:
        """ 在输出框插入一行文本 """
        cursor = self._out.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertBlock()
        try:
            lst = cursor.currentList()
            if lst is not None:
                lst.remove(cursor.block())
        except Exception:
            pass
        cursor.setCharFormat(QTextCharFormat())
        cursor.setBlockFormat(QTextBlockFormat())
        cursor.insertHtml(f"<b>{_escape(prefix)}</b> {_escape(text)}")
        self._out.setTextCursor(cursor)

    def _on_reco(self) -> None:
        """开始推荐"""
        if self._rec is None:
            try:
                self._rec = Recommender()
            except Exception as e:
                self._out.clear()
                self._insert_out_line("[错误]", f"初始化推荐引擎失败：{e}")
                self._insert_out_line("[系统]", "请先配置 XF_APPID/XF_API_KEY/XF_API_SECRET 环境变量后重试。")
                return
        req = RecommendRequest(
            age=int(self._age.currentText()),
            interests=[s.strip() for s in self._interests.text().split(',') if s.strip()],
            level=self._level.currentText(),
            recent_object=self._recent,
        )
        assert self._rec is not None
        self._btn.setEnabled(False)
        self._btn_regen.setEnabled(False)
        self._insert_out_line("[系统]", "正在为你生成推荐……")

        worker = RecommendDialog._RecoWorker(self._rec, req)
        self._reco_thread = worker
        worker.finished.connect(self._on_reco_done)
        worker.failed.connect(self._on_reco_fail)
        worker.start()

        self._btn_cancel.setEnabled(True)
        if self._reco_timer is not None:
            with contextlib.suppress(Exception):
                self._reco_timer.stop()
        self._reco_timer = QTimer(self)
        self._reco_timer.setSingleShot(True)
        self._reco_timer.setInterval(25000)
        self._reco_timer.timeout.connect(self._on_reco_timeout)
        self._reco_timer.start()

    @Slot(list)
    def _on_reco_done(self, items: list) -> None:
        """ 处理推荐结果 """
        lines: List[str] = []
        for it in items:
            lines.append(f"[{it.content_type}] {it.title}")
            if it.url:
                lines.append(f"链接：{it.url}")
            if it.tags:
                lines.append("标签：" + ", ".join(it.tags))
            lines.append("互动：" + it.prompt)
            lines.append("")
        if lines:
            md_lines: List[str] = []
            for it in items:
                title = it.title or "(未命名)"
                head = f"**{it.content_type}** " if getattr(it, "content_type", None) else ""
                if it.url:
                    md_lines.append(f"- {head}[{title}]({it.url})")
                else:
                    md_lines.append(f"- {head}{title}")
                if it.tags:
                    md_lines.append("  \n  标签：`" + "`, `".join(it.tags) + "`")
                if it.prompt:
                    md_lines.append(f"  \n  互动：{it.prompt}")
                md_lines.append("")
            md = "\n".join(md_lines)
        else:
            md = "暂时没有找到合适的内容，尝试调整年龄或兴趣试试。"

        def _md_to_html(md_text: str) -> str:
            """ 将 Markdown 文本转换为 HTML """
            try:
                md_t = re.sub(r"(?<!^)(?<!\n)\s(1\.\s)", r"\n\n\1", md_text)
                md_t = re.sub(r"(?<!^)(?<!\n)\s(([0-9]{1,2})\.\s)", r"\n\1", md_t)
                md_t = re.sub(r"(?<!^)(?<!\n)\s([-*]\s)", r"\n\1", md_t)
            except Exception:
                md_t = md_text
            try:
                import markdown
                html = markdown.markdown(md_t, extensions=["extra", "sane_lists"])
                html = re.sub(r"<ol(?![^>]*start=)", "<ol start='1'", html)
                fs, lh = _load_chat_style()
                style = f"font-size:{fs}px; line-height:{lh};"
                extra_css = (
                    "h1, h2, h3, h4, h5, h6{font-size:1em;margin:0.4em 0;}"
                    "ol, ul{margin:0.4em 1.2em;}li{margin:0.2em 0;}"
                )
                return f"<div style='{style}'><style>{extra_css}</style>" + html + "</div>"
            except Exception:
                s = re.sub(r"```[\s\S]*?```", lambda m: m.group(0).strip('`'), md_text)
                s = re.sub(r"^\s*#{1,6}\s*", "", s, flags=re.MULTILINE)
                s = re.sub(r"\*\*(.*?)\*\*", r"\1", s)
                s = re.sub(r"\*(.*?)\*", r"\1", s)
                s = re.sub(r"_(.*?)_", r"\1", s)
                s = re.sub(r"^\s*[-*]\s+", "• ", s, flags=re.MULTILINE)
                s = re.sub(r"`([^`]+)`", r"\1", s)
                s = re.sub(r"\n{3,}", "\n\n", s)
                return "<div>" + s.strip().replace("\n", "<br/>") + "</div>"

        self._out.setHtml(_md_to_html(md))
        if self._tts and lines:
            try:
                self._tts.speak("我为你准备了几条推荐，我们来挑一条试试。")
            except Exception:
                logging.exception("TTS speak failed in RecommendDialog")
        self._btn.setEnabled(True)
        self._btn_regen.setEnabled(True)
        self._btn_cancel.setEnabled(False)
        if self._reco_timer:
            with contextlib.suppress(Exception):
                self._reco_timer.stop()
            self._reco_timer = None
        if self._reco_thread:
            self._reco_thread.quit()
            self._reco_thread = None

    @Slot(str)
    def _on_reco_fail(self, err: str) -> None:
        """ 处理推荐失败 """
        def _friendly(e: str) -> str:
            """ 将错误信息转化为用户友好提示 """
            s = e.lower()
            if "getaddrinfo failed" in s:
                return "生成失败：网络解析失败（可能离线/DNS 问题）"
            if "timed out" in s or "timeout" in s:
                return "生成失败：请求超时，请稍后重试"
            if "1006" in s or "connection is closed" in s:
                return "生成失败：连接中断，请检查网络或凭据"
            return f"生成失败：{e}"

        self._insert_out_line("[错误]", _friendly(err))
        self._btn.setEnabled(True)
        self._btn_regen.setEnabled(True)
        self._btn_cancel.setEnabled(False)
        if self._reco_timer:
            with contextlib.suppress(Exception):
                self._reco_timer.stop()
            self._reco_timer = None
        if self._reco_thread:
            self._reco_thread.quit()
            self._reco_thread = None

    def _disconnect_reco_signals(self) -> None:
        """ 断开推荐线程信号连接 """
        w = self._reco_thread
        if not w:
            return
        try:
            w.finished.disconnect(self._on_reco_done)
        except Exception:
            pass
        try:
            w.failed.disconnect(self._on_reco_fail)
        except Exception:
            pass
        self._reco_worker = None

    @Slot()
    def _on_reco_cancel(self) -> None:
        """ 处理推荐取消 """
        self._disconnect_reco_signals()
        self._btn.setEnabled(True)
        self._btn_regen.setEnabled(True)
        self._btn_cancel.setEnabled(False)
        self._insert_out_line("[系统]", "已取消本次生成")
        if self._reco_timer:
            with contextlib.suppress(Exception):
                self._reco_timer.stop()
            self._reco_timer = None
        if self._reco_thread:
            with contextlib.suppress(Exception):
                self._reco_thread.quit()
            self._reco_thread = None

    @Slot()
    def _on_reco_timeout(self) -> None:
        """ 处理推荐超时 """
        self._disconnect_reco_signals()
        self._btn.setEnabled(True)
        self._btn_regen.setEnabled(True)
        self._btn_cancel.setEnabled(False)
        self._insert_out_line("[系统]", "等待超时，请稍后重试或检查网络配置。")
        if self._reco_thread:
            with contextlib.suppress(Exception):
                self._reco_thread.quit()
            self._reco_thread = None
