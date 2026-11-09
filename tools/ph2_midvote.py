# -*- coding: utf-8 -*-
"""PH2 中期重投：对 v1 协议已入库的 59 批做全量结构发现（vote + BIC）。"""
import sys
sys.path.insert(0, 'candidate/indpensim/v0.1')
import residual_discovery as rd

thetas = rd.load_theta()
bs = sorted(thetas)
print(f"对 {len(bs)} 个 v1 已入库批做全量结构发现：", flush=True)
per_batch, tally, diverged = rd.votes(bs, thetas)
for ch in ("S", "P"):
    print(f"\n== {ch} 通道 最优稀疏子集票数（{len(bs)} 批）==")
    for terms, k in sorted(tally[ch].items(), key=lambda kv: -kv[1])[:6]:
        print(f"  {list(terms)} — 票 {k} ({k/len(bs):.0%})")
