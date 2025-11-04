from __future__ import annotations

import random
from typing import Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QVBoxLayout, QWidget)


class ArithmeticDialog(QDialog):
    """两位数口算（加减乘除）

    - 操作数范围：0..99（两位数）
    - 减法保证结果非负；除法保证整除且被除数/除数均不超过 99。
    """

    def __init__(self, parent: QWidget | None = None, *, tts=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("两位数口算（+ − × ÷）")
        self.setFixedSize(360, 220)
        self._tts = tts
        self._answer: Optional[int] = None
        self._expr_text: str = ""
        # 记忆最近题目，降低重复率（存储标准化三元组：op,a,b）
        self._history: list[tuple[str, int, int]] = []
        self._build_ui()
        self._new_question()

    def _build_ui(self) -> None:
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
        try:
            if self._tts:
                self._tts.speak(text)
        except Exception:
            pass

    def _new_question(self) -> None:
        self._expr_text, self._answer = self._gen_question()
        self._q_label.setText(self._expr_text)
        self._hint.setText("")
        self._inp.clear()
        self._inp.setFocus()

    def _gen_question(self) -> Tuple[str, int]:
        """生成一题并尽量避免重复和过于简单的算式。

        规则（默认上限 99）：
        - 加法：a,b ∈ [10,99]；避免两者同时为整十；避免和历史重复（无序对）。
        - 减法：a ∈ [20,99]，b ∈ [2, a-2]；确保 a-b ≥ 2；避免历史重复（有序对）。
        - 乘法：a,b ∈ [6,99]；避免 0/1；避免小于 6 的平方（2×2,3×3,4×4,5×5）；避免历史重复（无序对）。
        - 除法：选择 b ∈ [6,49]，k ∈ [2, 99//b]，a=b*k；避免 a==b（k=1 已排除）；避免历史重复（有序对）。
        - 历史记忆：保存最近 30 题，命中则重试，最多尝试 50 次。
        """

        def norm_key(op: str, a: int, b: int) -> tuple[str, int, int]:
            if op in {"+", "×"}:  # 无序
                x, y = (a, b) if a <= b else (b, a)
                return (op, x, y)
            return (op, a, b)

        def push_history(key: tuple[str, int, int]) -> None:
            self._history.append(key)
            if len(self._history) > 30:
                self._history.pop(0)

        for _ in range(50):
            op = random.choice(["+", "-", "×", "÷"])
            if op == "+":
                a = random.randint(10, 99)
                b = random.randint(10, 99)
                # 避免两者同时为整十，且避免 a==b
                if a % 10 == 0 and b % 10 == 0:
                    continue
                if a == b:
                    continue
                key = norm_key(op, a, b)
                if key in self._history:
                    continue
                push_history(key)
                return f"{a} + {b} = ?", a + b
            if op == "-":
                a = random.randint(20, 99)
                b = random.randint(2, a - 2)
                if a - b < 2:
                    continue
                key = norm_key(op, a, b)
                if key in self._history:
                    continue
                push_history(key)
                return f"{a} − {b} = ?", a - b
            if op == "×":
                a = random.randint(6, 99)
                b = random.randint(6, 99)
                # 避免所有平方题（a==b）
                if a == b:
                    continue
                key = norm_key(op, a, b)
                if key in self._history:
                    continue
                push_history(key)
                return f"{a} × {b} = ?", a * b
            # ÷：b 为除数，k 为商，a=b*k≤99；避免 k=1（a==b）
            b = random.randint(6, 49)
            k_max = 99 // b
            if k_max < 2:
                continue
            k = random.randint(2, k_max)
            a = b * k
            key = norm_key("÷", a, b)
            if key in self._history:
                continue
            push_history(key)
            return f"{a} ÷ {b} = ?", k

        # 若重试仍失败，退回一个较为稳妥的题目
        a, b = 47, 18
        key = norm_key("+", a, b)
        push_history(key)
        return f"{a} + {b} = ?", a + b

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
            self._hint.setText("答对啦！试试下一题～")
            self._speak("答对啦！太棒了！")
        else:
            self._hint.setStyleSheet("color: #c62828;")
            self._hint.setText(f"再想想～ 正确答案是 {self._answer}")
            self._speak("再想想，我们一起看看正确答案。")
