# -*- coding: utf-8 -*-
"""R145 / D-32：pH 方程逐项预算 —— 尾段 pH 越域究竟是哪一项塌了。

背景（R144 登记）
----------------
D-32：模型尾段 pH 从 t=205 的 6.287 抬到 t=217.4 的 7.442，而全库 100 批实测 pH 上限
只有 6.766（`pH>6.8` 的批 0/100）。R144 已排除"碱流过大"（t>=200 的 Fb 中位 20.3 L/h、
贴上限占比 0%），推断是**产酸项在 P 衰减期过小**，但未做逐项定量。

pH 方程（model.rhs，acidic 分支）
--------------------------------
    dy[6] = gamma1*ph_prod + gamma1*r_p + gamma2*pH_dis + buffer
    ph_prod = r_b0 + r_e1 + r_d4 + r_d1 + m_ph*total_X
    pH_dis  = Fs + Foil + Fb + Fa + F_discharge + Fw
    buffer  = (-B + sqrt(B^2+4e-14))/2 - [H+]
    B       = -( [H+]*V + abc*(Fa - Fb)*step1 ) / (V + (Fb+Fa)*step1)

四项里 gamma1*ph_prod 是"代谢产酸"，buffer 是"补料/加碱后的缓冲平衡"，
gamma2*pH_dis 量级小（gamma2=2.5e-11 对 gamma1=3.25e-6）。

做法（只读，不改引擎）
--------------------
包裹 `simulate.integrate_interval`，拿到每个采样区间的 (t0, y0, inp1, par)；
在每个区间端点调用一次 `model.rhs` 取 dy[6]，再**自行重算** buffer 与 gamma2*pH_dis，
反解出 gamma1*(ph_prod + r_p)：

    acid_total := dy[6] - gamma2*pH_dis - buffer      （acidic 分支，符号已统一为"产酸为正"）

然后用独立重算的 r_p、r_d4、r_d1、m_ph*X 把 ph_prod 再拆一层：

    r_b0+r_e1 := acid_total/gamma1 - r_p - (m_ph*X + r_d4 + r_d1)

自检：四块加起来必须逐位还原 dy[6]（closure 应恒为 0，浮点误差量级）。

用法
----
  python tools/r145_d32_terms.py --batch 92
  python tools/r145_d32_terms.py --batch 92 --tail 180 --stride 5
"""
import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(_ROOT, "candidate", "indpensim", "v0.1"))

import simulate as S  # noqa: E402
import golden_params as gp  # noqa: E402
from model import rhs  # noqa: E402

OUT_DIR = os.path.join(_ROOT, "runs", "p3")

_ODE_KW = ("ode_method", "ode_rtol", "ode_atol", "ode_max_step")


def _rhs_kw(kw):
    return {k: v for k, v in kw.items() if k not in _ODE_KW}


def _inhib_factors(y, inp1, par):
    """复算 inhib_flag=2 下的 DO2/PAA 抑制因子（r_p 用）。"""
    p_std, mean_p = par[3], par[4]
    A_inhib, Xc_DO2, Pc_DO2 = par[45], par[43], par[44]
    r, eps, henrys, o2_in = par[37], par[40], par[35], par[99]
    rho_b = 1100.0 + float(y[3]) + float(y[11]) + float(y[12]) + float(y[13]) + float(y[14])
    h_b = (float(y[4]) / 1000.0) / (np.pi * r * r) * (1 - eps)
    pressure = float(inp1[10])
    pb = 1 + pressure + (rho_b * h_b) * 9.81 * 1e-5
    pt = 1 + pressure
    lmp = (pb - pt) / np.log(pb / pt)
    dostar = (lmp * o2_in) / henrys
    DO2_P = 0.5 * (1 - np.tanh(A_inhib * (Pc_DO2 * dostar - float(y[1]))))
    DO2_X = 0.5 * (1 - np.tanh(A_inhib * (Xc_DO2 * dostar - float(y[1]))))
    paa = float(y[29])
    PAA_P = 0.5 * (1 + np.tanh(-par[79] + paa))
    PAA_X = 0.5 * (1 + np.tanh(par[78] - paa))
    s = float(y[0])
    P_inhib = 2.5 * p_std * ((p_std * np.sqrt(2 * np.pi)) ** -1
                             * np.exp(-0.5 * ((s - mean_p) / p_std) ** 2))
    return P_inhib, DO2_P, DO2_X, PAA_P, PAA_X


