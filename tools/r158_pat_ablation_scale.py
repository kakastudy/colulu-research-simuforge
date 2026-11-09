# -*- coding: utf-8 -*-
"""R158 / T3-3：Raman / PAA-PLS 通道的**大规模接线 + 消融**。

问题
----
`docs/roadmap_next.md` §T3-3：「Raman/PAA PLS 消融」——
资产核证完毕、合成层三重验证完成（0.9995 / 0.9997 / 0.8463），
缺「**与引擎状态的大规模接线 + PAA 锚定修正层**」，属 V1+。

已有资产（本轮复用，不重做）
----------------------------
| 资产 | 位置 | 状态 |
|---|---|---|
| 合成层 `synth_batch()` | `tools/raman_pipeline.py` | ✅ r=0.9995（对 Batch_01 存储谱） |
| PLS 层 `predict_paa()` | `tools/raman_pipeline.py` | ✅ 循环自洽 r=0.9997 |
| PAT 前向库函数 | `tools/raman_pat_channel.py` | ✅ R103（含锚定修正层） |
| 双批消融 | `tools/pat_ablation.py` | ⚠️ 仅 b22 / b60 两批 |
| 引擎状态缓存 | `platform/.cache/bXX.json` | ✅ 86 批，golden 参数轨迹 |

本轮要补的三件事
----------------
1. **大规模接线**：把 PAT 通道接到**全部 86 批**（R120 只做了 2 批）。
2. **PAA 锚定修正层**：大批量验证触发条件下的净收益。
3. **消融口径**（本轮的方法论主线，见下）。

消融口径：必须避开的三个陷阱
-----------------------------
**陷阱 ①（PAA 通道结构性不可辨识，D-64）**：T3-1 已证 P 通道 CV nRMSE 劣于 A 档。
PAT 通道若沿用同一「用代理比率回归化验 PAA」的框架，只会重复这个否定结论。
⇒ 本轮换**不同的信息通路**：PAT 不是「代理比率」，而是**一条独立的前向测量通道**
（引擎状态 → 合成光谱 → PLS → PAA 读数）。它回答的是：
「PAT 读数本身能不能作为 PAA 的**软测量估值**」。

**陷阱 ②（量纲错误被相关系数掩盖 —— 本轮新发现）**：
R120 的三重验证全用相关系数，而**相关系数对线性缩放完全不变**。
本轮实测：PLS 输出 0–2.11，化验 PAA 430–2023 mg/L ⇒ **差 ~1000 倍**。
OLS 标定：lab(mg/L) = **721.3** × pred + 404.6（R² 0.72, r 0.8463）。
⇒ **PLS 资产的输出单位不是 mg/L**。若直接拿 PAT 读数去算覆盖/误差，
会得到「误差 400 倍」的荒谬结论，而相关系数口径完全看不出来。
⇒ 本轮所有**绝对量**指标一律先过标定（乘 721.3 或按批次 OLS），
并把「量纲」列为**显式登记项**（新债）。

**陷阱 ③（锚定层在锚点必然贴化验 ⇒ 覆盖率平凡满足）**：
`build_pat_channel` 的锚定修正层是**按构造**用化验锚点做比例校正的
（`fused = pat × lab_i/pat_i`）⇒ 在锚点处 `fused` 必然等于化验值。
若用「锚点处覆盖率」当判据 ⇒ **恒真**（D-38 的形态）。
⇒ 引入 **留一锚点交叉验证（leave-one-anchor-out, LOOA）**：
每个锚点用它**以外**的锚点构建融合层，再预测该锚点 ⇒ 衡量的是
**锚点之间的外推能力**，不是构造保证。
⇒ 这一项同时被列为 D-63 的延伸（覆盖率类指标必须做抗平凡满足检验）。

三口径消融（逐批）
------------------
| 口径 | 说明 | 回答的问题 |
|---|---|---|
| **A（引擎直报）** | 引擎 PAA 轨迹 vs 化验 PAA | 基线：模型自己报得准不准 |
| **B（PAT 转发）** | PAT 读数（标定后）vs 化验 PAA | 前向通道**不加锚定**时的独立信息量 |
| **C（PAT + 锚定，LOOA）** | 留一锚点交叉验证的融合估值 vs 化验 PAA | 锚定修正层的**真实**外推增益 |

三道硬门（沿用 D-63 的口径纪律，防平凡满足）
--------------------------------------------
| 门 | 内容 | 为什么 |
|---|---|---|
| ① | 须**明显优于** A 档（改善 > 1 pp） | 否则没带来任何东西 |
| ② | **CI 半宽 ≤ 25%** | 覆盖率单独看**可平凡满足**（区间开到 ±98% 当然覆盖 90%）—— 同 D-63 |
| ③ | **CI 半宽 < 它所替代的 A 档误差** | 否则不如直接上报模型值 |
| ④（新增） | **LOOA 下仍有效** | 防「锚点处构造贴合」的平凡满足（陷阱 ③） |

用法
----
    python tools/r158_pat_ablation_scale.py                 # 全 86 批
    python tools/r158_pat_ablation_scale.py --batches 22,60 # 冒烟
    python tools/r158_pat_ablation_scale.py --workers 6
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
CACHE = os.path.join(ROOT, "platform", ".cache")
DATA = os.path.join(ROOT, "data", "processed", "batches")

# ---------------------------------------------------------------- 量纲标定
# PLS 资产 `PAA_PLS_model.mat` 的输出单位**不是 mg/L**（本轮实测，见模块 docstring）。
# 标定来源：V6 .mat 的 Batch_01 —— **真实存储谱**（非合成）→ PLS → 与 PAA_offline 化验 OLS。
#   lab(mg/L) = 721.263 * pred + 404.644   (r = 0.8463)
# 该斜率是**资产级常数**（系数矩阵固定 ⇒ 线性映射固定），故全池通用。
PLS_UNIT_SCALE = 721.263
PLS_UNIT_INTERCEPT = 404.644

# 兜底：若某批 OLS 标定的斜率与资产常数偏离超过 3 倍，视为病态并记录
SCALE_TOLERANCE = 3.0


def _calibrate(pred, lab):
    """逐批 OLS 标定 PAT 输出 → mg/L。返回 (pred_mgL, slope, intercept, ok)。"""
    if len(pred) < 6 or len(lab) < 6:
        return None, np.nan, np.nan, False
    A = np.column_stack([pred, np.ones(len(pred))])
    coef, *_ = np.linalg.lstsq(A, lab, rcond=None)
    slope, inter = float(coef[0]), float(coef[1])
    ok = np.isfinite(slope) and slope > 0 and (
        1.0 / SCALE_TOLERANCE <= slope / PLS_UNIT_SCALE <= SCALE_TOLERANCE)
    return pred * slope + inter, slope, inter, bool(ok)


def _r2(y, yhat):
    if len(y) < 2:
        return float("nan")
    ss = np.sum((y - yhat) ** 2)
    st = np.sum((y - np.mean(y)) ** 2)
    return float(1.0 - ss / st) if st > 0 else float("nan")


def _nrmse(x, y):
    return float(np.sqrt(np.mean((x - y) ** 2)) / abs(np.mean(y)) * 100.0)


def _boot_ci(x, y, n_boot=400, seed=11, alpha=0.10):
    """预测误差的 bootstrap 90% 区间半宽（相对误差 %）。

    口径：重采样**化验点对**（x=估值, y=真值），每次算相对误差均值，
    取 5% / 95% 分位 ⇒ 半宽 = (p95 - p5)/2。
    """
    if len(x) < 4:
        return float("nan"), float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    rel = (x - y) / np.maximum(np.abs(y), 1e-9) * 100.0
    idx = rng.integers(0, len(rel), size=(n_boot, len(rel)))
    means = rel[idx].mean(axis=1)
    p5, p95 = np.percentile(means, [5, 95])
    return float(rel.mean()), float((p95 - p5) / 2.0), float(np.percentile(np.abs(rel), 90))


# ---------------------------------------------------------------- 单批任务
def run_batch(batch):
    """单批三口径消融。返回 dict（可 JSON 序列化）。"""
    import pandas as pd
    sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    from raman_pipeline import synth_batch, predict_paa
    from calibration import calib_params
    from knowledge_constraints import paa_pat_trigger

    out = {"batch": int(batch)}
    cf = os.path.join(CACHE, "b%02d.json" % batch)
    csvp = os.path.join(DATA, "batch_%02d.csv" % batch)
    if not (os.path.exists(cf) and os.path.exists(csvp)):
        out["error"] = "cache_or_csv_missing"
        return out

    d = json.load(open(cf, encoding="utf-8"))
    t = np.asarray(d["t"], float)
    sim = d["sim"]
    P = np.clip(np.asarray(sim["P"], float), 0, None)
    X = np.clip(np.asarray(sim["X"], float), 0, None)
    V = np.clip(np.asarray(sim["vis"], float), 0, None)
    S = np.asarray(sim["S"], float)
    PAA_eng = np.asarray(sim["PAA"], float)

    # ---- 化验锚点（稀疏，来自 V3 CSV 的 PAA_offline 列）----
    v3 = pd.read_csv(csvp)
    tv = pd.to_numeric(v3["time_h"], errors="coerce").to_numpy(float)
    y_all = pd.to_numeric(v3["PAA_offline"], errors="coerce").to_numpy(float)
    m = np.isfinite(y_all) & (tv > 20)
    t_lab, y_lab = tv[m], y_all[m]
    if len(y_lab) < 8:
        out["error"] = "too_few_anchors(%d)" % len(y_lab)
        return out

    # ---- PAT 前向通道（引擎状态 → 合成谱 → PLS）----
    spec = synth_batch(P, X, V, S, PAA_eng)
    pat_raw = predict_paa(spec)              # 资产单位（≈ g/L 量级）
    pat_at = np.interp(t_lab, t, pat_raw)    # 插到化验时点

    # ---- 触发器 ----
    try:
        mup = calib_params(batch).get("mup")
    except Exception:
        mup = None
    trig, reason = paa_pat_trigger(mup)

    # ---- 逐批标定（资产常数 + 逐批 OLS 对照）----
    pat_mgl_asset = pat_at * PLS_UNIT_SCALE + PLS_UNIT_INTERCEPT
    pat_mgl_ols, slope, inter, ok = _calibrate(pat_at, y_lab)

    # 引擎 PAA 在化验时点
    eng_at = np.interp(t_lab, t, PAA_eng)

    row = {
        "n_anchors": int(len(y_lab)),
        "trigger": bool(trig),
        "trigger_reason": reason,
        "mup": (float(mup) if mup is not None else None),
        "ols_slope": slope,
        "ols_intercept": inter,
        "ols_ok": ok,
        "asset_scale_ratio": float(np.median(np.abs(y_lab) / np.maximum(np.abs(pat_at), 1e-9))),
    }

    # ---- 口径 A：引擎直报 ----
    row["A_engine_nrmse"] = _nrmse(eng_at, y_lab)
    row["A_engine_r"] = float(np.corrcoef(eng_at, y_lab)[0, 1])
    row["A_engine_bias"] = float(np.mean(eng_at - y_lab))
    row["A_engine_r2"] = _r2(y_lab, eng_at)

    # ---- 口径 B：PAT 转发（资产常数标定）----
    row["B_pat_nrmse"] = _nrmse(pat_mgl_asset, y_lab)
    row["B_pat_r"] = float(np.corrcoef(pat_mgl_asset, y_lab)[0, 1])
    row["B_pat_bias"] = float(np.mean(pat_mgl_asset - y_lab))
    row["B_pat_r2"] = _r2(y_lab, pat_mgl_asset)

    # ---- 口径 C：PAT + 锚定修正（**留一锚点交叉验证**）----
    looa_pred = np.full(len(y_lab), np.nan)
    looa_ok = 0
    for i in range(len(y_lab)):
        keep = np.ones(len(y_lab), bool)
        keep[i] = False
        if keep.sum() < 2:
            continue
        pat_k = np.interp(t_lab[keep], t, pat_raw)
        if np.min(np.abs(pat_k)) <= 1e-6:
            continue
        # 逐锚比例锚定（与 build_pat_channel 同结构），但**排除**被预测的锚点
        ratio = y_lab[keep] / pat_k
        # 在被留出的锚点处：用最近邻保留锚点的比例做外推（分段常数）
        j = int(np.searchsorted(t_lab[keep], t_lab[i]))
        j = int(np.clip(j, 0, len(ratio) - 1))
        looa_pred[i] = pat_at[i] * ratio[j]
        looa_ok += 1
    row["C_looa_n"] = int(looa_ok)
    if looa_ok >= 6:
        okm = np.isfinite(looa_pred)
        row["C_looa_nrmse"] = _nrmse(looa_pred[okm], y_lab[okm])
        row["C_looa_r"] = float(np.corrcoef(looa_pred[okm], y_lab[okm])[0, 1])
        row["C_looa_bias"] = float(np.mean(looa_pred[okm] - y_lab[okm]))
        row["C_looa_r2"] = _r2(y_lab[okm], looa_pred[okm])
    else:
        row["C_looa_nrmse"] = None
        row["C_looa_r"] = None

    # ---- 控制组 A2：**只做偏置/比例校正的引擎 PAA**（完全不用 PAT）----
    # 回答：「失真批上 B 优于 A」究竟来自 PAT 的独立信息，还是仅来自
    # **两点校准**（把引擎 PAA 的系统偏置/尺度差修掉）？
    # A2 = 对引擎 PAA 做**留一锚点**的仿射校准（斜率+截距，同样用其余锚点拟合）
    #      ⇒ 若 A2 ≈ B，则 B 的优势全部来自校准，PAT 通道无净贡献。
    a2_pred = np.full(len(y_lab), np.nan)
    a2_ok = 0
    for i in range(len(y_lab)):
        keep = np.ones(len(y_lab), bool)
        keep[i] = False
        if keep.sum() < 3:
            continue
        A_k = np.column_stack([eng_at[keep], np.ones(keep.sum())])
        try:
            c_k, *_ = np.linalg.lstsq(A_k, y_lab[keep], rcond=None)
        except Exception:
            continue
        a2_pred[i] = float(c_k[0] * eng_at[i] + c_k[1])
        a2_ok += 1
    row["A2_looa_n"] = int(a2_ok)
    if a2_ok >= 6:
        okm2 = np.isfinite(a2_pred)
        row["A2_looa_nrmse"] = _nrmse(a2_pred[okm2], y_lab[okm2])
        row["A2_looa_r"] = float(np.corrcoef(a2_pred[okm2], y_lab[okm2])[0, 1])
    else:
        row["A2_looa_nrmse"] = None
        row["A2_looa_r"] = None

    # ---- 控制组 C0：同样用化验锚点，但**锚在引擎 PAA 上**（不用 PAT）----
    # 这是判定「C 的改善究竟来自 PAT 通道，还是仅来自『用了化验锚点』」的**关键对照**。
    # 若 C0 ≈ C ⇒ PAT 通道无净贡献（锚定技巧本身carry了全部收益）。
    looa0_pred = np.full(len(y_lab), np.nan)
    looa0_ok = 0
    for i in range(len(y_lab)):
        keep = np.ones(len(y_lab), bool)
        keep[i] = False
        if keep.sum() < 2:
            continue
        eng_k = eng_at[keep]
        if np.min(np.abs(eng_k)) <= 1e-6:
            continue
        ratio0 = y_lab[keep] / eng_k
        j = int(np.searchsorted(t_lab[keep], t_lab[i]))
        j = int(np.clip(j, 0, len(ratio0) - 1))
        looa0_pred[i] = eng_at[i] * ratio0[j]
        looa0_ok += 1
    row["C0_looa_n"] = int(looa0_ok)
    if looa0_ok >= 6:
        okm0 = np.isfinite(looa0_pred)
        row["C0_looa_nrmse"] = _nrmse(looa0_pred[okm0], y_lab[okm0])
        row["C0_looa_r"] = float(np.corrcoef(looa0_pred[okm0], y_lab[okm0])[0, 1])
        row["C0_looa_bias"] = float(np.mean(looa0_pred[okm0] - y_lab[okm0]))
        row["C0_looa_r2"] = _r2(y_lab[okm0], looa0_pred[okm0])
    else:
        row["C0_looa_nrmse"] = None
        row["C0_looa_r"] = None

    # ---- 控制组 C1：**比例锚定的平凡上界**（把化验值本身当锚定源）----
    # 若「锚定」这件事本身就能把误差压到很低，则 C 的收益不是 PAT 的功劳。
    # C1 = 用化验真值自身做比例锚定（等价于「知道全部锚点真值」的最乐观情形）。
    looa1_pred = np.full(len(y_lab), np.nan)
    looa1_ok = 0
    for i in range(len(y_lab)):
        keep = np.ones(len(y_lab), bool)
        keep[i] = False
        if keep.sum() < 2:
            continue
        # 用**邻近**锚点的化验值直接插值（完全不看 PAT、不看引擎）
        looa1_pred[i] = float(np.interp(t_lab[i], t_lab[keep], y_lab[keep]))
        looa1_ok += 1
    row["C1_looa_nrmse"] = (_nrmse(looa1_pred[np.isfinite(looa1_pred)],
                                   y_lab[np.isfinite(looa1_pred)])
                            if looa1_ok >= 6 else None)

    # ---- 净贡献：C 相对 C0 的改善（才是「PAT 通道本身的贡献」）----
    if (row.get("C_looa_nrmse") is not None and row.get("C0_looa_nrmse") is not None):
        row["C_net_vs_C0_pp"] = float(row["C0_looa_nrmse"] - row["C_looa_nrmse"])
    else:
        row["C_net_vs_C0_pp"] = None
    # B 相对 A 的改善，是否可被「单纯的截距/比例校正」解释？
    row["B_net_vs_A_biascorr_pp"] = float(
        row["A_engine_nrmse"] - row["B_pat_nrmse"]) if (
        row.get("A_engine_nrmse") is not None and row.get("B_pat_nrmse") is not None) else None

    # ---- 循环性检验（陷阱②的正面处理）：PAT 是否只是引擎 PAA 的重命名 ----
    # 若 PAT 与引擎 PAA 在化验点的关系近乎完美相关 ⇒ PAT 不含新信息
    row["pat_vs_engine_r"] = float(np.corrcoef(pat_at, eng_at)[0, 1])
    row["pat_vs_engine_slope"] = float(np.polyfit(eng_at, pat_at, 1)[0]) if len(pat_at) > 2 else float("nan")

    # ---- **增量信息检验**（门④的严格形式）----
    # 问：在**控制了引擎 PAA 之后**，PAT 是否仍能解释化验残差？
    # 做法：对化验值做回归  y ~ a + b·eng + c·pat   ⇒   若 c 的部分 R² ≈ 0
    #       ⇒ PAT 对化验的贡献**可被引擎 PAA 完全替代** ⇒ 无独立信息。
    # 这是比「相关系数高」更严格的判据：允许 PAT 与 eng 高度相关但仍带独立成分。
    try:
        A3 = np.column_stack([np.ones(len(y_lab)), eng_at, pat_at])
        coef3, *_ = np.linalg.lstsq(A3, y_lab, rcond=None)
        r2_full = _r2(y_lab, A3 @ coef3)
        A2 = np.column_stack([np.ones(len(y_lab)), eng_at])
        coef2, *_ = np.linalg.lstsq(A2, y_lab, rcond=None)
        r2_eng = _r2(y_lab, A2 @ coef2)
        row["incr_r2_full"] = r2_full
        row["incr_r2_eng_only"] = r2_eng
        row["incr_r2_pat_added"] = float(r2_full - r2_eng)
        # 增量显著性：PAT 系数的 t 统计量
        resid = y_lab - A3 @ coef3
        dof = max(len(y_lab) - 3, 1)
        s2 = float(resid @ resid) / dof
        try:
            cov = s2 * np.linalg.inv(A3.T @ A3)
            se = float(np.sqrt(cov[2, 2]))
            row["incr_t_pat"] = float(coef3[2] / se) if se > 0 else float("nan")
        except Exception:
            row["incr_t_pat"] = float("nan")
    except Exception:
        row["incr_r2_full"] = None
        row["incr_r2_eng_only"] = None
        row["incr_r2_pat_added"] = None
        row["incr_t_pat"] = None

    # ---- CI 半宽（口径②）----
    for tag, pred in (("A", eng_at), ("B", pat_mgl_asset)):
        m_, hw, p90 = _boot_ci(pred, y_lab)
        row[f"{tag}_relbias"] = m_
        row[f"{tag}_ci_halfwidth"] = hw
        row[f"{tag}_p90_absrel"] = p90
    if row.get("C_looa_nrmse") is not None:
        m_, hw, p90 = _boot_ci(looa_pred[np.isfinite(looa_pred)], y_lab[np.isfinite(looa_pred)])
        row["C_relbias"] = m_
        row["C_ci_halfwidth"] = hw
        row["C_p90_absrel"] = p90
    else:
        row["C_relbias"] = None
        row["C_ci_halfwidth"] = None

    out.update(row)
    return out


def _worker(args):
    return run_batch(args)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", default="all")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", default="runs/r158_pat_ablation_scale.json")
    args = ap.parse_args()

    sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))
    from golden_params import GOLDEN_ALL
    bs = list(GOLDEN_ALL) if args.batches == "all" else [
        int(x) for x in args.batches.split(",") if x.strip()]

    print("=" * 104)
    print("R158 / T3-3  Raman / PAA-PLS 通道大规模接线 + 消融（%d 批）" % len(bs))
    print("量纲标定：PLS 输出 × %.3f + %.3f → mg/L（资产级常数，V6 Batch_01 OLS）"
          % (PLS_UNIT_SCALE, PLS_UNIT_INTERCEPT))
    print("=" * 104)

    t0 = time.time()
    rows = []
    if args.workers > 1 and len(bs) > 1:
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            for i, r in enumerate(ex.map(_worker, bs), 1):
                rows.append(r)
                if r.get("error"):
                    print("  [%3d/%3d] b%-3d SKIP (%s)" % (i, len(bs), r["batch"], r["error"]))
                else:
                    print("  [%3d/%3d] b%-3d  A nRMSE %6.2f%%  B %6.2f%%  C(LOOA) %s  trig=%s"
                          % (i, len(bs), r["batch"], r["A_engine_nrmse"],
                             r["B_pat_nrmse"],
                             ("%6.2f%%" % r["C_looa_nrmse"]) if r.get("C_looa_nrmse") is not None else "   n/a ",
                             "Y" if r["trigger"] else "n"), flush=True)
    else:
        for i, b in enumerate(bs, 1):
            r = run_batch(b)
            rows.append(r)
            print("  [%3d/%3d] b%-3d %s" % (i, len(bs), b,
                                             r.get("error", "ok")), flush=True)

    good = [r for r in rows if not r.get("error")]
    summary = {"n_batches": len(rows), "n_ok": len(good), "elapsed_s": round(time.time() - t0, 1)}

    def stat(key, sel=None):
        vals = [r[key] for r in good if r.get(key) is not None
                and (sel is None or sel(r))]
        if not vals:
            return None
        return {"n": len(vals), "median": float(np.median(vals)),
                "mean": float(np.mean(vals)), "p10": float(np.percentile(vals, 10)),
                "p90": float(np.percentile(vals, 90))}

    trig = lambda r: r.get("trigger")
    summary["A_engine_nrmse"] = stat("A_engine_nrmse")
    summary["B_pat_nrmse"] = stat("B_pat_nrmse")
    summary["C_looa_nrmse"] = stat("C_looa_nrmse")
    summary["A2_looa_nrmse"] = stat("A2_looa_nrmse")
    summary["C0_looa_nrmse"] = stat("C0_looa_nrmse")
    summary["C1_looa_nrmse"] = stat("C1_looa_nrmse")
    summary["C_net_vs_C0_pp"] = stat("C_net_vs_C0_pp")
    summary["A_engine_nrmse_trigger"] = stat("A_engine_nrmse", trig)
    summary["B_pat_nrmse_trigger"] = stat("B_pat_nrmse", trig)
    summary["C_looa_nrmse_trigger"] = stat("C_looa_nrmse", trig)
    summary["C0_looa_nrmse_trigger"] = stat("C0_looa_nrmse", trig)
    summary["A_engine_nrmse_notrig"] = stat("A_engine_nrmse", lambda r: not r.get("trigger"))
    summary["B_pat_nrmse_notrig"] = stat("B_pat_nrmse", lambda r: not r.get("trigger"))
    summary["C_looa_nrmse_notrig"] = stat("C_looa_nrmse", lambda r: not r.get("trigger"))
    summary["C0_looa_nrmse_notrig"] = stat("C0_looa_nrmse", lambda r: not r.get("trigger"))
    summary["A_engine_r"] = stat("A_engine_r")
    summary["B_pat_r"] = stat("B_pat_r")
    summary["C_looa_r"] = stat("C_looa_r")
    summary["C0_looa_r"] = stat("C0_looa_r")
    summary["pat_vs_engine_r"] = stat("pat_vs_engine_r")
    summary["incr_r2_pat_added"] = stat("incr_r2_pat_added")
    summary["incr_t_pat"] = stat("incr_t_pat")
    summary["A_ci_halfwidth"] = stat("A_ci_halfwidth")
    summary["B_ci_halfwidth"] = stat("B_ci_halfwidth")
    summary["C_ci_halfwidth"] = stat("C_ci_halfwidth")
    summary["ols_slope"] = stat("ols_slope")
    summary["ols_ok_batches"] = int(sum(1 for r in good if r.get("ols_ok")))

    # ---- 硬门判定 ----
    def _med(d, k):
        return None if not d or d.get(k) is None else d[k]["median"]

    a_med = _med(summary, "A_engine_nrmse")
    b_med = _med(summary, "B_pat_nrmse")
    c_med = _med(summary, "C_looa_nrmse")
    c0_med = _med(summary, "C0_looa_nrmse")
    c1_med = _med(summary, "C1_looa_nrmse")
    net_med = _med(summary, "C_net_vs_C0_pp")

    verdicts = {}
    # --- 口径 B：PAT 转发（无锚定）---
    if b_med is None or a_med is None:
        verdicts["B"] = {"verdict": "NO_DATA"}
    else:
        improve = a_med - b_med
        hw = _med(summary, "B_ci_halfwidth")
        a_hw = _med(summary, "A_ci_halfwidth")
        gate1 = improve > 1.0
        gate2 = (hw is not None and hw <= 25.0)
        gate3 = (hw is not None and a_hw is not None and hw < a_hw)
        # 门④：循环性 —— PAT 是否只是引擎 PAA 的重命名，
        #      其「改善」不含新信息（引擎 PAA 本来就在 A 档里）。
        #      判据用**增量信息检验**（严格形式）：控制引擎 PAA 后，
        #      PAT 对化验的**增量 R²** 须显著 > 0。
        #      显著性判据用 PAT 系数的 |t| ≥ 2（≈ 95% 置信，t 分布 2 d.o.f. 近似）
        #      —— 单看增量 R² 会被大 R² 批的噪声放大，t 检验才控住。
        pv = _med(summary, "pat_vs_engine_r")
        inc = _med(summary, "incr_r2_pat_added")
        t_med = _med(summary, "incr_t_pat")
        n_sig = sum(1 for r in good if r.get("incr_t_pat") is not None
                    and abs(r["incr_t_pat"]) >= 2.0)
        n_tst = sum(1 for r in good if r.get("incr_t_pat") is not None)
        gate4 = (n_tst > 0 and n_sig >= max(1, int(round(0.05 * n_tst))))
        if gate1 and gate2 and gate3 and gate4:
            verdict = "DELIVERABLE"
        elif gate1 and gate2 and gate3:
            verdict = ("NOT_IDENTIFIABLE(门④: 控制引擎 PAA 后 PAT 的增量 R² 中位 %.4f、"
                       "|t|≥2 的批次仅 %d/%d ⇒ PAT 不含独立信息，仅是引擎 PAA 的重命名)"
                       % (inc if inc is not None else float('nan'), n_sig, n_tst))
        elif gate1:
            verdict = "MARGINAL(硬门②/③/④未过)"
        else:
            verdict = "NOT_IDENTIFIABLE(未优于 A 档)"
        verdicts["B"] = {"verdict": verdict, "improve_pp": improve,
                         "ci_halfwidth": hw, "A_ci_halfwidth": a_hw,
                         "pat_vs_engine_r": pv,
                         "incr_r2_pat_added": inc,
                         "incr_t_pat_median": t_med,
                         "n_sig_t_ge2": n_sig, "n_t_tested": n_tst,
                         "gate1_better_than_A": bool(gate1),
                         "gate2_ci_halfwidth_le_25": bool(gate2),
                         "gate3_ci_lt_A": bool(gate3),
                         "gate4_independent_of_engine": bool(gate4)}

    # --- 口径 C：PAT + 锚定（LOOA），关键对照 C0（引擎 + 同样锚定）---
    if c_med is None or c0_med is None:
        verdicts["C"] = {"verdict": "NO_DATA"}
    else:
        improve = a_med - c_med
        net = c0_med - c_med          # PAT 通道的**净**贡献（剔除「用了化验锚点」这一共同项）
        hw = _med(summary, "C_ci_halfwidth")
        a_hw = _med(summary, "A_ci_halfwidth")
        gate1 = improve > 1.0
        gate2 = (hw is not None and hw <= 25.0)
        gate3 = (hw is not None and a_hw is not None and hw < a_hw)
        gate4 = (net is not None and net > 1.0)   # 相对 C0 仍有净增益
        gate5 = (c1_med is not None and c_med > c1_med)  # 未达到「直接插值化验值」的平凡上界
        if gate1 and gate2 and gate3 and gate4 and gate5:
            verdict = "DELIVERABLE"
        elif gate1 and gate2 and gate3 and not gate4:
            verdict = ("NOT_IDENTIFIABLE(门④: C 相对 C0 的净增益 %.2f pp ⇒ "
                       "收益来自锚定技巧本身，非 PAT 通道)" % (net if net is not None else float('nan')))
        else:
            verdict = "MARGINAL(硬门未全过)"
        verdicts["C"] = {"verdict": verdict, "improve_pp": improve,
                         "net_vs_C0_pp": net, "C1_interp_upper_bound": c1_med,
                         "ci_halfwidth": hw, "A_ci_halfwidth": a_hw,
                         "gate1_better_than_A": bool(gate1),
                         "gate2_ci_halfwidth_le_25": bool(gate2),
                         "gate3_ci_lt_A": bool(gate3),
                         "gate4_net_gain_vs_C0": bool(gate4),
                         "gate5_below_interp_bound": bool(gate5)}
    summary["verdicts"] = verdicts

    # ---- 分层分析：引擎 PAA 是否失真（分层是本轮的核心发现）----
    # 判据：引擎 PAA 与化验的**批内**相关 A_engine_r。
    #   A_r ≤ 0.5 ⇒ 引擎 PAA 与化验不相关 ⇒ 属「引擎 PAA 失真批」（D-64 的表现）
    strata = {}
    for tag, sel in (("distorted", lambda r: r.get("A_engine_r") is not None
                      and r["A_engine_r"] <= 0.5),
                     ("trustworthy", lambda r: r.get("A_engine_r") is not None
                      and r["A_engine_r"] > 0.5)):
        g = [r for r in good if sel(r)]
        if not g:
            continue
        s_ = {"n": len(g)}
        for key in ("A_engine_nrmse", "B_pat_nrmse", "A2_looa_nrmse",
                    "C_looa_nrmse", "C0_looa_nrmse", "C1_looa_nrmse",
                    "A_engine_r", "B_pat_r", "pat_vs_engine_r",
                    "incr_r2_pat_added", "incr_t_pat", "ols_slope"):
            vals = [r[key] for r in g if r.get(key) is not None]
            if vals:
                s_[key] = {"median": float(np.median(vals)), "n": len(vals)}
        # 符号检验：B vs A
        d_ba = [r["A_engine_nrmse"] - r["B_pat_nrmse"] for r in g
                if r.get("B_pat_nrmse") is not None]
        d_b2 = [r["A2_looa_nrmse"] - r["B_pat_nrmse"] for r in g
                if r.get("A2_looa_nrmse") is not None]
        d_c0 = [r["C0_looa_nrmse"] - r["C_looa_nrmse"] for r in g
                if r.get("C_looa_nrmse") is not None
                and r.get("C0_looa_nrmse") is not None]
        for nm, dd in (("sign_B_vs_A", d_ba), ("sign_B_vs_A2", d_b2), ("sign_C_vs_C0", d_c0)):
            if dd:
                k = sum(1 for x in dd if x > 0)
                nn = len(dd)
                from math import comb
                p_ = sum(comb(nn, i) for i in range(0, min(k, nn - k) + 1)) * 2 / 2 ** nn
                s_[nm] = {"k": k, "n": nn, "p": min(p_, 1.0),
                          "delta_median": float(np.median(dd))}
        strata[tag] = s_
    summary["strata"] = strata

    out = {"summary": summary, "rows": rows,
           "meta": {"pls_unit_scale": PLS_UNIT_SCALE,
                    "pls_unit_intercept": PLS_UNIT_INTERCEPT,
                    "unit_source": "V6 Batch_01 stored spectra -> PLS -> OLS vs PAA_offline",
                    "engine": "unchanged (observation layer only)"}}
    p = os.path.join(ROOT, args.out)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1, default=str)
    print("\n" + "=" * 104)
    print("汇总：")
    for k in ("A_engine_nrmse", "B_pat_nrmse", "C_looa_nrmse", "C0_looa_nrmse",
              "C1_looa_nrmse", "C_net_vs_C0_pp",
              "A_engine_r", "B_pat_r", "C_looa_r", "C0_looa_r", "pat_vs_engine_r",
              "A_ci_halfwidth", "B_ci_halfwidth", "C_ci_halfwidth"):
        s = summary.get(k)
        print("  %-22s %s" % (k, ("median %.4g (n=%d)" % (s["median"], s["n"]))
                              if s else "n/a"))
    print("  verdicts:", json.dumps(verdicts, ensure_ascii=False, indent=1))
    print("\nwritten: %s   (%.1f s)" % (args.out, time.time() - t0))


if __name__ == "__main__":
    main()
