# -*- coding: utf-8 -*-
"""检查 sim t=200.0 状态的 CO2d ODE 导数。"""
import sys
import os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from model import rhs, N_STATES, state_names
from params import make_params

IDX = {name: i for i, name in enumerate(state_names())}

sim = pd.read_csv("runs/sim_mux033.csv")
v3 = pd.read_csv("data/processed/batches/batch_01.csv")

par = make_params(alpha_kla=85.0, N_conc_paa=150000.0, PAA_c=530000.0,
                  mup=0.033, mux=0.33, c_oil=1000.0)

for t_target in [199.0, 200.0, 200.2]:
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

    dy = rhs(t_target, y, inp1, par)
    print(f"t={t_target}: CO2={y[27]:.3f} CO2d={y[28]:.3f} dy28={dy[28]:.2f} S={y[0]:.5f} "
          f"Fg={inp1[2]:.0f} CO2i={0.5*(1+np.tanh(1*(7570-y[28]*1000))):.3f}")
