# -*- coding: utf-8 -*-
"""r141_analyse.py — D-8 的两项补充证据（跑在 r141_death_mode.py 之后）。

Part A `frontier`：从 `runs/p3/r141_death_mode.json` 计算「X 改善—产量代价」前沿。
    只统计 ΔX ≥ 5pt 的点（否则谈不上"修好 X"），按臂聚合"每 10pt X 的 Δyield"。
    判据：形态学链有价值 ⟺ 同等 ΔX 下产量代价更小。

Part B `limit`：验证形态学链的**退化极限**。
    稳态下死菌池 ≈ (age/lysis)·a1，X 的下降速率 ≈ age·a1（与溶菌速率无关）。
    ⇒ lysis→∞ 时死菌池→0，机制退化为"按 age 移除 a1"（等比衰亡的 a1 特例）；
      有限 lysis 时严格更差：产素代价立即发生（a1 先掉），X 的下降被 1/lysis 滞后，
      且死菌池本身仍计入 X ⇒ X 先被抬高。
    本 Part 用 age 固定、lysis 从 0.01 扫到 1.0 验证该收敛。

用法
----
    python tools/r141_analyse.py --part all
    python tools/r141_analyse.py --part limit --batches 8 29 56
"""
import argparse
import json
import os
import sys

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))

SRC = os.path.join(ROOT, "runs", "p3", "r141_death_mode.json")
OUT_F = os.path.join(ROOT, "runs", "p3", "r141_frontier.json")
OUT_L = os.path.join(ROOT, "runs", "p3", "r141_lysis_limit.json")


