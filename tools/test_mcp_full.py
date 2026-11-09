# -*- coding: utf-8 -*-
"""MCP 全工具 E2E：golden_set_validate（重） + optimize_feed（C 档）。"""
import asyncio, os, sys, json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SERVER = os.path.join(ROOT, "candidate", "indpensim", "v0.1", "mcp_server.py")


async def main():
    sp = StdioServerParameters(command=sys.executable, args=[SERVER], cwd=ROOT)
    async with stdio_client(sp) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            res = await s.call_tool("golden_set_validate", {})
            g = json.loads(res.content[0].text)
            print(f"GOLDEN: RMSE={g['rmse']:.2%} within5={len(g['within5'])}/12 "
                  f"catastrophic={len(g['catastrophic'])}")
            res = await s.call_tool("optimize_feed",
                                    {"batch_no": 8, "vars": ["Foil"], "maxiter": 4})
            o = json.loads(res.content[0].text)
            print(f"OPT batch8 {o['objective']}: base={o['baseline_yield_g']/1e6:.3f} Mg "
                  f"-> {o['opt_yield_g']/1e6:.3f} Mg, x={o['x_best']}, crash={o['crash_level']}")
            print("MCP FULL E2E PASS")


asyncio.run(main())
