# -*- coding: utf-8 -*-
"""R146 / D-35：沿已求出的 Gauss-Newton 方向做**阻尼线搜索**（复用已存的一阶步，不重算灵敏度）。

为什么单独一个工具：`r146_ph_ident.py --stage line` 会重算基线+灵敏度（40 次仿真），
而 d1 已经在 `runs/r146_ph_ident.json` 里了。这里只跑线搜索，省一半机时。

回答的问题：**一个全局的 pH 系数修正能走多远？**
  - 走多远还能保持 86 批的 ±5%？
  - 走多远会碰到 b36 的 pH 7.0 悬崖（D-32/D-36 机制）？
  - 即便走到最好的 λ，逐批 pH 偏差还剩多大离散？（若仍跨 0.3 个单位，
    则"全局重标定"在数学上不可能满足全库 —— 这是 D-35 的最终判据）

用法：
  python tools/r146_ph_linesearch.py                      # 10 个干净批，λ=0…1.5
  python tools/r146_ph_linesearch.py --lams 0,0.5,1.0,1.5 --workers 4
  python tools/r146_ph_linesearch.py --batches 8,11,36
"""
import argparse
import contextlib
import io
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))

from r146_ph_ident import (PH_KEYS, _run_task, load_frozen_yield,  # noqa: E402
                           load_params_map, summarise)

SRC = os.path.join(ROOT, "runs", "r146_ph_ident.json")
OUT = os.path.join(ROOT, "runs", "r146_ph_ident_line.json")
CLEAN10 = [8, 11, 16, 22, 23, 27, 36, 55, 60, 80]
ENV_LO, ENV_HI = 5.396, 6.766      # R145 §3 的实测 pH 包络（验证域）


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lams", default="0,0.25,0.5,0.75,1.0,1.25,1.5")
    ap.add_argument("--batches", default="")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    with open(SRC, encoding="utf-8") as f:
        src = json.load(f)
    d_log = np.array(src["stages"]["gn1"]["dlog"], dtype=float)
    base_theta = {k: float(src["theta_base"][k]) for k in PH_KEYS}
    lams = [float(x) for x in args.lams.split(",")]
    batches = [int(x) for x in args.batches.split(",")] if args.batches else CLEAN10

    print(f"源：{os.path.relpath(SRC, ROOT)}")
    print(f"Δ(lnθ) = {dict(zip(PH_KEYS, np.round(d_log, 4)))}")
    print(f"θ_base = { {k: f'{v:.4e}' for k, v in base_theta.items()} }")
    print(f"批 = {batches}   λ = {lams}\n")

    pmap = load_params_map()
    frozen = load_frozen_yield()
    tasks, tmeta = [], []
    for lam in lams:
        th = {k: base_theta[k] * np.exp(lam * d_log[i]) for i, k in enumerate(PH_KEYS)}
        for b in batches:
            tasks.append((b, dict(pmap[b], **th), f"{lam:g}"))
            tmeta.append((lam, b))

    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        rows = list(ex.map(_run_task, tasks))
    by = {}
    for (lam, b), r in zip(tmeta, rows):
        by.setdefault(f"{lam:g}", {})[b] = r

    # 口径闸门：λ=0 必须与冻结基准逐批一致（无 λ=0 时退化为不检查并显式说明）
    if "0" in by:
        g0 = by["0"]
        dmax = max(abs(g0[b]["yield_err"] - frozen[b]) for b in batches if b in frozen)
        print(f"[口径闸门] λ=0 与冻结基准 max|Δyield_err| = {dmax:.3e}")
        if dmax > 1e-9:
            raise SystemExit("λ=0 未能复现冻结基准，先修口径")
    else:
        dmax = float("nan")
        print("[口径闸门] 未包含 λ=0，跳过基准对账")

    print(f"\n{'λ':>5s} {'pH_RMSE':>8s} {'偏差':>8s} {'±5%':>7s} {'max|err|':>9s} "
          f"{'钳位':>5s} {'≥7':>4s} {'maxpH':>7s} {'偏差跨度':>9s}")
    table = []
    for lam in lams:
        rs = [by[f"{lam:g}"][b] for b in batches]
        _buf = io.StringIO()
        with contextlib.redirect_stdout(_buf):
            s = summarise(rs, f"λ={lam:g}")
        nclamp = sum(r["n_clamp"] for r in rs)
        nover = sum(r["n_over7"] for r in rs)
        phmax = max(r["ph_max"] for r in rs)
        biases = np.array([np.mean(r["resid"]) for r in rs])
        spread = float(biases.max() - biases.min())
        print(f"{lam:>5.2f} {s['ph_rmse']:>8.4f} {s['ph_bias']:>+8.4f} "
              f"{s['within5']:>3d}/{s['n']:<3d} {s['yield_max']:>9.2%} "
              f"{nclamp:>5d} {nover:>4d} {phmax:>7.3f} {spread:>9.4f}")
        table.append({"lam": lam, **s, "n_clamp": nclamp, "n_over7": nover,
                      "ph_max": phmax, "bias_spread": spread,
                      "per_batch_bias": {int(r["batch"]): float(np.mean(r["resid"])) for r in rs},
                      "per_batch_yield": {int(r["batch"]): r["yield_err"] for r in rs},
                      "per_batch_phmax": {int(r["batch"]): r["ph_max"] for r in rs}})

    best = min(table, key=lambda t: t["ph_rmse"])
    print(f"\n[最优 RMSE] λ={best['lam']:g} → pH RMSE {best['ph_rmse']:.4f}、"
          f"偏差 {best['ph_bias']:+.4f}、±5% {best['within5']}/{best['n']}、"
          f"逐批偏差仍跨 {best['bias_spread']:.4f}")
    ok = [t for t in table if t["n_clamp"] == 0 and t["n_over7"] == 0
          and t["ph_max"] <= ENV_HI and t["within5"] == t["n"]]
    print(f"[可行 λ] 无钳位/无≥7/不出包络/全批 ±5%：{[t['lam'] for t in ok] or 'none'}")
    if ok:
        print(f"         其中 RMSE 最小者 λ={min(ok, key=lambda t: t['ph_rmse'])['lam']:g}")

    out = {"src": os.path.relpath(SRC, ROOT), "dlog": d_log.tolist(),
           "theta_base": base_theta, "batches": batches, "table": table,
           "best_lambda": best["lam"], "admissible": [t["lam"] for t in ok],
           "gate_max_abs_delta": dmax}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"\n写出 {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
