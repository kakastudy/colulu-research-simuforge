# -*- coding: utf-8 -*-
"""S0.1 行为验证：MCP / dashboard / observe 走的 calib_params 路径，合并后变了多少。

黄金回归走的是 `golden_params.COMBINED`，S0.1 对它**零影响**（已逐批验证：
86 批 yield_err 与冻结副本差异 0.000e+00）。真正会变的是另一条路径——
`calibration.calib_params()`，它服务 MCP `golden_set_validate`、dashboard、
observe、optimize 等 8 个模块。

本脚本对 13 批历史校准批，同时用"合并前（CAL_LEGACY + PAA_CAL update）"与
"合并后（COMBINED + PAA 白名单补缺）"两套参数各仿真一次，输出产量偏差对比。
这样"合并到底改变了什么"是可量化的，而不是一句"应该没影响"。

用法：
    python tools/r132_mcp_path_check.py                 # 13 批
    python tools/r132_mcp_path_check.py --batches 8,27  # 指定
"""
import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))
sys.path.insert(0, HERE)

from simulate import simulate_open_loop, yield_metrics, classify_crash  # noqa: E402
from calibration import calib_params, calib_params_legacy, GOLDEN  # noqa: E402


def run_one(job):
    b, which = job
    params = calib_params(b) if which == "now" else calib_params_legacy(b)
    v3 = pd.read_csv(os.path.join(ROOT, "data", "processed", "batches", f"batch_{b:02d}.csv"))
    sim, _ = simulate_open_loop(b, params)
    ym = yield_metrics(sim, v3)
    err = float(ym["rel_err_total"])
    level, _ = classify_crash(sim, yield_err=err)
    return {"batch": b, "which": which, "yield_err": err,
            "crash": level, "n_keys": len(params)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", default="")
    ap.add_argument("--out", default=os.path.join(ROOT, "runs", "p3", "r132_mcp_path.json"))
    args = ap.parse_args()
    batches = ([int(x) for x in args.batches.split(",")] if args.batches else list(GOLDEN))

    jobs = [(b, w) for b in batches for w in ("legacy", "now")]
    from multiprocessing import Pool
    with Pool(min(8, os.cpu_count() or 1)) as pool:
        res = pool.map(run_one, jobs, chunksize=1)

    d = {}
    for r in res:
        d.setdefault(r["batch"], {})[r["which"]] = r

    print("=" * 84)
    print("S0.1 行为验证：calib_params 路径（MCP / dashboard / observe）合并前后")
    print("=" * 84)
    print(f"{'b':>3s} {'合并前':>9s} {'合并后':>9s} {'Δpt':>7s}  {'分级':>12s}")
    print("-" * 84)
    rows, drifts = [], []
    for b in batches:
        L, N = d[b]["legacy"], d[b]["now"]
        dl = (N["yield_err"] - L["yield_err"]) * 100
        rows.append({"batch": b, "legacy_err": L["yield_err"], "now_err": N["yield_err"],
                     "delta_pt": dl, "legacy_crash": L["crash"], "now_crash": N["crash"],
                     "legacy_keys": L["n_keys"], "now_keys": N["n_keys"]})
        flag = ""
        if abs(dl) > 1.0:
            flag = "  ← 显著"
            drifts.append(b)
        if L["crash"] != N["crash"]:
            flag += "  [分级变化]"
        print(f"{b:>3d} {L['yield_err']*100:>8.2f}% {N['yield_err']*100:>8.2f}% "
              f"{dl:>+7.2f}  {L['crash']:>6s}→{N['crash']:<6s}{flag}")

    rmse_l = float(np.sqrt(np.mean([r["legacy_err"] ** 2 for r in rows])))
    rmse_n = float(np.sqrt(np.mean([r["now_err"] ** 2 for r in rows])))
    within_l = sum(1 for r in rows if abs(r["legacy_err"]) <= 0.05)
    within_n = sum(1 for r in rows if abs(r["now_err"]) <= 0.05)
    print("-" * 84)
    print(f"  RMSE  合并前 {rmse_l*100:.2f}%  →  合并后 {rmse_n*100:.2f}%")
    print(f"  ±5% 内  {within_l}/{len(rows)}  →  {within_n}/{len(rows)}")
    print(f"  |Δ|>1pt 的批：{drifts if drifts else '无'}")

    out = {"batches": rows,
           "rmse_legacy": rmse_l, "rmse_now": rmse_n,
           "within5_legacy": within_l, "within5_now": within_n,
           "significant_drift": drifts}
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"\nSaved: {args.out}")


if __name__ == "__main__":
    main()
