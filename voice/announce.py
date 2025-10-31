"""播报工具

仅保留：
- 通用文本播报
- 数量播报

"""

from __future__ import annotations

import time

try:
    from .tts import speak_async as _speak_async
except (ImportError, OSError, RuntimeError):  # 可选依赖缺失
    _speak_async = None

try:
    # 包内提供中文标签映射
    from detection.coco_labels_cn import coco_labels_cn
except (ImportError, OSError):  # 极端情况下缺失则提供空映射
    coco_labels_cn = {}


def _noop(_: str) -> None:
    return None


_speak_func = _speak_async or _noop


def set_speaker(func) -> None:
    """设置自定义播报函数 例如 TTSManager.speak 建议在应用启动时调用一次"""
    globals()["_speak_func"] = func


def _measure_word(label_cn: str) -> str:
    """根据中文标签返回对应的量词"""
    by_name = {
        "人": "名",
        "小汽车": "辆",
        "自行车": "辆",
        "摩托车": "辆",
        "公交车": "辆",
        "卡车": "辆",
        "火车": "列",
        "船": "艘",
        "红绿灯": "个",
        "飞机": "架",
        "狗": "只",
        "猫": "只",
        "鸟": "只",
        "马": "匹",
        "羊": "只",
        "大象": "头",
        "斑马": "只",
        "长颈鹿": "只",
        "盆栽植物": "盆",
        "瓶子": "个",
        "椅子": "把",
        "电视": "台",
        "笔记本电脑": "台",
        "手机": "部",
    }
    return by_name.get(label_cn, "个")


_ONE = 1
_TWO = 2


def _count_to_cn(n: int) -> str:
    """将数量转换为中文表达形式"""
    if n <= _ONE:
        return "一"
    if n == _TWO:
        return "两"
    return str(n)


THRESHOLD_EXACT_READ = 3  # 小于该阈值播报具体数量，否则使用量词


def compose_non_tl_phrase(counts: dict[int, int]) -> str | None:
    """基于非交通类目标数量构建播报短语"""
    parts: list[str] = []
    for cls_id, cnt in counts.items():
        if cnt <= 0:
            continue
        name = coco_labels_cn.get(cls_id)
        if not name:
            continue
        mw = _measure_word(name)
        if cnt < THRESHOLD_EXACT_READ:
            parts.append(f"{_count_to_cn(cnt)}{mw}{name}")
        else:
            parts.append(f"多{mw}{name}")
    if not parts:
        return None
    return "，".join(parts)


def speak_non_tl(counts: dict[int, int], prefix: str | None = "检测到") -> None:
    """基于非交通类目标数量进行一次性播报"""
    phrase = compose_non_tl_phrase(counts)
    if not phrase:
        return
    text = f"{prefix}：{phrase}" if prefix else phrase
    _speak_func(text)


class Announcer:
    """带去重与最小间隔的播报器"""

    def __init__(
        self,
        min_interval_sec: float = 1.5,
    ) -> None:
        self._last_text: str | None = None
        self._last_t: float = 0.0
        self._min_interval = float(min_interval_sec)

    def say(self, text: str) -> None:
        """执行播报，若与上次相同且间隔过短则忽略"""
        now = time.time()
        if now - self._last_t < self._min_interval:
            return
        self._last_text = text
        self._last_t = now
        _speak_func(text)

    def say_non_tl(self, counts: dict[int, int]) -> None:
        """基于非交通类目标数量进行一次性播报"""
        phrase = compose_non_tl_phrase(counts)
        if not phrase:
            return
        self.say(f"检测到：{phrase}")
