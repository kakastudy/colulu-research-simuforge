# -*- coding: utf-8 -*-
"""S1.2 黏度批级标度校准 —— 用均值比直接给出 vis_scale 初值，再一次仿真验证。

诊断依据（runs/p3/r132_channel_class.json）：
    Viscosity_offline 中位 gain = 1.31，逐批范围 [0.73, 1.58]；
    最差批（b3/b29/b33）gain 1.49~1.58、bias +49%~+58%；
    最好的批（b8/b11/b16/b92）gain 0.94~0.99、bias −6%~−1%。
**规律**：COMBINED 里**有** vis_scale 的 8 批正好是 gain≈1 的那批；
其余 78 批跑默认 1.0，于是系统性地高 30%~50%。
所以这不是"动力学形状错"，而是"标度没逐批标定过"——A 类，可便宜修。

做法：黏度 ODE `dy9 = vis_scale·3·a₀^(1/3)·σ₁·σ₂ − k3·Fw` 对 vis_scale 近似线性，
故最优标度可用一次仿真的均值比直接给出：new_scale = old_scale / gain。
再做一次仿真验证（不改代码，只改参数）。

红线：黏度进 kla（`kla ∝ vis_scaled^c`）→ 影响 OTR → 可能牵动 DO2 与产量。
故本脚本同时报每个批的 yield_err 变化，超出 ±0.2pt 的批会被标记。

用法：
    python tools/r132_vis_scale_cal.py                # 86 批全量
    python tools/r132_vis_scale_cal.py --batches 3,29 # 指定
    python tools/r132_vis_scale_cal.py --apply        # 通过后写回 golden_params
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

from simulate import simulate_open_loop, yield_metrics  # noqa: E402
from golden_params import COMBINED, GOLDEN_ALL, build_params  # noqa: E402

CLASS_JSON = os.path.join(ROOT, "runs", "p3", "r132_channel_class.json")
VIS_MIN, VIS_MAX = 0.30, 1.60      # 标度允许范围（防拟合到极端）
YIELD_GUARD_PT = 0.2               # 产量退化红线


def vis_nrmse(sim, v3):
    """与 D6 同口径（索引对齐）的黏度 nRMSE。"""
    s = sim["vis"].to_numpy(float)
    l = v3["Viscosity_offline"].to_numpy(float)
    n = min(len(s), len(l))
    s, l = s[:n], l[:n]
    m = ~np.isnan(l) & (l > 0)
    if m.sum() < 3:
        return None
    return float(np.sqrt(np.mean((s[m] - l[m]) ** 2)) / np.mean(np.abs(l[m])) * 100)


def run_one(job):
    b, scale = job
    v3 = pd.read_csv(os.path.join(ROOT, "data", "processed", "batches", f"batch_{b:02d}.csv"))
    p = build_params(COMBINED[b])
    sim0, _ = simulate_open_loop(b, p)
    e0 = float(yield_metrics(sim0, v3)["rel_err_total"])
    n0 = vis_nrmse(sim0, v3)

    p2 = dict(p)
    p2["vis_scale"] = scale
    sim1, _ = simulate_open_loop(b, p2)
    e1 = float(yield_metrics(sim1, v3)["rel_err_total"])
    n1 = vis_nrmse(sim1, v3)

    return {"batch": b, "vis_scale_old": float(p.get("vis_scale", 1.0)),
            "vis_scale_new": float(scale), "vis_nrmse_old": n0, "vis_nrmse_new": n1,
            "yield_old": e0, "yield_new": e1, "dyield_pt": (e1 - e0) * 100}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", default="")
    ap.add_argument("--out", default=os.path.join(ROOT, "runs", "p3", "r132_vis_scale.json"))
    ap.add_argument("--apply", action="store_true", help="验证通过后写回 golden_params")
    args = ap.parse_args()

    cls = json.load(open(CLASS_JSON, encoding="utf-8"))["per_batch"]
    batches = ([int(x) for x in args.batches.split(",")] if args.batches
               else list(GOLDEN_ALL))

    jobs = []
    for b in batches:
        rec = cls.get(str(b), {}).get("Viscosity_offline")
        if not rec or rec.get("gain") is None or rec["gain"] <= 0:
            continue
        old = float(build_params(COMBINED[b]).get("vis_scale", 1.0))
        new = float(np.clip(old / rec["gain"], VIS_MIN, VIS_MAX))
        jobs.append((b, new))

    print("=" * 96)
    print("S1.2 黏度批级标度校准 —— new_scale = old_scale / gain，一次仿真验证")
    print(f"批数 {len(jobs)}；标度范围 [{VIS_MIN}, {VIS_MAX}]；产量红线 ±{YIELD_GUARD_PT}pt")
    print("=" * 96)

    from multiprocessing import Pool
    with Pool(min(8, os.cpu_count() or 1)) as pool:
        res = pool.map(run_one, jobs, chunksize=1)

    res = [r for r in res if r["vis_nrmse_old"] is not None and r["vis_nrmse_new"] is not None]
    n0 = np.median([r["vis_nrmse_old"] for r in res])
    n1 = np.median([r["vis_nrmse_new"] for r in res])
    print(f"\n{'b':>3s} {'scale旧':>7s} {'scale新':>7s} {'黏度nRMSE':>13s} {'产量Δpt':>8s}")
    print("-" * 96)
    for r in sorted(res, key=lambda x: -(x["vis_nrmse_old"] - x["vis_nrmse_new"]))[:12]:
        print(f"{r['batch']:>3d} {r['vis_scale_old']:>7.2f} {r['vis_scale_new']:>7.2f} "
              f"{r['vis_nrmse_old']:>6.1f} → {r['vis_nrmse_new']:>5.1f} {r['dyield_pt']:>+8.2f}")
    print("  ...（其余批见 JSON）")

    improved = sum(1 for r in res if r["vis_nrmse_new"] < r["vis_nrmse_old"])
    worsened = sum(1 for r in res if r["vis_nrmse_new"] > r["vis_nrmse_old"] + 0.5)
    yield_bad = [r for r in res if abs(r["dyield_pt"]) > YIELD_GUARD_PT]
    within = sum(1 for r in res if abs(r["yield_new"]) <= 0.05)

    print("-" * 96)
    print(f"  黏度 nRMSE 中位   {n0:.1f}  →  {n1:.1f}   （改善 {improved}/{len(res)} 批，变差 {worsened} 批）")
    print(f"  产量 |Δ|>{YIELD_GUARD_PT}pt 的批：{[r['batch'] for r in yield_bad] or '无'}")
    print(f"  产量 ±5% 内：{within}/{len(res)}")

    out = {"guard_pt": YIELD_GUARD_PT, "vis_nrmse_median_old": n0,
           "vis_nrmse_median_new": n1, "improved": improved, "worsened": worsened,
           "yield_guard_violations": [r["batch"] for r in yield_bad], "rows": res}
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"\nSaved: {args.out}")

    if args.apply:
        if yield_bad:
            print(f"\n✗ 拒绝写回：{len(yield_bad)} 批超产量红线")
            return
        patch = {r["batch"]: round(r["vis_scale_new"], 4) for r in res}
        print(f"\n待写回 {len(patch)} 批 vis_scale（另需人工确认后写入 golden_params）")
        with open(os.path.join(ROOT, "runs", "p3", "r132_vis_scale_patch.json"), "w",
                  encoding="utf-8") as f:
            json.dump(patch, f, indent=1)
        print("patch 已落 runs/p3/r132_vis_scale_patch.json")


if __name__ == "__main__":
    main()
