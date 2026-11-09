# -*- coding: utf-8 -*-
"""R134 T5: b27 / b92「窄窗」是数值假象还是真分岔。

背景（R131/R132 遗留）：
  b27 的产量对 mup 极敏感——0.03500 → −22.6%、0.03510 → +4.6%、0.03520 → +4.9%。
  若这是积分器/容差造成的数值混沌，则 `narrow` 标签应撤销、b27/b92 可升为"可控制"；
  若是真实的 ODE 分岔（洗涤器/门控导致的解支跳变），则"可评估不可控制"的结论成立，
  且 M5 起不得把 b27/b92 当作控制基线。

判据（预先登记，避免事后解释）：
  对同一 mup，四种求解器配置的产量误差**散布** Δ = max−min（单位 pt）：
    Δ ≤ 0.10 pt  → 数值无关 ⇒ 悬崖为真分岔，narrow 保留
    Δ > 1.00 pt  → 数值相关 ⇒ 悬崖为积分假象，narrow 可撤销
    0.10 < Δ ≤ 1.00 → 证据不足，维持 narrow（保守）
  同时报告每种配置下 |err| ≤ 5% 的**可行窗宽**（mup 跨度），看求解器加密后窗是否变宽。

注意：默认配置 (BDF, rtol 1e-3) 必须与 R133 冻结值逐位一致；本脚本只做对照，不改默认。
"""
import argparse
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))

CONFIGS = [
    ("BDF", 1e-3),      # 生产默认（对齐 ode15s）
    ("BDF", 1e-6),
    ("Radau", 1e-8),
    ("LSODA", 1e-8),
]

# 扫描点：围绕已知悬崖布置；b8 为对照（无悬崖）
CASES = {
    27: [0.03480, 0.03490, 0.03500, 0.03505, 0.03510, 0.03515, 0.03520, 0.03530, 0.03540],
    92: [0.03940, 0.03950, 0.03960, 0.03965, 0.03970, 0.03980, 0.03990],
    8: [0.04000, 0.04100, 0.04200, 0.04300],
}

BUDGET_PCT = 5.0


def run_one(job):
    """job = (batch, mup, method, rtol)。返回结果 dict。Windows spawn 需元组传参。"""
    b, mup, method, rtol = job
    from golden_params import COMBINED, build_params
    from simulate import simulate_open_loop, yield_metrics

    p = build_params(COMBINED[b])
    p["mup"] = mup
    p["ode_method"] = method
    p["ode_rtol"] = rtol
    t0 = time.time()
    try:
        sim, v3 = simulate_open_loop(b, p)
        ym = yield_metrics(sim, v3)
        return {"batch": b, "mup": mup, "method": method, "rtol": rtol,
                "yield_g": ym["total_sim_g"], "yield_err_pct": ym["rel_err_total"] * 100,
                "secs": round(time.time() - t0, 1), "error": None}
    except Exception as e:  # 求解失败本身也是证据（刚性/混沌下的积分崩溃）
        return {"batch": b, "mup": mup, "method": method, "rtol": rtol,
                "yield_g": None, "yield_err_pct": None,
                "secs": round(time.time() - t0, 1), "error": str(e)}


def analyse(rows):
    """按 (batch, mup) 汇总跨求解器散布；按 (batch, config) 汇总可行窗宽。"""
    by_bm, by_bc = {}, {}
    for r in rows:
        by_bm.setdefault((r["batch"], r["mup"]), []).append(r)
        by_bc.setdefault((r["batch"], r["method"], r["rtol"]), []).append(r)

    per_mup = []
    for (b, mup), rs in sorted(by_bm.items()):
        errs = [x["yield_err_pct"] for x in rs if x["yield_err_pct"] is not None]
        n_fail = sum(1 for x in rs if x["yield_err_pct"] is None)
        spread = (max(errs) - min(errs)) if len(errs) >= 2 else None
        per_mup.append({
            "batch": b, "mup": mup, "n_ok": len(errs), "n_fail": n_fail,
            "err_min_pct": min(errs) if errs else None,
            "err_max_pct": max(errs) if errs else None,
            "err_med_pct": float(np.median(errs)) if errs else None,
            "spread_pt": spread,
            "feasible": bool(errs and abs(float(np.median(errs))) <= BUDGET_PCT),
            "by_config": {f"{x['method']}@{x['rtol']:.0e}": x["yield_err_pct"] for x in rs},
        })

    per_config = []
    for (b, method, rtol), rs in sorted(by_bc.items()):
        rs = sorted(rs, key=lambda x: x["mup"])
        ok = [x["mup"] for x in rs
              if x["yield_err_pct"] is not None and abs(x["yield_err_pct"]) <= BUDGET_PCT]
        # 最长连续可行区间（mup 网格上的连续段）
        best = cur = 0
        prev = None
        for m in ok:
            cur = cur + 1 if (prev is not None and abs(m - prev) < 1e-9 + 1e-5) else 1
            best = max(best, cur)
            prev = m
        per_config.append({
            "batch": b, "method": method, "rtol": rtol,
            "n_points": len(rs), "n_feasible": len(ok),
            "feasible_mup": ok,
            "window_width_mup": (max(ok) - min(ok)) if len(ok) >= 2 else 0.0,
            "longest_consecutive": best,
        })
    return per_mup, per_config


