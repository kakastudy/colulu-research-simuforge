# -*- coding: utf-8 -*-
"""R144 / D-30 Part B：全批扫描 —— 采样末守卫在哪些批、哪个状态上触发。

判据
----
`simulate.guards` 对 states 0-30 做 `y[i] <= 0 -> 0.001`。本工具包裹该函数，
逐批记录触发次数、触发索引、首次触发时刻，并同时给出该批产量误差。

输出
----
  runs/p3/r144_d30_sweep.json

用法
----
  python tools/r144_d30_sweep.py            # 黄金集全部批次
  python tools/r144_d30_sweep.py --limit 8  # 冒烟
"""
import argparse
import json
import os
import sys
import time

import numpy as np

_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(_ROOT, "candidate", "indpensim", "v0.1"))

import simulate as S  # noqa: E402
import golden_params as gp  # noqa: E402

OUT_DIR = os.path.join(_ROOT, "runs", "p3")
NAMES = S.state_names()


def run_batch(b):
    """跑一批，记录守卫触发。返回 dict。"""
    orig = S.guards
    hits = []          # [(t, idx, pre_value)]
    n_calls = [0]

    def wrapped(y):
        n_calls[0] += 1
        pre = np.array(y, dtype=float)
        out = orig(y)
        for i in range(31):
            if pre[i] <= 0:
                hits.append({"t": round(n_calls[0] * 0.2, 1),
                             "idx": i, "name": NAMES[i],
                             "pre": float(pre[i])})
        return out

    S.guards = wrapped
    t0 = time.time()
    try:
        sim, d = S.simulate_open_loop(b, gp.params_for(b))
        ym = S.yield_metrics(sim, d)
        err = float(ym["rel_err_total"])
        ok = True
    except Exception as e:  # noqa: BLE001
        err = None
        ok = False
        sim = None
        d = None
    finally:
        S.guards = orig
    dt = time.time() - t0

    ph_hits = [h for h in hits if h["idx"] == 6]
    other = [h for h in hits if h["idx"] != 6]
    ph_min = float(np.nanmin(sim["pH"].to_numpy(float))) if sim is not None else None
    return {
        "batch": b,
        "ok": ok,
        "sec": round(dt, 1),
        "yield_err": err,
        "ph_min": ph_min,
        "n_hits_total": len(hits),
        "n_hits_ph": len(ph_hits),
        "first_ph_hit_t": ph_hits[0]["t"] if ph_hits else None,
        "deepest_phH": min((h["pre"] for h in ph_hits), default=None),
        "other_idx": sorted({h["name"] for h in other}),
        "other_n": len(other),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--batches", type=str, default="")
    args = ap.parse_args()

    batches = ([int(x) for x in args.batches.split(",") if x.strip()]
               if args.batches else sorted(gp.COMBINED.keys()))
    if args.limit:
        batches = batches[: args.limit]

    rows = []
    for k, b in enumerate(batches, 1):
        r = run_batch(b)
        rows.append(r)
        flag = ""
        if r["n_hits_ph"]:
            flag = f"  ⚠ pH钳位×{r['n_hits_ph']} 首 {r['first_ph_hit_t']}h 最深 {r['deepest_phH']:.2e}"
        print(f"[{k:>2}/{len(batches)}] b{b:<3} yield {r['yield_err']*100 if r['yield_err'] is not None else float('nan'):>+7.2f}%  "
              f"pHmin {r['ph_min'] if r['ph_min'] is not None else float('nan'):>5.2f}  "
              f"钳位 {r['n_hits_total']:>3}{flag}", flush=True)

    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, "r144_d30_sweep.json")
    json.dump({"n": len(rows), "rows": rows}, open(out, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    n_ph = sum(1 for r in rows if r["n_hits_ph"])
    n_any = sum(1 for r in rows if r["n_hits_total"])
    print(f"\n合计 {len(rows)} 批：任何守卫触发 {n_any} 批；pH([H+]) 触发 {n_ph} 批")
    if n_ph:
        bad = [r["batch"] for r in rows if r["n_hits_ph"]]
        print("  pH 触发批次:", bad)
        print("  其中 yield 误差:", {r["batch"]: round(r["yield_err"] * 100, 2)
                                     for r in rows if r["n_hits_ph"]})
    print(f"落盘 {out}")


if __name__ == "__main__":
    main()
