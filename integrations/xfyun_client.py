from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import ssl
from dataclasses import dataclass
from datetime import datetime
from time import mktime
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode, urlparse
from wsgiref.handlers import format_date_time

try:  #  运行时校验
    import websocket
    if not hasattr(websocket, "WebSocketApp"):
        raise ImportError("'websocket' 模块非 websocket-client 实现，缺少 WebSocketApp")
    _WS_IMPORT_ERR: Exception | None = None
except Exception as _e:  #  内部状态
    websocket = None
    _WS_IMPORT_ERR = _e
finally:
    # 使用 Any 包装，避免静态分析对属性可用性的误报
    _ws: Any = websocket  # type: ignore

# 科大讯飞 SparkCube WebSocket 客户端封装
# 依赖 test/SparkApi2.py 的协议思路，使用 websocket-client 直连服务，
# 支持多轮对话：将 messages 序列化为 message.text 的多条 role/content。
# 环境变量：XF_APPID/XF_API_KEY/XF_API_SECRET、XF_URL、XF_DOMAIN


@dataclass
class SparkConfig:
    # 注意：不要在字段默认值里调用 getenv（会在导入时就固定下来）。
    # 统一走 from_env() 在实例化时读取环境。
    appid: str = ""
    api_key: str = ""
    api_secret: str = ""
    url: str = "wss://sparkcube-api.xf-yun.com/v1/customize"
    domain: str = "max"
    temperature: float = 0.95
    top_k: int = 6
    max_tokens: int = 4 * 1024

    @staticmethod
    def from_env() -> "SparkConfig":
        return SparkConfig(
            appid=os.getenv("XF_APPID", ""),
            api_key=os.getenv("XF_API_KEY", ""),
            api_secret=os.getenv("XF_API_SECRET", ""),
            url=os.getenv("XF_URL", "wss://sparkcube-api.xf-yun.com/v1/customize"),
            domain=os.getenv("XF_DOMAIN", "max"),
            temperature=float(os.getenv("XF_TEMPERATURE", "0.95")),
            top_k=int(os.getenv("XF_TOPK", "6")),
            max_tokens=int(os.getenv("XF_MAX_TOKENS", str(4 * 1024))),
        )

    @staticmethod
    def load_from_json(path: str) -> "SparkConfig":
        """从 JSON 加载配置并写入环境变量，返回基于环境变量的新配置对象。

        文件格式示例见项目根目录的 config_example.json。
        """
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            raise RuntimeError(f"读取配置文件失败: {path}: {e}") from e

        # 将 JSON 中的键写入环境变量，便于后续模块统一读取
        for k, v in data.items():
            if isinstance(v, (int, float)):
                os.environ[k] = str(v)
            elif isinstance(v, str):
                os.environ[k] = v

        # 返回一次新的 from_env 结果（此处才读取刚写入的环境变量）
        return SparkConfig.from_env()