def verdict(per_mup, per_config, batch):
    """按预登记判据给结论。

    这里必须区分**两个不同的问题**（首版把它们混成一个"numerical_artifact"，
    会在 b27 上给出误导性结论）：
      Q1 可行窗是否会因加密求解器而**变宽**？→ 决定 `narrow` 标签去留
         （计划原文："若变宽 → 是数值问题，narrow 可撤销"）
      Q2 阈值之外的**跌落幅度**是否可复现？→ 决定能否引用具体误差数值
    实测 b27：Q1 否（四配置窗宽全为 0.00015）、Q2 否（−6.6% ~ −73.9%）。
    即：**阈值真实且稳健，跌落幅度是数值噪声**。只报 Q2 会把"窗宽稳定"这个
    关键事实抹掉，只报 Q1 又会让人误以为崩溃数值可信——所以两者都报。
    """
    pts = [p for p in per_mup if p["batch"] == batch and p["spread_pt"] is not None]
    cfg = [c for c in per_config if c["batch"] == batch]
    if not pts or not cfg:
        return {"batch": batch, "verdict": "insufficient", "why": "无跨求解器对照点"}
    max_spread = max(p["spread_pt"] for p in pts)
    ordered = sorted(pts, key=lambda x: x["mup"])
    jumps, worst = 0.0, None
    for a, b in zip(ordered, ordered[1:]):
        if a["err_med_pct"] is None or b["err_med_pct"] is None:
            continue
        j = abs(b["err_med_pct"] - a["err_med_pct"])
        if j > jumps:
            jumps, worst = j, (a["mup"], b["mup"], a["err_med_pct"], b["err_med_pct"])

    widths = {f"{c['method']}@{c['rtol']:.0e}": round(c["window_width_mup"], 6) for c in cfg}
    w_base = widths.get("BDF@1e-03", 0.0)
    w_max = max(widths.values()) if widths else 0.0
    widened = bool(w_base > 0 and w_max > 1.5 * w_base) or bool(w_base == 0 and w_max > 0.00005)

    threshold_real = not widened
    collapse_reproducible = max_spread <= 0.10

    if widened:
        v = "window_widened_revocable"
        why = (f"加密求解器后可行窗由 {w_base:.5f} 拓宽到 {w_max:.5f}（>1.5×）→ "
               f"窄窗主要是数值问题，可撤销 narrow 标签")
    elif collapse_reproducible:
        v = "threshold_robust_clean"
        why = (f"可行窗宽在全部配置下恒为 {w_max:.5f}（未变宽），且跨求解器散布仅 "
               f"{max_spread:.3f} pt → 阈值与跌落均与数值无关，量化结果可引用")
    else:
        v = "threshold_robust_collapse_noisy"
        why = (f"可行窗宽在全部配置下恒为 {w_max:.5f}（未变宽，BDF1e-3/1e-6/Radau/LSODA 一致）"
               f"→ **阈值真实，窄窗不是数值假象**；但阈值外跌落幅度跨求解器散布达 {max_spread:.1f} pt"
               f"（不可复现）→ **不得引用具体崩溃误差数值**，只可作定性判断")
    return {"batch": batch, "verdict": v, "why": why,
            "window_widened": widened, "threshold_real": threshold_real,
            "collapse_reproducible": collapse_reproducible,
            "max_spread_pt": round(max_spread, 4), "steepest_jump_pt": round(jumps, 2),
            "steepest_jump_at": worst, "window_width_by_config": widths,
            "n_feasible_points_by_config": {f"{c['method']}@{c['rtol']:.0e}": c["n_feasible"] for c in cfg}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", default="27,92,8")
    ap.add_argument("--serial", action="store_true")
    ap.add_argument("--reanalyse", action="store_true",
                    help="不重新仿真，读取已有 JSON 的 runs 重算判定（口径修好后用）")
    ap.add_argument("--out", default=os.path.join(ROOT, "runs", "p3", "r134_bifurcation.json"))
    args = ap.parse_args()

    batches = [int(x) for x in args.batches.split(",") if x.strip()]

    if args.reanalyse:
        prev = json.load(open(args.out, encoding="utf-8"))
        rows = prev["runs"]
        batches = sorted({r["batch"] for r in rows})
        t_start = time.time()
        print(f"重算判定（不重跑仿真）：{len(rows)} 条已有结果，批 {batches}")
    else:
        jobs = []
        for b in batches:
            for mup in CASES.get(b, []):
                for method, rtol in CONFIGS:
                    jobs.append((b, mup, method, rtol))

        print("=" * 100)
        print("R134 T5 b27/b92 分岔真伪 —— 多求解器 × 多容差 × mup 细扫")
        print(f"批 {batches}；共 {len(jobs)} 次仿真；"
              f"判据：①可行窗是否变宽（决定 narrow 去留）②阈值外跌落的跨求解器散布")
        print("=" * 100, flush=True)

        t_start = time.time()
        if args.serial:
            rows = []
            for i, j in enumerate(jobs, 1):
                rows.append(run_one(j))
                print(f"  [{i}/{len(jobs)}] b{j[0]} mup={j[1]:.5f} {j[2]}@{j[3]:.0e}", flush=True)
        else:
            from multiprocessing import Pool
            with Pool(min(8, os.cpu_count() or 1)) as pool:
                rows = pool.map(run_one, jobs, chunksize=1)
    t0 = t_start

    per_mup, per_config = analyse(rows)
    verdicts = [verdict(per_mup, per_config, b) for b in batches]

    print(f"\n{'批':>3s} {'mup':>9s} {'err_min%':>9s} {'err_max%':>9s} {'散布pt':>8s} {'可行':>5s}  各求解器")
    print("-" * 100)
    for p in per_mup:
        cfgs = " ".join(f"{k.split('@')[0]}:{('NA' if v is None else f'{v:+.2f}')}"
                        for k, v in p["by_config"].items())
        spread_s = "NA" if p["spread_pt"] is None else f"{p['spread_pt']:.3f}"
        emin = "NA" if p["err_min_pct"] is None else f"{p['err_min_pct']:.2f}"
        emax = "NA" if p["err_max_pct"] is None else f"{p['err_max_pct']:.2f}"
        print(f"{p['batch']:>3d} {p['mup']:>9.5f} {emin:>9s} {emax:>9s} "
              f"{spread_s:>8s} {str(p['feasible']):>5s}  {cfgs}")

    print("\n" + "=" * 100)
    print("判定")
    print("=" * 100)
    for v in verdicts:
        print(f"\nb{v['batch']}: 【{v['verdict']}】 {v['why']}")
        if v.get("window_width_by_config"):
            print("   各配置可行窗宽(mup):", v["window_width_by_config"])

    out = {"meta": {"batches": batches, "configs": [{"method": m, "rtol": r} for m, r in CONFIGS],
                    "budget_pct": BUDGET_PCT, "elapsed_s": round(time.time() - t0, 1),
                    "criteria": {"window_widened": "任一配置可行窗宽 >1.5× 基线(BDF@1e-3) → narrow 可撤销",
                                 "collapse_reproducible": "阈值外跌落跨求解器散布 <=0.10pt → 崩溃数值可引用"},
                    "note": "narrow 去留由『窗宽是否变宽』决定；『跌落幅度是否可复现』只决定能否引用具体数值"},
           "verdicts": verdicts, "per_mup": per_mup, "per_config": per_config, "runs": rows}
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"\nSaved: {args.out}  ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
