# -*- coding: utf-8 -*-
"""R152 / D-42：组合扫描 —— 放宽门控（抬中段）配降压旋钮（把产量拉回）。

为什么需要组合
--------------
单臂扫描（`r152_gate_scan.py`，6 批 × 9 臂）的结论是**没有一个单旋钮有选择性**：

| 臂 | d(60-120) | d(120-180) | 产量 | 选择性 |
|---|---|---|---|---|
| `mu_h×0.9` | +0.0135 | **+0.0557** | +13.1% | 0.24 |
| `meanP×1.25` | +0.0150 | **−0.0534** | +7.0% | 0.28 |
| `sd×2` | **+0.0833** | +0.0644 | **+29.7%** | **1.29** |
| `sd×5` | **+0.1407** | +0.0978 | **+41.5%** | **1.44** |
| `pcritPAA×2` | −0.0004 | −0.0114 | −2.1% | −0.04 |

`sd` 是唯一选择性 > 1 的臂 —— 它把中段抬起来了，但也把后段一起抬了，且产量爆到 +30~42%。
所以问题变成：**能不能用 `mu_p` 把总量压回来，同时保住中段？**
（`mu_p` 是**一阶全局**旋钮：它按比例缩放整条产素曲线，理论上不改变形状，但能抵消
 `sd` 带来的总量增加。两者相乘 = "更宽的门控 × 更小的产率"，是形状与总量的解耦尝试。）

`mu_p` 没有 `par[0]` 覆盖口，走 `params["dist_mup"]`（加性，`mu_p = par[0] + distMuP`，基线 0.012）。

用法
----
    python tools/r152_combo_scan.py                     # 12 批
    python tools/r152_combo_scan.py --batches 3,22,36
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
DEFAULT_BATCHES = (1, 2, 3, 5, 8, 12, 22, 36, 45, 50, 55, 59)


def arms_for(mu_p0, sd0, meanP0):
    """(name, overrides)。mu_p 用 dist_mup 的加性偏移。"""
    dp = lambda f: {"dist_mup": mu_p0 * (f - 1.0)}
    return [
        ("base", {}),
        ("C_sd1.6_mup0.70_mP1.10", {"P_std_dev": sd0 * 1.6, "mean_P": meanP0 * 1.10, **dp(0.70)}),
        ("D_sd1.8_mup0.66_mP1.10", {"P_std_dev": sd0 * 1.8, "mean_P": meanP0 * 1.10, **dp(0.66)}),
    ]


def one(job):
    batch, arms = job
    from golden_params import COMBINED, build_params
    import simulate as s

    out = []
    for name, ov in arms:
        p = dict(build_params(COMBINED[batch]))
        p.update(ov)
        sim, v3 = s.simulate_open_loop(int(batch), p)
        ym = s.yield_metrics(sim, v3)
        sm = s.shape_metrics(sim, v3, channels=("P",))["P"]
        va = s.validity(sim)
        out.append({
            "arm": name, "p_relrmse": sm["rel_rmse"], "p_r2": sm["r2"],
            "peak_ratio": sm["peak_ratio"], "end_ratio": sm["end_ratio"],
            "phase": {k: sm["phase"][k]["mean"] for k in PHASE_KEYS},
            "yield_err": float(ym["rel_err_total"]), "valid": bool(va["valid"]),
        })
    return {"batch": int(batch), "arms": out}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", type=str, default="")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--all86", action="store_true")
    ap.add_argument("--base-from", type=str, default="",
                    help="从某份 shape_baseline json 借 base 臂的数值，跳过 base 的仿真")
    args = ap.parse_args()

    from params import make_params
    par = make_params()
    mu_p0, sd0, meanP0 = float(par[0]), float(par[3]), float(par[4])
    arms = arms_for(mu_p0, sd0, meanP0)
    if args.batches:
        bs = [int(x) for x in args.batches.split(",") if x.strip()]
    elif args.all86:
        d = json.load(open(os.path.join(ROOT, "runs", "final_validation_v2.json"), encoding="utf-8"))
        bs = []
        for r in (d.get("rows") or d.get("results") or []):
            if isinstance(r, dict):
                b = r.get("batch", r.get("batch_no", r.get("b")))
                if b is not None:
                    bs.append(int(b))
        bs = sorted(set(bs))
    else:
        bs = list(DEFAULT_BATCHES)
    print(f"[r152-combo] batches={len(bs)} arms={len(arms)}  mu_p={mu_p0} sd={sd0} meanP={meanP0}",
          flush=True)

    run_arms = arms
    ref = None
    if args.base_from:
        ref = {r["batch"]: r for r in json.load(open(args.base_from, encoding="utf-8"))["rows"]}
        run_arms = [a for a in arms if a[0] != "base"]
        print(f"[r152-combo] base 臂取自 {os.path.basename(args.base_from)}（不重跑）", flush=True)

    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        rows = list(ex.map(one, [(b, run_arms) for b in bs]))

    if ref is not None:
        for r in rows:
            b = r["batch"]
            if b not in ref:
                continue
            x = ref[b]
            r["arms"].insert(0, {
                "arm": "base", "p_relrmse": x["p_relrmse"], "p_r2": x["p_r2"],
                "peak_ratio": x["p_peak_ratio"], "end_ratio": x["p_end_ratio"],
                "phase": {k: x["p_phase"][k] for k in PHASE_KEYS},
                "yield_err": x["yield_err"], "valid": x["valid"],
            })

    def agg(name, key):
        return float(np.mean([a[key] for r in rows for a in r["arms"] if a["arm"] == name]))

    def agg_ph(name, ph):
        # nanmean：180+ 相位在短批上无样点（np.mean 会把整列变成 nan）
        v = [a["phase"][ph] for r in rows for a in r["arms"] if a["arm"] == name]
        v = [x for x in v if np.isfinite(x)]
        return float(np.mean(v)) if v else float("nan")

    print(f"\n=== 跨批均值（{len(bs)} 批）===")
    print(f"{'arm':20s} {'relRMSE':>8s} {'峰比':>6s} {'末比':>6s} " +
          " ".join(f"{k:>8s}" for k in PHASE_KEYS) + f" {'产量%':>7s} {'valid':>5s}")
    rec = {}
    for name, _ in arms:
        rec[name] = {"p_relrmse": agg(name, "p_relrmse"), "peak_ratio": agg(name, "peak_ratio"),
                     "end_ratio": agg(name, "end_ratio"), "yield_err": agg(name, "yield_err"),
                     "phase": {k: agg_ph(name, k) for k in PHASE_KEYS},
                     "n_valid": int(sum(1 for r in rows for a in r["arms"]
                                        if a["arm"] == name and a["valid"]))}
        x = rec[name]
        print(f"{name:20s} {x['p_relrmse']:8.4f} {x['peak_ratio']:6.3f} {x['end_ratio']:6.3f} " +
              " ".join(f"{x['phase'][k]:+8.4f}" for k in PHASE_KEYS) +
              f" {x['yield_err'] * 100:+7.2f} {x['n_valid']:5d}")

    b = rec["base"]
    print("\n=== 相对 base ===")
    print(f"{'arm':20s} {'d(60-120)':>10s} {'d(120-180)':>11s} {'d(产量%)':>9s} "
          f"{'选择性':>7s} {'合格':>4s}")
    for name, _ in arms[1:]:
        x = rec[name]
        d1 = x["phase"]["60-120"] - b["phase"]["60-120"]
        d2 = x["phase"]["120-180"] - b["phase"]["120-180"]
        dy = (x["yield_err"] - b["yield_err"]) * 100
        sel = d1 / abs(d2) if abs(d2) > 1e-6 else float("inf")
        ok = "Y" if (d1 > 0.02 and d2 <= 0.02 and abs(x["yield_err"]) <= 0.05) else "N"
        print(f"{name:20s} {d1:+10.4f} {d2:+11.4f} {dy:+9.2f} {sel:7.2f} {ok:>4s}")

    print("\n合格 = d(60-120)>+0.02 且 d(120-180)<=+0.02 且 |产量误差|<=5%。")
    op = os.path.join(ROOT, "runs", "r152_combo_scan.json")
    json.dump({"batches": bs, "arms": rec, "mu_p0": mu_p0, "sd0": sd0, "meanP0": meanP0,
               "rows": rows}, open(op, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\nwritten: {op}")


if __name__ == "__main__":
    main()
