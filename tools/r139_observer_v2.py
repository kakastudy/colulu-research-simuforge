# -*- coding: utf-8 -*-
"""R139 Part H：双通道观测器 v2 —— 批级水平用 OUR，时间形用 CER。

## 为什么 R138 的 v1 只是"碰巧对"

R138：`X_est = X_model · (OUR_meas/OUR_model)^0.60`，86 批 nRMSE 中位 5.69%。
它有效，但 R139-D/E/G 三条证据表明**机制归因错了**：

1. 全局 median r_OUR = **0.844**，median r_CER = **1.039**。
   若模型 X 真偏高 20%，两通道应同比偏高；CER 没有。⇒ OUR 的偏低主要是
   **OUR 导出通道的标度偏差**（`Y_O2_X`/`m_O2_X` 逐批随机，b8=800/200/15 vs 默认 650/160/17.5），
   不是 X 偏高。
2. `log r_CER ~ log(X_lab/X_model)` 斜率 **1.005**（R² 0.699）、
   `log r_OUR ~ ...` 斜率 **1.420**（R² 0.433）。
   ⇒ CER 是 X 的**无偏代理**（1:1），OUR 超线性且被标度噪声污染。
3. 批内去均值回归：系数 **OUR +0.043 / CER +0.666**。
   ⇒ 一旦控制批间差异，OUR 对 X 的**时间变化**几乎零信息。

X 的主要误差恰恰是**批内时间结构**（R137：化验峰后 −12.8%，模型 −0.7%），
所以正确的做法是：时间形交给 CER，批级水平才让 OUR 参与。

## v2 形式

    log(X_est/X_model) = a + b·log r_OUR(t) + c·log r_CER(t)

- 若 c≫b 且 c≈1，则等价于"X_est ≈ X_model · r_CER · 一个批级水平修正"，
  这正是上文证据指向的结构。
- 系数用**批级 5 折 CV** 拟合，测试折评估，防止把 86 批的记忆当能力。

## 用法
    python tools/r139_observer_v2.py --all86 --cv
"""
import argparse
import json
import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "platform", ".cache")
DATA = os.path.join(ROOT, "data", "processed", "batches")
OUT = os.path.join(ROOT, "runs", "p3", "r139_observer_v2.json")

RATIO_CLIP = (0.5, 2.0)
SMOOTH_WIN = 9
RATIO_SMOOTH = 5


def load(batch):
    cf = os.path.join(CACHE, f"b{batch:02d}.json")
    if not os.path.exists(cf):
        return None
    d = json.load(open(cf, encoding="utf-8"))
    sim = d["sim"]
    t = np.array(d["t"], float)
    v3 = pd.read_csv(os.path.join(DATA, f"batch_{batch:02d}.csv"))
    tv = pd.to_numeric(v3["time_h"], errors="coerce").to_numpy(float)
    xl = pd.to_numeric(v3["X_offline"], errors="coerce").to_numpy(float)
    m = np.isfinite(xl) & (xl > 2.0)
    if m.sum() < 6:
        return None

    def ch(col, key):
        v = pd.to_numeric(v3[col], errors="coerce").to_numpy(float)
        s = pd.Series(v).rolling(SMOOTH_WIN, center=True, min_periods=2).median().to_numpy()
        vs = np.interp(t, tv, np.where(np.isfinite(s), s, v))   # 对齐到缓存时间轴
        # 裁剪 + 平滑观测比值（同 R138 口径）
        raw = np.clip(vs / np.maximum(np.array(sim[key], float), 1e-9), *RATIO_CLIP)
        return pd.Series(raw).rolling(RATIO_SMOOTH, center=True, min_periods=1).median().to_numpy()

    r_our, r_cer = ch("OUR", "OUR"), ch("CER", "CER")
    tlab = tv[m]
    return dict(b=batch, t=t, xm=np.array(sim["X"], float), tlab=tlab, xlab=xl[m],
                ro_lab=np.interp(tlab, t, r_our), rc_lab=np.interp(tlab, t, r_cer))


def nrmse(x, y):
    return float(np.sqrt(np.mean((x - y) ** 2)) / abs(np.mean(y)) * 100)


