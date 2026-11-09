# -*- coding: utf-8 -*-
"""R153 / D-48：生长耦合产素替代系数 λ 的批级扫描与判据。

口径完全沿用 `r151_shape_accept.py`（同一套 `shape_metrics` / `yield_metrics` /
`validity` / `classify_crash`），以便与 `runs/r151_shape_baseline.json` 直接逐批比对。

引擎侧
------
`model.py` 的 `_rp_gate = (1-λ)·P_inhib + λ·(μe/μmax)`，λ 由 `params["mu_p_growth"]`
透传。λ=0（默认）与原式逐位相同（R153 已验 `max|Δ|=0`）。

用法
----
    python tools/r153_lambda_scan.py --batches 3,22,36 --lams 0.25,0.35
    python tools/r153_lambda_scan.py --all86 --lams 0.30
    python tools/r153_lambda_scan.py --all86 --lams 0.30 --base-from runs/r151_shape_baseline.json
"""
import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
ENG = os.path.join(ROOT, "candidate", "indpensim", "v0.1")
sys.path.insert(0, ENG)

PHASE_KEYS = ("0-60", "60-120", "120-180", "180+")


def one(job):
    batch, lam = job
    from golden_params import COMBINED, build_params
    import simulate as s

    p = build_params(COMBINED[batch])
    if lam:
        p["mu_p_growth"] = float(lam)
    sim, v3 = s.simulate_open_loop(int(batch), p)
    ym = s.yield_metrics(sim, v3)
    sm = s.shape_metrics(sim, v3, channels=("P", "S"))
    va = s.validity(sim)
    lvl, _ = s.classify_crash(sim, yield_err=ym["rel_err_total"])

    row = {"batch": int(batch), "lam": float(lam),
           "yield_err": float(ym["rel_err_total"]),
           "valid": bool(va["valid"]), "crash": lvl, "flags": list(va["flags"])}
    for ch in ("P", "S"):
        m = sm.get(ch)
        if not m:
            continue
        row["%s_relrmse" % ch.lower()] = m["rel_rmse"]
        row["%s_r2" % ch.lower()] = m["r2"]
        row["%s_peak_ratio" % ch.lower()] = m["peak_ratio"]
        row["%s_end_ratio" % ch.lower()] = m["end_ratio"]
        row["%s_phase" % ch.lower()] = {k: m["phase"][k]["mean"] for k in PHASE_KEYS}
    return row


