# -*- coding: utf-8 -*-
"""MCP 服务端到端测试：stdio 连接 mcp_server.py，列工具 + 调用 solver_info/evaluate_batch。"""
import asyncio
import os
import sys
import json

sys.executable and None
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SERVER = os.path.join(ROOT, "candidate", "indpensim", "v0.1", "mcp_server.py")


async def main():
    sp = StdioServerParameters(command=sys.executable, args=[SERVER], cwd=ROOT)
    async with stdio_client(sp) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            print("TOOLS:", names)
            assert "simulate_batch" in names and "optimize_feed" in names

            r = await session.call_tool("solver_info", {})
            info = json.loads(r.content[0].text)
            print("INFO.version:", info["version"])
            print("INFO.golden:", len(info["golden_set"]["normal"]), "normal +",
                  len(info["golden_set"]["fault"]), "fault")

            r = await session.call_tool("evaluate_batch", {"batch_no": 8})
            ev = json.loads(r.content[0].text)
            print(f'EVAL batch8: yield_err={ev["yield"]["rel_err_total"]:+.1%} crash={ev["crash"]["level"]}')
            print("MCP E2E TEST PASS")


asyncio.run(main())
