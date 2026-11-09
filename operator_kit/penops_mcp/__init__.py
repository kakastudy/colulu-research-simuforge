# -*- coding: utf-8 -*-
"""penops_mcp —— L2 MCP 协议层（**当前未装载**、未启动、未注册到任何 Agent）。

    PYTHONPATH=<operator_kit> python -m penops_mcp --self-check
    PYTHONPATH=<operator_kit> python -m penops_mcp                 # stdio 服务

工具清单来自 `penops.tools()`（L1 单一真源），本包只做协议适配。
装载示例见同目录 `mcp.json.example` —— 本轮按用户要求不写入 `~/.workbuddy/mcp.json`。
"""
from .server import PROTOCOL_VERSIONS, SERVER_NAME, SERVER_VERSION, call_tool, handle, serve

__all__ = ["serve", "handle", "call_tool", "SERVER_NAME", "SERVER_VERSION", "PROTOCOL_VERSIONS"]
