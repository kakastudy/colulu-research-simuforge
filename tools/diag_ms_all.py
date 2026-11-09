# -*- coding: utf-8 -*-
"""Check m_s effect on all golden batches (quick scan)."""
import sys, os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics

GOLDEN = [8, 11, 16, 22, 23, 27, 36, 55, 60, 80, 91, 92]

print(f"{'Batch':>6s} {'m_s':>8s} {'yield_err':>10s} {'CO2d':>6s} {'status':>6s} {'S@156':>8s} {'P@200':>8s}")

for b in GOLDEN:
    d = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
    for m_s in [0.029, 0.005, 0.001]:
        params = {"mux": 0.47, "mup": 0.041, "alpha_kla": 85.0,
                  "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
                  "dist_flag": 1, "dist_tcin_asym": 10, "m_s": m_s}
        sim, _ = simulate_open_loop(b, params)
        ym = yield_metrics(sim, d)
        co2d_max = sim["CO2d"].max()
        crashed = co2d_max > 7.57
        s156 = sim[sim.time_h <= 156.4].iloc[-1]["S"] if len(sim[sim.time_h <= 156.4]) > 0 else 0.0
        p200 = sim[sim.time_h <= 200.4].iloc[-1]["P"] if len(sim[sim.time_h <= 200.4]) > 0 else 0.0
        status = "CRASH" if crashed else "ok"
        print(f"{b:>6d} {m_s:>8.4f} {ym['rel_err_total']:>+10.1%} {co2d_max:>6.2f} {status:>6s} {s156:>8.3f} {p200:>8.1f}")
    print()
