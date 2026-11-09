# -*- coding: utf-8 -*-
"""在 t=76 处重构状态并打印 PAA 方程各分量。"""
import sys
import os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from model import rhs, N_STATES, state_names
from params import make_params

IDX = {name: i for i, name in enumerate(state_names())}

batch = int(sys.argv[1]) if len(sys.argv) > 1 else 1
sim = pd.read_csv(f"data/processed/sim_batch_{batch:02d}.csv")
v3 = pd.read_csv(f"data/processed/batches/batch_{batch:02d}.csv")

par = make_params(alpha_kla=85.0, N_conc_paa=150000.0, PAA_c=530000.0,
                  mup=0.041, mux=0.41, c_oil=1000.0)
print("params[74:80]:", par[74:80])
print("params[22:26]:", par[22:26])

# 在 t=76 重构状态
row = sim[sim.time_h <= 76.0].iloc[-1]
y = np.zeros(N_STATES)
y[IDX["S"]] = row["S"]; y[IDX["DO2"]] = row["DO2"]; y[IDX["O2"]] = row["O2"]
y[IDX["P"]] = row["P"]; y[IDX["V"]] = row["V"]; y[IDX["Wt"]] = row["Wt"]
y[IDX["pH_H"]] = 10 ** (-row["pH"]); y[IDX["T"]] = row["T"]; y[IDX["Q"]] = 0.001
y[IDX["vis"]] = row["vis"] if "vis" in row else 4.0
y[IDX["A0"]] = row["A0"]; y[IDX["A1"]] = row["A1"]; y[IDX["A3"]] = row["A3"]; y[IDX["A4"]] = row["A4"]
y[IDX["CO2"]] = row["CO2outgas"]; y[IDX["PAA"]] = row["PAA"]; y[IDX["NH3"]] = row["NH3"]
y[IDX["A_t1"]] = row["A_t1"] if "A_t1" in row else 0.0

rowv = v3[v3.time_h <= 76.2].iloc[-1]
inp1 = np.array([2, rowv["Fs"], rowv["Fg"], rowv["RPM"], rowv["Fc"], rowv["Fh"],
                 rowv["Fb"], rowv["Fa"], 0.01, rowv["Fw"], rowv["pressure"], 0.0,
                 rowv["Fremoved"], rowv["Fpaa"], rowv["Foil"], rowv["NH3_shots"],
                 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])

# 手动计算 PAA 方程各分量
Fpaa = inp1[13]
PAA_c = par[74]
Y_PAA_P = par[75]
Y_PAA_X = par[76]
m_PAA = par[77]
V = y[4]
Fs = inp1[1]
Fb = inp1[6]
Fa = inp1[7]
Fw = inp1[9]
F_evp = 0.0  # 近似
dilution = Fs + Fb + Fa + Fw - F_evp + Fpaa
print(f"t=76: Fpaa={Fpaa} PAA_c={PAA_c} V={V}")
print(f"dilution={dilution}")
# 需要 dP_dt：用 rhs 的 dy[3] 近似
dy = rhs(76.0, y, inp1, par)
dP_dt = dy[3]
r_p = dP_dt + y[3] * dilution / V
X_1 = dy[11] + dy[12] + dy[13] + dy[14]
print(f"dy[3]=dP_dt={dP_dt:.4f}  r_p={r_p:.4f}  X_1={X_1:.4f}")
print(f"input = Fpaa*PAA_c/V = {Fpaa*PAA_c/V:.2f}")
print(f"-Y_PAA_P*dP_dt = {-Y_PAA_P*dP_dt:.2f}")
print(f"-Y_PAA_X*X_1 = {-Y_PAA_X*X_1:.2f}")
print(f"-m_PAA*P = {-m_PAA*y[3]:.2f}")
print(f"-PAA*dilution/V = {-y[29]*dilution/V:.2f}")
print(f"total dPAA/dt = {dy[29]:.2f}")
print(f"sim PAA(76)={row['PAA']}  sim PAA(78)={sim[sim.time_h<=78.0].iloc[-1]['PAA']}")
