"""命令行检测入口封装（Facade）

作为 `python -m detection.cli` 或通过 `main.py detect` 的薄封装；
外部仅依赖 `detection.api`，避免直接耦合内部实现 `detection.core`。
"""

from __future__ import annotations

from detection.api import main as _api_main


def main(argv: list[str] | None = None) -> None:
    """ 命令行检测入口"""
    _api_main(argv)


if __name__ == "__main__":
    main()
