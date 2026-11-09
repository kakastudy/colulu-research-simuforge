# -*- coding: utf-8 -*-
"""R138：基于在线 OUR 的生物量软测量（B 档），严格留一批交叉验证（LOBO）。

## 定位

GOAL.md §3 把「B 软测量（逆问题）」列为项目交付物之一，与 A 档仿真引擎并列。
R134–R137 反复证明：A 档（正问题）的 X 轨迹在现参数域内不可修——86 批是逐批独立
随机参数，任何全局常数都会改坏本来准的批。本工具走 B 档，问一个不同的问题：

    **X 能不能只靠在线 OUR + 一个早期化验锚点重建出来？**

若能，则 X 轨迹的达标路径不在 A 档，而在 B 档，且这正是工业标准做法
（生物反应器没有在线活菌传感器，必须靠软测量）。

## 方法：qO2 分解

定义比呼吸速率 qO2(t) = OUR(t) / X(t)（gO2/gX/h）。由氧平衡
    OUR = (μ/Y_O2_X + m_O2)·X + (产素耗氧)
可知 qO2 反映单位菌体的呼吸活性，随时间衰减（菌老化、维持能占比上升）。

R138 实测（100 批）：把 qO2 按 t=48h 归一化后，**形状在批间高度一致**
（t=36–156 的 CV 仅 5%–17%）。因此可分解为

    qO2(t) ≈ k_batch · φ(t)

  φ(t)  通用生理衰减形状（由**其他批**估计，不含目标批）
  k_batch  批级标度（由目标批的**早期锚点**定，不碰化验点本身之后的任何 X）

于是  X_est(t) = OUR_smooth(t) / (k_batch · φ(t))

**这是真正的预测**：目标批的全时程 X 只用 t≤anchor 的一个化验点，
其余全部来自在线 OUR 与跨批形状先验。

## 评估

留一批交叉验证（leave-one-batch-out）：每一批都由其余批估计 φ，
避免信息泄漏。报 nRMSE 于全部化验点（含锚点已剔除）。

## 用法
    python tools/r138_our_softsensor.py --all86 --anchor 48
    python tools/r138_our_softsensor.py --batch 56 --anchor 36
"""
import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "processed", "batches")
OUT = os.path.join(ROOT, "runs", "p3", "r138_our_softsensor.json")

# OUR 是尾气导出的在线量，5 min 采样但含高频噪声；用 3h 滚动中位平滑
SMOOTH_WIN = 15
GRID = np.arange(24.0, 300.0, 12.0)


# --------------------------------------------------------------------------- IO
def load(batch):
    d = pd.read_csv(os.path.join(DATA, f"batch_{batch:02d}.csv"))
    t = pd.to_numeric(d["time_h"], errors="coerce").to_numpy(float)
    our = pd.to_numeric(d["OUR"], errors="coerce").to_numpy(float)
    xl = pd.to_numeric(d["X_offline"], errors="coerce").to_numpy(float)
    s = pd.Series(our).rolling(SMOOTH_WIN, center=True, min_periods=3).median()
    our_s = np.where(np.isfinite(s.to_numpy(float)), s.to_numpy(float), our)
    ok = np.isfinite(t) & np.isfinite(our)
    return {"b": batch, "t": t[ok], "our": our_s[ok], "xl_raw": xl, "t_raw": t,
            "v3": d}


def lab_points(b):
    """化验 X 的点（时间, 值），只保留可用点。"""
    d = b["v3"]
    t = pd.to_numeric(d["time_h"], errors="coerce").to_numpy(float)
    x = pd.to_numeric(d["X_offline"], errors="coerce").to_numpy(float)
    m = np.isfinite(x) & np.isfinite(t)
    return t[m], x[m]


def qo2_at(b, times, min_x=3.0):
    """在给定时刻计算 qO2 = OUR/X（需同时有化验 X）。"""
    tl, xl = lab_points(b)
    out = np.full(len(times), np.nan)
    for i, tt in enumerate(times):
        if tt > tl[-1] or tt < tl[0]:
            continue
        x = np.interp(tt, tl, xl)
        if x < min_x:
            continue
        out[i] = np.interp(tt, b["t"], b["our"]) / x
    return out


