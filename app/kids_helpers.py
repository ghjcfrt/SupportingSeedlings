from __future__ import annotations

import contextlib
import logging
import re
from typing import List, Optional

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QTextEdit, QVBoxLayout,
                               QWidget)

from agent import Advisor, ChildProfile
from games import QuizGenerator
from recommend import Recommender, RecommendRequest


class GameDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, *, recent_object: Optional[str] = None, tts=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("潜能开发小游戏")
        self._tts = tts
        self._gen = QuizGenerator()
        self._recent = recent_object
        self._build_ui()
        self._new_quiz()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        self._q_label = QLabel("问题将出现在这里")
        self._q_label.setWordWrap(True)
        root.addWidget(self._q_label)
        self._opts: List[QPushButton] = []
        for i in range(3):
            btn = QPushButton(f"选项 {i+1}")
            btn.clicked.connect(lambda _, idx=i: self._choose(idx))
            self._opts.append(btn)
            root.addWidget(btn)
        row = QHBoxLayout()
        self._btn_next = QPushButton("下一题")
        self._btn_next.clicked.connect(self._new_quiz)
        row.addWidget(self._btn_next)
        root.addLayout(row)

    def _new_quiz(self) -> None:
        self._quiz = self._gen.generate(self._recent)
        self._q_label.setText(self._quiz.question)
        for i, text in enumerate(self._quiz.options):
            self._opts[i].setText(text)

    def _choose(self, idx: int) -> None:
        correct = (idx == self._quiz.answer_index)
        if self._tts:
            if correct:
                self._tts.speak("答对啦！")
            else:
                self._tts.speak("再想想，我们看看提示。")
            self._tts.speak(self._quiz.tip)


class AdvisorDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, *, tts=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("心理助理（连续对话·讯飞）")
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

    def _on_start(self) -> None:
        # 延迟创建 Advisor，便于缺少凭据时给出友好提示
        if self._advisor is None:
            try:
                self._advisor = Advisor()
            except Exception as e:
                self._chat.append(f"[系统] 无法初始化心理助理：{e}")
                return
        prof = ChildProfile(
            age=int(self._age.currentText()),
            mood=self._mood.currentText(),
            interests=[s.strip() for s in self._interests.text().split(',') if s.strip()],
            notes=self._notes.toPlainText().strip(),
        )
        assert self._advisor is not None
        self._session = self._advisor.start_session(prof)
        self._chat.append("[系统] 已建立会话，欢迎与心理助理对话。")

    def _on_reset(self) -> None:
        self._session = None
        self._chat.clear()
        self._chat.append("[系统] 会话已重置。")

    def _on_send(self) -> None:
        text = self._inp.text().strip()
        if not text:
            return
        if self._session is None:
            self._on_start()
        self._chat.append(f"[家长] {text}")
        # 异步调用，避免阻塞 UI
        try:
            assert self._session is not None and self._advisor is not None
        except AssertionError:
            self._chat.append("[系统] 会话未就绪")
            return
        self._send.setEnabled(False)
        self._inp.setEnabled(False)
        self._chat.append("[助理] 正在思考……")

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
        # 优先用 markdown -> HTML 渲染；若 markdown 库缺失，则退化为简单去标记文本
        def _md_to_html(md: str) -> str:
            try:  # 依赖 python-markdown
                import markdown  # type: ignore
                html = markdown.markdown(md, extensions=["extra", "sane_lists"])
                # 轻量样式：更好的可读性
                return (
                    "<div style='font-size:14px; line-height:1.6'>" + html + "</div>"
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

        html = _md_to_html(reply)
        cursor = self._chat.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._chat.setTextCursor(cursor)
        # 插入“助理”前缀与渲染内容
        self._chat.insertHtml("<b>[助理]</b> ")
        self._chat.insertHtml(html)
        self._chat.insertHtml("<br/>")
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
        self._chat.append(f"[错误] {err}")
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
        self._chat.append("[系统] 已取消本次请求")
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
        self._chat.append("[系统] 等待超时，请稍后重试或检查网络配置。")
        if self._ask_thread:
            with contextlib.suppress(Exception):
                self._ask_thread.quit()
            self._ask_thread = None


class RecommendDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, *, recent_object: Optional[str] = None, tts=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("个性化内容推荐")
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
        root.addWidget(self._out)

    def _on_reco(self) -> None:
        # 延迟创建 Recommender
        if self._rec is None:
            try:
                self._rec = Recommender()
            except Exception as e:
                self._out.setText(f"初始化推荐引擎失败：{e}\n请先配置 XF_APPID/XF_API_KEY/XF_API_SECRET 环境变量后重试。")
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
        self._out.append("[系统] 正在为你生成推荐……")

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
            try:
                import markdown  # type: ignore
                html = markdown.markdown(md_text, extensions=["extra", "sane_lists"])
                return "<div style='font-size:14px; line-height:1.6'>" + html + "</div>"
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
        self._out.append(f"[错误] 生成失败：{err}")
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
        self._out.append("[系统] 已取消本次生成")
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
        self._out.append("[系统] 等待超时，请稍后重试或检查网络配置。")
        if self._reco_thread:
            with contextlib.suppress(Exception):
                self._reco_thread.quit()
            self._reco_thread = None
        self._btn.setEnabled(True)
        self._btn_regen.setEnabled(True)
        self._btn_cancel.setEnabled(False)
        self._out.append("[系统] 等待超时，请稍后重试或检查网络配置。")
        if self._reco_thread:
            with contextlib.suppress(Exception):
                self._reco_thread.quit()
            self._reco_thread = None
