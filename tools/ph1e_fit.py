# -*- coding: utf-8 -*-
"""PH1-e：v2 协议完池后的层次先验完整拟合 + EB/DL 双路验收 → runs/hier_est/hier_prior_v2.json。

验收基准（MATLAB 生成机制）：
  μx: μ̂≈0.41±0.025 ｜ μp: μ̂≈0.041±0.0025 ｜ alpha_kla: 85±10
"""
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
import hier_est as he
import numpy as np

v2log = he.PROTOCOLS["v2"][1]
rows = he._iter_log(v2log)
print(f"v2 池入库 {len(rows)}/88 批", flush=True)
if len(rows) < 88:
    print("池未齐——先等 pwsh-524", flush=True)
    sys.exit(0)

# EB 温度重校（细网格下应有跨批 σ 可解析）
targets = {"mux": 0.025, "mup": 0.0025}
eb = {}
for param, tgt in targets.items():
    r = he.eb_temperature(rows, param=param, target_sigma=tgt)
    eb[param] = r
    print(f"EB {param}: {r}", flush=True)
T_star = (eb.get("mup") or {}).get("T", 1)

# 在 T* 下的批级 θ 分布（层次先验）
th_post = {p: [] for p in ("mux", "mup", "m_s")}
for r in rows:
    sw = [c for c in (r.get("sweep") or []) if c["loss"] < 9e5]
    if len(sw) < 2:
        continue
    arr = np.array([c["loss"] for c in sw])
    w = np.exp(-(arr - arr.min()) / T_star)
    w /= w.sum()
    for p in th_post:
        th_post[p].append(float(sum(wi * c[p] for wi, c in zip(w, sw))))
fit = {}
for p, vals in th_post.items():
    fit[p] = {"mu_hat": round(float(np.mean(vals)), 4),
              "sigma_hat": round(float(np.std(vals)), 4), "n": len(vals)}

# DL 双查（细网格后验波兰）
dl = {}
for p in ("mux", "mup", "m_s"):
    dl[p] = he.dl_sigma(rows, p)
print("层次先验拟合:", json.dumps(fit, ensure_ascii=False), flush=True)
print("DL:", json.dumps(dl, ensure_ascii=False), flush=True)

out = {"version": "v2-protocol", "n_batches": len(rows), "T_star": T_star,
       "eb": eb, "hier_fit": fit, "dl": dl,
       "matlab_ref": {"mux": (0.41, 0.025), "mup": (0.041, 0.0025),
                      "alpha_kla": (85, 10), "note": "per-batch randn 生成机制"}}
dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "runs", "hier_est", "hier_prior_v2.json")
with open(dst, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print("Saved:", dst, flush=True)
