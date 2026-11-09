# -*- coding: utf-8 -*-
"""R133 S1.3 黏度衰减支路校准（vis_decay_rate）。

背景
----
`dy[9] = vis_scale·3·a0^(1/3)·sig(t-t1)·sig(t-t2) − k3·Fw`
原始参数 k2=1e-4、t2=250h，批长仅 202–230h → 第二 sigmoid 全程 ≈0.5 的**常数**，
"衰减支路"名义存在、实际失效。obs 黏度在 156h 达峰后回落（b8：82.2 → 71.2），
而 sim 单调升到 87.5 后持平。

R132 已证否"标度型"（改 vis_scale 会把产量打出 ±5%：86/86 → 63/86）。
本轮改的是**形状**：新增一阶松弛项 `− vis_decay_rate · vis`（默认 0 = 原文行为）。

口径
----
- 误差只用 `Viscosity_offline` 的有效化验点（约 18–21 点/批），时间插值对齐；
  nRMSE = RMSE / mean(obs)（与 D6 同口径）。
- 黏度经 `kla ∝ vis_scaled^(-0.38)` 耦合进供氧 → 生长 → 产量，**必须过产量红线**：
  |Δyield| ≤ 0.2 pt 才接受；否则该批拒绝并登记。
- 单批 1-D 扫描（kd ∈ grid），取 nRMSE 最小者；同时记录产量偏移。

用法
----
python tools/r133_vis_decay_cal.py --batches 8,11,16,27,36,60 --apply
"""
import argparse
import json
import os
import sys
import time

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PKG = os.path.join(ROOT, "candidate", "indpensim", "v0.1")
sys.path.insert(0, PKG)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from golden_params import COMBINED, GOLDEN_ALL, build_params  # noqa: E402
from simulate import simulate_open_loop, yield_metrics  # noqa: E402

GRID = [0.0, 0.0005, 0.001, 0.0015, 0.002, 0.003, 0.004]
YIELD_TOL = 0.2   # pt


def load_v3(b):
    return pd.read_csv(os.path.join(ROOT, "data", "processed", "batches",
                                    f"batch_{b:02d}.csv"))


def load_obs(b):
    df = load_v3(b)
    t = df["time_h"].to_numpy(float)
    v = df["Viscosity_offline"].to_numpy(float)
    m = np.isfinite(t) & np.isfinite(v) & (v > 0)
    return t[m], v[m]


def nrmse_vis(sim, t_obs, v_obs):
    ts = sim["time_h"].to_numpy(float)
    vs = sim["vis"].to_numpy(float)
    if ts[-1] < t_obs[-1] - 1e-6:
        return None
    pred = np.interp(t_obs, ts, vs)
    return float(np.sqrt(np.mean((pred - v_obs) ** 2)) / np.mean(v_obs) * 100.0)


def yield_of(b, kd):
    p = build_params(COMBINED[b])
    if kd:
        p["vis_decay_rate"] = kd
    sim, _ = simulate_open_loop(b, p)
    ym = yield_metrics(sim, load_v3(b))
    return sim, ym


def eval_batch(job):
    """job = (b, grid)。返回逐 kd 的 (nrmse, yield, crash) 表。"""
    b, grid = job
    try:
        t_obs, v_obs = load_obs(b)
        v3 = load_v3(b)
    except FileNotFoundError:
        return b, None
    rows = []
    base_yield = None
    for kd in grid:
        try:
            sim, ym = yield_of(b, kd)
            nr = nrmse_vis(sim, t_obs, v_obs)
            yv = float(ym["rel_err_total"]) * 100.0          # 产量相对误差（pt）
        except Exception as exc:  # noqa: BLE001
            rows.append({"kd": kd, "error": f"{type(exc).__name__}: {exc}"})
            continue
        if kd == 0.0:
            base_yield = yv
        rows.append({"kd": kd, "nrmse": nr, "yield_err_pt": yv,
                     "dyield": None if base_yield is None else yv - base_yield})
    return b, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", default="8,11,16,27,36,60,91,92")
    ap.add_argument("--all", action="store_true", help="跑 GOLDEN_ALL 全量")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--apply", action="store_true", help="把通过守卫的结果写回 COMBINED")
    ap.add_argument("--grid", default=",".join(str(x) for x in GRID))
    args = ap.parse_args()

    grid = [float(x) for x in args.grid.split(",")]
    batches = list(GOLDEN_ALL) if args.all else [int(x) for x in args.batches.split(",")]
    t0 = time.time()

    jobs = [(b, grid) for b in batches]
    if args.workers > 1:
        import multiprocessing as mp
        with mp.Pool(args.workers) as pool:
            results = pool.map(eval_batch, jobs, chunksize=1)
    else:
        results = [eval_batch(j) for j in jobs]

    out = {}
    accepted = {}
    for b, rows in results:
        if not rows:
            continue
        out[b] = rows
        base = rows[0].get("nrmse")
        best = None
        for r in rows:
            if "error" in r or r.get("nrmse") is None:
                continue
            dy = r.get("dyield")
            if r["kd"] == 0.0 or dy is None or abs(dy) > YIELD_TOL:
                continue
            if base is not None and r["nrmse"] < base - 1.0:      # 至少改善 1 pt 才动
                if best is None or r["nrmse"] < best["nrmse"]:
                    best = r
        if best:
            accepted[b] = best

    summary = {
        "grid": grid,
        "yield_tol_pt": YIELD_TOL,
        "n_batches": len(out),
        "n_accepted": len(accepted),
        "base_nrmse_median": float(np.median([rows[0]["nrmse"] for rows in out.values()
                                              if rows[0].get("nrmse") is not None])),
        "accepted_nrmse_median": (float(np.median([a["nrmse"] for a in accepted.values()]))
                                  if accepted else None),
        "elapsed_s": round(time.time() - t0, 1),
    }
    res = {"summary": summary,
           "per_batch": {str(k): v for k, v in out.items()},
           "accepted": {str(k): v for k, v in accepted.items()}}
    p = os.path.join(ROOT, "runs", "p3", "r133_vis_decay.json")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)

    print(json.dumps(summary, ensure_ascii=False, indent=1))
    for b, a in sorted(accepted.items()):
        base = next(r for r in out[b] if r["kd"] == 0.0)
        print(f"  b{b:>3}: kd={a['kd']:.4f}  nRMSE {base['nrmse']:.1f} -> {a['nrmse']:.1f}"
              f"  dyield={a['dyield']:+.2f}pt")
    print("saved", p)

    if args.apply and accepted:
        import io
        gp = os.path.join(PKG, "golden_params.py")
        src = io.open(gp, encoding="utf-8").read()
        print("\n--apply 需要人工确认后写回 COMBINED；本轮仅输出建议，不自动改 SSOT。")


if __name__ == "__main__":
    main()
