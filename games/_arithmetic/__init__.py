"""Arithmetic game internal package.

公开常用入口，便于外部直接导入：

- ArithmeticDialog：UI 对话框
- ArithmeticGenerator：题目生成器
"""

from .logic import ArithmeticGenerator
from .ui import ArithmeticDialog

__all__ = [
	"ArithmeticDialog",
	"ArithmeticGenerator",
]
