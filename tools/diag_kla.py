# -*- coding: utf-8 -*-
"""计算 sim t=200.2 状态下的 OUR/OTR/kla/CO2d 导数。"""
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

dy = rhs(200.2, y, inp1, par)
print(f"dy[1] (DO2) = {dy[1]:.4f}")
print(f"dy[28] (CO2d) = {dy[28]:.4f}")
print(f"dy[27] (CO2) = {dy[27]:.4f}")
print(f"CO2d state = {y[28]:.6f}")
print(f"CO2 offgas = {y[27]:.6f}")

# 手动复算 OUR/OTR/kla
mu_p = par[0]; mux_max = par[1]
rho_a0 = par[17]; Y_O2_X = par[27]; Y_O2_P = par[28]; m_O2_X = par[29]
alpha_kla = par[30]; a = par[31]; b = par[32]; c = par[33]; d = par[34]
Henrys_c = par[35]; n_imp = par[36]; r = par[37]; r_imp = par[38]; Po = par[39]
epsilon = par[40]; g = par[41]; R = par[42]
delta_c_0 = par[85]
q_co2 = par[91]; X_crit_CO2 = par[92]
O_2_in = par[99]

Fg = inp1[2] / 60.0
RPM = inp1[3]
V = y[4]
V_m = V / 1000.0
viscosity = y[9] if row.get("vis") is not None else 4.0
if viscosity < 4:
    viscosity = 1.0
if viscosity <= 4:
    viscosity = 1.0
vis_scaled = viscosity / 100.0
oil_f = inp1[14] / V
N = RPM / 60.0
D_imp = 2 * r_imp
pho_b = 1100.0 + y[3] + y[11] + y[12] + y[13] + y[14]
unaerated_power = n_imp * Po * pho_b * N**3 * D_imp**5
P_g = 0.706 * (((unaerated_power**2) * N * D_imp**3) / (Fg**0.56)) ** 0.45
P_n = P_g / unaerated_power
variable_power = (n_imp * Po * pho_b * N**3 * D_imp**5 * P_n) / 1000.0
V_s = Fg / (np.pi * r * r)
h_b = (V / 1000.0) / (np.pi * r * r) * (1 - epsilon)
pressure_top = 1 + inp1[10]
P_air = (V_s * R * y[7] * V_m / (22.4 * h_b)) * np.log(1 + pho_b * 9.81 * h_b / (pressure_top * 1e5))
P_t1 = variable_power + P_air
kla = alpha_kla * ((V_s ** a) * ((P_t1 / V_m) ** b) * (vis_scaled ** c)) * (1 - oil_f ** d)
print(f"Fg={Fg:.4f} V_s={V_s:.4f} P_t1={P_t1:.2f} P_t1/V_m={P_t1/V_m:.3f} kla={kla:.2f}")
print(f"vis_scaled={vis_scaled:.4f} oil_f={oil_f:.6f}")
# DOstar
total_pressure = 1.64  # 近似
DOstar_tp = (total_pressure * O_2_in) / Henrys_c
print(f"DOstar_tp={DOstar_tp:.2f} DO2={y[1]:.2f}")
