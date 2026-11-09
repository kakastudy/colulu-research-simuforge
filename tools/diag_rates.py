# -*- coding: utf-8 -*-
"""单区间内部速率诊断：对比 sim 内部速率与 V3 隐含速率。"""
import sys
import os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from model import rhs, N_STATES, state_names
from params import make_params

IDX = {name: i for i, name in enumerate(state_names())}


def rates(t, y, inp1, par):
    """计算内部速率（与 rhs 相同公式，独立实现便于检查）。"""
    mu_p, mux_max = par[0], par[1]
    ratio_mu_e_mu_b = par[2]
    P_std_dev, mean_P = par[3], par[4]
    mu_v, mu_a, mu_diff = par[5], par[6], par[7]
    beta_1 = par[8]
    K_b, K_diff, K_diff_L, K_e, K_v = par[9], par[10], par[11], par[12], par[13]
    delta_r, k_v, D = par[14], par[15], par[16]
    rho_a0, rho_d, mu_h = par[17], par[18], par[19]
    r_0, delta_0 = par[20], par[21]
    Y_sX, Y_sP, m_s = par[22], par[23], par[24]
    c_oil, c_s = par[25], par[26]
    Y_O2_X, Y_O2_P, m_O2_X = par[27], par[28], par[29]
    alpha_kla = par[30]
    a, b, c, d = par[31], par[32], par[33], par[34]
    Henrys_c = par[35]
    r, r_imp = par[37], par[38]
    epsilon, g, R = par[40], par[41], par[42]
    X_crit_DO2, P_crit_DO2, A_inhib = par[43], par[44], par[45]
    Tf, Tw, Tcin, Th, Tair = par[46], par[47], par[48], par[49], par[50]
    C_ps, C_pw = par[51], par[52]
    delta_H_evap, U_jacket, A_c = par[53], par[54], par[55]
    Eg, Ed, k_g, k_d = par[56], par[57], par[58], par[59]
    Y_QX = par[60]
    abc = par[61]
    gamma1, gamma2, m_ph = par[62], par[63], par[64]
    K1, K2 = par[65], par[66]
    N_conc_oil = par[67]
    N_conc_paa, N_conc_shot = par[68], par[69]
    Y_NX, Y_NP, m_N = par[70], par[71], par[72]
    X_crit_N = par[73]
    PAA_c = par[74]
    Y_PAA_P, Y_PAA_X, m_PAA = par[75], par[76], par[77]
    X_crit_PAA, P_crit_PAA = par[78], par[79]
    delta_c_0 = par[85]
    t1, t2 = par[89], par[90]
    q_co2, X_crit_CO2 = par[91], par[92]
    pho_g, pho_oil, pho_w, pho_paa = par[95], par[96], par[97], par[98]
    O_2_in, N2_in, C_CO2_in = par[99], par[100], par[101]
    alpha_evp, beta_T = par[93], par[94]
    alpha_1 = par[104]
    Tv, T0 = par[102], par[103]

    inhib_flag = inp1[0]
    Fs = inp1[1]
    Fg = inp1[2] / 60.0
    RPM = inp1[3]
    Fc = inp1[4]
    Fh = inp1[5]
    Fb = inp1[6]
    Fa = inp1[7]
    step1 = inp1[8]
    Fw = inp1[9]
    if Fw < 0:
        Fw = 0.0
    pressure = inp1[10]
    F_discharge = inp1[12]
    Fpaa = inp1[13]
    Foil = inp1[14]
    NH3_shots = inp1[15]

    s = y[0]
    do2 = y[1]
    o2 = y[2]
    p = y[3]
    v = y[4]
    wt = y[5]
    h = y[6]
    temp = y[7]
    vis = y[9]
    a0 = y[11]
    a1 = y[12]
    a3 = y[13]
    a4 = y[14]
    co2 = y[27]
    co2d = y[28]
    paa = y[29]
    nh3 = y[30]
    a_t1 = y[10]
    total_x = a0 + a1 + a3 + a4

    if inhib_flag == 2:
        ph_inhib = 1.0 / (1.0 + h / K1 + K2 / h)
        nh3_inhib = 0.5 * (1.0 - np.tanh(X_crit_N - nh3))
        t_inhib = k_g * np.exp(-Eg / (R * temp)) - k_d * np.exp(-Ed / (R * temp))
        h_b = (v / 1000.0) / (np.pi * r ** 2) * (1.0 - epsilon)
        pressure_bottom = 1.0 + pressure + (pho_g * h_b) * g * 1e-5
        total_pressure = (pressure_bottom - pressure) / np.log(pressure_bottom / pressure)
        do_star_tp = (total_pressure * O_2_in) / Henrys_c
        do_2_inhib_x = 0.5 * (1.0 - np.tanh(X_crit_DO2 * do_star_tp - do2))
        co2_inhib = 0.5 * (1.0 + np.tanh(X_crit_CO2 - co2d * 1000.0))
        paa_inhib_x = 0.5 * (1.0 + np.tanh(X_crit_PAA - paa))
        mu_e = mux_max * ph_inhib * nh3_inhib * t_inhib * do_2_inhib_x * co2_inhib * paa_inhib_x
        mu_a0 = ratio_mu_e_mu_b * mux_max * ph_inhib * nh3_inhib * t_inhib * do_2_inhib_x * co2_inhib * paa_inhib_x
    else:
        mu_e = mux_max
        mu_a0 = ratio_mu_e_mu_b * mux_max

    k_diff = par[10] - a_t1 * beta_1
    if k_diff < K_diff_L:
        k_diff = K_diff_L

    r_e1 = mu_e * a0 * s / (K_e + s)
    r_b0 = mu_a0 * a1 * s / (K_b + s)
    r_d1 = mu_diff * a0 / (K_diff + s)
    r_d4 = mu_a * a3 / (K_diff + s)
    r_se1 = Y_sX * r_e1
    r_sb0 = Y_sX * r_b0
    r_m0 = m_s * a0 / (K_diff + s)
    r_m1 = m_s * rho_a0 * v_a1 * s / (K_v + s) if False else 0.0

    phi = np.zeros(10)
    v_2 = phi[0] + np.sum(phi[1:])
    rho_a1 = a1 / (a1 / rho_a0 + v_2) if a1 > 0 else rho_a0
    v_a1 = a1 / (2.0 * rho_a1) - v_2
    r_m1 = m_s * rho_a0 * v_a1 * s / (K_v + s)

    p_inhib = 2.5 * P_std_dev * ((P_std_dev * np.sqrt(2 * np.pi)) ** -1
                                 * np.exp(-0.5 * ((s - mean_P) / P_std_dev) ** 2))
    do_2_inhib_p = 0.5 * (1.0 - np.tanh(P_crit_DO2 * do_star_tp - do2))
    paa_inhib_p = 0.5 * (1.0 + np.tanh(X_crit_PAA - paa))
    r_p = mu_p * rho_a0 * v_a1 * p_inhib * do_2_inhib_p * paa_inhib_p - mu_h * p

    x_1 = r_e1 - a0 * 0.0  # 粗略
    our = -x_1 * Y_O2_X - m_O2_X * total_x - 0.0 * Y_O2_P

    return {
        "mu_e": mu_e, "mu_a0": mu_a0, "a0": a0, "a1": a1, "a3": a3, "a4": a4,
        "total_x": total_x, "r_e1": r_e1, "r_b0": r_b0, "r_d1": r_d1, "r_d4": r_d4,
        "r_se1": r_se1, "r_sb0": r_sb0, "r_m0": r_m0, "r_m1": r_m1,
        "r_p": r_p, "p_inhib": p_inhib, "v_a1": v_a1, "our_approx": our,
        "do2": do2, "ph": -np.log10(h), "temp": temp, "s": s, "paa": paa, "nh3": nh3,
    }


