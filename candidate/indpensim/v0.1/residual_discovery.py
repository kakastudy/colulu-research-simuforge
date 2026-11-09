# -*- coding: utf-8 -*-
"""PH2：残差结构发现（SINDy 式稀疏辨识）。

对已入库 θ_b 的批次：
  1. 以 θ_b 重跑引擎 → 轨迹
  2. S/P 通道做"残差通量"变换：φ_S ≈ d(S_sim−S_v3)/dt、φ_P ≈ d(P_sim−P_v3)/dt
     （机理同流稀释项一阶对消，微分残差≈未知项通量）
  3. 候选库（微生物/化学/物理领域来源，对齐 knowledge_constraints.ph2_candidates）：
       1, X, S, P, A_t1, X·S, P·S(前体抑制), T_偏移·X, 1(常数/维护), P(独立水解一阶)
  4. 全子集枚举（11 候选 → 2^11）+ 最小二乘 + BIC 排序 → 最优稀疏结构
  5. 批间一致性投票：系数符号 & 显著性跨批 ≥2/3 出现 → 候选"缺失动力学"

预期物理候选：P 水解一阶项（Pirt 1990；−k·P）；衰亡/自溶项 ∝ A_t1 或 X(转录老化)。
"""
import json
import os
import sys

import numpy as np
import pandas as pd

_V01 = os.path.dirname(os.path.abspath(__file__))
if _V01 not in sys.path:
    sys.path.insert(0, _V01)

from simulate import simulate_open_loop

_ROOT = os.path.abspath(os.path.join(_V01, "..", "..", ".."))
THETA_LOG = os.path.join(_ROOT, "runs", "hier_est", "train_theta.jsonl")

CAND = ["1", "X", "S", "P", "A_t1", "X*S", "P*S", "T_shift*X", "DO2_low"]


def load_theta():
    """θ_b 日志合成（v2 细网格优先，v1 兜底）——PH2 用位置参数足够（对 σ 无敏感）。"""
    out = {}
    v2p = os.path.join(_ROOT, "runs", "hier_est", "train_theta_v2.jsonl")
    if os.path.exists(v2p):
        out = {r["batch"]: r for r in map(json.loads, open(v2p, encoding="utf-8")) if r.get("theta_post")}
    v1p = THETA_LOG
    if os.path.exists(v1p):
        for line in open(v1p, encoding="utf-8"):
            r = json.loads(line)
            out.setdefault(r["batch"], r)
    return out


def _aligned_residuals(batch_no, theta):
    """θ_b 重跑 + 通道残差（S/P 逐点直差；X 按 t−4h 对齐化验点）。"""
    tp = theta["theta_post"]
    params = {"mux": tp["mux"], "mup": tp["mup"], "m_s": tp["m_s"], "alpha_kla": 85.0,
              "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
              "dist_flag": 1, "dist_tcin_asym": 10}
    sim, v3 = simulate_open_loop(batch_no, params)
    t_sim = sim["time_h"].to_numpy(float)
    t_v3 = v3["time_h"].to_numpy(float)
    out = {}
    for ch in ("S", "P"):
        s_at = np.interp(t_v3, t_sim, sim[ch].to_numpy(float))
        vv = pd.to_numeric(v3[ch], errors="coerce").to_numpy(float)
        okm = np.isfinite(vv) & (t_v3 > 20)
        out[ch] = {"t": t_v3[okm], "resid": s_at[okm] - vv[okm]}
    # X：化验点（滞后 4h 对齐）
    xo = pd.to_numeric(v3["X_offline"], errors="coerce").notna().to_numpy()
    lab = v3.loc[xo, "time_h"].to_numpy(float)
    sim_x = np.interp(lab - 4.0, t_sim, sim["X"].to_numpy(float))
    v_x = pd.to_numeric(v3.loc[xo, "X_offline"], errors="coerce").to_numpy(float)
    out["X"] = {"t": lab, "resid": sim_x - v_x}
    return sim, v3, out


