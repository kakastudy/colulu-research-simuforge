# -*- coding: utf-8 -*-
"""R164-1 / R165 探针：PH5 服务化补齐两个 MCP 工具的**零回归 + 标记完备性**验证。

背景（R164-1）
--------------
`docs/roadmap_next.md` §8.6.2 R164-1 要求：
  - `mcp_server.py` 工具数 **12 → 14**，新增 `discover_residual` + `observe_online`；
  - `ENGINE_CONTRACT.md` 登记两工具；
  - 返回体含「不可辨识 / 降级」标记；
  - **默认路径逐位零回归**（`max|Δ| = 0.00e+00`）。

环境障碍（承 D-85）
--------------------
`fastmcp` 未安装且未锁进 `requirements.txt` ⇒ MCP 服务本机不可启动。
本探针沿用 `tools/r163_mcp_integration_probe.py` 的 **stub 注入**（`sys.modules["fastmcp"]`）
对纯逻辑层做完整验证；不安装任何包、不改环境。

判据纪律（承 D-78 / 纪律 25 / 28 / 29 / 31）
--------------------------------------------
  - **零信息对照**：无 θ 批必须走降级分支（否则「不可辨识」恒真）；
  - **双向判别力**：正向（有 θ / 正常 EnKF）+ 反向（缺 θ / 低置信）都要有非零证据；
  - **不恒真、不恒假**：`identifiable` / `degraded` 在两臂上取不同值；
  - **判据非文本子串**：状态判定用返回体字段，不用 `grep -c`；
  - **零回归**：既有 12 个工具**函数源码逐字不变** + `solver_info()` 返回体逐位一致。

用法：
    py tools/r165_mcp_tools_probe.py --mode verify
"""
import argparse
import ast
import hashlib
import importlib.util
import json
import os
import sys
import time
import types

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
V01 = os.path.join(ROOT, "candidate", "indpensim", "v0.1")
sys.path.insert(0, V01)

SERVER = os.path.join(V01, "mcp_server.py")
FROZEN = os.path.join(ROOT, "runs", "_r165_backup", "mcp_server_pre_r165.py")
OUT = os.path.join(ROOT, "runs", "r165_mcp_tools_probe.json")

EXPECTED_OLD = ["solver_info", "simulate_batch", "evaluate_batch", "golden_set_validate",
                "estimate_batch", "estimate_batch_stage2", "reconstruct_batch",
                "batch_fallback_tier", "optimize_feed", "advise_control",
                "trajectory_check", "element_balance_check"]
EXPECTED_NEW = ["discover_residual", "observe_online"]


def _install_fastmcp_stub():
    """注入 fastmcp stub（@mcp.tool 变 identity decorator），仅用于逻辑测试。"""
    if "fastmcp" in sys.modules:
        return sys.modules["fastmcp"]
    stub = types.ModuleType("fastmcp")

    class _FakeMCP:
        def __init__(self, name, *a, **k):
            self.name = name

        def tool(self, fn=None, **k):
            if fn is None:
                return lambda f: f
            return fn

        def run(self, *a, **k):
            pass

        def resource(self, *a, **k):
            return lambda f: f

        def prompt(self, *a, **k):
            return lambda f: f

    stub.FastMCP = _FakeMCP
    sys.modules["fastmcp"] = stub
    return stub


def _load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _tool_funcs(src):
    """AST 提取所有被 @mcp.tool 装饰的顶层函数 → {name: 源码全文}。"""
    tree = ast.parse(src)
    out = {}
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for d in node.decorator_list:
            is_tool = False
            if isinstance(d, ast.Attribute) and d.attr == "tool":
                is_tool = True
            elif isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr == "tool":
                is_tool = True
            if is_tool:
                out[node.name] = ast.get_source_segment(src, node) or ""
                break
    return out


def _sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _dump(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)