def main():
    batch = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    d = pd.read_csv(f"data/processed/batches/batch_{batch:02d}.csv")
    par = make_params(alpha_kla=85.0, N_conc_paa=150000.0, PAA_c=530000.0,
                      mup=0.041, mux=0.41, c_oil=1000.0)
    # 用 sim_batch 的轨迹做初始状态（逐点取）
    sim = pd.read_csv(f"data/processed/sim_batch_{batch:02d}.csv")
    for target_t in [200.0, 200.2, 200.4, 200.6, 201.0, 202.0, 204.0]:
        row = sim[sim.time_h <= target_t].iloc[-1]
        y = np.zeros(N_STATES)
        y[IDX["S"]] = row["S"]; y[IDX["DO2"]] = row["DO2"]; y[IDX["O2"]] = row["O2"]
        y[IDX["P"]] = row["P"]; y[IDX["V"]] = row["V"]; y[IDX["Wt"]] = row["Wt"]
        y[IDX["pH_H"]] = 10 ** (-row["pH"]); y[IDX["T"]] = row["T"]; y[IDX["Q"]] = 0.001
        y[IDX["vis"]] = row["vis"] if "vis" in row else 4.0
        y[IDX["A0"]] = row["A0"]; y[IDX["A1"]] = row["A1"]; y[IDX["A3"]] = row["A3"]; y[IDX["A4"]] = row["A4"]
        y[IDX["CO2"]] = row["CO2outgas"]; y[IDX["PAA"]] = row["PAA"]; y[IDX["NH3"]] = row["NH3"]
        rowv = d[d.time_h <= target_t + 0.2].iloc[-1]
        inp1 = np.array([2, rowv["Fs"], rowv["Fg"], rowv["RPM"], rowv["Fc"], rowv["Fh"],
                         rowv["Fb"], rowv["Fa"], 0.01, rowv["Fw"], rowv["pressure"], 0.0,
                         rowv["Fremoved"], rowv["Fpaa"], rowv["Foil"], rowv["NH3_shots"],
                         0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
        r = rates(target_t, y, inp1, par)
        print(f"t={target_t:6.1f} mu_e={r['mu_e']:.4f} a0={r['a0']:.3f} a1={r['a1']:.3f} "
              f"X={r['total_x']:.2f} r_e1={r['r_e1']:.4f} r_b0={r['r_b0']:.4f} "
              f"r_se1={r['r_se1']:.4f} r_sb0={r['r_sb0']:.4f} r_m0={r['r_m0']:.4f} r_m1={r['r_m1']:.4f} "
              f"r_p={r['r_p']:.4f} P_inhib={r['p_inhib']:.2e} v_a1={r['v_a1']:.3f} "
              f"pH={r['ph']:.3f} T={r['temp']:.2f} DO2={r['do2']:.2f} S={r['s']:.4f}")


if __name__ == "__main__":
    main()