def part_frontier():
    d = json.load(open(SRC, encoding="utf-8"))
    rows = d["rows"]
    base = {r["b"]: r for r in rows if r["cfg"] == "base"}
    arms = [t for t, _ in d["meta"]["configs"][1:]]

    pts = []
    for b in d["meta"]["batches"]:
        for tag in arms:
            r = next(x for x in rows if x["b"] == b and x["cfg"] == tag)
            dX = base[b]["X_nrmse"] - r["X_nrmse"]
            dY = r["yield_err"] - base[b]["yield_err"]
            pts.append({"b": b, "cfg": tag, "arm": tag.split("_")[0],
                        "dX": dX, "dY": dY, "debris": r["debris_frac"],
                        "X_nrmse": r["X_nrmse"], "yield_err": r["yield_err"]})

    qual = [p for p in pts if p["dX"] >= 5.0]
    print("=" * 92)
    print(f"Part A　前沿：{len(pts)} 个配置点，其中 ΔX ≥ 5pt 的 {len(qual)} 个")
    print("=" * 92)
    print(f"{'臂':<8}{'n':>4}{'ΔX 中位':>10}{'ΔX 最大':>10}{'Δyield 中位':>12}"
          f"{'每10pt X 的Δyield 中位':>22}{'debris 中位':>12}")
    summ = {}
    for arm in ("prop", "morph"):
        sub = [p for p in qual if p["arm"] == arm]
        if not sub:
            continue
        per = [p["dY"] / p["dX"] * 10.0 for p in sub]
        s = {"n": len(sub),
             "dX_med": float(np.median([p["dX"] for p in sub])),
             "dX_max": float(np.max([p["dX"] for p in sub])),
             "dY_med": float(np.median([p["dY"] for p in sub])),
             "per10_med": float(np.median(per)),
             "debris_med": float(np.median([p["debris"] for p in sub]))}
        summ[arm] = s
        print(f"{arm:<8}{s['n']:>4}{s['dX_med']:>+10.1f}{s['dX_max']:>+10.1f}"
              f"{s['dY_med']:>+12.2f}{s['per10_med']:>+22.2f}{s['debris_med']:>11.1f}%")

    print("\n逐点（ΔX ≥ 5pt，按批）：")
    for p in sorted(qual, key=lambda z: (z["b"], z["arm"], -z["dX"])):
        print(f"  b{p['b']:<3d} {p['arm']:<6s} {p['cfg']:<14s}"
              f" ΔX {p['dX']:+6.1f}pt  Δyield {p['dY']:+7.2f}pt"
              f"  debris {p['debris']:5.1f}%")

    # 覆盖面上限：两臂各自能达到的最大 ΔX
    print("\n覆盖上限（X 最多能修多少）：")
    for arm in ("prop", "morph"):
        sub = [p for p in pts if p["arm"] == arm]
        best = max(sub, key=lambda z: z["dX"])
        print(f"  {arm:<6s} 最大 ΔX {best['dX']:+6.1f}pt（b{best['b']} {best['cfg']}，"
              f"debris {best['debris']:.1f}%，Δyield {best['dY']:+.2f}pt）")

    json.dump({"meta": {"src": os.path.relpath(SRC, ROOT), "qual_dx": 5.0},
               "summary": summ, "points": pts},
              open(OUT_F, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n已写入 {os.path.relpath(OUT_F, ROOT)}")
    return summ


def _one(args):
    b, age, lysis = args
    import pandas as pd
    from golden_params import COMBINED, build_params
    from simulate import simulate_open_loop, yield_metrics

    v3 = pd.read_csv(os.path.join(ROOT, "data", "processed", "batches", f"batch_{b:02d}.csv"))
    p = dict(build_params(COMBINED[b]))
    p.update({"death_mode": 1, "age_start": 144.0, "age_rate": age,
              "lysis_rate": lysis, "lysis_recycle": 0.5})
    sim, _ = simulate_open_loop(b, params=p)
    ym = yield_metrics(sim, v3)
    dead = float(sim["A3"].iloc[-1]) + float(sim["A4"].iloc[-1])
    Xe = float(sim["X"].iloc[-1])
    return {"b": int(b), "age": age, "lysis": lysis,
            "X_end": Xe, "P_end": float(sim["P"].iloc[-1]),
            "yield_err": 100.0 * float(ym["rel_err_total"]),
            "dead_pool": dead, "debris_frac": 100.0 * dead / Xe if Xe > 1e-9 else float("nan")}


def part_limit(batches, age=0.010, lysis_list=(0.01, 0.05, 0.20, 1.00)):
    import pandas as pd
    from golden_params import COMBINED, build_params
    from simulate import simulate_open_loop, yield_metrics
    from multiprocessing import Pool

    jobs = [(b, age, l) for b in batches for l in lysis_list]
    with Pool(min(8, os.cpu_count() or 1)) as pool:
        rows = pool.map(_one, jobs, chunksize=1)

    # 基线（用于对比）
    baselines = {}
    for b in batches:
        v3 = pd.read_csv(os.path.join(ROOT, "data", "processed", "batches", f"batch_{b:02d}.csv"))
        sim, _ = simulate_open_loop(b, build_params(COMBINED[b]))
        baselines[b] = {"X_end": float(sim["X"].iloc[-1]), "P_end": float(sim["P"].iloc[-1]),
                        "yield_err": 100.0 * float(yield_metrics(sim, v3)["rel_err_total"])}

    print("\n" + "=" * 92)
    print(f"Part B　退化极限：age={age:.3f} 固定，lysis 从 {lysis_list[0]} 扫到 {lysis_list[-1]}")
    print("=" * 92)
    for b in batches:
        bl = baselines[b]
        print(f"b{b} base: X末 {bl['X_end']:6.2f}  P末 {bl['P_end']:6.2f}  yield {bl['yield_err']:+6.2f}%")
        for l in lysis_list:
            r = next(x for x in rows if x["b"] == b and x["lysis"] == l)
            print(f"   lysis {l:<5}  死菌池 {r['dead_pool']:5.2f} ({r['debris_frac']:4.1f}%)"
                  f"  X末 {r['X_end']:6.2f}  P末 {r['P_end']:6.2f}  yield {r['yield_err']:+6.2f}%")
        print("   → 死菌池随 lysis 单调缩小；lysis→∞ 时退化为「按 age 直接移除 a1」")

    json.dump({"meta": {"age": age, "lysis_list": list(lysis_list),
                        "claim": "死菌池→0 且 X 降幅收敛 ⇒ 形态学链退化为等比衰亡的 a1 特例"},
               "baselines": baselines, "rows": rows},
              open(OUT_L, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n已写入 {os.path.relpath(OUT_L, ROOT)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", choices=["frontier", "limit", "all"], default="all")
    ap.add_argument("--batches", nargs="*", type=int, default=[8, 29, 56])
    ap.add_argument("--age", type=float, default=0.010)
    a = ap.parse_args()
    if a.part in ("frontier", "all"):
        part_frontier()
    if a.part in ("limit", "all"):
        part_limit(a.batches, age=a.age)


if __name__ == "__main__":
    main()
