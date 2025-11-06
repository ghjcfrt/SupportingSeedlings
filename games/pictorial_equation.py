"""Backward-compatible wrapper module for PictorialEquationDialog.

原模块保留为薄包装，实际实现已拆分至 `games._pictorial_equation` 子包：
- 逻辑：`games._pictorial_equation.logic.PictorialEquationGenerator`
- 界面：`games._pictorial_equation.ui.PictorialEquationDialog`
"""

from ._pictorial_equation.ui import PictorialEquationDialog

__all__ = ["PictorialEquationDialog"]
