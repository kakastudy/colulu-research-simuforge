# -*- coding: utf-8 -*-
"""PH2：D(x) 衰亡项拟合验证管道。

候选衰亡形式（对 X 轨迹修正）：
  X_corr(t) = X_sim(t) − c1·X(t) − c2·X(t)·A_t1(t) − c3·X(t)·A_t1(t)²
候选字典由 td古人模型（A_t1 = a0/(a1+a3+a4) 培养年龄比——引擎内已定义）。
跨批 least squares（训练池 θ_b），真值 = V3 X_offline（滞后 4h 对齐）。
验收：批 11/8 的 EnKF/平滑器 X 覆盖率提升（目标 ≥60%）+ 状态 RMSE X 下降。
"""
import os
import sys
import json

import numpy as np
import pandas as pd

sys.path.insert(0, 'candidate/indpensim/v0.1')
from simulate import simulate_open_loop
import hier_est as he

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(ROOT)
ASSAY_DELAY = 4.0


def X_resid_points(batch_no, theta):
    """θ_b 重放 → X 残差点（对 V3 化验点、滞后 4h）。"""
    tp = theta["theta_post"]
    params = {"mux": tp["mux"], "mup": tp["mup"], "m_s": tp["m_s"], "alpha_kla": 85.0,
              "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
              "dist_flag": 1, "dist_tcin_asym": 10}
    sim, v3 = simulate_open_loop(batch_no, params)
    t_sim = sim["time_h"].to_numpy(float)
    xo = pd.to_numeric(v3["X_offline"], errors="coerce").notna().to_numpy()
    lab = v3.loc[xo, "time_h"].to_numpy(float)
    sim_x = np.interp(lab - ASSAY_DELAY, t_sim, sim["X"].to_numpy(float))
    v_x = pd.to_numeric(v3.loc[xo, "X_offline"], errors="coerce").to_numpy(float)
    # 引擎 A_t1（=a0/(a1+a3+a4)）与 X 状态（同一时刻插值）
    a0 = sim["A0"].to_numpy(float); a1 = sim["A1"].to_numpy(float)
    a3 = sim["A3"].to_numpy(float); a4 = sim["A4"].to_numpy(float)
    at1 = a0 / np.maximum(a1 + a3 + a4, 1e-9)
    corr_t = lab - ASSAY_DELAY
    sim_X_at = np.interp(corr_t, t_sim, sim["X"].to_numpy(float))
    at1_at = np.interp(corr_t, t_sim, at1)
    return pd.DataFrame({"batch": batch_no, "t": lab, "resid": sim_x - v_x,
                         "X": sim_X_at, "A_t1": at1_at})


if __name__ == "__main__":
    tl = he.load_theta_log()
    thetas = {r["batch"]: r for r in tl}
    print(f"v1 证据池 {len(thetas)} 批")
    dfs = []
    for b in sorted(thetas.keys())[:30]:
        try:
            dfs.append(X_resid_points(b, thetas[b]))
        except Exception as e:
            print(f"  batch {b}: {type(e).__name__} {e}")
    all_pts = pd.concat(dfs, ignore_index=True)
    print(f"X 残差点 {len(all_pts)}（跨 30 批）")

    # 候选字典 X·A_t1、X·A_t1²、X；跨批 least squares
    F = np.column_stack([all_pts["X"] / 100.0,
                         all_pts["X"] * all_pts["A_t1"] / 100.0,
                         all_pts["X"] * all_pts["A_t1"] ** 2 / 100.0])
    y = all_pts["resid"].to_numpy(float)
    beta, *_ = np.linalg.lstsq(F, y, rcond=None)
    pred = F @ beta
    names = ["kd1·X/100", "kd2·X·A_t1/100", "kd3·X·A_t1²/100"]
    print("\ndeath-term fitted coefficients:")
    for n, b in zip(names, beta):
        print(f"  {n}: {b:+.4f}".encode("gbk", "replace").decode("gbk"))
    resid_before = y.std()
    resid_after = (y - pred).std()
    r2 = 1 - resid_after ** 2 / resid_before ** 2
    msg = (f"X resid sigma: {resid_before:.3f} -> after-term {resid_after:.3f} ; "
           f"R2 = {r2:.3f}")
    print(msg.encode("gbk", "replace").decode("gbk"))

    out = {"n_points": len(all_pts), "beta": beta.tolist(), "names": names,
           "std_before": round(float(resid_before), 4),
           "std_after": round(float(resid_after), 4),
           "r2": round(float(1 - resid_after ** 2 / resid_before ** 2), 4)}
    os.makedirs("runs/hier_est", exist_ok=True)
    with open("runs/hier_est/death_term.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("Saved: runs/hier_est/death_term.json")
