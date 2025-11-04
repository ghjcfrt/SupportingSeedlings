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


def _chunks(s: str, n: int) -> List[str]:
    return [s[i : i + n] for i in range(0, len(s), n)]


# --- 随机生成完整解 + 按比例挖空（不保证唯一解） ---
def _is_valid_value(grid: List[List[int]], r: int, c: int, v: int) -> bool:
    # 行
    for cc in range(9):
        if grid[r][cc] == v:
            return False
    # 列
    for rr in range(9):
        if grid[rr][c] == v:
            return False
    # 宫
    br, bc = (r // 3) * 3, (c // 3) * 3
    for i in range(3):
        for j in range(3):
            if grid[br + i][bc + j] == v:
                return False
    return True


def _find_mrv_cell(grid: List[List[int]]) -> Tuple[int, int, List[int]] | None:
    """从空格里选候选数最少的格子（MRV），返回 (r, c, candidates)。"""
    best: Tuple[int, int, List[int]] | None = None
    best_len = 10
    for r in range(9):
        for c in range(9):
            if grid[r][c] == 0:
                candidates = [v for v in range(1, 10) if _is_valid_value(grid, r, c, v)]
                if not candidates:
                    return (r, c, [])  # 无候选，直接表明死路
                if len(candidates) < best_len:
                    best = (r, c, candidates)
                    best_len = len(candidates)
                    if best_len == 1:
                        # 已经是最优
                        return best
    return best


def _generate_full_grid(max_retries: int = 3) -> List[List[int]]:
    """随机生成一个完整 9x9 解。使用 MRV + 随机值的回溯。"""
    for _ in range(max_retries):
        grid = [[0] * 9 for _ in range(9)]

        def dfs() -> bool:
            pick = _find_mrv_cell(grid)
            if pick is None:
                return True  # 无空格，完成
            r, c, candidates = pick
            if not candidates:
                return False
            random.shuffle(candidates)
            for v in candidates:
                if _is_valid_value(grid, r, c, v):
                    grid[r][c] = v
                    if dfs():
                        return True
                    grid[r][c] = 0
            return False

        if dfs():
            return grid
    # 若多次失败，抛异常
    raise RuntimeError("Failed to generate a full Sudoku grid after retries")


def _mask_grid(grid: List[List[int]], mask_rate: float) -> List[List[int]]:
    """按比例挖空，返回新网格（不保证唯一解）。"""
    k = max(0, min(81, int(round(81 * mask_rate))))
    positions = [(r, c) for r in range(9) for c in range(9)]
    random.shuffle(positions)
    g2 = [row[:] for row in grid]
    for i in range(k):
        r, c = positions[i]
        g2[r][c] = 0
    return g2


def _grid_to_str(grid: List[List[int]]) -> str:
    return "".join("".join(str(v) for v in row) for row in grid)


def _count_solutions(grid: List[List[int]], limit: int = 2) -> int:
    """统计解的数量，达到 limit 即提前停止。grid 会在过程中被回溯写入，但会恢复。"""
    def find_empty() -> Tuple[int, int] | None:
        for rr in range(9):
            for cc in range(9):
                if grid[rr][cc] == 0:
                    return rr, cc
        return None

    cnt = 0

    def dfs():
        nonlocal cnt
        if cnt >= limit:
            return
        pos = find_empty()
        if pos is None:
            cnt += 1
            return
        r, c = pos
        # 使用自然顺序 1..9（更快），无需随机
        for v in range(1, 10):
            if _is_valid_value(grid, r, c, v):
                grid[r][c] = v
                dfs()
                if cnt >= limit:
                    grid[r][c] = 0
                    return
                grid[r][c] = 0

    dfs()
    return cnt


def _mask_grid_unique(grid: List[List[int]], mask_rate: float, max_rounds: int = 6) -> List[List[int]]:
    """按比例挖空并保证唯一解；若一次遍历未达到目标，将重新打乱顺序继续尝试若干轮。

    策略：随机顺序尝试置零，置零后用解计数器统计解数（上限2），仅当解数仍为1时保留该置零；
    若一轮没有任何进展，则重新洗牌再尝试，最多尝试若干轮以避免长时间卡死。
    """
    target = max(0, min(81, int(round(81 * mask_rate))))
    g2 = [row[:] for row in grid]
    zeros = 0
    rounds = 0

    while zeros < target and rounds < max_rounds:
        # 只从当前非零格中尝试挖空
        positions = [(r, c) for r in range(9) for c in range(9) if g2[r][c] != 0]
        random.shuffle(positions)
        progressed = False
        for r, c in positions:
            if zeros >= target:
                break
            tmp = g2[r][c]
            g2[r][c] = 0
            # 复制后计数解（到2即停）
            copy_grid = [row[:] for row in g2]
            if _count_solutions(copy_grid, limit=2) == 1:
                zeros += 1
                progressed = True
            else:
                g2[r][c] = tmp
        if not progressed:
            rounds += 1
        else:
            # 有进展则重置轮次计数，提高达成目标的机会
            rounds = 0
    return g2


# 两类固定配色（高对比度）
_COLOR_GIVEN = QColor("#111111")   # 系统给定数字：高对比度深色
_COLOR_USER = QColor("#1976d2")    # 用户填写数字：高对比度蓝色

# 统一字体设置：加粗、加大，用户与系统相同大小
_FONT_POINT_SIZE = 18
_FONT_BOLD = True

# 单元格像素尺寸（宽高一致）。若觉得格子偏大/偏小可调整此值。
_CELL_SIZE = 44

# 棋盘与可用区边缘的安全留白（像素），避免外框与容器边界重合
_BOARD_SAFE_PADDING = 4

# 难度配置：mask 挖空比例，maxSolutions=1 表示唯一解；>1 表示允许多解
_DIFFICULTY_CONFIG = {
    "简单": {"mask": 0.50, "maxSolutions": 1},
    "中等": {"mask": 0.60, "maxSolutions": 1},
    "困难": {"mask": 0.70, "maxSolutions": 1},
    "多解": {"mask": 0.65, "maxSolutions": 999},  # 不限制唯一性
}


class SudokuDelegate(QStyledItemDelegate):
    """自定义委托：
    - 仅允许输入 1..9（单字符）
    - 在单元格绘制后叠加 3×3 粗边框
    """

    def createEditor(self, parent, option, index):  # type: ignore[override]
        from PySide6.QtWidgets import QLineEdit

        editor = QLineEdit(parent)
        editor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        editor.setMaxLength(1)
        editor.setValidator(QIntValidator(1, 9, parent))
        f = editor.font()
        f.setPointSize(_FONT_POINT_SIZE)
        f.setBold(_FONT_BOLD)
        editor.setFont(f)
        # 编辑态：强制白底与用户蓝色前景，避免“变黑”与可读性问题
        editor.setStyleSheet("QLineEdit{ background: #FFFFFF; color: #1976d2; }")
        # 捕获方向键，离开编辑并移动到相邻格
        editor.installEventFilter(self)
        return editor

    def setEditorData(self, editor, index):  # type: ignore[override]
        text = index.data() or ""
        editor.setText(str(text))

    def setModelData(self, editor, model, index):  # type: ignore[override]
        t = editor.text().strip()
        if t.isdigit() and 1 <= int(t) <= 9:
            model.setData(index, t)
        else:
            model.setData(index, "")

    def paint(self, painter: QPainter, option, index):  # type: ignore[override]
        # 判定是否为当前聚焦单元（模拟 CSS :focus）
        view = option.widget
        has_focus_outline = False
        if view is not None:
            try:
                has_focus_outline = view.hasFocus() and (view.currentIndex() == index)
            except Exception:
                has_focus_outline = False

        rect = option.rect
        # 棋盘白底（表尾除外），避免系统选中底色与文字高亮色导致“看不见字”
        painter.save()
        painter.fillRect(rect, QColor("#FFFFFF"))
        painter.restore()

        # 行/列索引
        row = index.row()
        col = index.column()

        # 不再有表尾（10×10 扩展已取消）

        # 若聚焦则叠加浅蓝底（更低不透明度，保证文字对比度）
        if has_focus_outline:
            painter.save()
            painter.fillRect(rect.adjusted(1, 1, -1, -1), QColor(240, 248, 255, 90))
            painter.restore()

        # 绘制文本：根据是否可编辑（givens 不可编辑）决定颜色；用户已填用蓝色
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

        # 再叠加画 3×3 粗边框（仅内部粗线；外层圆角边框由 viewport 呈现）
        # 计算需要加粗的边（不在最外层绘制）
        top_w = 3 if (row % 3 == 0 and row != 0) else 1
        left_w = 3 if (col % 3 == 0 and col != 0) else 1
        right_w = 3 if (((col + 1) % 3 == 0) and col != 8) else 1
        bottom_w = 3 if (((row + 1) % 3 == 0) and row != 8) else 1

        color = QColor("#888")

        painter.save()
        # Top
        pen = QPen(color)
        pen.setWidth(top_w)
        painter.setPen(pen)
        painter.drawLine(rect.topLeft(), rect.topRight())
        # Left
        pen.setWidth(left_w)
        painter.setPen(pen)
        painter.drawLine(rect.topLeft(), rect.bottomLeft())
        # Right
        pen.setWidth(right_w)
        painter.setPen(pen)
        painter.drawLine(rect.topRight(), rect.bottomRight())
        # Bottom
        pen.setWidth(bottom_w)
        painter.setPen(pen)
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        painter.restore()

        # 最后叠加“淡蓝色外框”（置于最上层），模拟网页的 :focus outline
        if has_focus_outline:
            painter.save()
            pen = QPen(QColor("#4facfe"))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.drawRect(option.rect.adjusted(1, 1, -1, -1))
            painter.restore()

    def eventFilter(self, obj, event):  # type: ignore[override]
        # 在编辑器内拦截方向键：提交/关闭编辑器并移动到相邻单元格（避免只移动光标）
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Left, Qt.Key.Key_Right):
                view = self.parent()
                try:
                    # 提交当前编辑内容并关闭编辑器
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
                    return True  # 已处理
                except Exception:
                    return False
        return super().eventFilter(obj, event)


class SudokuDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("数独（9×9）")
        # 允许窗口缩放，自适应调整数独大小
        self.setMinimumSize(520, 640)
        # 维护窗口纵横比（基于初始尺寸），可按需关闭
        # 暂时取消横纵比约束（如需恢复，将其改回 True）
        self._maintain_aspect = False
        # 开启棋盘自适应尺寸，尽量填满可用区，减少空白
        self._adaptive_grid = True
        # 关闭调试用尺寸信息显示
        self._show_size_info = False
        self._in_aspect_resize = False
        self._givens: List[List[bool]] = []
        self._build_ui()
        # 初次随机生成一题
        self._load_puzzle(self._new_random_puzzle())
        # 首次展示后刷新尺寸信息（不自适应时仅更新文字）
        QTimer.singleShot(0, self._update_grid_size)
        # 记录初始窗口宽高比
        w = max(1, self.width())
        h = max(1, self.height())
        self._aspect_ratio = w / h

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        gb = QGroupBox("填入 1-9，使每行、每列、每个 3×3 宫内不重复")
        gb.setStyleSheet("""
        QGroupBox {
            color: white;       /* 仅设置标题文字颜色 */
            font-weight: 600;
        }
        QGroupBox::title {
            subcontrol-position: top center; /* 标题居中 */
        }
        """)
        box_layout = QVBoxLayout()
        box_layout.setContentsMargins(8, 8, 8, 8)
        box_layout.setSpacing(4)
        # 记录布局，便于后续计算有效可用区域
        self._box_layout = box_layout

        # 构建 9×9 表格（“网页 81 输入样式”：隐藏表头，无外置表尾）
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
        # 网格线由委托自绘；关闭默认网格线
        self._table.setShowGrid(False)
        # 隐藏行列表头
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setVisible(False)
        self._table.setStyleSheet(
            """
QAbstractScrollArea { background: transparent; }
QTableWidget { background: transparent; }
QTableView { background: transparent; }
QTableWidget::viewport {
    background: transparent;
    border: 2px solid #FFFFFF;  /* 外轮廓白色描边 */
    border-radius: 8px;    /* 外轮廓圆角，仿网页输入样式 */
}
QTableView::viewport {
    background: transparent;
}
QTableWidget::item:selected { background: #FFFFFF; }
"""
        )
        # 隐藏表头，不再设置头标签/表尾

        for i in range(9):
            self._table.setColumnWidth(i, _CELL_SIZE)
            self._table.setRowHeight(i, _CELL_SIZE)
        # 固定棋盘尺寸并居中显示
        self._table.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._apply_table_fixed_size()

        # GroupBox 保持可扩展，棋盘固定尺寸
        gb.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        box_layout.addWidget(self._table, 0, Qt.AlignmentFlag.AlignCenter)
        gb.setLayout(box_layout)
        self._gb = gb
        root.addWidget(gb, 1)

        # 提示信息
        self._hint = QLabel("")
        self._hint.setStyleSheet("color:#666")
        root.addWidget(self._hint)

    # 调试尺寸信息已关闭，不创建对应标签

        # 难度选择 + 操作按钮（整体左对齐）
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

        # 自定义难度设置区域（默认隐藏，仅在选择“自定义”时显示；整体左对齐）
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

        # 当切换难度时，显示/隐藏自定义设置
        self._difficulty.currentTextChanged.connect(self._on_difficulty_changed)

    # 无表尾，无需初始化

    def _load_puzzle(self, s: str) -> None:
        # 防止 itemChanged 期间触发颜色逻辑
        self._loading = True
        try:
            self._givens = [[False] * 9 for _ in range(9)]
            self._table.clearContents()
            rows = _chunks(s, 9)
            first_editable: tuple[int, int] | None = None
            for r, row in enumerate(rows):
                for c, ch in enumerate(row):
                    item = QTableWidgetItem()
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    # 统一白底
                    item.setBackground(QColor("#FFFFFF"))
                    if ch in {"0", "."}:
                        item.setText("")
                        # 可编辑
                        item.setFlags(
                            Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsEditable
                        )
                        # 初始前景为深色，输入后会统一用用户颜色
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
                        # 只读给定数字（白底、粗体）
                        item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                        f = self.font()
                        f.setPointSize(_FONT_POINT_SIZE)
                        f.setBold(_FONT_BOLD)
                        item.setFont(f)
                        # 给定数字统一高对比度深色
                        item.setForeground(_COLOR_GIVEN)
                        self._givens[r][c] = True
                    self._table.setItem(r, c, item)
            self._hint.setText("")
            # 默认选中第一个可编辑格子并聚焦，方便方向键+直接输入
            if first_editable is not None:
                r0, c0 = first_editable
                self._table.setCurrentCell(r0, c0)
                self._table.setFocus()
            # 无表尾，不需要额外处理
        finally:
            self._loading = False
        # 信号连接（只连接一次）
        if not hasattr(self, "_color_signal_connected"):
            self._table.itemChanged.connect(self._on_item_changed)
            self._color_signal_connected = True

    # 不再需要表尾

    def _pick_difficulty(self) -> tuple[str, dict]:
        combo = getattr(self, "_difficulty", None)
        label = combo.currentText() if combo is not None else "中等"
        if label == "随机":
            base = random.choice(list(_DIFFICULTY_CONFIG.keys()))
            return base, _DIFFICULTY_CONFIG[base]
        if label == "自定义":
            # 读取自定义参数
            mask = float(self._spin_mask.value()) if hasattr(self, "_spin_mask") else 0.6
            rounds = 6
            unique = bool(self._chk_unique.isChecked()) if hasattr(self, "_chk_unique") else True
            cfg = {"mask": mask, "maxSolutions": (1 if unique else 999), "rounds": rounds}
            return label, cfg
        base = label if label in _DIFFICULTY_CONFIG else "中等"
        return base, _DIFFICULTY_CONFIG[base]

    def _new_random_puzzle(self) -> str:
        """生成一个完整解并按难度参数挖空，返回 81 位字符串（0 表示空）。"""
        base, cfg = self._pick_difficulty()
        mask_rate = float(cfg.get("mask", 0.6))
        max_solutions = int(cfg.get("maxSolutions", 1))
        rounds = int(cfg.get("rounds", 6))
        full = _generate_full_grid()
        if max_solutions <= 1:
            masked = _mask_grid_unique(full, mask_rate, max_rounds=rounds)
        else:
            # 允许多解：不做唯一性限制，直接随机挖空
            masked = _mask_grid(full, mask_rate)
        return _grid_to_str(masked)

    def _on_difficulty_changed(self, text: str) -> None:
        # 仅在选择“自定义”时显示参数面板
        if hasattr(self, "_custom_box"):
            self._custom_box.setVisible(text == "自定义")
        # 可见性变更会影响可用高度，需重新计算网格尺寸
        QTimer.singleShot(0, self._update_grid_size)

    def _update_grid_size(self) -> None:
        """根据 GroupBox 可用区域自适应单元格大小；若关闭自适应，仅更新尺寸信息。"""
        table = getattr(self, "_table", None)
        gb = getattr(self, "_gb", None)
        if table is None or gb is None:
            return

        # 若未启用自适应，则不调整棋盘尺寸，只更新显示信息
        if not getattr(self, "_adaptive_grid", False):
            # 固定棋盘尺寸并仅更新尺寸信息
            self._apply_table_fixed_size()
            self._update_size_info()
            return

    # GroupBox 的内容矩形（已扣掉标题和边框），布局内边距可能仍保留少量留白
        cr = gb.contentsRect()

        # 扣除布局内边距与安全留白，得到实际可用绘制区域
        try:
            m = self._box_layout.contentsMargins()  # type: ignore[attr-defined]
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

        # 无表尾

        # 不再额外设置视口边距
        table.setViewportMargins(0, 0, 0, 0)

        # 保持无滚动条
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # 固定棋盘尺寸并更新尺寸信息
        self._apply_table_fixed_size()
        self._update_size_info()

    # 不再需要同步表尾尺寸

    def _update_size_info(self) -> None:
        """更新调试尺寸信息（仅当显式开启时）。"""
        try:
            if not getattr(self, "_show_size_info", False):
                return
            # 计算窗口/可用区/视口/棋盘等尺寸
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
            # 输出到标签
            info_text = (
                f"窗口: {w}×{h} | 可用区: {crw}×{crh} | 视口: {view_w}×{view_h} | "
                f"单元格: {cell}px | 棋盘: {grid_w}×{grid_h}"
            )
            lab = getattr(self, "_size_info", None)
            if lab is not None:
                lab.setText(info_text)
        except Exception:
            # 尺寸信息非关键，不抛出
            pass

    def set_size_info_visible(self, visible: bool) -> None:
        """预留接口：启用/禁用调试用尺寸信息显示。

        可在运行时调用：dialog.set_size_info_visible(True/False)
        """
        self._show_size_info = bool(visible)
        lab = getattr(self, "_size_info", None)
        root_layout = self.layout()
        if self._show_size_info:
            # 需要显示：若标签不存在则创建并加入根布局
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
            # 需要隐藏：若标签存在则从布局隐藏即可
            if lab is not None:
                lab.setVisible(False)

    def _apply_table_fixed_size(self) -> None:
        """根据当前行列宽高，固定棋盘控件尺寸，便于在布局中水平居中。"""
        table = getattr(self, "_table", None)
        if table is None:
            return
        try:
            cols = min(9, table.columnCount())
            rows = min(9, table.rowCount())
            w = sum(table.columnWidth(i) for i in range(cols))
            h = sum(table.rowHeight(i) for i in range(rows))
            # 外轮廓边框绘制在 viewport 内部，不额外加尺寸
            table.setFixedSize(max(0, w), max(0, h))
        except Exception:
            pass

    def resizeEvent(self, e):  # type: ignore[override]
        # 保持窗口横纵比：根据用户主要拖动方向调整另一条边
        if getattr(self, "_maintain_aspect", False) and not getattr(self, "_in_aspect_resize", False):
            new_size = e.size()
            old_size = e.oldSize()
            w, h = new_size.width(), new_size.height()
            # 建立或校正比例
            ratio = getattr(self, "_aspect_ratio", None)
            if not ratio or ratio <= 0:
                ratio = max(1, w) / max(1, h)
                self._aspect_ratio = ratio
            # 判断用户主要改变的边
            dw = abs(w - (old_size.width() if old_size.isValid() else w))
            dh = abs(h - (old_size.height() if old_size.isValid() else h))
            # 调整另一维，避免递归
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
        grid: List[List[int]] = [[0] * 9 for _ in range(9)]
        for r in range(9):
            for c in range(9):
                item = self._table.item(r, c)
                t = item.text().strip() if item else ""
                grid[r][c] = int(t) if t.isdigit() else 0
        return grid

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if getattr(self, "_loading", False):
            return
        t = (item.text() or "").strip()
        # 用户输入统一使用高对比度蓝色；为空则回到默认深色
        item.setForeground(_COLOR_USER if t else _COLOR_GIVEN)
        # 统一白底
        item.setBackground(QColor("#FFFFFF"))
        # 统一字体：加粗、加大
        f = item.font()
        f.setPointSize(_FONT_POINT_SIZE)
        f.setBold(_FONT_BOLD)
        item.setFont(f)

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
                    item = self._table.item(r, c)
                    if item:
                        item.setText("")
                        # 同步样式
                        item.setForeground(_COLOR_GIVEN)
                        item.setBackground(QColor("#FFFFFF"))
                        f = item.font()
                        f.setPointSize(_FONT_POINT_SIZE)
                        f.setBold(_FONT_BOLD)
                        item.setFont(f)
        self._hint.setText("")

    def _on_new(self) -> None:
        # 直接生成新题（不使用固定题库）
        self._load_puzzle(self._new_random_puzzle())
        self._hint.setText("")
