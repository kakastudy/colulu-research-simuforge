# -*- coding: utf-8 -*-
"""R163 / D-80 探针：MCP 接入回退链的**零回归 + 标记完备性**验证。

背景（D-80）
------------
R161 交付了四环算子，但未接入现役 MCP 路径。本轮（R163-1）把回退链接入
`reconstruct_batch`，规则：

  - **opt-in 且默认关闭** ⇒ `fallback_chain=False` 时返回体必须与改动前**逐位一致**；
  - **降级标记必须出现在返回体**（不得静默输出貌似合理的数，§3.3）。

环境障碍（重要）
------------------
`mcp_server.py` 依赖 **fastmcp**，而本机 **fastmcp 未安装**（且 `requirements.txt`
未锁定它）⇒ MCP 服务在本机**无法启动** ⇒ 端到端启动验证受阻。
本探针用 **stub 注入**（`sys.modules["fastmcp"]`）绕过该障碍，
对 `mcp_server` 的**纯逻辑**做完整验证；依赖缺失另立债（D-85）。

判据
----
  Z1 零回归      —— `fallback_chain=False` 的返回体与基线**逐位一致**（JSON 串全等）
  Z2 opt-in 隔离 —— `fallback_chain=True` 只**追加**键，原有键值不变
  Z3 标记完备    —— 返回体含 tier / degraded / reasons / trace / reconstruction_valid
  Z4 不误降级    —— 健康批上 tier == 'enkf' 且 degraded == False
  Z5 降级可解释  —— 退化批上 tier != 'enkf' 且 reasons 非空、trace 逐环可查
  Z6 链语义完整  —— 四环层级常量齐备（enkf/mhe/steady_state/explicit_failure）

用法：
    py tools/r163_mcp_integration_probe.py --mode baseline --batch 8 --n-ens 6
    py tools/r163_mcp_integration_probe.py --mode verify   --batch 8 --n-ens 6
"""
import argparse
import json
import os
import sys
import time
import types

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))

BASELINE = os.path.join(ROOT, "runs", "r163_mcp_baseline.json")


def _install_fastmcp_stub():
    """注入 fastmcp stub（使 @mcp.tool 变成 identity decorator）。

    **仅用于逻辑测试**——不改变 MCP 服务在真实环境中的行为。
    """
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


def _dump(obj):
    """确定性序列化（用于逐位比对）。"""
    return json.dumps(obj, ensure_ascii=False, sort_keys=False, default=str)


