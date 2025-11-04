from __future__ import annotations

from typing import List, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (QDialog, QGridLayout, QGroupBox, QHBoxLayout,
                               QLabel, QLineEdit, QMessageBox, QPushButton,
                               QVBoxLayout, QWidget)

# 简单内置数独题目（0 表示空格）
_PUZZLES: List[str] = [
    # easy
    "530070000600195000098000060800060003400803001700020006060000280000419005000080079",
    # medium
    "000260701680070090190004500820100040004602900050003028009300074040050036703018000",
]


def _chunks(s: str, n: int) -> List[str]:
    return [s[i : i + n] for i in range(0, len(s), n)]


class SudokuDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("数独（9×9）")
        self.setFixedSize(520, 640)
        self._puzzle_index = 0
        self._cells: List[List[QLineEdit]] = []
        self._givens: List[List[bool]] = []
        self._build_ui()
        self._load_puzzle(_PUZZLES[self._puzzle_index])

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        gb = QGroupBox("填入 1-9，使每行、每列、每个 3×3 宫内不重复")
        grid = QGridLayout()
        grid.setSpacing(2)

        # 创建 9x9 输入格
        for r in range(9):
            row_cells: List[QLineEdit] = []
            for c in range(9):
                e = QLineEdit()
                e.setMaxLength(1)
                e.setAlignment(Qt.AlignmentFlag.AlignCenter)
                e.setValidator(QIntValidator(1, 9, self))
                e.setFixedSize(42, 42)
                # 网格线风格（粗细宫格）
                top = 3 if r % 3 == 0 else 1
                left = 3 if c % 3 == 0 else 1
                right = 3 if c == 8 else (3 if (c + 1) % 3 == 0 else 1)
                bottom = 3 if r == 8 else (3 if (r + 1) % 3 == 0 else 1)
                e.setStyleSheet(
                    f"border-top:{top}px solid #888;"
                    f"border-left:{left}px solid #888;"
                    f"border-right:{right}px solid #888;"
                    f"border-bottom:{bottom}px solid #888;"
                    "font-size:18px;"
                )
                grid.addWidget(e, r, c)
                row_cells.append(e)
            self._cells.append(row_cells)
        gb.setLayout(grid)
        root.addWidget(gb)

        self._hint = QLabel("")
        self._hint.setStyleSheet("color:#666")
        root.addWidget(self._hint)

        ctrl = QHBoxLayout()
        btn_check = QPushButton("检验")
        btn_check.clicked.connect(self._on_check)
        btn_reset = QPushButton("重置本题")
        btn_reset.clicked.connect(self._on_reset)
        btn_new = QPushButton("新题")
        btn_new.clicked.connect(self._on_new)
        ctrl.addWidget(btn_check)
        ctrl.addWidget(btn_reset)
        ctrl.addWidget(btn_new)
        root.addLayout(ctrl)

    def _load_puzzle(self, s: str) -> None:
        self._givens = [[False] * 9 for _ in range(9)]
        rows = _chunks(s, 9)
        for r, row in enumerate(rows):
            for c, ch in enumerate(row):
                cell = self._cells[r][c]
                if ch in {"0", "."}:
                    cell.setText("")
                    cell.setReadOnly(False)
                    cell.setStyleSheet(cell.styleSheet() + "color:#1976d2;")
                    self._givens[r][c] = False
                else:
                    cell.setText(ch)
                    cell.setReadOnly(True)
                    cell.setStyleSheet(cell.styleSheet() + "background:#f3f3f3;color:#333;")
                    self._givens[r][c] = True
        self._hint.setText("")

    def _collect(self) -> List[List[int]]:
        grid: List[List[int]] = [[0] * 9 for _ in range(9)]
        for r in range(9):
            for c in range(9):
                t = self._cells[r][c].text().strip()
                grid[r][c] = int(t) if t.isdigit() else 0
        return grid

    def _valid(self, grid: List[List[int]]) -> Tuple[bool, str]:
        # 检查每行
        for r in range(9):
            seen = set()
            for c in range(9):
                v = grid[r][c]
                if v == 0:
                    return False, f"第 {r+1} 行有空格"
                if v in seen:
                    return False, f"第 {r+1} 行有重复"
                seen.add(v)
        # 列
        for c in range(9):
            seen = set()
            for r in range(9):
                v = grid[r][c]
                if v in seen:
                    return False, f"第 {c+1} 列有重复"
                seen.add(v)
        # 宫
        for br in range(0, 9, 3):
            for bc in range(0, 9, 3):
                seen = set()
                for r in range(br, br + 3):
                    for c in range(bc, bc + 3):
                        v = grid[r][c]
                        if v in seen:
                            return False, "某个 3×3 宫有重复"
                        seen.add(v)
        return True, "OK"

    def _on_check(self) -> None:
        grid = self._collect()
        ok, msg = self._valid(grid)
        if ok:
            self._hint.setStyleSheet("color:#2e7d32")
            self._hint.setText("恭喜完成！")
            QMessageBox.information(self, "完成", "恭喜你完成了这道数独！")
        else:
            self._hint.setStyleSheet("color:#c62828")
            self._hint.setText(msg)

    def _on_reset(self) -> None:
        # 清空非 givens
        for r in range(9):
            for c in range(9):
                if not self._givens[r][c]:
                    self._cells[r][c].setText("")
        self._hint.setText("")

    def _on_new(self) -> None:
        self._puzzle_index = (self._puzzle_index + 1) % len(_PUZZLES)
        self._load_puzzle(_PUZZLES[self._puzzle_index])
