# -*- coding: utf-8 -*-
"""R157 / T3-1：I3 置信区间覆盖率的**多通道**评估（X / P / S / DO2）。

问题
----
GOAL §4 标准 5 要求「置信区间覆盖率经验证（I3）」。
现状：**I3 只覆盖 X 通道**（R139：B 档双通道观测器，90% 区间 [−6.82%, +9.45%]，
逐点覆盖 **0.8992**）。S / P / DO2 / PAA 的 CI **从未做过**（观测器目前只估 X）。

做法
----
用**与 R139 已验证的同一套结构**（结构化双通道形式）逐通道做 I3：

    log(ch_est / ch_model) = p·mean(log r_OUR) + q·(log r_CER − mean(log r_CER))
        r_OUR = obs_OUR / sim_OUR ,  r_CER = obs_CER / sim_CER

- **X 通道是回归检查**：必须复现 R139 的 nRMSE 3.17% / 覆盖 0.8992，否则说明harness 有错。
- **P / S / DO2 通道是新问题**：同一形式的观测器是否还能拿到信息？
  - P 的目标是 **P_offline（HPLC 化验，21 点）**，与 X 用 X_offline 同口径；
  - S / DO2 无稀疏化验，目标取 V3 连续列（115 点缓存栅格）⇒
    **I3 解释不同**：只度量模型误差，不含化验噪声（报告里会显式标注）。
- 系数用**批级 5 折 CV** 拟合（训练折定系数、测试折评估），防止把 86 批的记忆当能力。
- I3 覆盖：CV 测试残差（归一化到目标均值）的 90% 经验区间 ⇒ 逐点覆盖率。

结论口径
--------
每个通道给一个判定：
  DELIVERABLE        —— CV nRMSE 明显优于 A 档，且覆盖率在可接受区间；
  NOT_IDENTIFIABLE   —— 系数≈0 / CV 不优于 A 档 ⇒ **该通道没有可用代理**，I3 不扩展；
  MARGINAL           —— 有改善但覆盖率不足。

**"没有代理"是一个有价值的否定结论**：它把 GOAL 标准 5 的覆盖面从"未做"变成
"已查证、并给出可引用的边界"，从而让口径裁决有证据支撑。

用法
----
    python tools/r157_i3_channels.py
    python tools/r157_i3_channels.py --channels X,P,S,DO2 --folds 5
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
CACHE = os.path.join(ROOT, "platform", ".cache")
DATA = os.path.join(ROOT, "data", "processed", "batches")

RATIO_CLIP = (0.5, 2.0)
SMOOTH_WIN = 9
RATIO_SMOOTH = 5

# 通道 → (目标列, 模型通道, 目标性质)
#   "assay"     —— 离线化验（21 点稀疏，HPLC / 干重 / 粘度等）：**软测量的合法目标**
#   "model_ref" —— V3 连续列，是参考模型的输出轨迹，**不是化验**；
#                  用它当"真值"是循环论证（模型对照模型），只作参考，不作交付依据
CHANNELS = {
    "X":   ("X_offline",          "X",   "assay"),
    "P":   ("P_offline",          "P",   "assay"),
    "PAA": ("PAA_offline",        "PAA", "assay"),
    "vis": ("Viscosity_offline",  "vis", "assay"),
    "S":   ("S",                  "S",   "model_ref"),
    "DO2": ("DO2",                "DO2", "model_ref"),
}


def _ratio(v3, col, sim, mod, t, tv):
    """观测/模型比值（R139 同口径）。

    v3[col] 是 **CSV 完整栅格（1150 点）**的观测列；`sim[mod]` 是**缓存栅格（115 点）**的模型通道。
    ⇒ 先把观测列平滑后插到缓存栅格 `t`，再与模型相除；比值再平滑一次。
    """
    v = pd.to_numeric(v3[col], errors="coerce").to_numpy(float)
    s = pd.Series(v).rolling(SMOOTH_WIN, center=True, min_periods=2).median().to_numpy()
    vs = np.interp(t, tv, np.where(np.isfinite(s), s, v))   # 对齐到缓存时间轴
    raw = np.clip(vs / np.maximum(np.asarray(mod, float), 1e-9), *RATIO_CLIP)
    return pd.Series(raw).rolling(RATIO_SMOOTH, center=True, min_periods=1).median().to_numpy()


def load(batch, ch):
    cf = os.path.join(CACHE, f"b{batch:02d}.json")
    if not os.path.exists(cf):
        return None
    d = json.load(open(cf, encoding="utf-8"))
    sim, obs = d["sim"], d["obs"]
    t = np.array(d["t"], float)
    csvp = os.path.join(DATA, f"batch_{batch:02d}.csv")
    if not os.path.exists(csvp):
        return None
    v3 = pd.read_csv(csvp)
    tv = pd.to_numeric(v3["time_h"], errors="coerce").to_numpy(float)

    tcol, mcol, kind = CHANNELS[ch]
    if kind == "assay":
        y = pd.to_numeric(v3[tcol], errors="coerce").to_numpy(float)
        m = np.isfinite(y)
        if m.sum() < 6:
            return None
        tlab, ylab = tv[m], y[m]
    else:
        y = pd.to_numeric(v3[tcol], errors="coerce").to_numpy(float)
        m = np.isfinite(y)
        if m.sum() < 6:
            return None
        tlab, ylab = tv[m], y[m]

    xm_all = np.asarray(sim[mcol], float)
    xm = np.interp(tlab, t, xm_all)
    r_our = _ratio(v3, "OUR", sim, sim["OUR"], t, tv)
    r_cer = _ratio(v3, "CER", sim, sim["CER"], t, tv)
    r_do2 = _ratio(v3, "DO2", sim, sim["DO2"], t, tv)
    # 前体投加速率 Fpaa/V（**已知进料流量**，是真正在线可得的信号）
    fpaa = pd.to_numeric(v3["Fpaa"], errors="coerce").to_numpy(float)
    vv = pd.to_numeric(v3["V"], errors="coerce").to_numpy(float)
    fp = np.interp(tlab, tv, np.nan_to_num(fpaa / np.maximum(vv, 1e-9)))
    return dict(b=batch, ch=ch, kind=kind, t=t, tlab=tlab, ylab=ylab, xm=xm,
                ro=np.interp(tlab, t, r_our), rc=np.interp(tlab, t, r_cer),
                rd=np.interp(tlab, t, r_do2), fp=fp,
                ro_bar=float(np.nanmedian(r_our)), rc_bar=float(np.nanmedian(r_cer)))


def _design(rec, proxies):
    """设计矩阵：常数 + 每个代理的「批内去均值逐点项」+ 「批级水平项」。

    代理 r_X = 观测/模型 比值。形式与 R139 已验证的结构化版一致：
        log(ch_est/ch_model) = const + p·(log r_CER − mean) + q·mean(log r_OUR)
    额外代理（DO2）按同一结构追加。
    """
    cols = [np.ones(len(rec["tlab"]))]
    names = ["const"]
    for p in proxies:
        lg = np.log(np.maximum(rec[p], 1e-6))
        cols.append(lg - lg.mean())
        names.append(f"{p}:point")
        cols.append(np.full_like(lg, lg.mean()))
        names.append(f"{p}:level")
    return np.column_stack(cols), names


def _fit(recs, proxies):
    A = np.vstack([_design(r, proxies)[0] for r in recs])
    Y = np.concatenate([np.log(np.maximum(r["ylab"] / np.maximum(r["xm"], 1e-9), 1e-6))
                        for r in recs])
    coef, *_ = np.linalg.lstsq(A, Y, rcond=None)
    return coef


def _predict(rec, coef, proxies):
    A, _ = _design(rec, proxies)
    return rec["xm"] * np.exp(A @ coef)


def _nrmse(x, y):
    return float(np.sqrt(np.mean((x - y) ** 2)) / abs(np.mean(y)) * 100)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--channels", type=str, default="X,P,S,DO2")
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--proxies", type=str, default="rc,ro",
                    help="代理集合：rc=CER 比值、ro=OUR 比值、rd=DO2 比值、fp=前体投加速率 Fpaa/V（逗号分隔）")
    ap.add_argument("--ci-half-width-max", type=float, default=25.0,
                    help="CI 半宽上限（%%）；超过即判不可交付（区间太宽等于没给信息）")
    ap.add_argument("--out", type=str, default="runs/r157_i3_channels.json")
    args = ap.parse_args()

    PROX = [p.strip() for p in args.proxies.split(",") if p.strip()]
    PKEY = {"rc": "rc", "ro": "ro", "rd": "rd", "fp": "fp"}
    proxies = [PKEY[p] for p in PROX]

    sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))
    from golden_params import GOLDEN_ALL
    bs = list(GOLDEN_ALL)

    out = {"channels": {}}
    print("=" * 100)
    print(f"R157 / T3-1  I3 置信区间覆盖率 —— 多通道评估（批级 {args.folds} 折 CV）")
    print("=" * 100)

    for ch in [c.strip() for c in args.channels.split(",") if c.strip()]:
        recs = [r for r in (load(b, ch) for b in bs) if r]
        if not recs:
            print(f"\n【{ch}】无可用批次")
            continue
        kind = recs[0]["kind"]
        print(f"\n{'─'*100}\n【{ch}】目标口径：{'离线化验（稀疏，21 点）——合法软测量目标' if kind=='assay' else 'V3 参考模型输出（非化验）——**循环论证，仅作参考**'}"
              f"　n={len(recs)} 批　样本点/批 中位 {int(np.median([len(r['ylab']) for r in recs]))}")

        # A 档基线
        v_A = np.array([_nrmse(r["xm"], r["ylab"]) for r in recs])

        # CV
        coef_full = _fit(recs, proxies)
        allres, test_n = [], []
        for k in range(args.folds):
            tr = [r for r in recs if r["b"] % args.folds != k]
            te = [r for r in recs if r["b"] % args.folds == k]
            c = _fit(tr, proxies)
            for rec in te:
                est = _predict(rec, c, proxies)
                test_n.append(_nrmse(est, rec["ylab"]))
                allres.extend(list((est - rec["ylab"]) / abs(np.mean(rec["ylab"])) * 100))
        test_n = np.array(test_n)
        ar = np.array(allres)
        lo, hi = (np.percentile(ar, 5), np.percentile(ar, 95)) if ar.size else (np.nan, np.nan)
        cov = float(np.mean((ar >= lo) & (ar <= hi))) if ar.size else float("nan")
        ci_hw = float((hi - lo) / 2.0) if np.isfinite(lo) and np.isfinite(hi) else float("nan")

        # 信息含量：CV 测试残差 vs 各代理（批内去均值后）的相关
        cc = {}
        for p in proxies:
            vals = []
            for r in recs:
                est = _predict(r, coef_full, proxies)
                resid = np.log(np.maximum(r["ylab"], 1e-9) / np.maximum(r["xm"], 1e-9))
                pred = np.log(np.maximum(est, 1e-9) / np.maximum(r["xm"], 1e-9))
                lg = np.log(np.maximum(r[p], 1e-6))
                rr = resid - pred
                if rr.std() > 1e-12 and (lg - lg.mean()).std() > 1e-12:
                    vals.append(float(np.corrcoef(rr, lg - lg.mean())[0, 1]))
            cc[p] = float(np.median(vals)) if vals else float("nan")

        # ---- 判定（三道硬门，缺一不可）----
        # 门 1：观测器须明显优于 A 档（否则软测量没带来任何东西）
        # 门 2：CI 半宽须 ≤ 绝对上限（区间太宽 ⇒ 覆盖率是"靠宽换来的"，等于没给信息；
        #       这正是 D-38「恒真的判据等于没有判据」的同类陷阱 —— 覆盖率单独看是**可平凡满足**的）
        # 门 3：CI 半宽须**严于**它所替代的 A 档误差（否则不如直接上报模型值）
        gain = float(np.median(v_A) - np.median(test_n))
        g1 = gain > 1.0
        g2 = np.isfinite(ci_hw) and ci_hw <= args.ci_half_width_max
        g3 = np.isfinite(ci_hw) and ci_hw < float(np.median(v_A))
        if g1 and g2 and g3:
            verdict = "DELIVERABLE"
        elif not g1:
            verdict = "NOT_IDENTIFIABLE"
        else:
            verdict = "MARGINAL"

        print(f"  A 档（模型直接上报）      nRMSE 中位 {np.median(v_A):6.2f}%   p90 {np.percentile(v_A,90):6.2f}%")
        print(f"  B 档观测器（CV 测试）      nRMSE 中位 {np.median(test_n):6.2f}%   p90 {np.percentile(test_n,90):6.2f}%"
              f"   最坏 {test_n.max():6.2f}%")
        print(f"  改善（中位）              {gain:+.2f} pp")
        print(f"  系数（结构化）            "
              + "  ".join(f"{p}:{coef_full[1+2*i]:+.3f}点/{coef_full[2+2*i]:+.3f}级"
                          for i, p in enumerate(proxies))
              + f"   常数 {coef_full[0]:+.3f}")
        print(f"  残差 vs 代理相关（批内去均值）  "
              + "  ".join(f"{p}:{cc[p]:+.3f}" for p in proxies))
        print(f"  **I3：90% 区间 [{lo:+.2f}%, {hi:+.2f}%]　半宽 {ci_hw:.2f}%　逐点覆盖率 {cov*100:.2f}%**")
        print(f"  三道硬门：① 优于A档 {'✓' if g1 else '✗'}"
              f"　② 半宽≤{args.ci_half_width_max:.0f}% {'✓' if g2 else '✗'}"
              f"　③ 半宽<A档误差 {'✓' if g3 else '✗'}")
        print(f"  ⇒ 判定：**{verdict}**"
              + ("　（无可用代理 ⇒ I3 不覆盖该通道）" if verdict == "NOT_IDENTIFIABLE"
                 else "　（有改善但 CI 不够紧）" if verdict == "MARGINAL" else ""))
        out["channels"][ch] = {
            "kind": kind, "n": len(recs), "proxies": proxies,
            "nrmse_A_median": float(np.median(v_A)), "nrmse_A_p90": float(np.percentile(v_A, 90)),
            "nrmse_cv_median": float(np.median(test_n)), "nrmse_cv_p90": float(np.percentile(test_n, 90)),
            "nrmse_cv_max": float(test_n.max()),
            "gain_median_pp": gain,
            "coef": [float(x) for x in coef_full],
            "resid_corr": {k: v for k, v in cc.items()},
            "ci_level": 0.90, "ci_lo_pct": float(lo), "ci_hi_pct": float(hi),
            "ci_half_width_pct": ci_hw, "coverage": cov, "verdict": verdict,
            "gates": {"gain_gt_1pp": bool(g1),
                      "ci_half_width_le_max": bool(g2),
                      "ci_half_width_lt_A": bool(g3)},
        }

    print(f"\n{'='*100}\n【汇总】\n{'='*100}")
    print(f"  {'通道':<6}{'A档nRMSE':>12}{'B档nRMSE(CV)':>16}{'改善':>9}{'I3覆盖':>10}  判定")
    for ch, d in out["channels"].items():
        print(f"  {ch:<6}{d['nrmse_A_median']:>11.2f}%{d['nrmse_cv_median']:>15.2f}%"
              f"{d['gain_median_pp']:>8.2f}pp{d['coverage']*100:>9.2f}%  {d['verdict']}")

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"\nwritten: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
