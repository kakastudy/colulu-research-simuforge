# -*- coding: utf-8 -*-
"""R151 / D-43：形状口径的基线与判据 —— 给验收体系补上"形状"这一维。

为什么需要
----------
R150 已确认：86/86 批产量达标（中位 -0.07%），而 P 的 relRMSE 中位 15.6%、
max 84.8%，两者相关仅 +0.0113；P 误差 >0.20 的 21 批产量**全部**达标。
⇒ `yield_metrics().rel_err_total` 是标量和，只约束一个自由度，峰高可被尾低完全抵消。
在此口径下，D-42（产素时间剖面）的任何改进都无法被度量。本工具先立尺，再谈改模型。

本工具**只读 + 标准仿真**：不改参数、不改引擎、不写 data/processed。

输出
----
`runs/r151_shape_baseline.json`：per-batch 形状量 + 汇总 + `frozen` 快照段
（后续 D-42 的改动一律与 `frozen` 比，避免"改完再看基线已经动了"）。

用法
----
    python tools/r151_shape_accept.py                 # 86 批验证集
    python tools/r151_shape_accept.py --all-100
    python tools/r151_shape_accept.py --batches 22,36,55
    python tools/r151_shape_accept.py --workers 6
"""
import argparse
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
ENG = os.path.join(ROOT, "candidate", "indpensim", "v0.1")
sys.path.insert(0, ENG)

PHASE_KEYS = ("0-60", "60-120", "120-180", "180+")

# 判据草案（R151 立，D-42 结项前逐条收紧）。**soft**：当前不达标不阻断交付，
# 但必须打印 WARN 并计入台账；D-42 完成后其中 P 两条升为 hard。
GATE = {
    "p_relrmse_median": 0.10,     # 当前 0.156
    "p_phase_60_120_mean": -0.05,  # 当前 -0.092（跨批均值）
    "peak_ratio_median_abs_dev": 0.10,
    "end_ratio_median_abs_dev": 0.10,
    "s_r2_median": 0.60,
    "n_yield_ok_but_p_bad_max": 21,   # R151 基线 21/86（D-42 目标 <=10）
}


def golden_batches():
    """验证集批号。R148 纪律：必须从 final_validation_v2.json 取（88 批的 COMBINED 是错的）。"""
    p = os.path.join(ROOT, "runs", "final_validation_v2.json")
    d = json.load(open(p, encoding="utf-8"))
    rows = d.get("rows") or d.get("results") or []
    bs = []
    for r in rows:
        if isinstance(r, dict):
            b = r.get("batch", r.get("batch_no", r.get("b")))
            if b is not None:
                bs.append(int(b))
    return sorted(set(bs))


def one(batch, mode=None):

    """mode=None = 基线（逐位不变）；mode="v2" = R156 候选基线 v2。"""
    from golden_params import COMBINED, build_params
    import simulate as s

    p = build_params(COMBINED[batch])
    if mode == "v2":
        from golden_params import apply_candidate_v2
        apply_candidate_v2(p, batch)
    sim, v3 = s.simulate_open_loop(int(batch), p)
    ym = s.yield_metrics(sim, v3)
    sm = s.shape_metrics(sim, v3, channels=("P", "S"))
    va = s.validity(sim)
    lvl, why = s.classify_crash(sim, yield_err=ym["rel_err_total"])
    # R155 / D-38：五通道健康分级（A CO2d / B pH 钳位 / C pH 越域 / D P 崩塌 / E 产量破线）
    hl = s.classify_health(sim, v3, yield_err=ym["rel_err_total"])

    row = {
        "batch": int(batch),
        "yield_err": float(ym["rel_err_total"]),
        "valid": bool(va["valid"]),
        "crash": lvl,
        "health": hl["level"],
        "health_flags": list(hl["flags"]),
        "p_drop_ratio": float(hl["p_drop_ratio"]),
        "p_drop_rel": float(hl["p_drop_rel"]),
        "p_drop_ref": float(hl["p_drop_ref"]),
        "flags": list(va["flags"]),
    }
    for ch in ("P", "S"):
        m = sm.get(ch)
        if not m:
            continue
        row[f"{ch.lower()}_relrmse"] = m["rel_rmse"]
        row[f"{ch.lower()}_r2"] = m["r2"]
        row[f"{ch.lower()}_peak_ratio"] = m["peak_ratio"]
        row[f"{ch.lower()}_end_ratio"] = m["end_ratio"]
        row[f"{ch.lower()}_dt_peak"] = m["t_peak_sim"] - m["t_peak_meas"]
        row[f"{ch.lower()}_phase"] = {k: m["phase"][k]["mean"] for k in PHASE_KEYS}
    return row


