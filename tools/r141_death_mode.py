# -*- coding: utf-8 -*-
"""r141_death_mode.py — D-8「kd 等比衰减，形态学分区失效」的闭合实验。

问题
----
现行实现把衰亡 `-kd·y[i]` **等比**施加到 a0/a1/a3/a4：
  · 形态分区比例恒定，"只移除死菌、保留活菌"无法表达；
  · a1 占总生物量 80–83%，且 `r_p = μp·a1/2`（一阶）⇒ 砍 X 必然同比例砍产素。
这就是 R137「晚期衰亡把 X 修好、却把 86/86 产量打成 33/86」的结构性原因。

R141 给引擎加了 `death_mode=1`：**叠加**在等比项之上的形态学链
    A1 --(age_rate, μ 门控, t≥age_start)--> A3 --(lysis_rate)--> 出系统（可回收到 S）
老化是 X 内部转移（不动总量），只有溶菌降 X；死菌池 a3/a4 由此首次非零。

本工具检验的问题
----------------
**同样的 X 修正幅度下，形态学链是否比等比衰亡少伤产量？**
即：结构修复是否移动了「X 可修—产量可保」的可行域边界。

两条臂都**叠加**在逐批标定基线之上（不动 `biomass_death_rate` / `death_start`）：
  prop 臂：`late_death_rate += δ`（等比，μ 门控天然晚期作用）——R137 的路子
  morph 臂：`death_mode=1, age_rate=α, lysis_rate=λ, age_start=144`

判据
----
对每批，看 (ΔX nRMSE, Δyield)。形态学链有价值 ⟺ 在同等 ΔX 下 Δyield 更小（更不负）。

用法
----
    python tools/r141_death_mode.py                    # 默认 10 批 × 7 配置
    python tools/r141_death_mode.py --all86            # 全量（约 90 min）
    python tools/r141_death_mode.py --batches 8 29 16
"""
import argparse
import json
import os
import sys
import time

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

OUT = os.path.join(ROOT, "runs", "p3", "r141_death_mode.json")
LAG_H = 4.0

# 默认抽样：覆盖 X 误差谱系（b8 最准 / b29 最差 / b16 曾崩 / b80 R137 崩批）
DEFAULT_BATCHES = [8, 16, 27, 29, 36, 51, 56, 80, 87, 91]

# 两条臂的配置：都叠加在逐批标定基线之上
CONFIGS = [
    ("base", {}),
    # --- prop 臂：等比晚期衰亡（R137 的路子），δ 加在 late_death_rate 上 ---
    ("prop_d005", {"late_death_rate_add": 0.005}),
    ("prop_d010", {"late_death_rate_add": 0.010}),
    ("prop_d020", {"late_death_rate_add": 0.020}),
    # --- morph 臂：形态学链，age/lysis 均从 144h 起 ---
    ("morph_a05_l02", {"death_mode": 1, "age_start": 144.0, "age_rate": 0.005,
                       "lysis_rate": 0.002, "lysis_recycle": 0.5}),
    ("morph_a10_l05", {"death_mode": 1, "age_start": 144.0, "age_rate": 0.010,
                       "lysis_rate": 0.005, "lysis_recycle": 0.5}),
    ("morph_a20_l10", {"death_mode": 1, "age_start": 144.0, "age_rate": 0.020,
                       "lysis_rate": 0.010, "lysis_recycle": 0.5}),
]


def nrmse(t_sim, v_sim, t_obs, v_obs):
    """化验有效点上的归一化 RMSE，观测时刻 t 对应模型 t−LAG_H（与 R139/R140 同口径）。"""
    m = np.isfinite(v_obs)
    if m.sum() < 3:
        return float("nan")
    pred = np.interp(t_obs[m] - LAG_H, t_sim, v_sim)
    den = float(np.mean(v_obs[m]))
    return float(100.0 * np.sqrt(np.mean((pred - v_obs[m]) ** 2)) / den) if den else float("nan")


