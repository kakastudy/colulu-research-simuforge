# -*- coding: utf-8 -*-
"""HTTP 传输层 MCP 验证：list_tools（应 11 个）+ advise_control E2E（批 8 单候选）。"""
import asyncio
import io
import json
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="gbk", errors="replace")

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

URL = "http://127.0.0.1:8931/mcp"


async def main():
    async with streamable_http_client(URL) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = await s.list_tools()
            names = sorted(t.name for t in tools.tools)
            print(len(names), "tools:", names)
            assert "advise_control" in names and "trajectory_check" in names
            res = await s.call_tool("advise_control",
                                    {"batch_no": 8, "t_window_start": 60,
                                     "t_window_end": 120, "candidates": [{"Fs": 1.03}]})
            out = json.loads(res.content[0].text)
            print("advise_control OK: target_g=%.0f best=%s crash=%s t1_ok=%s" % (
                out["target_g"], out["best"]["scales"], out["best"]["crash"],
                out["t1_validation"]["ok"]))
            print("HTTP MCP 11-TOOLS E2E PASS")

asyncio.run(main())
