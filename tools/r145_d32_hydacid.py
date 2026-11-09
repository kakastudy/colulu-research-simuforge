# -*- coding: utf-8 -*-
"""R145 / D-32 反事实实验：把产品水解通道在 pH 方程里的符号翻正。

假设
----
`model.rhs` 的 pH 方程里，`r_p` 整体乘 `gamma1`。而 `r_p = 产素 - mu_h·P`，
所以水解项 `mu_h·P` 在 pH 方程里是**碱化**贡献。青霉素 G 水解生成青霉噻唑酸
（一元羧酸）应当**产酸**。`ph_hyd_acid=True` 把该通道翻正。

本工具回答
----------
Q1 翻正后，5 批钳位批的 pH 是否回到 [5.0, 6.8]？
Q2 对全 86 批的产量有什么代价？（yield_err 分布、±5% 命中数）
Q3 pH 轨迹相对数据的 RMSE 是变好还是变坏？（判据不是"更好看"，是"更接近实测"）

用法
----
  python tools/r145_d32_hydacid.py --workers 8
"""
import argparse
import json
import os
import sys

import numpy as np

_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(_ROOT, "candidate", "indpensim", "v0.1"))

CLAMP_PH = 3.0015  # 守卫 0.001 → pH 3.000，容许 1e-3 的数值抖动


def one(batch):
    from golden_params import COMBINED, build_params
    from simulate import simulate_open_loop, yield_metrics, trajectory_metrics

    pr = dict(build_params(COMBINED[batch]))
    pr["ph_hyd_acid"] = True
    sim, v3 = simulate_open_loop(batch, pr)
    ym = yield_metrics(sim, v3)
    tm = trajectory_metrics(sim, v3, channels=("pH",))
    ph = sim["pH"].to_numpy(float)
    return {
        "batch": int(batch),
        "yield_err": float(ym["rel_err_total"]) * 100.0,
        "ph_max": float(ph.max()),
        "ph_end": float(ph[-1]),
        "ph_rmse": float(tm["pH"]["rmse"]),
        "ph_over7": int(np.sum(ph > 7.0)),
        "clamped": bool(ph.min() < CLAMP_PH),
        "ph_min": float(ph.min()),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--ref", default=os.path.join(_ROOT, "runs", "final_validation_v2.json"))
    ap.add_argument("--out", default=os.path.join(_ROOT, "runs", "p3", "r145_d32_hydacid.json"))
    args = ap.parse_args()

    ref = {r["batch"]: r for r in json.load(open(args.ref, encoding="utf-8"))["results"]}
    batches = sorted(ref)

    from multiprocessing import Pool
    with Pool(min(args.workers, os.cpu_count() or 1)) as pool:
        rows = pool.map(one, batches, chunksize=1)

    err_off = np.array([ref[r["batch"]]["yield_err"] * 100.0 for r in rows])
    err_on = np.array([r["yield_err"] for r in rows])
    d = err_on - err_off

    print("=" * 92)
    print(f"{'批':>4} {'yield_off':>10} {'yield_on':>10} {'Δ':>8} | {'pHmax_off':>9} "
          f"{'pHmax_on':>9} {'pH末_on':>8} {'pH_RMSE_on':>10} {'钳位':>4}")
    for r in rows:
        b = r["batch"]
        flag = "★" if (abs(d[batches.index(b)]) > 5.0 or r["clamped"]) else " "
        print(f"{b:>4} {err_off[batches.index(b)]:>+10.2f} {r['yield_err']:>+10.2f} "
              f"{d[batches.index(b)]:>+8.2f} | {ref[b]['ph_end']:>9.3f} "
              f"{r['ph_max']:>9.3f} {r['ph_end']:>8.3f} {r['ph_rmse']:>10.3f} "
              f"{'是' if r['clamped'] else '':>4}{flag}")

    n_in = int(np.sum(np.abs(err_on) <= 5.0))
    print("-" * 92)
    print(f"开关 OFF：±5% 命中 {int(np.sum(np.abs(err_off) <= 5.0))}/86，"
          f"RMSE(err) {np.sqrt(np.mean(err_off ** 2)):.3f}%，max|err| {np.max(np.abs(err_off)):.2f}%")
    print(f"开关 ON ：±5% 命中 {n_in}/86，"
          f"RMSE(err) {np.sqrt(np.mean(err_on ** 2)):.3f}%，max|err| {np.max(np.abs(err_on)):.2f}%")
    print(f"Δyield 最大 {np.max(np.abs(d)):.2f} pt；超 ±5pt 的批 "
          f"{[rows[i]['batch'] for i in range(len(rows)) if abs(d[i]) > 5.0]}")
    print(f"ON 时仍被钳位：{[r['batch'] for r in rows if r['clamped']]}")
    print(f"ON 时 pH 越 7 的批：{[r['batch'] for r in rows if r['ph_max'] > 7.0]}")

    # 与 OFF 臂的 pH_max 对照（OFF 来自 r145_d32_scan_all86.json）
    scan_p = os.path.join(_ROOT, "runs", "p3", "r145_d32_scan_all86.json")
    if os.path.exists(scan_p):
        scan = {r["batch"]: r for r in json.load(open(scan_p, encoding="utf-8"))}
        over_off = [b for b in batches if scan.get(b, {}).get("ph_max", 0) > 7.0]
        over_on = [r["batch"] for r in rows if r["ph_max"] > 7.0]
        clamp_off = [b for b in batches if scan.get(b, {}).get("first_clamp_t") is not None]
        pmax_off = np.array([scan[b]["ph_max"] for b in batches if b in scan])
        pmax_on = np.array([r["ph_max"] for r in rows])
        print(f"pH_max>7 ：OFF {len(over_off)} 批 {over_off} → ON {len(over_on)} 批 {over_on}")
        print(f"被钳位  ：OFF {len(clamp_off)} 批 {clamp_off} → "
              f"ON {len([r for r in rows if r['clamped']])} 批")
        print(f"pH_max 均值 {pmax_off.mean():.3f} → {pmax_on.mean():.3f}，"
              f"max {pmax_off.max():.3f} → {pmax_on.max():.3f}")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    json.dump({"rows": rows}, open(args.out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"落盘 {args.out}")


if __name__ == "__main__":
    main()