def _q(v):
    v = np.asarray(v, float)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return {"median": float("nan"), "p90": float("nan"),
                "min": float("nan"), "max": float("nan"), "n": 0}
    return {"median": float(np.median(v)), "p90": float(np.percentile(v, 90)),
            "min": float(np.min(v)), "max": float(np.max(v)), "n": int(v.size)}


def summarise(rows):
    out = {"n": len(rows)}
    for key in ("yield_err", "p_relrmse", "p_r2", "p_peak_ratio", "p_end_ratio",
                "p_dt_peak", "s_relrmse", "s_r2"):
        out[key] = _q([r.get(key, float("nan")) for r in rows])
    # 跨批分相位均值：逐（批,相位）先算，再对批取均值（不是拿单批均值当跨批均值）
    out["p_phase_mean"] = {}
    out["p_phase_n_neg"] = {}
    for k in PHASE_KEYS:
        vals = [r["p_phase"][k] for r in rows if "p_phase" in r]
        out["p_phase_mean"][k] = float(np.nanmean(vals)) if vals else float("nan")
        out["p_phase_n_neg"][k] = int(sum(1 for v in vals if v < 0))
    out["n_yield_ok"] = int(sum(1 for r in rows if abs(r["yield_err"]) <= 0.05))
    out["n_valid"] = int(sum(1 for r in rows if r["valid"]))
    out["n_catastrophic"] = int(sum(1 for r in rows if r["crash"] == "catastrophic"))
    out["n_benign"] = int(sum(1 for r in rows if r["crash"] == "benign"))
    out["n_normal"] = int(sum(1 for r in rows if r["crash"] == "normal"))
    # R155 / D-38：五通道健康分级的计数与**名单**（名单比计数有用：新发批必须能被点名）
    # R157 / T1-1：额外记录 `n_health_rows` —— 有 health 字段的行数。
    # 旧 json（D-38 之前生成）只有 `crash` 字段 ⇒ n_health 计数全 0，
    # 而"全 0"与"真的没有健康问题"在汇总层**无法区分** ⇒ 恒真隐患。
    # 调用方据此判定 health 判据是否可用（本工具用 n_health_rows == n）。
    out["n_health_rows"] = int(sum(1 for r in rows if r.get("health")))
    out["health_available"] = bool(rows) and out["n_health_rows"] == len(rows)
    out["n_health"] = {k: int(sum(1 for r in rows if r.get("health") == k))
                       for k in ("normal", "benign", "degraded", "catastrophic")}
    out["catastrophic_batches"] = sorted(int(r["batch"]) for r in rows
                                         if r.get("health") == "catastrophic")
    out["degraded_batches"] = sorted(int(r["batch"]) for r in rows
                                     if r.get("health") == "degraded")
    out["health_flags_tally"] = {}
    for r in rows:
        for f in r.get("health_flags", []) or []:
            out["health_flags_tally"][f] = out["health_flags_tally"].get(f, 0) + 1
    # 产量达标但 P 形状差 的批（D-43 的量化证据）
    out["n_yield_ok_but_p_bad"] = int(sum(
        1 for r in rows if abs(r["yield_err"]) <= 0.05 and r.get("p_relrmse", 0) > 0.20))
    return out


