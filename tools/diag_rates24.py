# -*- coding: utf-8 -*-
"""完整诊断 mux=0.24 在 t=200 的所有速率。"""
import sys
import os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from model import rhs, N_STATES, state_names
from params import make_params

IDX = {name: i for i, name in enumerate(state_names())}

sim = pd.read_csv("runs/sim_mux024.csv")
v3 = pd.read_csv("data/processed/batches/batch_01.csv")

par = make_params(alpha_kla=85.0, N_conc_paa=150000.0, PAA_c=530000.0,
                  mup=0.041, mux=0.24, c_oil=1000.0)

t_target = 200.0
row = sim[sim.time_h <= t_target].iloc[-1]
y = np.zeros(N_STATES)
y[IDX["S"]] = row["S"]; y[IDX["DO2"]] = row["DO2"]; y[IDX["O2"]] = row["O2"]
y[IDX["P"]] = row["P"]; y[IDX["V"]] = row["V"]; y[IDX["Wt"]] = row["Wt"]
y[IDX["pH_H"]] = 10 ** (-row["pH"]); y[IDX["T"]] = row["T"]; y[IDX["Q"]] = 0.001
y[IDX["vis"]] = row["vis"] if "vis" in row else 4.0
y[IDX["A0"]] = row["A0"]; y[IDX["A1"]] = row["A1"]; y[IDX["A3"]] = row["A3"]; y[IDX["A4"]] = row["A4"]
y[IDX["CO2"]] = row["CO2outgas"]; y[IDX["CO2d"]] = row["CO2d"]; y[IDX["PAA"]] = row["PAA"]; y[IDX["NH3"]] = row["NH3"]
y[IDX["A_t1"]] = row["A_t1"] if "A_t1" in row else 0.0

rowv = v3[v3.time_h <= t_target + 0.2].iloc[-1]
inp1 = np.array([2, rowv["Fs"], rowv["Fg"], rowv["RPM"], rowv["Fc"], rowv["Fh"],
                 rowv["Fb"], rowv["Fa"], 0.01, rowv["Fw"], rowv["pressure"], 0.0,
                 rowv["Fremoved"], rowv["Fpaa"], rowv["Foil"], rowv["NH3_shots"],
                 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])

# 手动计算关键中间量
Fg = inp1[2] / 60.0
Fs = inp1[1]; Foil = inp1[14]; Fpaa = inp1[13]
s = y[0]; a_0 = y[11]; a_1 = y[12]; P = y[3]; V = y[4]; CO2d = y[28]; CO2 = y[27]
pH_H = y[6]; T = y[7]; NH3 = y[30]; PAA = y[29]

mu_p = par[0]; mux_max = par[1]; ratio = par[2]; P_sd = par[3]; mean_P = par[4]
mu_a = par[6]; mu_diff = par[7]; beta_1 = par[8]; K_b = par[9]; K_diff = par[10]
K_diff_L = par[11]; K_e = par[12]; K_v = par[13]; mu_h = par[19]
Y_sX = par[22]; Y_sP = par[23]; m_s = par[24]; c_oil = par[25]; c_s = par[26]
alpha_kla = par[30]; Henrys_c = par[35]; X_crit_DO2 = par[43]; P_crit_DO2 = par[44]
A_inhib = par[45]; X_crit_N = par[73]; X_crit_PAA = par[78]; P_crit_PAA = par[79]
k_g = par[58]; k_d = par[59]; Eg = par[56]; Ed = par[57]
K1 = par[65]; K2 = par[66]; q_co2 = par[91]; X_crit_CO2 = par[92]
O_2_in = par[99]; C_CO2_in = par[101]; delta_c_0 = par[85]
rho_a0 = par[17]

# 压力
h_b = (V / 1000.0) / (np.pi * par[37]**2) * (1 - par[40])
pb = 1 + inp1[10] + par[95] * h_b * 9.81 * 1e-5
pt = 1 + inp1[10]
tp = (pb - pt) / np.log(pb / pt)
DOstar_tp = (tp * O_2_in) / Henrys_c

