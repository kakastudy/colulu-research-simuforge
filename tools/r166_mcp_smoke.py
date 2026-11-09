# -*- coding: utf-8 -*-
"""R166 / D-85 MCP 冒烟闸门 —— 无 stub、进程内、不监听任何端口。

背景（多轮寻优结论，见 docs/r166_verdict.md §3 V4）
--------------------------------------------------
第三方 `fastmcp` 2.x 全系要求 rich>=13.9.4 / pydantic>=2.11 / 更高 mcp / anyio 4.x，
实测 pip dry-run：
  * 2.14.7 → 连带升级 30+ 包（pydantic 2.14.3 / anyio 4.16 / mcp 1.30）；
  * 2.0.0  → 连带升级 11 包（rich 15 / fastapi 0.162 / starlette 1.7 / anyio 4.16）。
且 `--no-deps` 装 2.14.7 后 import 直接失败（rich 13.7.1 不支持 tracebacks_max_frames）。
⇒ 最优解：不引入第三方包，改用**官方 SDK 内置** `mcp.server.fastmcp.FastMCP`
（已装 mcp==1.12.0），由 `_OfficialSDKFastMCP` 抹平 `@tool` / `run` 两处 API 差异。

**硬约束**：本闸门不调用 `mcp.run()`、不启动服务、不触碰 8770 端口
（用户 2026-11-05 明确要求 Do NOT restart or retry）。

判据 S1–S9（数据来自 runs/r165_mcp_tools_probe.json 与改前备份，不手写结论）。
"""
import argparse
import ast
import asyncio
import importlib.util
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs"
BACKUP = RUNS / "_r166_backup" / "mcp_server_pre_r166.py"
CURRENT = ROOT / "candidate" / "indpensim" / "v0.1" / "mcp_server.py"
sys.path.insert(0, str(ROOT / "candidate" / "indpensim" / "v0.1"))


def tool_funcs(text):
    """AST 提取 `@mcp.tool` 顶层函数 → {name: (ast.dump(body), signature)}。"""
    out = {}
    for n in ast.parse(text).body:
        if not isinstance(n, ast.FunctionDef):
            continue
        if not any(isinstance(d, ast.Attribute) and d.attr == "tool"
                   for d in n.decorator_list):
            continue
        out[n.name] = ast.dump(ast.Module(body=n.body, type_ignores=[]))
    return out


