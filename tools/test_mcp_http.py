# -*- coding: utf-8 -*-
"""MCP HTTP 传输端到端验证（fastmcp 客户端 ↔ mcp_server http 8931）。"""
import asyncio
import json

from fastmcp import Client

URL = "http://127.0.0.1:8931/mcp"


async def main():
    async with Client(URL) as s:
        tools = await s.list_tools()
        names = [t.name for t in tools]
        print("TOOLS:", len(names), names)
        info = await s.call_tool("solver_info", {})
        d = json.loads(info.content[0].text)
        print("INFO:", d["version"], "| golden normal:", d["golden_set"]["normal"])
        tr = await s.call_tool("trajectory_check", {"batch_no": 8})
        t = json.loads(tr.content[0].text)
        print("TRAJ b8 T max.nrmse=%.1f%%" % t["metrics"]["T"]["nrmse_max_pct"])
        print("MCP HTTP E2E PASS（服务常驻验证）")


asyncio.run(main())
