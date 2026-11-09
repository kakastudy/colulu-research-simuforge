# -*- coding: utf-8 -*-
"""r140_n_balance.py — N 元素平衡的口径诊断与收口（GOAL §4.3 唯一破线项）。

背景
----
`conservation_metrics.element_balance` 给出的 N 平衡中位 −15.8%（10/12，b36/b91 超 35%）。
R138 曾判「`N_conc_paa=150000` 是 MATLAB 原值，PAA 过量供给致 N 不守恒」，但那是**归因**，
不是**口径核验**。本工具只做一件事：把 N 账的每一项摊开，逐项对比 MATLAB 定义，找漏项。

三个已确认的口径疑点
--------------------
1) **单位方向错**（本次新发现）
   MATLAB `Parameter_list.m:76-77`：
     `Y_NX = 10;  % mg of N2 per gram of X DW`   → 10 mgN/gX = 0.010 gN/gX
     `Y_NP = 80;  % mg of N2 per gram of X DW`   → 80 mgN/gP = 0.080 gN/gP
   现实现写的是 `P/Y_NP + X/Y_NX`，即把二者当 **gP/gN、gX/gN**（取倒数方向）：
     P 项 = P/80     = 0.0125 gN/gP   ← 比正确值小 6.4 倍
     X 项 = X/10     = 0.100  gN/gX   ← 比正确值大 10 倍
   两项误差方向相反、量级相近，**总和凑巧接近**（b8：3.52e5 vs 正确 3.51e5）。
   这正是 R137「错误的正確」的第二次出现：结论数字对，分解全错。

2) **漏维持消耗**（本次新发现）
   MATLAB `indpensim_ode.m:568` 的 N 状态有三项消耗：
     `X_C_nitrogen + P_C_nitrogen - m_N*total_X`
   现实现只做了前两项，**`m_N=0.03` 的维持项整项漏掉**。
   量级：b8 的 ∫X_mass dt ≈ 3e6 gX·h，即便按 0.001/h 计也有 3e3 g N，按 0.03/h 计可达 9e4 g N
   （N_in 仅 3.8e5 g）——足以翻转符号。

3) **N_in 的氮源是模型虚构**
   `N_conc_paa=150000 mg/L`、`N_conc_oil=20000 mg/L` 都来自 `Parameter_list.m`，
   而苯乙酸（C8H8O2）与三油酸甘油酯（C57H104O6）**本身不含氮**。
   这两个常数是为了让模型内部 N 状态不崩而设的"隐藏氮源"，无实验依据。
   ⇒ 外部 N 账的天花板由它们决定，与实现无关。

口径档位（本工具逐档计算）
--------------------------
  A. 现行实现            N_out = P/Y_NP + X/Y_NX
  B. 修正单位            N_out = P·0.080 + X·0.010
  C. B + 维持（0.03/h）  += m_N · ∫X_mass dt
  D. B + 维持（0.001/h） += 同上，m_N 取 1/30
  E. 真实化学计量         N_out = P·0.08378(青霉素G) + X·0.090(生物质)
  F. E + 维持（0.001/h）

用法
----
  python tools/r140_n_balance.py                 # 12 批 GOLDEN
  python tools/r140_n_balance.py --all86
  python tools/r140_n_balance.py --all86 --out runs/p3/r140_n_balance.json
"""
import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1"))
from conservation_metrics import (  # noqa: E402
    CF_P, CF_X, C_PAA, C_OIL, C_S, CF_GLC, CF_OIL, CF_PAA,
    N_SHOT, N_OIL, N_PAA, F_N_NH3, Y_NX, Y_NP, BUDGET_N, _trapz,
)
from calibration import GOLDEN  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "runs", "p3", "r140_n_balance.json")

M_N = 0.03          # MATLAB par(73)，单位本身存疑（见口径 C/D 对比）
N_FRAC_P = 28.014 / 334.39   # 青霉素 G 含氮分数 8.378%
N_FRAC_X = 0.090             # 生物质含氮 9%（文献 8–12%）


