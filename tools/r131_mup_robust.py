# -*- coding: utf-8 -*-
"""R131 稳健性扫描：落点是否在悬崖上（μp 平台检测）。

背景：b92 在 mup=0.039565 时产量 +15.5%，0.03957 时 +0.07%——6e-6 的差异造成 15 pt 摆动，
说明命中点是"刀尖"而非"平台"。对控制用途而言，落在刀尖上的标定不可交付。
本脚本对候选落点做邻域扫描，只在"产量全程满足 ±5% 的连续区间"内选取平台点。
"""
import os
import sys
import json
import numpy as np
import pandas as pd
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))

from golden_params import COMBINED          # noqa: E402
from diag_final_validation_v3 import build_params  # noqa: E402

# 扫描规格：--spec "36:lo:hi;60:lo:hi"（lo/hi 为 mup 绝对区间），缺省用 b27/b92 默认区间
DEFAULT_SPEC = "27:0.0344:0.03585;92:0.0392:0.04005"


def build_cases(spec):
    cases = []
    for part in spec.split(";"):
        if not part.strip():
            continue
        b, lo, hi = part.split(":")
        for m in np.arange(float(lo), float(hi) + 1e-9, 0.0001):
            cases.append((int(b), round(float(m), 5)))
    return cases


CASES = None


def run(c):
    from simulate import simulate_open_loop, yield_metrics
    b, mup = c
    p = build_params(COMBINED[b])
    p["mup"] = mup
    sim, _ = simulate_open_loop(b, p)
    v3 = pd.read_csv(os.path.join(ROOT, "data", "processed", "batches", f"batch_{b:02d}.csv"))
    return b, mup, round(100.0 * yield_metrics(sim, v3)["rel_err_total"], 2)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", default=DEFAULT_SPEC)
    ap.add_argument("--out", default="r131_mup_robustness.json")
    _a = ap.parse_args()
    CASES = build_cases(_a.spec)
    with Pool(min(8, os.cpu_count() or 1)) as pool:
        out = pool.map(run, CASES, chunksize=1)
    out.sort(key=lambda x: (x[0], x[1]))

    res = {}
    for b in sorted({c[0] for c in CASES}):
        rows = [(m, y) for bb, m, y in out if bb == b]
        print(f"\n--- batch {b} ---")
        # 找最长连续可行区间的中点（平台中心），要求区间在扫描范围内且不贴边界
        best, cur = None, []
        for m, y in rows:
            print(f"  mup={m:.5f}  yield={y:+7.2f}%{'  OK' if abs(y) <= 5 else ''}")
            if abs(y) <= 5:
                cur.append((m, y))
                if best is None or len(cur) > len(best):
                    best = list(cur)
            else:
                cur = []
        if best:
            ms = [m for m, _ in best]
            ymid = np.median([y for _, y in best])
            print(f"  最长可行区间 [{min(ms):.5f}, {max(ms):.5f}] len={len(best)} "
                  f"→ 平台中心 mup={(min(ms)+max(ms))/2:.5f} (中位 yield {ymid:+.2f}%)")
            res[b] = {"lo": min(ms), "hi": max(ms), "n": len(best),
                      "center": round((min(ms) + max(ms)) / 2, 5), "median_yield": ymid}
        else:
            print("  无可行区间（该批为悬崖型，标定不可交付）")
            res[b] = None
    json.dump({"rows": out, "plateau": res},
              open(os.path.join(ROOT, "runs", "p3", _a.out), "w",
                   encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"\nsaved: runs/p3/{_a.out}")
