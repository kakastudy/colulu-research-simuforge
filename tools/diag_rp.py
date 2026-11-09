# -*- coding: utf-8 -*-
"""在 t=200.2/200.4 重构 sim 状态，计算 r_p / dP_dt 各分量。"""
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

for target_t in [200.0, 200.2, 200.4, 200.6, 201.0, 202.0]:
    row = sim[sim.time_h <= target_t].iloc[-1]
    y = np.zeros(N_STATES)
    y[IDX["S"]] = row["S"]; y[IDX["DO2"]] = row["DO2"]; y[IDX["O2"]] = row["O2"]
    y[IDX["P"]] = row["P"]; y[IDX["V"]] = row["V"]; y[IDX["Wt"]] = row["Wt"]
    y[IDX["pH_H"]] = 10 ** (-row["pH"]); y[IDX["T"]] = row["T"]; y[IDX["Q"]] = 0.001
    y[IDX["vis"]] = row["vis"] if "vis" in row else 4.0
    y[IDX["A0"]] = row["A0"]; y[IDX["A1"]] = row["A1"]; y[IDX["A3"]] = row["A3"]; y[IDX["A4"]] = row["A4"]
    y[IDX["CO2"]] = row["CO2outgas"]; y[IDX["PAA"]] = row["PAA"]; y[IDX["NH3"]] = row["NH3"]
    y[IDX["A_t1"]] = row["A_t1"] if "A_t1" in row else 0.0

    rowv = v3[v3.time_h <= target_t + 0.2].iloc[-1]  # 区间 [target_t, target_t+0.2] 的 MV
    inp1 = np.array([2, rowv["Fs"], rowv["Fg"], rowv["RPM"], rowv["Fc"], rowv["Fh"],
                     rowv["Fb"], rowv["Fa"], 0.01, rowv["Fw"], rowv["pressure"], 0.0,
                     rowv["Fremoved"], rowv["Fpaa"], rowv["Foil"], rowv["NH3_shots"],
                     0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
    dy = rhs(target_t, y, inp1, par)
    dP_dt = dy[3]
    V = y[4]
    Fs, Fb, Fa, Fw, Fpaa = inp1[1], inp1[6], inp1[7], inp1[9], inp1[13]
    F_evp = 0.0
    dilution = Fs + Fb + Fa + Fw - F_evp + Fpaa
    r_p = dP_dt + y[3] * dilution / V
    print(f"t={target_t}: simP={row['P']:.3f} dy3={dP_dt:+.4f} dilution={dilution:.1f} "
          f"P*dil/V={y[3]*dilution/V:.4f} r_p={r_p:+.4f}  Fs={Fs:.1f} Fb={Fb:.1f} Fpaa={Fpaa:.1f} "
          f"simDO2={row['DO2']:.2f} simPAA={row['PAA']:.0f} simpH={row['pH']:.3f}")
