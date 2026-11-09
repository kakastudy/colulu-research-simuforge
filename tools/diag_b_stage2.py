# -*- coding: utf-8 -*-
"""B 档第二阶段估计器：把 mup 锚定在 P_offline 化验轨迹上（可辨识性补强）。

背景（PROBLEM.md §12.11）：纯在线通道（DO2/CO2d/pH/T/NH3/OUR/CER/CO2outgas）不含
足够的 P 生产信息，mup 不可辨识 → 5/12 批次产率崩塌（-92%~-96%）。
本模块在第一阶段（在线网格）选出 mux/m_s/dTcin 之后，固定其余参数，
对 mup 单维度网格扫描，目标 = P_offline 化验轨迹 RMSE（Plant 真实拥有的数据
形式：12h 粒度、滞后 4h，indpensim_run.m Off_line_delay=4）。

评估独立性：产率偏差 yield_err 在估计完成后单独计算（未参与目标）。
"""
import sys, os, json
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics

T_OFF_DELAY = 4.0


def p_offline_rmse(sim, v3):
    """P_offline(t) = P(t-4h)（滞后 4h 登记口径）。返回 (rmse_gL, n)。"""
    rows = []
    po = pd.to_numeric(v3["P_offline"], errors="coerce")
    for i, val in po.items():
        if not np.isfinite(val):
            continue
        t_lab = float(v3.loc[i, "time_h"])
        s_p = np.interp(t_lab - T_OFF_DELAY, sim["time_h"].to_numpy(float),
                        sim["P"].to_numpy(float))
        rows.append((s_p, float(val)))
    if not rows:
        return np.nan, 0
    s = np.array([r[0] for r in rows]); v = np.array([r[1] for r in rows])
    return float(np.sqrt(np.mean((s - v) ** 2))), len(rows)


def estimate_stage2(batch_no, stage1_params, mup_grid=(0.010, 0.020, 0.030, 0.041, 0.050, 0.060, 0.070, 0.080)):
    v3 = pd.read_csv(f"data/processed/batches/batch_{batch_no:02d}.csv")
    rows = []
    for mup in mup_grid:
        params = dict(stage1_params, mup=float(mup))
        sim, _ = simulate_open_loop(batch_no, params)
        rmse, n = p_offline_rmse(sim, v3)
        rows.append({"mup": float(mup), "p_rmse": rmse, "n": n})
    best = min(rows, key=lambda r: r["p_rmse"])
    # 独立评估（不参与估计目标）
    params = dict(stage1_params, mup=best["mup"])
    sim, _ = simulate_open_loop(batch_no, params)
    ym = yield_metrics(sim, v3)
    co2d = float(sim["CO2d"].max())
    return {
        "batch": batch_no,
        "stage1_mup": stage1_params.get("mup"),
        "stage2_mup": best["mup"],
        "p_offline_rmse": best["p_rmse"],
        "n_lab": best["n"],
        "yield_err": float(ym["rel_err_total"]),
        "co2d_max": co2d,
        "scan": rows,
    }


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", default="8,16,36,55,80,92")
    ap.add_argument("--s1", default="runs/soft_sensing_7ch_all.json")
    ap.add_argument("--out", default="runs/soft_sensing_stage2.json")
    a = ap.parse_args()
    s1 = {r["batch"]: r["params"] for r in json.load(open(a.s1, encoding="utf-8"))}
    results = []
    for b in [int(x) for x in a.batches.split(",")]:
        r = estimate_stage2(b, s1[b])
        results.append(r)
        print(f"batch {b:2d}: mup {r['stage1_mup']:.3f} -> {r['stage2_mup']:.3f} "
              f"p_rmse={r['p_offline_rmse']:.2f} yield_err={r['yield_err']:+.1%} "
              f"CO2d={r['co2d_max']:.2f}{' CRASH' if r['co2d_max'] > 7.57 else ''}", flush=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    print(f"Saved: {a.out}")
