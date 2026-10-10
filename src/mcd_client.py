"""mcd_client.py — 麦当劳 MCP Server 轻量客户端。

协议要点（D0 探查结论，见 docs/d0-api-notes.md）：
- Streamable HTTP，服务端不返回 mcp-session-id，因此每次 tools/call 前
  先发一次 initialize 即可完成无状态调用。
- 返回 content[].text 为「字段说明 + 内嵌 JSON」，需提取 Original Response。
- 限流 600 次/分钟，本客户端内置最小间隔控制。
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

MCP_URL = "https://mcp.mcd.cn"
MIN_INTERVAL = 0.15  # 约 400 次/分钟，低于官方 600 限流
RETRIES = 2          # 网络类错误重试次数（指数退避）


class McpError(RuntimeError):
    """MCP 调用失败（网络错误 / 业务错误码）。"""


def extract_embedded_json(text: str) -> dict:
    """从 MCP text 中提取内嵌 JSON（Original Response）。

    text 尾部可能拼接了工具提示文本，故从最后一个 } 逐步回退解析。
    未找到 JSON 或解析失败抛 ValueError。
    """
    m = re.search(r'\{"success":.*', text, re.S)
    if not m:
        raise ValueError("返回中未找到 JSON")
    snippet = m.group(0)
    end = snippet.rfind("}")
    while end > 0:
        try:
            return json.loads(snippet[:end + 1])
        except json.JSONDecodeError:
            end = snippet.rfind("}", 0, end)
    raise ValueError(f"JSON 解析失败: {snippet[:200]}")


@dataclass
class McpClient:
    """麦当劳 MCP 客户端。

    用法:
        client = McpClient(token="xxx")
        raw_text = client.call("list-nutrition-foods")
        data = client.call_json("query-meals", {"storeCode": "1450724",
                                                "orderType": 1, "beType": 1})
    """

    token: str
    url: str = MCP_URL
    _last_call_ts: float = field(default=0.0, repr=False)

    # ------------------------------------------------------------------ #
    def _rpc(self, payload: dict) -> dict | None:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {self.token}",
        }
        req = urllib.request.Request(
            self.url, data=json.dumps(payload).encode("utf-8"),
            headers=headers, method="POST",
        )
        try:
            resp = urllib.request.urlopen(req, timeout=60)
        except urllib.error.HTTPError as e:  # 401/429 等协议层错误：不重试
            raise McpError(f"HTTP {e.code}: {e.read().decode('utf-8', 'ignore')[:200]}") from e
        except urllib.error.URLError as e:  # 网络/超时：指数退避重试
            for attempt in range(1, RETRIES + 1):
                time.sleep(0.5 * attempt)
                try:
                    resp = urllib.request.urlopen(req, timeout=60)
                    break
                except urllib.error.URLError:
                    if attempt == RETRIES:
                        raise McpError(f"网络错误（已重试 {RETRIES} 次）: {e}") from e
        raw = resp.read().decode("utf-8")
        return self._parse_response(raw)

    @staticmethod
    def _parse_response(raw: str) -> dict | None:
        """兼容纯 JSON 与 SSE(data:) 两种返回。"""
        if raw.lstrip().startswith("{"):
            return json.loads(raw)
        for line in raw.split("\n"):
            if line.startswith("data:"):
                try:
                    return json.loads(line[5:].strip())
                except json.JSONDecodeError:
                    continue
        return None

    def _throttle(self) -> None:
        now = time.monotonic()
        wait = MIN_INTERVAL - (now - self._last_call_ts)
        if wait > 0:
            time.sleep(wait)
        self._last_call_ts = time.monotonic()

    # ------------------------------------------------------------------ #
    def call(self, tool: str, arguments: dict | None = None) -> str:
        """调用工具，返回 text 原文（含字段说明与 Original Response）。"""
        self._throttle()
        self._rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                   "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                              "clientInfo": {"name": "mcd-fit-coach", "version": "0.1.0"}}})
        self._throttle()
        data = self._rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                          "params": {"name": tool, "arguments": arguments or {}}})
        if not data or "result" not in data:
            raise McpError(f"tools/call {tool} 异常返回: {data}")
        if data["result"].get("isError"):
            raise McpError(f"tools/call {tool} 业务错误: {data['result']}")
        texts = [c.get("text", "") for c in data["result"].get("content", [])
                 if c.get("type") == "text"]
        return "\n".join(texts)

    def call_json(self, tool: str, arguments: dict | None = None) -> dict:
        """调用工具并提取 Original Response 为 dict；失败( success=false )抛 McpError。"""
        text = self.call(tool, arguments)
        try:
            obj = extract_embedded_json(text)
        except ValueError as e:
            raise McpError(f"{tool} {e}") from e
        if isinstance(obj, dict) and obj.get("success") is False:
            raise McpError(f"{tool} 业务失败: {obj.get('code')} {obj.get('message')}")
        return obj
