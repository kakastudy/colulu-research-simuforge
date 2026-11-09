# -*- coding: utf-8 -*-
"""PH4 前置演示：滚动控制咨询算子（advise_control）。

场景：批 8 在 t=120h（生理中期）咨询"下一窗（120–160h）糖/油补料倍率"。
方法：领域约束下的反事实重放评分（counterfactual replay scoring）——
对 K 个候选倍率组合用窗口 MV 缩放模拟全程 → 分数 = |批末产量 − V3 目标|；
带有效性域告警与崩溃分级裁决。输出建议（best scale + 证据链）。
"""
import sys, os, json
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics, classify_crash

d = pd.read_csv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "data", "processed", "batches", "batch_08.csv"))
BASE = {"mux": 0.47, "mup": 0.041, "alpha_kla": 85.0, "PAA_c": 530000.0,
        "N_conc_paa": 150000.0, "c_oil": 1000.0, "dist_flag": 1,
        "dist_tcin_asym": 10, "m_s": 0.029}
T_NOW, T1 = 120.0, 160.0
TARGET = float(d["V"].iloc[-1] * d["P"].iloc[-1] -
               (d["Fremoved"] * d["P"]).sum() * 0.2)  # 近似：以完全口径重排——用 yield 口径更准
# —— 直接用 yield_metrics 的 total_v3_g 作目标（简单一致）——

print("=== 批 8 advise_control 演示：窗 [120,160) 糖/油倍率咨询 ===", flush=True)
CANDS = [(1.00, 1.00), (1.03, 1.00), (1.06, 1.00), (1.00, 0.95), (1.03, 0.95), (0.97, 1.00)]

# 目标（完全产量口径）
sim0, _ = simulate_open_loop(8, BASE)
ym0 = yield_metrics(sim0, d)
target_g = ym0["total_v3_g"]
print(f"V3 目标产量: {target_g/1e6:.3f} Mg；基线偏差 {ym0['rel_err_total']:+.1%}", flush=True)

rows = []
for vfs, foil in CANDS:
    params = dict(BASE, mv_window_scales=[{"t0": T_NOW, "t1": T1, "scales": {"Fs": vfs, "Foil": foil}}])
    try:
        sim, _ = simulate_open_loop(8, params)
        ym = yield_metrics(sim, d)
        lvl, reasons = classify_crash(sim, yield_err=float(ym["rel_err_total"]))
        gap = ym["total_sim_g"] - target_g
        rows.append({"Fs": vfs, "Foil": foil, "yield_Mg": round(ym["total_sim_g"] / 1e6, 4),
                     "gap_pct": round(100 * gap / target_g, 2), "level": lvl})
        print(f"  Fs×{vfs:.2f} Foil×{foil:.2f}: yield={ym['total_sim_g']/1e6:.3f} Mg "
              f"gap={100*gap/target_g:+.2f}% {lvl}", flush=True)
    except Exception as e:
        rows.append({"Fs": vfs, "Foil": foil, "yield_Mg": None, "gap_pct": None,
                     "level": "DIVERGED"})
        print(f"  Fs×{vfs:.2f} Foil×{foil:.2f}: DIVERGED ({type(e).__name__})", flush=True)

ok_rows = [r for r in rows if r["gap_pct"] is not None and r["level"] != "catastrophic"]
if ok_rows:
    best = min(ok_rows, key=lambda r: abs(r["gap_pct"]))
    print(f"\n建议（advise）: 窗 [120,160) Fs×{best['Fs']} Foil×{best['Foil']}"
          f" → gap {best['gap_pct']:+.2f}%（崩溃分级 {best['level']}）", flush=True)

# T1 操作窗校验（PH4 硬约束，knowledge_constraints.validate_t1）
from knowledge_constraints import validate_t1
sim_end = sim0.iloc[-1]
_t1_sample = {"T": float(sim_end["T"]), "pH": float(sim_end["pH"]),
              "CO2d": float(sim0["CO2d"].max()), "DO2": float(sim_end["DO2"]),
              "mv_scales": dict(BASE.get("mv_scales") or {"Fs": 1.0, "Foil": 1.0})}
_t1_ok, _t1_reasons = validate_t1(_t1_sample)
print(f"\nT1 操作窗校验: {'PASS' if _t1_ok else 'FAIL'}; reasons={_t1_reasons}", flush=True)

os.makedirs("runs/hier_est", exist_ok=True)
with open("runs/hier_est/advise_b8_demo.json", "w", encoding="utf-8") as f:
    json.dump({"target_g": target_g, "cands": rows, "best": best if ok_rows else None}, f, ensure_ascii=False, indent=2)
print("Saved: runs/hier_est/advise_b8_demo.json")
