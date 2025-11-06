from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QVBoxLayout, QWidget)

from .logic import ArithmeticGenerator


class ArithmeticDialog(QDialog):
    """两位数口算（+ − × ÷）对话框（UI）。"""

    def __init__(self, parent: QWidget | None = None, *, tts=None) -> None:
        """初始化对话框。"""
        super().__init__(parent)
        self.setWindowTitle("两位数口算（+ − × ÷）")
        self.setFixedSize(360, 220)
        self._tts = tts
        self._answer: Optional[int] = None
        self._expr_text: str = ""
        self._gen = ArithmeticGenerator()
        self._build_ui()
        self._new_question()

    def _build_ui(self) -> None:
        """构建用户界面。"""
        root = QVBoxLayout(self)
        self._q_label = QLabel("题目")
        self._q_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._q_label.setStyleSheet("font-size: 22px; font-weight: 600;")
        root.addWidget(self._q_label)

        row = QHBoxLayout()
        row.addWidget(QLabel("你的答案："))
        self._inp = QLineEdit()
        self._inp.setPlaceholderText("请输入整数")
        self._inp.setValidator(QIntValidator(-9999, 9999, self))
        self._inp.returnPressed.connect(self._check)
        row.addWidget(self._inp, 1)
        root.addLayout(row)

        hint_row = QHBoxLayout()
        self._hint = QLabel("")
        self._hint.setStyleSheet("color:#666;")
        hint_row.addWidget(self._hint)
        root.addLayout(hint_row)

        ctrl = QHBoxLayout()
        self._btn_check = QPushButton("检验")
        self._btn_check.clicked.connect(self._check)
        self._btn_next = QPushButton("下一题")
        self._btn_next.clicked.connect(self._new_question)
        ctrl.addWidget(self._btn_check)
        ctrl.addWidget(self._btn_next)
        root.addLayout(ctrl)

    def _speak(self, text: str) -> None:
        """将文本转化为语音并播放。"""
        try:
            if self._tts:
                self._tts.speak(text)
        except Exception:
            pass

    def _new_question(self) -> None:
        """ 生成新题目。 """
        self._expr_text, self._answer = self._gen.gen_question()
        self._q_label.setText(self._expr_text)
        self._hint.setText("")
        self._inp.clear()
        self._inp.setFocus()

    def _check(self) -> None:
        """ 检验答案。"""
        if self._answer is None:
            return
        text = self._inp.text().strip()
        if not text:
            self._hint.setText("请先输入答案哦～")
            return
        try:
            val = int(text)
        except ValueError:
            self._hint.setText("需要输入整数。")
            return
        if val == self._answer:
            self._hint.setStyleSheet("color: #2e7d32;")
            self._hint.setText("答对啦！试试下一题～")
            self._speak("答对啦！太棒了！")
        else:
            self._hint.setStyleSheet("color: #c62828;")
            self._hint.setText(f"再想想～ 正确答案是 {self._answer}")
            self._speak("再想想，我们一起看看正确答案。")
            self._speak("再想想，我们一起看看正确答案。")
        if val == self._answer:
            self._hint.setStyleSheet("color: #2e7d32;")
            self._hint.setText("答对啦！试试下一题～")
            self._speak("答对啦！太棒了！")
        else:
            self._hint.setStyleSheet("color: #c62828;")
            self._hint.setText(f"再想想～ 正确答案是 {self._answer}")
            self._speak("再想想，我们一起看看正确答案。")
