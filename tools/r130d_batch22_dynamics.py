# -*- coding: utf-8 -*-
"""R130d: 批 22 动力学解剖 —— S/X/mu_e/维持项/生长项逐时段轨迹。

目的：定位早峰批的「生长停止」机制。输出关键时段的：
- S（底物）、X（生物量）、mu_e（有效比生长速率）
- r_e1（生长速率）、r_m0+r_m1（维持消耗）、r_p（产P速率）
- A0/A1/A3/A4 形态分布

用法：python r130d_batch22_dynamics.py
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop  # noqa: E402
from model import rhs, N_STATES  # noqa: E402
from params import make_params  # noqa: E402
from simulate import build_inp1, build_initial_state, guards  # noqa: E402

B = 22
PARAMS = {"mux": 0.35, "mup": 0.065, "dist_tcin_asym": 20, "m_s": 0.029,
          "m_s_schedule": [(110, 0.010)], "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40,
          "alpha_kla": 85, "mu_h_scale": 3.5}


def main():
    sim, v3 = simulate_open_loop(B, params=PARAMS)
    d = v3

    # 重建参数与初始状态
    par = make_params(alpha_kla=85.0, N_conc_paa=150000.0, PAA_c=530000.0,
                      mup=0.065, mux=0.35, c_oil=1000.0)
    par[24] = 0.029
    par[18] = 3.5
    par[91] = 0.12
    par[70] = 25
    par[71] = 40
    m_s_idx = 0
    m_s_current = 0.029

    y = build_initial_state(d, x0_biomass=None, x0_force=False)
    t_current = float(d.iloc[0]["time_h"])
    mv_row = d.iloc[0]

    rows = []
    k = 1
    for i in range(1, len(d)):
        row = d.iloc[i]
        t_sample = float(row["time_h"])
        if t_sample <= t_current:
            continue
        k += 1
        # m_s schedule
        if m_s_idx < 1 and t_current >= 110:
            m_s_current = 0.010
            par[24] = 0.010
            m_s_idx += 1
        inp1 = build_inp1(mv_row, inhib=2, dist_flag=1,
                          dist_tcin=20.0 * (1 - np.exp(-t_current / 40.0)))
        # 在区间中点评估动力学
        y_mid = y + 0.0
        dy = rhs(t_current, y, inp1, par, biomass_death_rate=0.0, death_start=0.0, vis_scale=1.0)
        # 提取关键速率
        # 需要重新计算内部变量（rhs 内部），这里用近似：从 dy 反推
        # 直接打印状态
        s = y[0]
        x = y[11] + y[12] + y[13] + y[14]
        mu_e = y[32]  # state mux
        a0, a1, a3, a4 = y[11], y[12], y[13], y[14]
        rows.append({
            "t": t_current, "S": s, "X": x, "mu_e": mu_e,
            "A0": a0, "A1": a1, "A3": a3, "A4": a4,
            "dX": dy[11] + dy[12] + dy[13] + dy[14],
            "dS": dy[0], "dP": dy[3],
        })
        # 简单欧拉推进（用于采样，非精确积分）
        h = t_sample - t_current
        y = y + dy * h * 0.5
        y = guards(y)
        t_current = t_sample
        mv_row = row

    df = pd.DataFrame(rows)
    # 关键时段采样
    keys = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 140, 160, 180, 200, 220, 240]
    print(f"{'t':>6s} {'S':>7s} {'X':>7s} {'mu_e':>7s} {'A0':>6s} {'A1':>6s} {'A3':>6s} {'A4':>6s} {'dX/dt':>8s} {'dS/dt':>8s} {'dP/dt':>7s}")
    for kk in keys:
        sub = df[(df['t'] >= kk) & (df['t'] < kk + 10)]
        if len(sub) == 0:
            continue
        r = sub.iloc[len(sub) // 2]
        print(f"{r['t']:6.1f} {r['S']:7.3f} {r['X']:7.2f} {r['mu_e']:7.4f} "
              f"{r['A0']:6.2f} {r['A1']:6.2f} {r['A3']:6.2f} {r['A4']:6.2f} "
              f"{r['dX']:8.4f} {r['dS']:8.4f} {r['dP']:7.4f}")

    # 保存完整轨迹
    df.to_csv(f"data/processed/r130d_batch22_dynamics.csv", index=False)
    print("Saved: data/processed/r130d_batch22_dynamics.csv")


if __name__ == "__main__":
    main()
