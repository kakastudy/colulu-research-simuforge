# -*- coding: utf-8 -*-
"""R156 / D-55：86 批回归 —— `ph_fix=1` 改了谁、没改谁，以及重标后能不能守住 ±5%。

背景
----
`ph_fix=1` 只动 pH 方程的 **basic 分支**（pH >= 7 才触发），acidic 分支逐字未动。
所以**只有越 7 的批会变**，其余逐位不变。R155 验收数据里 invalid 9 批
（37/40/43/49/50/51/54/91/92）正是 pH 越 7 的批。

本工具做三件事
--------------
1. 跑 86 批 `ph_fix=1`，与冻结基线 `runs/r151_shape_baseline.json`（= ph_fix=0）逐批比，
   报 **哪些批 max|Δ| = 0**（应为 77）、**哪些批变了**（应为 9）
2. 对变化的批做 `mup` 重标臂，看能否把产量拉回 ±5%
3. 报健康分级变化（normal/degraded/catastrophic）与 pH 越 7、钳位计数

用法
----
    python tools/r156_regress86.py --ph-fix 1 --workers 8 --json runs/r156_regress_fix.json
    python tools/r156_regress86.py --ph-fix 1 --mup-mult 0.86 \
        --batches 37,40,43,49,50,51,54,91,92 --json runs/r156_regress_recal.json
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
sys.path.insert(0, os.path.join(ROOT, "tools"))

PHASE_KEYS = ("0-60", "60-120", "120-180", "180+")
BASE_JSON = os.path.join(ROOT, "runs", "r151_shape_baseline.json")
METRICS = ("yield_err", "p_relrmse", "p_r2", "p_peak_ratio", "p_end_ratio",
           "p_dt_peak", "s_relrmse", "s_r2", "s_peak_ratio", "s_end_ratio")


def one(job):
    batch, ph_fix, mup_mult = job
    try:
        import simulate as s
        from golden_params import COMBINED, build_params

        p = dict(build_params(COMBINED[batch]))
        p["ph_fix"] = int(ph_fix)
        if mup_mult is not None:
            p["mup"] = float(p.get("mup", 0.041)) * float(mup_mult)
        sim, v3 = s.simulate_open_loop(int(batch), p)
        ym = s.yield_metrics(sim, v3)
        sm = s.shape_metrics(sim, v3, channels=("P", "S"))
        va = s.validity(sim)
        hl = s.classify_health(sim, v3, yield_err=ym["rel_err_total"])
        au = sim.attrs.get("guard_audit", {})
        row = {
            "batch": int(batch), "ph_fix": int(ph_fix), "mup_mult": mup_mult,
            "yield_err": float(ym["rel_err_total"]),
            "valid": bool(va["valid"]), "flags": list(va["flags"]),
            "health": hl["level"], "health_flags": list(hl["flags"]),
            "n_clamp": int(au.get("tally", {}).get("pH_H", 0)),
            "ph_max_pre": float(np.nanmax(sim["pH_pre"].to_numpy(float)))
            if sim["pH_pre"].notna().any() else float("nan"),
            "ph_end": float(sim["pH"].iloc[-1]),
        }
        for ch in ("P", "S"):
            m = sm.get(ch)
            if not m:
                continue
            row[f"{ch.lower()}_relrmse"] = float(m["rel_rmse"])
            row[f"{ch.lower()}_r2"] = float(m["r2"])
            row[f"{ch.lower()}_peak_ratio"] = float(m["peak_ratio"])
            row[f"{ch.lower()}_end_ratio"] = float(m["end_ratio"])
            row[f"{ch.lower()}_dt_peak"] = float(m["t_peak_sim"] - m["t_peak_meas"])
            row[f"{ch.lower()}_phase"] = {k: float(m["phase"][k]["mean"]) for k in PHASE_KEYS}
        return row
    except Exception as e:  # noqa: BLE001
        import traceback
        return {"batch": int(batch), "error": f"{type(e).__name__}: {e}",
                "tb": traceback.format_exc()[-600:]}


def compare(rows):
    """与冻结基线（ph_fix=0）逐批比。"""
    if not os.path.exists(BASE_JSON):
        return None
    base = {r["batch"]: r for r in json.load(open(BASE_JSON, encoding="utf-8"))["rows"]}
    out = []
    for r in rows:
        if "error" in r or r["batch"] not in base:
            continue
        b = base[r["batch"]]
        d = {}
        for k in METRICS:
            if k in r and k in b and np.isfinite(r[k]) and np.isfinite(b[k]):
                d[k] = float(r[k]) - float(b[k])
        for ph in PHASE_KEYS:
            for ch in ("p", "s"):
                k = f"{ch}_phase"
                if k in r and k in b and ph in r[k] and ph in b[k]:
                    d[f"{ch}_phase_{ph}"] = float(r[k][ph]) - float(b[k][ph])
        mx = max((abs(v) for v in d.values()), default=0.0)
        out.append({"batch": r["batch"], "max_abs_delta": mx,
                    "delta": d, "yield_err": r["yield_err"], "base_yield_err": b["yield_err"],
                    "valid": r["valid"], "base_valid": b["valid"],
                    "health": r["health"], "base_health": b.get("health"),
                    "n_clamp": r.get("n_clamp"), "ph_max_pre": r.get("ph_max_pre"),
                    "ph_end": r.get("ph_end")})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", default=None, help="逗号分隔；缺省 = 全部 86 批")
    ap.add_argument("--ph-fix", type=int, default=1, choices=[0, 1])
    ap.add_argument("--mup-mult", type=float, default=None)
    ap.add_argument("--mup-map", default=None,
                    help="逐批 mup 倍率，格式 '37:0.868,50:0.834'；与 --mup-mult 互斥")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--json", default="runs/r156_regress.json")
    args = ap.parse_args()

    if args.batches:
        batches = [int(x) for x in args.batches.split(",") if x.strip()]
    else:
        d = json.load(open(BASE_JSON, encoding="utf-8"))
        batches = sorted(r["batch"] for r in d["rows"])

    jobs = [(b, args.ph_fix, args.mup_mult) for b in batches]
    if args.mup_map:
        mmap = {}
        for item in args.mup_map.split(","):
            if not item.strip():
                continue
            k, v = item.split(":")
            mmap[int(k)] = float(v)
        jobs = [(b, args.ph_fix, mmap.get(b, args.mup_mult)) for b in batches]
        print("mup map:", mmap)
    rows = []
    if args.workers > 1:
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            for r in ex.map(one, jobs):
                rows.append(r)
                print("done", r.get("batch"), r.get("error", ""), flush=True)
    else:
        for j in jobs:
            r = one(j)
            rows.append(r)
            print("done", r.get("batch"), r.get("error", ""), flush=True)

    ok = [r for r in rows if "error" not in r]
    cmp_ = compare(ok)
    print(f"\n=== ph_fix={args.ph_fix} mup_mult={args.mup_mult}：{len(ok)} 批 ===")
    ye = np.array([r["yield_err"] for r in ok], float) * 100
    print(f"  产量偏差：中位 {np.median(ye):+.2f}%  |Δ|>5% 的批 {int((np.abs(ye) > 5).sum())}"
          f"  min {ye.min():+.2f}%  max {ye.max():+.2f}%")
    print(f"  valid {sum(1 for r in ok if r['valid'])}/{len(ok)}"
          f"   钳位批 {sum(1 for r in ok if r['n_clamp'] > 0)}"
          f"   pH_pre>=7 批 {sum(1 for r in ok if np.isfinite(r['ph_max_pre']) and r['ph_max_pre'] >= 7.0)}")
    import collections
    print(f"  health: {dict(collections.Counter(r['health'] for r in ok))}")

    if cmp_:
        zero = [c["batch"] for c in cmp_ if c["max_abs_delta"] == 0.0]
        changed = [c for c in cmp_ if c["max_abs_delta"] > 0.0]
        print(f"\n  与冻结基线（ph_fix=0）比：max|Δ|=0 的批 {len(zero)}/{len(cmp_)}")
        print(f"  有变化的批 {len(changed)}：{[c['batch'] for c in changed]}")
        for c in sorted(changed, key=lambda x: x["batch"]):
            print(f"    b{c['batch']:<3} max|Δ|={c['max_abs_delta']:.4e}  "
                  f"yield {c['base_yield_err']*100:+7.2f}% -> {c['yield_err']*100:+7.2f}%  "
                  f"valid {c['base_valid']}->{c['valid']}  health {c['base_health']}->{c['health']}  "
                  f"clamp={c['n_clamp']} pHmax={c['ph_max_pre']:.3f} pHend={c['ph_end']:.2f}")

    os.makedirs(os.path.dirname(os.path.join(ROOT, args.json)), exist_ok=True)
    with open(os.path.join(ROOT, args.json), "w", encoding="utf-8") as f:
        json.dump({"ph_fix": args.ph_fix, "mup_mult": args.mup_mult,
                   "rows": rows, "compare": cmp_}, f, indent=1)
    print("\n->", args.json)


if __name__ == "__main__":
    main()
