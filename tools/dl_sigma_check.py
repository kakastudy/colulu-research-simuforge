# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, 'candidate/indpensim/v0.1')
import hier_est as he

v1 = he.load_theta_log()
v2 = he._iter_log(he.PROTOCOLS['v2'][1])
print(f'v1: {len(v1)} 批 | v2: {len(v2)} 批')
# DL 估计（以 v2 数据优先，需 ≥6 批；当前混合）
for param in ("mux", "mup", "m_s"):
    r_v2 = he.dl_sigma(v2, param)
    r_v1 = he.dl_sigma(v1, param)
    print(f'{param:>4}: v1-σpop={r_v1["sigma_pop"]} (var_w={r_v1["var_mean"]}, n={r_v1["n"]}) | '
          f'v2-σpop={r_v2["sigma_pop"]} (var_w={r_v2["var_mean"]}, n={r_v2["n"]})')
print('\n参考：MATLAB σ_gen —— μx 0.025 / μp 0.0025 / m_s 无（代理域）')
