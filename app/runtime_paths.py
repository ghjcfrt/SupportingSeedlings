"""运行时资源路径工具

提供在开发环境与 PyInstaller 单文件 (frozen) 环境下统一的资源根目录：
- 开发时：返回仓库根目录（本文件的上上级目录）
- 打包后：返回可执行文件所在目录（main.exe 同级目录）

并提供常用的模型目录定位函数。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def app_root() -> Path:
    """返回资源根目录。

    - 如果是 PyInstaller 单文件（sys.frozen 为 True）：返回 exe 所在目录
    - 否则：返回当前包的上上级目录（项目根）
    """
    try:
        if getattr(sys, "frozen", False):  # PyInstaller 单文件
            return Path(sys.executable).resolve().parent
    except Exception:
        pass
    # 源码运行：本文件位于 app/runtime_paths.py -> parents[1] 指向项目根
    return Path(__file__).resolve().parents[1]


def model_dir(sub: str | None = None) -> Path:
    """返回模型目录路径，默认指向 models/yolo。

    参数 sub: 可选子目录名，如传入 "yolo" 则返回 models/yolo。
    """
    base = app_root() / "models"
    if sub:
        base = base / sub
    return base


def ensure_model_dir(sub: str | None = None) -> Path:
    """确保模型目录存在并返回路径。"""
    p = model_dir(sub)
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return p


def prefer_local_weights(path: str | os.PathLike[str]) -> str:
    """将给定的权重路径解析为“相对 app 根”的绝对路径（若为相对）。

    - 若 path 是绝对路径，原样返回
    - 若为相对路径，则以 app_root() 作为前缀拼接
    """
    p = Path(path)
    if not p.is_absolute():
        p = app_root() / p
    return str(p)


def configure_local_model_caches() -> Path:
    """将常见的模型/权重缓存目录环境变量重定向到本地 models/yolo 目录。

    返回设置后的目录路径。
    """
    target = ensure_model_dir("yolo")
    # 常见缓存环境变量
    env_overrides = {
        "TORCH_HOME": str(target),
        "HF_HOME": str(target),
        "HUGGINGFACE_HUB_CACHE": str(target),
        "TRANSFORMERS_CACHE": str(target),
        # Ultralytics 相关（如果被库读取则生效；未知键不会有副作用）
        "ULTRALYTICS_HOME": str(target),
        "YOLO_CACHE_DIR": str(target),
    }
    for k, v in env_overrides.items():
        try:
            os.environ.setdefault(k, v)
        except Exception:
            pass
    return target


def ensure_weights_file(resolved_path: str, alias_name: str | None = None) -> str:
    """若指定权重文件不存在，尝试使用 Ultralytics 下载到本地并返回路径。

    参数:
      - resolved_path: 绝对路径，指向希望保存的 .pt 文件位置
      - alias_name: 可选，Ultralytics 官方模型别名（如 "yolo11n.pt"），
                    若未提供，则使用目标文件名作为别名尝试下载。
    """
    p = Path(resolved_path)
    if p.exists():
        return str(p)
    # 确保目录存在
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    # 通过 Ultralytics 的下载工具拉取到指定目录
    name = alias_name or p.name
    try:
        from ultralytics.utils.downloads import download  # type: ignore
        download(name, dir=p.parent)
        # 下载完成后，如果文件名不同，尝试将下载的文件重命名为目标名
        cand = p.parent / name
        if cand.exists() and cand.name != p.name:
            try:
                cand.rename(p)
            except Exception:
                # 若重命名失败但目标已存在，忽略
                if not p.exists():
                    raise
    except Exception:
        # 下载失败时不抛出致命错误，交由上层用 YOLO 内部机制继续尝试
        pass
    return str(p)
