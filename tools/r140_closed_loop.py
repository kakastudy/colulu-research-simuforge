# -*- coding: utf-8 -*-
"""r140_closed_loop.py — 闭环数据同化（D-16 的唯一检验方式）。

做什么
------
开环（A 档）跑一遍、闭环（R139 v2 观测器反馈进 ODE）跑一遍，86 批对比三项：
  1. X 轨迹 nRMSE        —— 同化是否真的把菌丝浓度拉住
  2. P 轨迹 nRMSE        —— D-16「X 与 P 因果倒置耦合」能否被同化解开（P 不被校正，纯观察）
  3. 最终产量偏差         —— GOAL §2 红线 ±5%，同化不能把产量推出线

闭环机制（引擎 `simulate_open_loop` 的 `assimilate` 开关，默认关闭）
--------------------------------------------------------------------
每个观测时刻 t_k（默认 12h，warmup 24h）：
    r_OUR = OUR_obs(t_k)/OUR_model(t_k)      r_CER = CER_obs(t_k)/CER_model(t_k)
    mo    = mean(log r_OUR 截至 t_k)           mc = mean(log r_CER 历史)
    k_hat = exp(p·mo + q·(log r_CER − mc))
    A0,A1,A3,A4 ← k_hat × 原值                 （等比缩放，保持形态比例）
门控：|mo| > 0.45 ⇒ 判定批级标度不可辨识，该步不校正（与 R139 后处理同判据）。

为什么必须用 v2 而不是 v1
------------------------
v1（`OUR^0.60`）修的是 OUR 导出通道标度偏差，闭环里会把 18.5% 的系统偏置直接灌进状态，
形成自激。v2 把批级标度（OUR）与时间形（CER）分开，才不会。

用法
----
  python tools/r140_closed_loop.py --batches 8 16 51        # 抽样
  python tools/r140_closed_loop.py --all86                   # 全量（约 15–20 min）
  python tools/r140_closed_loop.py --all86 --dt 6 --warmup 12
"""
import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "candidate", "indpensim", "v0.1"))
from simulate import simulate_open_loop, yield_metrics  # noqa: E402
from calibration import GOLDEN  # noqa: E402
from golden_params import COMBINED, build_params  # noqa: E402

OUT = os.path.join(HERE, "runs", "p3", "r140_closed_loop.json")
LAG_H = 4.0          # 化验滞后（与 conservation_metrics / R139 同口径）


def nrmse(t_sim, v_sim, t_obs, v_obs):
    """在化验有效点上比对，观测时刻 t 对应模型 t−LAG_H。"""
    m = np.isfinite(v_obs)
    if m.sum() < 3:
        return float("nan")
    pred = np.interp(t_obs[m] - LAG_H, t_sim, v_sim)
    den = np.mean(v_obs[m])
    return float(100.0 * np.sqrt(np.mean((pred - v_obs[m]) ** 2)) / den) if den else float("nan")