def module_consts(text):
    """提取 solver_info 依赖的模块级字面常量。"""
    out = {}
    for n in ast.parse(text).body:
        if isinstance(n, ast.Assign) and len(n.targets) == 1 \
                and isinstance(n.targets[0], ast.Name) \
                and n.targets[0].id in ("VERSION", "PARAM_KEYS_INFO"):
            try:
                out[n.targets[0].id] = ast.literal_eval(n.value)
            except Exception:
                pass
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    checks = []

    def check(cid, name, ok, got):
        checks.append({"id": cid, "name": name, "pass": bool(ok), "got": got})

    # S1 无 stub 导入
    err = None
    m = None
    try:
        import mcp_server as m
    except Exception as exc:
        err = "%s: %s" % (type(exc).__name__, exc)
    check("S1", "无 stub 直接 import mcp_server（D-85 实质关闭）", err is None,
          {"error": err, "backend": None if m is None else m._FASTMCP_BACKEND})

    # S2 依赖环境
    spec = importlib.util.find_spec("fastmcp")
    sdk_ok = importlib.util.find_spec("mcp.server.fastmcp") is not None
    check("S2", "第三方 fastmcp 未安装；官方 SDK FastMCP 可用（零依赖污染）",
          spec is None and sdk_ok,
          {"third_party_fastmcp_spec": None if spec is None else str(spec.origin),
           "official_sdk_available": sdk_ok})

    # S3 依赖锁
    req = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    check("S3", "requirements.txt 锁 mcp==1.12.0 且不含 fastmcp 发行版",
          "mcp==1.12.0" in req and "fastmcp==" not in req,
          {"mcp_locked": "mcp==1.12.0" in req,
           "fastmcp_pinned": "fastmcp==" in req})

    if m is None:
        out = {"round": "R166", "tool": "r166_mcp_smoke", "checks": checks,
               "n_pass": sum(1 for c in checks if c["pass"]),
               "n_checks": len(checks), "verdict": "FAIL"}
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 1

    # S4 进程内 list_tools（官方 SDK 为 async）
    tools = []
    lt_err = None
    try:
        lt = m.mcp.list_tools()
        if asyncio.iscoroutine(lt):
            lt = asyncio.run(lt)
        tools = [t.name for t in lt]
    except Exception as exc:
        lt_err = "%s: %s" % (type(exc).__name__, exc)
    check("S4", "进程内 list_tools() 可枚举工具（不启动服务 / 不监听端口）",
          lt_err is None and len(tools) == 14,
          {"error": lt_err, "n_tools": len(tools), "tools": sorted(tools)})

    # S5 与 R165 冻结工具名集合一致
    probe = json.loads((RUNS / "r165_mcp_tools_probe.json").read_text(encoding="utf-8"))
    m1 = next((c for c in probe["checks"] if c.get("id") == "M1"), {})
    m1v = m1.get("got") or m1.get("value") or {}
    frozen_names = set(m1v.get("names", []))
    check("S5", "工具名集合与 R165 冻结快照一致（14 个，零增减）",
          bool(frozen_names) and set(tools) == frozen_names,
          {"n_frozen": len(frozen_names), "n_now": len(tools),
           "added": sorted(set(tools) - frozen_names),
           "removed": sorted(frozen_names - set(tools))})

    # S6 既有 14 个工具函数体与改前备份逐字一致
    before = tool_funcs(BACKUP.read_text(encoding="utf-8"))
    after = tool_funcs(CURRENT.read_text(encoding="utf-8"))
    same = sorted(k for k in before if k in after and before[k] == after[k])
    check("S6", "14 个工具函数体与 R166 改前逐字一致（只改 import 段）",
          len(same) == 14 and set(before) == set(after),
          {"n_before": len(before), "n_after": len(after),
           "n_identical": len(same), "changed": sorted(set(before) ^ set(after))})

    # S7 solver_info 依赖的模块级常量逐字一致
    cb, ca = module_consts(BACKUP.read_text(encoding="utf-8")), \
        module_consts(CURRENT.read_text(encoding="utf-8"))
    check("S7", "solver_info 依赖的 VERSION / PARAM_KEYS_INFO 未变", cb == ca,
          {"identical": cb == ca, "version": ca.get("VERSION")})

    # S8 solver_info 实际返回体与 R165 冻结版本一致
    si = m.solver_info()
    m4 = next((c for c in probe["checks"] if c.get("id") == "M4"), {})
    m4v = m4.get("got") or m4.get("value") or {}
    v_frozen = m4v.get("version_frozen")
    check("S8", "solver_info() 返回体 version 与 R165 冻结快照一致",
          si.get("version") == v_frozen and si.get("name") == "indpensim-solver",
          {"version_now": si.get("version"), "version_frozen": v_frozen,
           "name": si.get("name"), "keys": sorted(si.keys())})

    # S9 未启动服务（静态：本脚本不调用 run；__main__ 块仍为原样且未被执行）
    src = CURRENT.read_text(encoding="utf-8")
    tree = ast.parse(src)
    main_guard = [n for n in tree.body if isinstance(n, ast.If)]
    has_run = any(isinstance(x, ast.Call) and isinstance(x.func, ast.Attribute)
                  and x.func.attr == "run" for g in main_guard for x in ast.walk(g))
    smoke_tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    def _is_forbidden(n):
        if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)):
            return False
        if n.func.attr in ("bind", "listen", "serve_forever"):
            return True
        if n.func.attr != "run":
            return False
        # asyncio.run 只是协程调度，不是「启动服务」；其余 run（如 mcp.run）禁止。
        return not (isinstance(n.func.value, ast.Name)
                    and n.func.value.id == "asyncio")

    forbidden = [n for n in ast.walk(smoke_tree) if _is_forbidden(n)]
    check("S9", "冒烟闸门无 run/bind/listen 调用（AST 判据）⇒ 不启动服务、不碰 8770 端口",
          has_run and len(forbidden) == 0,
          {"server_main_block_has_run": has_run,
           "smoke_forbidden_calls": len(forbidden),
           "note": "__main__ 块保留但未执行；用户明确禁止重启 8770 服务"})

    n_pass = sum(1 for c in checks if c["pass"])
    out = {"round": "R166", "tool": "r166_mcp_smoke", "debt": "D-85",
           "checks": checks, "n_pass": n_pass, "n_checks": len(checks),
           "verdict": "PASS" if n_pass == len(checks) else "FAIL",
           "env_note": "third-party fastmcp intentionally NOT installed; "
                       "official MCP SDK FastMCP used via compat layer"}
    if a.json:
        (RUNS / "r166_mcp_smoke.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=1, default=str),
            encoding="utf-8")
    print("MCP 冒烟 %d/%d %s" % (n_pass, len(checks), out["verdict"]))
    for c in checks:
        print("  %s %-3s %s" % ("[OK]" if c["pass"] else "[FAIL]", c["id"], c["name"]))
    return 0 if out["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
