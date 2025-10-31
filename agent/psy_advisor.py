"""心理助理：接入讯飞开放平台（SparkCube）并支持多轮对话"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from integrations import SparkClient, SparkConfig


@dataclass
class ChildProfile:
    age: int = 5
    mood: str = "愉快"
    interests: List[str] = field(default_factory=list)
    notes: str = ""


class ChatSession:
    def __init__(self, system_prompt: Optional[str] = None) -> None:
        self.messages: List[Dict[str, str]] = []
        if system_prompt:
            self.messages.append({"role": "system", "content": system_prompt})

    def append_user(self, text: str) -> None:
        self.messages.append({"role": "user", "content": text})

    def append_assistant(self, text: str) -> None:
        self.messages.append({"role": "assistant", "content": text})


class Advisor:
    """心理助理：封装 Spark 多轮对话。"""

    def __init__(self, cfg: Optional[SparkConfig] = None) -> None:
        # 显式标注，便于类型检查
        self.client: SparkClient = SparkClient(cfg)

    @staticmethod
    def _default_system(profile: Optional[ChildProfile]) -> str:
        meta = ""
        if profile is not None:
            meta = f"孩子年龄:{profile.age}; 情绪:{profile.mood}; 兴趣:{','.join(profile.interests)}; 备注:{profile.notes}"
        return (
            "你是一位儿童发展心理学助理，请基于家长的叙述从‘可能原因’与‘具体可执行策略’两部分给出建议，"
            "语气温和而坚定；优先强调连结与共情，再给出结构化建议。"
            + ("\n已知画像：" + meta if meta else "")
        )

    def start_session(self, profile: Optional[ChildProfile] = None) -> ChatSession:
        return ChatSession(self._default_system(profile))

    def ask(self, session: ChatSession, text: str) -> str:
        session.append_user(text)
        reply = self.client.chat(session.messages)
        if reply:
            session.append_assistant(reply)
        return reply


def analyze_profile(profile: ChildProfile, question: str) -> str:
    """一次性问答：根据画像给出建议文本（非 JSON）"""
    adv = Advisor()
    sess = adv.start_session(profile)
    return adv.ask(sess, question)
