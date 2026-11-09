# -*- coding: utf-8 -*-
r"""operator_kit 交付闸门 —— L1 Python 库 + L2 MCP 协议端到端复验。

    python operator_kit/tools/verify_kit.py --freeze-baseline   # 首次：建立旧资产哈希基线
    python operator_kit/tools/verify_kit.py                      # 全量（含一次真实仿真）
    python operator_kit/tools/verify_kit.py --fast               # 跳过耗时仿真

判据组织：
    A 布局与零改动   B L1 Python 库   C L2 MCP 协议   D 单一真源与交付物

方法论（承 R168.1）：**断言数据而不是断言容器**。
只验证「server 能启动 / tools/list 有 21 项」远远不够；必须实跑工具、核对错误码、
核对协议握手、核对 stdout 纯净、核对两层清单逐项相等。
"""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import subprocess
import sys
import time
from typing import Any

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(KIT)
if KIT not in sys.path:
    sys.path.insert(0, KIT)

import penops  # noqa: E402
from penops import guards, registry  # noqa: E402

BASELINE = os.path.join(KIT, "ASSET_BASELINE.json")
MANIFEST = os.path.join(KIT, "manifest.json")
EVIDENCE = os.path.join(KIT, "runs", "verify_kit.json")

# 旧资产（L0 冻结基线 / 引擎 / 数据边界）—— 本次封装一行都不该动
FROZEN_ASSETS = [
    "candidate/indpensim/v0.1/mcp_server.py",
    "candidate/indpensim/v0.1/model.py",
    "candidate/indpensim/v0.1/simulate.py",
    "candidate/indpensim/v0.1/golden_params.py",
    "candidate/indpensim/v0.1/soft_sensing.py",
    "candidate/indpensim/v0.1/observe.py",
    "candidate/indpensim/v0.1/solver_chain.py",
    "platform_v2/engine_api.py",
    "platform_v2/scan.py",
    "platform_v2/param_catalog.py",
    "platform/ops_registry.py",
    "platform/serve.py",
    "GOAL.md",
    "ENGINE_CONTRACT.md",
]


