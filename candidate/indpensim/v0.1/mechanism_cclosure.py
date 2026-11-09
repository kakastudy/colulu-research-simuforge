# -*- coding: utf-8 -*-
"""机理侧碳记账（A1 选项 1 落地：呼吸归认口径）。

地位（须披露）：V3 与引擎的尾气 CO2 % 通道（~1.7-2.0%，×Fg≈65 m³/h ≈ 0.15-0.17 t C/批）
与液相账（进料 C ~9.5 t/批 → 产品+生物量 ~4 t C）相差 ~5.5 t C/批——该差额只能是
呼吸 CO2 通量，但被所述气体流量单位排除。经 12 批核验，差额批间一致（resp share
+56%~+66%），即"进料 C = 产品 C + 生物量 C + 增余底物 C + 呼吸 CO2 C"总能闭合，
呼吸份额是账面归认值而非独立检验。气体通道单位溯源（indpensim.m 尾气公式）留待
数据提供方原文核证（当前环境无外网，T2 原文检索不可用）。

本模块输出：液相账四项 + resp_share_pct（=呼吸归认份额）= 100% − 液相输出占比。
数值检验力：若引擎积分漂移，液相输出占比会异常（对照 12 批一致性）。
"""
import sys, os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from simulate import simulate_open_loop
from calibration import calib_params, GOLDEN

C_S, C_OIL, C_PAA = 600.0, 1000.0, 530.0
CF_GLC, CF_OIL, CF_PAA, CF_P, CF_X = 0.400, 0.773, 0.706, 0.575, 0.45

# R157 / T1-2：`np.trapezoid` 是 numpy 2.0 才引入的新名，numpy 1.x 只有 `np.trapz`。
# 本项目 requirements.txt 锁定 numpy<2.0 ⇒ 直接写 `np.trapezoid` 会在 pinned 环境必崩。
_TRAPZ = getattr(np, "trapezoid", None) or np.trapz


def trapz(t, v):
    return float(_TRAPZ(v, t))


def mechanism_c_closure(sim, v3):
    t = sim["time_h"].to_numpy(float)  # sim 行丢首行（k>=2），与 v3 行 1:1 Offset 对齐
    n = len(t)
    Fs = sim["Fs"].to_numpy(float)
    Foil = np.clip(sim["Foil"].to_numpy(float), 0, None)
    Fpaa = np.clip(sim["Fpaa"].to_numpy(float), 0, None)
    C_in = trapz(t, Fs * C_S * CF_GLC + Foil * C_OIL * CF_OIL + Fpaa * C_PAA * CF_PAA)

    CO2_pct = sim["CO2outgas"].to_numpy(float)  # 引擎尾气 CO2 %
    CO2_out = trapz(t, CO2_pct / 100.0 * v3["Fg"].to_numpy(float)[1:n + 1] / 22.4 * 12.0)  # gC

    P_end = sim["P"].iloc[-1] * sim["V"].iloc[-1]
    P_harv = float(-(sim["Fremoved"] * sim["P"]).sum()) * 0.2
    S_end = sim["S"].iloc[-1] * sim["V"].iloc[-1]

    X = sim["X"].to_numpy(float)
    V = sim["V"].to_numpy(float)
    M_X = X * V
    F_rm = np.clip(-sim["Fremoved"].to_numpy(float), 0, None)
    M_X_removed = trapz(t, F_rm * X)
    dM_X = M_X[-1] + M_X_removed - M_X[0]

    C_out = CO2_out + CF_P * (P_end + P_harv) + CF_X * dM_X + CF_GLC * S_end
    resid = (C_in - C_out) / C_in
    return {"C_in_g": C_in, "C_out_g": C_out, "C_CO2_g": CO2_out,
            "C_P_g": CF_P * (P_end + P_harv), "C_dX_g": CF_X * dM_X,
            "C_S_end_g": CF_GLC * float(S_end),
            "resid_pct": 100.0 * resid,
            "mv_warnings": sim.attrs.get("mv_warnings", [])}


def run(batch_nos, out_path):
    rs = []
    for b in batch_nos:
        sim, v3 = simulate_open_loop(b, calib_params(b))
        r = {"batch": int(b), **mechanism_c_closure(sim, v3)}
        r["resp_share_pct"] = r.pop("resid_pct")  # 呼吸归认份额 = 100% - 液相输出占比
        rs.append(r)
        print(f"batch {b:2d}: resp_share={r['resp_share_pct']:+6.2f}% C_in={r['C_in_g']/1e3:8.0f} kg "
              f"C_gas帐={r['C_CO2_g']/1e3:6.0f} C_dX={r['C_dX_g']/1e3:6.0f} kg "
              f"P={r['C_P_g']/1e3:6.0f} kg S_end={r['C_S_end_g']/1e3:5.0f} kg",
              flush=True)
    import json
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(rs, f, ensure_ascii=False, indent=2)
    print(f"Saved: {out_path}")
    return rs


if __name__ == "__main__":
    run(GOLDEN, "runs/mechanism_c_closure.json")
