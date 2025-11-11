from __future__ import annotations

import re


def clean_advisor_reply(md: str) -> str:
    """清理心理助理模型回复的尾部签名/祝词等噪音，返回清理后的 Markdown 文本。"""
    try:
        s = md.rstrip()
        if not s:
            return md
        lines = s.splitlines()
        # 去掉末尾空行
        while lines and lines[-1].strip() == "":
            lines.pop()
        if not lines:
            return ""
        sig_re = re.compile(r"^\s*(祝好[！!。,.，]*|此致\s*敬礼?|此致|敬礼|Best regards|Kind regards|Regards|Sincerely|Thanks|Thank you)\s*$", re.IGNORECASE)
        name_placeholder_re = re.compile(r"^\s*\[?\s*您.?的姓名\s*\]?\s*$")
        name_bracket_re = re.compile(r"^\s*\[.*?姓名.*?\]\s*$")
        role_line_re = re.compile(r"^\s*(扶苗(心理)?助理|.*助理|.*团队|.*老师)\s*$")
        dash_name_re = re.compile(r"^\s*[\-–—]\s*.*$")

        def _is_name_like(line: str) -> bool:
            """ 判断一行文本是否像是“姓名占位”或“署名” """
            t = line.strip()
            return bool(
                name_placeholder_re.match(t)
                or name_bracket_re.match(t)
                or role_line_re.match(t)
                or dash_name_re.match(t)
            )

        # 情形1：末行是祝词 -> 删除；若前一行为“姓名/占位/角色”也一并删除
        if lines and sig_re.match(lines[-1]):
            lines.pop()
            if lines and _is_name_like(lines[-1]):
                lines.pop()
            return "\n".join(lines).rstrip()

        # 情形2：末行是“姓名/占位/角色”，且其上一行为祝词 -> 两行一起删除
        if len(lines) >= 2 and _is_name_like(lines[-1]) and sig_re.match(lines[-2]):
            lines.pop()
            lines.pop()
            return "\n".join(lines).rstrip()

        # 情形3：仅有末行是明显的“姓名占位”（无祝词），也删除
        if lines and _is_name_like(lines[-1]):
            lines.pop()
            return "\n".join(lines).rstrip()

        return md
    except Exception:
        # 任何异常都保持原文，避免吞内容
        return md
