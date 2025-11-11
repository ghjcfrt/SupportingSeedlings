"""扶苗核心

提供基于 YOLO 的简化检测能力：
- 加载一次模型，支持图片/帧检测
- 返回中文标签、置信度与边框
- 选择“距画面中心最近”的目标作为“中央物体”
- 绘制结果并高亮中央物体
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np

from detection.coco_labels_cn import coco_labels_cn

from .runtime_paths import (configure_local_model_caches, ensure_weights_file,
                            prefer_local_weights)

# 在导入 Ultralytics 之前，将缓存与下载目录重定向到本地 models/yolo
try:
    configure_local_model_caches()
except Exception:
    pass

try:
    # 优先使用公开入口（Ultralytics v8/11 推荐）
    from ultralytics import YOLO  # type: ignore[attr-defined]
except ImportError as e:
    YOLO = None
    _YOLO_IMPORT_ERR = e
else:
    _YOLO_IMPORT_ERR = None


def _select_device(requested: str | None) -> str:
    """选择推理设备字符串"""
    try:
        import torch
        if requested and requested.lower() not in {"", "auto"}:
            return requested
        if torch.cuda.is_available():
            return "cuda"
        mps = getattr(getattr(torch, "backends", None), "mps", None)
        if mps is not None and mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


@dataclass
class SSConfig:
    """扶苗检测配置"""
    model_path: str = "models/yolo/yolo11n.pt"
    conf: float = 0.6
    img_size: list[int] | None = None  # None -> 原始尺寸
    device: str = "auto"


@dataclass
class Detection:
    """ 检测结果 """
    cls_id: int
    label_cn: str
    conf: float
    box: tuple[int, int, int, int]  # x1,y1,x2,y2


class SSDetector:
    """面向扶苗教学的简化检测封装"""

    def __init__(self, cfg: SSConfig | None = None) -> None:
        """初始化检测器"""
        global _YOLO_IMPORT_ERR
        if YOLO is None:
            raise ImportError(
                "未安装 ultralytics，请先安装依赖（见 README）"
            ) from _YOLO_IMPORT_ERR
        self.cfg = cfg or SSConfig()
        self.device = _select_device(self.cfg.device)
        # 解析并优先使用本地（exe 根目录下）权重，若缺失则自动下载到该目录
        resolved = prefer_local_weights(self.cfg.model_path)
        min_bytes = int(os.getenv("SS_MIN_MODEL_BYTES", "1000000"))  # 默认 1MB 下限

        def _size_ok(p: str) -> bool:
            """ 检查文件是否存在且尺寸合适 """
            try:
                return Path(p).exists() and Path(p).stat().st_size >= min_bytes
            except Exception:
                return False

        # 若不存在或太小，先下载
        if not _size_ok(resolved):
            ensure_weights_file(resolved, alias_name=Path(resolved).name)

        # 试跑构造，失败则删除并重试一次
        last_err: Exception | None = None
        for _ in range(2):  # 最多两次尝试
            try:
                # 再次校验尺寸，避免不完整文件
                if not _size_ok(resolved):
                    ensure_weights_file(resolved, alias_name=Path(resolved).name)
                self.cfg.model_path = resolved
                self.model = YOLO(resolved)
                last_err = None
                break
            except Exception as e:
                last_err = e
                # 删除可能的残缺文件后重试下载
                try:
                    if Path(resolved).exists():
                        Path(resolved).unlink(missing_ok=True)
                except Exception:
                    pass
                ensure_weights_file(resolved, alias_name=Path(resolved).name)
        if last_err is not None:
            # 最终仍失败，抛出原错误
            raise last_err

    # -------- 检测与结果整理 --------
    def detect_frame(self, frame: np.ndarray) -> tuple[list[Detection], np.ndarray]:
        """检测单帧图像"""
        if frame is None or not isinstance(frame, np.ndarray):
            raise TypeError("frame 必须是 numpy 图像")
        imgsz = self.cfg.img_size
        if imgsz is None:
            h, w = frame.shape[:2]
            imgsz = [h, w]
        results = self.model.predict(
            frame, imgsz=imgsz, conf=self.cfg.conf, device=self.device, verbose=False
        )
        r = results[0]
        dets: list[Detection] = []
        h_img, w_img = frame.shape[:2]
        for box in getattr(r, "boxes", []) or []:
            try:
                cls_id = int(box.cls.item())
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                conf = float(box.conf.item()) if hasattr(box, "conf") else 0.0
            except Exception:
                continue
            # 规范化坐标
            x1i = max(0, min(w_img - 1, int(x1)))
            y1i = max(0, min(h_img - 1, int(y1)))
            x2i = max(0, min(w_img, int(x2)))
            y2i = max(0, min(h_img, int(y2)))
            if x2i <= x1i or y2i <= y1i:
                continue
            label = coco_labels_cn.get(cls_id, str(cls_id))
            dets.append(Detection(cls_id, label, conf, (x1i, y1i, x2i, y2i)))
        # 生成一张可视化图：仅使用 YOLO 原生英文标签与配色
        # 使用 YOLO 自带的绘制方法，不传中文，避免 OpenCV 中文渲染为问号
        plotted = r.plot()
        return dets, plotted

    def detect_image_file(self, path: str) -> tuple[list[Detection], np.ndarray]:
        """检测图片文件"""
        img = cv2.imread(path)
        if img is None:
            raise FileNotFoundError(f"无法读取图片: {path}")
        return self.detect_frame(img)

    # -------- 中央物体选择与可视化 --------
    @staticmethod
    def pick_center_object(dets: Iterable[Detection], frame_shape: tuple[int, int, int]) -> int | None:
        """从检测结果中选择“距画面中心最近”的目标"""
        h, w = frame_shape[:2]
        cx_img, cy_img = w / 2.0, h / 2.0
        best_idx: int | None = None
        best_key: tuple[float, float] | None = None
        for i, d in enumerate(dets):
            x1, y1, x2, y2 = d.box
            cx = (x1 + x2) / 2.0
            cy = (y1 + y2) / 2.0
            dx = cx - cx_img
            dy = cy - cy_img
            dist2 = dx * dx + dy * dy
            key = (dist2, -float(d.conf))
            if best_key is None or key < best_key:
                best_key = key
                best_idx = i
        return best_idx

    @staticmethod
    def annotate_with_center(
        frame: np.ndarray,
        dets: list[Detection],
        center_idx: int | None,
    ) -> np.ndarray:
        """直接返回 YOLO 已绘制的图像，不再叠加任何自定义框或中文文本"""
        return frame






