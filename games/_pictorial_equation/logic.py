from __future__ import annotations

import random

# no external typing imports required

_EMOJIS = ["🍎", "🍌", "🍇", "🍓", "🍊", "🌟", "🌸", "🚗", "🎈"]


class PictorialEquationGenerator:
    """图文方程题目生成器（两元一次）。"""

    def generate(self) -> tuple[str, str, tuple[int, int], str]:
        """ 生成图文方程题目。"""
        # 选择两个不同的表情
        e1, e2 = random.sample(_EMOJIS, 2)
        while True:
            x = random.randint(0, 99)
            y = random.randint(0, 99)
            if x == 0 and y == 0:
                continue
            a1 = random.randint(2, 9)
            a2 = random.randint(2, 9)
            s1 = a1 * x + a2 * y
            s2 = x + y
            break
        eq_text = f"{e1}*{a1} + {e2}*{a2} = {s1}\n{e1} + {e2} = {s2}"
        return e1, e2, (x, y), eq_text

