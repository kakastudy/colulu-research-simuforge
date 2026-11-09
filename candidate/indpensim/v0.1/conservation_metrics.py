# -*- coding: utf-8 -*-
"""元素平衡定量核验（GOAL.md §4.3）：C / N / O 批级闭合，以 V3 数据为锚 + 引擎常数。

方法（批级总量守恒）：
  C:  in  = Fs*c_s*Cf(glc) + Foil*c_oil*Cf(oil) + Fpaa*c_paa*Cf(paa)
      out = ∫CER(t)*V(t)dt * 12/44 + (P_harv+P_end)*Cf(P)
            + X 增量与随罐移除*Cf(X) + S_end*Cf(glc)
      err% = (out-in)/in

  【R134 口径修正】CER 在 V3 数据里是**体积速率 g/L/h**，且是 CO2 质量速率；
  旧实现写成 ∫CER dt / 44（漏乘罐体积 V、且把 CO2 当摩尔数换算），
  使 CO2 项从 ~6.6e6 g 碳塌缩到 ~7 g 碳，C 平衡被系统性低估 → 12 批全 fail（中位 −64.5%）。
  现按 ∫CER·V dt × (12/44) 还原为「总 CO2 碳量」，与 P/X 项同量纲相加。
  N:  in  = ΣNH3_shots(N_conc_shot*0.822) + Foil*N_conc_oil + Fpaa*N_conc_paa
      out = P*Y_NP^-1 + (X 增量与移除)*Y_NX^-1
  O:  以 RQ=CER/OUR 批级中位数与区间检验（O2 守恒已含于机制呼吸项），
      并给出 ∫OUR 与 ∫CER 比值。

常数登记（T7，来自引擎 par + 标准分子式）：
  c_s=600 g/L（par[26]）、c_oil=1000 g/L（par[25]）、c_paa=530 g/L（par[73]/1000）
  Cf(glc)=0.400  (C6H12O6, MW 180.16)
  Cf(oil)=0.773  (triolein C57H104O6, MW 885.4)
  Cf(paa)=0.706  (C8H8O2, MW 136.15)
  Cf(P)=0.575    (青霉素 G 酸 C16H18N2O4S, MW 334.39)
  Cf(X)=0.45     （青霉属生物质典型值，文献级）
  Y_NX=10 gX/gN、Y_NP=80 gP/gN、N_conc_shot=400000 mg/kg、N_conc_oil=20000 mg/L、
  N_conc_paa=150000 mg/L（引擎 par[66..70]）
  NH3 N 分数 0.822（17.031 中 N=14.007）

注意：X 的罐内总量与移除量用 X(t)（X_offline 线性插值）近似——化验 12h 粒度，
滞后 4h 已对齐；误差预算 ±10% 由此承担。
"""
import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from simulate import simulate_open_loop  # noqa
from calibration import calib_params, GOLDEN

# —— 登记常数（T7）——
C_S, C_OIL, C_PAA = 600.0, 1000.0, 530.0    # g/L 各进料底物浓度
CF_GLC, CF_OIL, CF_PAA = 0.400, 0.773, 0.706  # gC/g
CF_P, CF_X = 0.575, 0.45
Y_NX, Y_NP = 10.0, 80.0                      # gX/gN, gP/gN（引擎 par[69] par[70]）
N_SHOT, N_OIL, N_PAA = 400000.0, 20000.0, 150000.0  # mg/kg, mg/L, mg/L
F_N_NH3 = 0.822

# 误差预算（PROBLEM.md §6 流程定标）：C ±20%（常数+插值承担）、N ±35%（进料小通量+浓度量纲）
BUDGET_C, BUDGET_N = 0.20, 0.35


# numpy>=2.0 更名为 trapezoid；本项目运行在 numpy 1.26（仅 trapz），做兼容
_TRAPZ = getattr(np, "trapezoid", None) or np.trapz


def _trapz(hours, values):
    return float(_TRAPZ(values, hours))


