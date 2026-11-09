# -*- coding: utf-8 -*-
"""R138：碳平衡观测器（elemental-balance soft sensor）反演生物量 X。

## 为什么换范式

R134–R137 一直在 A 档（正问题）里改 ODE 结构 / 调动力学常数，结论是「X 通道在现有
参数域内 parametric-infeasible」——因为 86 批是逐批独立的随机参数，任何全局常数都会
改坏本来准的批（R137: 28 双改善 vs 45 破线）。

但 GOAL.md §3 早就把这件事划给了 **B 档软测量（逆问题）**：
    "B 软测量 —— UKF/EnKF/MHE + 稳态碳平衡基线"

本工具实现的正是「稳态碳平衡基线」的**动态累积版本**，即渐进观测器
（asymptotic observer, Bastin & Dochain）的碳形式：

    d(V·C_vessel)/dt = C_feed - C_removed - C_respired

    C_vessel = S·f_s + X·f_X + P·f_P + PAA·f_paa      (gC/L)
    C_feed   = Fs·c_s·f_s + Foil·c_oil·f_oil + Fpaa·c_paa·f_paa
    C_removed= (-Fremoved)·C_vessel                    (Fremoved<0 表示移出)
    C_respired = CER·V·(12/44)                         (CER 是 g/L/h 的 CO2 质量速率)

**关键性质：X 方程里不含任何动力学参数**（没有 mux/mup/kd/death_start）。
X 只由「进了多少碳 - 呼吸掉多少碳 - 移走多少碳 - 变成产物多少碳」决定。

这正是绕开 R137 死结的地方：不需要为 86 批各拍一组常数，因为压根没有常数要拍。

## 两个模式

- `--p-source lab` ：P 用化验插值。这是**数据自洽性检验**——若反演出的 X 能对上
  X_offline，说明碳平衡闭合、且这条路能给出可信的 X 轨迹。
- `--p-source sim` ：P 用模型预测。这是**真盲反演**，用于回答"模型 P 对不对"。

## 用法
    python tools/r138_carbon_observer.py --batches 8,29,56 --p-source lab
    python tools/r138_carbon_observer.py --all86 --p-source lab --jobs 8
"""
import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))

# —— 与 conservation_metrics.py 登记的同一套常数（T7），此处 import 保持单一来源 ——
from conservation_metrics import (  # noqa: E402
    C_S, C_OIL, C_PAA, CF_GLC, CF_OIL, CF_PAA, CF_P, CF_X,
)

_TRAPZ = getattr(np, "trapezoid", None) or np.trapz

OUT = os.path.join(ROOT, "runs", "p3", "r138_carbon_observer.json")


