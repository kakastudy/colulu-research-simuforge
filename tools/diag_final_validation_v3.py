# -*- coding: utf-8 -*-
"""黄金回归守护 v3 —— 证据化崩溃分级（benign/catastrophic）+ 全黄金集复验。

R131 改造：
- 参数表与批列表迁出到 tools/golden_params.py（单一事实源，消除 diag/d6 两份副本漂移）
- 执行改为多进程并行（8 核），单批 ~28 s → 86 批 ~6 min；指标口径逐字不变
- JSON 结构与字段名保持不变，runs/final_validation_v2.json 仍为黄金回归权威证据

用法：
    python tools/diag_final_validation_v3.py            # 并行（默认）
    python tools/diag_final_validation_v3.py --serial   # 串行（对照/调试）
    python tools/diag_final_validation_v3.py --out runs/xxx.json
"""
import sys, os, json, argparse
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))
sys.path.insert(0, HERE)

from golden_params import COMBINED, GOLDEN_NORMAL, FAULT, build_params  # noqa: E402
# R132: build_params 已迁入 candidate/indpensim/v0.1/golden_params.py，作为唯一装配口径。


def run_batch(b):
    from simulate import simulate_open_loop, yield_metrics, classify_crash
    v3 = pd.read_csv(os.path.join(ROOT, "data", "processed", "batches", f"batch_{b:02d}.csv"))
    cp = COMBINED[b]
    params = build_params(cp)
    sim, _ = simulate_open_loop(b, params)
    ym = yield_metrics(sim, v3)
    err = ym["rel_err_total"]
    level, reasons = classify_crash(sim, yield_err=err)
    return {
        "batch": b, "type": "normal" if b in GOLDEN_NORMAL else "fault",
        "yield_sim": ym["total_sim_g"], "yield_v3": ym["total_v3_g"],
        "yield_err": err, "co2d_max": float(sim["CO2d"].max()),
        "ph_end": float(sim["pH"].iloc[-1]), "crash_level": level, "crash_reasons": reasons,
        "params": {k: (v if not isinstance(v, float) or np.isfinite(v) else str(v))
                   for k, v in cp.items()},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--serial", action="store_true", help="串行执行（对照用）")
    ap.add_argument("--out", default=os.path.join(ROOT, "runs", "final_validation_v2.json"))
    ap.add_argument("--procs", type=int, default=0)
    args = ap.parse_args()

    batches = GOLDEN_NORMAL + FAULT
    if args.serial:
        results = [run_batch(b) for b in batches]
    else:
        from multiprocessing import Pool
        n = args.procs or min(8, os.cpu_count() or 1)
        with Pool(n) as pool:
            results = pool.map(run_batch, batches, chunksize=1)

    print("=" * 72)
    print("FINAL Golden Set Validation v3 (PAA per-batch calibration)")
    print("=" * 72)
    print(f"{'Batch':>6s} {'Type':>6s} {'yield_err':>9s} {'CO2d':>6s} {'pH_end':>6s} {'crash':>12s}")
    print("-" * 72)
    all_errs = []
    for r in results:
        err = r["yield_err"]
        print(f"{r['batch']:>6d} {r['type']:>6s} {err:>+9.1%} "
              f"{r['co2d_max']:>6.2f} {r['ph_end']:>6.2f} {r['crash_level']:>12s}")
        all_errs.append(err)

    out_path = args.out
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)

    n = len(results)
    rmse = float(np.sqrt(np.mean(np.square(all_errs))))
    n_cat = sum(1 for r in results if r["crash_level"] == "catastrophic")
    n_ben = sum(1 for r in results if r["crash_level"] == "benign")
    n_norm = sum(1 for r in results if r["crash_level"] == "normal")
    n_within5 = sum(1 for r in results if r["crash_level"] != "catastrophic"
                    and abs(r["yield_err"]) <= 0.05)

    print("-" * 72)
    print(f"Crash: normal={n_norm}/{n} benign={n_ben}/{n} catastrophic={n_cat}/{n}")
    print(f"No catastrophic + |yield err| <= 5%: {n_within5}/{n}")
    print(f"RMSE of yields: {rmse:.2%}")
    print(f"Saved: {os.path.relpath(out_path, ROOT)}")

    summary = {"n_batches": n, "rmse": rmse, "n_normal": n_norm, "n_benign": n_ben,
               "n_catastrophic": n_cat, "n_within5pct": n_within5,
               "worst_abs_err": max(abs(e) for e in all_errs)}
    with open(os.path.join(ROOT, "runs", "r131_golden_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    return summary


if __name__ == "__main__":
    main()
