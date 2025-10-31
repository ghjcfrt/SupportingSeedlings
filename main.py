"""项目便捷入口

用法
    - python main.py                  启动 儿童识物 GUI
    - python main.py gui             启动 儿童识物 GUI
    - python main.py detect [args]   运行检测 CLI

推荐的模块入口（更规范）：
    - python -m app.kids_gui         启动 GUI
    - python -m detection.cli        运行检测 CLI
"""
from __future__ import annotations

import sys

from app.kids_gui import main as kids_main
from detection.cli import main as detect_main


def _run_gui() -> None:
    """启动 儿童识物 GUI（默认）"""
    kids_main()


def _run_detect(argv: list[str]) -> None:
    """运行检测 CLI"""
    detect_main(argv)


def _print_usage() -> None:
    """打印用法说明"""
    print(
        "用法:\n"
        "  python main.py                 # 启动 儿童识物 GUI（默认）\n"
        "  python main.py gui             # 启动 儿童识物 GUI\n"
        "  python main.py detect [参数]   # 运行检测 CLI\n",
        end="",
    )


def main() -> None:
    """主入口 根据命令行参数分发到不同子模块"""
    if len(sys.argv) == 1:
        _run_gui()
        return

    cmd = (sys.argv[1] or "").strip().lower()
    rest = sys.argv[2:]

    if cmd == "gui":
        _run_gui()
        return
    if cmd in {"detect", "det", "yolo"}:
        _run_detect(rest)
        return

    _print_usage()
    sys.exit(2)


if __name__ == "__main__":
    main()
