"""Pictorial equation game internal package.

公开常用入口，便于外部直接导入：

- PictorialEquationDialog：UI 对话框
- PictorialEquationGenerator：题目生成器
"""

from .logic import PictorialEquationGenerator
from .ui import PictorialEquationDialog

__all__ = [
	"PictorialEquationDialog",
	"PictorialEquationGenerator",
]
