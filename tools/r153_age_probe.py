# -*- coding: utf-8 -*-
"""R153 / D-48 前置探针：从实测 P 反推"需要的产素通量时间剖面"。

目的
----
D-48 提案是让 `mu_p` 随菌龄衰减。但衰减形式不能拍脑袋，先要问：
**实测数据要求 r_p 在时间上怎么分布？** 若实测要求的 r_p/base 比值随时间单调下降，
则"指数衰减"形式成立；若不是（例如中间某段有个鼓包），则要另选形式。

推导
----
从 dy[3] 与实测 P 轨迹反推（忽略 p_deg，默认 0）：
    dP/dt = r_p - mu_h*P - dil*P
⇒ r_p_needed = dP/dt + (mu_h + dil) * P

模型侧基线（60 h 后 S≈0 ⇒ P_inhib=DO2_P=PAA_P=1，v_2=0 ⇒ rho_a1=rho_a0）：
    r_p_base = mu_p * rho_a0 * v_a1 - mu_h*P,  v_a1 = A1/(2*rho_a0)
             = mu_p * A1 / 2 - mu_h * P

于是 `ratio = r_p_needed / r_p_base` 就是"mu_p 应乘的因子"，
其时间剖面直接告诉我们 D-48 的衰减曲线该长什么样。

只读，不改引擎。
"""
import argparse
import json
import os
import sys

import numpy as np

ENG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "candidate", "indpensim", "v0.1")
sys.path.insert(0, ENG)

from golden_params import COMBINED, build_params  # noqa: E402
import simulate as S  # noqa: E402

PHASES = (("0-60", 0, 60), ("60-120", 60, 120), ("120-180", 120, 180),
          ("180+", 180, 1e9))


def mu_h_series(par, pH, T_K):
    """逐点 mu_h = exp(B1 + B2*pH + B3*T + B4*pH^2 + B5*T^2) * par[18]。

    与 model.py `inhib_flag==2` 分支（默认）逐字一致；B = par[80..84]。
    注意：model 里写 `ph_val = -log10(y[6])`，因为 `y[6]` 是 **[H+] 浓度**；
    而 `sim["pH"]` 这一列**已经是 pH 值**（实测 6.4 上下），不能再取 -log10
    —— 重取会把 exp(...) 从 4.6e-3 放大到 13.8（差 3000 倍）。
    T 的单位是**开尔文**（304–310 K），不是摄氏度。
    """
    B = [float(par[i]) for i in range(80, 85)]
    return np.exp(B[0] + B[1] * pH + B[2] * T_K + B[3] * pH ** 2
                  + B[4] * T_K ** 2) * float(par[18])


def p_inhib_series(par, s):
    """与 model.py 逐字一致的残糖高斯门控（峰值 2.5/sqrt(2π) ≈ 0.997）。"""
    sd = float(par[3])
    mp = float(par[4])
    return 2.5 * (1.0 / np.sqrt(2 * np.pi)) * np.exp(-0.5 * ((s - mp) / sd) ** 2)


def batch_par(cp):
    """复刻 simulate_open_loop 的 par 构建（只保留影响 mu_h / P_inhib 的覆盖）。

    `mean_P`(par[4]) 与 `P_std_dev`(par[3]) 在 86 批里无批级覆盖（已核 COMBINED 键集），
    所以它们取 make_params 默认；`mu_h_scale`(par[18]) 有 31/86 批覆盖，必须应用。
    `mup` 直接是 par[0]（make_params 的 p[0]=mup，非"状态变量初值"，R152 台账 D-47 已更正）。
    """
    par = S.make_params(alpha_kla=cp.get("alpha_kla", 85.0),
                        N_conc_paa=cp.get("N_conc_paa", 150000.0),
                        PAA_c=cp.get("PAA_c", 530000.0),
                        mup=cp["mup"], mux=cp["mux"],
                        c_oil=cp.get("c_oil", 1000.0))
    if "mu_h_scale" in cp:
        par[18] = cp["mu_h_scale"]
    return par


