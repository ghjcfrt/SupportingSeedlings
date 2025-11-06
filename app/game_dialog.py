""" 潜能开发小游戏对话框（UI）。"""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (QDialog, QLabel, QPushButton, QVBoxLayout,
                               QWidget)

from games import ArithmeticDialog, PictorialEquationDialog, SudokuDialog


class GameDialog(QDialog):
    """ 潜能开发小游戏对话框（UI）。"""

    def __init__(self, parent: QWidget | None = None, *, recent_object: Optional[str] = None, tts=None) -> None:
        """ 初始化小游戏对话框 """
        super().__init__(parent)
        self.setWindowTitle("潜能开发小游戏")
        self.setFixedSize(360, 260)
        self._tts = tts
        self._recent = recent_object
        self._build_ui()

    def _build_ui(self) -> None:
        """ 构建对话框 UI """
        root = QVBoxLayout(self)
        title = QLabel("选择一个小游戏开始：")
        title.setWordWrap(True)
        root.addWidget(title)

        btn1 = QPushButton("两位数口算（+ − × ÷）")
        btn1.clicked.connect(self._open_arithmetic)
        root.addWidget(btn1)

        btn2 = QPushButton("图文算式（表情计数）")
        btn2.clicked.connect(self._open_pictorial)
        root.addWidget(btn2)

        btn3 = QPushButton("数独（9×9）")
        btn3.clicked.connect(self._open_sudoku)
        root.addWidget(btn3)

        root.addStretch(1)

    def _open_arithmetic(self) -> None:
        """ 打开两位数口算对话框 """
        dlg = ArithmeticDialog(self, tts=self._tts)
        dlg.exec()

    def _open_pictorial(self) -> None:
        """ 打开图文算式对话框 """
        dlg = PictorialEquationDialog(self, tts=self._tts)
        dlg.exec()

    def _open_sudoku(self) -> None:
        """ 打开数独对话框 """
        dlg = SudokuDialog(self)
        dlg.exec()
