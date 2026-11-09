# -*- coding: utf-8 -*-
"""R145 / D-32 反事实二：pH 降级为**输入**（ph_mode="measured"），86 批全扫。

动机
----
pH 是受控变量：Fa/Fb 是 pH 控制器的输出，不是独立激励。开环回放控制器输出，
等于把控制器的跟踪误差写进 pH 状态。R144 已证这条路径会越出数据从未到过的区间
（实测 pH 上限 6.766，模型到 7.44 并撞上 basic 分支奇点）。

本工具把 pH 每隔 0.2 h 用实测值覆盖，回答：
Q1 其余 81 批的产量是否对 pH 处理方式稳健？（若稳健，说明只有 5 批是"靠钳位达标"）
Q2 那 5 批放开 pH 后真实偏差有多大？
Q3 换成实测 pH 后，模型 pH 的"开环"漂移还有多大（诊断列 pH_openloop）？

用法
----
  python tools/r145_d32_phmode.py --workers 8
"""
import argparse
import json
import os
import sys

import numpy as np

_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(_ROOT, "candidate", "indpensim", "v0.1"))

FOCUS = {37, 50, 51, 91, 92}


def one(batch):
    from golden_params import COMBINED, build_params
    from simulate import simulate_open_loop, yield_metrics

    pr = dict(build_params(COMBINED[batch]))
    pr["ph_mode"] = "measured"
    sim, v3 = simulate_open_loop(batch, pr)
    ym = yield_metrics(sim, v3)
    pho = sim["pH_openloop"].to_numpy(float)
    return {
        "batch": int(batch),
        "yield_err": float(ym["rel_err_total"]) * 100.0,
        "ph_open_max": float(pho.max()),
        "ph_open_min": float(pho.min()),
        "ph_open_clamped": bool(pho.min() < 3.0015),
        "ph_open_end": float(pho[-1]),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--ref", default=os.path.join(_ROOT, "runs", "final_validation_v2.json"))
    ap.add_argument("--out", default=os.path.join(_ROOT, "runs", "p3", "r145_d32_phmode.json"))
    args = ap.parse_args()

    ref = {r["batch"]: r for r in json.load(open(args.ref, encoding="utf-8"))["results"]}
    batches = sorted(ref)

    from multiprocessing import Pool
    with Pool(min(args.workers, os.cpu_count() or 1)) as pool:
        rows = pool.map(one, batches, chunksize=1)

    err_on = np.array([r["yield_err"] for r in rows])
    err_off = np.array([ref[r["batch"]]["yield_err"] * 100.0 for r in rows])
    d = err_on - err_off

    print("=" * 80)
    print(f"{'批':>4} {'yield_off':>10} {'yield_on':>10} {'Δ':>9} | {'pH开环max':>10} {'钳位':>4}")
    for r, i in zip(rows, range(len(rows))):
        star = " ★" if r["batch"] in FOCUS else ""
        print(f"{r['batch']:>4} {err_off[i]:>+10.2f} {r['yield_err']:>+10.2f} {d[i]:>+9.2f} | "
              f"{r['ph_open_max']:>10.3f} {'是' if r['ph_open_clamped'] else '':>4}{star}")
    print("-" * 80)
    keep = [i for i in range(len(rows)) if rows[i]["batch"] not in FOCUS]
    print(f"全 86 批：±5% 命中 {int(np.sum(np.abs(err_on) <= 5.0))}/86，"
          f"RMSE(err) {np.sqrt(np.mean(err_on ** 2)):.3f}%")
    print(f"除 5 批关注外 {len(keep)} 批：±5% 命中 "
          f"{int(np.sum(np.abs(err_on[keep]) <= 5.0))}/{len(keep)}，"
          f"RMSE {np.sqrt(np.mean(err_on[keep] ** 2)):.3f}%，"
          f"max|Δ| {np.max(np.abs(d[keep])):.2f} pt")
    print(f"5 批关注：Δ = {[round(float(d[i]), 2) for i in range(len(rows)) if rows[i]['batch'] in FOCUS]}")
    print(f"开环 pH（未覆盖前的模型自漂移）max 全库 {max(r['ph_open_max'] for r in rows):.3f}；"
          f"仍被钳位 {[r['batch'] for r in rows if r['ph_open_clamped']]}")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    json.dump({"rows": rows}, open(args.out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"落盘 {args.out}")


if __name__ == "__main__":
    main()
