# -*- coding: utf-8 -*-
"""R135 T6: b55 / b91 产量归因 —— 把偏差拆成「底物供给 / 产率上限 / 抑制项」三份。

为什么做：b91（−30% 量级）与 b55（红线内）长期被归为"红线内无解"（docs/deepening_plan.md），
但"无解"只是结论，"为什么无解"从未拆开。归因与调参是两件事：
  - **归因**：用**反事实干预**（只改一个机制维度，看产量动多少）量化各维度的贡献量级；
  - **调参**：去拟合参数把误差消掉 —— 本项目原则是「C 类只登记不硬凑」，不做。

方法（反事实弹性，不拟合）：
  以 calib_params(b) 为基线，对三个**机制上互斥**的维度各做一次 +10% 干预：
    A 产率上限  : mu_p × 1.10            （比产素速率上限，与生物量无关）
    B 底物供给  : mv_scales{Fs:1.10}      （进料碳源 +10%，喂得更足）
    C1 抑制(PAA): P_crit_PAA = -1e3      （tanh 饱和 → PAA 抑制项恒 1，即"关掉"）
    C2 抑制(DO2): P_crit_DO2 = -1e3      （同上）
  再跑一次 A+B+C1+C2 全叠加，检验可加性（不假设线性）。
  每条产出**弹性**：Δerr_pp / +10% 干预。弹性接近 0 = 该维度**不是**这台批的瓶颈。

同时记录状态诊断（不改参数，只看基线解）：
  S 谷值与其耗尽时间占比、PAA 峰值 vs P_crit_PAA(200)、DO2 谷值、
  X_end/X_v3、P_end/P_v3 —— 用来交叉验证弹性方向是否与物理解释一致。

判据（先登记）：
  · 某维度弹性 ≥ 2 pp/10% 且方向为"改善" → 该维度是**瓶颈候选**
  · 全部弹性 < 1 pp/10% → 判为**结构性**（瓶颈不在这些维度，需改 ODE，V1+）
  · 叠加后仍不达标（|err|<5%）→ 记"多维同时欠账"，不做单点归因

用法：
  python tools/r135_b55_b91_attrib.py
  python tools/r135_b55_b91_attrib.py --batches 91,55,36,8
"""
import argparse
import json
import os
import sys
from statistics import median

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))

from simulate import simulate_open_loop, yield_metrics  # noqa: E402
from calibration import calib_params  # noqa: E402
from golden_params import COMBINED  # noqa: E402

UPLIFT = 1.10


def _yield_err(sim, v3):
    return float(yield_metrics(sim, v3)["rel_err_total"])


def _diag(sim, v3):
    """基线解的状态诊断（不参与归因，只作物理交叉验证）。"""
    S = sim["S"].to_numpy(float)
    t = sim["time_h"].to_numpy(float)
    xo = pd.to_numeric(v3["X_offline"], errors="coerce").dropna()
    x_sim_end = float(sim["A0"].iloc[-1] + sim["A1"].iloc[-1] + sim["A3"].iloc[-1] + sim["A4"].iloc[-1]) \
        if "A0" in sim.columns else float("nan")
    return {
        "S_min": round(float(np.min(S)), 3),
        "S_end": round(float(S[-1]), 3),
        "frac_S_below_1": round(float(np.mean(S < 1.0)), 3),
        "S_exhaust_h": (round(float(t[np.argmax(S < 0.5)]), 1) if np.any(S < 0.5) else None),
        "PAA_max": round(float(sim["PAA"].max()), 1),
        "PAA_end": round(float(sim["PAA"].iloc[-1]), 1),
        "PAA_above_200_frac": round(float(np.mean(sim["PAA"].to_numpy(float) > 200.0)), 3),
        "DO2_min": round(float(sim["DO2"].min()), 2),
        "DO2_end": round(float(sim["DO2"].iloc[-1]), 2),
        "P_end": round(float(sim["P"].iloc[-1]), 1),
        "X_end_sim": round(x_sim_end, 2),
        "X_end_v3": (round(float(xo.iloc[-1]), 2) if len(xo) else None),
        "X_ratio_end": (round(x_sim_end / float(xo.iloc[-1]), 3) if len(xo) and xo.iloc[-1] > 1e-9 else None),
    }