def run_one(b, assim, lr_star=None):
    v3 = pd.read_csv(os.path.join(HERE, "data", "processed", "batches", f"batch_{b:02d}.csv"))
    # 必须用逐批标定参数（86 批验收基线口径）；用名义参数会让 b51 之类崩到 +178%
    p_open = build_params(COMBINED[b])
    p_closed = dict(p_open)
    p_closed["assimilate"] = assim
    sim0, _ = simulate_open_loop(b, p_open)
    sim1, _ = simulate_open_loop(b, params=p_closed)

    t0 = sim0["time_h"].to_numpy(float)
    t1 = sim1["time_h"].to_numpy(float)
    to = v3["time_h"].to_numpy(float)
    xo = pd.to_numeric(v3["X_offline"], errors="coerce").to_numpy(float)
    po = pd.to_numeric(v3["P"], errors="coerce").to_numpy(float)

    y0 = yield_metrics(sim0, v3)
    y1 = yield_metrics(sim1, v3)
    # yield_metrics 返回分数（R136 踩过的坑），统一 ×100 存百分数
    e0 = 100.0 * float(y0["rel_err_total"])
    e1 = 100.0 * float(y1["rel_err_total"])

    rec = {
        "b": int(b),
        "X_nrmse_open": nrmse(t0, sim0["X"].to_numpy(float), to, xo),
        "X_nrmse_closed": nrmse(t1, sim1["X"].to_numpy(float), to, xo),
        "P_nrmse_open": nrmse(t0, sim0["P"].to_numpy(float), to, po),
        "P_nrmse_closed": nrmse(t1, sim1["P"].to_numpy(float), to, po),
        "yield_err_open": e0,
        "yield_err_closed": e1,
        "dyield": e1 - e0,
        "X_end_open": float(sim0["X"].iloc[-1]),
        "X_end_closed": float(sim1["X"].iloc[-1]),
        "X_end_lab": float(pd.to_numeric(v3["X_offline"], errors="coerce").dropna().iloc[-1]),
        "P_end_open": float(sim0["P"].iloc[-1]),
        "P_end_closed": float(sim1["P"].iloc[-1]),
        "P_end_lab": float(v3["P"].iloc[-1]),
        "n_assim": len(sim1.attrs.get("assim_log", [])),
        "n_gated": sum(1 for x in sim1.attrs.get("assim_log", []) if x["gated"]),
        "k_min": float(min((x["k"] for x in sim1.attrs.get("assim_log", [])), default=1.0)),
        "k_max": float(max((x["k"] for x in sim1.attrs.get("assim_log", [])), default=1.0)),
    }
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", default=None)
    ap.add_argument("--all86", action="store_true")
    ap.add_argument("--dt", type=float, default=12.0, help="观测/校正间隔（h）")
    ap.add_argument("--warmup", type=float, default=24.0, help="起始校正时刻（h）")
    ap.add_argument("--p", type=float, default=0.599)
    ap.add_argument("--q", type=float, default=0.713)
    ap.add_argument("--gate", type=float, default=0.45)
    ap.add_argument("--k-lo", type=float, default=0.95, help="单步校正下界（无约束会崩批）")
    ap.add_argument("--k-hi", type=float, default=1.05, help="单步校正上界")
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()

    if a.all86:
        sys.path.insert(0, os.path.join(HERE, "tools"))
        from golden_params import GOLDEN_ALL
        batches = list(GOLDEN_ALL)
    elif a.batches:
        batches = [int(x) for x in a.batches.replace(",", " ").split()]
    else:
        batches = list(GOLDEN)

    assim = {"dt": a.dt, "warmup": a.warmup, "p": a.p, "q": a.q, "gate": a.gate,
             "k_lo": a.k_lo, "k_hi": a.k_hi}
    rows = []
    print(f"闭环参数：{assim}")
    print(f"{'批':>4s}{'X open→closed':>22s}{'P open→closed':>22s}{'产量 err':>18s}{'门控':>6s}")
    for b in batches:
        try:
            r = run_one(b, assim)
        except Exception as e:
            print(f"{b:4d}  ERROR {e}", flush=True)
            continue
        rows.append(r)
        print(f"{b:4d}{r['X_nrmse_open']:10.1f}→{r['X_nrmse_closed']:8.1f}%"
              f"{r['P_nrmse_open']:11.1f}→{r['P_nrmse_closed']:8.1f}%"
              f"{r['yield_err_open']:+9.2f}→{r['yield_err_closed']:+7.2f}%"
              f"{r['n_gated']:4d}/{r['n_assim']:<3d}", flush=True)

    if not rows:
        print("无有效批次")
        return

    def col(k):
        return np.array([r[k] for r in rows], float)

    x0, x1 = col("X_nrmse_open"), col("X_nrmse_closed")
    p0, p1 = col("P_nrmse_open"), col("P_nrmse_closed")
    y0, y1 = col("yield_err_open"), col("yield_err_closed")

    print(f"\n=== {len(rows)} 批汇总 ===")
    print(f"{'指标':<22s}{'开环':>10s}{'闭环':>10s}{'改善批':>9s}{'恶化批':>9s}")
    for nm, a0, a1 in (("X nRMSE 中位 %", x0, x1), ("P nRMSE 中位 %", p0, p1),
                       ("|产量偏差| 中位 %", np.abs(y0), np.abs(y1))):
        better = int(np.sum(a1 < a0 - 0.5))
        worse = int(np.sum(a1 > a0 + 0.5))
        print(f"{nm:<22s}{np.median(a0):10.2f}{np.median(a1):10.2f}{better:9d}{worse:9d}")

    print(f"\n产量红线（±5%）：开环 {int(np.sum(np.abs(y0)<=5))}/{len(rows)}"
          f" → 闭环 {int(np.sum(np.abs(y1)<=5))}/{len(rows)}")
    print(f"产量偏差范围：开环 [{y0.min():+.2f}, {y0.max():+.2f}] → "
          f"闭环 [{y1.min():+.2f}, {y1.max():+.2f}]")
    print(f"闭环最坏产量变动：{y1[np.argmax(np.abs(col('dyield')))]:+.2f}%")

    # D-16 判定：X 改善的同时 P 是否也改善（同向）？
    dX, dP = x0 - x1, p0 - p1
    both = int(np.sum((dX > 0.5) & (dP > 0.5)))
    onlyX = int(np.sum((dX > 0.5) & (dP <= 0.5)))
    print(f"\nD-16 耦合检验：X 改善且 P 同步改善 {both} 批 / 仅 X 改善 {onlyX} 批"
          f"（同向率 {100*both/max(len(rows),1):.0f}%）")
    if len(rows) > 2:
        rho = np.corrcoef(dX, dP)[0, 1]
        print(f"  ρ(ΔX 改善, ΔP 改善) = {rho:+.3f}")

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump({"meta": {"n": len(rows), "assim": assim, "lag_h": LAG_H,
                        "note": "yield_metrics 返回分数，已 ×100；P 不参与校正，纯观察"},
               "rows": rows},
              open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n已写入 {a.out}")


if __name__ == "__main__":
    main()
