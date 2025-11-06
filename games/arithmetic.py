"""Backward-compatible wrapper module for ArithmeticDialog.

原模块保留为薄包装，实际实现已拆分至 `games._arithmetic` 子包：
- 逻辑：`games._arithmetic.logic.ArithmeticGenerator`
- 界面：`games._arithmetic.ui.ArithmeticDialog`
"""

from ._arithmetic.ui import ArithmeticDialog

__all__ = ["ArithmeticDialog"]
