# -*- coding: utf-8 -*-
"""R156 / D-55 第一问：`basic` 分支的驱动项到底错在哪 —— 逐点抓 dy[6]。

为什么要做这个
--------------
D-55 的记载是「`basic` 分支含 `−Kw/H⁺` 正反馈，`t* = H⁺²/(2Kw)`」。
这是 R148 从数值现象反推的结论，**没有在方程层验证过**。本轮先把病灶钉死在公式上，
否则后面三个候选形式（有界化 / 对数状态 / 降代数）就只是猜。

做法
----
不改引擎文件。在探针里把 `simulate.rhs` 包一层记录器，只在 `pH ≥ 6.85` 时记下
`(t, pH, H⁺, dy[6], V)`，然后事后按 pH 分箱统计：

  - `dy6 / (OH_eq − OH_now)` 是否 ≈ 1（若 ≈1 ⇒ 驱动项用的是 **OH 口径**，而状态是 H⁺）
  - 同一 pH 下 `dH⁺/dt` 的符号：**若在「该变酸」的状态下 dy[6] < 0**，就是反向驱动
  - `t* = H⁺²/(2Kw)` 与实测「从 pH 7 走到钳位」的时长对照

判据
----
若在 basic 分支内 dy[6] 的符号与「回到平衡所需方向」相反，且量级 ≈ Kw/H⁺，
则 D-55 的机制描述成立，且**唯一正确的修法是把驱动项换成 H⁺ 口径**（不动点不变）。

用法
----
    python tools/r156_ph_probe.py --batches 37,50,51,91,92
    python tools/r156_ph_probe.py --batches 22 --fs-u 1.01     # 制造越 7
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
ENG = os.path.join(ROOT, "candidate", "indpensim", "v0.1")
sys.path.insert(0, ENG)

KW = 1e-14


def probe_one(batch, fs_u=1.0, ph_lo=6.85):
    import simulate as s
    from golden_params import COMBINED, build_params

    rec = []
    orig = s.rhs

    def wrapped(t, y, inp1, par, **kw):
        d = orig(t, y, inp1, par, **kw)
        h = float(y[6])
        if h > 0.0:
            ph = -np.log10(max(h, 1e-15))
            if ph >= ph_lo:
                rec.append((float(t), ph, h, float(d[6]), float(y[4])))
        return d

    s.rhs = wrapped
    try:
        bp = dict(build_params(COMBINED[batch]))
        if abs(fs_u - 1.0) > 1e-12:
            bp["fs_ctl"] = {"kp": 0.0, "ki": 0.0, "u_lo": fs_u, "u_hi": fs_u}
        sim, v3 = s.simulate_open_loop(int(batch), bp)
    finally:
        s.rhs = orig

    au = sim.attrs.get("guard_audit", {})
    return {
        "batch": int(batch), "fs_u": float(fs_u),
        "rec": rec, "sim": sim, "v3": v3,
        "n_clamp": int(au.get("tally", {}).get("pH_H", 0)),
        "ph_max": float(np.nanmax(sim["pH_pre"].to_numpy(float))) if sim["pH_pre"].notna().any() else float("nan"),
        "ph_end": float(sim["pH"].iloc[-1]),
        "yield_err": float(s.yield_metrics(sim, v3)["rel_err_total"]),
    }


def report(r):
    rec = r["rec"]
    print(f"\n===== batch {r['batch']}  fs_u={r['fs_u']:.3f} "
          f"钳位={r['n_clamp']}  pH_max={r['ph_max']:.3f}  pH_end={r['ph_end']:.3f} "
          f"产量偏差={r['yield_err']*100:+.2f}%   记录点={len(rec)} =====")
    if not rec:
        print("  （无 pH >= 6.85 的点）")
        return None
    t = np.array([x[0] for x in rec])
    ph = np.array([x[1] for x in rec])
    h = np.array([x[2] for x in rec])
    dy6 = np.array([x[3] for x in rec])

    # 按 pH 分箱：dy6 的符号与量级
    bins = [(6.85, 6.99), (6.99, 7.05), (7.05, 7.20), (7.20, 7.60), (7.60, 99.0)]
    print(f"  {'pH 区间':>12} {'N':>6} {'中位 H+':>11} {'中位 dy6':>12} {'dy6/Kw·H':>11} "
          f"{'负向占比':>9} {'中位 OH':>10} {'|dy6|/OH':>9}")
    rows = []
    for lo, hi in bins:
        m = (ph >= lo) & (ph < hi)
        if not m.any():
            continue
        hh = h[m]
        oh = KW / np.maximum(hh, 1e-30)
        d = dy6[m]
        neg = float((d < 0).mean())
        ratio_h = float(np.median(d / np.maximum(hh, 1e-30)))
        ratio_oh = float(np.median(np.abs(d) / np.maximum(oh, 1e-30)))
        print(f"  [{lo:5.2f},{hi:5.2f}) {m.sum():6d} {np.median(hh):11.3e} {np.median(d):12.3e} "
              f"{ratio_h:11.2f} {neg:8.0%} {np.median(oh):10.3e} {ratio_oh:9.3f}")
        rows.append({"lo": lo, "hi": hi, "n": int(m.sum()), "h_med": float(np.median(hh)),
                     "dy6_med": float(np.median(d)), "neg_frac": neg,
                     "ratio_h": ratio_h, "ratio_oh": ratio_oh})

    # 关键时刻：pH 首次 >= 7 后 0..3 h 的 dy6 走向
    i7 = np.argmax(ph >= 7.0) if (ph >= 7.0).any() else None
    if i7 is not None:
        t7 = t[i7]
        print(f"\n  首次 pH>=7 在 t={t7:.1f} h（pH={ph[i7]:.4f}, H+={h[i7]:.3e}）")
        print(f"  理论 t* = H+^2/(2Kw) = {h[i7]**2/(2*KW):.3f} h")
        sel = (t >= t7) & (t <= t7 + 3.0)
        if sel.any():
            print(f"  {'t-t7':>7} {'pH':>9} {'H+':>12} {'dy6':>13} {'dy6 符号':>9}")
            idx = np.where(sel)[0]
            step = max(1, len(idx) // 12)
            for j in idx[::step][:12]:
                print(f"  {t[j]-t7:7.3f} {ph[j]:9.4f} {h[j]:12.3e} {dy6[j]:13.3e} "
                      f"{'→酸' if dy6[j] > 0 else '→碱(反)':>9}")
    return {"batch": r["batch"], "fs_u": r["fs_u"], "bins": rows,
            "ph_max": r["ph_max"], "ph_end": r["ph_end"], "n_clamp": r["n_clamp"],
            "yield_err": r["yield_err"], "t_first7": float(t[i7]) if i7 is not None else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", default="37,50,51,91,92")
    ap.add_argument("--fs-u", type=float, default=1.0)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    out = []
    for b in [int(x) for x in args.batches.split(",") if x.strip()]:
        r = probe_one(b, fs_u=args.fs_u)
        rep = report(r)
        if rep:
            out.append(rep)

    if out:
        print("\n===== 汇总 =====")
        print(f"{'batch':>6} {'ph_max':>8} {'ph_end':>8} {'钳位':>6} {'产量%':>9} {'t_first7':>9} "
              f"{'dy6<0 占比(pH>7)':>16}")
        for o in out:
            frac = np.mean([b["neg_frac"] for b in o["bins"] if b["lo"] >= 6.99]) \
                if any(b["lo"] >= 6.99 for b in o["bins"]) else float("nan")
            print(f"{o['batch']:6d} {o['ph_max']:8.3f} {o['ph_end']:8.3f} {o['n_clamp']:6d} "
                  f"{o['yield_err']*100:+9.2f} {(o['t_first7'] if o['t_first7'] is not None else float('nan')):9.2f} "
                  f"{frac:16.0%}")
    if args.json:
        import json
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"rows": out}, fh, ensure_ascii=False, indent=1)
        print(f"\njson -> {args.json}")


if __name__ == "__main__":
    main()
