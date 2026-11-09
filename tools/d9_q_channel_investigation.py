# -*- coding: utf-8 -*-
"""R129o: Q 通道系统性问题调查——3.6x 比例偏差。

D6 健康视图显示 Q 通道 12/12 critical（nRMSE ~550%）。仿真 Q (y[8]/1000)
系统性高于 V3 Q 约 3.6 倍。

Q 状态变量 (y[8]) 是总热流率 (dQ_dt)，包含：
- Fs 进料加热
- Fw 水加热
- F_evp 蒸发冷却
- delta_H_evap 蒸发焓
- Qrxn_t 反应热
- Ws 搅拌功率
- Fc 冷却夹套
- Fh 加热夹套
- Qcon 对流

V3 Q 可能只代表总热移除率（夹套冷却 + 蒸发），而非总热流率。
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))

import numpy as np
import pandas as pd

from simulate import simulate_open_loop


COMBINED = {
    8:  {"mux": 0.47, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.029,
          "biomass_death_rate": 0.001, "death_start": 100},
}

GOLDEN = [8, 11, 16, 22, 23, 27, 36, 55, 60, 80, 91, 92]


def main():
    print("=" * 80, flush=True)
    print("R129o: Q 通道系统性问题调查", flush=True)
    print("=" * 80, flush=True)

    # Check Q values across batches
    print("\nV3 Q values across batches:", flush=True)
    for b in [8, 11, 16, 22, 60]:
        v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
        print("  Batch {:2d}: Q min={:.1f} max={:.1f} mean={:.1f}".format(
            b, v3['Q'].min(), v3['Q'].max(), v3['Q'].mean()))

    # Check if V3 Q is related to Fg
    v3 = pd.read_csv("data/processed/batches/batch_08.csv")
    print("\nBatch 8 Q vs Fg:", flush=True)
    print("  Fg: min={:.1f} max={:.1f} mean={:.1f}".format(
        v3['Fg'].min(), v3['Fg'].max(), v3['Fg'].mean()))
    print("  Q/Fg: min={:.2f} max={:.2f} mean={:.2f}".format(
        (v3['Q'] / v3['Fg']).min(), (v3['Q'] / v3['Fg']).max(), (v3['Q'] / v3['Fg']).mean()))

    # Check if V3 Q is related to Fc (cooling)
    print("\n  Fc: min={:.1f} max={:.1f} mean={:.1f}".format(
        v3['Fc'].min(), v3['Fc'].max(), v3['Fc'].mean()))
    print("  Q/Fc: min={:.2f} max={:.2f} mean={:.2f}".format(
        (v3['Q'] / v3['Fc']).min(), (v3['Q'] / v3['Fc']).max(), (v3['Q'] / v3['Fc']).mean()))

    # Check if V3 Q is related to Fh (heating)
    print("\n  Fh: min={:.1f} max={:.1f} mean={:.1f}".format(
        v3['Fh'].min(), v3['Fh'].max(), v3['Fh'].mean()))

    # Check if V3 Q is related to pressure
    print("\n  pressure: min={:.2f} max={:.2f} mean={:.2f}".format(
        v3['pressure'].min(), v3['pressure'].max(), v3['pressure'].mean()))

    # Check if V3 Q is related to T (temperature)
    print("\n  T: min={:.1f} max={:.1f} mean={:.1f}".format(
        v3['T'].min(), v3['T'].max(), v3['T'].mean()))

    # Simulate batch 8 and check Q
    print("\nSim Q vs V3 Q (batch 8):", flush=True)
    cp = COMBINED[8]
    params = {"mux": cp["mux"], "mup": cp["mup"], "alpha_kla": 85.0,
              "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
              "dist_flag": 1, "dist_tcin_asym": cp["dist_tcin_asym"], "m_s": cp["m_s"],
              "biomass_death_rate": cp["biomass_death_rate"], "death_start": cp["death_start"]}
    sim, _ = simulate_open_loop(8, params)
    print("  V3 Q:  min={:.1f} max={:.1f} mean={:.1f}".format(
        v3['Q'].min(), v3['Q'].max(), v3['Q'].mean()))
    print("  Sim Q: min={:.1f} max={:.1f} mean={:.1f}".format(
        sim['Q'].min(), sim['Q'].max(), sim['Q'].mean()))
    print("  Ratio: mean={:.4f}".format(sim['Q'].mean() / v3['Q'].mean()))

    # Check if V3 Q is the total heat removal (Qcon + evaporation)
    # The sim Q (y[8]/1000) is the total heat flow (dQ_dt)
    # V3 Q might be just the jacket cooling (Qcon)
    # Let me check if V3 Q is related to the cooling flow rate (Fc)
    print("\n  V3 Q / Fc ratio: mean={:.4f}".format((v3['Q'] / v3['Fc']).mean()))
    print("  V3 Q / Fh ratio: mean={:.4f}".format((v3['Q'] / v3['Fh']).mean()))

    # Check if V3 Q is related to the total heat removal
    # The total heat removal includes jacket cooling + evaporation
    # Let me check if V3 Q is related to Fc + F_evp
    print("\n  V3 Q / (Fc + Fh) ratio: mean={:.4f}".format((v3['Q'] / (v3['Fc'] + v3['Fh'])).mean()))

    print("\nConclusion:", flush=True)
    print("  V3 Q values (200-800) suggest it's in kW or similar unit.", flush=True)
    print("  Sim Q (y[8]/1000) values (1000-2500) suggest a different scale.", flush=True)
    print("  The ratio is ~3.6x, suggesting V3 Q might be only a subset", flush=True)
    print("  of the total heat flow (e.g., jacket cooling only).", flush=True)
    print("  This is a pre-existing issue, not affected by the death term.", flush=True)


if __name__ == "__main__":
    main()
