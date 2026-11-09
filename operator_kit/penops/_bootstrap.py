# -*- coding: utf-8 -*-
"""引擎加载器 —— 进程内复用 `mcp_server.py` 的 14 个工具函数本体，零 MCP 依赖。

为什么需要 stub
---------------
`candidate/indpensim/v0.1/mcp_server.py` 顶层会尝试：

    from fastmcp import FastMCP            # 第三方发行版，本项目刻意未装
    from mcp.server.fastmcp import FastMCP # 官方 SDK，装了但会拉起 pydantic/anyio 一整套

而 L1 只是**在 Python 进程内调用那 14 个函数**，根本不需要启动任何 MCP 服务。
因此默认向 `sys.modules` 注入一个极小的 `fastmcp` 替身：`@mcp.tool` 直接返回
原函数。这样：

1. 14 个函数体**逐字复用**（与 R167「同源原则」一致，不复制实现）；
2. L1 库不依赖 `mcp` / `pydantic` / `anyio` 任何版本，可独立搬运；
3. import 更快、行为确定，不受 SDK 版本差异影响。

`PENOPS_REAL_MCP=1` 可关闭 stub，改用真实 SDK（仅调试用，不影响函数体）。
`runtime_status()` 会如实报出当前 backend，不把 stub 伪装成已装载服务。
"""
from __future__ import annotations

import importlib
import os
import sys
import types
from typing import Any

from ._paths import bootstrap_paths, import_engine, preserved_cwd

ENV_REAL_MCP = "PENOPS_REAL_MCP"

_MCP: Any = None
_MCP_ERROR: str | None = None
_STUB_INSTALLED = False


class _StubFastMCP:
    """只需要 `tool` 装饰器：返回原函数，顺手登记名字。"""

    def __init__(self, name: str | None = None, **_: Any):
        self.name = name or "inproc"
        self.tools: dict[str, Any] = {}

    def tool(self, *args: Any, **kwargs: Any):
        def register(fn):
            self.tools[fn.__name__] = fn
            return fn

        if len(args) == 1 and callable(args[0]) and not kwargs:
            return register(args[0])
        return register

    def run(self, *args: Any, **kwargs: Any):  # pragma: no cover - 库内不会调用
        raise RuntimeError("penops 只做进程内调用；MCP 服务请使用 penops_mcp")


def _install_stub() -> None:
    global _STUB_INSTALLED
    if _STUB_INSTALLED or "fastmcp" in sys.modules:
        return
    mod = types.ModuleType("fastmcp")
    mod.FastMCP = _StubFastMCP  # type: ignore[attr-defined]
    mod.__penops_stub__ = True  # type: ignore[attr-defined]
    sys.modules["fastmcp"] = mod
    _STUB_INSTALLED = True


def use_real_mcp() -> bool:
    return os.environ.get(ENV_REAL_MCP, "").strip().lower() in ("1", "true", "yes")


def load_mcp_server():
    """惰性加载 `mcp_server`，返回模块对象。失败显式抛错，不静默降级。"""
    global _MCP, _MCP_ERROR
    if _MCP is not None:
        return _MCP
    if _MCP_ERROR is not None:
        raise ImportError(_MCP_ERROR)

    bootstrap_paths()
    real = use_real_mcp()
    if not real:
        _install_stub()
    try:
        with preserved_cwd():  # mcp_server 顶层 os.chdir(_ROOT)
            mod = importlib.import_module("mcp_server")
    except Exception as exc:  # noqa: BLE001
        _MCP_ERROR = f"{type(exc).__name__}: {exc}"
        raise ImportError(f"引擎服务层加载失败：{_MCP_ERROR}") from exc

    mod._FASTMCP_BACKEND = (
        getattr(mod, "_FASTMCP_BACKEND", "unknown") if real
        else "fastmcp-stub:penops (进程内复用，未启动服务)"
    )
    _MCP = mod
    return _MCP


def engine_module(name: str):
    """按名字加载引擎模块（惰性）。"""
    bootstrap_paths()
    with preserved_cwd():
        return import_engine(name)


def backend_info() -> dict:
    return {
        "real_mcp_sdk": use_real_mcp(),
        "stub_installed": _STUB_INSTALLED,
        "mcp_server_loaded": _MCP is not None,
        "mcp_server_error": _MCP_ERROR,
        "mcp_backend": getattr(_MCP, "_FASTMCP_BACKEND", None) if _MCP else None,
    }