def _verdict(err0_pct, el, probes):
    """按弹性谱下结论。

    判据修正记录（首版错在哪）：首版把"弹性 >=2pp"直接叫"瓶颈候选"，这是把
    **敏感性**当成了**归因**。对一台已经在红线内的批，"Fs +10% 让产量掉 96pp"
    不代表底物供给是残差的原因，只代表**产量对进料极度敏感**（贴着分岔边界）。
    正确的两件事必须分开说：
      - 抑制项 delta ~ 0  -> 该机制**未激活**，可从解释里**排除**（硬证据）；
      - 产率/进料 delta 很大 -> **高杠杆**，但方向一错就过冲，**不可用于修补**。
    """
    flags = []
    d_paa = abs(el["C1_paa_inhib_off"])
    d_do2 = abs(el["C2_do2_inhib_off"])
    lev_a = abs(el["A_yield_ceiling_mup_x110"])
    lev_b = abs(el["B_substrate_feed_x110"])
    lev = max(lev_a, lev_b)
    within = abs(err0_pct) <= 5.0

    if d_paa < 0.5:
        flags.append("PAA 抑制项未激活(delta~0)")
    if d_do2 < 0.5:
        flags.append("DO2 抑制项未激活(delta~0)")
    if within:
        flags.append("落点在 ±5% 红线内")
    if lev >= 20.0:
        flags.append(f"高产率杠杆 {lev:.0f}pp/10% -> 近分岔，不可微调")

    if within and lev >= 20.0:
        verdict = "redline_near_bifurcation"
        why = (f"基线 {err0_pct:+.2f}% 已在红线内，但 10% 级进料/产率变化即可把产量推出 ±20%"
               f"（A {el['A_yield_ceiling_mup_x110']:+.1f}pp / B {el['B_substrate_feed_x110']:+.1f}pp）"
               f" -> 落点贴着分岔边界，只能评估不能微调")
    elif within:
        verdict = "redline_clean"
        why = (f"基线 {err0_pct:+.2f}%，产率/进料弹性仅 {lev:.1f}pp/10%（远离分岔），"
               f"抑制项 delta~0 -> 该批无未解释的产量残差")
    elif lev >= 20.0:
        verdict = "high_leverage"
        why = (f"基线 {err0_pct:+.2f}% 超红线，产率/进料杠杆 {lev:.0f}pp/10% -> "
               f"可移动但会跨分岔，属结构性不可修补（强行凑参的路径已封）")
    else:
        verdict = "structural"
        why = (f"基线 {err0_pct:+.2f}%，三个维度弹性全部 <20pp（产率 {lev_a:.1f} / 进料 {lev_b:.1f} / "
               f"抑制 {d_paa:.1f},{d_do2:.1f}）-> 瓶颈不在这些维度，需改 ODE（V1+）")
    return verdict, why + "；" + "；".join(flags)