def ph_budget(t, y, inp1, par, **rkw):
    """在状态 y 上重算 pH 方程各分项。"""
    dy = rhs(t, y, inp1, par, **rkw)

    V = float(y[4])
    y6 = float(y[6])
    Fa, Fb, step1 = float(inp1[7]), float(inp1[6]), float(inp1[8])
    Fw = max(float(inp1[9]), 0.0)
    abc, gamma1, gamma2, m_ph = par[61], par[62], par[63], par[64]
    mu_h, mu_a, mu_diff = par[19], par[6], par[7]
    beta_1, K_diff_L = par[8], par[11]

    ph = float(-np.log10(max(y6, 1e-12)))
    basic = ph >= 7.0

    if basic:
        ca, cb, y7_use = -abc, abc, 1e-14 / y6 - y6
    else:
        ca, cb, y7_use = abc, -abc, y6
    B = -((y7_use * V + ca * Fa * step1 + cb * Fb * step1) / (V + Fb * step1 + Fa * step1))
    root = np.sqrt(B * B + 4e-14)
    buf = ((-B - root) / 2 if basic else (-B + root) / 2) - y7_use

    pH_dis = float(inp1[1]) + float(inp1[14]) + Fb + Fa + float(inp1[12]) + Fw
    dis_term = (-gamma2 * pH_dis) if basic else (gamma2 * pH_dis)

    dy6 = float(dy[6])
    acid_total = dy6 - dis_term - buf          # = ±gamma1*(ph_prod + r_p)
    signed = -acid_total if basic else acid_total

    a_0, a_1, a_3 = float(y[11]), float(y[12]), float(y[13])
    total_X = a_0 + a_1 + a_3 + float(y[14])
    s = float(y[0])
    den = a_1 + a_3 + float(y[14]) + float(y[15])
    A_t1 = a_0 / den if den else 0.0
    K_diff = max(par[10] - A_t1 * beta_1, K_diff_L)
    r_d1 = mu_diff * a_0 / (K_diff + s) if (K_diff + s) else 0.0
    r_d4 = mu_a * a_3
    m_ph_term = m_ph * total_X

    P_inhib, DO2_P, _DO2_X, PAA_P, _PAA_X = _inhib_factors(y, inp1, par)
    mu_p_eff = par[0] + float(inp1[17])          # dist_mup
    # mu_h 按抑制分支取：inhib=0 -> 0.003；inhib=1/2 -> k4（inhib=2 再乘 par[18]）。
    # R145 修正：原实现直接取 par[19]，而 inhib=2（黄金集默认）下 par[19] **不被使用**，
    # 有限差分 d(dy6)/d(par[19]) = 0 已证。正确取值为 k4 = exp(B1+B2·pH+B3·T+B4·pH²+B5·T²)。
    B1, B2, B3, B4, B5 = par[80], par[81], par[82], par[83], par[84]
    k4 = float(np.exp((B1 + B2 * ph + B3 * float(y[7]) + B4 * ph ** 2) + B5 * float(y[7]) ** 2))
    if int(inp1[0]) == 0:
        mu_h_eff = 0.003
    elif int(inp1[0]) == 1:
        mu_h_eff = k4
    else:
        mu_h_eff = k4 * par[18]
    r_p = mu_p_eff * a_1 / 2.0 * P_inhib * DO2_P * PAA_P - mu_h_eff * float(y[3])

    ph_prod = signed / gamma1 - r_p
    s_term = ph_prod - (m_ph_term + r_d4 + r_d1)

    return {
        "t": float(t), "ph": ph, "basic": bool(basic), "y6": y6, "dy6": dy6,
        "B": float(B), "buf_term": float(buf), "dis_term": float(dis_term),
        "acid_term": float(signed),
        "ph_prod_plus_rp": float(signed / gamma1),
        "ph_prod": float(ph_prod), "r_p": float(r_p),
        "m_ph_X": float(m_ph_term), "r_d4": float(r_d4), "r_d1": float(r_d1),
        "s_term": float(s_term),
        "s": s, "X": total_X, "P": float(y[3]), "V": V,
        "Fa": Fa, "Fb": Fb, "Fs": float(inp1[1]), "Fw": Fw,
        "Foil": float(inp1[14]), "Fdis": float(inp1[12]),
        "P_inhib": float(P_inhib), "DO2_P": float(DO2_P), "PAA_P": float(PAA_P),
        "pH_dis": float(pH_dis),
        "closure": float(dy6 - (dis_term + buf + acid_total)),
    }


