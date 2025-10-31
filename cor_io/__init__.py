"""设备与摄像头相关工具门面
"""

from __future__ import annotations

from .camera_utils import get_directshow_device_names, map_indices_to_names

__all__ = [
    "get_directshow_device_names",
    "map_indices_to_names",
]