# 抑制
pH_val = -np.log10(max(pH_H, 1e-12))
pH_inhib = 1.0 / (1 + pH_H / K1 + K2 / pH_H)
NH3_inhib = 0.5 * (1 - np.tanh(A_inhib * (X_crit_N - NH3)))
T_inhib = k_g * np.exp(-Eg / (par[42] * T)) - k_d * np.exp(-Ed / (par[42] * T))
CO2_inhib = 0.5 * (1 + np.tanh(A_inhib * (X_crit_CO2 - CO2d * 1000)))
DO_2_inhib_X = 0.5 * (1 - np.tanh(A_inhib * (X_crit_DO2 * DOstar_tp - y[1])))
DO_2_inhib_P = 0.5 * (1 - np.tanh(A_inhib * (P_crit_DO2 * DOstar_tp - y[1])))
PAA_inhib_X = 0.5 * (1 + np.tanh(X_crit_PAA - PAA))
PAA_inhib_P = 0.5 * (1 + np.tanh(-P_crit_PAA + PAA))

mu_e = mux_max * pH_inhib * NH3_inhib * T_inhib * DO_2_inhib_X * CO2_inhib * PAA_inhib_X
mu_a0 = ratio * mu_e

P_inhib = 2.5 * P_sd * ((P_sd * np.sqrt(2 * np.pi)) ** -1 * np.exp(-0.5 * ((s - mean_P) / P_sd) ** 2))

K_diff_eff = max(K_diff - y[15] * beta_1, K_diff_L) if hasattr(y, 'A_t1') else K_diff
K_diff_eff = max(K_diff - 0.0 * beta_1, K_diff_L)

r_b0 = mu_a0 * a_1 * s / (K_b + s)
r_se1 = Y_sX * mu_e * a_0 * s / (K_e + s)
r_sb0 = Y_sX * r_b0
r_m0 = m_s * a_0 / (K_diff_eff + s)
r_d1 = mu_diff * a_0 / (K_diff_eff + s)
rho_a1 = a_1 / (a_1 / rho_a0 + 0.0)
v_a1 = a_1 / (2 * rho_a1) - 0.0
r_p = mu_p * rho_a0 * v_a1 * P_inhib * DO_2_inhib_P * PAA_inhib_P - mu_h * P
r_m1 = m_s * rho_a0 * v_a1 * s / (K_v + s)

# 体积/稀释
F_evp = V * par[93] * (np.exp(2.5 * (T - par[103]) / (par[102] - par[103])) - 1)
dilution = Fs + inp1[6] + inp1[7] + inp1[9] - F_evp + Fpaa

input_rate = Fs * c_s / V + Foil * c_oil / V
consumption = r_se1 + r_sb0 + r_m0 + r_m1 + Y_sP * mu_p * rho_a0 * v_a1 * P_inhib * DO_2_inhib_P * PAA_inhib_P

print(f"=== mux=0.24 @ t=200 ===")
print(f"S={s:.6f} A0={a_0:.3f} A1={a_1:.3f} X={a_0+a_1:.2f} P={P:.2f} V={V:.0f}")
print(f"pH={pH_val:.3f} T={T:.2f} DO2={y[1]:.2f} CO2={CO2:.3f} CO2d={CO2d:.3f} NH3={NH3:.1f} PAA={PAA:.1f}")
print(f"DOstar_tp={DOstar_tp:.2f} total_pressure={tp:.3f}")
print(f"pH_inhib={pH_inhib:.3f} NH3_inhib={NH3_inhib:.3f} T_inhib={T_inhib:.3f} "
      f"CO2_inhib={CO2_inhib:.3f} DO2iX={DO_2_inhib_X:.3f} DO2iP={DO_2_inhib_P:.3f} "
      f"PAAiX={PAA_inhib_X:.3f} PAAiP={PAA_inhib_P:.3f}")
print(f"mu_e={mu_e:.4f} mu_a0={mu_a0:.4f}")
print(f"r_e1={mu_e*a_0*s/(K_e+s):.4f} r_b0={r_b0:.4f} r_se1={r_se1:.4f} r_sb0={r_sb0:.4f}")
print(f"r_m0={r_m0:.4f} r_m1={r_m1:.4f} r_d1={r_d1:.4f}")
print(f"r_p={r_p:.4f} P_inhib={P_inhib:.4f} v_a1={v_a1:.2f}")
print(f"input={input_rate:.4f} consumption={consumption:.4f} diff={input_rate-consumption:.4f}")
print(f"dilution={dilution:.0f} F_evp={F_evp:.1f}")
print(f"X_1={r_e1-mu_h*a_1:.4f} (r_e1 - r_d2)")
print(f"dy[S]={-consumption+input_rate-s*dilution/V:.6f}")