# --------------------------------------------------------------------------- 形状
def shape_of(b, anchor_t):
    """归一化形状 φ(t) = qO2(t)/qO2(anchor)，只在可靠区间；无效返回 None。"""
    q = qo2_at(b, GRID)
    if not np.isfinite(q).any():
        return None
    # anchor 附近的观测值（±18h 窗口内取中位，抗单点噪声）
    m = np.isfinite(q) & (np.abs(GRID - anchor_t) <= 18.0)
    if m.sum() < 1:
        return None
    qa = float(np.median(q[m]))
    if qa <= 1e-6:
        return None
    phi = q / qa
    phi[~np.isfinite(phi)] = np.nan
    return {"phi": phi, "qa": qa}


def global_shape(shapes, anchor_t):
    """跨批形状的中位数与离散度（只用传入的批，即 LOBO 的训练集）。"""
    M = np.vstack([s["phi"] for s in shapes])
    phi = np.nanmedian(M, axis=0)
    lo = np.nanpercentile(M, 25, axis=0)
    hi = np.nanpercentile(M, 75, axis=0)
    cv = np.nanstd(M, axis=0) / np.maximum(np.nanmean(M, axis=0), 1e-9)
    qa = np.array([s["qa"] for s in shapes], float)
    # 形状在中位数缺失处用最近有效值填充（晚期少数批已结束）
    good = np.isfinite(phi)
    if good.sum() >= 2:
        phi = np.interp(GRID, GRID[good], phi[good])
    return {"phi": phi, "lo": lo, "hi": hi, "cv": cv,
            "qa_med": float(np.median(qa)), "qa_iqr": [float(np.percentile(qa, 25)),
                                                       float(np.percentile(qa, 75))]}


# --------------------------------------------------------------------------- 估计
def estimate(b, phi_grid, anchor_t, anchor_x=None):
    """X_est(t) = OUR(t) / (k · φ(t))。

    k 由锚点确定：k = qO2(anchor)/φ(anchor)。
    anchor_x 显式给出时直接用；否则用该批在 anchor 时刻的化验插值。
    """
    tl, xl = lab_points(b)
    if anchor_x is None:
        if anchor_t > tl[-1] or anchor_t < tl[0]:
            return None
        anchor_x = float(np.interp(anchor_t, tl, xl))
    if anchor_x <= 1.0:
        return None
    our_a = float(np.interp(anchor_t, b["t"], b["our"]))
    qa = our_a / anchor_x                       # 锚点处的实测 qO2
    phi_a = float(np.interp(anchor_t, GRID, phi_grid))
    if phi_a <= 1e-6:
        return None
    k = qa / phi_a                              # 批级标度
    phi_t = np.interp(b["t"], GRID, phi_grid)
    phi_t = np.maximum(phi_t, 1e-4)
    x = b["our"] / (k * phi_t)
    return {"t": b["t"], "x": x, "k": k, "qa": qa, "anchor_x": anchor_x}


def score(b, est, anchor_t, skip_first=1):
    """与化验 X 比对。剔除 anchor 时刻本身及其之前（那是输入，不是预测）。"""
    tl, xl = lab_points(b)
    m = tl > anchor_t + 1.0
    if m.sum() < 3:
        return None
    tv, yt = tl[m], xl[m]
    ys = np.interp(tv, est["t"], est["x"])
    if not np.all(np.isfinite(ys)):
        return None
    res = ys - yt
    mo = abs(np.mean(yt))
    ss_tot = float(np.sum((yt - yt.mean()) ** 2))
    return {"n": int(len(tv)), "nrmse": round(float(np.sqrt(np.mean(res ** 2)) / mo * 100), 2),
            "bias": round(float(res.mean() / mo * 100), 2),
            "r2": round(1.0 - float(np.sum(res ** 2)) / ss_tot, 4) if ss_tot > 1e-12 else None,
            "peak_ratio": round(float(np.max(ys) / np.max(yt)), 3) if yt.max() > 1e-9 else None,
            "end_ratio": round(float(ys[-1] / yt[-1]), 3) if abs(yt[-1]) > 1e-9 else None,
            "curve": [[round(float(a), 1), round(float(c), 2), round(float(d), 2)]
                      for a, c, d in zip(tv, yt, ys)]}


