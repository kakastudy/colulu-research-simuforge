# -*- coding: utf-8 -*-
"""Scan improved params for batches 22, 55, 80, 91, 92 with stronger dTcin."""
import sys, os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics

# (batch, mux, mup, m_s, dTcin) combinations to try
SCANTS = [
    (22, 0.41, 0.070, 0.025, 20),
    (22, 0.41, 0.070, 0.025, 25),
    (22, 0.47, 0.070, 0.025, 20),
    (22, 0.47, 0.070, 0.025, 25),
    (55, 0.47, 0.055, 0.025, 20),
    (55, 0.47, 0.055, 0.025, 25),
    (55, 0.47, 0.041, 0.025, 20),
    (55, 0.47, 0.041, 0.025, 25),
    (80, 0.35, 0.041, 0.025, 20),
    (80, 0.35, 0.041, 0.025, 25),
    (80, 0.41, 0.041, 0.025, 20),
    (80, 0.41, 0.041, 0.025, 25),
    (91, 0.41, 0.041, 0.029, 0),
    (91, 0.47, 0.041, 0.029, 0),
    (91, 0.41, 0.041, 0.025, 0),
    (91, 0.47, 0.041, 0.025, 0),
    (92, 0.47, 0.030, 0.020, 20),
    (92, 0.47, 0.030, 0.020, 25),
    (92, 0.47, 0.041, 0.015, 25),
    (92, 0.47, 0.041, 0.015, 30),
]

results = {}
for b, mux, mup, m_s, dtcin in SCANTS:
    d = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
    params = {"mux": mux, "mup": mup, "alpha_kla": 85.0,
              "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
              "dist_flag": 1, "dist_tcin_asym": dtcin, "m_s": m_s}
    sim, _ = simulate_open_loop(b, params)
    ym = yield_metrics(sim, d)
    err = ym["rel_err_total"]
    co2d_max = sim["CO2d"].max()
    crashed = co2d_max > 7.57
    status = "CRASH" if crashed else "ok"
    tag = f"mux={mux:.2f} mup={mup:.3f} m_s={m_s:.4f} dTcin={dtcin:+d}"
    print(f"  B{b}: {tag}: yield={err:+.1%} CO2d={co2d_max:.2f} {status}", flush=True)
    if not crashed:
        if b not in results or abs(err) < abs(results[b]["err"]):
            results[b] = {"err": err, "mux": mux, "mup": mup, "m_s": m_s, "dtcin": dtcin, "co2d": co2d_max}

print(f"\n=== Best improved ===")
for b in sorted(results):
    r = results[b]
    print(f"  Batch {b}: yield={r['err']:+.1%} CO2d={r['co2d']:.2f} (mux={r['mux']:.2f} mup={r['mup']:.3f} m_s={r['m_s']:.4f} dTcin={r['dtcin']:+d})")
