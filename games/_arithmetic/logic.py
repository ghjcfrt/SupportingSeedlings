from __future__ import annotations

import random
from typing import List


class ArithmeticGenerator:
    """两位数口算题目生成器（加减乘除）。

    规则（默认上限 99）：
    - 加法：a,b ∈ [10,99]；避免两者同时为整十；避免 a==b；避免历史重复（无序对）。
    - 减法：a ∈ [20,99]，b ∈ [2, a-2]；确保 a-b ≥ 2；避免历史重复（有序对）。
    - 乘法：a,b ∈ [6,99]；避免平方题（a==b）；避免历史重复（无序对）。
    - 除法：随机 b ∈ [2,99]，取商 k ∈ [0, min(99, 999//b)]，令 a=b*k，保证整除、答案<100、a<1000；避免历史重复（有序对）。
    - 历史记忆：保存最近 30 题，命中则重试，最多尝试 50 次。
    """

    def __init__(self) -> None:
        """ 初始化题目生成器。 """
        # 标准化三元组历史：(op, a, b)
        self._history: List[tuple[str, int, int]] = []

    def _norm_key(self, op: str, a: int, b: int) -> tuple[str, int, int]:
        """ 标准化历史记录键 """
        if op in {"+", "×"}:  # 无序对
            x, y = (a, b) if a <= b else (b, a)
            return (op, x, y)
        return (op, a, b)

    def _push_history(self, key: tuple[str, int, int]) -> None:
        """ 推入历史记录 """
        self._history.append(key)
        if len(self._history) > 30:
            self._history.pop(0)

    def gen_question(self) -> tuple[str, int]:
        """生成一道两位数口算题目。"""
        for _ in range(50):
            op = random.choice(["+", "-", "×", "÷"])
            if op == "+":
                a = random.randint(10, 99)
                b = random.randint(10, 99)
                if a % 10 == 0 and b % 10 == 0:
                    continue
                if a == b:
                    continue
                key = self._norm_key(op, a, b)
                if key in self._history:
                    continue
                self._push_history(key)
                return f"{a} + {b} = ?", a + b
            if op == "-":
                a = random.randint(20, 99)
                b = random.randint(2, a - 2)
                if a - b < 2:
                    continue
                key = self._norm_key(op, a, b)
                if key in self._history:
                    continue
                self._push_history(key)
                return f"{a} − {b} = ?", a - b
            if op == "×":
                a = random.randint(6, 99)
                b = random.randint(6, 99)
                if a == b:  # 避免平方题
                    continue
                key = self._norm_key(op, a, b)
                if key in self._history:
                    continue
                self._push_history(key)
                return f"{a} × {b} = ?", a * b
            # ÷
            b = random.randint(2, 99)
            k_max = min(99, 999 // b)
            k = random.randint(0, k_max)
            a = b * k
            key = self._norm_key("÷", a, b)
            if key in self._history:
                continue
            self._push_history(key)
            return f"{a} ÷ {b} = ?", k

        # 兜底
        a, b = 47, 18
        key = self._norm_key("+", a, b)
        self._push_history(key)
        return f"{a} + {b} = ?", a + b
