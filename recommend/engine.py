from __future__ import annotations

import json
from dataclasses import dataclass
from typing import List, Literal

from integrations import SparkClient

ContentType = Literal["绘本", "故事音乐", "科普视频"]


@dataclass
class Recommendation:
    title: str
    url: str | None
    content_type: ContentType
    tags: List[str]
    age_min: int
    age_max: int
    prompt: str  # 互动问题提示


@dataclass
class RecommendRequest:
    age: int
    interests: List[str]
    level: str = "启蒙"
    recent_object: str | None = None  # 最近识别的物体（可空）


class Recommender:
    """基于讯飞大模型生成结构化推荐（JSON 输出）"""

    def __init__(self) -> None:
        self._client = SparkClient()

    def recommend(self, req: RecommendRequest, k: int = 5) -> List[Recommendation]:
        sys = (
            "你是一名儿童内容推荐助手，请基于孩子年龄与兴趣生成适合的推荐列表，"
            "涵盖‘绘本/故事音乐/科普视频’三类中的至少一类；"
            "请严格输出 JSON 数组，不要出现解释性文字。JSON 模式：\n"
            "[{\n  'title': str,\n  'url': str|null,\n  'content_type': '绘本'|'故事音乐'|'科普视频',\n  'tags': [str],\n  'age_min': int,\n  'age_max': int,\n  'prompt': str\n}]"
        )
        interests = ", ".join(req.interests) if req.interests else "无"
        user = (
            f"孩子年龄: {req.age}; 认知层级: {req.level}; 兴趣: {interests}; 需要 {k} 条;"
            + (f" 最近识别物体: {req.recent_object};" if req.recent_object else "")
            + " 请多样化，并为每条生成一个简短的互动问题（prompt）。"
        )
        messages = [{"role": "system", "content": sys}, {"role": "user", "content": user}]
        text = self._client.chat(messages)
        # 容错解析：尝试提取 JSON 数组
        try:
            # 去掉可能的 markdown 包裹
            cleaned = text.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.strip("`")
                idx = cleaned.find("[")
                cleaned = cleaned[idx:]
            data = json.loads(cleaned)
            items: List[Recommendation] = []
            for e in data[:k]:
                items.append(
                    Recommendation(
                        title=e.get("title", ""),
                        url=e.get("url"),
                        content_type=e.get("content_type", "绘本"),
                        tags=e.get("tags", []) or [],
                        age_min=int(e.get("age_min", max(3, req.age - 1))),
                        age_max=int(e.get("age_max", req.age + 2)),
                        prompt=e.get("prompt", ""),
                    )
                )
            return items
        except Exception:
            # 解析失败时退化为一条纯文本建议
            return [
                Recommendation(
                    title="为你生成了推荐（解析失败，已提供文本）",
                    url=None,
                    content_type="绘本",
                    tags=req.interests,
                    age_min=max(3, req.age - 1),
                    age_max=req.age + 2,
                    prompt=text[:200],
                )
            ]
