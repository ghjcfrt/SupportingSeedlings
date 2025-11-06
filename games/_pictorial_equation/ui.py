from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QVBoxLayout, QWidget)

from .logic import PictorialEquationGenerator


class PictorialEquationDialog(QDialog):
    """图文方程（两元一次）对话框（UI）。"""

    def __init__(self, parent: QWidget | None = None, *, tts=None) -> None:
        """ 初始化对话框。"""
        super().__init__(parent)
        self.setWindowTitle("图文方程（两元一次）")
        self.setFixedSize(560, 360)
        self._tts = tts
        self._answer: Optional[tuple[int, int]] = None
        self._e1 = ""
        self._e2 = ""
        self._gen = PictorialEquationGenerator()
        self._build_ui()
        self._new_question()

    def _build_ui(self) -> None:
        """ 构建用户界面。"""
        root = QVBoxLayout(self)
        self._eq_label = QLabel("")
        self._eq_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._eq_label.setStyleSheet("font-size: 30px;")
        self._eq_label.setWordWrap(True)
        root.addWidget(self._eq_label)

        self._text_label = QLabel("每个表情代表一个数字（0-99）。请根据等式分别填出它们代表的数字：")
        self._text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._text_label.setStyleSheet("font-size: 16px; color:#666;")
        root.addWidget(self._text_label)

        row1 = QHBoxLayout()
        row1.setSpacing(6)
        row1.setContentsMargins(0, 0, 0, 0)
        self._lab1 = QLabel("")
        self._lab1.setStyleSheet("font-size: 26px;")
        self._lab1.setContentsMargins(0, 0, 0, 0)
        row1.addWidget(self._lab1)
        self._inp1 = QLineEdit()
        self._inp1.setPlaceholderText("数字")
        self._inp1.setValidator(QIntValidator(0, 99, self))
        self._inp1.returnPressed.connect(self._check)
        self._inp1.setFixedWidth(110)
        self._inp1.setFixedHeight(40)
        self._inp1.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._inp1.setStyleSheet("font-size: 22px;")
        row1.addWidget(self._inp1)
        row1_box = QWidget()
        row1_box.setLayout(row1)
        root.addWidget(row1_box, 0, Qt.AlignmentFlag.AlignHCenter)

        row2 = QHBoxLayout()
        row2.setSpacing(6)
        row2.setContentsMargins(0, 0, 0, 0)
        self._lab2 = QLabel("")
        self._lab2.setStyleSheet("font-size: 26px;")
        self._lab2.setContentsMargins(0, 0, 0, 0)
        row2.addWidget(self._lab2)
        self._inp2 = QLineEdit()
        self._inp2.setPlaceholderText("数字")
        self._inp2.setValidator(QIntValidator(0, 99, self))
        self._inp2.returnPressed.connect(self._check)
        self._inp2.setFixedWidth(110)
        self._inp2.setFixedHeight(40)
        self._inp2.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._inp2.setStyleSheet("font-size: 22px;")
        row2.addWidget(self._inp2)
        row2_box = QWidget()
        row2_box.setLayout(row2)
        root.addWidget(row2_box, 0, Qt.AlignmentFlag.AlignHCenter)

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
        """将文本转化为语音并播放。"""
        try:
            if self._tts:
                self._tts.speak(text)
        except Exception:
            pass

    def _new_question(self) -> None:
        """ 生成新题目。 """
        e1, e2, answer, eq_text = self._gen.generate()
        self._e1, self._e2 = e1, e2
        self._answer = answer
        self._eq_label.setText(eq_text)
        self._text_label.setText("每个表情代表一个数字（0-99）。\n请根据等式分别填出它们代表的数字：")
        self._hint.setText("")
        self._lab1.setText(f"{self._e1}=")
        self._lab2.setText(f"{self._e2}=")
        self._inp1.clear()
        self._inp2.clear()
        self._inp1.setFocus()

    def _check(self) -> None:
        """ 检验答案。"""
        if self._answer is None:
            return
        t1 = self._inp1.text().strip()
        t2 = self._inp2.text().strip()
        if not t1 or not t2:
            self._hint.setText("请把两个答案都填上哦～")
            return
        try:
            v1 = int(t1)
            v2 = int(t2)
        except ValueError:
            self._hint.setText("需要输入整数。")
            return
        ans1, ans2 = self._answer
        if v1 == ans1 and v2 == ans2:
            self._hint.setStyleSheet("color: #2e7d32;")
            self._hint.setText("太棒了，答对啦！")
            self._speak("答对啦！太棒了！")
        else:
            self._hint.setStyleSheet("color: #c62828;")
            self._hint.setText(
                f"再想想～ 正确答案是 {self._e1}={ans1}，{self._e2}={ans2}"
            )
            self._speak("再想想，我们一起看看正确答案。")
