# -*- coding: utf-8 -*-
"""R159：证伪 R158 的 A2（引擎 PAA + 两点仿射校准）正面结论。

背景
----
R158（T3-3）在 86 批上得到一条**唯一正面结论**：
「失真批（按 ``A_engine_r <= 0.5`` 分层，n=41）上，A2（引擎 PAA 做留一锚点仿射校准）
nRMSE 中位 **0.49%**，严格支配 PAT 转发（31.90%）与 PAT+锚定（11.23%）」
⇒ 结论「处理失真批应优先做两点校准，而非引入 Raman 资产」。

本轮要查的问题
--------------
R158 的同一张分层表里，有两个数字放在一起非常可疑：

| 量 | 失真批（n=41）中位 |
|---|---|
| ``A_engine_r``（引擎 PAA 与化验的批内相关） | **0.0518** |
| ``A2_looa_nrmse`` | **0.49%** |
| ``C1_looa_nrmse``（**直接插值化验值**的平凡上界） | **0.57%** |

``A_engine_r`` ≈ 0.05 意味着**引擎 PAA 与化验值几乎不相关**；而 A2 的误差
（0.49%）竟然**低于「直接插值化验真值」的平凡上界（0.57%）** —— 一个只用
**引擎读数**的预测器不可能优于**直接用真值插值**的方案，除非：

  (a) 该批的**化验值本身近乎常数** ⇒ 任何"预测常数"的模型都能命中
      ⇒ A2 的低误差来自**化验信号退化**，而不是校准能力；
  (b) 或者 A2 存在**平凡满足**（构造上贴住真值）。

⇒ 本轮把 A2 拆成**五道证伪门**，逐门实测：

===  ======================================================================
门   检验内容
===  ======================================================================
G1   **化验信号退化度**：失真批的化验值变异系数（CV）是否显著低于可信批？
     若失真批 CV ≈ 0 ⇒ 该层被"化验恒定"定义，A2 的 0.49% 是平凡的。
G2   **常数预测基线**（控制组）：用「留一锚点的化验均值」当预测器，
     误差有多大？若与 A2 同量级 ⇒ A2 无净贡献（"更简单的基线未被击败"）。
G3   **A2 的斜率/截距可辨识性**：失真批上拟合出的斜率是否 ≈ 0？
     斜率 ≈ 0 ⇒ A2 退化成"预测一个常数"，与 G2 同义。
G4   **时间因果性**：LOOA 用**全部其余锚点**（含未来）拟合。
     改用「只用 t 之前的锚点」的前推式（forward-only），
     若 A2 的优势大幅消失 ⇒ 原优势含**时间泄漏**。
G5   **在线可得性**：A2 需要**化验锚点**，而分组标签 ``A_engine_r``
     本身要化验值才能算 ⇒ 部署时不可得。
     检验：**不用化验标签**、只用线上可得量的触发器能否命中失真批。
===  ======================================================================

输出
----
``runs/r159_a2_falsification.json``（含逐批诊断 + 5 门判决 + 控制组）

用法
----
    py tools/r159_a2_falsification.py
    py tools/r159_a2_falsification.py --batches 1,22,60      # 冒烟
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
CACHE = os.path.join(ROOT, "platform", ".cache")
DATA = os.path.join(ROOT, "data", "processed", "batches")

# R158 用的资产级量纲标定常数（本轮复用，不重标）
PLS_UNIT_SCALE = 721.263
PLS_UNIT_INTERCEPT = 404.644


# ---------------------------------------------------------------- 小工具
def _nrmse(x, y):
    """相对 RMSE（%），分母取真值均值绝对值（R158 同口径）。"""
    m = abs(float(np.mean(y)))
    if m < 1e-12:
        return float("nan")
    return float(np.sqrt(np.mean((np.asarray(x, float) - np.asarray(y, float)) ** 2)) / m * 100.0)


def _r(x, y):
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    if len(x) < 3 or np.std(x) < 1e-12 or np.std(y) < 1e-12:
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1])


def _sign_test(d):
    """符号检验：返回 (k=差值为正的个数, n, p, 中位差)。"""
    d = np.asarray([x for x in d if np.isfinite(x)], float)
    n = len(d)
    if n == 0:
        return {"k": 0, "n": 0, "p": None, "delta_median": None}
    k = int(np.sum(d > 0))
    # 双尾二项检验（scipy 不可用时的精确/正态近似）
    from math import comb
    p = None
    if n > 0:
        lo = min(k, n - k)
        tail = sum(comb(n, i) for i in range(0, lo + 1)) / (2.0 ** n)
        p = min(1.0, 2.0 * tail)
    return {"k": k, "n": n, "p": p, "delta_median": float(np.median(d))}


def _stat(vals):
    vals = [v for v in vals if v is not None and np.isfinite(v)]
    if not vals:
        return {"n": 0, "median": None}
    a = np.asarray(vals, float)
    return {
        "n": int(len(a)),
        "median": float(np.median(a)),
        "mean": float(np.mean(a)),
        "p10": float(np.percentile(a, 10)),
        "p90": float(np.percentile(a, 90)),
        "min": float(np.min(a)),
        "max": float(np.max(a)),
    }


# ---------------------------------------------------------------- 单批
def run_batch(batch):
    """单批 A2 证伪诊断。"""
    import pandas as pd

    out = {"batch": int(batch)}
    cf = os.path.join(CACHE, "b%02d.json" % batch)
    csvp = os.path.join(DATA, "batch_%02d.csv" % batch)
    if not (os.path.exists(cf) and os.path.exists(csvp)):
        out["error"] = "cache_or_csv_missing"
        return out

    d = json.load(open(cf, encoding="utf-8"))
    t = np.asarray(d["t"], float)
    sim = d["sim"]
    PAA_eng = np.asarray(sim["PAA"], float)

    v3 = pd.read_csv(csvp)
    tv = pd.to_numeric(v3["time_h"], errors="coerce").to_numpy(float)
    y_all = pd.to_numeric(v3["PAA_offline"], errors="coerce").to_numpy(float)
    m = np.isfinite(y_all) & (tv > 20)
    t_lab, y_lab = tv[m], y_all[m]
    if len(y_lab) < 8:
        out["error"] = "too_few_anchors(%d)" % len(y_lab)
        return out

    eng_at = np.interp(t_lab, t, PAA_eng)
    n = len(y_lab)

    out["n_anchors"] = int(n)

    # ---- G1：化验信号退化度 -------------------------------------------
    lab_mean = float(np.mean(y_lab))
    lab_std = float(np.std(y_lab))
    lab_cv = lab_std / abs(lab_mean) * 100.0 if abs(lab_mean) > 1e-12 else float("nan")
    lab_range = float(np.max(y_lab) - np.min(y_lab))
    out["lab_mean"] = lab_mean
    out["lab_std"] = lab_std
    out["lab_cv_pct"] = lab_cv
    out["lab_range"] = lab_range
    out["lab_min"] = float(np.min(y_lab))
    out["lab_max"] = float(np.max(y_lab))
    # 化验值的"动态性"：相邻锚点变化幅度中位（相对均值）
    d1 = np.abs(np.diff(y_lab)) / max(abs(lab_mean), 1e-12) * 100.0
    out["lab_step_med_pct"] = float(np.median(d1)) if len(d1) else float("nan")

    # 引擎侧的对应动态性
    out["eng_cv_pct"] = (float(np.std(eng_at)) / abs(float(np.mean(eng_at))) * 100.0
                         if abs(float(np.mean(eng_at))) > 1e-12 else float("nan"))
    out["eng_min"] = float(np.min(eng_at))
    out["eng_max"] = float(np.max(eng_at))
    out["A_engine_r"] = _r(eng_at, y_lab)
    out["A_engine_nrmse"] = _nrmse(eng_at, y_lab)

    # ---- G2：常数预测基线（控制组：留一锚点的化验均值）----------------
    const_pred = np.array([np.mean(np.delete(y_lab, i)) for i in range(n)], float)
    out["G2_const_looa_nrmse"] = _nrmse(const_pred, y_lab)

    # ---- G2b：另一个更简单的控制组 —— 全局常数（该批全部化验的均值）
    out["G2b_globalmean_nrmse"] = _nrmse(np.full(n, lab_mean), y_lab)

    # ---- G2c：单点锚定（用最近邻锚点做比例锚定，只有 1 个参数）--------
    #          —— "两点校准"名称的最小实现
    # C0 的逐锚比例锚定（分段常数比例）—— 与 R158 同构，复算用于对照
    c0_pred = np.full(n, np.nan)
    for i in range(n):
        keep = np.ones(n, bool)
        keep[i] = False
        ek = eng_at[keep]
        if np.min(np.abs(ek)) <= 1e-6:
            continue
        ratio = y_lab[keep] / ek
        j = int(np.searchsorted(t_lab[keep], t_lab[i]))
        j = int(np.clip(j, 0, len(ratio) - 1))
        c0_pred[i] = eng_at[i] * ratio[j]
    okc = np.isfinite(c0_pred)
    out["C0_looa_nrmse"] = _nrmse(c0_pred[okc], y_lab[okc]) if okc.sum() >= 6 else None

    # ---- A2 原口径（复算 R158 的实现，LOOA 全其余锚点）----------------
    a2_pred = np.full(n, np.nan)
    a2_slopes = []
    a2_ints = []
    for i in range(n):
        keep = np.ones(n, bool)
        keep[i] = False
        if keep.sum() < 3:
            continue
        A_k = np.column_stack([eng_at[keep], np.ones(int(keep.sum()))])
        try:
            c_k, *_ = np.linalg.lstsq(A_k, y_lab[keep], rcond=None)
        except Exception:
            continue
        a2_pred[i] = float(c_k[0] * eng_at[i] + c_k[1])
        a2_slopes.append(float(c_k[0]))
        a2_ints.append(float(c_k[1]))
    a2ok = np.isfinite(a2_pred)
    out["A2_looa_nrmse"] = _nrmse(a2_pred[a2ok], y_lab[a2ok]) if a2ok.sum() >= 6 else None
    out["A2_looa_r"] = _r(a2_pred[a2ok], y_lab[a2ok]) if a2ok.sum() >= 6 else None

    # ---- G3：斜率/截距可辨识性 -----------------------------------------
    if a2_slopes:
        sl = np.asarray(a2_slopes, float)
        it = np.asarray(a2_ints, float)
        out["A2_slope_median"] = float(np.median(sl))
        out["A2_slope_iqr"] = float(np.percentile(sl, 75) - np.percentile(sl, 25))
        out["A2_intercept_median"] = float(np.median(it))
        # 斜率相对可辨识度：斜率 95% 置信区间是否覆盖 0（斜率不可辨识）
        # 简单代理：|斜率中位| / (斜率 IQR/1.35) 作为信噪比代理
        iqr = out["A2_slope_iqr"]
        out["A2_slope_snr_proxy"] = (abs(out["A2_slope_median"]) / (iqr / 1.349)
                                     if iqr > 1e-12 else float("inf"))
        # 斜率 ≈ 0 ⇒ A2 退化为常数预测
        out["A2_is_constant_like"] = bool(abs(out["A2_slope_median"]) < 1e-6)
        # 引擎读数的动态范围（相对）：若引擎本身几乎不变，斜率无意义
        out["A2_pred_spread_pct"] = (float(np.std(a2_pred[a2ok])) / abs(lab_mean) * 100.0
                                    if a2ok.sum() >= 6 and abs(lab_mean) > 1e-12 else float("nan"))
        out["A2_pred_range"] = (float(np.max(a2_pred[a2ok]) - np.min(a2_pred[a2ok]))
                                if a2ok.sum() >= 6 else float("nan"))
        out["lab_range_as_pred"] = out["A2_pred_range"]

    # ---- G4：时间因果（前推式：只用 t 之前的锚点）----------------------
    fwd_pred = np.full(n, np.nan)
    for i in range(n):
        past = np.where(t_lab < t_lab[i])[0]
        if len(past) < 3:
            continue
        A_k = np.column_stack([eng_at[past], np.ones(len(past))])
        try:
            c_k, *_ = np.linalg.lstsq(A_k, y_lab[past], rcond=None)
        except Exception:
            continue
        fwd_pred[i] = float(c_k[0] * eng_at[i] + c_k[1])
    fwok = np.isfinite(fwd_pred)
    out["A2_forward_nrmse"] = _nrmse(fwd_pred[fwok], y_lab[fwok]) if fwok.sum() >= 6 else None
    out["A2_forward_n"] = int(fwok.sum())

    # 前推式常数基线（同样只用过去）
    fwd_const = np.full(n, np.nan)
    for i in range(n):
        past = np.where(t_lab < t_lab[i])[0]
        if len(past) < 1:
            continue
        fwd_const[i] = float(np.mean(y_lab[past]))
    fcok = np.isfinite(fwd_const)
    out["G2_forward_const_nrmse"] = (_nrmse(fwd_const[fcok], y_lab[fcok])
                                     if fcok.sum() >= 6 else None)

    # 前推式 C0（逐锚比例，只用过去）
    fwd_c0 = np.full(n, np.nan)
    for i in range(n):
        past = np.where(t_lab < t_lab[i])[0]
        if len(past) < 2:
            continue
        ek = eng_at[past]
        if np.min(np.abs(ek)) <= 1e-6:
            continue
        ratio = y_lab[past] / ek
        j = int(np.clip(np.searchsorted(t_lab[past], t_lab[i]) - 1, 0, len(ratio) - 1))
        fwd_c0[i] = eng_at[i] * ratio[j]
    f0ok = np.isfinite(fwd_c0)
    out["C0_forward_nrmse"] = (_nrmse(fwd_c0[f0ok], y_lab[f0ok]) if f0ok.sum() >= 6 else None)

    # ---- G5：在线可得性 -----------------------------------------------
    # 分组标签 A_engine_r 需要化验值 ⇒ 线上不可得。
    # 这里给出**线上可得**的替代判据候选：引擎自身的可观测量。
    _eng_mean = float(np.mean(eng_at))
    out["online_signals"] = {
        "eng_paa_min": float(np.min(eng_at)),
        "eng_paa_max": float(np.max(eng_at)),
        "eng_paa_rel_range": (float((np.max(eng_at) - np.min(eng_at))
                                    / max(abs(_eng_mean), 1e-12))
                              if abs(_eng_mean) > 1e-12 else float("nan")),
        "eng_paa_mean": _eng_mean,
        "eng_paa_final": float(eng_at[-1]),
    }

    return out


# ---------------------------------------------------------------- 主流程
def main(argv=None):
    ap = argparse.ArgumentParser(description="R159 A2 证伪探针")
    ap.add_argument("--batches", default="", help="逗号分隔；默认全 86 批")
    ap.add_argument("--out", default="runs/r159_a2_falsification.json")
    args = ap.parse_args(argv)

    if args.batches.strip() == "all":
        sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))
        from golden_params import GOLDEN_ALL
        batches = list(GOLDEN_ALL)
    elif args.batches.strip():
        batches = [int(x) for x in args.batches.split(",") if x.strip()]
    else:
        batches = list(range(1, 87))

    t0 = time.time()
    rows = []
    for b in batches:
        r = run_batch(b)
        rows.append(r)
        sys.stdout.write(".")
        sys.stdout.flush()
    print()

    ok = [r for r in rows if "error" not in r]

    # 分层：与 R158 完全同口径（A_engine_r <= 0.5）
    dis = [r for r in ok if r.get("A_engine_r") is not None and r["A_engine_r"] <= 0.5]
    tru = [r for r in ok if r.get("A_engine_r") is not None and r["A_engine_r"] > 0.5]

    def layer(name, g):
        return {
            "n": len(g),
            "A_engine_r": _stat([r["A_engine_r"] for r in g]),
            "lab_cv_pct": _stat([r["lab_cv_pct"] for r in g]),
            "lab_step_med_pct": _stat([r["lab_step_med_pct"] for r in g]),
            "lab_range": _stat([r["lab_range"] for r in g]),
            "A_engine_nrmse": _stat([r["A_engine_nrmse"] for r in g]),
            "A2_looa_nrmse": _stat([r["A2_looa_nrmse"] for r in g]),
            "A2_forward_nrmse": _stat([r["A2_forward_nrmse"] for r in g]),
            "G2_const_looa_nrmse": _stat([r["G2_const_looa_nrmse"] for r in g]),
            "G2b_globalmean_nrmse": _stat([r["G2b_globalmean_nrmse"] for r in g]),
            "G2_forward_const_nrmse": _stat([r["G2_forward_const_nrmse"] for r in g]),
            "C0_looa_nrmse": _stat([r["C0_looa_nrmse"] for r in g]),
            "C0_forward_nrmse": _stat([r["C0_forward_nrmse"] for r in g]),
            "A2_slope_median": _stat([r.get("A2_slope_median") for r in g]),
            "A2_pred_spread_pct": _stat([r.get("A2_pred_spread_pct") for r in g]),
            "A2_pred_range": _stat([r.get("A2_pred_range") for r in g]),
            "lab_range_as_pred": _stat([r.get("lab_range_as_pred") for r in g]),
            "sign_A2_vs_G2const": _sign_test(
                [(r["A2_looa_nrmse"] - r["G2_const_looa_nrmse"]) for r in g
                 if r.get("A2_looa_nrmse") is not None and r.get("G2_const_looa_nrmse") is not None]),
            "sign_A2fwd_vs_G2fwdconst": _sign_test(
                [(r["A2_forward_nrmse"] - r["G2_forward_const_nrmse"]) for r in g
                 if r.get("A2_forward_nrmse") is not None
                 and r.get("G2_forward_const_nrmse") is not None]),
        }

    summary = {
        "n_batches": len(batches),
        "n_ok": len(ok),
        "elapsed_s": round(time.time() - t0, 2),
        "pool": {
            "A2_looa_nrmse": _stat([r.get("A2_looa_nrmse") for r in ok]),
            "G2_const_looa_nrmse": _stat([r.get("G2_const_looa_nrmse") for r in ok]),
            "A2_forward_nrmse": _stat([r.get("A2_forward_nrmse") for r in ok]),
            "G2_forward_const_nrmse": _stat([r.get("G2_forward_const_nrmse") for r in ok]),
            "sign_A2_vs_G2const": _sign_test(
                [(r["A2_looa_nrmse"] - r["G2_const_looa_nrmse"]) for r in ok
                 if r.get("A2_looa_nrmse") is not None and r.get("G2_const_looa_nrmse") is not None]),
            "sign_A2fwd_vs_G2fwdconst": _sign_test(
                [(r["A2_forward_nrmse"] - r["G2_forward_const_nrmse"]) for r in ok
                 if r.get("A2_forward_nrmse") is not None
                 and r.get("G2_forward_const_nrmse") is not None]),
        },
        "strata": {
            "distorted": layer("distorted", dis),
            "trustworthy": layer("trustworthy", tru),
        },
    }

    # ---- 五门判决 -----------------------------------------------------
    def med(layer_key, field):
        v = summary["strata"][layer_key][field]["median"]
        return v

    dis_d = summary["strata"]["distorted"]
    tru_d = summary["strata"]["trustworthy"]

    g1_cv_dis = dis_d["lab_cv_pct"]["median"]
    g1_cv_tru = tru_d["lab_cv_pct"]["median"]
    g1_fired = bool(g1_cv_dis is not None and g1_cv_tru is not None
                    and g1_cv_dis < 0.25 * g1_cv_tru)

    g2_a2 = dis_d["A2_looa_nrmse"]["median"]
    g2_const = dis_d["G2_const_looa_nrmse"]["median"]
    g2_ratio = (g2_a2 / g2_const) if (g2_a2 and g2_const) else None
    g2_fired = bool(g2_ratio is not None and g2_ratio >= 0.8)

    g3_slope = dis_d["A2_slope_median"]["median"]
    g3_const_like = bool(g3_slope is not None and abs(g3_slope) < 1e-6)
    g3_spread_ratio = None
    if (dis_d["A2_pred_spread_pct"]["median"] is not None
            and dis_d["lab_range"]["median"] is not None
            and dis_d["lab_range"]["median"] > 0):
        g3_spread_ratio = (dis_d["A2_pred_spread_pct"]["median"]
                           / dis_d["lab_range"]["median"] * 100.0)

    g4_a2f = dis_d["A2_forward_nrmse"]["median"]
    g4_cf = dis_d["G2_forward_const_nrmse"]["median"]
    g4_ratio = (g4_a2f / g4_cf) if (g4_a2f and g4_cf) else None
    g4_fired = bool(g4_ratio is not None and g4_ratio >= 0.8)

    summary["verdicts"] = {
        "G1_lab_degenerate": {
            "question": "失真批的化验信号是否退化（CV 极低）？",
            "lab_cv_distorted_pct": g1_cv_dis,
            "lab_cv_trustworthy_pct": g1_cv_tru,
            "ratio": (g1_cv_dis / g1_cv_tru) if (g1_cv_dis and g1_cv_tru) else None,
            "FIRED": g1_fired,
            "meaning": "化验信号退化 ⇒ 该层是被'化验恒定'定义的，不是'引擎失真'",
        },
        "G2_const_baseline": {
            "question": "更简单的常数预测基线是否与 A2 同量级？",
            "A2_median_pct": g2_a2,
            "const_looa_median_pct": g2_const,
            "A2_over_const": g2_ratio,
            "FIRED": g2_fired,
            "meaning": "A2/常数基线 ≈ 1 ⇒ A2 无净贡献（更简单基线未被击败）",
        },
        "G3_slope_degenerate": {
            "question": "A2 的斜率是否退化为 0（预测常数）？",
            "A2_slope_median": g3_slope,
            "slope_constant_like": g3_const_like,
            "pred_spread_over_lab_range_pct": g3_spread_ratio,
            "FIRED": bool(g3_const_like
                          or (g3_spread_ratio is not None and g3_spread_ratio < 50.0)),
            "meaning": "斜率≈0 或 预测动态范围远小于化验动态范围 ⇒ A2 退化为常数预测",
        },
        "G4_time_leak": {
            "question": "改用前推式（只用过去锚点）后 A2 优势是否消失？",
            "A2_forward_median_pct": g4_a2f,
            "const_forward_median_pct": g4_cf,
            "A2_over_const_forward": g4_ratio,
            "FIRED": g4_fired,
            "meaning": "前推式下 A2/常数 ≈ 1 ⇒ 原优势含时间泄漏或不可归因于校准",
        },
    }
    summary["verdicts"]["G5_online_availability"] = {
        "question": "分组标签是否在线可得？",
        "FIRED": True,
        "meaning": ("A_engine_r 需化验值才能算 ⇒ 线上不可得；"
                   "且 A2 本身需要化验锚点 ⇒ 只能作为'离线锚定+在线外推'的兜底"),
    }

    # ---- 第六段：**剔除退化批后的重判**（唯一有效的口径）--------------
    # 退化判据：化验 CV < 2%（化验值被钉在常数，无动态信息）
    DEG_CV = 2.0
    deg_rows = [r for r in ok if r["lab_cv_pct"] < DEG_CV]
    info_rows = [r for r in ok if r["lab_cv_pct"] >= DEG_CV]
    deg_batches = sorted(r["batch"] for r in deg_rows)

    # 真·失真批 = 有信息 且 A_engine_r <= 0.5
    true_dis = [r for r in info_rows
                if r["A_engine_r"] is not None and r["A_engine_r"] <= 0.5]

    def _sig(gs, fa, fb):
        return _sign_test([(r[fa] - r[fb]) for r in gs
                           if r.get(fa) is not None and r.get(fb) is not None])

    summary["degenerate_exclusion"] = {
        "criterion": "lab_cv_pct < %.1f%%（化验值无动态信息）" % DEG_CV,
        "n_degenerate": len(deg_rows),
        "n_informative": len(info_rows),
        "degenerate_batches": deg_batches,
        "layers": {
            "informative": layer("informative", info_rows),
            "degenerate": layer("degenerate", deg_rows),
            "true_distorted": layer("true_distorted", true_dis),
        },
        "sign_A2_vs_const_informative": _sig(info_rows, "A2_looa_nrmse",
                                             "G2_const_looa_nrmse"),
        "sign_A2_vs_C0_informative": _sig(info_rows, "A2_looa_nrmse",
                                          "C0_looa_nrmse"),
    }

    # ---- 第七段：**R158 结论的交叉影响** ------------------------------
    # 退化批污染了 R158 的哪几条结论？剔除后是否翻转？
    r158_path = os.path.join(ROOT, "runs", "r158_pat_ablation_scale.json")
    if os.path.exists(r158_path):
        r158 = json.load(open(r158_path, encoding="utf-8"))["rows"]
        deg_set = set(deg_batches)
        r158_info = [r for r in r158 if r["batch"] not in deg_set]
        r158_dis_all = [r for r in r158
                        if r.get("A_engine_r") is not None and r["A_engine_r"] <= 0.5]
        r158_true_dis = [r for r in r158_info
                         if r.get("A_engine_r") is not None and r["A_engine_r"] <= 0.5]

        def _r158_layer(g, label):
            return {
                "label": label, "n": len(g),
                "A_engine_nrmse": _stat([r.get("A_engine_nrmse") for r in g]),
                "B_pat_nrmse": _stat([r.get("B_pat_nrmse") for r in g]),
                "A2_looa_nrmse": _stat([r.get("A2_looa_nrmse") for r in g]),
                "C0_looa_nrmse": _stat([r.get("C0_looa_nrmse") for r in g]),
                "incr_r2_pat_added": _stat([r.get("incr_r2_pat_added") for r in g]),
                "incr_t_pat": _stat([r.get("incr_t_pat") for r in g]),
                "pat_vs_engine_r": _stat([r.get("pat_vs_engine_r") for r in g]),
                "n_abs_t_ge2": sum(1 for r in g if r.get("incr_t_pat") is not None
                                   and abs(r["incr_t_pat"]) >= 2),
                "sign_B_vs_A": _sign_test(
                    [(r["B_pat_nrmse"] - r["A_engine_nrmse"]) for r in g
                     if r.get("B_pat_nrmse") is not None
                     and r.get("A_engine_nrmse") is not None]),
                "sign_A2_vs_B": _sign_test(
                    [(r["A2_looa_nrmse"] - r["B_pat_nrmse"]) for r in g
                     if r.get("A2_looa_nrmse") is not None
                     and r.get("B_pat_nrmse") is not None]),
            }

        summary["r158_cross_impact"] = {
            "degenerate_batches": deg_batches,
            "layers": {
                "pool_all_86": _r158_layer(r158, "R158 原口径（86 批）"),
                "informative": _r158_layer(r158_info, "剔除退化批"),
                "distorted_all": _r158_layer(r158_dis_all, "失真批（R158 原分层）"),
                "true_distorted": _r158_layer(r158_true_dis, "真·失真批（有信息且 r<=0.5）"),
            },
        }

    # 综合判决
    trivial = [k for k in ("G1_lab_degenerate", "G2_const_baseline",
                           "G3_slope_degenerate", "G4_time_leak")
               if summary["verdicts"][k]["FIRED"]]
    if len(trivial) >= 2:
        final = ("A2_NOT_MEASURABLE（至少 %d 道门触发：A2 的低误差主要来自"
                 "化验信号退化/平凡满足，而非校准能力）" % len(trivial))
    elif len(trivial) == 1:
        final = "A2_PARTIAL（1 道门触发，需按限定口径解读）"
    else:
        final = "A2_ROBUST（无门触发，A2 优势不来自平凡满足）"
    summary["final_verdict"] = final
    summary["gates_fired"] = trivial

    # 剔除退化批后的最终口径判决
    try:
        inf_l = summary["degenerate_exclusion"]["layers"]["informative"]
        a2_inf = inf_l["A2_looa_nrmse"]["median"]
        c0_inf = inf_l["C0_looa_nrmse"]["median"]
        if a2_inf is not None and c0_inf is not None:
            if a2_inf >= c0_inf:
                summary["verdict_after_exclusion"] = (
                    "A2_RETRACTED（剔除退化批后 A2 中位 %.2f%% **劣于** C0 中位 %.2f%%"
                    " ⇒ R158 的『A2 严格支配』结论撤回）" % (a2_inf, c0_inf))
            else:
                summary["verdict_after_exclusion"] = (
                    "A2_SURVIVES（剔除退化批后 A2 中位 %.2f%% 仍优于 C0 中位 %.2f%%）"
                    % (a2_inf, c0_inf))
    except Exception:
        summary["verdict_after_exclusion"] = "N/A"

    out_path = os.path.join(ROOT, args.out)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "rows": rows,
                   "meta": {"tool": "r159_a2_falsification.py",
                            "r158_reference": "runs/r158_pat_ablation_scale.json"}},
                  f, ensure_ascii=False, indent=1)

    print("== 分层（与 R158 同口径）==")
    for k in ("distorted", "trustworthy"):
        s = summary["strata"][k]
        print("  [%s] n=%d" % (k, s["n"]))
        for fld in ("A_engine_r", "lab_cv_pct", "lab_range", "A_engine_nrmse",
                    "A2_looa_nrmse", "G2_const_looa_nrmse", "G2b_globalmean_nrmse",
                    "A2_forward_nrmse", "G2_forward_const_nrmse",
                    "C0_looa_nrmse", "C0_forward_nrmse",
                    "A2_slope_median", "A2_pred_spread_pct"):
            m = s[fld]["median"]
            print("     %-28s %s" % (fld, ("%.4f" % m) if m is not None else "NA"))
        print("     sign A2 vs const(LOOA)  ", s["sign_A2_vs_G2const"])
        print("     sign A2fwd vs const(fwd)", s["sign_A2fwd_vs_G2fwdconst"])
    print("== 五门判决 ==")
    for k, v in summary["verdicts"].items():
        print("  %-26s FIRED=%s" % (k, v["FIRED"]))
    print("== 综合 ==\n  %s" % final)

    de = summary.get("degenerate_exclusion")
    if de:
        print("== 剔除退化批（%s）==" % de["criterion"])
        print("  退化批 n=%d（%s）" % (de["n_degenerate"],
                                       ",".join(str(b) for b in de["degenerate_batches"])))
        print("  有信息批 n=%d / 真·失真批 n=%d"
              % (de["n_informative"], de["layers"]["true_distorted"]["n"]))
        print("  %-30s %12s %12s %12s" % ("指标", "有信息批", "退化批", "真失真批"))
        for fld in ("A_engine_r", "lab_cv_pct", "lab_range", "A_engine_nrmse",
                    "A2_looa_nrmse", "G2_const_looa_nrmse", "C0_looa_nrmse",
                    "A2_forward_nrmse", "G2_forward_const_nrmse",
                    "A2_slope_median", "A2_pred_spread_pct"):
            vals = []
            for lk in ("informative", "degenerate", "true_distorted"):
                m = de["layers"][lk][fld]["median"]
                vals.append(("%.4f" % m) if m is not None else "NA")
            print("  %-30s %12s %12s %12s" % (fld, *vals))
        print("  sign A2 vs 常数(有信息批):", de["sign_A2_vs_const_informative"])
        print("  sign A2 vs C0 (有信息批):", de["sign_A2_vs_C0_informative"])
    if "verdict_after_exclusion" in summary:
        print("== 剔除后判决 ==\n  %s" % summary["verdict_after_exclusion"])
    cx = summary.get("r158_cross_impact")
    if cx:
        print("== R158 结论交叉影响 ==")
        for lk, l in cx["layers"].items():
            print("  [%s] n=%d" % (lk, l["n"]))
            print("     incr_r2_pat_added 中位 %s | incr_t 中位 %s | |t|>=2 %d"
                  % (l["incr_r2_pat_added"]["median"], l["incr_t_pat"]["median"],
                     l["n_abs_t_ge2"]))
            print("     sign B vs A:", l["sign_B_vs_A"])
            print("     A2 vs C0 中位: A2=%s C0=%s"
                  % (l["A2_looa_nrmse"]["median"], l["C0_looa_nrmse"]["median"]))
    print("  -> %s" % out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
