# -*- coding: utf-8 -*-
"""R133 收口一次性全量扫描 —— 一次仿真，三份产物。

为什么要合并
------------
本轮改动（黏度上报口径 vis_out_scale）原则上不影响产量路径，但"原则上"不算证据。
黄金回归、D6 健康视图、平台轨迹缓存各自都要跑 86 次仿真；本机单批 ~35 s，
分三次跑要 1.5 h。合并为一次扫描，**同一 sim 对象**同时喂给三处，既省时也消除了
"三次跑的不是同一个东西"的风险。

产物
----
- runs/r133_golden.json          产量回归（schema 同 final_validation_v2.json）
- runs/p3/d6_r133.json           通道健康（schema 同 d6_health_view.json）
- platform/.cache/bXX.json       平台轨迹（下采样 2h）
- runs/p3/r133_final_pass.json   汇总（含与 R131 冻结副本的逐批 diff）

用法：python tools/r133_final_pass.py [--workers 8] [--no-series]
"""
import argparse
import json
import os
import sys
import time

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PKG = os.path.join(ROOT, "candidate", "indpensim", "v0.1")
sys.path.insert(0, PKG)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from golden_params import COMBINED, GOLDEN_NORMAL, FAULT, GOLDEN_ALL, build_params  # noqa: E402
from d6_health_view import CHANNEL_MAP, OFFLINE_CHANNELS, OFFLINE_DELAY_H, \
    compute_channel_metrics  # noqa: E402

SERIES_CH = [
    ("S", "S", "S", False), ("P", "P", "P", False),
    ("X", "X", "X_offline", True), ("PAA", "PAA", "PAA_offline", True),
    ("DO2", "DO2", "DO2", False), ("OUR", "OUR", "OUR", False),
    ("vis", "vis", "Viscosity_offline", True), ("CER", "CER", "CER", False),
]
STEP_H = 2.0