def gate_check(summ):
    chk = []
    v = summ["p_relrmse"]["median"]
    chk.append(("P relRMSE 中位", v, f"<= {GATE['p_relrmse_median']:.2f}", v <= GATE["p_relrmse_median"]))
    v = summ["p_phase_mean"]["60-120"]
    chk.append(("P 60-120 相位均值", v, f">= {GATE['p_phase_60_120_mean']:+.2f}",
                v >= GATE["p_phase_60_120_mean"]))
    v = abs(summ["p_peak_ratio"]["median"] - 1.0)
    chk.append(("|峰比-1| 中位", v, f"<= {GATE['peak_ratio_median_abs_dev']:.2f}",
                v <= GATE["peak_ratio_median_abs_dev"]))
    v = abs(summ["p_end_ratio"]["median"] - 1.0)
    chk.append(("|末比-1| 中位", v, f"<= {GATE['end_ratio_median_abs_dev']:.2f}",
                v <= GATE["end_ratio_median_abs_dev"]))
    # S 不用 relRMSE：S 前期贴近 0，分母小 ⇒ 相对误差爆炸（实测中位 3.2，无判别力）。
    v = summ["s_r2"]["median"]
    # R154 / D-44：这条只反映**初始相（0–20 h）峰**的拟合度 —— S 的方差几乎全部来自那一段，
    # 而补料期的残糖（门控的自变量）对 R² 贡献 ≈0（残糖中位只差 13%，s_r2_hi 中位却是 −1.55）。
    # 因此它**不能**代表"模型把残糖算对了"，任何门控相关结论必须另用 s_resid / gate_duty（tools/r154_s_resid.py）。
    chk.append(("S R2 中位[仅初始相]", v, f">= {GATE['s_r2_median']:.2f}", v >= GATE["s_r2_median"]))
    # 这条才是 D-43 的要害：多少批"产量看着达标、P 形状其实很差"
    v = float(summ["n_yield_ok_but_p_bad"])
    chk.append(("产量达标但 P relRMSE>0.20", v,
                f"<= {GATE['n_yield_ok_but_p_bad_max']}", v <= GATE["n_yield_ok_but_p_bad_max"]))
    return chk


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", type=str, default="")
    ap.add_argument("--all-100", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", type=str, default="runs/r151_shape_baseline.json")
    args = ap.parse_args()

    if args.batches:
        bs, src = [int(x) for x in args.batches.split(",") if x.strip()], "manual"
    elif args.all_100:
        bs, src = list(range(1, 101)), "all100"
    else:
        bs, src = golden_batches(), "golden86"
    if args.limit:
        bs = bs[: args.limit]
    print(f"[r151] batches = {len(bs)} ({src}); workers = {args.workers}", flush=True)

    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        rows = list(ex.map(one, bs))

    summ = summarise(rows)
    chk = gate_check(summ)
    out = {"source": src, "batches": bs, "gate": GATE,
           "summary": summ, "gate_check": [{"name": n, "value": v, "rule": r, "pass": bool(p)}
                                           for n, v, r, p in chk],
           "rows": rows}
    op = os.path.join(ROOT, args.out)
    json.dump(out, open(op, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"\n=== 形状基线（{summ['n']} 批）===")
    print(f"  产量 |err|<=5%      {summ['n_yield_ok']}/{summ['n']}")
    print(f"  P relRMSE          中位 {summ['p_relrmse']['median']:.4f}  P90 {summ['p_relrmse']['p90']:.4f}"
          f"  max {summ['p_relrmse']['max']:.4f}")
    print(f"  P R2               中位 {summ['p_r2']['median']:.4f}  min {summ['p_r2']['min']:.4f}")
    print(f"  P 峰比/末比        中位 {summ['p_peak_ratio']['median']:.3f} / {summ['p_end_ratio']['median']:.3f}")
    print(f"  P 峰时差 (sim-meas) 中位 {summ['p_dt_peak']['median']:+.1f} h  P90 {summ['p_dt_peak']['p90']:+.1f} h")
    print(f"  S R2/relRMSE       中位 {summ['s_r2']['median']:.3f} / {summ['s_relrmse']['median']:.3f}"
          f"（relRMSE 分母是 |S| 均值，前期贴 0 时无判别力，只作记录）")
    print(f"  P 分相位均值       " + "  ".join(f"{k}:{summ['p_phase_mean'][k]:+.4f}" for k in PHASE_KEYS))
    print(f"  P 该相位为负的批数 " + "  ".join(f"{k}:{summ['p_phase_n_neg'][k]}" for k in PHASE_KEYS))
    print(f"  valid {summ['n_valid']}/{summ['n']}   crash: normal {summ['n_normal']}"
          f" / benign {summ['n_benign']} / catastrophic {summ['n_catastrophic']}")
    print(f"  产量达标但 P relRMSE>0.20 的批: {summ['n_yield_ok_but_p_bad']}/{summ['n']}")

    print("\n=== 形状判据（R151 草案，soft）===")
    for n, v, rule, ok in chk:
        print(f"  [{'PASS' if ok else 'WARN'}] {n:20s} = {v:+.4f}   {rule}")

    print("\n=== P relRMSE 最差 12 批 ===")
    print(" 批  relRMSE    峰比  末比  峰时差   产量%  相位 0-60/60-120/120-180/180+")
    for r in sorted(rows, key=lambda r: -r.get("p_relrmse", 0))[:12]:
        ph = " ".join(f"{r['p_phase'][k]:+.3f}" for k in PHASE_KEYS)
        print(f"{r['batch']:>3d}  {r['p_relrmse']:.4f}  {r['p_peak_ratio']:5.2f} {r['p_end_ratio']:5.2f}"
              f"  {r['p_dt_peak']:+6.1f}h  {r['yield_err']*100:+6.2f}  {ph}")
    print(f"\nwritten: {op}")


if __name__ == "__main__":
    main()
