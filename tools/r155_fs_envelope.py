# -*- coding: utf-8 -*-
"""R155 / D-54 第二问：进料剖面的**可行域厚度**——不改反馈，只把 Fs 静态缩放。

为什么要做这个
--------------
第一轮闭环（全域 PI、门控邻域、时间窗、小增益）**全部**把产量打到 −99%。
逐批轨迹显示的不是"控制器逻辑错"，而是 **pH 在 60–80 h 掉到 3.000**（guards 钳位），
此后糖不再被消耗、S 指数累积到 78 g/L。机制与 R148 的记载一致：
pH 方程的 `basic` 分支含 `−Kw/H⁺` 正反馈，pH 越 7 必崩（t* = H⁺²/(2Kw)，pH 7.0→0.5 h）。

而闭环在 40–50 h 只把 pH 抬了 **0.03–0.05**（6.708 vs 6.660）就崩了。
所以问题变成：**Fs 剖面到底能偏多少而不崩？** 这是"控制器能不能装"的前置问题，
也是 D-52（双稳态）在进料维度的定量版本。

方法
----
`fs_ctl = {"kp":0, "ki":0, "u_lo":u, "u_hi":u}` ⇒ u ≡ u，纯静态缩放，无反馈。
扫 u ∈ [0.85, 1.15]，看 yield_err / p_relrmse / valid / pH_max / 钳位步数。

判据
----
- 若 u 偏离 1.0 只有 ±2–5% 就出现产量崩塌 ⇒ 进料维度没有可操作裕度
  ⇒ **闭环控制器在这套方程里装不进去**（D-54 关闭为否定）
- 若一侧宽一侧窄 ⇒ 记录不对称性（产酸 vs 产碱方向）

用法
----
    python tools/r155_fs_envelope.py --batches 3,22,55,59,60 --us 0.85,0.90,0.95,0.98,1.02,1.05,1.10 --workers 5
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

from r155_closed_loop import metrics  # noqa: E402


def one(job):
    batch, us, ph_fix, mup_mult = job
    try:
        import simulate as s
        from golden_params import COMBINED, build_params

        bp = dict(build_params(COMBINED[batch]))
        bp["ph_fix"] = int(ph_fix)   # R156：0=原 pH 方程，1=链式法则修正
        if mup_mult is not None:      # R156：重标后的逐批 mup 倍率
            bp["mup"] = float(bp.get("mup", 0.041)) * float(mup_mult)
        sim0, v30 = s.simulate_open_loop(int(batch), bp)
        au = sim0.attrs.get("guard_audit", {})
        base = metrics(sim0, v30)
        base["ph_max"] = float(np.nanmax(sim0["pH_pre"].to_numpy(float))) \
            if sim0["pH_pre"].notna().any() else float("nan")
        base["n_clamp"] = int(au.get("tally", {}).get("pH_H", 0))
        rows = []
        for u in us:
            p1 = dict(bp)
            p1["fs_ctl"] = {"kp": 0.0, "ki": 0.0, "u_lo": u, "u_hi": u}
            sim1, v31 = s.simulate_open_loop(int(batch), p1)
            m = metrics(sim1, v31)
            mu = sim1.attrs.get("guard_audit", {})
            m["ph_max"] = float(np.nanmax(sim1["pH_pre"].to_numpy(float))) \
                if sim1["pH_pre"].notna().any() else float("nan")
            m["n_clamp"] = int(mu.get("tally", {}).get("pH_H", 0))
            m["u"] = float(u)
            rows.append(m)
        return {"batch": int(batch), "base": base, "arms": rows}
    except Exception as e:  # noqa: BLE001
        import traceback
        return {"batch": int(batch), "error": f"{type(e).__name__}: {e}",
                "tb": traceback.format_exc()[-600:]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", type=str, default="3,22,55,59,60")
    ap.add_argument("--us", type=str, default="0.85,0.90,0.95,0.98,1.02,1.05,1.10")
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--mup-map", default=None,
                    help="逐批 mup 倍率 '37:0.850,50:0.834'")
    ap.add_argument("--ph-fix", type=int, default=0, choices=[0, 1],
                    help="R156/D-55：0=原 pH 方程，1=basic 分支链式法则修正")
    ap.add_argument("--json", type=str, default="runs/r155_fs_envelope.json")
    args = ap.parse_args()

    batches = [int(x) for x in args.batches.split(",") if x.strip()]
    us = [float(x) for x in args.us.split(",") if x.strip()]
    mmap = {}
    if args.mup_map:
        for it in args.mup_map.split(","):
            if it.strip():
                k, v = it.split(":")
                mmap[int(k)] = float(v)
    jobs = [(b, us, args.ph_fix, mmap.get(b)) for b in batches]
    out = []
    if args.workers > 1:
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            for r in ex.map(one, jobs):
                out.append(r)
                print("done", r.get("batch"), r.get("error", ""), flush=True)
    else:
        for j in jobs:
            r = one(j)
            out.append(r)
            print("done", r.get("batch"), r.get("error", ""), flush=True)

    ok = [r for r in out if "error" not in r]
    print(f"\n=== Fs 静态缩放包络（{len(ok)} 批，ph_fix={args.ph_fix}）===")
    print(f"{'u':>6s}{'yield中位':>10s}{'yield最差':>10s}{'p_rrmse':>9s}{'pH_max':>8s}{'钳位批':>7s}{'valid':>7s}{'|Δy|>5批':>9s}")
    b = ok
    print(f"{1.0:6.2f}{np.median([r['base']['yield_err'] for r in b])*100:10.2f}"
          f"{min(r['base']['yield_err'] for r in b)*100:10.2f}"
          f"{np.median([r['base']['p_relrmse'] for r in b]):9.4f}"
          f"{np.median([r['base']['ph_max'] for r in b]):8.4f}"
          f"{sum(1 for r in b if r['base']['n_clamp'] > 0):7d}"
          f"{sum(1 for r in b if r['base']['valid']):7d}{0:9d}")
    for u in us:
        rows = [a for r in ok for a in r["arms"] if abs(a["u"] - u) < 1e-12]
        if not rows:
            continue
        y = np.array([a["yield_err"] for a in rows], float)
        print(f"{u:6.2f}{np.median(y)*100:10.2f}{y.min()*100:10.2f}"
              f"{np.median([a['p_relrmse'] for a in rows]):9.4f}"
              f"{np.median([a['ph_max'] for a in rows]):8.4f}"
              f"{sum(1 for a in rows if a['n_clamp'] > 0):7d}"
              f"{sum(1 for a in rows if a['valid']):7d}"
              f"{sum(1 for a in rows if abs(a['yield_err']) > 0.05):9d}")

    os.makedirs(os.path.dirname(os.path.join(ROOT, args.json)), exist_ok=True)
    with open(os.path.join(ROOT, args.json), "w", encoding="utf-8") as f:
        json.dump({"us": us, "batches": batches, "rows": out}, f, indent=1)
    print("\n->", args.json)


if __name__ == "__main__":
    main()
