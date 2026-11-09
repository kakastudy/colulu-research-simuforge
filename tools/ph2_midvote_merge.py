# -*- coding: utf-8 -*-
"""PH2 中期重投（合并 v1+26 v2 = ~62 批）：跨批 A_t1 一致性大样本测试。"""
import sys, os, json
sys.path.insert(0, 'candidate/indpensim/v0.1')
import numpy as np
import residual_discovery as rd

thetas = rd.load_theta()
bs = sorted(thetas)
print(f"合并批数: {len(bs)}（v1 60 + v2 新增 {len(bs) - 60} +重叠）", flush=True)

per_batch, tally, diverged = rd.votes(bs, thetas)

# A_t1 跨批一致性统计（方向 + 显著性）
ut1 = {"appears": 0, "neg": 0, "pos": 0}
for b, rr in per_batch.items():
    for ch in ("S", "P"):
        terms = rr[ch]["best"]["terms"]
        if "A_t1" in terms:
            ut1["appears"] += 1
            beta = rr[ch]["best"]["beta"][terms.index("A_t1")]
            ut1["neg" if beta < 0 else "pos"] += 1
rate = ut1["neg"] / max(ut1["appears"], 1)
print(f"\nA_t1 一致性: 出现 {ut1['appears']}/{len(bs) * 2} 站点；负系数 {ut1['neg']}（{rate:.0%}）", flush=True)

out = {"n_batches": len(bs),
       "tally_S": {str(k): v for k, v in tally["S"].items()},
       "tally_P": {str(k): v for k, v in tally["P"].items()},
       "A_t1": ut1}
dst = 'runs/hier_est/residual_discovery_mid.json'
with open(dst, 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print(f"Saved: {dst}")
