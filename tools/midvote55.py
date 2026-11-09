# -*- coding: utf-8 -*-
"""R66 v2 池中途刷新：残差投票 + A_t1 一致性再估（复用 rd.votes；序列化按 merge 模式）。"""
import io
import json
import os
import sys
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="gbk", errors="replace")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))

import residual_discovery as rd

thetas = rd.load_theta()
bs = sorted(thetas)
print(f"载入 {len(bs)} 批（v2 优先合并）", flush=True)
per_batch, tally, diverged = rd.votes(bs, thetas)
print(f"per_batch={len(per_batch)} diverged={len(diverged)}", flush=True)

# A_t1 一致性（语义与 midvote merge 相同: S/P 各批最优子集中 A_t1 的负向占比）
ap_n = ap_neg = 0
for b, rr in per_batch.items():
    for ch in ("S", "P"):
        terms = rr[ch]["best"].get("terms", []) or []
        if "A_t1" not in terms:
            continue
        ap_n += 1
        bts = rr[ch]["best"].get("beta") or []
        if list(terms):
            idx = list(terms).index("A_t1")
            if idx < len(bts) and bts[idx] < 0:
                ap_neg += 1
print(f"A_t1: appears={ap_n} neg={ap_neg} ({(ap_neg/ap_n if ap_n else 0):.0%})", flush=True)

out = {
    "n_batches": len(bs),
    "n_effective": len(per_batch),
    "diverged": [str(d) for d in diverged],
    "A_t1": {"appears": ap_n, "neg": ap_neg, "pos": ap_n - ap_neg},
    "tally_S": {str(k): v for k, v in tally["S"].items()},
    "tally_P": {str(k): v for k, v in tally["P"].items()},
}
apath = os.path.join(ROOT, "runs", "hier_est", "residual_discovery_mid55.json")
with open(apath, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print("Saved:", apath, flush=True)
