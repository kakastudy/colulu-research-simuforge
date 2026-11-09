# -*- coding: utf-8 -*-
"""R130h: 不可修复批次 V3 特征诊断 —— 对比可修复 vs 不可修复批的 V3 轨迹特征。

输出每批的 V3 关键特征：
- 批长、P 峰值/末值、X_offline 峰值/末值、S 耗尽时刻
- pH 范围、DO2 范围、CO2d 范围
- 进料总量、喂食模式（Fs/Fg/Fpaa 均值）
- 故障标志

目的：找出不可修复批的结构性特征（pH 崩溃/CO2 catastrophic/结构产率误差）。
"""
import json
import os

import numpy as np
import pandas as pd

FIXABLE = [1, 2, 3, 5, 7, 8, 9, 11, 12, 14, 15, 16, 17, 18, 20, 22, 23, 24, 26, 27, 28, 29, 30, 31, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 45, 46, 47, 48, 49, 50, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 95, 96, 98]
UNFIXABLE = [4, 6, 10, 13, 19, 21, 25, 32, 44, 51, 81, 94, 97, 99, 100]


def feat(b):
    d = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
    xoff = pd.to_numeric(d["X_offline"], errors="coerce")
    t_end = float(d["time_h"].iloc[-1])
    p_last = float(d["P"].iloc[-1])
    p_max = float(d["P"].max())
    x_max = float(xoff.max()) if xoff.notna().any() else 0
    x_last = float(xoff.iloc[-1]) if pd.notna(xoff.iloc[-1]) else 0
    s_min = float(d["S"].min())
    ph = d["pH"]
    do2 = d["DO2"]
    co2d = d["CO2d"] if "CO2d" in d else d["CO2outgas"]
    feed_fs = float(d["Fs"].mean())
    feed_fg = float(d["Fg"].mean())
    feed_fpaa = float(d["Fpaa"].mean())
    fault = int(d["FaultFlag"].iloc[0]) if "FaultFlag" in d else 0
    return {
        "batch": b, "t_end": round(t_end, 1), "p_last": round(p_last, 2),
        "p_max": round(p_max, 2), "x_max": round(x_max, 2), "x_last": round(x_last, 2),
        "s_min": round(s_min, 4), "ph_min": round(float(ph.min()), 2),
        "ph_max": round(float(ph.max()), 2), "do2_min": round(float(do2.min()), 2),
        "co2_max": round(float(co2d.max()), 2),
        "feed_fs": round(feed_fs, 4), "feed_fg": round(feed_fg, 4),
        "feed_fpaa": round(feed_fpaa, 4), "fault": fault,
    }


def main():
    out = {"fixable": [], "unfixable": []}
    for b in UNFIXABLE:
        f = feat(b)
        out["unfixable"].append(f)
        print(f"UNFIX b{b:>3d} t={f['t_end']:5.0f} P={f['p_last']:6.1f} Xpk={f['x_max']:5.1f} "
              f"pH[{f['ph_min']:.1f},{f['ph_max']:.1f}] DO2min={f['do2_min']:.1f} "
              f"CO2max={f['co2_max']:.2f} fault={f['fault']} Fs={f['feed_fs']:.3f}")
    print()
    # 抽样可修复批对照
    for b in [8, 22, 36, 60, 80, 91]:
        f = feat(b)
        out["fixable"].append(f)
        print(f"FIX   b{b:>3d} t={f['t_end']:5.0f} P={f['p_last']:6.1f} Xpk={f['x_max']:5.1f} "
              f"pH[{f['ph_min']:.1f},{f['ph_max']:.1f}] DO2min={f['do2_min']:.1f} "
              f"CO2max={f['co2_max']:.2f} fault={f['fault']} Fs={f['feed_fs']:.3f}")
    with open("runs/p3/r130h_unfixable_features.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)
    print("Saved: runs/p3/r130h_unfixable_features.json")


if __name__ == "__main__":
    main()
