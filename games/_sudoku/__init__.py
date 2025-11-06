"""Sudoku game internal package.

公开常用入口，便于外部直接导入：

- SudokuDialog：UI 对话框
- 逻辑工具：generate_full_grid, mask_grid, mask_grid_unique, grid_to_str, DIFFICULTY_CONFIG
"""

from .logic import (DIFFICULTY_CONFIG, generate_full_grid,
                    grid_to_str, mask_grid, mask_grid_unique)
from .ui import SudokuDialog

__all__ = [
	"SudokuDialog",
	"DIFFICULTY_CONFIG",
	"generate_full_grid",
	"mask_grid",
	"mask_grid_unique",
	"grid_to_str",
]
