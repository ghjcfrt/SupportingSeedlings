"""Backward-compatible wrapper module for SudokuDialog.

原模块保留为薄包装，实际实现已拆分至 `games._sudoku` 子包：
- 逻辑：`games._sudoku.logic.*`
- 界面：`games._sudoku.ui.SudokuDialog`
"""

from ._sudoku.ui import SudokuDialog

__all__ = ["SudokuDialog"]