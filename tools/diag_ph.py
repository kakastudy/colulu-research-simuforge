# -*- coding: utf-8 -*-
"""重构 sim 在 t=200 的状态，用 row 200.2 的 MV 计算 dy[6] 各分量。"""
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

# 用 sim 在 t=200 的状态（来自 sim_batch_01.csv，nominal 参数）
row = sim[sim.time_h <= 200.0].iloc[-1]
y = np.zeros(N_STATES)
y[IDX["S"]] = row["S"]; y[IDX["DO2"]] = row["DO2"]; y[IDX["O2"]] = row["O2"]
y[IDX["P"]] = row["P"]; y[IDX["V"]] = row["V"]; y[IDX["Wt"]] = row["Wt"]
y[IDX["pH_H"]] = 10 ** (-row["pH"]); y[IDX["T"]] = row["T"]; y[IDX["Q"]] = 0.001
y[IDX["vis"]] = row["vis"] if "vis" in row else 4.0
y[IDX["A0"]] = row["A0"]; y[IDX["A1"]] = row["A1"]; y[IDX["A3"]] = row["A3"]; y[IDX["A4"]] = row["A4"]
y[IDX["CO2"]] = row["CO2outgas"]; y[IDX["PAA"]] = row["PAA"]; y[IDX["NH3"]] = row["NH3"]
y[IDX["A_t1"]] = row["A_t1"] if "A_t1" in row else 0.0
print(f"t=200: y7={y[6]:.4e} pH={-np.log10(y[6]):.3f} X={y[11]+y[12]+y[13]+y[14]:.2f} V={y[4]:.0f}")

# row 200.2 的 MV
for tt in [200.0, 200.2, 200.4, 200.6, 200.8, 201.0, 201.2, 201.4, 201.6, 201.8, 202.0]:
    rowv = v3[v3.time_h <= tt].iloc[-1]
    inp1 = np.array([2, rowv["Fs"], rowv["Fg"], rowv["RPM"], rowv["Fc"], rowv["Fh"],
                     rowv["Fb"], rowv["Fa"], 0.01, rowv["Fw"], rowv["pressure"], 0.0,
                     rowv["Fremoved"], rowv["Fpaa"], rowv["Foil"], rowv["NH3_shots"],
                     0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
    dy = rhs(200.0, y, inp1, par)
    # 手工分解 pH
    y7 = y[6]
    if -np.log10(y7) < 7:
        cb, ca, y7u, pbal = -0.033, 0.033, y7, 0
    else:
        cb, ca, y7u, pbal = 0.033, -0.033, 1e-14 / y7 - y7, 1
    Fa, Fb, step1, V = inp1[7], inp1[6], 0.01, y[4]
    B = (y7u * V + ca * Fa * step1 + cb * Fb * step1) / (V + Fb * step1 + Fa * step1)
    B = -B
    term_B = ((-B + np.sqrt(B**2 + 4e-14)) / 2 - y7u) if pbal == 0 else ((-B - np.sqrt(B**2 + 4e-14)) / 2 - y7u)
    gamma1 = par[62]
    # ph_prod
    total_X = y[11] + y[12] + y[13] + y[14]
    mu_e = par[1] * 0.5 / (1 + y7 / par[65] + par[66] / y7) * 0.5 * (1 - np.tanh(par[73] - y[30])) * 1.0
    # 简化：只打印 B 相关
    print(f"  t={tt}: Fb={Fb:7.2f} Fa={Fa:6.2f} B={B:+.3e} B_orig={-B:+.3e} termB={term_B:+.3e} dy6={dy[6]:+.3e}")
