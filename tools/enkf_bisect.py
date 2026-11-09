# -*- coding: utf-8 -*-
"""二分诊断批跑：3 配置（全开/只在线/只化验）→ 对比 X 轨迹健康度。"""
import sys
sys.path.insert(0, 'candidate/indpensim/v0.1')
import observe as ob
import numpy as np

cfgs = [
    ("both", dict(assim_online=True, assim_assay=True)),
    ("online_only", dict(assim_online=True, assim_assay=False)),
    ("assay_only", dict(assim_online=False, assim_assay=True)),
    ("none", dict(assim_online=False, assim_assay=False)),
]
out = {}
for name, kw in cfgs:
    r = ob.enkf_observe(11, n_ens=20, verbose=False, out_path=None, **kw)
    recs = r["records"]
    xs = [(round(x["time_h"]), round(x["X_sum"], 2), round(x["P_mean"], 3)) for x in recs
          if x["time_h"] in (40.2, 80.2, 120.2, 160.2, 200.2, 240.2)]
    out[name] = {"fail": r.get("integration_failures"), "marks": xs}
    print(f"[{name}] fail={r.get('integration_failures')} :: " +
          " | ".join(f"t{t}: X={x} P={p}" for t, x, p in xs), flush=True)
import json
with open('runs/hier_est/enkf_bisect.json', 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print('saved diagnostic')
