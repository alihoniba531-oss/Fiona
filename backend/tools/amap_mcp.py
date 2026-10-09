"""百炼托管高德 MCP 的无状态 tools/call 客户端。"""
import itertools
import json
import os
import re
import socket
import time
import urllib.error
import urllib.request


AMAP_MCP_URL = "https://dashscope.aliyuncs.com/api/v1/mcps/amap-maps/mcp"
MAX_RESPONSE_BYTES = 1_000_000
_REQUEST_IDS = itertools.count(1)
_DEFAULT_TIMEOUT_SECONDS = 8.0


def _timeout_seconds() -> float:
    try:
        timeout = float(os.environ.get("FIONA_AMAP_TIMEOUT_SECONDS", "8"))
    except (TypeError, ValueError):
        return _DEFAULT_TIMEOUT_SECONDS
    return timeout if 1 <= timeout <= 30 else _DEFAULT_TIMEOUT_SECONDS


def _sse_messages(text: str):
    """按空行分隔 SSE 事件，并连接同一事件的 data 字段。"""
    data = []
    # SSE 仅用 LF、CRLF 与 CR 分隔行；补一个空行处理末尾事件。
    for line in [*re.split(r"\r\n|\r|\n", text), ""]:
        if not line:
            if data:
                try:
                    yield json.loads("\n".join(data))
                except (ValueError, TypeError):
                    pass
            data = []
        elif not line.startswith(":"):
            field, _, value = line.partition(":")
            if field == "data":
                data.append(value[1:] if value.startswith(" ") else value)


def _parse_response(raw: bytes, content_type: str, request_id: int) -> dict | None:
    try:
        text = raw.decode("utf-8")
        if "text/event-stream" in content_type.lower():
            return next((message for message in _sse_messages(text)
                         if isinstance(message, dict) and message.get("id") == request_id), None)
        message = json.loads(text)
        return message if isinstance(message, dict) and message.get("id") == request_id else None
    except (UnicodeDecodeError, ValueError, TypeError):
        return None


def call_tool(name: str, arguments: dict) -> dict:
    """返回解析后的 data 或固定错误码，任何失败均不暴露参数或响应原文。"""
    started = time.perf_counter()

    def failed(kind: str) -> dict:
        ms = (time.perf_counter() - started) * 1000
        print(f"[amap-mcp] failed tool={name} kind={kind} ms={ms:.1f}", flush=True)
        return {"ok": False, "error": kind}

    try:
        if os.environ.get("FIONA_AMAP_ENABLED", "1") == "0":
            return failed("disabled")
        api_key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
        if not api_key:
            return failed("missing_key")
        budget = _timeout_seconds()
        request_id = next(_REQUEST_IDS)
        body = json.dumps({
            "jsonrpc": "2.0", "id": request_id, "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(AMAP_MCP_URL, data=body, method="POST", headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        })
        remaining = budget - (time.perf_counter() - started)
        if remaining <= 0:
            return failed("timeout")
        with urllib.request.urlopen(request, timeout=remaining) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            content_type = response.headers.get("Content-Type", "")
        if len(raw) > MAX_RESPONSE_BYTES:
            return failed("too_large")
        if time.perf_counter() - started > budget:
            return failed("timeout")
        message = _parse_response(raw, content_type, request_id)
        if message is None:
            return failed("bad_response")
        if "error" in message:
            return failed("rpc_error")
        result = message.get("result")
        if not isinstance(result, dict):
            return failed("bad_response")
        content = result.get("content")
        text_blocks = [block.get("text") for block in content
                       if isinstance(block, dict) and block.get("type") == "text"] if isinstance(content, list) else []
        if result.get("isError"):
            return failed("quota" if any(isinstance(text, str) and "OVER_LIMIT" in text
                                        for text in text_blocks) else "tool_error")
        if not text_blocks or not isinstance(text_blocks[0], str):
            return failed("bad_response")
        text = text_blocks[0]
        try:
            data = json.loads(text)
        except (TypeError, ValueError):
            data = text
        return {"ok": True, "data": data}
    except urllib.error.HTTPError as exc:
        kind = "auth" if exc.code in (401, 403) else "not_enabled" if exc.code == 404 else "http"
        return failed(kind)
    except (socket.timeout, TimeoutError):
        return failed("timeout")
    except urllib.error.URLError as exc:
        return failed("timeout" if isinstance(exc.reason, (socket.timeout, TimeoutError)) else "exception")
    except Exception:
        return failed("exception")