def one(job):
    """单批 × 单配置。返回记录 dict。"""
    b, tag, cfg = job
    from golden_params import COMBINED, build_params
    from simulate import simulate_open_loop, yield_metrics

    v3 = pd.read_csv(os.path.join(ROOT, "data", "processed", "batches", f"batch_{b:02d}.csv"))
    base_p = dict(build_params(COMBINED[b]))
    p = dict(base_p)
    if "late_death_rate_add" in cfg:
        add = cfg["late_death_rate_add"]
        p["late_death_rate"] = float(base_p.get("late_death_rate", 0.0) or 0.0) + add
        cfg = {k: v for k, v in cfg.items() if k != "late_death_rate_add"}
    p.update(cfg)

    sim, _ = simulate_open_loop(b, params=p)
    t = sim["time_h"].to_numpy(float)
    to = v3["time_h"].to_numpy(float)
    xo = pd.to_numeric(v3["X_offline"], errors="coerce").to_numpy(float)
    po = pd.to_numeric(v3["P"], errors="coerce").to_numpy(float)
    yo = pd.to_numeric(v3["Penicillin_offline"], errors="coerce").to_numpy(float) \
        if "Penicillin_offline" in v3.columns else po

    ym = yield_metrics(sim, v3)
    yield_err = 100.0 * float(ym["rel_err_total"])  # 返回分数，×100

    Xs = sim["X"].to_numpy(float)
    Ps = sim["P"].to_numpy(float)
    # 峰值比 / 末值比：模型峰值 / 化验峰值
    xp_lab = float(np.nanmax(xo)) if np.isfinite(xo).any() else float("nan")
    pp_lab = float(np.nanmax(po)) if np.isfinite(po).any() else float("nan")
    end_lab = float(xo[np.isfinite(xo)][-1]) if np.isfinite(xo).any() else float("nan")
    deb = (float(sim["A3"].iloc[-1]) + float(sim["A4"].iloc[-1]))

    return {
        "b": int(b), "cfg": tag,
        "X_nrmse": nrmse(t, Xs, to, xo),
        "P_nrmse": nrmse(t, Ps, to, po),
        "yield_err": yield_err,
        "peakR": (float(np.max(Xs)) / xp_lab) if xp_lab else float("nan"),
        "endR": (float(Xs[-1]) / end_lab) if end_lab else float("nan"),
        "X_end": float(Xs[-1]),
        "P_end": float(Ps[-1]),
        "A1_end": float(sim["A1"].iloc[-1]),
        "debris_frac": (deb / float(Xs[-1]) * 100.0) if Xs[-1] > 1e-9 else float("nan"),
        "kd0": float(base_p.get("biomass_death_rate", 0.0) or 0.0),
        "late0": float(base_p.get("late_death_rate", 0.0) or 0.0),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", nargs="*", type=int, default=None)
    ap.add_argument("--all86", action="store_true")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()

    if a.all86:
        from golden_params import GOLDEN_ALL
        batches = sorted(GOLDEN_ALL)
    elif a.batches:
        batches = a.batches
    else:
        batches = DEFAULT_BATCHES

    jobs = [(b, tag, cfg) for b in batches for tag, cfg in CONFIGS]

    print("=" * 96)
    print(f"R141 D-8 形态学衰亡对照：{len(batches)} 批 × {len(CONFIGS)} 配置 = {len(jobs)} 次仿真")
    print(f"批：{batches}")
    print("=" * 96, flush=True)

    t0 = time.time()
    from multiprocessing import Pool
    with Pool(min(a.workers, os.cpu_count() or 1)) as pool:
        rows = pool.map(one, jobs, chunksize=1)
    rows.sort(key=lambda r: (r["b"], [c[0] for c in CONFIGS].index(r["cfg"])))

    base = {r["b"]: r for r in rows if r["cfg"] == "base"}
    print(f"\n耗时 {time.time()-t0:.0f}s\n")

    # ---- 逐批明细 ----
    for b in batches:
        b0 = base[b]
        print(f"b{b:<4d} base: XnR {b0['X_nrmse']:5.1f}%  PnR {b0['P_nrmse']:5.1f}%"
              f"  yield {b0['yield_err']:+6.2f}%  peakR {b0['peakR']:.3f}  debris {b0['debris_frac']:.1f}%")
        for tag, _ in CONFIGS[1:]:
            r = next(x for x in rows if x["b"] == b and x["cfg"] == tag)
            dX = b0["X_nrmse"] - r["X_nrmse"]
            dP = b0["P_nrmse"] - r["P_nrmse"]
            dY = r["yield_err"] - b0["yield_err"]
            print(f"      {tag:<14s} ΔX {dX:+6.1f}pt  ΔP {dP:+6.1f}pt  Δyield {dY:+6.2f}pt"
                  f"  peakR {r['peakR']:.3f}  debris {r['debris_frac']:5.1f}%")

    # ---- 臂级汇总：同为"X 改善"时，产量代价谁更小 ----
    print("\n" + "=" * 96)
    print("臂级汇总（Δ 相对各批 base；正 ΔX = X 变好，负 Δyield = 产量变差）")
    print(f"{'配置':<16s}{'ΔX 中位':>10s}{'ΔP 中位':>10s}{'Δyield 中位':>12s}"
          f"{'产量破线批':>10s}{'X 改善批':>9s}{'debris 中位':>11s}")
    summary = {}
    for tag, _ in CONFIGS[1:]:
        dX, dP, dY, deb = [], [], [], []
        brk = 0
        for b in batches:
            r = next(x for x in rows if x["b"] == b and x["cfg"] == tag)
            dX.append(base[b]["X_nrmse"] - r["X_nrmse"])
            dP.append(base[b]["P_nrmse"] - r["P_nrmse"])
            dY.append(r["yield_err"] - base[b]["yield_err"])
            deb.append(r["debris_frac"])
            if abs(r["yield_err"]) > 5.0:
                brk += 1
        s = {"dX_med": float(np.median(dX)), "dP_med": float(np.median(dP)),
             "dY_med": float(np.median(dY)), "yield_break": brk,
             "x_better": int(np.sum(np.array(dX) > 1.0)),
             "debris_med": float(np.median(deb))}
        summary[tag] = s
        print(f"{tag:<16s}{s['dX_med']:+10.1f}{s['dP_med']:+10.1f}{s['dY_med']:+12.2f}"
              f"{brk:>7d}/{len(batches)}{s['x_better']:>9d}{s['debris_med']:>10.1f}%")

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump({"meta": {"batches": batches, "configs": [[t, c] for t, c in CONFIGS],
                        "lag_h": LAG_H,
                        "note": "yield_err 为百分数；两臂均叠加在逐批标定基线之上"},
               "summary": summary, "rows": rows},
              open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n已写入 {os.path.relpath(a.out, ROOT)}")


if __name__ == "__main__":
    main()
