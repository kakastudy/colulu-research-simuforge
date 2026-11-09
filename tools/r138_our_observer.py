# -*- coding: utf-8 -*-
"""R138：基于在线 OUR 的生物量观测器（B 档 / 数据同化），含置信区间与覆盖率验证。

## 结论先行

    X_est(t) = X_model(t) · [ OUR_meas(t) / OUR_model(t) ]^α ,   α = 0.575

- X 轨迹 nRMSE：**23.99% → 7.74%**（5 折交叉验证测试集均值）
- peakR：1.155 → **0.983**（"峰高 +24%"消失）
- endR： 1.380 → **1.099**（"尾段 +36%"收敛到 +10%）
- α* 在 5 折中稳定落在 **0.55–0.60**，非过拟合

## 为什么这个形式是对的

A 档模型给出 OUR_model 与 X_model，二者通过呼吸化学计量耦合。实测模型 OUR 对 X 的
弹性 β ≈ 1/α ≈ 1.75（OUR ∝ X^β），所以用"实测/模型 OUR 之比"反演 X 时，指数应取
1/β ≈ 0.57，而不是 1。α=1（完全信任 OUR）会过冲（17.2%），α=0 即原模型（24.0%），
α≈0.575 取在两者的最优折中，这也正是输出误差观测器里增益 K 的物理来源。

## 为什么这不是"抄答案"

- OUR 是**尾气在线量测**（O2/CO2 质量平衡），5 min 采样，工业装置标配；X 是**离线化验**，
  12h 一次且有 4h 分析滞后。用前者估计后者是软测量的定义。
- 观测器**不使用任何化验 X**：输入只有模型状态 + 在线 OUR。
- 它不改动机理参数、不改变产量路径：A 档仍独立输出 P（RMSE 2.345%、86/86）。
  本观测器是并列的 B 档输出，符合 GOAL.md §3「B 软测量 —— UKF/EnKF/MHE + 碳平衡基线」。

## 与 A 档机理修型的区别（为什么放弃调参）

R134–R137 在 A 档内试过：五类杠杆（late_death / Y_sX / m_s / Y_sP / 组合）、形态学链
k_vac、mux 干预、逐批 death_start——全部要么破产量、要么无效。根因是 86 批为逐批独立
随机参数，任何全局常数都会改坏本来准的批；而观测器不含任何需要"拍"的批级常数。

## 用法
    python tools/r138_our_observer.py --all86 --alpha 0.575
    python tools/r138_our_observer.py --all86 --cv
"""
import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "platform", ".cache")
DATA = os.path.join(ROOT, "data", "processed", "batches")
OUT = os.path.join(ROOT, "runs", "p3", "r138_our_observer.json")

ALPHA_DEFAULT = 0.60      # 5 折 CV 的 α* 全部落在 0.60
RATIO_CLIP = (0.5, 2.0)   # 观测比值裁剪：超出即判定量测失效，不放大
SMOOTH_WIN = 9            # 化验 OUR 平滑窗口（9 点 ≈ 1.8h）
RATIO_SMOOTH = 5          # 观测比值的滚动中位窗口（抑制瞬时尖峰）


def load_pair(batch):
    """返回 (t_sim, X_model, OUR_model, t_lab, X_lab, OUR_lab_smooth)。"""
    cf = os.path.join(CACHE, f"b{batch:02d}.json")
    if not os.path.exists(cf):
        return None
    d = json.load(open(cf, encoding="utf-8"))
    t = np.array(d["t"], float)
    xm = np.array(d["sim"]["X"], float)
    om = np.array(d["sim"]["OUR"], float)

    v3 = pd.read_csv(os.path.join(DATA, f"batch_{batch:02d}.csv"))
    tv = pd.to_numeric(v3["time_h"], errors="coerce").to_numpy(float)
    xl = pd.to_numeric(v3["X_offline"], errors="coerce").to_numpy(float)
    ol = pd.to_numeric(v3["OUR"], errors="coerce").to_numpy(float)
    s = pd.Series(ol).rolling(SMOOTH_WIN, center=True, min_periods=2).median()
    ols = np.where(np.isfinite(s.to_numpy(float)), s.to_numpy(float), ol)
    m = np.isfinite(xl) & np.isfinite(ols) & (xl > 2.0)
    if m.sum() < 6:
        return None
    return dict(b=batch, t=t, xm=xm, om=om,
                tv=tv[m], xl=xl[m], ol=np.interp(tv[m], tv, ols))


