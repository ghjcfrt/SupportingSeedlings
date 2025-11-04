from __future__ import annotations

import contextlib
import json
import logging
import re
from html import escape as _escape
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QFont, QTextBlockFormat, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QTextEdit, QVBoxLayout,
                               QWidget)

from agent import Advisor, ChildProfile
from games import ArithmeticDialog, PictorialEquationDialog, SudokuDialog
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
                # 基本边界
                if size < 8 or size > 48:
                    size = default_size
                if line_h < 1.1 or line_h > 2.4:
                    line_h = default_lh
                return size, line_h
        except Exception:
            # 配置异常时回退默认
            return default_size, default_lh
    return default_size, default_lh


class GameDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, *, recent_object: Optional[str] = None, tts=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("潜能开发小游戏")
        self.setFixedSize(360, 260)
        self._tts = tts
        self._recent = recent_object
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        title = QLabel("选择一个小游戏开始：")
        title.setWordWrap(True)
        root.addWidget(title)

        btn1 = QPushButton("两位数口算（+ − × ÷）")
        btn1.clicked.connect(self._open_arithmetic)
        root.addWidget(btn1)

        btn2 = QPushButton("图文算式（表情计数）")
        btn2.clicked.connect(self._open_pictorial)
        root.addWidget(btn2)

        btn3 = QPushButton("数独（9×9）")
        btn3.clicked.connect(self._open_sudoku)
        root.addWidget(btn3)

        root.addStretch(1)

    def _open_arithmetic(self) -> None:
        dlg = ArithmeticDialog(self, tts=self._tts)
        dlg.exec()

    def _open_pictorial(self) -> None:
        dlg = PictorialEquationDialog(self, tts=self._tts)
        dlg.exec()

    def _open_sudoku(self) -> None:
        dlg = SudokuDialog(self)
        dlg.exec()


class AdvisorDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, *, tts=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("心理助理（连续对话·讯飞）")
        self.setFixedSize(450, 700)
        self._tts = tts
        self._advisor: Advisor | None = None
        self._session = None
        self._ask_thread: QThread | None = None
        self._ask_worker: QObject | None = None
        self._ask_timer: QTimer | None = None
        self._build_ui()

    class _AskWorker(QObject):
        finished = Signal(str)
        failed = Signal(str)

        def __init__(self, advisor: Advisor, session, text: str) -> None:
            super().__init__()
            self._advisor = advisor
            self._session = session
            self._text = text

        def run(self) -> None:
            try:
                reply = self._advisor.ask(self._session, self._text)
                self.finished.emit(reply)
            except Exception as e:
                logging.exception("AdvisorDialog _AskWorker failed")
                self.failed.emit(str(e))

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        # 基本画像与会话控制
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
        # 统一默认显示效果；支持通过 config.json 配置 CHAT_FONT_SIZE/CHAT_LINE_HEIGHT
        try:
            fs, lh = _load_chat_style()
            self._chat_fs, self._chat_lh = fs, lh  # 记录以便调试输出
            self._chat.document().setDefaultStyleSheet(
                f"body, p, div {{ font-size:{fs}px; line-height:{lh}; }}"
            )
            # 同步设置文档默认字体（像素大小），确保列表序号/标题等也按照同一字号渲染
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

        # 免责声明（固定展示在界面底部，字体略小/灰色）
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
        # 开一个全新的段落，避免落在上一条 HTML 的<li>/<h*> 等上下文中
        cursor.insertBlock()
        # 若仍处于列表环境，显式移出该列表
        removed_from_list = False
        try:
            lst = cursor.currentList()
            if lst is not None:
                lst.remove(cursor.block())
                removed_from_list = True
        except Exception:
            pass
        # 重置本段的字符/段落格式，避免继承粗体/缩进
        cursor.setCharFormat(QTextCharFormat())
        cursor.setBlockFormat(QTextBlockFormat())
        # 插入为当前段内联 HTML（依赖默认样式控制字号/行距）
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
                # 记录点大小与像素大小（像素值更能代表最终渲染大小）
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
        # 延迟创建 Advisor，便于缺少凭据时给出友好提示
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
        self._session = None
        self._chat.clear()
        self._insert_line("[系统]", "会话已重置。")

    def _on_send(self) -> None:
        text = self._inp.text().strip()
        if not text:
            return
        if self._session is None:
            self._on_start()
        self._insert_line("[家长]", text)
        self._debug_dump_last_blocks(self._chat, "after_parent", max_blocks=3)
        # 异步调用，避免阻塞 UI
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
        # 通过绑定到对话框（GUI 线程）的槽函数，避免跨线程操作 UI
        worker.finished.connect(self._on_ask_done)
        worker.failed.connect(self._on_ask_fail)
        th.finished.connect(worker.deleteLater)
        th.finished.connect(th.deleteLater)
        th.start()
        # 启用取消与超时
        self._btn_cancel.setEnabled(True)
        if self._ask_timer is not None:
            try:
                self._ask_timer.stop()
            except Exception:
                pass
        self._ask_timer = QTimer(self)
        self._ask_timer.setSingleShot(True)
        self._ask_timer.setInterval(25000)  # 25s 超时
        self._ask_timer.timeout.connect(self._on_ask_timeout)
        self._ask_timer.start()

    @Slot(str)
    def _on_ask_done(self, reply: str) -> None:
        # 轻量清洗：去掉模型末尾常见的署名/祝词（如“祝好”，“[您的姓名]”等），避免奇怪的名字显示
        def _strip_signature(md: str) -> tuple[str, int]:
            try:
                s = md.rstrip()
                if not s:
                    return md, 0
                lines = s.splitlines()
                removed = 0
                # 先移除末尾空行
                while lines and lines[-1].strip() == "":
                    lines.pop()
                    removed += 1
                if not lines:
                    return "", removed
                sig_re = re.compile(r"^\s*(祝好[！!。,.，]*|此致\s*敬礼?|此致|敬礼|Best regards|Kind regards|Regards|Sincerely|Thanks|Thank you)\s*$", re.IGNORECASE)
                # 仅针对明显的“占位签名/姓名”做处理，避免误删正文
                name_placeholder_re = re.compile(r"^\s*\[?\s*您.?的姓名\s*\]?\s*$")
                name_bracket_re = re.compile(r"^\s*\[.*?姓名.*?\]\s*$")
                role_line_re = re.compile(r"^\s*(扶苗(心理)?助理|.*助理|.*团队|.*老师)\s*$")
                dash_name_re = re.compile(r"^\s*[\-–—]\s*.*$")

                def _is_name_like(line: str) -> bool:
                    line_str = line.strip()
                    return bool(
                        name_placeholder_re.match(line_str)
                        or name_bracket_re.match(line_str)
                        or role_line_re.match(line_str)
                        or dash_name_re.match(line_str)
                    )

                # 情形1：末行是祝词 -> 删除；若前一行为“姓名/占位/角色”也一并删除
                if lines and sig_re.match(lines[-1]):
                    lines.pop()
                    removed += 1
                    if lines and _is_name_like(lines[-1]):
                        lines.pop()
                        removed += 1
                    return "\n".join(lines).rstrip(), removed

                # 情形2：末行是“姓名/占位/角色”，且其上一行为祝词 -> 两行一起删除
                if len(lines) >= 2 and _is_name_like(lines[-1]) and sig_re.match(lines[-2]):
                    lines.pop()
                    lines.pop()
                    removed += 2
                    return "\n".join(lines).rstrip(), removed

                # 情形3：仅有末行是明显的“姓名占位”（无祝词），也删除
                if lines and _is_name_like(lines[-1]):
                    lines.pop()
                    removed += 1
                    return "\n".join(lines).rstrip(), removed

                return md, 0
            except Exception:
                return md, 0

        # 先清理末尾署名/祝词
        reply_clean, removed_cnt = _strip_signature(reply)
        if removed_cnt:
            logging.debug("[CHAT-CLEAN] signature_removed=%s lines_removed=%s", True, removed_cnt)

        # 优先用 markdown -> HTML 渲染；若 markdown 库缺失，则退化为简单去标记文本
        def _md_to_html(md: str) -> str:
            # 预处理：当模型未严格产出 Markdown 列表时，确保数字序号或无序项前有换行
            try:
                md = re.sub(r"(?<!^)(?<!\n)\s(1\.\s)", r"\n\n\1", md)
                md = re.sub(r"(?<!^)(?<!\n)\s(([0-9]{1,2})\.\s)", r"\n\1", md)
                md = re.sub(r"(?<!^)(?<!\n)\s([-*]\s)", r"\n\1", md)
            except Exception:
                pass
            try:  # 依赖 python-markdown
                import markdown  # type: ignore
                html = markdown.markdown(md, extensions=["extra", "sane_lists"])
                # 避免有序列表跨消息延续序号，显式从 1 开始
                html = re.sub(r"<ol(?![^>]*start=)", "<ol start='1'", html)
                # 使用与聊天一致的字号/行距，并统一标题/列表字号
                fs, lh = _load_chat_style()
                style = (
                    f"font-size:{fs}px; line-height:{lh};"
                )
                extra_css = (
                    "h1, h2, h3, h4, h5, h6{font-size:1em;margin:0.4em 0;}"
                    "ol, ul{margin:0.4em 1.2em;}li{margin:0.2em 0;}"
                )
                return (
                    f"<div style='{style}'><style>{extra_css}</style>" + html + "</div>"
                )
            except Exception:
                # 退化为去 Markdown 符号的纯文本
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
        # 将助理前缀插入到首个段落中，避免出现在单独一行或字号不一致
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
        # 停止计时与取消按钮
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
            w.finished.disconnect(self._on_ask_done)  # type: ignore[attr-defined]
        with contextlib.suppress(Exception):
            w.failed.disconnect(self._on_ask_fail)  # type: ignore[attr-defined]
        self._ask_worker = None

    @Slot()
    def _on_ask_cancel(self) -> None:
        # 仅取消等待与信号，不强行终止底层 I/O
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
        self._disconnect_ask_signals()
        self._send.setEnabled(True)
        self._inp.setEnabled(True)
        self._btn_cancel.setEnabled(False)
        self._insert_line("[系统]", "等待超时，请稍后重试或检查网络配置。")
        if self._ask_thread:
            with contextlib.suppress(Exception):
                self._ask_thread.quit()
            self._ask_thread = None


class RecommendDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, *, recent_object: Optional[str] = None, tts=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("个性化内容推荐")
        self.setFixedSize(450, 350)
        self._tts = tts
        self._recent = recent_object
        self._rec: Recommender | None = None
        self._reco_thread: QThread | None = None
        self._reco_worker: QObject | None = None
        self._reco_timer: QTimer | None = None
        self._build_ui()

    class _RecoWorker(QObject):
        finished = Signal(list)
        failed = Signal(str)

        def __init__(self, rec: Recommender, req: RecommendRequest) -> None:
            super().__init__()
            self._rec = rec
            self._req = req

        def run(self) -> None:
            try:
                items = self._rec.recommend(self._req)
                self.finished.emit(items)
            except Exception as e:
                logging.exception("RecommendDialog _RecoWorker failed")
                self.failed.emit(str(e))

    def _build_ui(self) -> None:
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
        # 与助理对话区域保持一致的默认样式（可由 config.json 控制）
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

        # 推荐界面也展示免责声明
        try:
            disclaim_fs2 = max(10, int(fs) - 2)  # fs 来自上面的 try 块
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
        # 延迟创建 Recommender
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
        # 异步调用，避免阻塞 UI
        self._btn.setEnabled(False)
        self._btn_regen.setEnabled(False)
        self._insert_out_line("[系统]", "正在为你生成推荐……")

        worker = RecommendDialog._RecoWorker(self._rec, req)
        th = QThread(self)
        self._reco_thread = th
        self._reco_worker = worker
        worker.moveToThread(th)
        th.started.connect(worker.run)

        # 绑定到对话框槽，保证在 GUI 线程更新 UI
        worker.finished.connect(self._on_reco_done)
        worker.failed.connect(self._on_reco_fail)
        th.finished.connect(worker.deleteLater)
        th.finished.connect(th.deleteLater)
        th.start()
        # 启用取消与超时
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
        lines: List[str] = []
        for it in items:
            lines.append(f"[{it.content_type}] {it.title}")
            if it.url:
                lines.append(f"链接：{it.url}")
            if it.tags:
                lines.append("标签：" + ", ".join(it.tags))
            lines.append("互动：" + it.prompt)
            lines.append("")
        # 构造 Markdown 并渲染为 HTML
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
            # 预处理：改善不规范列表的换行
            try:
                md_t = re.sub(r"(?<!^)(?<!\n)\s(1\.\s)", r"\n\n\1", md_text)
                md_t = re.sub(r"(?<!^)(?<!\n)\s(([0-9]{1,2})\.\s)", r"\n\1", md_t)
                md_t = re.sub(r"(?<!^)(?<!\n)\s([-*]\s)", r"\n\1", md_t)
            except Exception:
                md_t = md_text
            try:
                import markdown  # type: ignore
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
        def _friendly(e: str) -> str:
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
        w = self._reco_worker
        if not w:
            return
        with contextlib.suppress(Exception):
            w.finished.disconnect(self._on_reco_done)  # type: ignore[attr-defined]
        with contextlib.suppress(Exception):
            w.failed.disconnect(self._on_reco_fail)  # type: ignore[attr-defined]
        self._reco_worker = None

    @Slot()
    def _on_reco_cancel(self) -> None:
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
        self._disconnect_reco_signals()
        self._btn.setEnabled(True)
        self._btn_regen.setEnabled(True)
        self._btn_cancel.setEnabled(False)
        self._insert_out_line("[系统]", "等待超时，请稍后重试或检查网络配置。")
        if self._reco_thread:
            with contextlib.suppress(Exception):
                self._reco_thread.quit()
            self._reco_thread = None
        self._btn.setEnabled(True)
        self._btn_regen.setEnabled(True)
        self._btn_cancel.setEnabled(False)
        self._insert_out_line("[系统]", "等待超时，请稍后重试或检查网络配置。")
        if self._reco_thread:
            with contextlib.suppress(Exception):
                self._reco_thread.quit()
            self._reco_thread = None
        self._btn_cancel.setEnabled(False)
        self._insert_out_line("[系统]", "等待超时，请稍后重试或检查网络配置。")
        if self._reco_thread:
            with contextlib.suppress(Exception):
                self._reco_thread.quit()
            self._reco_thread = None
