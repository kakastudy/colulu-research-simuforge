# -*- coding: utf-8 -*-
"""R156 / D-55 第二问：pH 修好之后，那 5 批还能不能重新标定回 ±5%？

背景
----
`ph_fix=1` 修好了 basic 分支，5 批钳位批的 pH 从「崩到 3.00」回到「6.6–7.0」，
但产量从 −2.3%~+3.5% 跳到 **+21%~+69%**。这不是回归，是 R147/D-36 预告过的：
那 5 批的 `mup` 是在「pH 会崩、后期不产素」的世界里标出来的。pH 修好后必须重标。

要回答的两件事
--------------
1. **可控性**：在 ph_fix=1 下，`yield` 对 `mup` 是否单调？R154 在钳位世界里测到
   弹性跨批差 3 个量级（b3 +0.3 / b59 +411 pp per unit mup），那是双稳态造成的。
   若 pH 修好后变成单调、跨批同量级 ⇒ **D-52 的「±1% 上界」是 D-55 的下游症状**。
2. **可标定性**：需要多大的 mup 倍率才能把产量拉回 0？若所需倍率落在 0.3–1.0 的
   常规区间且逐批一致 ⇒ 重标可行。

做法
----
对每批：base（ph_fix=1, mup 原值）+ 若干 mup 倍率，记录 yield_err / P 峰值 / pH_max / 钳位。
再用线性插值给出「把 yield 打到 0 所需的倍率」。

用法
----
    python tools/r156_recal.py --batches 37,50,51,91,92 --mults 0.4,0.5,0.6,0.7,0.8,0.9,1.0 --workers 7
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
ENG = os.path.join(ROOT, "candidate", "indpensim", "v0.1")
sys.path.insert(0, ENG)


def one(job):
    batch, mults, ph_fix = job
    try:
        import simulate as s
        from golden_params import COMBINED, build_params

        bp = dict(build_params(COMBINED[batch]))
        bp["ph_fix"] = int(ph_fix)
        mup0 = float(bp.get("mup", 0.041))
        rows = []
        for m in [1.0] + list(mults):
            p1 = dict(bp)
            p1["mup"] = mup0 * float(m)
            sim, v3 = s.simulate_open_loop(int(batch), p1)
            ym = s.yield_metrics(sim, v3)
            au = sim.attrs.get("guard_audit", {})
            rows.append({
                "mult": float(m), "mup": float(p1["mup"]),
                "yield_err": float(ym["rel_err_total"]),
                "p_peak": float(np.nanmax(sim["P"].to_numpy(float))),
                "p_end": float(sim["P"].iloc[-1]),
                "ph_max": float(np.nanmax(sim["pH_pre"].to_numpy(float)))
                if sim["pH_pre"].notna().any() else float("nan"),
                "n_clamp": int(au.get("tally", {}).get("pH_H", 0)),
            })
        # 线性插值求 yield=0 的倍率（只在跨越 0 的相邻点之间）
        need = float("nan")
        rows_s = sorted(rows, key=lambda r: r["mult"])
        for a, b in zip(rows_s, rows_s[1:]):
            if a["yield_err"] == 0.0:
                need = a["mult"]
                break
            if a["yield_err"] * b["yield_err"] < 0:
                w = abs(a["yield_err"]) / (abs(a["yield_err"]) + abs(b["yield_err"]))
                need = a["mult"] + w * (b["mult"] - a["mult"])
                break
        return {"batch": int(batch), "mup0": mup0, "rows": rows, "need_mult": need,
                "ph_fix": int(ph_fix)}
    except Exception as e:  # noqa: BLE001
        import traceback
        return {"batch": int(batch), "error": f"{type(e).__name__}: {e}",
                "tb": traceback.format_exc()[-600:]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", default="37,50,51,91,92")
    ap.add_argument("--mults", default="0.4,0.5,0.6,0.7,0.8,0.9,1.0")
    ap.add_argument("--ph-fix", type=int, default=1, choices=[0, 1])
    ap.add_argument("--workers", type=int, default=7)
    ap.add_argument("--json", default="runs/r156_recal.json")
    args = ap.parse_args()

    batches = [int(x) for x in args.batches.split(",") if x.strip()]
    mults = [float(x) for x in args.mults.split(",") if x.strip()]
    jobs = [(b, mults, args.ph_fix) for b in batches]

    out = []
    if args.workers > 1:
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            for r in ex.map(one, jobs):
                out.append(r)
                print("done", r.get("batch"), r.get("error", ""), flush=True)
    else:
        for j in jobs:
            r = one(j)
            out.append(r)
            print("done", r.get("batch"), r.get("error", ""), flush=True)

    ok = [r for r in out if "error" not in r]
    print(f"\n=== mup 重标（ph_fix={args.ph_fix}，{len(ok)} 批）===")
    for r in ok:
        print(f"\n-- batch {r['batch']}  mup0={r['mup0']:.5f}  需倍率={r['need_mult']:.3f} --")
        print(f"  {'mult':>6} {'mup':>9} {'yield%':>9} {'P峰':>8} {'P末':>8} {'pH_max':>8} {'钳位':>5}")
        for a in sorted(r["rows"], key=lambda x: x["mult"]):
            print(f"  {a['mult']:6.2f} {a['mup']:9.5f} {a['yield_err']*100:+9.2f} "
                  f"{a['p_peak']:8.3f} {a['p_end']:8.3f} {a['ph_max']:8.3f} {a['n_clamp']:5d}")

    if ok:
        print("\n=== 弹性（pp per unit mult，用 0.8→1.0 段）===")
        for r in ok:
            d = {round(a["mult"], 3): a["yield_err"] for a in r["rows"]}
            if 0.8 in d and 1.0 in d:
                print(f"  b{r['batch']:<4} {(d[1.0]-d[0.8])/0.2*100:+8.1f} pp/mult"
                      f"   需倍率 {r['need_mult']:.3f}")
        needs = [r["need_mult"] for r in ok if np.isfinite(r["need_mult"])]
        if needs:
            print(f"  需倍率：中位 {np.median(needs):.3f}  范围 [{min(needs):.3f}, {max(needs):.3f}]")

    os.makedirs(os.path.dirname(os.path.join(ROOT, args.json)), exist_ok=True)
    with open(os.path.join(ROOT, args.json), "w", encoding="utf-8") as f:
        json.dump({"mults": mults, "ph_fix": args.ph_fix, "rows": out}, f, indent=1)
    print("\n->", args.json)


if __name__ == "__main__":
    main()
