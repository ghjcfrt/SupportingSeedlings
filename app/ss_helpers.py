"""面向外部的聚合入口：保持兼容的同时将各对话框拆分为独立模块。

原来从 app.kids_helpers 导入的符号依然可用：
- GameDialog
- AdvisorDialog
- RecommendDialog
"""

from .advisor_dialog import AdvisorDialog
from .game_dialog import GameDialog
from .recommend_dialog import RecommendDialog

__all__ = [
    "GameDialog",
    "AdvisorDialog",
    "RecommendDialog",
]