def design(rec, extra_level=True):
    """设计矩阵：log r_OUR、log r_CER，可选再加批级水平项（批内中位）。"""
    xm = np.interp(rec["tlab"], rec["t"], rec["xm"])
    y = np.log(np.maximum(rec["xlab"] / np.maximum(xm, 1e-9), 1e-6))
    lo = np.log(np.maximum(rec["ro_lab"], 1e-6))
    lc = np.log(np.maximum(rec["rc_lab"], 1e-6))
    cols = [lo, lc]
    if extra_level:
        # 批级水平：两通道批内中位的对数（常数列，与逐点项共线 → 用去均值形式避免）
        cols = [lo - lo.mean(), lc - lc.mean(), np.full_like(lo, lo.mean()),
                np.full_like(lo, lc.mean())]
    X = np.column_stack(cols) if cols else None
    return X, y, xm


def fit(recs, extra_level=True):
    A = np.vstack([design(r, extra_level)[0] for r in recs])
    Y = np.concatenate([design(r, extra_level)[1] for r in recs])
    coef, *_ = np.linalg.lstsq(A, Y, rcond=None)
    return coef


def predict(rec, coef, extra_level=True):
    A, _, xm = design(rec, extra_level)
    return xm * np.exp(A @ coef), xm


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all86", action="store_true")
    ap.add_argument("--batches", default=None)
    ap.add_argument("--cv", action="store_true")
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()

    if args.all86:
        bs = [int(x) for x in open(os.path.join(ROOT, "runs", "p3", "_golden86.txt")).read().split()]
    elif args.batches:
        bs = [int(x) for x in args.batches.split(",")]
    else:
        bs = sorted(int(f[1:3]) for f in os.listdir(CACHE) if f.startswith("b") and f.endswith("json"))
    recs = [r for r in (load(b) for b in bs) if r]

    base = json.load(open(os.path.join(ROOT, "runs", "p3", "r138_our_observer.json"), encoding="utf-8"))
    r138 = {r["batch"]: r["obs"]["nrmse"] for r in base["rows"]}

    print("=" * 96)
    print(f"R139-H  双通道观测器 v2      n={len(recs)} 批")
    print("=" * 96)

    for extra in (False, True):
        coef = fit(recs, extra)
        if extra:
            print(f"\n  含批级水平项：逐点 OUR {coef[0]:+.3f} / CER {coef[1]:+.3f}"
                  f"；批级 OUR {coef[2]:+.3f} / CER {coef[3]:+.3f}")
        else:
            print(f"\n  仅逐点项：OUR {coef[0]:+.3f} / CER {coef[1]:+.3f}")
        vals = []
        for rec in recs:
            xe, xm = predict(rec, coef, extra)
            vals.append(nrmse(xe, rec["xlab"]))
        vals = np.array(vals)
        tag = "含水平" if extra else "仅逐点"
        print(f"  {tag}：中位 {np.median(vals):5.2f}  p90 {np.percentile(vals,90):5.2f}"
              f"  <15% {(vals<15).sum():2d}  <20% {(vals<20).sum():2d}  >25% {(vals>25).sum():2d}"
              f"  最坏 {vals.max():5.2f}")

    # ---- CV：训练折定系数，测试折评估 ----
    coef_full = fit(recs, True)
    cv_summary = {}
    if args.cv:
        print("\n--- 批级 5 折 CV（训练定系数，测试评估）---")
        test_n, allres = [], []
        for k in range(args.folds):
            tr = [r for r in recs if r["b"] % args.folds != k]
            te = [r for r in recs if r["b"] % args.folds == k]
            c = fit(tr, True)
            v = []
            for rec in te:
                xe, _ = predict(rec, c, True)
                v.append(nrmse(xe, rec["xlab"]))
                allres.extend(list((xe - rec["xlab"]) / abs(np.mean(rec["xlab"])) * 100))
            test_n.extend(v)
            print(f"  fold {k}: 测试 nRMSE 中位 {np.median(v):5.2f}%  n={len(te)}"
                  f"  系数 OUR {c[0]:+.3f} CER {c[1]:+.3f} / 水平 OUR {c[2]:+.3f} CER {c[3]:+.3f}")
        tn = np.array(test_n)
        print(f"  → CV 测试集中位均值 {np.mean([np.median(test_n[i::args.folds]) for i in range(args.folds)]):.2f}%"
              f"；合并中位 {np.median(tn):.2f}%，p90 {np.percentile(tn,90):.2f}%，最坏 {tn.max():.2f}%")
        # I3 覆盖率
        ar = np.array(allres)
        lo, hi = np.percentile(ar, 5), np.percentile(ar, 95)
        print(f"  90% 经验区间 [{lo:+.2f}%, {hi:+.2f}%]，逐点覆盖率 {np.mean((ar>=lo)&(ar<=hi))*100:.2f}%")
        cv_summary = {"nrmse_med_test": float(np.median(tn)),
                      "nrmse_p90_test": float(np.percentile(tn, 90)),
                      "ci_level": 0.90, "ci_lo_pct": round(float(lo), 2),
                      "ci_hi_pct": round(float(hi), 2),
                      "coverage": round(float(np.mean((ar >= lo) & (ar <= hi))), 4)}

    # ---- 终评：v2 vs R138 v1 vs A 档 ----
    print("\n--- 终评（86 批）---")
    v1 = np.array([r138.get(rec["b"], np.nan) for rec in recs])
    v2 = np.array([nrmse(predict(rec, coef_full, True)[0], rec["xlab"]) for rec in recs])
    v0 = np.array([nrmse(np.interp(rec["tlab"], rec["t"], rec["xm"]), rec["xlab"]) for rec in recs])
    print(f"  {'方案':<16s}{'中位':>8s}{'p90':>8s}{'<15%':>7s}{'<20%':>7s}{'>25%':>7s}{'最坏':>8s}")
    for nm, a in (("A 模型", v0), ("B v1(OUR^0.6)", v1), ("B v2(双通道)", v2)):
        print(f"  {nm:<16s}{np.nanmedian(a):8.2f}{np.nanpercentile(a,90):8.2f}"
              f"{np.nansum(a<15):7d}{np.nansum(a<20):7d}{np.nansum(a>25):7d}{np.nanmax(a):8.2f}")
    worse = [(rec["b"], b, a) for rec, a, b in zip(recs, v2, v1) if np.isfinite(b) and a - b > 3]
    better = [rec["b"] for rec, a, b in zip(recs, v2, v1) if np.isfinite(b) and b - a > 3]
    print(f"\n  v2 相对 v1 改善 >3pt 的批：{len(better)}；恶化 >3pt：{len(worse)}")
    if worse:
        txt = ", ".join(f"b{bb}({o:.1f}→{n:.1f})" for bb, o, n in worse[:10])
        print(f"  恶化批：{txt}")

    # ---- Part I：可解释的两参数结构（批级=OUR 定标度，逐点=CER 定时间形）----
    print("\n" + "=" * 96)
    print("R139-I  结构化版本：log(X_est/X_model) = p·mean(log r_OUR) + q·(log r_CER − mean(log r_CER))")
    print("=" * 96)
    A, Y = [], []
    for rec in recs:
        lo = np.log(np.maximum(rec["ro_lab"], 1e-6))
        lc = np.log(np.maximum(rec["rc_lab"], 1e-6))
        xm = np.interp(rec["tlab"], rec["t"], rec["xm"])
        A.append(np.column_stack([np.full_like(lo, lo.mean()), lc - lc.mean()]))
        Y.append(np.log(np.maximum(rec["xlab"] / np.maximum(xm, 1e-9), 1e-6)))
    A, Y = np.vstack(A), np.concatenate(Y)
    pq, *_ = np.linalg.lstsq(A, Y, rcond=None)
    print(f"  p（批级 OUR）= {pq[0]:+.3f}   q（逐点 CER）= {pq[1]:+.3f}")

    def pred_struct(rec, pq):
        lo = np.log(np.maximum(rec["ro_lab"], 1e-6))
        lc = np.log(np.maximum(rec["rc_lab"], 1e-6))
        xm = np.interp(rec["tlab"], rec["t"], rec["xm"])
        return xm * np.exp(pq[0] * lo.mean() + pq[1] * (lc - lc.mean()))

    v3 = np.array([nrmse(pred_struct(rec, pq), rec["xlab"]) for rec in recs])
    print(f"  86 批：中位 {np.median(v3):5.2f}  p90 {np.percentile(v3,90):5.2f}"
          f"  <15% {(v3<15).sum():2d}  <20% {(v3<20).sum():2d}  >25% {(v3>25).sum():2d}  最坏 {v3.max():5.2f}")
    print("  5 折 CV：")
    cv3 = []
    for k in range(5):
        tr = [r for r in recs if r["b"] % 5 != k]
        te = [r for r in recs if r["b"] % 5 == k]
        Atr = np.vstack([np.column_stack([
            np.full_like(np.log(np.maximum(r["ro_lab"], 1e-6)), np.log(np.maximum(r["ro_lab"], 1e-6)).mean()),
            np.log(np.maximum(r["rc_lab"], 1e-6)) - np.log(np.maximum(r["rc_lab"], 1e-6)).mean()]) for r in tr])
        Ytr = np.concatenate([np.log(np.maximum(r["xlab"] / np.maximum(
            np.interp(r["tlab"], r["t"], r["xm"]), 1e-9), 1e-6)) for r in tr])
        c, *_ = np.linalg.lstsq(Atr, Ytr, rcond=None)
        vv = [nrmse(pred_struct(r, c), r["xlab"]) for r in te]
        cv3.extend(vv)
        print(f"    fold {k}: 中位 {np.median(vv):5.2f}%  p={c[0]:+.3f} q={c[1]:+.3f}  n={len(te)}")
    cv3 = np.array(cv3)
    print(f"  → CV 合并中位 {np.median(cv3):.2f}%，p90 {np.percentile(cv3,90):.2f}%，最坏 {cv3.max():.2f}%")
    cv_struct = {"nrmse_med_test": float(np.median(cv3)),
                 "nrmse_p90_test": float(np.percentile(cv3, 90)),
                 "nrmse_max_test": float(cv3.max())}

    # ---- 最坏批诊断 ----
    print("\n--- 最坏批（v2 与结构化版本）---")
    order = np.argsort(-v2)[:6]
    print(f"  {'批':>4s}{'模型':>8s}{'v1':>8s}{'v2':>8s}{'结构化':>9s}")
    worst_info = []
    for i in order:
        rec = recs[i]
        print(f"  b{rec['b']:<3d}{v0[i]:8.2f}{v1[i]:8.2f}{v2[i]:8.2f}{v3[i]:9.2f}")
        worst_info.append({"b": rec["b"], "n_model": float(v0[i]), "n_v1": float(v1[i]),
                           "n_v2": float(v2[i]), "n_struct": float(v3[i])})

    # ---- Part J：门控 + 最终交付指标 ----
    print("\n" + "=" * 96)
    print("R139-J  门控：批级 r_OUR 水平极端离群 → 判定通道标度不可辨识，回退 A 档并报警")
    print("=" * 96)
    g0 = float(np.median([np.median(np.exp(np.log(np.maximum(r["ro_lab"], 1e-6)))) for r in recs]))
    J1 = np.array([abs(np.log(np.median(np.maximum(rec["ro_lab"], 1e-6)) / g0)) for rec in recs])
    print(f"  全局 g0 = {g0:.4f}（86 批批级 r_OUR 中位的中位）")
    for thr in (0.30, 0.35, 0.40, 0.45, 0.50):
        flag = J1 > thr
        trig = [recs[i]["b"] for i in np.where(flag)[0]]
        print(f"  阈值 {thr:.2f}（r_OUR_bar 落在 [{g0*np.exp(-thr):.3f}, {g0*np.exp(thr):.3f}] 之外）"
              f" → 触发 {len(trig)} 批：{trig}")
    THR = 0.45
    flag = J1 > THR
    final = np.where(flag, v0, v2)
    print(f"\n  采用阈值 {THR:.2f}；回退批：{[recs[i]['b'] for i in np.where(flag)[0]]}")
    print(f"\n  {'方案':<22s}{'中位':>8s}{'p90':>8s}{'<10%':>7s}{'<15%':>7s}{'<20%':>7s}{'最坏':>8s}")
    for nm4, a in (("A 档机理", v0), ("B v1 (R138, OUR^0.6)", v1),
                   ("B v2 (双通道)", v2), ("B v2 + 门控回退", final)):
        print(f"  {nm4:<22s}{np.nanmedian(a):8.2f}{np.nanpercentile(a,90):8.2f}"
              f"{np.nansum(a<10):7d}{np.nansum(a<15):7d}{np.nansum(a<20):7d}{np.nanmax(a):8.2f}")

    json.dump({"meta": {"n": len(recs), "coef": list(map(float, coef_full)),
                        "pq": list(map(float, pq)), "g0": g0, "gate_thr": THR,
                        "gate_reason": "批级 r_OUR 水平离群 ⇒ 通道标度不可辨识 ⇒ 回退 A 档",
                        "form": "log(X_est/X_model)=p*mean(log r_OUR)+q*(log r_CER-mean) [结构化]；"
                                "四系数版见 coef",
                        "cv": cv_summary, "cv_struct": cv_struct,
                        "ratio_clip": RATIO_CLIP},
               "worst": worst_info,
               "rows": [{"b": rec["b"], "n_model": float(v0[i]), "n_v1": float(v1[i]),
                         "n_v2": float(v2[i]), "n_struct": float(v3[i]),
                         "J1": float(J1[i]), "gated": bool(flag[i]),
                         "n_final": float(final[i])}
                        for i, rec in enumerate(recs)]},
              open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n已写入 {args.out}")


if __name__ == "__main__":
    main()
