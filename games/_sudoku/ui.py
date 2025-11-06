from __future__ import annotations

import random
from typing import List, Tuple

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QColor, QIntValidator, QPainter, QPen
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox,
                               QDialog, QDoubleSpinBox, QFrame, QGroupBox,
                               QHBoxLayout, QLabel, QMessageBox, QPushButton,
                               QSizePolicy, QStyledItemDelegate, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from .logic import (DIFFICULTY_CONFIG, chunks, generate_full_grid, grid_to_str,
                    mask_grid, mask_grid_unique)

# 颜色与字体配置（UI 专用）
_COLOR_GIVEN = QColor("#111111")
_COLOR_USER = QColor("#1976d2")
_FONT_POINT_SIZE = 18
_FONT_BOLD = True
_CELL_SIZE = 44
_BOARD_SAFE_PADDING = 4


class SudokuDelegate(QStyledItemDelegate):
    """ 数独单元格委托（UI）。"""
    def createEditor(self, parent, option, index):
        """ 创建单元格编辑器。"""
        from PySide6.QtWidgets import QLineEdit

        editor = QLineEdit(parent)
        editor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        editor.setMaxLength(1)
        editor.setValidator(QIntValidator(1, 9, parent))
        f = editor.font()
        f.setPointSize(_FONT_POINT_SIZE)
        f.setBold(_FONT_BOLD)
        editor.setFont(f)
        editor.setStyleSheet("QLineEdit{ background: #FFFFFF; color: #1976d2; }")
        editor.installEventFilter(self)
        return editor

    def setEditorData(self, editor, index):
        """ 设置编辑器数据。"""
        text = index.data() or ""
        editor.setText(str(text))

    def setModelData(self, editor, model, index):
        """ 从编辑器获取数据并设置到模型。"""
        t = editor.text().strip()
        if t.isdigit() and 1 <= int(t) <= 9:
            model.setData(index, t)
        else:
            model.setData(index, "")

    def paint(self, painter: QPainter, option, index):
        """ 绘制单元格内容与边框。"""
        view = option.widget
        has_focus_outline = False
        if view is not None:
            try:
                has_focus_outline = view.hasFocus() and (view.currentIndex() == index)
            except Exception:
                has_focus_outline = False

        rect = option.rect
        painter.save()
        painter.fillRect(rect, QColor("#FFFFFF"))
        painter.restore()

        row = index.row()
        col = index.column()

        if has_focus_outline:
            painter.save()
            painter.fillRect(rect.adjusted(1, 1, -1, -1), QColor(240, 248, 255, 90))
            painter.restore()

        text = (index.data() or "").strip()
        flags = index.flags()
        is_editable = bool(flags & Qt.ItemFlag.ItemIsEditable)
        if text:
            color = _COLOR_USER if is_editable else _COLOR_GIVEN
            painter.save()
            painter.setPen(color)
            f = painter.font()
            f.setPointSize(_FONT_POINT_SIZE)
            f.setBold(_FONT_BOLD)
            painter.setFont(f)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(text))
            painter.restore()

        top_w = 3 if (row % 3 == 0 and row != 0) else 1
        left_w = 3 if (col % 3 == 0 and col != 0) else 1
        right_w = 3 if (((col + 1) % 3 == 0) and col != 8) else 1
        bottom_w = 3 if (((row + 1) % 3 == 0) and row != 8) else 1

        color = QColor("#888")

        painter.save()
        pen = QPen(color)
        pen.setWidth(top_w)
        painter.setPen(pen)
        painter.drawLine(rect.topLeft(), rect.topRight())
        pen.setWidth(left_w)
        painter.setPen(pen)
        painter.drawLine(rect.topLeft(), rect.bottomLeft())
        pen.setWidth(right_w)
        painter.setPen(pen)
        painter.drawLine(rect.topRight(), rect.bottomRight())
        pen.setWidth(bottom_w)
        painter.setPen(pen)
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        painter.restore()

        if has_focus_outline:
            painter.save()
            pen = QPen(QColor("#4facfe"))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.drawRect(option.rect.adjusted(1, 1, -1, -1))
            painter.restore()

    def eventFilter(self, obj, event):
        """ 处理键盘事件，实现方向键移动单元格。"""
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Left, Qt.Key.Key_Right):
                view = self.parent()
                try:
                    self.commitData.emit(obj)
                    self.closeEditor.emit(obj)
                    from PySide6.QtWidgets import QTableWidget as _QTableWidget
                    if isinstance(view, _QTableWidget):
                        r = view.currentRow()
                        c = view.currentColumn()
                        if key == Qt.Key.Key_Up:
                            r = max(0, r - 1)
                        elif key == Qt.Key.Key_Down:
                            r = min(8, r + 1)
                        elif key == Qt.Key.Key_Left:
                            c = max(0, c - 1)
                        elif key == Qt.Key.Key_Right:
                            c = min(8, c + 1)
                        view.setCurrentCell(r, c)
                        view.setFocus()
                    return True
                except Exception:
                    return False
        return super().eventFilter(obj, event)


