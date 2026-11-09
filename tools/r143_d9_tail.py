# -*- coding: utf-8 -*-
"""R143 · D-9 附：b92 尾段 pH 崩落的性质（数值 or 结构）。

R143b 发现：三臂的 `pH_end` 全都是 3.00（化验 6.49），且 b91 同样崩落、三个正常批不崩。
这说明 b92 的 `rmse_pH=0.772` 主要不是"故障没复现"，而是**故障窗之后的尾段崩落**（tail RMSE 2.30，
凹陷窗内仅 0.254）。若不判断它是数值伪影还是结构性发散，就无法决定要不要开新债。

判据（沿用 R134 T5 的口径）：
  · 若跨求解器/跨容差 pH 崩落时刻与末值一致 → **结构性**，与积分器无关，可引用；
  · 若随容差收窄消失 → 数值伪影，登记为数值债即可。

副产物：复核剂量响应里 mag=3e-4 的异常点（pH_all 0.450 / yield +10.95%），确认它不是真最优。
"""
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))

import numpy as np
import pandas as pd

from simulate import simulate_open_loop, load_batch, yield_metrics
import golden_params as gp

OUT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "runs", "p3", "r143_d9_tail.json"))
B = 92
WIN = (141.2, 167.6)
CONFIGS = [
    {"name": "BDF@1e-3(默认)", "ode_method": "BDF", "ode_rtol": 1e-3, "ode_atol": 1e-6},
    {"name": "BDF@1e-6", "ode_method": "BDF", "ode_rtol": 1e-6, "ode_atol": 1e-8},
    {"name": "Radau@1e-8", "ode_method": "Radau", "ode_rtol": 1e-8, "ode_atol": 1e-10},
]


def main():
    d = load_batch(B)
    lab_ph = pd.to_numeric(d["pH"], errors="coerce").to_numpy(float)
    t_lab = pd.to_numeric(d["time_h"], errors="coerce").to_numpy(float)
    rec = {"batch": B, "configs": [], "dose_recheck": []}

    print("=" * 86)
    print("b92 尾段 pH 崩落：跨求解器 / 跨容差")
    print("=" * 86)
    print(f"{'config':>18} {'pH@210':>8} {'pH@220':>8} {'pH@230':>8} {'pH_min':>8} "
          f"{'崩落起点':>9} {'yield%':>8}")
    for cfg in CONFIGS:
        p = dict(gp.params_for(B))
        p.update({k: v for k, v in cfg.items() if k != "name"})
        try:
            sim, _ = simulate_open_loop(B, p)
        except Exception as exc:  # 积分失败本身就是结论，不能中断整轮
            rec["configs"].append({"config": cfg["name"], "status": "integrate_failed",
                                   "error": str(exc)[:200]})
            print(f"{cfg['name']:>18} {'积分失败':>8}  {str(exc)[:80]}")
            continue
        t = sim["time_h"].to_numpy(float)
        ph = sim["pH"].to_numpy(float)

        def at(x):
            return float(np.interp(x, t, ph))

        bad = t[ph < 5.0]
        ym = yield_metrics(sim, d)
        row = {
            "config": cfg["name"], "status": "ok",
            "ph_at_210": at(210.0), "ph_at_220": at(220.0), "ph_at_230": at(230.0),
            "ph_min": float(ph.min()), "ph_end": float(ph[-1]),
            "collapse_start": float(bad[0]) if len(bad) else None,
            "yield_err": float(ym["rel_err_total"]),
        }
        rec["configs"].append(row)
        print(f"{cfg['name']:>18} {row['ph_at_210']:>8.3f} {row['ph_at_220']:>8.3f} "
              f"{row['ph_at_230']:>8.3f} {row['ph_min']:>8.3f} "
              f"{(row['collapse_start'] or float('nan')):>9.1f} {row['yield_err']*100:>8.2f}")

    # 复核 mag=3e-4 的异常点
    print()
    print("=" * 86)
    print("剂量响应异常点复核（mag=3e-4）")
    print("=" * 86)
    print(f"{'mag':>9} {'pH_win':>8} {'pH_210':>8} {'pH_220':>8} {'pH_end':>8} {'yield%':>8}")
    for mag in (0.0, 3e-4, 1e-3):
        p = dict(gp.params_for(B))
        if mag > 0:
            p.update({"fault_type": 2, "fault_start": WIN[0], "fault_end": WIN[1],
                      "fault_magnitude": mag})
        sim, _ = simulate_open_loop(B, p)
        t = sim["time_h"].to_numpy(float)
        ph = sim["pH"].to_numpy(float)
        t_al = t_lab - 4.0
        m = (t_lab >= WIN[0]) & (t_lab <= WIN[1]) & np.isfinite(lab_ph)
        sv = np.interp(t_al[m], t, ph)
        rw = float(np.sqrt(np.mean((sv - lab_ph[m]) ** 2)))
        ym = yield_metrics(sim, d)
        row = {"mag": mag, "rmse_pH_win": rw,
               "ph_at_210": float(np.interp(210.0, t, ph)),
               "ph_at_220": float(np.interp(220.0, t, ph)),
               "ph_end": float(ph[-1]), "yield_err": float(ym["rel_err_total"])}
        rec["dose_recheck"].append(row)
        print(f"{mag:>9.4g} {rw:>8.3f} {row['ph_at_210']:>8.3f} {row['ph_at_220']:>8.3f} "
              f"{row['ph_end']:>8.3f} {row['yield_err']*100:>8.2f}")

    json.dump(rec, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=float)
    print(f"\n落盘 {OUT}")


if __name__ == "__main__":
    main()
