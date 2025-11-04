from __future__ import annotations

import random
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QVBoxLayout, QWidget)

_EMOJIS = ["🍎", "🍌", "🍇", "🍓", "🍊", "🌟", "🌸", "🚗", "🎈"]


class PictorialEquationDialog(QDialog):
    """图文算式（表情计数）

    展示两组表情的数量求和，如：🍎🍎🍎 + 🍌🍌，让孩子输入总数。
    """

    def __init__(self, parent: QWidget | None = None, *, tts=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("图文算式（表情计数）")
        self.setFixedSize(420, 260)
        self._tts = tts
        self._answer: Optional[int] = None
        self._build_ui()
        self._new_question()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        self._img_label = QLabel("")
        self._img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img_label.setStyleSheet("font-size: 34px;")
        root.addWidget(self._img_label)

        self._text_label = QLabel("")
        self._text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._text_label.setStyleSheet("font-size: 18px; color:#666;")
        root.addWidget(self._text_label)

        row = QHBoxLayout()
        row.addWidget(QLabel("总共有："))
        self._inp = QLineEdit()
        self._inp.setPlaceholderText("请输入总数")
        self._inp.setValidator(QIntValidator(0, 999, self))
        self._inp.returnPressed.connect(self._check)
        row.addWidget(self._inp, 1)
        row.addWidget(QLabel("个"))
        root.addLayout(row)

        self._hint = QLabel("")
        root.addWidget(self._hint)

        ctrl = QHBoxLayout()
        btn_check = QPushButton("检验")
        btn_check.clicked.connect(self._check)
        btn_next = QPushButton("下一题")
        btn_next.clicked.connect(self._new_question)
        ctrl.addWidget(btn_check)
        ctrl.addWidget(btn_next)
        root.addLayout(ctrl)

    def _speak(self, text: str) -> None:
        try:
            if self._tts:
                self._tts.speak(text)
        except Exception:
            pass

    def _new_question(self) -> None:
        e1, e2 = random.sample(_EMOJIS, 2)
        c1 = random.randint(1, 9)
        c2 = random.randint(1, 9)
        self._answer = c1 + c2
        self._img_label.setText(f"{e1 * c1}  +  {e2 * c2}")
        self._text_label.setText("共有多少个？")
        self._hint.setText("")
        self._inp.clear()
        self._inp.setFocus()

    def _check(self) -> None:
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
            self._hint.setText("太棒了，答对啦！")
            self._speak("答对啦！太棒了！")
        else:
            self._hint.setStyleSheet("color: #c62828;")
            self._hint.setText(f"再想想～ 正确答案是 {self._answer}")
            self._speak("再想想，我们一起看看正确答案。")