# --------------------------------------------------------------------------- 核心
def carbon_balance2(df, p_series=None, x_init=None, t_init=None,
                    include_paa=True, include_removed=True):
    """累积碳平衡反演 X(t) —— 主实现。"""
    t_all = pd.to_numeric(df["time_h"], errors="coerce").to_numpy(float)
    ok = np.isfinite(t_all)
    t = t_all[ok]
    n = len(t)

    def col(name, fill=0.0):
        v = pd.to_numeric(df[name], errors="coerce").to_numpy(float)[ok]
        return np.where(np.isfinite(v), v, fill)

    Fs, Foil, Fpaa = col("Fs"), col("Foil"), col("Fpaa")
    Frm = col("Fremoved")
    V = col("V", np.nan)
    CER, S = col("CER"), col("S")
    good = np.isfinite(V) & (V > 0)
    if not good.all():
        V = np.interp(t, t[good], V[good])

    # 游离 PAA（mg/L → g/L）
    if include_paa and "PAA_offline" in df.columns:
        paa = pd.to_numeric(df["PAA_offline"], errors="coerce").to_numpy(float)[ok]
        mp = np.isfinite(paa)
        PAA = np.interp(t, t[mp], paa[mp]) / 1000.0 if mp.sum() >= 2 else np.zeros(n)
    else:
        PAA = np.zeros(n)

    if p_series is None:
        pl = pd.to_numeric(df["P_offline"], errors="coerce").to_numpy(float)[ok]
        mp = np.isfinite(pl)
        P = np.interp(t, t[mp], pl[mp]) if mp.sum() >= 2 else np.zeros(n)
        p_src = "lab"
    else:
        P = np.asarray(p_series, float)[:n]
        p_src = "ext"

    if x_init is None or t_init is None:
        xl = pd.to_numeric(df["X_offline"], errors="coerce").to_numpy(float)[ok]
        mi = np.isfinite(xl)
        if mi.sum() == 0:
            raise ValueError("no X_offline to anchor")
        i0 = int(np.argmax(mi))
        x_init, t_init = float(xl[i0]), float(t[i0])
    else:
        i0 = int(np.argmin(np.abs(t - t_init)))

    # 瞬时碳通量 (gC/h)
    q_in = Fs * C_S * CF_GLC + Foil * C_OIL * CF_OIL + Fpaa * C_PAA * CF_PAA / 1000.0
    q_resp = CER * V * (12.0 / 44.0)
    c_vessel = S * CF_GLC + P * CF_P + PAA * CF_PAA          # gC/L（不含 X）
    q_rm = (-Frm) * c_vessel if include_removed else np.zeros(n)   # Frm<0 → 正移出

    # 累积（梯形）
    def cum(y):
        out = np.zeros(n)
        out[1:] = np.cumsum((y[1:] + y[:-1]) * 0.5 * np.diff(t))
        return out

    C_in, C_resp, C_rm = cum(q_in), cum(q_resp), cum(q_rm)

    # X(t0) 的罐内碳
    X0 = float(x_init)
    C_X0 = X0 * CF_X * V[i0]

    # X 的碳量 = 初值 + 进 - 呼吸 - 移出 - 非 X 部分的变化
    C_X = C_X0 + (C_in - C_in[i0]) - (C_resp - C_resp[i0]) - (C_rm - C_rm[i0]) \
          - (c_vessel * V - c_vessel[i0] * V[i0])
    X = C_X / (CF_X * V)

    # ---- 闭合诊断：碳去哪了 ----
    diag = {
        "n": int(n),
        "t_span": [float(t[0]), float(t[-1])],
        "C_in_total": float(C_in[-1] - C_in[0]),
        "C_resp_total": float(C_resp[-1] - C_resp[0]),
        "C_removed_total": float(C_rm[-1] - C_rm[0]),
        "C_P_change": float((P[-1] * V[-1] - P[0] * V[0]) * CF_P),
        "C_S_change": float((S[-1] * V[-1] - S[0] * V[0]) * CF_GLC),
        "frac_resp": None, "frac_X": None,
    }
    net = diag["C_in_total"] - diag["C_resp_total"] - diag["C_removed_total"]
    if abs(diag["C_in_total"]) > 1e-9:
        diag["frac_resp"] = round(diag["C_resp_total"] / diag["C_in_total"], 4)
    xl = pd.to_numeric(df["X_offline"], errors="coerce").to_numpy(float)[ok]
    diag["C_X_change"] = float((X[-1] * V[-1] - X[i0] * V[i0]) * CF_X)
    if abs(net) > 1e-9:
        diag["frac_X"] = round(diag["C_X_change"] / net, 4)
    diag["p_source"] = p_src
    return {"t": t, "X": X, "X0": X0, "t0": float(t[i0]), "diag": diag,
            "P": P, "V": V, "CER": CER}


# --------------------------------------------------------------------------- 对比
def compare_to_lab(t, X, df, x_col="X_offline"):
    """把反演 X 与化验 X 在化验时刻上比较（不插值、不用化验值做锚以外的任何事）。"""
    tl = pd.to_numeric(df["time_h"], errors="coerce").to_numpy(float)
    xl = pd.to_numeric(df[x_col], errors="coerce").to_numpy(float)
    m = np.isfinite(xl) & np.isfinite(tl)
    tl, xl = tl[m], xl[m]
    if len(tl) < 3:
        return None
    xs = np.interp(tl, t, X)
    # 首个锚点必然完全相等，去掉它以免虚高 R2
    ttl, xxl, xxs = tl[1:], xl[1:], xs[1:]
    if len(ttl) < 2:
        return None
    res = xxs - xxl
    mo = abs(np.mean(xxl))
    ss_tot = float(np.sum((xxl - xxl.mean()) ** 2))
    ss_res = float(np.sum(res ** 2))
    return {
        "n_pts": int(len(ttl)),
        "nrmse": round(float(np.sqrt(np.mean(res ** 2)) / mo * 100.0), 2),
        "bias_pct": round(float(res.mean() / mo * 100.0), 2),
        "r2": round(1.0 - ss_res / ss_tot, 4) if ss_tot > 1e-12 else None,
        # 首末结构量：峰比 / 末端比 / 峰后斜率差
        "end_ratio": round(float(xxs[-1] / xxl[-1]), 3) if abs(xxl[-1]) > 1e-9 else None,
        "peak_ratio": round(float(xxs.max() / xxl.max()), 3) if abs(xxl.max()) > 1e-9 else None,
        "curve": [[round(float(a), 1), round(float(b), 2), round(float(c), 2), round(float(c / b), 3)]
                  for a, b, c in zip(ttl, xxl, xxs)],
    }