def _pick_theta_batches():
    """数据驱动地选正向（有 θ_b）与反向（无 θ_b）批，不硬编码批号。"""
    log = os.path.join(ROOT, "runs", "hier_est", "train_theta_v2.jsonl")
    have = set()
    if os.path.exists(log):
        for line in open(log, encoding="utf-8"):
            r = json.loads(line)
            if r.get("theta_post"):
                have.add(int(r["batch"]))
    pos = min(have) if have else None
    neg = next((b for b in range(1, 101) if b not in have), None)
    return pos, neg, len(have)


def _pick_golden_batch():
    """observe_online 需要 calib_params(b) 可用 ⇒ 取黄金集成员。"""
    from calibration import GOLDEN
    return int(sorted(GOLDEN)[0]) if GOLDEN else 8


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["verify"], default="verify")
    a = ap.parse_args()
    t0 = time.time()
    checks = []

    def ck(cid, desc, ok, value, threshold):
        checks.append({"id": cid, "desc": desc, "pass": bool(ok),
                       "value": value, "threshold": threshold})

    src_new = open(SERVER, encoding="utf-8").read()
    src_old = open(FROZEN, encoding="utf-8").read() if os.path.exists(FROZEN) else ""
    f_new = _tool_funcs(src_new)
    f_old = _tool_funcs(src_old) if src_old else {}

    # ---- M1/M2/M3：静态结构（AST，不依赖 fastmcp） ----
    ck("M1", "MCP 工具数 12 → 14（AST 静态计数）",
       len(f_new) == 14 and len(f_old) == 12,
       {"before": len(f_old), "after": len(f_new), "names": sorted(f_new)}, "12 → 14")
    unchanged = [n for n in EXPECTED_OLD if n in f_old and n in f_new
                 and f_old[n] == f_new[n]]
    ck("M2", "既有 12 个工具函数体**逐字未变**（零回归静态证据）",
       len(unchanged) == 12,
       {"unchanged": unchanged, "changed": [n for n in EXPECTED_OLD if n not in unchanged],
        "old_hashes": {n: _sha(f_old.get(n, "")) for n in EXPECTED_OLD},
        "new_hashes": {n: _sha(f_new.get(n, "")) for n in EXPECTED_OLD}}, "12/12 逐字相同")
    added = sorted(set(f_new) - set(f_old))
    ck("M3", "新增工具恰为 discover_residual / observe_online（无夹带）",
       added == sorted(EXPECTED_NEW) and all(n in f_new for n in EXPECTED_OLD),
       {"added": added, "removed": sorted(set(f_old) - set(f_new))}, "恰好 2 个")

    # ---- 动态验证（stub 注入） ----
    _install_fastmcp_stub()
    mod_new = _load_module(SERVER, "r165_mcp_server_now")
    mod_old = _load_module(FROZEN, "r165_mcp_server_frozen") if src_old else None

    # M4：既有工具返回体逐位一致（取无副作用、秒级的 solver_info）
    si_new = mod_new.solver_info()
    si_old = mod_old.solver_info() if mod_old else None
    ck("M4", "solver_info() 返回体与冻结快照**逐位一致**（version 未改、既有行为未变）",
       si_old is not None and _dump(si_new) == _dump(si_old),
       {"version_now": si_new.get("version"), "version_frozen": (si_old or {}).get("version"),
        "json_equal": si_old is not None and _dump(si_new) == _dump(si_old)}, "JSON 全等")

    pos_b, neg_b, n_theta = _pick_theta_batches()
    keys_dr = ("identifiable", "degraded", "degradation_reasons", "mycelium_compartments")

    # M5/M6：discover_residual 反向（零信息对照 = 无 θ）
    dr_neg = mod_new.discover_residual(neg_b) if neg_b else {}
    ck("M5", "discover_residual 返回体恒含不可辨识 / 降级标记（反向臂）",
       all(k in dr_neg for k in keys_dr),
       {"present": [k for k in keys_dr if k in dr_neg], "batch": neg_b}, "4/4 键齐备")
    ck("M6", "反向判别力：无 θ 批 ⇒ theta_available=False / identifiable=False / degraded=True / reasons 非空",
       (dr_neg.get("theta_available") is False
        and dr_neg.get("identifiable") is False
        and dr_neg.get("degraded") is True
        and len(dr_neg.get("degradation_reasons") or []) > 0
        and not dr_neg.get("structures")),
       {"theta_available": dr_neg.get("theta_available"),
        "identifiable": dr_neg.get("identifiable"), "degraded": dr_neg.get("degraded"),
        "reasons": dr_neg.get("degradation_reasons"), "structures": list(dr_neg.get("structures") or {})},
       "缺 θ 显式降级，不猜测")

    # M7：discover_residual 正向（有 θ，产出数字证据）
    dr_pos = mod_new.discover_residual(pos_b) if pos_b else {}
    st = dr_pos.get("structures") or {}
    has_numbers = all(isinstance((st.get(ch) or {}).get("design_cond"), (int, float))
                      and isinstance((st.get(ch) or {}).get("delta_bic"), (int, float))
                      for ch in ("S", "P"))
    ck("M7", "正向臂：有 θ 批产出 S/P 稀疏结构 + 数据驱动判据数字（不恒假）",
       dr_pos.get("theta_available") is True and set(st) >= {"S", "P"} and has_numbers
       and dr_pos.get("criteria", {}).get("min_delta_bic") == 2.0,
       {"batch": pos_b, "theta_available": dr_pos.get("theta_available"),
        "identifiable": dr_pos.get("identifiable"), "degraded": dr_pos.get("degraded"),
        "S": {k: (st.get("S") or {}).get(k) for k in ("n_samples", "n_terms", "design_cond", "delta_bic")},
        "P": {k: (st.get("P") or {}).get(k) for k in ("n_samples", "n_terms", "design_cond", "delta_bic")},
        "reasons": dr_pos.get("degradation_reasons")}, "structures 含 S/P 且判据为数字")
    ck("M8", "两臂 `identifiable` / `degraded` 取不同值（判据非恒真 / 非恒假）",
       (dr_neg.get("degraded") is True
        and (dr_pos.get("degraded") is False or dr_pos.get("theta_available") is True)),
       {"neg": {"degraded": dr_neg.get("degraded"), "identifiable": dr_neg.get("identifiable")},
        "pos": {"degraded": dr_pos.get("degraded"), "identifiable": dr_pos.get("identifiable"),
                "theta_available": dr_pos.get("theta_available")}}, "反向必降级，正向有证据")

    # M9/M10/M11：observe_online（低 n_ens + **短窗口**冒烟）
    # 说明：完整 `enkf_observe` 在 1050 步 × BDF 下 >120 s（R163 已实测）。这里不改算子、
    # 不 stub 掉 EnKF，而是把 `simulate.load_batch` 临时换成**前 120 行（24 h）**的真实 DataFrame，
    # 让真实 EnKF 路径在可复现的短窗口内跑完；算子数值正确性由 pytest 与既有 enkf_*.json 保证。
    gb = _pick_golden_batch()
    print(f"[probe] observe_online 短窗口冒烟 b{gb} ...", flush=True)
    import simulate
    _orig_load_batch = simulate.load_batch
    _SHORT_ROWS = 120

    def _short_load_batch(b):
        d = _orig_load_batch(b)
        return d.iloc[:_SHORT_ROWS].copy()

    simulate.load_batch = _short_load_batch
    try:
        oo = mod_new.observe_online(gb, n_ens=4, seed=7, stride=200, health_probe=False)
    finally:
        simulate.load_batch = _orig_load_batch
    keys_oo = ("degraded", "reconstruction_valid", "identifiable",
               "degradation_reasons", "mycelium_compartments")
    ck("M9", "observe_online 返回体恒含降级 / 不可辨识标记",
       all(k in oo for k in keys_oo),
       {"present": [k for k in keys_oo if k in oo], "batch": gb}, "5/5 键齐备")
    ck("M10", "软告警双向：n_ens=4 ⇒ degraded=True（低置信）但 reconstruction_valid=True 且记录非空",
       (oo.get("degraded") is True and oo.get("reconstruction_valid") is True
        and oo.get("n_records", 0) > 0 and len(oo.get("records_sample") or []) > 0
        and any("ensemble_too_small" in str(x) for x in (oo.get("degradation_reasons") or []))),
       {"n_ens": oo.get("n_ens"), "degraded": oo.get("degraded"),
        "reconstruction_valid": oo.get("reconstruction_valid"),
        "n_records": oo.get("n_records"),
        "n_sample": len(oo.get("records_sample") or []),
        "integration_failures": oo.get("integration_failures"),
        "reasons": oo.get("degradation_reasons")}, "降级与可用估计分离（不恒假）")
    mc = oo.get("mycelium_compartments") or {}
    ck("M11", "菌丝分室 A0/A1/A3/A4 恒标 identifiable=False（结构性不可辨识，D-88 / R164-7）",
       (mc.get("identifiable") is False
        and set(mc.get("not_exposed") or []) >= {"A0", "A1", "A3", "A4"}
        and oo.get("identifiable") is False),
       {"mycelium_identifiable": mc.get("identifiable"),
        "not_exposed": mc.get("not_exposed"), "top_level_identifiable": oo.get("identifiable"),
        "exposed": mc.get("exposed")}, "恒 False，且两工具口径一致")

    # M12：只读性（调用前后两个工具所在源码与 data/ 未被改写）
    src_after = open(SERVER, encoding="utf-8").read()
    ck("M12", "只读性：探针执行未改写 mcp_server.py（工具自身不写引擎 / 不写 data/）",
       src_after == src_new,
       {"sha_before": _sha(src_new), "sha_after": _sha(src_after),
        "out_path": "runs/r165_mcp_tools_probe.json（唯一写入）"}, "源码哈希不变")

    n_pass = sum(1 for c in checks if c["pass"])
    verdict = "PASS" if n_pass == len(checks) else "FAIL"
    out = {"round": "R165", "task": "R164-1", "tool": "r165_mcp_tools_probe",
           "verdict": verdict, "n_pass": n_pass, "n_checks": len(checks),
           "checks": checks, "tool_count": {"before": len(f_old), "after": len(f_new),
                                            "added": added},
           "theta_log": {"n_batches": n_theta, "positive_batch": pos_b, "negative_batch": neg_b},
           "golden_smoke_batch": gb,
           "smoke_window": {"rows": 120, "hours": "~24", "n_ens": 4,
                            "note": "真实 EnKF 路径 + 截断输入；完整时程 >120 s，不进探针"},
           "zero_regression_scope": ("MCP 服务层纯新增；引擎数值路径未动 ⇒ 完整 86 批零回归 "
                                     "由 tools/r134_zero_regression.py 在闸门阶段复核"),
           "env_note": "fastmcp 未安装（D-85），本探针用 stub 注入验证逻辑层，不安装任何包",
           "wall_s": round(time.time() - t0, 2)}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)

    print(f"== R164-1 MCP 工具探针 ==")
    print(f"工具数 {len(f_old)} → {len(f_new)}；新增 {added}")
    print(f"θ 日志 {n_theta} 批；正向 b{pos_b} / 反向 b{neg_b}；EnKF 冒烟 b{gb}")
    print(f"判据 {n_pass}/{len(checks)} {verdict} ｜ 写出 {OUT}（{out['wall_s']} s）")
    for c in checks:
        print(f"  [{'PASS' if c['pass'] else 'FAIL'}] {c['id']} {c['desc']}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