# --------------------------------------------------------------------------- 主流程
def run(batches, anchor_t, single=None):
    cache = {}
    for b in batches:
        try:
            cache[b] = load(b)
        except Exception as e:
            print(f"  ! load b{b}: {e}")

    shapes = {}
    for b, obj in cache.items():
        s = shape_of(obj, anchor_t)
        if s:
            shapes[b] = s

    rows = []
    if single is not None:
        targets = [single]
    else:
        targets = sorted(cache)

    for b in targets:
        if b not in cache or b not in shapes:
            continue
        # LOBO：用其余批估计 φ（目标批不参与）
        train = [shapes[k] for k in shapes if k != b]
        if len(train) < 5:
            continue
        gs = global_shape(train, anchor_t)
        est = estimate(cache[b], gs["phi"], anchor_t)
        if not est:
            continue
        sc = score(cache[b], est, anchor_t)
        if not sc:
            continue
        sc["batch"] = b
        sc["k"] = round(float(est["k"]), 5)
        sc["qa"] = round(float(est["qa"]), 5)
        rows.append(sc)

    return rows, shapes


def summarize(rows, anchor_t, tag=""):
    if not rows:
        print("no rows")
        return {}
    nr = np.array([r["nrmse"] for r in rows], float)
    bi = np.array([r["bias"] for r in rows], float)
    r2 = np.array([r["r2"] for r in rows if r["r2"] is not None], float)
    pk = np.array([r["peak_ratio"] for r in rows if r["peak_ratio"]], float)
    en = np.array([r["end_ratio"] for r in rows if r["end_ratio"]], float)
    print(f"\n=== OUR 软测量（LOBO，锚点 t={anchor_t:.0f}h）{tag}  n={len(rows)} ===")
    print(f"X nRMSE  中位 {np.median(nr):6.2f}%   p25 {np.percentile(nr,25):6.2f}  "
          f"p75 {np.percentile(nr,75):6.2f}  p90 {np.percentile(nr,90):6.2f}  max {nr.max():6.2f}")
    print(f"bias     中位 {np.median(bi):+6.2f}%   |bias| 中位 {np.median(np.abs(bi)):5.2f}%")
    if len(r2):
        print(f"R2       中位 {np.median(r2):.4f}")
    if len(pk):
        print(f"peakR    中位 {np.median(pk):.3f}   endR 中位 {np.median(en):.3f}")
    print(f"nRMSE<15% 的批: {(nr<15).sum()}/{len(nr)} ; <20%: {(nr<20).sum()} ; <25%: {(nr<25).sum()}")
    return {"n": len(rows), "nrmse_med": float(np.median(nr)),
            "nrmse_p90": float(np.percentile(nr, 90)),
            "bias_med": float(np.median(bi)),
            "r2_med": float(np.median(r2)) if len(r2) else None,
            "frac_lt15": float((nr < 15).mean()), "frac_lt20": float((nr < 20).mean())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=None)
    ap.add_argument("--all86", action="store_true")
    ap.add_argument("--anchor", type=float, default=48.0)
    ap.add_argument("--anchors", default=None, help="多个锚点扫描，如 24,36,48,72")
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()

    if args.all86:
        bs = [int(x) for x in open(os.path.join(ROOT, "runs", "p3", "_golden86.txt")).read().split()]
    else:
        import glob
        bs = [int(os.path.basename(f)[6:8]) for f in sorted(glob.glob(os.path.join(DATA, "batch_*.csv")))]

    anchors = ([float(x) for x in args.anchors.split(",")] if args.anchors else [args.anchor])
    all_out = {}
    for a in anchors:
        rows, shapes = run(bs, a, single=args.batch)
        s = summarize(rows, a)
        all_out[str(a)] = {"summary": s, "rows": rows}
        if args.batch:
            for r in rows:
                print(f"\n b{r['batch']}  nRMSE {r['nrmse']:.2f}%  bias {r['bias']:+.2f}%  "
                      f"R2 {r['r2']}  k {r['k']}  peakR {r['peak_ratio']}  endR {r['end_ratio']}")
                print("   t     X_lab   X_est")
                for c in r["curve"]:
                    print("  %5.0f  %7.2f  %7.2f" % (c[0], c[1], c[2]))

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"meta": {"anchors": anchors, "mode": "LOBO", "smooth_win": SMOOTH_WIN},
                   "results": all_out}, f, ensure_ascii=False, indent=1)
    print(f"\n已写入 {args.out}")


if __name__ == "__main__":
    main()
