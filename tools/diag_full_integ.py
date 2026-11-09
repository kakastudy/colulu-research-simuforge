# -*- coding: utf-8 -*-
"""全系统积分 [200.2, 200.4]，密集输出，看哪个状态先动。"""
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

# 密集输出
t_eval = np.linspace(200.2, 200.4, 101)
sol = solve_ivp(lambda t, yy: rhs(t, yy, inp1, par), [200.2, 200.4], y0,
                method="BDF", rtol=1e-6, atol=1e-9, max_step=0.002, t_eval=t_eval)
print(f"S={IDX['S']} DO2={IDX['DO2']} P={IDX['P']} pHH={IDX['pH_H']} T={IDX['T']} A0={IDX['A0']} A1={IDX['A1']} PAA={IDX['PAA']} NH3={IDX['NH3']} CO2={IDX['CO2']} O2={IDX['O2']}")
for i, t in enumerate(sol.t):
    y = sol.y[:, i]
    print(f"  t={t:8.4f} S={y[IDX['S']]:.6f} DO2={y[IDX['DO2']]:.3f} P={y[IDX['P']]:.4f} "
          f"pH={-np.log10(y[IDX['pH_H']]):.4f} T={y[IDX['T']]:.3f} A0={y[IDX['A0']]:.3f} A1={y[IDX['A1']]:.3f} "
          f"PAA={y[IDX['PAA']]:.1f} NH3={y[IDX['NH3']]:.1f} CO2={y[IDX['CO2']]:.5f} O2={y[IDX['O2']]:.4f}")
