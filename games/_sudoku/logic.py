from __future__ import annotations

import random
from typing import List, Tuple


def chunks(s: str, n: int) -> List[str]:
    """将字符串分块为指定大小的块。"""
    return [s[i : i + n] for i in range(0, len(s), n)]


def is_valid_value(grid: List[List[int]], r: int, c: int, v: int) -> bool:
    """ 检查在位置 (r,c) 放置值 v 是否有效。"""
    for cc in range(9):
        if grid[r][cc] == v:
            return False
    for rr in range(9):
        if grid[rr][c] == v:
            return False
    br, bc = (r // 3) * 3, (c // 3) * 3
    for i in range(3):
        for j in range(3):
            if grid[br + i][bc + j] == v:
                return False
    return True


def _find_mrv_cell(grid: List[List[int]]) -> Tuple[int, int, List[int]] | None:
    """ 寻找最小剩余值（MRV）单元格 """
    best: Tuple[int, int, List[int]] | None = None
    best_len = 10
    for r in range(9):
        for c in range(9):
            if grid[r][c] == 0:
                candidates = [v for v in range(1, 10) if is_valid_value(grid, r, c, v)]
                if not candidates:
                    return (r, c, [])
                if len(candidates) < best_len:
                    best = (r, c, candidates)
                    best_len = len(candidates)
                    if best_len == 1:
                        return best
    return best


def generate_full_grid(max_retries: int = 3) -> List[List[int]]:
    """ 生成完整的数独解盘。"""
    for _ in range(max_retries):
        grid = [[0] * 9 for _ in range(9)]

        def dfs() -> bool:
            pick = _find_mrv_cell(grid)
            if pick is None:
                return True
            r, c, candidates = pick
            if not candidates:
                return False
            random.shuffle(candidates)
            for v in candidates:
                if is_valid_value(grid, r, c, v):
                    grid[r][c] = v
                    if dfs():
                        return True
                    grid[r][c] = 0
            return False

        if dfs():
            return grid
    raise RuntimeError("Failed to generate a full Sudoku grid after retries")


def mask_grid(grid: List[List[int]], mask_rate: float) -> List[List[int]]:
    """ 按照指定遮罩率遮罩数独盘。"""
    k = max(0, min(81, int(round(81 * mask_rate))))
    positions = [(r, c) for r in range(9) for c in range(9)]
    random.shuffle(positions)
    g2 = [row[:] for row in grid]
    for i in range(k):
        r, c = positions[i]
        g2[r][c] = 0
    return g2


def grid_to_str(grid: List[List[int]]) -> str:
    """将数独网格转换为字符串。"""
    return "".join("".join(str(v) for v in row) for row in grid)


def count_solutions(grid: List[List[int]], limit: int = 2) -> int:
    """ 计算数独解的数量，最多计算到 limit 个解。"""
    def find_empty() -> Tuple[int, int] | None:
        """ 寻找下一个空单元格 """
        for rr in range(9):
            for cc in range(9):
                if grid[rr][cc] == 0:
                    return rr, cc
        return None

    cnt = 0

    def dfs():
        """ 深度优先搜索计数解 """
        nonlocal cnt
        if cnt >= limit:
            return
        pos = find_empty()
        if pos is None:
            cnt += 1
            return
        r, c = pos
        for v in range(1, 10):
            if is_valid_value(grid, r, c, v):
                grid[r][c] = v
                dfs()
                if cnt >= limit:
                    grid[r][c] = 0
                    return
                grid[r][c] = 0

    dfs()
    return cnt


def mask_grid_unique(grid: List[List[int]], mask_rate: float, max_rounds: int = 6) -> List[List[int]]:
    """ 生成唯一解的数独盘面，按指定遮罩率遮罩。"""
    target = max(0, min(81, int(round(81 * mask_rate))))
    g2 = [row[:] for row in grid]
    zeros = 0
    rounds = 0

    while zeros < target and rounds < max_rounds:
        positions = [(r, c) for r in range(9) for c in range(9) if g2[r][c] != 0]
        random.shuffle(positions)
        progressed = False
        for r, c in positions:
            if zeros >= target:
                break
            tmp = g2[r][c]
            g2[r][c] = 0
            copy_grid = [row[:] for row in g2]
            if count_solutions(copy_grid, limit=2) == 1:
                zeros += 1
                progressed = True
            else:
                g2[r][c] = tmp
        if not progressed:
            rounds += 1
        else:
            rounds = 0
    return g2


# 难度配置
DIFFICULTY_CONFIG = {
    "简单": {"mask": 0.50, "maxSolutions": 1},
    "中等": {"mask": 0.60, "maxSolutions": 1},
    "困难": {"mask": 0.70, "maxSolutions": 1},
    "多解": {"mask": 0.65, "maxSolutions": 999},
}
