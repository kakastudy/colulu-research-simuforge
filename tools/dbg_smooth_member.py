# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, os.path.abspath('candidate/indpensim/v0.1'))
import numpy as np
from simulate import simulate_open_loop
import hier_est

sweep = [r for r in hier_est.load_theta_log()[0]["sweep"]] if False else None
tl = hier_est.load_theta_log()
th = {r["batch"]: r for r in tl}
sweep = th[11]["sweep"] if 11 in th else th[1]["sweep"]
valid = [r for r in sweep if r["loss"] < 9e5]
rng = np.random.default_rng(11)
cell = valid[0]
th_j = {"mux": float(cell["mux"]) + rng.normal(0, 0.010),
        "mup": float(cell["mup"]) + rng.normal(0, 0.0015),
        "m_s": float(cell["m_s"]) + rng.normal(0, 0.0015)}
params = {"mux": th_j["mux"], "mup": th_j["mup"], "m_s": th_j["m_s"], "alpha_kla": 85.0,
          "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
          "dist_flag": 1, "dist_tcin_asym": 10}
print("params:", {k: round(v, 5) for k, v in params.items()})
try:
    sim, _ = simulate_open_loop(11, params)
    print("OK: rows", len(sim))
except Exception as e:
    import traceback
    traceback.print_exc()
