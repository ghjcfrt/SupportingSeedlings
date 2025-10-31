from __future__ import annotations

import json
from pathlib import Path

from integrations import SparkClient


def mask(s: str, keep: int = 4) -> str:
    if not s:
        return ""
    return s[:keep] + "***" + s[-keep:]


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    candidates = [Path.cwd() / "config.json", root / "config.json"]
    print("[check] cwd=", Path.cwd())
    print("[check] module_root=", root)
    for p in candidates:
        exists = p.is_file()
        size = p.stat().st_size if exists else 0
        print(f"[check] candidate: {p} exists={exists} size={size}")
    # Try load via client (it will auto-load json if env missing)
    try:
        client = SparkClient()
        cfg = client.cfg
        print("[ok] loaded config:")
        print("  appid=", cfg.appid)
        print("  api_key=", mask(cfg.api_key))
        print("  api_secret=", mask(cfg.api_secret))
        print("  url=", cfg.url)
        print("  domain=", cfg.domain)
    except Exception as e:
        print("[error] ", e)
        # Also try explicit load to surface JSON errors
        for p in candidates:
            if p.is_file():
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        json.load(f)
                    print(f"[check] JSON parse ok: {p}")
                except Exception as je:
                    print(f"[check] JSON parse failed: {p}: {je}")


if __name__ == "__main__":
    main()
