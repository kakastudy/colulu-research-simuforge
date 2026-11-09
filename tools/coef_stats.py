# -*- coding: utf-8 -*-
"""系数符号跨批统计（PH2 验证：候选缺失项的批间符号一致性）。"""
import json
import numpy as np

with open('runs/hier_est/residual_discovery.json', encoding='utf-8') as f:
    d = json.load(f)

for ch in ("S", "P"):
    m = {}
    for b, rr in d["per_batch"].items():
        terms = rr[ch]["terms"]; beta = rr[ch]["beta"]
        for t, coef in zip(terms, beta):
            key = (t, "S" if ch == "S" else "P")
            m.setdefault(key, []).append(coef)
    print(f"== {ch} 通道候选系数统计 ==")
    for (t, _c), coefs in sorted(m.items(), key=lambda kv: -len(kv[1])):
        a = np.array(coefs)
        print(f"  {t:>10}: n={len(a):2d} median={np.median(a):+.3e} "
              f"min={a.min():+.3e} max={a.max():+.3e}")
