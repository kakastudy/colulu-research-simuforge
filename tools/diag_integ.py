# -*- coding: utf-8 -*-
"""测试 [200.2, 200.4] 区间各求解器/容差下 S 的结果。"""
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

print(f"start S={y[0]:.6f} pH={-np.log10(y[6]):.3f}")
configs = [
    ("BDF", dict(rtol=1e-3, atol=1e-6, max_step=0.001)),
    ("BDF", dict(rtol=1e-3, atol=1e-6, max_step=0.0005)),
    ("BDF", dict(rtol=1e-4, atol=1e-7, max_step=0.001)),
    ("BDF", dict(rtol=1e-5, atol=1e-8, max_step=0.001)),
    ("LSODA", dict(rtol=1e-3, atol=1e-6)),
    ("LSODA", dict(rtol=1e-4, atol=1e-7)),
    ("Radau", dict(rtol=1e-3, atol=1e-6)),
    ("Radau", dict(rtol=1e-4, atol=1e-7)),
]
for method, kw in configs:
    sol = solve_ivp(lambda t, yy: rhs(t, yy, inp1, par), [200.2, 200.4], y,
                    method=method, **kw)
    s_end = sol.y[0, -1]
    ph_end = -np.log10(sol.y[6, -1])
    print(f"{method:7s} {kw}: S_end={s_end:.6f} pH_end={ph_end:.3f} nsteps={len(sol.t)}")