class SudokuDialog(QDialog):
    """数独（9×9）对话框（UI）。"""
    def __init__(self, parent: QWidget | None = None) -> None:
        """ 初始化对话框。"""
        super().__init__(parent)
        self.setWindowTitle("数独（9×9）")
        self.setMinimumSize(520, 640)
        self._maintain_aspect = False
        self._adaptive_grid = True
        self._show_size_info = False
        self._in_aspect_resize = False
        self._givens: List[List[bool]] = []
        self._build_ui()
        self._load_puzzle(self._new_random_puzzle())
        QTimer.singleShot(0, self._update_grid_size)
        w = max(1, self.width())
        h = max(1, self.height())
        self._aspect_ratio = w / h

    def _build_ui(self) -> None:
        """ 构建用户界面。"""
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        gb = QGroupBox("填入 1-9，使每行、每列、每个 3×3 宫内不重复")
        gb.setStyleSheet(
            """
        QGroupBox { color: white; font-weight: 600; }
        QGroupBox::title { subcontrol-position: top center; }
        """
        )
        box_layout = QVBoxLayout()
        box_layout.setContentsMargins(8, 8, 8, 8)
        box_layout.setSpacing(4)
        self._box_layout = box_layout

        self._table = QTableWidget(9, 9)
        self._table.setFrameShape(QFrame.Shape.NoFrame)
        self._table.setItemDelegate(SudokuDelegate(self._table))
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self._table.setAlternatingRowColors(False)
        self._table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.SelectedClicked
            | QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.AnyKeyPressed
        )
        self._table.setShowGrid(False)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setVisible(False)
        self._table.setStyleSheet(
            """
        QAbstractScrollArea { background: transparent; }
        QTableWidget { background: transparent; }
        QTableView { background: transparent; }
        QTableWidget::viewport {
            background: transparent;
            border: 2px solid #FFFFFF;
            border-radius: 8px;
        }
        QTableView::viewport { background: transparent; }
        QTableWidget::item:selected { background: #FFFFFF; }
        """
        )
        for i in range(9):
            self._table.setColumnWidth(i, _CELL_SIZE)
            self._table.setRowHeight(i, _CELL_SIZE)
        self._table.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._apply_table_fixed_size()
        gb.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        box_layout.addWidget(self._table, 0, Qt.AlignmentFlag.AlignCenter)
        gb.setLayout(box_layout)
        self._gb = gb
        root.addWidget(gb, 1)

        self._hint = QLabel("")
        self._hint.setStyleSheet("color:#666")
        root.addWidget(self._hint)

        ctrl = QHBoxLayout()
        ctrl.setAlignment(Qt.AlignmentFlag.AlignLeft)
        ctrl.addWidget(QLabel("难度："))
        self._difficulty = QComboBox()
        self._difficulty.addItems(["随机", "简单", "中等", "困难", "多解", "自定义"])
        self._difficulty.setCurrentText("中等")
        ctrl.addWidget(self._difficulty)

        btn_check = QPushButton("检验")
        btn_check.clicked.connect(self._on_check)
        btn_reset = QPushButton("重置本题")
        btn_reset.clicked.connect(self._on_reset)
        btn_new = QPushButton("新题")
        btn_new.clicked.connect(self._on_new)
        ctrl.addWidget(btn_check)
        ctrl.addWidget(btn_reset)
        ctrl.addWidget(btn_new)

        ctrl_box = QWidget()
        ctrl_box.setLayout(ctrl)
        ctrl_box.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self._ctrl_box = ctrl_box
        root.addWidget(ctrl_box, 0, Qt.AlignmentFlag.AlignLeft)

        custom_layout = QHBoxLayout()
        custom_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        custom_layout.addWidget(QLabel("挖空比例："))
        self._spin_mask = QDoubleSpinBox()
        self._spin_mask.setRange(0.0, 0.95)
        self._spin_mask.setSingleStep(0.01)
        self._spin_mask.setDecimals(2)
        self._spin_mask.setValue(0.60)
        custom_layout.addWidget(self._spin_mask)

        self._chk_unique = QCheckBox("保证唯一解")
        self._chk_unique.setChecked(True)
        custom_layout.addWidget(self._chk_unique)

        self._custom_box = QWidget()
        self._custom_box.setLayout(custom_layout)
        self._custom_box.setVisible(False)
        self._custom_box.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        root.addWidget(self._custom_box, 0, Qt.AlignmentFlag.AlignLeft)

        self._difficulty.currentTextChanged.connect(self._on_difficulty_changed)

    def _load_puzzle(self, s: str) -> None:
        """ 加载数独盘面字符串到表格。"""
        self._loading = True
        try:
            self._givens = [[False] * 9 for _ in range(9)]
            self._table.clearContents()
            rows = chunks(s, 9)
            first_editable: tuple[int, int] | None = None
            for r, row in enumerate(rows):
                for c, ch in enumerate(row):
                    item = QTableWidgetItem()
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    item.setBackground(QColor("#FFFFFF"))
                    if ch in {"0", "."}:
                        item.setText("")
                        item.setFlags(
                            Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsEditable
                        )
                        item.setForeground(_COLOR_GIVEN)
                        f = self.font()
                        f.setPointSize(_FONT_POINT_SIZE)
                        f.setBold(_FONT_BOLD)
                        item.setFont(f)
                        self._givens[r][c] = False
                        if first_editable is None:
                            first_editable = (r, c)
                    else:
                        item.setText(ch)
                        item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                        f = self.font()
                        f.setPointSize(_FONT_POINT_SIZE)
                        f.setBold(_FONT_BOLD)
                        item.setFont(f)
                        item.setForeground(_COLOR_GIVEN)
                        self._givens[r][c] = True
                    self._table.setItem(r, c, item)
            self._hint.setText("")
            if first_editable is not None:
                r0, c0 = first_editable
                self._table.setCurrentCell(r0, c0)
                self._table.setFocus()
        finally:
            self._loading = False
        if not hasattr(self, "_color_signal_connected"):
            self._table.itemChanged.connect(self._on_item_changed)
            self._color_signal_connected = True

    def _pick_difficulty(self) -> tuple[str, dict]:
        """ 选择难度配置。 """
        combo = getattr(self, "_difficulty", None)
        label = combo.currentText() if combo is not None else "中等"
        if label == "随机":
            base = random.choice(list(DIFFICULTY_CONFIG.keys()))
            return base, DIFFICULTY_CONFIG[base]
        if label == "自定义":
            mask = float(self._spin_mask.value()) if hasattr(self, "_spin_mask") else 0.6
            rounds = 6
            unique = bool(self._chk_unique.isChecked()) if hasattr(self, "_chk_unique") else True
            cfg = {"mask": mask, "maxSolutions": (1 if unique else 999), "rounds": rounds}
            return label, cfg
        base = label if label in DIFFICULTY_CONFIG else "中等"
        return base, DIFFICULTY_CONFIG[base]

    def _new_random_puzzle(self) -> str:
        """ 生成新的随机数独盘面字符串。"""
        base, cfg = self._pick_difficulty()
        mask_rate = float(cfg.get("mask", 0.6))
        max_solutions = int(cfg.get("maxSolutions", 1))
        rounds = int(cfg.get("rounds", 6))
        full = generate_full_grid()
        if max_solutions <= 1:
            masked = mask_grid_unique(full, mask_rate, max_rounds=rounds)
        else:
            masked = mask_grid(full, mask_rate)
        return grid_to_str(masked)

    def _on_difficulty_changed(self, text: str) -> None:
        """ 难度更改时的处理。"""
        if hasattr(self, "_custom_box"):
            self._custom_box.setVisible(text == "自定义")
        QTimer.singleShot(0, self._update_grid_size)

    def _update_grid_size(self) -> None:
        """ 更新数独表格大小以适应窗口。"""
        table = getattr(self, "_table", None)
        gb = getattr(self, "_gb", None)
        if table is None or gb is None:
            return
        if not getattr(self, "_adaptive_grid", False):
            self._apply_table_fixed_size()
            self._update_size_info()
            return
        cr = gb.contentsRect()
        try:
            m = self._box_layout.contentsMargins()
            ml, mt, mr, mb = m.left(), m.top(), m.right(), m.bottom()
        except Exception:
            ml = mt = mr = mb = 0
        avail_w = cr.width() - ml - mr - _BOARD_SAFE_PADDING * 2
        avail_h = cr.height() - mt - mb - _BOARD_SAFE_PADDING * 2
        cell = min(avail_w // 9, avail_h // 9)
        cell = max(20, min(256, int(cell)))
        if cell <= 0:
            return
        for c in range(9):
            table.setColumnWidth(c, cell)
        for r in range(9):
            table.setRowHeight(r, cell)
        table.setViewportMargins(0, 0, 0, 0)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._apply_table_fixed_size()
        self._update_size_info()

    def _update_size_info(self) -> None:
        """ 更新窗口与表格大小信息显示。"""
        try:
            if not getattr(self, "_show_size_info", False):
                return
            w, h = max(1, self.width()), max(1, self.height())
            gb = getattr(self, "_gb", None)
            table = getattr(self, "_table", None)
            crw = crh = 0
            cell = 0
            grid_w = grid_h = 0
            view_w = view_h = 0
            if gb is not None:
                cr = gb.contentsRect()
                crw, crh = max(0, cr.width()), max(0, cr.height())
            if table is not None:
                try:
                    cell = int(table.columnWidth(0))
                except Exception:
                    cell = 0
                grid_w = cell * 9
                grid_h = cell * 9
                try:
                    vp = table.viewport()
                    view_w, view_h = vp.width(), vp.height()
                except Exception:
                    view_w = view_h = 0
            info_text = (
                f"窗口: {w}×{h} | 可用区: {crw}×{crh} | 视口: {view_w}×{view_h} | 单元格: {cell}px | 棋盘: {grid_w}×{grid_h}"
            )
            lab = getattr(self, "_size_info", None)
            if lab is not None:
                lab.setText(info_text)
        except Exception:
            pass

    def set_size_info_visible(self, visible: bool) -> None:
        """ 设置是否显示大小信息。"""
        self._show_size_info = bool(visible)
        lab = getattr(self, "_size_info", None)
        root_layout = self.layout()
        if self._show_size_info:
            if lab is None:
                from PySide6.QtWidgets import QLabel as _QLabel
                lab = _QLabel("")
                lab.setStyleSheet("color:#999; font-family: Consolas, 'Courier New', monospace;")
                self._size_info = lab
                try:
                    if root_layout is not None:
                        root_layout.addWidget(lab)
                except Exception:
                    pass
            lab.setVisible(True)
            self._update_size_info()
        else:
            if lab is not None:
                lab.setVisible(False)

    def _apply_table_fixed_size(self) -> None:
        """ 应用表格固定大小。"""
        table = getattr(self, "_table", None)
        if table is None:
            return
        try:
            cols = min(9, table.columnCount())
            rows = min(9, table.rowCount())
            w = sum(table.columnWidth(i) for i in range(cols))
            h = sum(table.rowHeight(i) for i in range(rows))
            table.setFixedSize(max(0, w), max(0, h))
        except Exception:
            pass

    def resizeEvent(self, e):
        """ 处理窗口调整大小事件，保持宽高比（如启用）。"""
        if getattr(self, "_maintain_aspect", False) and not getattr(self, "_in_aspect_resize", False):
            new_size = e.size()
            old_size = e.oldSize()
            w, h = new_size.width(), new_size.height()
            ratio = getattr(self, "_aspect_ratio", None)
            if not ratio or ratio <= 0:
                ratio = max(1, w) / max(1, h)
                self._aspect_ratio = ratio
            dw = abs(w - (old_size.width() if old_size.isValid() else w))
            dh = abs(h - (old_size.height() if old_size.isValid() else h))
            if dw >= dh:
                h_target = int(round(w / ratio))
                if h_target != h:
                    self._in_aspect_resize = True
                    self.resize(w, h_target)
                    self._in_aspect_resize = False
                    return
            else:
                w_target = int(round(h * ratio))
                if w_target != w:
                    self._in_aspect_resize = True
                    self.resize(w_target, h)
                    self._in_aspect_resize = False
                    return
        super().resizeEvent(e)
        self._update_grid_size()

    def _collect(self) -> List[List[int]]:
        """ 收集当前表格中的数独数据为二维列表。"""
        grid: List[List[int]] = [[0] * 9 for _ in range(9)]
        for r in range(9):
            for c in range(9):
                item = self._table.item(r, c)
                t = item.text().strip() if item else ""
                grid[r][c] = int(t) if t.isdigit() else 0
        return grid

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        """ 单元格内容更改时的处理。"""
        if getattr(self, "_loading", False):
            return
        t = (item.text() or "").strip()
        item.setForeground(_COLOR_USER if t else _COLOR_GIVEN)
        item.setBackground(QColor("#FFFFFF"))
        f = item.font()
        f.setPointSize(_FONT_POINT_SIZE)
        f.setBold(_FONT_BOLD)
        item.setFont(f)

    def _valid(self, grid: List[List[int]]) -> Tuple[bool, str]:
        """ 验证数独盘面是否合法完整。"""
        for r in range(9):
            seen = set()
            for c in range(9):
                v = grid[r][c]
                if v == 0:
                    return False, f"第 {r+1} 行有空格"
                if v in seen:
                    return False, f"第 {r+1} 行有重复"
                seen.add(v)
        for c in range(9):
            seen = set()
            for r in range(9):
                v = grid[r][c]
                if v in seen:
                    return False, f"第 {c+1} 列有重复"
                seen.add(v)
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
        """ 检验当前盘面是否合法完整。"""
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
        """ 重置当前题目。"""
        for r in range(9):
            for c in range(9):
                if not self._givens[r][c]:
                    item = self._table.item(r, c)
                    if item:
                        item.setText("")
                        item.setForeground(_COLOR_GIVEN)
                        item.setBackground(QColor("#FFFFFF"))
                        f = item.font()
                        f.setPointSize(_FONT_POINT_SIZE)
                        f.setBold(_FONT_BOLD)
                        item.setFont(f)
        self._hint.setText("")

    def _on_new(self) -> None:
        """ 生成新题。"""
        self._load_puzzle(self._new_random_puzzle())
        self._hint.setText("")