def run(batch, stride=1):
    """包裹 integrate_interval，逐区间在起点算pH预算。"""
    orig = S.integrate_interval
    recs = []

    def wrapped(t0, y0, inp1, par, **kw):
        y1 = orig(t0, y0, inp1, par, **kw)
        recs.append((float(t0), np.array(y0, dtype=float).copy(),
                     np.array(inp1, dtype=float).copy(),
                     np.array(par, dtype=float).copy(), dict(kw)))
        return y1

    S.integrate_interval = wrapped
    try:
        sim, v3 = S.simulate_open_loop(batch, gp.params_for(batch))
    finally:
        S.integrate_interval = orig

    t_v3 = v3["time_h"].to_numpy(float)
    ph_v3 = pd.to_numeric(v3["pH"], errors="coerce").to_numpy(float)

    rows = []
    for i, (t0, y0, inp1, par, kw) in enumerate(recs):
        if i % stride:
            continue
        b = ph_budget(t0, y0, inp1, par, **_rhs_kw(kw))
        b["ph_data"] = float(np.interp(b["t"], t_v3, ph_v3))
        rows.append(b)
    return rows, sim, v3


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=92)
    ap.add_argument("--stride", type=int, default=1)
    ap.add_argument("--tail", type=float, default=150.0, help="打印该时刻之后的预算表")
    ap.add_argument("--no-write", action="store_true")
    args = ap.parse_args()

    rows, sim, v3 = run(args.batch, stride=args.stride)
    if not rows:
        print("无记录")
        return

    cl = max(abs(r["closure"]) for r in rows)
    print(f"批 {args.batch}：{len(rows)} 个预算点；自洽残差 max|closure| = {cl:.3e}")
    print(f"  模型 pH 末 = {rows[-1]['ph']:.3f}，数据 pH 末 = {rows[-1]['ph_data']:.3f}")
    print(f"  basic 分支命中点数 = {sum(r['basic'] for r in rows)}")

    print(f"\n{'t':>7} {'pH':>7} {'pHdat':>6} {'S':>7} {'X':>6} {'P':>6} "
          f"{'acid':>9} {'buf':>9} {'dis':>9} {'b0+e1':>8} {'m_phX':>8} "
          f"{'r_d1':>8} {'r_d4':>8} {'r_p':>8} {'Fb':>5}")
    for r in rows:
        if r["t"] < args.tail:
            continue
        print(f"{r['t']:>7.1f} {r['ph']:>7.3f} {r['ph_data']:>6.2f} {r['s']:>7.3f} "
              f"{r['X']:>6.2f} {r['P']:>6.2f} {r['acid_term']:>9.2e} "
              f"{r['buf_term']:>9.2e} {r['dis_term']:>9.2e} {r['s_term']:>8.4f} "
              f"{r['m_ph_X']:>8.4f} {r['r_d1']:>8.2e} {r['r_d4']:>8.2e} "
              f"{r['r_p']:>8.4f} {r['Fb']:>5.1f}")

    if not args.no_write:
        os.makedirs(OUT_DIR, exist_ok=True)
        out = os.path.join(OUT_DIR, f"r145_d32_terms_b{args.batch}.json")
        json.dump({"batch": args.batch, "closure_max": cl, "rows": rows},
                  open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"\n落盘 {out}")


if __name__ == "__main__":
    main()