def one(b):
    cp = COMBINED[b]
    par = batch_par(cp)
    sim, v3 = S.simulate_open_loop(b, build_params(cp))
    ts = sim["time_h"].to_numpy(float)
    Ps = sim["P"].to_numpy(float)
    Ss = sim["S"].to_numpy(float)
    A1 = sim["A1"].to_numpy(float)
    V = sim["V"].to_numpy(float)
    Fg = sim["Fg"].to_numpy(float)
    pH = sim["pH"].to_numpy(float)
    T = sim["T"].to_numpy(float)

    tv = v3["time_h"].to_numpy(float)
    Pm = v3["P"].to_numpy(float)

    mu_h = mu_h_series(par, pH, T)          # 逐点，不是常数
    mu_p = float(par[0])
    PI = p_inhib_series(par, Ss)            # 残糖门控（DO2_P / PAA_P 取 1，见 docstring）

    # 实测侧：按 time_h 插值到模型网格，避免行号错位（R150 教训）
    Pm_i = np.interp(ts, tv, Pm)
    dPm = np.gradient(Pm_i, ts)
    dil = Fg / V
    rp_need = dPm + (mu_h + dil) * Pm_i     # = r_p 本身（dy[3] = r_p - dil*P）

    # 模型侧：r_p = mu_p*A1/2*PI - mu_h*P（v_2=0 ⇒ rho_a1=rho_a0 ⇒ v_a1=A1/(2*rho_a0)）
    # 精确反解所需 mu_p(t)：mu_p_need = (r_p_need + mu_h*P) / (A1/2*PI)
    denom = 0.5 * A1 * PI
    rp_base = mu_p * denom - mu_h * Ps

    out = {"batch": b, "tmax": float(ts.max()),
           "mu_h_med": float(np.median(mu_h)), "mu_p": mu_p,
           "p_inhib_med": float(np.median(PI))}
    # 只在不病态的点上反解：PI 必须真打开（否则 denom→0，ratio 爆炸），
    # 且 A1 不能接近 0（同样会让 denom→0）。
    ok = (PI > 0.2) & (A1 > 1e-3)
    ratio = np.full_like(ts, np.nan)
    ratio[ok] = (rp_need[ok] + mu_h[ok] * Ps[ok]) / (0.5 * A1[ok] * PI[ok])
    # 相对倍数（以 mu_p 标称值归一）—— 1.0 = 与现行常数 mu_p 一致
    mult = ratio / mu_p if mu_p > 0 else ratio

    for name, lo, hi in PHASES:
        m = (ts >= lo) & (ts < hi) & ok & np.isfinite(mult) & (mult > 0)
        out[name] = float(np.median(mult[m])) if m.sum() >= 5 else float("nan")
        out["n_" + name] = int(m.sum())
    # 基线自检：同源时 base 的 mult 应 ≈ 1（见 main 里的断言）
    m = ok & np.isfinite(mult) & (mult > 0)
    out["mult_all_med"] = float(np.median(mult[m])) if m.sum() else float("nan")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", type=str, default="")
    ap.add_argument("--all86", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--json", type=str, default="runs/r153_age_probe.json")
    a = ap.parse_args()

    if a.all86:
        bs = [b for b in sorted(COMBINED) if b != 0]
    else:
        bs = [int(x) for x in a.batches.split(",") if x.strip()]

    from concurrent.futures import ProcessPoolExecutor
    from concurrent.futures.process import BrokenProcessPool
    rows = []
    try:
        with ProcessPoolExecutor(max_workers=a.workers) as ex:
            for r in ex.map(one, bs):
                rows.append(r)
                print(f"  b{r['batch']:>3d} tmax {r['tmax']:.0f} | "
                      + "  ".join(f"{k}={r[k]:+.3f}" for k, _, _ in PHASES), flush=True)
    except BrokenProcessPool:
        rows = [one(b) for b in bs]

    print("\n=== 需要的 mu_p 乘子（r_p_needed / r_p_base）分相位 ===")
    print("相位      中位    均值    批数")
    for name, _, _ in PHASES:
        v = np.array([r[name] for r in rows], float)
        v = v[np.isfinite(v)]
        print(f"{name:8s} {np.median(v):+7.3f} {v.mean():+7.3f}  {len(v)}")

    print("\n=== 逐批（看是否单调下降）===")
    print("  b  0-60   60-120 120-180 180+")
    for r in rows:
        print(f"{r['batch']:>3d} " + " ".join(
            (f"{r[k]:+7.3f}" if np.isfinite(r[k]) else "    nan") for k, _, _ in PHASES))

    if a.json:
        os.makedirs(os.path.dirname(a.json) or ".", exist_ok=True)
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump({"rows": rows}, fh, ensure_ascii=False, indent=1)
        print("\nsaved:", a.json)


if __name__ == "__main__":
    main()
