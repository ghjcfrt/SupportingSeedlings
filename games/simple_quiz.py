from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class QuizItem:
    question: str
    options: List[str]
    answer_index: int
    tip: str


class QuizGenerator:
    """根据上下文（最近识别物体或通用主题）生成三选一问题"""

    def __init__(self, seed: Optional[int] = None):
        self._rand = random.Random(seed)

    def _make_from_object(self, obj: str) -> QuizItem | None:
        o = obj.lower()
        if any(k in o for k in ["猫", "狗", "动物"]):
            return QuizItem(
                question="下面哪个是哺乳动物的共同特征？",
                options=["会下蛋", "有羽毛", "用奶喂宝宝"],
                answer_index=2,
                tip="哺乳动物会用乳汁喂宝宝，例如猫和狗。",
            )
        if any(k in o for k in ["车", "汽车", "巴士", "车辆"]):
            return QuizItem(
                question="汽车前挡风玻璃的主要作用是？",
                options=["让车更快", "挡风与保护视线", "装饰用"],
                answer_index=1,
                tip="挡风玻璃能防风雨与飞来的小颗粒，保障驾驶视线。",
            )
        if any(k in o for k in ["鸟", "天空", "飞"]):
            return QuizItem(
                question="鸟类飞行时最主要依靠的结构是？",
                options=["尾巴", "翅膀", "嘴巴"],
                answer_index=1,
                tip="翅膀拍动产生升力，帮助鸟在空中飞行。",
            )
        return None

    def _generic(self) -> QuizItem:
        bank = [
            QuizItem(
                question="红、黄、蓝被称为？",
                options=["对比色", "三原色", "补色"],
                answer_index=1,
                tip="三原色可以调出很多其他颜色。",
            ),
            QuizItem(
                question="哪一种是液体？",
                options=["石头", "水", "空气"],
                answer_index=1,
                tip="在常温下，水是液体。",
            ),
            QuizItem(
                question="下列哪一个是昆虫？",
                options=["蜘蛛", "蜻蜓", "螃蟹"],
                answer_index=1,
                tip="蜻蜓有六条腿和一对翅膀，是昆虫。",
            ),
        ]
        return self._rand.choice(bank)

    def generate(self, recent_object: Optional[str] = None) -> QuizItem:
        if recent_object:
            q = self._make_from_object(recent_object)
            if q:
                return q
        return self._generic()