def run_batch(batch, p_source="lab"):
    d = pd.read_csv(os.path.join(ROOT, "data", "processed", "batches", f"batch_{batch:02d}.csv"))
    P_ext = None
    if p_source == "sim":
        # 用引擎预测的 P 替代化验
        sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))
        import golden_params as gp
        from simulate import simulate_open_loop
        sim, _ = simulate_open_loop(batch, gp.params_for(batch))
        ts = sim["time_h"].to_numpy(float)
        t = pd.to_numeric(d["time_h"], errors="coerce").to_numpy(float)
        P_ext = np.interp(t, ts, sim["P"].to_numpy(float))

    cb = carbon_balance2(d, p_series=P_ext)
    cmp_res = compare_to_lab(cb["t"], cb["X"], d)
    return {"batch": batch, "p_source": p_source, "diag": cb["diag"], "vs_lab": cmp_res}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", default="8,29,56")
    ap.add_argument("--all86", action="store_true")
    ap.add_argument("--p-source", choices=["lab", "sim"], default="lab")
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    bs = ([int(x) for x in open(os.path.join(ROOT, "runs", "p3", "_golden86.txt")).read().split()]
          if args.all86 else [int(x) for x in args.batches.split(",")])

    rows = []
    for b in bs:
        try:
            r = run_batch(b, args.p_source)
        except Exception as e:
            print(f"  ! b{b}: {e}")
            continue
        rows.append(r)
        v = r["vs_lab"]
        if v and args.verbose:
            print(f"b{b:<4d} nRMSE {v['nrmse']:6.2f}%  bias {v['bias_pct']:+7.2f}%  "
                  f"R2 {v['r2']}  peakR {v['peak_ratio']}  endR {v['end_ratio']}")

    ok = [r for r in rows if r["vs_lab"]]
    print(f"\n=== 碳平衡反演 X vs 化验 X（{len(ok)}/{len(rows)} 批，P 来源={args.p_source}）===")
    if ok:
        nr = [r["vs_lab"]["nrmse"] for r in ok]
        r2 = [r["vs_lab"]["r2"] for r in ok if r["vs_lab"]["r2"] is not None]
        pk = [r["vs_lab"]["peak_ratio"] for r in ok if r["vs_lab"]["peak_ratio"]]
        en = [r["vs_lab"]["end_ratio"] for r in ok if r["vs_lab"]["end_ratio"]]
        fr = [r["diag"]["frac_resp"] for r in ok if r["diag"]["frac_resp"] is not None]
        print(f"nRMSE  中位 {np.median(nr):6.2f}%  p25 {np.percentile(nr,25):6.2f}  "
              f"p75 {np.percentile(nr,75):6.2f}  min {np.min(nr):6.2f}  max {np.max(nr):6.2f}")
        print(f"R2     中位 {np.median(r2):.4f}" if r2 else "R2  n/a")
        print(f"peakR  中位 {np.median(pk):.3f}   endR 中位 {np.median(en):.3f}")
        print(f"呼吸占总进料碳 中位 {np.median(fr)*100:.1f}%  → 碳是主要去向" if fr else "")
        print(f"nRMSE<15% 的批: {sum(1 for x in nr if x < 15)}/{len(nr)} ; <25%: {sum(1 for x in nr if x < 25)}")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"meta": {"p_source": args.p_source, "n": len(rows)}, "rows": rows},
                  f, ensure_ascii=False, indent=1)
    print(f"\n已写入 {args.out}")


if __name__ == "__main__":
    main()