def n_terms(v3):
    """返回该批的 N 账各项（不做判断，只摊开）。"""
    t = v3["time_h"].to_numpy(float)
    V = v3["V"].to_numpy(float)
    Foil = np.clip(v3["Foil"].to_numpy(float), 0, None)
    Fpaa = np.clip(v3["Fpaa"].to_numpy(float), 0, None)
    Frm = v3["Fremoved"].to_numpy(float)

    # X(t)：X_offline 插值，-4h 滞后对齐（与 conservation_metrics 同口径）
    xo_t, xo_v = [], []
    xo = pd.to_numeric(v3.get("X_offline"), errors="coerce")
    for i, val in xo.items():
        if np.isfinite(val):
            xo_t.append(t[i] - 4.0)
            xo_v.append(float(val))
    if len(xo_t) < 2:
        raise ValueError("X_offline 不足两点")
    order = np.argsort(xo_t)
    X_of = lambda tt: np.interp(tt, np.array(xo_t)[order], np.array(xo_v)[order])

    X_mass = X_of(t) * V                      # g
    I_X = _trapz(t, X_mass)                   # gX·h

    # 产量（与 conservation_metrics 口径一致）
    Ph = _trapz(t, -np.clip(Frm, None, 0) * v3["P"].to_numpy(float))
    Pe = float(v3["V"].iloc[-1] * v3["P"].iloc[-1])
    P_tot = Ph + Pe

    # X 净增（罐内 + 随排放移除 − 初始）
    X_rem = _trapz(t, -np.clip(Frm, None, 0) * X_of(t))
    X_end = float(xo.dropna().iloc[-1]) * float(V[-1])
    X0 = X_of(t[0]) * float(V[0])
    X_net = max(X_end + X_rem - X0, 0.0)

    # N_in 三项
    NH3g = float(np.nansum(pd.to_numeric(v3["NH3_shots"], errors="coerce").fillna(0)))
    n_nh3 = NH3g * N_SHOT / 1000.0 * F_N_NH3
    n_oil = _trapz(t, Foil) * N_OIL / 1000.0
    n_paa = _trapz(t, Fpaa) * N_PAA / 1000.0
    N_in = n_nh3 + n_oil + n_paa

    return dict(N_in=N_in, n_nh3=n_nh3, n_oil=n_oil, n_paa=n_paa,
                P_tot=P_tot, X_net=X_net, I_X=I_X, V_removed=_trapz(t, -np.clip(Frm, None, 0)))


def modes(r):
    """六种口径下的 N_out（g N）。"""
    P, X, I = r["P_tot"], r["X_net"], r["I_X"]
    return {
        "A_现行": P / Y_NP + X / Y_NX,
        "B_修单位": P * Y_NP / 1000.0 + X * Y_NX / 1000.0,
        "C_B+维持0.03": P * Y_NP / 1000.0 + X * Y_NX / 1000.0 + M_N * I,
        "D_B+维持0.001": P * Y_NP / 1000.0 + X * Y_NX / 1000.0 + (M_N / 30.0) * I,
        "E_真实计量": P * N_FRAC_P + X * N_FRAC_X,
        "F_E+维持0.001": P * N_FRAC_P + X * N_FRAC_X + (M_N / 30.0) * I,
    }