def sha256(path: str) -> str | None:
    if not os.path.exists(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def freeze_baseline() -> dict:
    out = {"created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
           "root": ROOT, "files": {}}
    for rel in FROZEN_ASSETS:
        out["files"][rel] = sha256(os.path.join(ROOT, rel))
    with open(BASELINE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return out


class Gate:
    def __init__(self):
        self.items: list[dict] = []

    def add(self, cid: str, label: str, ok: bool, evidence: Any = None) -> None:
        self.items.append({"id": cid, "label": label, "ok": bool(ok), "evidence": evidence})
        print(f"  [{'PASS' if ok else 'FAIL'}] {cid:<5s} {label}"
              + ("" if evidence is None else f"   ({_brief(evidence)})"))

    @property
    def n_pass(self) -> int:
        return sum(1 for x in self.items if x["ok"])

    @property
    def ok(self) -> bool:
        return all(x["ok"] for x in self.items)


def _brief(e: Any) -> str:
    s = json.dumps(e, ensure_ascii=False, default=str)
    return s[:150] + ("…" if len(s) > 150 else "")


# ---------------------------------------------------------------------------
# MCP 客户端（真实子进程 stdio）
# ---------------------------------------------------------------------------
class MCPClient:
    def __init__(self, profile: str = "capabilities"):
        env = dict(os.environ)
        env["PYTHONPATH"] = KIT
        env["PENOPS_ENGINE_ROOT"] = ROOT
        self.p = subprocess.Popen(
            [sys.executable, "-m", "penops_mcp", "--profile", profile],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", env=env, cwd=KIT, bufsize=1,
        )
        self.n = 0
        self.lines: list[str] = []

    def raw(self, obj: dict, expect: bool = True) -> dict | None:
        self.p.stdin.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self.p.stdin.flush()
        if not expect:
            return None
        line = self.p.stdout.readline()
        self.lines.append(line)
        return json.loads(line)

    def req(self, method: str, params: dict | None = None) -> dict:
        self.n += 1
        return self.raw({"jsonrpc": "2.0", "id": self.n, "method": method,
                         "params": params or {}})  # type: ignore[return-value]

    def tool(self, name: str, args: dict | None = None) -> tuple[bool, dict]:
        r = self.req("tools/call", {"name": name, "arguments": args or {}})
        body = json.loads(r["result"]["content"][0]["text"])
        return r["result"]["isError"], body

    def close(self) -> str:
        try:
            self.p.stdin.close()
        except OSError:
            pass
        self.p.terminate()
        try:
            self.p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.p.kill()
        return self.p.stderr.read() or ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze-baseline", action="store_true")
    ap.add_argument("--fast", action="store_true", help="跳过真实仿真（约 20 s）")
    a = ap.parse_args()

    if a.freeze_baseline:
        b = freeze_baseline()
        print(f"基线已写入 {BASELINE}（{len(b['files'])} 个文件）")
        return 0

    print("=== A. 布局与旧资产零改动 ===")
    g = Gate()
    layout = penops.status()
    g.add("A1", "引擎/数据/平台目录布局齐全", layout["layout"]["ok"],
          layout["layout"]["exists"])

    if not os.path.exists(BASELINE):
        print("  [WARN] 基线不存在，自动建立（本次不计为比对通过）")
        freeze_baseline()
    with open(BASELINE, encoding="utf-8") as f:
        base = json.load(f)["files"]
    now = {rel: sha256(os.path.join(ROOT, rel)) for rel in FROZEN_ASSETS}
    changed = [k for k in FROZEN_ASSETS if base.get(k) != now.get(k)]
    g.add("A2", f"{len(FROZEN_ASSETS)} 个旧资产文件 sha256 与基线逐位一致",
          not changed, {"changed": changed})

    # 新代码不得含对旧目录的写操作（静态守卫）
    writes = []
    for sub in ("penops", "penops_mcp"):
        d = os.path.join(KIT, sub)
        for fn in os.listdir(d):
            if not fn.endswith(".py"):
                continue
            with open(os.path.join(d, fn), encoding="utf-8") as f:
                src = f.read()
            for token in ("open(..., 'w'", "write_text(", "shutil.rmtree", "os.remove("):
                if token in src:
                    writes.append(f"{sub}/{fn}:{token}")
    g.add("A3", "封装层不含写文件/删文件操作（只读装配）", not writes, writes)

    print("=== B. L1 Python 库 ===")
    g.add("B1", "import penops 且版本可读", penops.__version__ == "0.1.0",
          {"version": penops.__version__})
    g.add("B2", f"运行时装载核验（能力 {layout['n_capabilities_loaded']}/"
                f"{layout['n_capabilities']}，算子 {layout['n_primitives_loaded']}/"
                f"{layout['n_primitives']}）", layout["ok"],
          {"backend": layout["backend"]["mcp_backend"]})

    # schema 与函数签名零漂移
    drift = []
    for c in registry.CAPABILITIES + registry.V2_EXTENSIONS:
        fn = registry.capability_function(c["id"])
        sig = set(inspect.signature(fn).parameters)
        props = set(registry.capability_schema(c["id"])["properties"]) - {"confirm"}
        if sig != props:
            drift.append({"id": c["id"], "missing": sorted(sig - props),
                          "extra": sorted(props - sig)})
    g.add("B3", "18 个能力的 inputSchema 参数名与函数签名逐项一致", not drift, drift)

    # R167 登记的 12 个算子必须都在目录里
    aliases = {p["alias"] for p in registry.PRIMITIVES if p["alias"]}
    need = set(registry.R167_OPERATOR_ALIASES.values())
    g.add("B4", "R167 登记的 12 个底层算子全部收录", need <= aliases,
          {"n": len(aliases), "missing": sorted(need - aliases)})

    # 零算力实跑
    light = {}
    for name in ("solver_info", "param_catalog", "list_responses"):
        r = penops.call(name)
        light[name] = {"ok": r["ok"], "code": r.get("code"),
                       "elapsed_s": r["elapsed_s"]}
    g.add("B5", "三个零算力能力实跑成功", all(x["ok"] for x in light.values()), light)

    # 统一返回体结构
    r = penops.call("solver_info")
    g.add("B6", "统一返回体含 ok/name/level/elapsed_s/result",
          all(k in r for k in ("ok", "name", "level", "elapsed_s", "result")),
          sorted(r.keys()))

    # 错误码矩阵
    matrix = {
        "unknown_operator": penops.call("no_such_tool"),
        "confirm_required": penops.call("golden_set_validate", full=False),
        "opt_in_required": penops.call("observe_online", batch_no=8, health_probe=True),
        "param_forbidden_l3": penops.call("evaluate_batch", batch_no=8,
                                          params={"k_dual": 1.0}),
        "batch_out_of_range": penops.call("evaluate_batch", batch_no=999),
        "param_invalid": penops.call("solver_info", bogus=1),
    }
    codes = {k: v.get("code") for k, v in matrix.items()}
    g.add("B7", "六类错误码显式且稳定", all(codes[k] == k for k in matrix),
          codes)

    # L3 递归拒绝（三个嵌套位置）
    nested = [
        penops.call("evaluate_batch", batch_no=8, params={"dist_noise_sigma": 0.1}),
        penops.call("run_simulation", batch=8, overrides={"innovation_criteria": {}}),
        penops.call("advise_control", batch_no=8, t_window_start=60, t_window_end=120,
                    candidates=[{"Fs": 1.0, "alpha_kla_override": 85}]),
    ]
    g.add("B8", "L3 五键在 params/overrides/candidates 三层嵌套均被拒绝",
          all(x.get("code") == "param_forbidden_l3" for x in nested),
          [x.get("code") for x in nested])

    # 底层算子（原生对象）
    from penops import primitives as P
    names = P.get("model.state_names")()
    prim = penops.invoke_primitive("knowledge_constraints.control_hard")
    g.add("B9", "底层算子可原生调用（33 状态名 + T1 硬约束）",
          len(names) == 33 and prim["ok"], {"n_states": len(names), "prim_ok": prim["ok"]})

    # python_objects 边界：L1 可调用，MCP 层应拒绝（在 C 组再验一次）
    g.add("B10", "需内存对象的算子在 L1 可调用（DataFrame 直通）",
          callable(P.get("simulate.yield_metrics")), "simulate.yield_metrics")

    if not a.fast:
        t0 = time.time()
        ev = penops.evaluate_batch(batch_no=8)
        g.add("B11", "真实 A 档仿真实跑（batch 8）",
              ev["ok"] and "yield" in (ev.get("result") or {}),
              {"elapsed_s": round(time.time() - t0, 1),
               "yield": (ev.get("result") or {}).get("yield"),
               "crash": (ev.get("result") or {}).get("crash", {}).get("level")})

    print("=== C. L2 MCP 协议（真实 stdio 子进程） ===")
    c = MCPClient()
    stderr = ""
    try:
        init = c.req("initialize", {"protocolVersion": "2025-06-18",
                                    "capabilities": {},
                                    "clientInfo": {"name": "verify_kit", "version": "1"}})
        g.add("C1", "initialize 握手与协议版本协商",
              init.get("result", {}).get("protocolVersion") == "2025-06-18"
              and init["result"]["serverInfo"]["name"] == "penops-penicillin-operators",
              {"protocolVersion": init.get("result", {}).get("protocolVersion")})

        # notification 不得回包：紧随其后发 ping，读到的必须是 ping 的响应
        c.raw({"jsonrpc": "2.0", "method": "notifications/initialized"}, expect=False)
        ping = c.req("ping")
        g.add("C2", "notification 不回包（ping 的 id 不错位）",
              ping.get("id") == c.n and ping.get("result") == {}, {"id": ping.get("id")})

        tl = c.req("tools/list")["result"]["tools"]
        well_formed = all("name" in t and "description" in t and "inputSchema" in t
                          and t["inputSchema"].get("type") == "object" for t in tl)
        g.add("C3", f"tools/list 返回 {len(tl)} 个工具且每个 schema 完整",
              len(tl) == 21 and well_formed, {"n": len(tl)})

        is_err, body = c.tool("solver_info")
        g.add("C4", "tools/call solver_info 实跑成功",
              (not is_err) and body.get("result", {}).get("name") == "indpensim-solver",
              {"isError": is_err})

        is_err, body = c.tool("golden_set_validate", {"full": False})
        g.add("C5", "重调用未确认 ⇒ isError + confirm_required",
              is_err and body.get("code") == "confirm_required",
              {"isError": is_err, "code": body.get("code")})

        is_err, body = c.tool("invoke_operator", {"name": "model.state_names", "kwargs": {}})
        g.add("C6", "元工具 invoke_operator 调到底层算子",
              (not is_err) and len(body.get("result") or []) == 33,
              {"n": len(body.get("result") or [])})

        is_err, body = c.tool("invoke_operator", {"name": "simulate.yield_metrics", "kwargs": {}})
        g.add("C7", "需内存对象的算子在 MCP 层被显式拒绝（能力边界）",
              is_err and body.get("code") == "python_object_required", body.get("code"))

        is_err, lo = c.tool("list_operators", {"agent_safe_only": True})
        is_err2, st = c.tool("runtime_status")
        unified = all("result" in x and x.get("level") == "meta" for x in (lo, st))
        g.add("C8", "元工具可用且同样返回统一返回体（result/level=meta）",
              (not is_err) and (not is_err2) and unified
              and lo["result"]["n"] > 0 and st["result"]["ok"] is True,
              {"agent_safe_ops": lo.get("result", {}).get("n"),
               "status_ok": st.get("result", {}).get("ok"), "unified": unified})

        unknown = c.req("no/such/method")
        g.add("C9", "未知方法返回 JSON-RPC -32601",
              unknown.get("error", {}).get("code") == -32601,
              unknown.get("error", {}).get("code"))

        g.add("C10", "stdout 每一行都是合法 JSON-RPC（协议流纯净）",
              all(isinstance(json.loads(x), dict) and "jsonrpc" in json.loads(x)
                  for x in c.lines), {"n_lines": len(c.lines)})
    finally:
        stderr = c.close()
    g.add("C11", "诊断日志只走 stderr，不污染 stdout",
          "[penops-mcp]" in stderr and "启动" in stderr,
          {"stderr_lines": len(stderr.strip().splitlines())})

    # full profile：底层算子逐个注册
    cf = MCPClient(profile="full")
    try:
        cf.req("initialize", {"protocolVersion": "2024-11-05"})
        tf = cf.req("tools/list")["result"]["tools"]
        opnames = [t["name"][4:].replace("__", ".", 1) for t in tf
                   if t["name"].startswith("op__")]
        known = set(registry.PRIM_BY_NAME)
        g.add("C12", f"full profile 展开 {len(opnames)} 个底层算子工具且全部可映射回目录",
              len(tf) > 21 and all(n in known for n in opnames),
              {"n_tools": len(tf), "n_ops": len(opnames),
               "unmapped": [n for n in opnames if n not in known][:5]})
    finally:
        cf.close()

    print("=== D. 单一真源与交付物 ===")
    d_tools = penops.tools(profile="capabilities")
    tool_names = {t["name"] for t in d_tools}
    n_tools = len(d_tools)
    expect_names = ({x["id"] for x in registry.CAPABILITIES}
                    | {x["id"] for x in registry.V2_EXTENSIONS}
                    | set(registry.META_BY_ID))
    g.add("D1", "MCP 工具名集合 == L1 能力 + 元工具集合（两层不分叉）",
          tool_names == expect_names,
          {"missing": sorted(expect_names - tool_names),
           "extra": sorted(tool_names - expect_names)})

    # 未装载核验
    user_cfg = os.path.join(os.path.expanduser("~"), ".workbuddy", "mcp.json")
    installed = False
    if os.path.exists(user_cfg):
        try:
            with open(user_cfg, encoding="utf-8") as f:
                installed = "penops" in f.read()
        except OSError:
            pass
    local_cfg = os.path.exists(os.path.join(KIT, "mcp.json"))
    g.add("D2", "MCP 未装载（未写 mcp.json、未注册到 Agent 配置）",
          (not installed) and (not local_cfg),
          {"user_config_has_penops": installed, "local_mcp_json": local_cfg})

    required = ["QUICKSTART.py", "pyproject.toml", "penops/__init__.py",
                "penops/registry.py", "penops/guards.py", "penops/client.py",
                "penops_mcp/server.py", "penops_mcp/mcp.json.example",
                "examples/sdk_basic.py", "examples/mcp_agent.py"]
    missing = [p for p in required if not os.path.exists(os.path.join(KIT, p))]
    g.add("D3", f"{len(required)} 个交付文件齐备", not missing, {"missing": missing})

    # manifest（机器可读清单）
    manifest = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "kit": KIT, "engine_root": ROOT,
        "l1": {"package": "penops", "version": penops.__version__,
               "n_capabilities": len(registry.CAPABILITIES),
               "n_v2_extensions": len(registry.V2_EXTENSIONS),
               "n_primitives": len(registry.PRIMITIVES),
               "capabilities": [x["id"] for x in registry.CAPABILITIES + registry.V2_EXTENSIONS],
               "primitives": [x["name"] for x in registry.PRIMITIVES],
               "r167_aliases": sorted(aliases)},
        "l2": {"package": "penops_mcp", "transport": "stdio",
               "protocol_versions": list(__import__("penops_mcp").PROTOCOL_VERSIONS),
               "installed": False, "profile_default": "capabilities",
               "n_tools": n_tools, "tools": [t["name"] for t in d_tools],
               "config_example": "penops_mcp/mcp.json.example"},
        "guards": {"forbidden_l3_keys": sorted(guards.FORBIDDEN_KEYS),
                   "opt_in_params": sorted(guards.OPT_IN_PARAMS),
                   "caps": guards.CAPS,
                   "batch_range": [guards.BATCH_MIN, guards.BATCH_MAX]},
        "verification": {"pass": g.n_pass, "total": len(g.items),
                         "evidence": "runs/verify_kit.json"},
    }
    os.makedirs(os.path.dirname(EVIDENCE), exist_ok=True)
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    with open(MANIFEST, encoding="utf-8") as f:
        back = json.load(f)
    g.add("D4", "manifest.json 可生成且计数与 registry 一致",
          back["l1"]["n_capabilities"] == 14 and back["l1"]["n_v2_extensions"] == 4
          and back["l1"]["n_primitives"] == len(registry.PRIMITIVES)
          and back["l2"]["n_tools"] == n_tools,
          {"n_tools": back["l2"]["n_tools"], "n_primitives": back["l1"]["n_primitives"]})

    print(f"\n=== 结论：PASS {g.n_pass}/{len(g.items)} ===")
    with open(EVIDENCE, "w", encoding="utf-8") as f:
        json.dump({"verdict": "PASS" if g.ok else "FAIL",
                   "pass": g.n_pass, "total": len(g.items),
                   "items": g.items, "manifest": manifest},
                  f, ensure_ascii=False, indent=2, default=str)
    print(f"证据：{EVIDENCE}")
    return 0 if g.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