def eval_batch(job):
    b, want_series = job
    from simulate import simulate_open_loop, yield_metrics, classify_crash

    v3 = pd.read_csv(os.path.join(ROOT, "data", "processed", "batches", f"batch_{b:02d}.csv"))
    cp = COMBINED[b]
    sim, _ = simulate_open_loop(b, build_params(cp))

    ym = yield_metrics(sim, v3)
    err = float(ym["rel_err_total"])
    level, reasons = classify_crash(sim, yield_err=err)
    golden = {
        "batch": b, "type": "normal" if b in GOLDEN_NORMAL else "fault",
        "yield_sim": ym["total_sim_g"], "yield_v3": ym["total_v3_g"],
        "yield_err": err, "co2d_max": float(sim["CO2d"].max()),
        "ph_end": float(sim["pH"].iloc[-1]), "crash_level": level, "crash_reasons": reasons,
        "params": {k: (v if not isinstance(v, float) or np.isfinite(v) else str(v))
                   for k, v in cp.items()},
    }

    chans, pairs, crit, nsum, ncnt = {}, [], 0, 0.0, 0
    for name, (scol, vcol) in CHANNEL_MAP.items():
        if scol not in sim.columns or vcol not in v3.columns:
            continue
        m = compute_channel_metrics(sim, v3, scol, vcol, lag_h=0.0)
        chans[name] = m
        if m["health"] in ("healthy", "warning", "critical"):
            nsum += m["nrmse"]; ncnt += 1
            if m["health"] == "critical":
                crit += 1
            pairs.append(m["health"])
    avg = nsum / ncnt if ncnt else 0.0
    bh = "healthy" if (avg < 8 and crit == 0) else ("critical" if (avg > 15 or crit > 2) else "warning")
    d6 = {"batch_health": bh, "avg_nrmse": round(avg, 2), "critical_count": crit, "channels": chans}

    series = None
    if want_series:
        ts = sim["time_h"].to_numpy(float)
        grid = np.arange(ts[0], ts[-1] + 1e-9, STEP_H)
        series = {"t": [round(float(x), 2) for x in grid], "sim": {}, "obs": {}, "off": {}}
        tv = v3["time_h"].to_numpy(float)
        for key, scol, ocol, offline in SERIES_CH:
            if scol not in sim.columns:
                continue
            series["sim"][key] = [round(float(x), 4) for x in
                                  np.interp(grid, ts, sim[scol].to_numpy(float))]
            if ocol not in v3.columns:
                continue
            ov = v3[ocol].to_numpy(float)
            m = np.isfinite(ov)
            if offline:
                series["off"][key] = [[round(float(tv[i]), 1), round(float(ov[i]), 4)]
                                      for i in np.where(m)[0]]
            else:
                series["obs"][key] = [round(float(x), 4) for x in np.interp(grid, tv, ov)]

    return b, golden, d6, pairs, series


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--no-series", action="store_true")
    args = ap.parse_args()

    t0 = time.time()
    want = not args.no_series
    jobs = [(b, want) for b in GOLDEN_ALL]
    if args.workers > 1:
        import multiprocessing as mp
        with mp.Pool(args.workers) as pool:
            out = pool.map(eval_batch, jobs, chunksize=1)
    else:
        out = [eval_batch(j) for j in jobs]

    golden_rows, d6_batches, all_pairs = [], {}, []
    cache = os.path.join(ROOT, "platform", ".cache")
    if want:
        os.makedirs(cache, exist_ok=True)
    for b, g, d, pairs, series in out:
        golden_rows.append(g)
        d6_batches[str(b)] = d
        all_pairs.extend(pairs)
        if series:
            with open(os.path.join(cache, f"b{b:02d}.json"), "w", encoding="utf-8") as f:
                json.dump(series, f, separators=(",", ":"))
    golden_rows.sort(key=lambda r: r["batch"])

    os.makedirs(os.path.join(ROOT, "runs", "p3"), exist_ok=True)
    with open(os.path.join(ROOT, "runs", "r133_golden.json"), "w", encoding="utf-8") as f:
        json.dump({"results": golden_rows}, f, ensure_ascii=False, indent=1)

    hp = sum(1 for h in all_pairs if h == "healthy")
    tp = len(all_pairs)
    with open(os.path.join(ROOT, "runs", "p3", "d6_r133.json"), "w", encoding="utf-8") as f:
        json.dump({"offline_delay_h": 0.0, "overall_verdict": "healthy" if hp / tp > .8
                   else ("warning" if hp / tp >= .5 else "critical"),
                   "healthy_pairs": hp, "total_pairs": tp,
                   "healthy_pct": round(100.0 * hp / tp, 1),
                   "batches": d6_batches}, f, ensure_ascii=False, indent=1)

    # ---- 与 R131 冻结副本逐批 diff ----
    frozen_p = os.path.join(ROOT, "runs", "final_validation_v2_R131_FROZEN.json")
    diffs = {}
    if os.path.exists(frozen_p):
        fr = json.load(open(frozen_p, encoding="utf-8"))
        frows = fr["results"] if isinstance(fr, dict) and "results" in fr else fr
        fm = {int(r["batch"]): r for r in frows}
        for r in golden_rows:
            o = fm.get(r["batch"])
            diffs[r["batch"]] = None if o is None else abs(r["yield_err"] - o["yield_err"])

    errs = np.array([r["yield_err"] for r in golden_rows])
    rmse = float(np.sqrt(np.mean(errs ** 2)) * 100)
    within = int(np.sum(np.abs(errs) <= 0.05))
    cat = sum(1 for r in golden_rows if r["crash_level"] == "catastrophic")
    maxdiff = max((v for v in diffs.values() if v is not None), default=None)
    nonzero = [b for b, v in diffs.items() if v is not None and v > 0]

    summary = {
        "n": len(golden_rows), "rmse_pct": round(rmse, 3),
        "within5": within, "catastrophic": cat,
        "healthy_pairs": hp, "total_pairs": tp,
        "healthy_pct": round(100.0 * hp / tp, 1),
        "yield_diff_max_vs_R131": maxdiff,
        "batches_with_any_diff": nonzero,
        "elapsed_s": round(time.time() - t0, 1),
    }
    with open(os.path.join(ROOT, "runs", "p3", "r133_final_pass.json"), "w", encoding="utf-8") as f:
        json.dump({"summary": summary,
                   "diff_vs_R131": {str(k): v for k, v in sorted(diffs.items())}},
                  f, ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
