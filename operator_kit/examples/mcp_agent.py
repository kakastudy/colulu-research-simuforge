# -*- coding: utf-8 -*-
r"""L2 示例：以 Agent 的视角 spawn MCP 服务并调用工具（**不装载、不注册**）。

这只是「Agent 会怎么用」的演示：用一个本地子进程走完整 stdio JSON-RPC 握手。
本轮没有把服务写进 `~/.workbuddy/mcp.json`，也没有启动常驻进程。

运行：
    python examples/mcp_agent.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable


class MCPClient:
    def __init__(self, profile: str = "capabilities"):
        env = dict(os.environ)
        env["PYTHONPATH"] = KIT
        env["PENOPS_ENGINE_ROOT"] = os.path.dirname(KIT)
        self.p = subprocess.Popen(
            [PY, "-m", "penops_mcp", "--profile", profile],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", env=env, bufsize=1,
        )
        self.n = 0

    def request(self, method: str, params: dict | None = None) -> dict:
        self.n += 1
        self.p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": self.n,
                                       "method": method, "params": params or {}},
                                      ensure_ascii=False) + "\n")
        self.p.stdin.flush()
        return json.loads(self.p.stdout.readline())

    def tool(self, name: str, args: dict | None = None) -> dict:
        r = self.request("tools/call", {"name": name, "arguments": args or {}})
        body = json.loads(r["result"]["content"][0]["text"])
        return {"isError": r["result"]["isError"], **body}

    def close(self) -> None:
        try:
            self.p.stdin.close()
        finally:
            self.p.terminate()


def main() -> None:
    c = MCPClient()
    try:
        init = c.request("initialize", {"protocolVersion": "2024-11-05",
                                        "capabilities": {},
                                        "clientInfo": {"name": "demo-agent", "version": "1"}})
        print("initialize →", init["result"]["serverInfo"], init["result"]["protocolVersion"])
        c.p.stdin.write(json.dumps({"jsonrpc": "2.0",
                                    "method": "notifications/initialized"}) + "\n")
        c.p.stdin.flush()

        tools = c.request("tools/list")["result"]["tools"]
        print("tools/list →", len(tools), "个工具；末三个:", [t["name"] for t in tools[-3:]])

        print("solver_info →", c.tool("solver_info")["result"]["name"])
        print("元工具 list_operators →", c.tool("list_operators",
                                                 {"agent_safe_only": True})["result"]["n"], "个可直接调算子")
        print("元工具 invoke_operator →", c.tool("invoke_operator",
                                                 {"name": "model.state_names"})["ok"])
        blocked = c.tool("parameter_scan", {"batch": 8, "axes": [{"key": "mux", "n": 2,
                                                                    "from": 0.40, "to": 0.42}]})
        print("重调用未确认 →", blocked["code"], "（isError =", blocked["isError"], "）")
    finally:
        c.close()


if __name__ == "__main__":
    main()