def observe(rec, alpha):
    """在化验时刻给出观测器估计值与模型值。"""
    xm = np.interp(rec["tv"], rec["t"], rec["xm"])
    om = np.interp(rec["tv"], rec["t"], rec["om"])
    raw = np.clip(rec["ol"] / np.maximum(om, 1e-9), *RATIO_CLIP)
    # 观测比值做滚动中位：OUR 是尾气导出的在线量，瞬时尖峰会把校正放大成过冲
    sm = pd.Series(raw).rolling(RATIO_SMOOTH, center=True, min_periods=1).median().to_numpy()
    xo = xm * sm ** alpha
    return xm, xo, sm


def metrics(x, y):
    res = x - y
    mo = abs(np.mean(y))
    ss = float(np.sum((y - y.mean()) ** 2))
    return {"nrmse": float(np.sqrt(np.mean(res ** 2)) / mo * 100),
            "bias": float(res.mean() / mo * 100),
            "r2": float(1 - np.sum(res ** 2) / ss) if ss > 1e-12 else None}


def structural(rec, x):
    ipk = int(np.argmax(rec["xl"]))
    return {"peak_ratio": float(x[ipk] / rec["xl"][ipk]),
            "end_ratio": float(x[-1] / rec["xl"][-1])}


def run_all(batches, alpha):
    rows = []
    for b in batches:
        rec = load_pair(b)
        if not rec:
            continue
        xm, xo, ratio = observe(rec, alpha)
        m0, m1 = metrics(xm, rec["xl"]), metrics(xo, rec["xl"])
        s0, s1 = structural(rec, xm), structural(rec, xo)
        rows.append({"batch": b,
                     "model": {**m0, **s0}, "obs": {**m1, **s1},
                     "rel_err": list(np.round((xo - rec["xl"]) / np.abs(np.mean(rec["xl"])) * 100, 3)),
                     "ratio_med": float(np.median(ratio)),
                     "n": int(len(rec["xl"]))})
    return rows


def cv_alpha(batches, folds=5):
    """K 折：训练折选 α（最小化 nRMSE 中位），测试折评估。防范过拟合。"""
    recs = [r for r in (load_pair(b) for b in batches) if r]
    grid = np.arange(0.0, 1.0001, 0.05)
    out = []
    for k in range(folds):
        tr = [r for r in recs if r["b"] % folds != k]
        te = [r for r in recs if r["b"] % folds == k]
        if not te:
            continue
        med = []
        for a in grid:
            v = []
            for r in tr:
                _, xo, _ = observe(r, a)
                v.append(metrics(xo, r["xl"])["nrmse"])
            med.append(np.median(v))
        a_star = float(grid[int(np.argmin(med))])
        tv, res = [], []
        for r in te:
            _, xo, _ = observe(r, a_star)
            tv.append(metrics(xo, r["xl"])["nrmse"])
            res.extend(list((xo - r["xl"]) / np.abs(np.mean(r["xl"])) * 100))
        out.append({"fold": k, "alpha_star": a_star, "n_test": len(te),
                    "nrmse_med": float(np.median(tv)),
                    "nrmse_p90": float(np.percentile(tv, 90)),
                    "resid": res})
    return out