def analyse(batch):
    base = calib_params(batch)
    sim0, v3 = simulate_open_loop(batch, base)
    err0 = _yield_err(sim0, v3)

    probes = {}

    def run(tag, over):
        p = dict(base)
        p.update(over)
        sim, _ = simulate_open_loop(batch, p)
        e = _yield_err(sim, v3)
        probes[tag] = {"err": e, "delta_pp": round((e - err0) * 100.0, 2)}
        return e

    run("A_yield_ceiling_mup_x110", {"mup": base["mup"] * UPLIFT})
    run("B_substrate_feed_x110", {"mv_scales": {"Fs": UPLIFT}})
    run("C1_paa_inhib_off", {"P_crit_PAA": -1.0e3})
    run("C2_do2_inhib_off", {"P_crit_DO2": -1.0e3})
    run("D_all", {"mup": base["mup"] * UPLIFT, "mv_scales": {"Fs": UPLIFT},
                  "P_crit_PAA": -1.0e3, "P_crit_DO2": -1.0e3})

    diag = _diag(sim0, v3)
    el = {k: v["delta_pp"] for k, v in probes.items() if k != "D_all"}
    verdict, why = _verdict(err0 * 100.0, el, probes)
    additivity = {
        "sum_of_singles_pp": round(sum(el.values()), 2),
        "joint_pp": probes["D_all"]["delta_pp"],
        "interaction_pp": round(probes["D_all"]["delta_pp"] - sum(el.values()), 2),
    }
    return {
        "batch": int(batch),
        "mu_p": round(float(base["mup"]), 5),
        "err_base_pct": round(err0 * 100.0, 2),
        "probes": probes,
        "elasticity_pp_per_10pct": el,
        "additivity": additivity,
        "diag": diag,
        "verdict": verdict,
        "why": why,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", default="91,55,36,8")
    ap.add_argument("--out", default=os.path.join(ROOT, "runs", "p3", "r135_b55_b91_attrib.json"))
    ap.add_argument("--reanalyse", action="store_true",
                    help="不重跑仿真：用已存的弹性谱重算判定（判据改动时用）")
    args = ap.parse_args()

    if args.reanalyse:
        d = json.load(open(args.out, encoding="utf-8"))
        for r in d["batches"]:
            v, why = _verdict(r["err_base_pct"], r["elasticity_pp_per_10pct"], r["probes"])
            r["verdict"], r["why"] = v, why
        d["meta"]["criteria"] = {
            "redline_clean": "|err|<=5% 且 max(|A|,|B|)<20pp",
            "redline_near_bifurcation": "|err|<=5% 但 max(|A|,|B|)>=20pp",
            "high_leverage": "|err|>5% 且 max(|A|,|B|)>=20pp（不可修补）",
            "structural": "|err|>5% 且全部 <20pp",
            "note": "抑制项 |Δ|<0.5pp 记为『未激活』——是排除证据，不是瓶颈",
        }
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        print(f"{'批':>4} {'err%':>8} {'A(μp)':>8} {'B(Fs)':>8} {'C1':>6} {'C2':>6}  verdict")
        for r in d["batches"]:
            el = r["elasticity_pp_per_10pct"]
            print(f"{r['batch']:>4} {r['err_base_pct']:>+8.2f} {el['A_yield_ceiling_mup_x110']:>+8.2f} "
                  f"{el['B_substrate_feed_x110']:>+8.2f} {el['C1_paa_inhib_off']:>+6.2f} "
                  f"{el['C2_do2_inhib_off']:>+6.2f}  {r['verdict']}")
            print(f"       {r['why']}")
        print(f"\n已更新 {args.out}")
        return

    batches = [int(x) for x in args.batches.split(",") if x.strip()]

    mups = [c["mup"] for c in COMBINED.values() if "mup" in c]
    mu_med = float(median(mups))

    rows = []
    for b in batches:
        r = analyse(b)
        r["mu_p_population_median"] = round(mu_med, 5)
        r["mu_p_vs_median"] = round(float(r["mu_p"]) / mu_med, 3)
        rows.append(r)
        print(f"\n批 {b}: 基线 err {r['err_base_pct']:+.2f}%  (μp {r['mu_p']:.4f} = 群体中位 {mu_med:.4f} 的 "
              f"{r['mu_p_vs_median']:.2f}×)")
        print(f"  弹性（+10% 干预 → Δerr pp）: " +
              "  ".join(f"{k.split('_')[0]}={v:+.2f}" for k, v in r["elasticity_pp_per_10pct"].items()))
        print(f"  叠加 D_all: {r['probes']['D_all']['err']*100:+.2f}%  "
              f"(单点之和 {r['additivity']['sum_of_singles_pp']:+.2f}pp, "
              f"交互 {r['additivity']['interaction_pp']:+.2f}pp)")
        d = r["diag"]
        print(f"  诊断: S_min={d['S_min']} S_end={d['S_end']} 低硫占比={d['frac_S_below_1']*100:.0f}% "
              f"S<0.5g/L 起于 {d['S_exhaust_h']}h | PAA_max={d['PAA_max']} "
              f"(>200 占 {d['PAA_above_200_frac']*100:.0f}%) | DO2_min={d['DO2_min']} | "
              f"X_end 比 {d['X_ratio_end']}")
        print(f"  判定：【{r['verdict']}】{r['why']}")

    print("\n" + "=" * 100)
    print("汇总")
    print("=" * 100)
    print(f"{'批':>4} {'err%':>8} {'μp/中位':>8} {'μp×1.1':>8} {'Fs×1.1':>8} {'PAA关':>8} {'DO2关':>8} {'全叠加':>8}  verdict")
    for r in rows:
        el = r["elasticity_pp_per_10pct"]
        print(f"{r['batch']:>4} {r['err_base_pct']:>+8.2f} {r['mu_p_vs_median']:>8.2f} "
              f"{el['A_yield_ceiling_mup_x110']:>+8.2f} {el['B_substrate_feed_x110']:>+8.2f} "
              f"{el['C1_paa_inhib_off']:>+8.2f} {el['C2_do2_inhib_off']:>+8.2f} "
              f"{r['probes']['D_all']['delta_pp']:>+8.2f}  {r['verdict']}")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"meta": {"uplift": UPLIFT, "batches": batches,
                            "mu_p_population_median": round(mu_med, 5),
                            "method": "counterfactual elasticity（不拟合参数）",
                            "criteria": {"single_dim": "单一维度改善 >=2pp/10%",
                                         "multi_dim": ">=2 个维度改善 >=2pp/10%",
                                         "structural": "全部 <2pp/10%"}},
                   "batches": rows}, f, ensure_ascii=False, indent=1)
    print(f"\n已写入 {args.out}")


if __name__ == "__main__":
    main()
