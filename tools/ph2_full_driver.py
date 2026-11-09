# -*- coding: utf-8 -*-
"""PH2 全量重投驱动器：v2 池 ≥88 批时自动执行全量结构发现，否则报告进度。

R76 语义修正版：公式层 A_t1（_features 已修）、votes() 三元组返回、
A_t1 appears/neg 聚合与 residual_discovery_mid55.json / ph2_acceptance 同 schema。
"""
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="gbk", errors="replace")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))

import residual_discovery as rd

thetas = rd.load_theta()
# 闸门按 v2 日志实际内容计（R83 修正）：合并并集会把 v1 粗网格批也算入，导致
# 池未满时提前放行（n=88 假象）——正式判读素材应全为 v2 细网格。
v2p = os.path.join(ROOT, "runs", "hier_est", "train_theta_v2.jsonl")
n_v2 = sum(1 for r in map(json.loads, open(v2p, encoding="utf-8"))
           if r.get("theta_post")) if os.path.exists(v2p) else 0
n = len(thetas)
if n_v2 < 88:
    print(f"v2 池 {n_v2}/88 未齐——先等 pwsh-524（断点续跑；合并并集 n={n} 不作为闸门）")
    sys.exit(0)
print(f"v2 池齐 ({n})——执行 PH2 全量结构发现", flush=True)
per_batch, tally, diverged = rd.votes(sorted(thetas), thetas)
print(f"per_batch={len(per_batch)} diverged={len(diverged)}", flush=True)
for ch in ("S", "P"):
    print(f"\n== {ch} 通道 最优稀疏子集票数（{n} 批）==", flush=True)
    for terms, k in sorted(tally[ch].items(), key=lambda kv: -kv[1])[:8]:
        print(f"  {list(terms)} — 票 {k} ({k/n:.0%})", flush=True)

# A_t1 一致性（公式层水平语义见 R76; 投票结果为辅助披露）
ap_n = ap_neg = 0
for b, rr in per_batch.items():
    for ch in ("S", "P"):
        terms = rr[ch]["best"].get("terms", []) or []
        if "A_t1" not in terms:
            continue
        ap_n += 1
        bts = rr[ch]["best"].get("beta") or []
        idx = list(terms).index("A_t1")
        if idx < len(bts) and bts[idx] < 0:
            ap_neg += 1
print(f"A_t1(vote, 辅助): appears={ap_n} neg={ap_neg} ({(ap_neg/ap_n if ap_n else 0):.0%})", flush=True)

out = {
    "n_batches": n,
    "n_effective": len(per_batch),
    "diverged": [str(d) for d in diverged],
    "A_t1": {"appears": ap_n, "neg": ap_neg, "pos": ap_n - ap_neg,
             "note": "辅助披露（导数空间子集投票, 公式层口径）——一致性判据以 death_term.json β 拟合为准"},
    "tally_S": {str(k): v for k, v in tally["S"].items()},
    "tally_P": {str(k): v for k, v in tally["P"].items()},
}
with open(os.path.join(ROOT, "runs", "hier_est", "residual_discovery_full.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print("Saved: runs/hier_est/residual_discovery_full.json")