def element_balance(v3):
    """从 V3 批数据计算 C/N 闭合与 O 系比指标。返回 dict。"""
    t = v3["time_h"].to_numpy(float)
    Fs = v3["Fs"].to_numpy(float)
    Foil = v3["Foil"].to_numpy(float)
    Fpaa = v3["Fpaa"].to_numpy(float)
    Frem = np.clip(v3["Fremoved"].to_numpy(float), 0, None)
    Frm = v3["Fremoved"].to_numpy(float)
    dt = np.gradient(t)
    msgs = {"assumptions": "c_paa 按 g/L 530；X(t) 由 X_offline 插值 + 4h 滞后对齐；"
                           "CER/OUR 视为 g/L/h 体积速率（R134 修正：×V 后 ×12/44 折碳）"}

    # ---- C 输入 ----
    C_glc = _trapz(t, Fs * C_S * CF_GLC)
    C_oil = _trapz(t, np.clip(Foil, 0, None) * C_OIL * CF_OIL)
    C_paa = _trapz(t, np.clip(Fpaa, 0, None) * C_PAA * CF_PAA)
    C_in = C_glc + C_oil + C_paa
    # Fremoved 为负数排放 → 排故体积 × X(t)
    V_removed = _trapz(t, -np.clip(Frm, None, 0))  # L

    # ---- X(t)（X_offline 插值，含 -4h 滞后对齐）----
    xo_t, xo_v = [], []
    xo = pd.to_numeric(v3.get("X_offline"), errors="coerce")
    for i, val in xo.items():
        if np.isfinite(val):
            xo_t.append(t[i] - 4.0)
            xo_v.append(float(val))
    X_t_of_t = None
    if len(xo_t) >= 2:
        order = np.argsort(xo_t)
        X_t_of_t = lambda tt: np.interp(tt, np.array(xo_t)[order], np.array(xo_v)[order])

    # ---- P 输出（harvest+end 由 yield 口径复用）----
    Ph = _trapz(t, -np.clip(Frm, None, 0) * v3["P"].to_numpy(float))  # g 随排放移除
    Pe = float(v3["V"].iloc[-1] * v3["P"].iloc[-1])
    S_end = float(v3["S"].iloc[-1] * v3["V"].iloc[-1])

    # CER 为体积速率 g/L/h → 乘罐体积还原总量，再按 12/44 折成碳
    CER_g = _trapz(t, np.clip(v3["CER"].to_numpy(float), 0, None) * v3["V"].to_numpy(float))
    OUR_g = _trapz(t, np.clip(v3["OUR"].to_numpy(float), 0, None) * v3["V"].to_numpy(float))
    C_co2 = CER_g * 12.0 / 44.0
    C_prod = (Ph + Pe) * CF_P
    C_biom = 0.0
    C_sub_end = S_end * CF_GLC

    X_net = 0.0
    if X_t_of_t is not None:
        X_end = float(v3["X_offline"].dropna().iloc[-1]) if len(xo_v) else 0.0
        X_rem = _trapz(t, -np.clip(Frm, None, 0) * X_t_of_t(t))  # g X 随排放移除
        X0_mass = (X_t_of_t(t[0]) if np.isfinite(X_t_of_t(t[0])) else 0.0) * float(v3["V"].iloc[0])
        # 准入增长折 C：净增 X 量（当前罐 + 排放 - 初始）中正被生长消耗
        X_net = (float(v3["X_offline"].dropna().iloc[-1]) * float(v3["V"].iloc[-1])
                 + X_rem - X0_mass)
        C_biom = max(X_net, 0.0) * CF_X

    C_out = C_co2 + C_prod + C_biom + C_sub_end
    err_C = (C_out - C_in) / C_in if C_in else np.nan

    # ---- N ----
    NH3g = float(np.nansum(pd.to_numeric(v3["NH3_shots"], errors="coerce").fillna(0)))  # kg
    N_in = NH3g * N_SHOT / 1000.0 * F_N_NH3 \
        + _trapz(t, np.clip(Foil, 0, None)) * N_OIL / 1000.0 \
        + _trapz(t, np.clip(Fpaa, 0, None)) * N_PAA / 1000.0
    N_out = (Ph + Pe) / Y_NP
    if X_t_of_t is not None and X_net > 0:
        N_out += X_net / Y_NX
    err_N = (N_out - N_in) / N_in if N_in else np.nan

    # ---- O（数据侧） ----
    rq = (v3["CER"] / np.maximum(v3["OUR"], 1e-9)).replace([np.inf, -np.inf], np.nan).dropna()
    rq_med = float(rq.median()) if len(rq) else np.nan

    return {
        "C_in_g": C_in, "C_out_g": C_out, "err_C_pct": 100.0 * err_C,
        "C_in_split": {"glc": C_glc, "oil": C_oil, "paa": C_paa},
        "C_out_split": {"co2": C_co2, "P": C_prod, "X": C_biom, "S_end": C_sub_end},
        "N_in_g": N_in, "N_out_g": N_out, "err_N_pct": 100.0 * err_N,
        "CER_g": CER_g, "OUR_g": OUR_g, "RQ_med": rq_med,
        "V_removed_L": V_removed, "note": msgs,
        "pass_C": bool(abs(err_C) <= BUDGET_C), "pass_N": bool(abs(err_N) <= BUDGET_N),
    }


def run(batch_nos, out_path):
    results = []
    for b in batch_nos:
        v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
        try:
            r = element_balance(v3)
        except Exception as e:
            r = {"batch": int(b), "error": str(e)}
        r = {"batch": int(b), **r}
        results.append(r)
        print(f"batch {b:2d}: C_err={r.get('err_C_pct', float('nan')):+.1f}% "
              f"N_err={r.get('err_N_pct', float('nan')):+.1f}% RQ={r.get('RQ_med', float('nan')):.2f} "
              f"C:{r.get('pass_C')} N:{r.get('pass_N')}", flush=True)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    print(f"Saved: {out_path}")
    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", default=",".join(map(str, GOLDEN)))
    ap.add_argument("--out", default="runs/element_balance.json")
    a = ap.parse_args()
    run([int(x) for x in a.batches.split(",")], a.out)
