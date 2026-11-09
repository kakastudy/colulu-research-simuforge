# -*- coding: utf-8 -*-
import sys, os
import pandas as pd
sys.path.insert(0, 'candidate/indpensim/v0.1')
from simulate import simulate_open_loop, yield_metrics
d = pd.read_csv('data/processed/batches/batch_36.csv')
for m_s in [0.017, 0.016, 0.014]:
    for dtcin in [10, 12]:
        params = {'mux': 0.41, 'mup': 0.041, 'alpha_kla': 85.0, 'PAA_c': 530000.0, 'N_conc_paa': 150000.0, 'c_oil': 1000.0, 'dist_flag': 1, 'dist_tcin_asym': dtcin, 'm_s': m_s}
        sim, _ = simulate_open_loop(36, params)
        ym = yield_metrics(sim, d)
        co2d = sim['CO2d'].max()
        status = 'CRASH' if co2d > 7.57 else 'ok'
        print(f"m_s={m_s:.4f} dTcin={dtcin:+d}: yield={ym['rel_err_total']:+.1%} CO2d={co2d:.2f} {status}")