def full_account(b):
    """完整 N 账（含 N 池变化与随罐移除），需要跑仿真拿内部 NH3 通道。

    恒等式：N_in = N_products + N_biomass + N_maintenance + (N_pool_end − N_pool_0) + N_removed
    重排：  N_consumed = N_in − ΔN_pool − N_removed
    若实现正确，`N_consumed` 应等于由 P/X 产量按化学计量算出的消耗。
    """
    from simulate import simulate_open_loop  # 局部导入，避免纯数据模式也加载 scipy
    from golden_params import params_for

    v3 = pd.read_csv(os.path.join(HERE, "data", "processed", "batches", f"batch_{b:02d}.csv"))
    # 必须用逐批标定参数：86 批基线里 Y_NP=40 / Y_NX=25 与名义值 80/10 不同，
    # 混用会让"模型常数口径"失去意义。
    pr = params_for(b)
    out, _ = simulate_open_loop(b, pr)
    y_nx_b = float(pr.get("Y_NX", Y_NX))
    y_np_b = float(pr.get("Y_NP", Y_NP))
    t = out["time_h"].to_numpy(float)
    V = out["V"].to_numpy(float)
    NH3 = out["NH3"].to_numpy(float)                    # mg/L
    Frm = out["Fremoved"].to_numpy(float)

    n_pool0 = NH3[0] * V[0] / 1000.0                    # g N
    n_poolE = NH3[-1] * V[-1] / 1000.0
    n_removed = _trapz(t, -np.clip(Frm, None, 0) * NH3) / 1000.0

    r = n_terms(v3)
    n_in = r["N_in"]
    # 输入 − 存量增加 − 随液移出 = 被反应消耗（应为正）
    n_consumed = n_in - (n_poolE - n_pool0) - n_removed

    P, X = r["P_tot"], r["X_net"]
    cons_model = P * y_np_b / 1000.0 + X * y_nx_b / 1000.0
    cons_real = P * N_FRAC_P + X * N_FRAC_X
    return {
        "b": int(b),
        "N_in": n_in, "pool0": n_pool0, "poolE": n_poolE, "d_pool": n_poolE - n_pool0,
        "N_removed": n_removed, "N_consumed": n_consumed,
        "NH3_0": float(NH3[0]), "NH3_E": float(NH3[-1]),
        "Y_NP_b": y_np_b, "Y_NX_b": y_nx_b,
        "cons_model": cons_model,      # 逐批标定常数口径
        "cons_real": cons_real,        # 真实化学计量
        "P_tot": P, "X_net": X,
        "err_model": 100.0 * (n_consumed - cons_model) / cons_model if cons_model else float("nan"),
        "err_real": 100.0 * (n_consumed - cons_real) / cons_real if cons_real else float("nan"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all86", action="store_true")
    ap.add_argument("--batches", default=None)
    ap.add_argument("--with-pool", action="store_true",
                    help="跑仿真拿内部 NH3，做含 N 池变化与移除的完整账")
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()

    if a.all86:
        sys.path.insert(0, os.path.join(HERE, "tools"))
        from golden_params import GOLDEN_ALL
        batches = list(GOLDEN_ALL)
    elif a.batches:
        batches = [int(x) for x in a.batches.split(",")]
    else:
        batches = list(GOLDEN)

    rows = []
    for b in batches:
        v3 = pd.read_csv(os.path.join(HERE, "data", "processed", "batches", f"batch_{b:02d}.csv"))
        try:
            r = n_terms(v3)
        except Exception as e:
            print(f"batch {b:2d}: ERROR {e}", flush=True)
            continue
        md = modes(r)
        row = {"b": int(b), **{k: float(v) for k, v in r.items()}}
        for k, v in md.items():
            row[f"err_{k}"] = 100.0 * (v - r["N_in"]) / r["N_in"]
            row[f"out_{k}"] = float(v)
        rows.append(row)
        print(f"b{b:2d} N_in={r['N_in']/1e3:7.1f}k  "
              + "  ".join(f"{k}={row['err_'+k]:+6.1f}%" for k in md), flush=True)

    if a.with_pool:
        print("\n=== 完整账（含 N 池变化与随罐移除，需仿真内部 NH3）===")
        print(f"{'批':>4s}{'NH3初末':>15s}{'N_in':>9s}{'Δ池':>9s}{'移除':>8s}"
              f"{'实耗':>9s}{'模型常数':>9s}{'err':>8s}{'真实计量':>9s}{'err':>8s}")
        pool_rows = []
        for b in batches:
            try:
                fr = full_account(b)
            except Exception as e:
                print(f"b{b:>3d}  ERROR {e}", flush=True)
                continue
            pool_rows.append(fr)
            print(f"{b:4d}{fr['NH3_0']:7.0f}→{fr['NH3_E']:6.0f}"
                  f"{fr['N_in']/1e3:9.0f}{fr['d_pool']/1e3:+9.0f}{fr['N_removed']/1e3:8.0f}"
                  f"{fr['N_consumed']/1e3:9.0f}{fr['cons_model']/1e3:9.0f}{fr['err_model']:+7.0f}%"
                  f"{fr['cons_real']/1e3:9.0f}{fr['err_real']:+7.0f}%", flush=True)
        if pool_rows:
            em = np.array([r["err_model"] for r in pool_rows])
            er = np.array([r["err_real"] for r in pool_rows])
            print(f"\n  中位：模型常数口径 {np.median(em):+.0f}% / 真实计量口径 {np.median(er):+.0f}%"
                  f"（n={len(pool_rows)}）")
            print("  解读：误差 = (实耗 − 化学计量消耗)/化学计量消耗。"
                  "模型口径不为零 ⇒ 模型 N 状态本身不守恒；真实口径不为零 ⇒ 氮源常数与真实分子式不符。")
            os.makedirs(os.path.dirname(a.out), exist_ok=True)
            base = a.out[:-5] if a.out.endswith(".json") else a.out
            json.dump({"meta": {"note": "含 N 池与移除的完整账；d_pool=末−初，N_consumed=N_in−Δ池−移除"},
                       "rows": pool_rows},
                      open(base + "_pool.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            print(f"  已写入 {base}_pool.json")

    if not rows:
        print("无有效批次")
        return

    print("\n=== 86 批汇总（N 误差中位数 / 达标批数（|err|≤35%）/ 最坏）===")
    print(f"{'口径':<16s}{'中位':>9s}{'达标':>8s}{'p90|err|':>10s}{'最坏':>9s}")
    keys = list(modes(rows[0]).keys())
    summ = {}
    for k in keys:
        e = np.array([r[f"err_{k}"] for r in rows])
        ok = int(np.sum(np.abs(e) <= 100 * BUDGET_N))
        summ[k] = dict(median=float(np.median(e)), ok=ok, n=len(rows),
                       p90=float(np.percentile(np.abs(e), 90)), worst=float(e[np.argmax(np.abs(e))]))
        print(f"{k:<16s}{np.median(e):+8.1f}%{ok:5d}/{len(rows):<3d}"
              f"{np.percentile(np.abs(e),90):9.1f}%{e[np.argmax(np.abs(e))]:+8.1f}%")

    print("\n=== N_in 结构（中位，g）===")
    tot = np.median([r["N_in"] for r in rows])
    for k in ("n_nh3", "n_oil", "n_paa"):
        v = np.median([r[k] for r in rows])
        print(f"  {k:<8s}{v:10.0f}  ({100*v/tot:5.1f}%)")

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump({"meta": {"n": len(rows), "m_N": M_N, "n_frac_p": N_FRAC_P, "n_frac_x": N_FRAC_X,
                        "note": "A=现行实现 B=修正mg单位 C=B+m_N0.03 D=B+m_N0.001 "
                                "E=真实化学计量 F=E+m_N0.001"},
               "summary": summ, "rows": rows},
              open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n已写入 {a.out}")


if __name__ == "__main__":
    main()