class SparkClient:
    def __init__(self, cfg: Optional[SparkConfig] = None) -> None:
        # 优先使用传入配置；否则从环境变量构造；若缺失则尝试自动加载根目录 config.json
        self.cfg: SparkConfig = cfg or SparkConfig.from_env()
        debug_lines: list[str] = []
        if not (self.cfg.appid and self.cfg.api_key and self.cfg.api_secret):
            # 自动查找 config.json：当前工作目录与项目根目录（二级上级）
            candidates: list[str] = []
            try:
                cwd = os.getcwd()
                candidates.append(os.path.join(cwd, "config.json"))
            except Exception as e:
                debug_lines.append(f"cwd 获取失败: {e}")
            try:
                proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
                candidates.append(os.path.join(proj_root, "config.json"))
            except Exception as e:
                debug_lines.append(f"proj_root 计算失败: {e}")
            used: Optional[str] = None
            for p in candidates:
                exists = os.path.isfile(p)
                size = 0
                try:
                    size = os.path.getsize(p) if exists else 0
                except Exception:
                    size = -1
                debug_lines.append(f"候选: {p} | 存在: {exists} | 大小: {size}")
                if exists:
                    self.cfg = SparkConfig.load_from_json(p)
                    used = p
                    break
            if used:
                debug_lines.append(f"已加载配置: {used}")
        # 二次检查
        if not (self.cfg.appid and self.cfg.api_key and self.cfg.api_secret):
            hint = "\n".join(debug_lines)
            raise RuntimeError(
                "未配置讯飞凭据。请在根目录提供 config.json（参考 config_example.json）或设置环境变量 XF_APPID/XF_API_KEY/XF_API_SECRET。\n"
                f"调试信息:\n{hint}"
            )
        if _WS_IMPORT_ERR is not None:
            raise RuntimeError(
                "未找到 WebSocketApp。请安装 websocket-client 并移除同名冲突包：\n"
                "  uv pip uninstall websocket\n"
                "  uv add websocket-client\n"
                "或确保运行环境优先解析到 websocket-client（模块名为 websocket）。"
            ) from _WS_IMPORT_ERR

    # --- 私有：鉴权 URL 生成 ---
    def _create_ws_url(self) -> str:
        host = urlparse(self.cfg.url).netloc
        path = urlparse(self.cfg.url).path
        now = datetime.now()
        date = format_date_time(mktime(now.timetuple()))
        signature_origin = f"host: {host}\n" + f"date: {date}\n" + f"GET {path} HTTP/1.1"
        signature_sha = hmac.new(self.cfg.api_secret.encode("utf-8"), signature_origin.encode("utf-8"), hashlib.sha256).digest()
        signature_sha_base64 = base64.b64encode(signature_sha).decode("utf-8")
        authorization_origin = (
            f'api_key="{self.cfg.api_key}", algorithm="hmac-sha256", headers="host date request-line", signature="{signature_sha_base64}"'
        )
        authorization = base64.b64encode(authorization_origin.encode("utf-8")).decode("utf-8")
        v = {"authorization": authorization, "date": date, "host": host}
        return self.cfg.url + "?" + urlencode(v)

    # --- 对外：多轮对话 ---
    def chat(self, messages: List[Dict[str, str]], *, files: Optional[List[str]] = None) -> str:
        """与 Spark 进行一次对话，返回模型完整回复文本。

        messages: [{"role": "system|user|assistant", "content": "..."}, ...]
        files: Spark 文档 fileID 列表（可选）
        """
        ws_url = self._create_ws_url()
        # 组织 payload
        text_items: List[Dict[str, Any]] = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            text_items.append({"role": role, "content": content})
        # 如包含私有文档文件
        if files:
            text_items.insert(0, {"type": "file", "file": list(files)})

        payload = {
            "header": {"app_id": self.cfg.appid, "uid": "kid-edu"},
            "parameter": {
                "chat": {
                    "domain": self.cfg.domain,
                    "temperature": self.cfg.temperature,
                    "top_k": self.cfg.top_k,
                    "max_tokens": self.cfg.max_tokens,
                }
            },
            "payload": {"message": {"text": text_items}},
        }

        answer_chunks: list[str] = []

        def on_message(ws, message):
            data = json.loads(message)
            code = data.get("header", {}).get("code", -1)
            if code != 0:
                ws.close()
                return
            choices = data.get("payload", {}).get("choices", {})
            status = choices.get("status", 2)
            texts = choices.get("text", [])
            if texts:
                content = texts[0].get("content", "")
                if content:
                    answer_chunks.append(content)
            if status == 2:
                ws.close()

        def on_open(ws):
            ws.send(json.dumps(payload))

        def on_error(ws, error):
            answer_chunks.append(f"[错误]{error}")

        def on_close(ws, *args):
            pass

        _ws.enableTrace(False)
        ws = _ws.WebSocketApp(
            ws_url, on_message=on_message, on_open=on_open, on_error=on_error, on_close=on_close
        )
        ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})
        return "".join(answer_chunks).strip()