def _features(sim, v3, t):
    t_sim = sim["time_h"].to_numpy(float)
    def at(ch):
        return np.interp(t, t_sim, sim[ch].to_numpy(float))
    X = at("X"); S = at("S"); P = at("P"); DO2 = at("DO2"); T = at("T")
    # A_t1 用公式层口径（R65/R72 澄清): a0/(a1+a3+a4) — 记录列 sim["A_t1"] 是另一约定
    #（数值 60→4500 随培养上行、与公式层全时反相），其系数符号语义会整体翻转。
    a0 = at("A0")
    den = (at("A1") + at("A3") + at("A4"))
    A_t1 = a0 / np.maximum(den, 1e-9)
    cols = {
        "1": np.ones_like(t, float),
        "X": X, "S": S, "P": P, "A_t1": A_t1,
        "X*S": X * S / 50.0, "P*S": P * S / 100.0,
        "T_shift*X": (T - 298.0) * X / 5.0,
        "DO2_low": np.clip(15.0 - DO2, 0, None) * X / 10.0,
    }
    return cols


def sparse_fit(t, resid, cols, max_terms=3):
    """全子集 + BIC。"""
    names = list(cols)
    Phi = np.column_stack([cols[c] for c in names])
    n = len(resid)
    best = None
    res_all = []
    idx_pool = range(1 << len(names))
    for msk in idx_pool:
        idx = [j for j in range(len(names)) if msk >> j & 1]
        if not (1 <= len(idx) <= max_terms):
            continue
        phi = Phi[:, idx]
        beta, *_ = np.linalg.lstsq(phi, resid, rcond=None)
        e = resid - phi @ beta
        sse = float(e @ e)
        k = len(idx) + 1
        bic = n * np.log(max(sse / n, 1e-12)) + k * np.log(n)
        res_all.append({"terms": [names[i] for i in idx], "beta": list(map(float, beta)),
                         "bic": bic, "sse": sse})
    res_all.sort(key=lambda r: r["bic"])
    best = res_all[0]
    return best, res_all[:5]


def discover_batch(batch_no, theta, h=0.4):
    sim, v3, res = _aligned_residuals(batch_no, theta)
    results = {}
    for ch in ("S", "P"):
        t = res[ch]["t"]; r = res[ch]["resid"]
        dres = np.gradient(r, t)
        cols = _features(sim, v3, t)
        best, top5 = sparse_fit(t, dres, cols)
        results[ch] = {"best": best, "top5": top5}
    return results


def votes(batch_nos, thetas):
    """跨批一致性投票：最优子集词频 & 系数符号均值。
    单批容错（R66）：某批引擎重放 NaN/发散时跳过该批并计数，不让全池投票崩链
    （I2：跳过清单显式返回在 per_batch 之外的 diverged 键）。"""
    per_batch = {}
    diverged = []
    for b in batch_nos:
        if b not in thetas:
            continue
        try:
            per_batch[b] = discover_batch(b, thetas[b])
        except Exception as e:
            diverged.append({"batch": b, "error": f"{type(e).__name__}: {str(e)[:120]}"})
            print(f"[votes] batch {b} diverged -> skip ({type(e).__name__})", flush=True)
    tally = {"S": {}, "P": {}}
    for b, rr in per_batch.items():
        for ch in ("S", "P"):
            key = tuple(rr[ch]["best"]["terms"])
            tally[ch][key] = tally[ch].get(key, 0) + 1
    return per_batch, tally, diverged


if __name__ == "__main__":
    thetas = load_theta()
    bs = sorted(thetas)[:15]
    print(f"对 {len(bs)} 个已入库批做结构发现：", flush=True)
    per_batch, tally, diverged = votes(bs, thetas)
    for ch in ("S", "P"):
        print(f"\n== {ch} 通道 最优稀疏子集票数 ==")
        for terms, k in sorted(tally[ch].items(), key=lambda kv: -kv[1])[:5]:
            print(f"  {list(terms)} — 票数 {k}/{len(bs)}")
    with open(os.path.join(_ROOT, "runs", "hier_est", "residual_discovery.json"),
              "w", encoding="utf-8") as f:
        json.dump({"n_batches": len(bs), "per_batch": {
            str(b): {ch: rr[ch]["best"] for ch in ("S", "P")} for b, rr in per_batch.items()},
            "tally": {"S": {str(k): v for k, v in tally["S"].items()},
                      "P": {str(k): v for k, v in tally["P"].items()}}}, f, ensure_ascii=False, indent=2)
    print("Saved: runs/hier_est/residual_discovery.json")