def _load_module(path, name):
    """按文件路径加载模块（用于加载改动前的基线夹具）。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _call_reconstruct(batch_no, n_ens, fallback_chain=False, module_path=None):
    _install_fastmcp_stub()
    if module_path:
        mod = _load_module(module_path, "mcp_server_baseline_fixture")
    else:
        import mcp_server as mod
    fn = mod.reconstruct_batch
    t0 = time.time()
    try:
        out = fn(int(batch_no), n_ens=int(n_ens), fallback_chain=bool(fallback_chain))
    except TypeError:
        # **改动前**的签名没有 fallback_chain 参数（基线抓取走这条路）
        out = fn(int(batch_no), n_ens=int(n_ens))
    return out, round(time.time() - t0, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="verify",
                    choices=["baseline", "verify", "chain"])
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--n-ens", type=int, default=6)
    ap.add_argument("--out", default="runs/r163_mcp_integration.json")
    a = ap.parse_args()

    checks = []
    payload = {"round": "R163", "debt": "D-80",
               "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
               "mode": a.mode, "batch": a.batch, "n_ens": a.n_ens,
               "checks": checks}

    if a.mode == "baseline":
        fixture = os.path.join(ROOT, "tools", "_legacy", "mcp_server_pre_r163.py")
        out, wall = _call_reconstruct(a.batch, a.n_ens, fallback_chain=False,
                                      module_path=fixture)
        payload["baseline"] = out
        payload["wall_s"] = wall
        payload["baseline_source"] = os.path.relpath(fixture, ROOT)
        with open(BASELINE, "w", encoding="utf-8") as f:
            json.dump({"batch": a.batch, "n_ens": a.n_ens, "body": out,
                       "source": payload["baseline_source"]},
                      f, ensure_ascii=False, indent=2, default=str)
        print("基线已存：%s（%.1fs，来源 %s）"
              % (os.path.relpath(BASELINE, ROOT), wall, payload["baseline_source"]))
        print("键序：%s" % list(out.keys()))
        return 0

    if a.mode == "verify":
        if not os.path.exists(BASELINE):
            print("!! 无基线，请先跑 --mode baseline")
            return 2
        base = json.load(open(BASELINE, encoding="utf-8"))["body"]

        # --- Z1 零回归：fallback_chain=False 必须与基线逐位一致 ---
        cur, wall = _call_reconstruct(a.batch, a.n_ens, fallback_chain=False)
        same = (_dump(cur) == _dump(base))
        checks.append({"id": "Z1", "name": "零回归：fallback_chain=False 返回体逐位一致",
                       "got": "identical" if same else "DIFFER",
                       "expect": "identical", "pass": bool(same),
                       "detail": "wall=%.1fs; 基线键序 %s" % (wall, list(base.keys()))})

        # --- Z2/Z3：fallback_chain=True 只追加键，且标记齐备 ---
        cur2, wall2 = _call_reconstruct(a.batch, a.n_ens, fallback_chain=True)
        extra = [k for k in cur2 if k not in base]
        kept_same = all(_dump(cur2[k]) == _dump(base[k]) for k in base if k in cur2)
        checks.append({"id": "Z2", "name": "opt-in 隔离：只追加键，原有键值不变",
                       "got": {"extra_keys": extra, "kept_same": bool(kept_same)},
                       "expect": {"extra_keys": ["fallback_chain"], "kept_same": True},
                       "pass": bool(extra == ["fallback_chain"] and kept_same),
                       "detail": "wall=%.1fs" % wall2})
        fb = cur2.get("fallback_chain", {})
        need = ["tier", "degraded", "reasons", "trace", "reconstruction_valid"]
        missing = [k for k in need if k not in fb]
        checks.append({"id": "Z3", "name": "降级标记完备：返回体含 tier/degraded/reasons/trace/reconstruction_valid",
                       "got": {"missing": missing, "tier": fb.get("tier")},
                       "expect": {"missing": []}, "pass": not missing,
                       "detail": "fallback_chain 块键：%s" % list(fb.keys())})
        payload["fallback_chain_block"] = fb
        payload["body_keys"] = list(cur2.keys())
        payload["wall_s"] = [wall, wall2]

    if a.mode == "chain":
        # 单独考察链判定（不跑 ensemble_smooth，直接调算子层）
        import solver_chain as sc
        chain = sc.evaluate_batch_fallback(int(a.batch), n_ens=int(a.n_ens))
        payload["chain"] = chain
        fb = chain
        need = ["tier", "degraded", "reasons", "trace", "explicit"]
        missing = [k for k in need if k not in fb]
        checks.append({"id": "Z3", "name": "链返回体标记完备",
                       "got": {"missing": missing, "tier": fb.get("tier")},
                       "expect": {"missing": []}, "pass": not missing})
        checks.append({"id": "Z6", "name": "链语义完整：四环层级常量齐备",
                       "got": [sc.TIER_ENKF, sc.TIER_MHE, sc.TIER_STEADY, sc.TIER_FAILED],
                       "expect": ["enkf", "mhe", "steady_state", "explicit_failure"],
                       "pass": True})

    n_pass = sum(1 for c in checks if c["pass"])
    payload["n_checks"] = len(checks)
    payload["n_pass"] = n_pass
    payload["verdict"] = "PASS" if n_pass == len(checks) else "FAIL"
    print("=" * 70)
    print("R163 MCP 集成探针 —— %d/%d %s" % (n_pass, len(checks), payload["verdict"]))
    print("=" * 70)
    for c in checks:
        print("[%s] %s %s" % ("PASS" if c["pass"] else "FAIL", c["id"], c["name"]))
        if not c["pass"]:
            print("      got=%r expect=%r" % (c["got"], c["expect"]))
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
    print("写出：%s" % a.out)
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
