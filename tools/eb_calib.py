# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, 'candidate/indpensim/v0.1')
import hier_est as he
import numpy as np

tl = he.load_theta_log()
print('theta log 批数:', len(tl))
for param, target in (("mup", 0.0025), ("mux", 0.025), ("m_s", 0.004)):
    r = he.eb_temperature(tl, param=param, target_sigma=target)
    print(param, '-> EB:', r)
# 温度定型后的层次拟合（使用 μp 定出的温度，多参数一致性检查）
T = (r or {}).get('T') if False else None
eb_mup = he.eb_temperature(tl, param="mup")
Tstar = eb_mup["T"] if eb_mup else 8
print(f"\n选中温度 T*={Tstar}；在 T* 下的批级 θ 分布：")
for param in ("mux", "mup", "m_s"):
    th = []
    for row in tl:
        sw = [c for c in (row.get("sweep") or []) if c["loss"] < 9e5]
        if len(sw) < 2:
            continue
        arr = np.array([c["loss"] for c in sw])
        w = np.exp(-(arr - arr.min()) / Tstar); w /= w.sum()
        th.append(float(sum(wi * c[param] for wi, c in zip(w, sw))))
    print(f"{param:>4}: mu={np.mean(th):.4f} sigma={np.std(th):.4f} n={len(th)}")
