# -*- coding: utf-8 -*-
"""R133 S1.3 前置探针：黏度"先升后降"形状的定量证据。

只读数据 + 少量仿真，不做任何参数改动。

回答三个问题：
  Q1 观测黏度到底有多少批在批末回落？回落的起降时刻与幅度是多少？
  Q2 现状仿真黏度是单调饱和吗？（与 Q1 对照）
  Q3 回落段能否用现有衰减支路解释？—— 即 t2 需要落在多少小时量级。

产物：runs/p3/r133_vis_shape.json
用法：python tools/r133_vis_shape_probe.py [--sim N]
"""
import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PKG = os.path.join(ROOT, "candidate", "indpensim", "v0.1")
sys.path.insert(0, PKG)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from golden_params import COMBINED, GOLDEN_ALL, build_params  # noqa: E402


def load_v3(batch_no):
    return pd.read_csv(os.path.join(ROOT, "data", "processed", "batches",
                                    f"batch_{batch_no:02d}.csv"))


def smooth(y, win=9):
    if len(y) < win:
        return y
    k = np.ones(win) / win
    return np.convolve(y, k, mode="same")


def obs_shape(b):
    """观测侧形状量：峰、峰时、批末值、回落幅度、回落段斜率。"""
    df = load_v3(b)
    if "Viscosity_offline" not in df.columns or "time_h" not in df.columns:
        return None
    t = df["time_h"].to_numpy(float)
    v = df["Viscosity_offline"].to_numpy(float)
    m = np.isfinite(t) & np.isfinite(v) & (v > 0)
    t, v = t[m], v[m]
    if t.size < 20:
        return None
    vs = smooth(v, 9)
    ipk = int(np.argmax(vs))
    t_pk, v_pk = float(t[ipk]), float(vs[ipk])
    v_end = float(np.median(vs[-5:]))
    t_end = float(t[-1])
    # 回落段：峰后到批末的线性斜率（cP/h）
    if t_end - t_pk > 10:
        seg_t, seg_v = t[ipk:], vs[ipk:]
        slope = float(np.polyfit(seg_t, seg_v, 1)[0])
    else:
        slope = 0.0
    return {
        "n_obs": int(t.size),
        "t_end": t_end,
        "t_peak": t_pk,
        "v_peak": v_pk,
        "v_end": v_end,
        "decline_abs": v_pk - v_end,
        "decline_rel": (v_pk - v_end) / v_pk if v_pk > 0 else 0.0,
        "post_peak_slope": slope,
        "v_max": float(vs.max()),
        "v_min_head": float(np.median(vs[:5])),
    }


def sim_shape(b):
    from simulate import simulate_open_loop
    sim, _ = simulate_open_loop(b, build_params(COMBINED[b]))
    t = sim["time_h"].to_numpy(float)
    col = "vis" if "vis" in sim.columns else ("Viscosity" if "Viscosity" in sim.columns else None)
    if col is None:
        return None
    v = sim[col].to_numpy(float)
    m = np.isfinite(v)
    t, v = t[m], v[m]
    vs = smooth(v, 9)
    ipk = int(np.argmax(vs))
    return {
        "col": col,
        "t_end": float(t[-1]),
        "t_peak": float(t[ipk]),
        "v_peak": float(vs[ipk]),
        "v_end": float(np.median(vs[-5:])),
        "decline_rel": float((vs[ipk] - np.median(vs[-5:])) / vs[ipk]) if vs[ipk] > 0 else 0.0,
        "monotone_frac": float(np.mean(np.diff(vs) >= -1e-9)),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sim", type=int, default=6, help="顺带跑几条仿真做形状对照")
    ap.add_argument("--sim-batches", default="8,11,16,27,36,60")
    args = ap.parse_args()

    rows = {}
    for b in GOLDEN_ALL:
        s = obs_shape(b)
        if s:
            rows[b] = s

    declines = np.array([r["decline_rel"] for r in rows.values()])
    peaks = np.array([r["t_peak"] for r in rows.values()])
    ends = np.array([r["t_end"] for r in rows.values()])
    slopes = np.array([r["post_peak_slope"] for r in rows.values()])

    summary = {
        "n_batches": len(rows),
        "decline_rel_median": float(np.median(declines)),
        "decline_rel_p25": float(np.percentile(declines, 25)),
        "decline_rel_p75": float(np.percentile(declines, 75)),
        "frac_decline_gt5pct": float(np.mean(declines > 0.05)),
        "frac_decline_gt10pct": float(np.mean(declines > 0.10)),
        "frac_decline_lt0": float(np.mean(declines < 0.0)),
        "t_peak_median": float(np.median(peaks)),
        "t_peak_p25": float(np.percentile(peaks, 25)),
        "t_peak_p75": float(np.percentile(peaks, 75)),
        "t_end_median": float(np.median(ends)),
        "post_peak_slope_median": float(np.median(slopes)),
        "t_peak_over_t_end_median": float(np.median(peaks / ends)),
        "batches_decline_gt10": [int(b) for b, r in rows.items() if r["decline_rel"] > 0.10],
        "batches_rise_only": [int(b) for b, r in rows.items() if r["decline_rel"] < 0.0],
    }

    sims = {}
    if args.sim > 0:
        for b in [int(x) for x in args.sim_batches.split(",")][: args.sim]:
            if b not in COMBINED:
                continue
            try:
                sims[b] = sim_shape(b)
            except Exception as exc:  # noqa: BLE001
                sims[b] = {"error": f"{type(exc).__name__}: {exc}"}

    out = {"obs_summary": summary, "obs_per_batch": {str(k): v for k, v in rows.items()},
           "sim_shape": {str(k): v for k, v in sims.items()}}
    os.makedirs(os.path.join(ROOT, "runs", "p3"), exist_ok=True)
    p = os.path.join(ROOT, "runs", "p3", "r133_vis_shape.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print("--- sim ---")
    for k, v in sims.items():
        print(k, v)
    print("saved", p)


if __name__ == "__main__":
    main()
