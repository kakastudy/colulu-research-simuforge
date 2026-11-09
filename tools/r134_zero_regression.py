# -*- coding: utf-8 -*-
"""R134 零回归闸门 —— 全 86 批产量与冻结基准逐批比对。

用途：任何触碰 `simulate.py` / `model.py` / `golden_params.py` 的改动，跑一遍本闸门，
      确认没有把产量路径改坏。判据是**逐批差值**，不是"RMSE 差不多"——
后者会把单个批次的漂移平均掉。

用法：
    python tools/r134_zero_regression.py                 # 对 runs/final_validation_v2.json
    python tools/r134_zero_regression.py --ref runs/r133_golden.json
    python tools/r134_zero_regression.py --tol 0 0        # 要求逐位一致（默认）

退出码：0 全部通过；1 有批次超差（可用于 CI/钩子）。
"""
import argparse
import json
import os
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))


def one(batch):
    """单批：返回 (批号, 官方产量, 相对误差)。走 build_params 以免漏装配。"""
    from golden_params import COMBINED, build_params
    from simulate import simulate_open_loop, yield_metrics

    sim, v3 = simulate_open_loop(batch, build_params(COMBINED[batch]))
    ym = yield_metrics(sim, v3)
    return int(batch), float(ym["total_sim_g"]), float(ym["rel_err_total"]) * 100.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default=os.path.join(ROOT, "runs", "final_validation_v2.json"))
    ap.add_argument("--tol", type=float, default=0.0,
                    help="允许的最大逐批相对偏差（%%），默认 0 = 逐位一致")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", default=os.path.join(ROOT, "runs", "p3", "r134_zero_regression.json"))
    args = ap.parse_args()

    ref = {r["batch"]: r for r in json.load(open(args.ref, encoding="utf-8"))["results"]}
    batches = sorted(ref)

    print("=" * 84)
    print(f"R134 零回归闸门：{len(batches)} 批，基准 {os.path.relpath(args.ref, ROOT)}")
    print(f"判据：逐批 |Δyield| / yield ≤ {args.tol:g}%")
    print("=" * 84, flush=True)

    t0 = time.time()
    from multiprocessing import Pool
    with Pool(min(args.workers, os.cpu_count() or 1)) as pool:
        rows = pool.map(one, batches, chunksize=1)

    bad = []
    deltas = []
    for b, y, err in rows:
        r = ref[b]
        d = (y - r["yield_sim"]) / r["yield_sim"] * 100.0
        deltas.append(abs(d))
        if abs(d) > args.tol + 1e-12:
            bad.append({"batch": b, "now_g": y, "ref_g": r["yield_sim"],
                        "delta_pct": round(d, 8), "yield_err_now_pct": round(err, 4)})

    n = len(rows)
    within5 = sum(1 for _, _, e in rows if abs(e) <= 5.0)
    rms = (sum(e * e for _, _, e in rows) / n) ** 0.5
    print(f"\n产量回归：RMSE {rms:.3f}%（红线 3.5%） | within ±5%: {within5}/{n} | "
          f"max |Δ| {max(deltas):.2e}%")
    if bad:
        print(f"\n❌ {len(bad)} 批超差：")
        for x in bad[:20]:
            print(f"   b{x['batch']:>3d}  now={x['now_g']:>14,.1f}  ref={x['ref_g']:>14,.1f}  "
                  f"Δ={x['delta_pct']:+.6f}%")
    else:
        print(f"\n✅ 全 {n} 批逐批一致（容差 {args.tol:g}%）")

    out = {"meta": {"ref": os.path.relpath(args.ref, ROOT), "tol_pct": args.tol,
                    "n": n, "elapsed_s": round(time.time() - t0, 1),
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%S")},
           "summary": {"rmse_pct": round(rms, 4), "within5": within5, "n": n,
                       "max_abs_delta_pct": max(deltas), "n_out_of_tol": len(bad),
                       "pass": len(bad) == 0},
           "out_of_tol": bad}
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"Saved: {args.out}  ({time.time()-t0:.0f}s)")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
