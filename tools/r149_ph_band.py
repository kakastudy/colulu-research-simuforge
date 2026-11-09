# -*- coding: utf-8 -*-
"""R149 / D-39 附件：实测 pH 到底是"自由观测量"还是"控制设定量"。

动机
----
R148 §5.5 用"模型峰高于实测峰"推断模型 pH 振幅过大，R149 又发现全球 min/max 口径
把不同时刻的极值放在一起比（模型极小点在 90–174 h，实测极小点在 17–25 h）。
在下任何 pH 相关结论之前，必须先回答一个更前置的问题：

    **实测 pH 这条序列，本身有多少变化？**

IndPenSim 的 pH 由加碱/加酸反馈控制到 6.5 附近。若实测 pH 的批内标准差只有 0.02 量级，
那么"模型 pH 振幅是实测的 4–6 倍"这句话没有意义——分母趋近于 0，比值没有上限。
本工具只读数据文件，**不跑仿真**。

用法
----
    python tools/r149_ph_band.py
    python tools/r149_ph_band.py --batches 22,36,55

输出：runs/r149_ph_band.json
"""
import argparse
import json
import os
import sys

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))


def one(b):
    from simulate import load_batch
    d = load_batch(int(b))
    ph = d["pH"].to_numpy(float)
    ph = ph[np.isfinite(ph)]
    if ph.size < 10:
        return None
    return {
        "batch": int(b), "n": int(ph.size),
        "min": float(ph.min()), "max": float(ph.max()),
        "mean": float(ph.mean()), "std": float(ph.std()),
        "range": float(ph.max() - ph.min()),
        # 落在 6.50±0.05 内的样点占比 —— 控制带宽度
        "frac_band_005": float(np.mean(np.abs(ph - 6.5) <= 0.05)),
        "frac_band_010": float(np.mean(np.abs(ph - 6.5) <= 0.10)),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", type=str, default="", help="默认 1..100 全部可读批")
    args = ap.parse_args()

    if args.batches:
        bs = [int(x) for x in args.batches.split(",") if x.strip()]
    else:
        bs = list(range(1, 101))

    rows = [r for r in (one(b) for b in bs) if r]
    a = {k: np.array([r[k] for r in rows]) for k in ("std", "range", "mean", "max", "min",
                                                     "frac_band_005")}
    print(f"批数 {len(rows)}（只读数据，未跑仿真）\n")
    print(f"  批内标准差  中位 {np.median(a['std']):.4f}   P90 {np.percentile(a['std'], 90):.4f}"
          f"   max {a['std'].max():.4f}")
    print(f"  批内极差    中位 {np.median(a['range']):.4f}   P90 {np.percentile(a['range'], 90):.4f}"
          f"   max {a['range'].max():.4f}")
    print(f"  批内均值    {a['mean'].min():.4f} – {a['mean'].max():.4f}"
          f"   中位 {np.median(a['mean']):.4f}")
    print(f"  6.50±0.05 内样点占比  中位 {np.median(a['frac_band_005']):.3f}"
          f"   最小 {a['frac_band_005'].min():.3f}")
    print(f"  全局范围    {a['min'].min():.4f} – {a['max'].max():.4f}\n")

    # 分档：控制带内的批 vs 失控批
    lost = [r for r in rows if r["range"] > 0.50]
    held = [r for r in rows if r["range"] <= 0.50]
    print(f"  受控（批内极差 ≤0.50）：{len(held)} 批，极差中位 "
          f"{np.median([r['range'] for r in held]):.3f}")
    print(f"  失控（批内极差 >0.50）：{len(lost)} 批 —— "
          + ", ".join(f"b{r['batch']}({r['range']:.2f})" for r in lost))

    out = {"n": len(rows), "rows": rows,
           "summary": {k: {"median": float(np.median(v)), "p90": float(np.percentile(v, 90)),
                           "min": float(v.min()), "max": float(v.max())}
                       for k, v in a.items()},
           "n_range_le_050": len(held), "n_range_gt_050": len(lost)}
    p = os.path.join(ROOT, "runs", "r149_ph_band.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"\n写出 {p}")


if __name__ == "__main__":
    main()