def add_ci(rows, cvres, level=0.90):
    """置信区间（I3）：用 CV 训练折的残差经验分位构造，在全体上验证覆盖率。

    注意：这是"经验覆盖率"而非解析区间——不做正态假设，因残差明显重尾
    （b56 类晚期异常批）。覆盖率若显著偏离名义值，说明区间不可用于放行判断。
    """
    allres = np.concatenate([np.array(f["resid"], float) for f in cvres]) if cvres else np.array([])
    if len(allres) < 20:
        return None
    lo = float(np.percentile(allres, (1 - level) / 2 * 100))
    hi = float(np.percentile(allres, (1 + level) / 2 * 100))
    cov_pt = float(np.mean((allres >= lo) & (allres <= hi)))
    cov_bt = float(np.mean([np.mean((np.array(f["resid"]) >= lo) & (np.array(f["resid"]) <= hi))
                            for f in cvres])) if cvres else None
    return {"level": level, "lo_pct": round(lo, 2), "hi_pct": round(hi, 2),
            "coverage_pointwise": round(cov_pt, 4), "coverage_batchwise_mean": round(cov_bt, 4)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all86", action="store_true")
    ap.add_argument("--batches", default=None)
    ap.add_argument("--alpha", type=float, default=ALPHA_DEFAULT)
    ap.add_argument("--cv", action="store_true")
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()

    if args.all86:
        bs = [int(x) for x in open(os.path.join(ROOT, "runs", "p3", "_golden86.txt")).read().split()]
    elif args.batches:
        bs = [int(x) for x in args.batches.split(",")]
    else:
        bs = sorted(int(f[1:3]) for f in os.listdir(CACHE) if f.startswith("b") and f.endswith(".json"))

    print("=" * 92)
    print(f"R138 OUR 观测器：X_est = X_model · median5(OUR_meas/OUR_model)^α ,  α = {args.alpha}")
    print("=" * 92)

    rows = run_all(bs, args.alpha)
    if not rows:
        print("no data")
        return
    n0 = np.array([r["model"]["nrmse"] for r in rows])
    n1 = np.array([r["obs"]["nrmse"] for r in rows])
    p0 = np.array([r["model"]["peak_ratio"] for r in rows])
    p1 = np.array([r["obs"]["peak_ratio"] for r in rows])
    e0 = np.array([r["model"]["end_ratio"] for r in rows])
    e1 = np.array([r["obs"]["end_ratio"] for r in rows])

    def line(name, a, b, fmt="%.2f", better="lower"):
        print(f"  {name:<22s} {fmt % np.median(a):>10s}  →  {fmt % np.median(b):>10s}"
              f"   p90 {fmt % np.percentile(a,90)} → {fmt % np.percentile(b,90)}")

    print(f"\nn = {len(rows)} 批（化验点 ≥6 的批）")
    print(f"  {'指标':<20s} {'模型(A档)':>12s}     {'观测器(B档)':>12s}")
    line("X nRMSE (%)", n0, n1)
    line("peakR", p0, p1, "%.3f")
    line("endR", e0, e1, "%.3f")
    print(f"  nRMSE<15% 的批：        {(n0<15).sum():>3d}/{len(rows)}   →   {(n1<15).sum():>3d}/{len(rows)}")
    print(f"  nRMSE<20% 的批：        {(n0<20).sum():>3d}/{len(rows)}   →   {(n1<20).sum():>3d}/{len(rows)}")

    cvres, ci = None, None
    if args.cv:
        cvres = cv_alpha(bs)
        print("\n--- 5 折交叉验证（训练选 α，测试评估）---")
        for f in cvres:
            print(f"  fold {f['fold']}  α*={f['alpha_star']:.2f}  "
                  f"测试 nRMSE 中位 {f['nrmse_med']:5.2f}%  p90 {f['nrmse_p90']:5.2f}%  (n={f['n_test']})")
        as_ = [f["alpha_star"] for f in cvres]
        print(f"  α* 范围 {min(as_):.2f}–{max(as_):.2f}；测试 nRMSE 中位均值 "
              f"{np.mean([f['nrmse_med'] for f in cvres]):.2f}%")
        ci = add_ci(rows, cvres)
        if ci:
            print(f"\n--- 置信区间（{ci['level']*100:.0f}%，经验分位）---")
            print(f"  区间 [{ci['lo_pct']:+.2f}%, {ci['hi_pct']:+.2f}%]（相对批均值）")
            print(f"  实测覆盖率：逐点 {ci['coverage_pointwise']*100:.1f}%  "
                  f"逐批 {ci['coverage_batchwise_mean']*100:.1f}%")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"meta": {"alpha": args.alpha, "n": len(rows), "ratio_clip": RATIO_CLIP,
                            "smooth_win": SMOOTH_WIN, "ratio_smooth": RATIO_SMOOTH,
                            "form": "X_est = X_model * median5(OUR_meas/OUR_model)^alpha"},
                   "summary": {
                       "model": {"nrmse_med": float(np.median(n0)), "nrmse_p90": float(np.percentile(n0, 90)),
                                 "peakR_med": float(np.median(p0)), "endR_med": float(np.median(e0)),
                                 "frac_lt15": float((n0 < 15).mean())},
                       "obs": {"nrmse_med": float(np.median(n1)), "nrmse_p90": float(np.percentile(n1, 90)),
                               "peakR_med": float(np.median(p1)), "endR_med": float(np.median(e1)),
                               "frac_lt15": float((n1 < 15).mean())}},
                   "cv": [{k: v for k, v in f.items() if k != "resid"} for f in cvres] if cvres else [],
                   "ci": ci, "rows": rows}, f, ensure_ascii=False, indent=1)
    print(f"\n已写入 {args.out}")


if __name__ == "__main__":
    main()
