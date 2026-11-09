# -*- coding: utf-8 -*-
"""列出 fastmcp 注册的全部工具名。"""
import io
import sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="gbk", errors="replace")
sys.path.insert(0, r"C:\Users\admin\Desktop\AI4S研究\青霉素反应罐\candidate\indpensim\v0.1")

import asyncio
import mcp_server

tools = asyncio.run(mcp_server.mcp.list_tools())
names = sorted(t.name for t in tools)
print(len(names), "tools:", names)
