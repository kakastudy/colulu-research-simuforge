# -*- coding: utf-8 -*-
"""B 档第二阶段估计器（正式模块化）：mup 锚定 P_offline 化验轨迹。

背景（§14.3）：纯在线通道 mup 不可辨识（部分批次产率崩塌 -92%~-96%），
P_offline 化验（12h 粒度、滞后 4h，indpensim_run.m Off_line_delay=4）救援后
5/5 崩塌批已验证救回（16/36/55/80/92，见 runs/*scan.json / b92_pinpoint.json）。

协作：第一阶段用 soft_sensing.estimate_batch（在线 54 组合），把其 params
传给 estimate_stage2 扫 mup；产率偏差独立评估不参与估计目标。
"""
import os
import numpy as np
import pandas as pd

_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..",
                                         "data", "processed"))
T_OFF_DELAY = 4.0


def p_offline_rmse(sim, v3):
    """P_offline(t) = P(t-4h)：sim 与 V3 化验点的对照 RMSE（g/L）。"""
    rows = []
    po = pd.to_numeric(v3["P_offline"], errors="coerce")
    for i, val in po.items():
        if not np.isfinite(val):
            continue
        if hasattr(i, "tz_localize") or str(i).isdigit():
            idx = i
        else:
            idx = None
        t_lab = float(v3.loc[idx, "time_h"]) if idx is not None else float(v3["time_h"].iloc[i])
        s_p = np.interp(t_lab - T_OFF_DELAY, sim["time_h"].to_numpy(float),
                        sim["P"].to_numpy(float))
        rows.append((s_p, float(val)))
    if not rows:
        return float("nan"), 0
    s = np.array([r[0] for r in rows])
    v = np.array([r[1] for r in rows])
    return float(np.sqrt(np.mean((s - v) ** 2))), len(rows)


def load_v3(batch_no, data_dir=None):
    return pd.read_csv(os.path.join(data_dir or _DATA_DIR, "batches", f"batch_{batch_no:02d}.csv"))


def estimate_stage2(batch_no, stage1_params, v3=None, mup_grid=None, on_progress=None):
    """在 stage-1 参数（mux/m_s/dtcin 等已定）上单维扫描 mup，目标 = P_offline RMSE。

    返回 dict：batch / stage1_mup / stage2_mup / p_offline_rmse / n_lab /
    yield_err / co2d_max / scan。
    """
    if v3 is None:
        v3 = load_v3(batch_no)
    mup_grid = list(mup_grid or [0.010, 0.020, 0.025, 0.030, 0.0325, 0.034,
                                 0.038, 0.041, 0.045, 0.050])
    from simulate import simulate_open_loop, yield_metrics

    rows = []
    for j, mup in enumerate(mup_grid):
        params = dict(stage1_params, mup=float(mup))
        sim, _ = simulate_open_loop(int(batch_no), params)
        rmse, n = p_offline_rmse(sim, v3)
        ym = yield_metrics(sim, v3)
        rows.append({"mup": float(mup), "p_rmse": rmse, "n": n,
                     "yield_err": float(ym["rel_err_total"]),
                     "co2d": float(sim["CO2d"].max())})
        if on_progress is not None:
            try:
                on_progress(j + 1, len(mup_grid))
            except Exception:
                pass
    best = min(rows, key=lambda r: r["p_rmse"])

    from simulate import yield_metrics
    params = dict(stage1_params, mup=best["mup"])
    sim, _ = simulate_open_loop(int(batch_no), params)
    ym = yield_metrics(sim, v3)
    return {
        "batch": int(batch_no),
        "stage1_mup": stage1_params.get("mup"),
        "stage2_mup": best["mup"],
        "p_offline_rmse": best["p_rmse"],
        "n_lab": best["n"],
        "yield_err": float(ym["rel_err_total"]),
        "co2d_max": float(sim["CO2d"].max()),
        "scan": rows,
    }
