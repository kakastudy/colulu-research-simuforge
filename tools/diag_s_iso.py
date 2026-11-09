# -*- coding: utf-8 -*-
"""S ODE 单独积分测试：固定其他状态，只积分 S，看 BDF 是否跳变。"""
import sys
import os
import numpy as np
import pandas as pd
from scipy.integrate import solve_ivp

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from model import rhs, N_STATES, state_names
from params import make_params

IDX = {name: i for i, name in enumerate(state_names())}

sim = pd.read_csv("data/processed/sim_batch_01.csv")
v3 = pd.read_csv("data/processed/batches/batch_01.csv")

par = make_params(alpha_kla=85.0, N_conc_paa=150000.0, PAA_c=530000.0,
                  mup=0.041, mux=0.41, c_oil=1000.0)

row = sim[sim.time_h <= 200.2].iloc[-1]
y0 = np.zeros(N_STATES)
y0[IDX["S"]] = row["S"]; y0[IDX["DO2"]] = row["DO2"]; y0[IDX["O2"]] = row["O2"]
y0[IDX["P"]] = row["P"]; y0[IDX["V"]] = row["V"]; y0[IDX["Wt"]] = row["Wt"]
y0[IDX["pH_H"]] = 10 ** (-row["pH"]); y0[IDX["T"]] = row["T"]; y0[IDX["Q"]] = 0.001
y0[IDX["vis"]] = row["vis"] if "vis" in row else 4.0
y0[IDX["A0"]] = row["A0"]; y0[IDX["A1"]] = row["A1"]; y0[IDX["A3"]] = row["A3"]; y0[IDX["A4"]] = row["A4"]
y0[IDX["CO2"]] = row["CO2outgas"]; y0[IDX["PAA"]] = row["PAA"]; y0[IDX["NH3"]] = row["NH3"]
y0[IDX["A_t1"]] = row["A_t1"] if "A_t1" in row else 0.0

rowv = v3[v3.time_h <= 200.4].iloc[-1]
inp1 = np.array([2, rowv["Fs"], rowv["Fg"], rowv["RPM"], rowv["Fc"], rowv["Fh"],
                 rowv["Fb"], rowv["Fa"], 0.01, rowv["Fw"], rowv["pressure"], 0.0,
                 rowv["Fremoved"], rowv["Fpaa"], rowv["Foil"], rowv["NH3_shots"],
                 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])

# 冻结除 S 外的所有状态
y_frozen = y0.copy()

def f_s(t, yy):
    y = y_frozen.copy()
    y[IDX["S"]] = yy[0]
    dy = rhs(t, y, inp1, par)
    return np.array([dy[0]])

print(f"start S={y0[IDX['S']]:.6f}")
for rtol, atol, ms in [(1e-3, 1e-6, 0.01), (1e-6, 1e-9, 0.01), (1e-8, 1e-11, 0.001)]:
    sol = solve_ivp(f_s, [200.2, 200.4], [y0[IDX["S"]]], method="BDF",
                    rtol=rtol, atol=atol, max_step=ms)
    print(f"rtol={rtol:.0e} atol={atol:.0e} max_step={ms}: S_end={sol.y[0,-1]:.6f} nsteps={len(sol.t)}")
