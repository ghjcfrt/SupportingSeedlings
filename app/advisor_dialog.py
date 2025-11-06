""" 心理助理对话框（UI）。"""
from __future__ import annotations

import contextlib
import json
import logging
import re
from html import escape as _escape
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QFont, QTextBlockFormat, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QTextEdit, QVBoxLayout,
                               QWidget)

from agent import Advisor, ChildProfile, clean_advisor_reply


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


class AdvisorDialog(QDialog):
    """ 心理助理对话框（UI）。"""

    def __init__(self, parent: QWidget | None = None, *, tts=None) -> None:
        """ 初始化心理助理对话框 """
        super().__init__(parent)
        self.setWindowTitle("心理助理（连续对话·讯飞）")
        self.setFixedSize(450, 700)
        self._tts = tts
        self._advisor: Advisor | None = None
        self._session = None
        self._ask_thread: QThread | None = None
        # 标注为具体的工作者类型以让类型检查识别自定义信号
        self._ask_worker: Optional["AdvisorDialog._AskWorker"] = None
        self._ask_timer: QTimer | None = None
        self._build_ui()

    class _AskWorker(QObject):
        """ 异步请求心理助理的工作线程。"""

        finished = Signal(str)
        failed = Signal(str)

        def __init__(self, advisor: Advisor, session, text: str) -> None:
            """ 初始化工作线程 """
            super().__init__()
            self._advisor = advisor
            self._session = session
            self._text = text

        def run(self) -> None:
            """ 执行请求心理助理 """
            try:
                reply = self._advisor.ask(self._session, self._text)
                self.finished.emit(reply)
            except Exception as e:
                logging.exception("AdvisorDialog _AskWorker failed")
                self.failed.emit(str(e))

    def _build_ui(self) -> None:
        """ 构建对话框 UI """
        root = QVBoxLayout(self)
        form = QHBoxLayout()
        form.addWidget(QLabel("年龄:"))
        self._age = QComboBox()
        for a in range(3, 13):
            self._age.addItem(str(a))
        form.addWidget(self._age)
        form.addWidget(QLabel("情绪:"))
        self._mood = QComboBox()
        for m in ["愉快", "焦虑", "易怒", "低落", "兴奋"]:
            self._mood.addItem(m)
        form.addWidget(self._mood)
        root.addLayout(form)

        self._interests = QLineEdit()
        self._interests.setPlaceholderText("兴趣（逗号分隔）：动物, 车辆, 音乐, 自然…")
        root.addWidget(self._interests)
        self._notes = QTextEdit()
        self._notes.setPlaceholderText("补充说明（可选）")
        root.addWidget(self._notes)

        ctrl = QHBoxLayout()
        self._btn_start = QPushButton("开始对话")
        self._btn_start.clicked.connect(self._on_start)
        self._btn_reset = QPushButton("重置会话")
        self._btn_reset.clicked.connect(self._on_reset)
        ctrl.addWidget(self._btn_start)
        ctrl.addWidget(self._btn_reset)
        root.addLayout(ctrl)

        self._chat = QTextEdit()
        self._chat.setReadOnly(True)
        try:
            fs, lh = _load_chat_style()
            self._chat_fs, self._chat_lh = fs, lh
            self._chat.document().setDefaultStyleSheet(
                f"body, p, div {{ font-size:{fs}px; line-height:{lh}; }}"
            )
            try:
                df = QFont()
                df.setPixelSize(fs)
                self._chat.document().setDefaultFont(df)
            except Exception:
                pass
        except Exception:
            self._chat_fs, self._chat_lh = 14, 1.6
        root.addWidget(self._chat)

        in_row = QHBoxLayout()
        self._inp = QLineEdit()
        self._inp.setPlaceholderText("输入你的问题，例如：孩子最近睡前总是抗拒怎么办？")
        self._send = QPushButton("发送")
        self._send.clicked.connect(self._on_send)
        self._btn_cancel = QPushButton("取消")
        self._btn_cancel.setEnabled(False)
        self._btn_cancel.clicked.connect(self._on_ask_cancel)
        in_row.addWidget(self._inp, 1)
        in_row.addWidget(self._send)
        in_row.addWidget(self._btn_cancel)
        root.addLayout(in_row)

        try:
            base_fs = getattr(self, "_chat_fs", 14)
            disclaim_fs = max(10, int(base_fs) - 2)
        except Exception:
            disclaim_fs = 12
        self._disclaimer = QLabel(
            "免责声明：本助理提供的建议仅供参考，不能替代专业医疗、心理或教育建议。如遇紧急或严重情况，请及时联系专业人士。"
        )
        self._disclaimer.setWordWrap(True)
        try:
            f = QFont()
            f.setPixelSize(disclaim_fs)
            self._disclaimer.setFont(f)
        except Exception:
            pass
        self._disclaimer.setStyleSheet("color:#666;")
        self._disclaimer.setContentsMargins(2, 6, 2, 0)
        root.addWidget(self._disclaimer)

    def _insert_line(self, prefix: str, text: str) -> None:
        """在文档末尾开新段落并插入一行，强制与上文断开（不延续列表/标题）。"""
        cursor = self._chat.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertBlock()
        removed_from_list = False
        try:
            lst = cursor.currentList()
            if lst is not None:
                lst.remove(cursor.block())
                removed_from_list = True
        except Exception:
            pass
        cursor.setCharFormat(QTextCharFormat())
        cursor.setBlockFormat(QTextBlockFormat())
        cursor.insertHtml(f"<b>{_escape(prefix)}</b> {_escape(text)}")
        self._chat.setTextCursor(cursor)
        logging.debug("[CHAT-INSERT] prefix=%s removed_from_list=%s", prefix, removed_from_list)
        self._debug_dump_last_blocks(self._chat, f"insert_line:{prefix}", max_blocks=3)

    def _debug_dump_last_blocks(self, edit: QTextEdit, label: str, max_blocks: int = 3) -> None:
        """调试：输出文本末尾若干段落的字体/段落信息，定位字号/行距异常来源。"""
        if not logging.getLogger().isEnabledFor(logging.DEBUG):
            return
        try:
            doc = edit.document()
            stylesheet = doc.defaultStyleSheet()
            df = doc.defaultFont()
            logging.debug(
                "[CHAT-STYLE] label=%s cfg_font=%spx cfg_lineHeight=%s df_px=%s df_pt=%s stylesheet=%s",
                label,
                getattr(self, "_chat_fs", None),
                getattr(self, "_chat_lh", None),
                getattr(df, "pixelSize", lambda: None)(),
                getattr(df, "pointSizeF", lambda: None)(),
                stylesheet,
            )
            block = doc.lastBlock()
            count = 0
            while block.isValid() and count < max_blocks:
                pos = block.position()
                cursor = QTextCursor(doc)
                cursor.setPosition(pos)
                cf = cursor.charFormat()
                bf = cursor.blockFormat()
                font = cf.font()
                cf_pt = cf.fontPointSize()
                font_pt = font.pointSizeF()
                try:
                    font_px = font.pixelSize()
                except Exception:
                    font_px = None
                text_preview = block.text().replace("\n", "↵")
                if len(text_preview) > 80:
                    text_preview = text_preview[:77] + "…"
                logging.debug(
                    "[CHAT-BLOCK] #%s num=%s len=%s cf_pt=%s font_pt=%s font_px=%s weight=%s italic=%s align=%s lineHeight(type=%s,val=%s) text=%s",
                    count,
                    block.blockNumber(),
                    len(block.text()),
                    cf_pt,
                    font_pt,
                    font_px,
                    font.weight(),
                    font.italic(),
                    int(bf.alignment()),
                    bf.lineHeightType(),
                    bf.lineHeight(),
                    text_preview,
                )
                block = block.previous()
                count += 1
        except Exception:
            logging.exception("debug dump blocks failed: %s", label)

    def _on_start(self) -> None:
        """ 开始新会话 """
        if self._advisor is None:
            try:
                self._advisor = Advisor()
            except Exception as e:
                self._insert_line("[系统]", f"无法初始化心理助理：{e}")
                return
        prof = ChildProfile(
            age=int(self._age.currentText()),
            mood=self._mood.currentText(),
            interests=[s.strip() for s in self._interests.text().split(',') if s.strip()],
            notes=self._notes.toPlainText().strip(),
        )
        assert self._advisor is not None
        self._session = self._advisor.start_session(prof)
        self._insert_line("[系统]", "已建立会话，欢迎与心理助理对话。")
        self._debug_dump_last_blocks(self._chat, "after_start", max_blocks=3)

    def _on_reset(self) -> None:
        """ 重置会话 """
        self._session = None
        self._chat.clear()
        self._insert_line("[系统]", "会话已重置。")

    def _on_send(self) -> None:
        """ 发送用户输入 """
        text = self._inp.text().strip()
        if not text:
            return
        if self._session is None:
            self._on_start()
        self._insert_line("[家长]", text)
        self._debug_dump_last_blocks(self._chat, "after_parent", max_blocks=3)
        try:
            assert self._session is not None and self._advisor is not None
        except AssertionError:
            self._insert_line("[系统]", "会话未就绪")
            return
        self._send.setEnabled(False)
        self._inp.setEnabled(False)
        self._insert_line("[助理]", "正在思考……")
        self._debug_dump_last_blocks(self._chat, "after_thinking", max_blocks=3)

        worker = AdvisorDialog._AskWorker(self._advisor, self._session, text)
        th = QThread(self)
        self._ask_thread = th
        self._ask_worker = worker
        worker.moveToThread(th)
        th.started.connect(worker.run)
        worker.finished.connect(self._on_ask_done)
        worker.failed.connect(self._on_ask_fail)
        th.finished.connect(worker.deleteLater)
        th.finished.connect(th.deleteLater)
        th.start()
        self._btn_cancel.setEnabled(True)
        if self._ask_timer is not None:
            try:
                self._ask_timer.stop()
            except Exception:
                pass
        self._ask_timer = QTimer(self)
        self._ask_timer.setSingleShot(True)
        self._ask_timer.setInterval(25000)
        self._ask_timer.timeout.connect(self._on_ask_timeout)
        self._ask_timer.start()

    @Slot(str)
    def _on_ask_done(self, reply: str) -> None:
        """ 处理心理助理回复 """
        reply_clean = clean_advisor_reply(reply)

        def _md_to_html(md: str) -> str:
            try:
                md = re.sub(r"(?<!^)(?<!\n)\s(1\.\s)", r"\n\n\1", md)
                md = re.sub(r"(?<!^)(?<!\n)\s(([0-9]{1,2})\.\s)", r"\n\1", md)
                md = re.sub(r"(?<!^)(?<!\n)\s([-*]\s)", r"\n\1", md)
            except Exception:
                pass
            try:
                import markdown

                html = markdown.markdown(md, extensions=["extra", "sane_lists"])
                html = re.sub(r"<ol(?![^>]*start=)", "<ol start='1'", html)
                fs, lh = _load_chat_style()
                style = f"font-size:{fs}px; line-height:{lh};"
                extra_css = (
                    "h1, h2, h3, h4, h5, h6{font-size:1em;margin:0.4em 0;}"
                    "ol, ul{margin:0.4em 1.2em;}li{margin:0.2em 0;}"
                )
                return f"<div style='{style}'><style>{extra_css}</style>" + html + "</div>"
            except Exception:
                s = re.sub(r"```[\s\S]*?```", lambda m: m.group(0).strip('`'), md)
                s = re.sub(r"^\s*#{1,6}\s*", "", s, flags=re.MULTILINE)
                s = re.sub(r"\*\*(.*?)\*\*", r"\1", s)
                s = re.sub(r"\*(.*?)\*", r"\1", s)
                s = re.sub(r"_(.*?)_", r"\1", s)
                s = re.sub(r"^\s*[-*]\s+", "• ", s, flags=re.MULTILINE)
                s = re.sub(r"`([^`]+)`", r"\1", s)
                s = re.sub(r"\n{3,}", "\n\n", s)
                return "<div>" + s.strip().replace("\n", "<br/>") + "</div>"

        html = _md_to_html(reply_clean)
        try:
            if re.search(r"<p\b", html):
                html = re.sub(r"(<p\b[^>]*>)", r"\1<b>[助理]</b> ", html, count=1)
            else:
                html = re.sub(r"(<div\b[^>]*>)", r"\1<b>[助理]</b> ", html, count=1)
        except Exception:
            pass
        cursor = self._chat.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertBlock()
        self._chat.setTextCursor(cursor)
        self._chat.insertHtml(html)
        logging.debug("[CHAT-HTML] reply_html_head=%s", html[:200].replace("\n", " "))
        self._debug_dump_last_blocks(self._chat, "after_reply", max_blocks=5)
        self._inp.clear()
        self._send.setEnabled(True)
        self._inp.setEnabled(True)
        if self._tts and reply:
            try:
                self._tts.speak("这是我的建议。")
            except Exception:
                logging.exception("TTS speak failed in AdvisorDialog")
        if self._ask_thread:
            self._ask_thread.quit()
            self._ask_thread = None
        if self._ask_timer:
            with contextlib.suppress(Exception):
                self._ask_timer.stop()
            self._ask_timer = None
        self._btn_cancel.setEnabled(False)

    @Slot(str)
    def _on_ask_fail(self, err: str) -> None:
        def _friendly(e: str) -> str:
            s = e.lower()
            if "getaddrinfo failed" in s:
                return "网络解析失败（可能离线/DNS 问题）"
            if "timed out" in s or "timeout" in s:
                return "请求超时，请稍后重试"
            if "1006" in s or "connection is closed" in s:
                return "连接中断，请检查网络或凭据"
            return e

        self._insert_line("[错误]", _friendly(err))
        self._send.setEnabled(True)
        self._inp.setEnabled(True)
        if self._ask_thread:
            self._ask_thread.quit()
            self._ask_thread = None
        if self._ask_timer:
            with contextlib.suppress(Exception):
                self._ask_timer.stop()
            self._ask_timer = None
        self._btn_cancel.setEnabled(False)

    def _disconnect_ask_signals(self) -> None:
        w = self._ask_worker
        if not w:
            return
        with contextlib.suppress(Exception):
            w.finished.disconnect(self._on_ask_done)
        with contextlib.suppress(Exception):
            w.failed.disconnect(self._on_ask_fail)
        self._ask_worker = None

    @Slot()
    def _on_ask_cancel(self) -> None:
        """ 取消当前请求 """
        self._disconnect_ask_signals()
        self._send.setEnabled(True)
        self._inp.setEnabled(True)
        self._btn_cancel.setEnabled(False)
        self._insert_line("[系统]", "已取消本次请求")
        if self._ask_timer:
            with contextlib.suppress(Exception):
                self._ask_timer.stop()
            self._ask_timer = None
        if self._ask_thread:
            with contextlib.suppress(Exception):
                self._ask_thread.quit()
            self._ask_thread = None

    @Slot()
    def _on_ask_timeout(self) -> None:
        """ 当前请求超时 """
        self._disconnect_ask_signals()
        self._send.setEnabled(True)
        self._inp.setEnabled(True)
        self._btn_cancel.setEnabled(False)
        self._insert_line("[系统]", "等待超时，请稍后重试或检查网络配置。")
        if self._ask_thread:
            with contextlib.suppress(Exception):
                self._ask_thread.quit()
            self._ask_thread = None
        self._send.setEnabled(True)
        self._inp.setEnabled(True)
        self._btn_cancel.setEnabled(False)
        self._insert_line("[系统]", "等待超时，请稍后重试或检查网络配置。")
        if self._ask_thread:
            with contextlib.suppress(Exception):
                self._ask_thread.quit()
            self._ask_thread = None
