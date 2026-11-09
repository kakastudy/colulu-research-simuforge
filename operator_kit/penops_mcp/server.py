# -*- coding: utf-8 -*-
r"""L2 —— MCP 协议适配层（stdio JSON-RPC，零外部依赖，**当前未装载**）。

定位
----
这一层**不含任何数值逻辑**：工具清单、参数 schema、调用、守卫全部委托 L1 `penops`。
因此 L1 与 L2 不可能分叉 —— `tools/list` 就是 `penops.tools()` 的返回值。

协议
----
传输：stdio，一行一个 JSON 消息（MCP 标准 stdio 接法）。
版本：2024-11-05（同时接受 2025-03-26 / 2025-06-18 的客户端请求）。
方法：
    initialize                  → protocolVersion / capabilities / serverInfo
    notifications/initialized   → 通知，无响应
    ping                        → {}
    tools/list                  → {tools: [...]}（含 inputSchema）
    tools/call                  → {content:[{type:"text",text:...}], isError}
    resources/list · prompts/list → 空列表（供客户端探测，不声明这两个能力）
未知方法走 JSON-RPC -32601；notification 一律不回包。

工具集（默认 profile=capabilities，共 21 个）
    14 个 A/B/C/D 能力 + 4 个 v2 扩展 + 3 个元工具：
      list_operators   发现全部 58 个底层算子
      invoke_operator  按全限定名调用底层算子（需 JSON 参数）
      runtime_status   运行时装载核验
`--profile full` 额外把可直接用 JSON 调的底层算子逐个注册为 `op__module__attr`。

安全与失败可见
--------------
* **stdout 只写 JSON-RPC**；任何日志/异常都写 stderr，绝不污染协议流。
* 业务失败（ok=False）⇒ `isError=true`，但 content 里仍给完整
  `{ok,code,error,detail}` —— Agent 必须拿得到原因码，而不是一句"调用失败"。
* L3 五键 / opt-in / confirm / 数值上限四道闸由 L1 `guards` 统一执行，本层不绕过。
* 长时间计算是同步阻塞的：Agent 应先用 `runtime_status` 自检，再决定要不要
  给 `confirm=true`（本服务不启动后台服务、不监听端口、不写任何文件）。

启动（仅示意，**本轮不装载**）
    PYTHONPATH=<operator_kit> python -m penops_mcp --profile capabilities
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from typing import Any

# 允许 `python penops_mcp/server.py` 直接启动
if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import penops  # noqa: E402
from penops import guards, registry  # noqa: E402
from penops._paths import check_layout  # noqa: E402
from penops.errors import OperatorError  # noqa: E402
from penops.result import ok_envelope  # noqa: E402

PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
DEFAULT_PROTOCOL = "2024-11-05"
SERVER_NAME = "penops-penicillin-operators"
SERVER_VERSION = penops.__version__

JSONRPC_PARSE_ERROR = -32700
JSONRPC_INVALID_REQUEST = -32600
JSONRPC_METHOD_NOT_FOUND = -32601
JSONRPC_INVALID_PARAMS = -32602
JSONRPC_INTERNAL_ERROR = -32603

ENV_PROFILE = "PENOPS_MCP_PROFILE"

INSTRUCTIONS = (
    "青霉素补料分批发酵罐仿真算子集。先调用 runtime_status 做装载自检；"
    "用 list_operators 发现底层算子，用 invoke_operator 调用。"
    "重调用工具（86 批复验 / 集合平滑 / 寻优 / 参数扫描 / 在线同化）必须显式传 confirm=true。"
    "L3 五键保持拒绝；fallback_chain / health_probe 需 opt_in。"
    "失败点绝不渲染成 0 值；报产量误差时须同时报 validity。"
)


def _log(msg: str) -> None:
    """所有诊断信息走 stderr —— stdout 是协议通道。"""
    print(f"[penops-mcp] {msg}", file=sys.stderr, flush=True)


def _result_obj(payload: Any) -> dict:
    """tools/call 返回体：JSON 文本 + isError，永不丢错误码。"""
    ok = bool(isinstance(payload, dict) and payload.get("ok", False))
    return {
        "content": [{"type": "text",
                     "text": json.dumps(payload, ensure_ascii=False, default=str)}],
        "isError": not ok,
    }


def _meta_dispatch(name: str, args: dict) -> dict:
    """元工具也返回统一返回体 —— Agent 不该为「哪个工具长什么样」写分支。"""
    if name == "runtime_status":
        return ok_envelope(name, penops.status(), level="meta")
    if name == "list_operators":
        return ok_envelope(
            name,
            registry.list_operators(layer=args.get("layer"),
                                    agent_safe_only=bool(args.get("agent_safe_only", False))),
            level="meta",
        )
    if name == "invoke_operator":
        op = args.get("name")
        kwargs = args.get("kwargs") or {}
        if not op:
            raise OperatorError("param_invalid", "invoke_operator 缺少 name")
        if not isinstance(kwargs, dict):
            raise OperatorError("param_invalid", "kwargs 必须是对象")
        # 先按 MCP 边界校验（拒绝需要内存对象的算子），再走统一返回体
        guards.validate_primitive(op, kwargs, allow_python_objects=False)
        return penops.invoke_primitive(op, **kwargs)
    raise OperatorError("unknown_operator", f"未知元工具 {name!r}")


def call_tool(name: str, args: dict | None, *, profile: str = "capabilities") -> dict:
    """执行一个 MCP 工具，返回统一返回体（永远不抛异常出去）。"""
    args = dict(args or {})
    try:
        if name in registry.META_BY_ID:
            return _meta_dispatch(name, args)
        if name.startswith("op__") and profile == "full":
            op = name[4:].replace("__", ".", 1)
            guards.validate_primitive(op, args.get("kwargs") or {}, allow_python_objects=False)
            return penops.invoke_primitive(op, **(args.get("kwargs") or {}))
        if name in registry.CAP_BY_ID or name in registry.V2_BY_ID:
            # confirm 在 kwargs 里由 guards 统一剥离并校验；不另设旁路
            return penops.call(name, **args)
        raise OperatorError("unknown_operator", f"未知工具 {name!r}",
                            {"hint": "用 tools/list 查看全部工具"})
    except OperatorError as exc:
        return exc.to_dict()
    except Exception as exc:  # noqa: BLE001
        _log(f"工具 {name} 异常：{type(exc).__name__}: {exc}")
        _log(traceback.format_exc(limit=5))
        return OperatorError("call_failed",
                             f"工具 {name} 执行失败：{type(exc).__name__}: {exc}").to_dict()


def handle(req: Any, *, profile: str = "capabilities") -> dict | None:
    """处理一条 JSON-RPC 消息；notification 返回 None（不回包）。"""
    if not isinstance(req, dict):
        return {"jsonrpc": "2.0", "id": None,
                "error": {"code": JSONRPC_INVALID_REQUEST, "message": "请求必须是对象"}}
    rpc_id = req.get("id")
    is_notification = "id" not in req
    method = req.get("method")
    params = req.get("params") or {}

    def ok(result: Any) -> dict | None:
        if is_notification:
            return None
        return {"jsonrpc": "2.0", "id": rpc_id, "result": result}

    def err(code: int, message: str, data: Any = None) -> dict | None:
        if is_notification:
            return None
        e: dict[str, Any] = {"code": code, "message": message}
        if data is not None:
            e["data"] = data
        return {"jsonrpc": "2.0", "id": rpc_id, "error": e}

    try:
        if method == "initialize":
            asked = (params or {}).get("protocolVersion") if isinstance(params, dict) else None
            version = asked if asked in PROTOCOL_VERSIONS else DEFAULT_PROTOCOL
            return ok({
                "protocolVersion": version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "instructions": INSTRUCTIONS,
            })
        if method in ("notifications/initialized", "notifications/cancelled",
                      "notifications/progress"):
            return None
        if method == "ping":
            return ok({})
        if method == "tools/list":
            return ok({"tools": penops.tools(profile=profile)})
        if method == "tools/call":
            if not isinstance(params, dict) or "name" not in params:
                return err(JSONRPC_INVALID_PARAMS, "tools/call 需要 params.name")
            payload = call_tool(params["name"], params.get("arguments") or {}, profile=profile)
            return ok(_result_obj(payload))
        if method in ("resources/list", "prompts/list"):
            key = "resources" if method == "resources/list" else "prompts"
            return ok({key: []})
        if method and str(method).startswith("notifications/"):
            return None
        return err(JSONRPC_METHOD_NOT_FOUND, f"未知方法 {method!r}")
    except Exception as exc:  # noqa: BLE001
        _log(f"handle({method}) 异常：{type(exc).__name__}: {exc}")
        _log(traceback.format_exc(limit=5))
        return err(JSONRPC_INTERNAL_ERROR, f"{type(exc).__name__}: {exc}")


def serve(*, profile: str = "capabilities", inp=None, out=None) -> int:
    """stdio 主循环。每行一条 JSON 消息；EOF 时退出。"""
    inp = inp or sys.stdin
    out = out or sys.stdout
    _log(f"启动 profile={profile} · protocol={DEFAULT_PROTOCOL} · "
         f"engine={check_layout()['project_root']}")
    for line in inp:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as exc:
            resp = {"jsonrpc": "2.0", "id": None,
                    "error": {"code": JSONRPC_PARSE_ERROR, "message": f"JSON 解析失败：{exc}"}}
        else:
            resp = handle(req, profile=profile)
        if resp is not None:
            out.write(json.dumps(resp, ensure_ascii=False, default=str) + "\n")
            out.flush()
    _log("stdin EOF，服务退出")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="penops MCP stdio server（当前未装载）")
    ap.add_argument("--profile", choices=("capabilities", "full"),
                    default=os.environ.get(ENV_PROFILE, "capabilities"),
                    help="capabilities=18 能力+3 元工具（默认）；full 额外展开底层算子")
    ap.add_argument("--self-check", action="store_true",
                    help="只做 tools/list 与三项元工具自检，不进入 stdio 循环")
    a = ap.parse_args(argv)
    if a.self_check:
        tools = penops.tools(profile=a.profile)
        print(json.dumps({
            "ok": True, "profile": a.profile, "n_tools": len(tools),
            "tools": [t["name"] for t in tools],
            "runtime": {k: penops.status()[k] for k in
                        ("ok", "n_capabilities_loaded", "n_primitives_loaded")},
        }, ensure_ascii=False, indent=2))
        return 0
    return serve(profile=a.profile)


if __name__ == "__main__":
    raise SystemExit(main())
