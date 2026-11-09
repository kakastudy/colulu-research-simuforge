# -*- coding: utf-8 -*-
"""R129ah: Non-golden batch validation — run model on all 100 batches with nominal params.

This tests the model's generalization capability. The golden set (12 batches) has
calibrated params. The remaining 88 batches use nominal params from params.py.

Report: yield error distribution, crash rate, RMSE.
"""
import os
import sys
import json
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))

from simulate import simulate_open_loop, yield_metrics, classify_crash


GOLDEN = [8, 11, 16, 22, 23, 27, 36, 55, 60, 80, 91, 92]


def main():
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    print("=" * 80, flush=True)
    print("R129ah: Non-golden batch validation (100 batches, nominal params)", flush=True)
    print("=" * 80, flush=True)

    results = []
    n_total = 0
    n_ok = 0
    n_crash = 0
    n_within5 = 0
    errs = []

    for b in range(1, 101):
        csv_path = os.path.join(base, "data", "processed", "batches", f"batch_{b:02d}.csv")
        if not os.path.exists(csv_path):
            continue

        n_total += 1
        try:
            v3 = pd.read_csv(csv_path)
            # Use nominal params (no calibration)
            params = {}
            sim, _ = simulate_open_loop(b, params)
            ym = yield_metrics(sim, v3)
            level, reasons = classify_crash(sim, yield_err=ym["rel_err_total"])

            err = ym["rel_err_total"]
            errs.append(err)
            is_golden = "GOLDEN" if b in GOLDEN else "non-golden"

            if level == "catastrophic":
                n_crash += 1
            elif level == "normal":
                n_ok += 1
                if abs(err) <= 0.05:
                    n_within5 += 1

            results.append({
                "batch": b, "type": is_golden, "yield_err": err,
                "crash": level, "p_final": float(sim["P"].iloc[-1]) if "P" in sim else 0,
                "x_final": float(sim["X"].iloc[-1]) if "X" in sim else 0,
            })

            if n_total % 20 == 0:
                print("  ... processed {} batches ({} ok, {} crash, {} within5%)".format(
                    n_total, n_ok, n_crash, n_within5), flush=True)
        except Exception as e:
            results.append({"batch": b, "type": "error", "yield_err": None,
                            "crash": "error", "error": str(e)[:100]})

    # Summary
    print("\n" + "=" * 80, flush=True)
    print("SUMMARY", flush=True)
    print("=" * 80, flush=True)
    print("  Total batches: {}".format(n_total), flush=True)
    print("  Normal: {}".format(n_ok), flush=True)
    print("  Catastrophic: {}".format(n_crash), flush=True)
    print("  Within 5%: {}".format(n_within5), flush=True)
    if errs:
        errs_arr = np.array(errs)
        print("  RMSE: {:.2%}".format(np.sqrt(np.mean(errs_arr**2))), flush=True)
        print("  Mean err: {:+.2%}".format(np.mean(errs_arr)), flush=True)
        print("  Median err: {:+.2%}".format(np.median(errs_arr)), flush=True)
        print("  Min err: {:+.2%}".format(np.min(errs_arr)), flush=True)
        print("  Max err: {:+.2%}".format(np.max(errs_arr)), flush=True)

    # Golden vs non-golden breakdown
    golden_errs = [r["yield_err"] for r in results if r.get("type") == "GOLDEN" and r.get("yield_err") is not None]
    non_golden_errs = [r["yield_err"] for r in results if r.get("type") == "non-golden" and r.get("yield_err") is not None]
    if golden_errs:
        print("\n  Golden set ({} batches): RMSE={:.2%} mean={:+.2%}".format(
            len(golden_errs), np.sqrt(np.mean(np.array(golden_errs)**2)), np.mean(golden_errs)), flush=True)
    if non_golden_errs:
        print("  Non-golden ({} batches): RMSE={:.2%} mean={:+.2%}".format(
            len(non_golden_errs), np.sqrt(np.mean(np.array(non_golden_errs)**2)), np.mean(non_golden_errs)), flush=True)

    # Print worst 20
    print("\n--- Worst 20 batches ---", flush=True)
    sorted_results = sorted([r for r in results if r.get("yield_err") is not None],
                            key=lambda x: abs(x["yield_err"]), reverse=True)
    for r in sorted_results[:20]:
        print("  Batch {} ({}): yield_err={:+.2%} crash={}".format(
            r["batch"], r["type"], r["yield_err"], r["crash"]), flush=True)

    # Print best 20
    print("\n--- Best 20 batches ---", flush=True)
    sorted_results = sorted([r for r in results if r.get("yield_err") is not None],
                            key=lambda x: abs(x["yield_err"]))
    for r in sorted_results[:20]:
        print("  Batch {} ({}): yield_err={:+.2%} crash={}".format(
            r["batch"], r["type"], r["yield_err"], r["crash"]), flush=True)

    # Save
    dst = os.path.join(base, "runs", "p3", "d9_nongolden_validation.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("\nSaved: %s" % dst, flush=True)


if __name__ == "__main__":
    main()
