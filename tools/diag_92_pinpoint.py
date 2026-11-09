# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, 'candidate/indpensim/v0.1')
import pandas as pd
from simulate import simulate_open_loop, yield_metrics
from diag_b_stage2 import p_offline_rmse
d = pd.read_csv('data/processed/batches/batch_92.csv')
best = {}
for mup in (0.0321, 0.0322, 0.0323):
    params = {'mux': 0.47, 'mup': mup, 'm_s': 0.029, 'dist_tcin_asym': 18, 'alpha_kla': 85.0,
              'PAA_c': 530000.0, 'N_conc_paa': 150000.0, 'c_oil': 1000.0, 'dist_flag': 1}
    sim, v3 = simulate_open_loop(92, params)
    pr, _ = p_offline_rmse(sim, v3)
    ym = yield_metrics(sim, v3)
    e = ym['rel_err_total']
    best[round(mup, 4)] = (round(pr, 2), e, float(sim['CO2d'].max()))
    print(f"mup={mup:.4f}: p_rmse={pr:.2f} yield={e:+.2%} co2d={sim['CO2d'].max():.2f}")
with open('runs/b92_pinpoint.json', 'w', encoding='utf-8') as f:
    import json
    json.dump(best, f, ensure_ascii=False, indent=2)
print('saved runs/b92_pinpoint.json')
