# -*- coding: utf-8 -*-
"""v2 26 批 EB 重校验证：细网格是否让 σ̂ 达到生成分散度 0.0025（PH1-e 预验证）。"""
import sys
sys.path.insert(0, 'candidate/indpensim/v0.1')
import hier_est as he
import numpy as np

rows = he._iter_log(he.PROTOCOLS['v2'][1])
print('v2 协议入库:', len(rows), '批')
if len(rows) >= 20:
    for param, target in (('mup', 0.0025), ('mux', 0.025), ('m_s', 0.004)):
        r = he.eb_temperature(rows, param=param, target_sigma=target)
        print(param, '->', r)
    T = (he.eb_temperature(rows, param='mup', target_sigma=target) or {}).get('T', 8)
    print(f'\nT*={T} 下批级 θ 分布:')
    for p in ('mux', 'mup', 'm_s'):
        th = []
        for row in rows:
            sw = [c for c in (row.get("sweep") or []) if c["loss"] < 9e5]
            if len(sw) < 2:
                continue
            arr = np.array([c["loss"] for c in sw])
            w = np.exp(-(arr - arr.min()) / T); w /= w.sum()
            th.append(float(sum(wi * c[p] for wi, c in zip(w, sw))))
        print(f"{p:>4}: mu={np.mean(th):.4f} sigma={np.std(th):.4f} n={len(th)}")
