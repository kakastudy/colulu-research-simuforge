# -*- coding: utf-8 -*-
"""重构 sim 在 t=200.2 的状态，用 row 200.4 的 MV 计算 S ODE 各分量（正确索引）。"""
import sys
import os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from model import rhs, N_STATES, state_names
from params import make_params

IDX = {name: i for i, name in enumerate(state_names())}

sim = pd.read_csv("data/processed/sim_batch_01.csv")
v3 = pd.read_csv("data/processed/batches/batch_01.csv")

par = make_params(alpha_kla=85.0, N_conc_paa=150000.0, PAA_c=530000.0,
                  mup=0.041, mux=0.41, c_oil=1000.0)

row = sim[sim.time_h <= 200.2].iloc[-1]
y = np.zeros(N_STATES)
y[IDX["S"]] = row["S"]; y[IDX["DO2"]] = row["DO2"]; y[IDX["O2"]] = row["O2"]
y[IDX["P"]] = row["P"]; y[IDX["V"]] = row["V"]; y[IDX["Wt"]] = row["Wt"]
y[IDX["pH_H"]] = 10 ** (-row["pH"]); y[IDX["T"]] = row["T"]; y[IDX["Q"]] = 0.001
y[IDX["vis"]] = row["vis"] if "vis" in row else 4.0
y[IDX["A0"]] = row["A0"]; y[IDX["A1"]] = row["A1"]; y[IDX["A3"]] = row["A3"]; y[IDX["A4"]] = row["A4"]
y[IDX["CO2"]] = row["CO2outgas"]; y[IDX["PAA"]] = row["PAA"]; y[IDX["NH3"]] = row["NH3"]
y[IDX["A_t1"]] = row["A_t1"] if "A_t1" in row else 0.0

rowv = v3[v3.time_h <= 200.4].iloc[-1]
inp1 = np.array([2, rowv["Fs"], rowv["Fg"], rowv["RPM"], rowv["Fc"], rowv["Fh"],
                 rowv["Fb"], rowv["Fa"], 0.01, rowv["Fw"], rowv["pressure"], 0.0,
                 rowv["Fremoved"], rowv["Fpaa"], rowv["Foil"], rowv["NH3_shots"],
                 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])

# 参数（正确索引）
mu_p = par[0]; mux_max = par[1]; ratio = par[2]; P_std_dev = par[3]; mean_P = par[4]
mu_v = par[5]; mu_a = par[6]; mu_diff = par[7]; beta_1 = par[8]; K_b = par[9]
K_diff = par[10]; K_diff_L = par[11]; K_e = par[12]; K_v = par[13]
rho_a0 = par[17]; mu_h = par[19]; Y_sX = par[22]; Y_sP = par[23]; m_s = par[24]
c_oil = par[25]; c_s = par[26]
K1 = par[65]; K2 = par[66]; X_crit_PAA = par[78]; P_crit_PAA = par[79]
X_crit_DO2 = par[43]; P_crit_DO2 = par[44]; A_inhib = par[45]
X_crit_N = par[73]
Henrys_c = par[35]

S = y[0]; DO2 = y[1]; P = y[3]; V = y[4]
A0 = y[11]; A1 = y[12]
total_X = A0 + A1 + y[13] + y[14]

# 抑制项
pH_inhib = 1.0 / (1 + y[6] / K1 + K2 / y[6])
DOstar_tp = 1.64 * 0.204 / Henrys_c
DO_2_inhib_X = 0.5 * (1 - np.tanh(A_inhib * (X_crit_DO2 * DOstar_tp - DO2)))
DO_2_inhib_P = 0.5 * (1 - np.tanh(A_inhib * (P_crit_DO2 * DOstar_tp - DO2)))
PAA_inhib_X = 0.5 * (1 + np.tanh(X_crit_PAA - y[29]))
PAA_inhib_P = 0.5 * (1 + np.tanh(-P_crit_PAA + y[29]))
ph_val = -np.log10(np.maximum(y[6], 1e-12))
k4 = np.exp((par[80] + par[81] * ph_val + par[82] * y[7] + par[83] * ph_val**2) + par[84] * y[7]**2)
mu_h = k4

mu_a0 = ratio * mux_max * pH_inhib * 1.0 * 1.0 * DO_2_inhib_X * 1.0 * PAA_inhib_X
mu_e = mux_max * pH_inhib * 1.0 * 1.0 * DO_2_inhib_X * 1.0 * PAA_inhib_X
A_t1 = A0 / (A1 + y[13] + y[14] + 0.0)
K_diff_eff = par[10] - A_t1 * beta_1
if K_diff_eff < K_diff_L:
    K_diff_eff = K_diff_L
r_b0 = mu_a0 * A1 * S / (K_b + S)
r_sb0 = Y_sX * r_b0
r_e1 = mu_e * A0 * S / (K_e + S)
r_se1 = Y_sX * r_e1
r_d1 = mu_diff * A0 / (K_diff_eff + S)
r_m0 = m_s * A0 / (K_diff_eff + S)
rho_a1 = A1 / (A1 / rho_a0 + 0.0)
v_a1 = A1 / (2 * rho_a1) - 0.0
P_inhib = 2.5 * P_std_dev * (P_std_dev * np.sqrt(2 * np.pi)) ** -1 * np.exp(-0.5 * ((S - mean_P) / P_std_dev) ** 2)
r_p = mu_p * rho_a0 * v_a1 * P_inhib * DO_2_inhib_P * PAA_inhib_P - mu_h * P
r_m1 = m_s * rho_a0 * v_a1 * S / (K_v + S)

Fs, Foil = inp1[1], inp1[14]
dilution = Fs + inp1[6] + inp1[7] + inp1[9] - 0.0 + inp1[13]
print(f"t=200.2: S={S:.6f} A0={A0:.3f} A1={A1:.3f} X={total_X:.2f} V={V:.0f}")
print(f"  pH_inhib={pH_inhib:.4f} DOstar={DOstar_tp:.2f} DO_2_inhib_P={DO_2_inhib_P:.4f} PAA_inhib_P={PAA_inhib_P:.4f} mu_h={mu_h:.5f}")
print(f"  mu_e={mu_e:.4f} mu_a0={mu_a0:.4f} v_a1={v_a1:.3f} P_inhib={P_inhib:.4f}")
print(f"  r_e1={r_e1:.4f} r_b0={r_b0:.4f} r_se1={r_se1:.4f} r_sb0={r_sb0:.4f} r_d1={r_d1:.4f} r_m0={r_m0:.4f} r_m1={r_m1:.4f}")
print(f"  r_p={r_p:.4f} Y_sP*r_p={Y_sP*r_p:.4f}")
print(f"  input: Fs*c_s/V={Fs*c_s/V:.4f} Foil*c_oil/V={Foil*c_oil/V:.4f} total={Fs*c_s/V+Foil*c_oil/V:.4f}")
print(f"  dilution={dilution:.1f} S*dil/V={S*dilution/V:.6f}")
dy = rhs(200.2, y, inp1, par)
print(f"  dy[0] (rhs) = {dy[0]:.10e}")
print(f"  manual: {-(r_se1+r_sb0+r_m0+r_m1) + Fs*c_s/V + Foil*c_oil/V - Y_sP*(mu_p*rho_a0*v_a1*P_inhib*DO_2_inhib_P*PAA_inhib_P) - S*dilution/V:.10e}")
print(f"  manual2: {-(r_se1+r_sb0+r_m0+r_m1) + Fs*c_s/V + Foil*c_oil/V - Y_sP*r_p - S*dilution/V:.10e}")