def summarise(rows):
    def q(v):
        v = np.asarray(v, float)
        v = v[np.isfinite(v)]
        if v.size == 0:
            return {"median": float("nan"), "p90": float("nan"), "mean": float("nan"), "n": 0}
        return {"median": float(np.median(v)), "p90": float(np.percentile(v, 90)),
                "mean": float(v.mean()), "n": int(v.size)}

    out = {"n": len(rows)}
    for k in ("yield_err", "p_relrmse", "p_peak_ratio", "p_end_ratio", "s_r2"):
        out[k] = q([r.get(k, np.nan) for r in rows])
    out["p_phase_mean"] = {k: float(np.nanmean([r["p_phase"][k] for r in rows]))
                           for k in PHASE_KEYS}
    out["n_yield_ok"] = int(sum(1 for r in rows if abs(r["yield_err"]) <= 0.05))
    out["n_valid"] = int(sum(1 for r in rows if r["valid"]))
    out["n_yield_ok_but_p_bad"] = int(sum(
        1 for r in rows if abs(r["yield_err"]) <= 0.05 and r.get("p_relrmse", 0) > 0.20))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", type=str, default="")
    ap.add_argument("--all86", action="store_true")
    ap.add_argument("--lams", type=str, default="0.25,0.35")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--json", type=str, default="runs/r153_lambda_scan.json")
    ap.add_argument("--base-from", type=str, default="",
                    help="λ=0 臂直接取自已有的基线 json（如 runs/r151_shape_baseline.json），省 1/3 时间")
    a = ap.parse_args()

    if a.all86:
        from r151_shape_accept import golden_batches
        bs = golden_batches()
    else:
        bs = [int(x) for x in a.batches.split(",") if x.strip()]
    lams = [float(x) for x in a.lams.split(",") if x.strip()]

    base = {}
    if a.base_from:
        blob = json.load(open(os.path.join(ROOT, a.base_from), encoding="utf-8")) \
            if not os.path.isabs(a.base_from) else json.load(open(a.base_from, encoding="utf-8"))
        base = {r["batch"]: r for r in blob["rows"]}
        print("base 复用 %d 批（%s）" % (len(base), os.path.basename(a.base_from)), flush=True)

    jobs = [(b, l) for l in lams for b in bs if not (l == 0.0 and b in base)]
    t0 = time.time()
    print("=== λ 扫描：%d 批 × %d 个 λ，%d 次仿真，workers=%d ==="
          % (len(bs), len(lams), len(jobs), a.workers), flush=True)

    rows = []
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        done = 0
        for r in ex.map(one, jobs):
            rows.append(r)
            done += 1
            if done % 10 == 0 or done == len(jobs):
                print("  %d/%d  %.0fs" % (done, len(jobs), time.time() - t0), flush=True)

    # 整理成分臂结构
    by_lam = {}
    for r in rows:
        by_lam.setdefault(r["lam"], []).append(r)
    for l in lams:
        if l == 0.0 and base:
            by_lam[0.0] = [dict(base[b], lam=0.0) for b in bs if b in base]

    print("\n臂      relRMSE中位  relRMSE均值  峰比  末比  | 0-60    60-120 120-180 180+  | 产量达标 valid  产达P差")
    summary = {}
    for l in lams:
        rs = by_lam.get(l, [])
        if not rs:
            continue
        s = summarise(rs)
        summary[l] = s
        pm = s["p_phase_mean"]
        print("λ=%.2f  %9.4f  %9.4f  %.3f %.3f | %+.3f %+.3f %+.3f %+.3f | %3d/%3d  %2d/%2d   %2d"
              % (l, s["p_relrmse"]["median"], s["p_relrmse"]["mean"],
                 s["p_peak_ratio"]["median"], s["p_end_ratio"]["median"],
                 pm["0-60"], pm["60-120"], pm["120-180"], pm["180+"],
                 s["n_yield_ok"], s["n"], s["n_valid"], s["n"], s["n_yield_ok_but_p_bad"]))

    # 逐批对照（对每个 λ 与 base 比）
    if 0.0 in by_lam:
        B = {r["batch"]: r for r in by_lam[0.0]}
        print("\n逐批 ΔrelRMSE（负=改善）；括号内为 Δ产量百分点")
        for l in lams:
            if l == 0.0:
                continue
            rs = by_lam.get(l, [])
            imp = [r for r in rs if r["batch"] in B and r["p_relrmse"] < B[r["batch"]]["p_relrmse"]]
            wor = [r for r in rs if r["batch"] in B and r["p_relrmse"] > B[r["batch"]]["p_relrmse"]]
            d_y = [ (r["yield_err"] - B[r["batch"]]["yield_err"]) * 100
                    for r in rs if r["batch"] in B]
            print("  λ=%.2f：relRMSE 改善 %d / 恶化 %d；Δ产量 中位 %+.2f pp，max|Δ| %.2f pp"
                  % (l, len(imp), len(wor), float(np.median(d_y)) if d_y else float("nan"),
                     float(np.max(np.abs(d_y))) if d_y else float("nan")))

    if a.json:
        p = a.json if os.path.isabs(a.json) else os.path.join(ROOT, a.json)
        os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            json.dump({"lams": lams, "rows": rows,
                       "by_lam": {str(k): v for k, v in by_lam.items()},
                       "summary": {str(k): v for k, v in summary.items()},
                       "elapsed_s": round(time.time() - t0, 1)}, fh,
                      ensure_ascii=False, indent=1)
        print("\nsaved:", p)


if __name__ == "__main__":
    main()
