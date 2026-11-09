# -*- coding: utf-8 -*-
"""v2 协议 9 批 EB 中期预览：σ̂(T) 是否已可达生成 σ=0.0025（对照 v1 的 0.0019-0.0022 上限）。"""
import sys
sys.path.insert(0, 'candidate/indpensim/v0.1')
import hier_est as he
import numpy as np

v2log = he.PROTOCOLS['v2'][1]
rows = he._iter_log(v2log)
print('v2 已入库:', len(rows), '批')
if len(rows) >= 6:
    for param, target in (('mup', 0.0025), ('mux', 0.025), ('m_s', 0.004)):
        r = he.eb_temperature(rows, param=param, target_sigma=target)
        print(param, '->', r)
