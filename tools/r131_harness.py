# -*- coding: utf-8 -*-
"""R131 并行实验框架 —— 多进程批量仿真（8 核）。

单批 open-loop 仿真约 28 s；本框架用 multiprocessing.Pool 并行，把
12 批 × N 配置的扫描从 O(N) 降到 O(N/8)。

约定：
- 每个 worker 只 import simulate，不共享状态 → 确定性可复现。
- 指标统一口径：
  * yield_err = yield_metrics()["rel_err_total"]（总产量相对误差，与黄金回归一致）
  * X 通道：nRMSE（离线化验对齐，Off_line_delay=4），corr，peak_t，decay_tail
  * S/P/pH 通道 nRMSE（辅助判据）
"""
import os
import sys
import numpy as np
import pandas as pd
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))

OFFLINE_DELAY_H = 4.0  # indpensim_run.m L49 Off_line_delay=4


def _load_v3(batch):
    return pd.read_csv(os.path.join(ROOT, "data", "processed", "batches", f"batch_{batch:02d}.csv"))


def _nrmse(sim_v, lab_v):
    sim_v = np.asarray(sim_v, float)
    lab_v = np.asarray(lab_v, float)
    m = np.isfinite(lab_v) & np.isfinite(sim_v)
    if m.sum() < 3:
        return float("nan"), m.sum()
    lab_mean = float(np.mean(np.abs(lab_v[m])))
    rmse = float(np.sqrt(np.mean((sim_v[m] - lab_v[m]) ** 2)))
    if lab_mean > 1e-10:
        return 100.0 * rmse / lab_mean, int(m.sum())
    return 100.0 * rmse, int(m.sum())


def channel_metrics(sim, v3, cols):
    """离线通道指标：按 4h 化验滞后对齐（sim(t+delay) vs lab(t)）。"""
    out = {}
    t = v3["time_h"].values
    for name, col in cols.items():
        lab = v3[col].values
        if not np.isfinite(lab).any():
            continue
        # 化验点在 lab 非 NaN 处；对应 sim 取 t+delay
        sim_vals = np.interp(t + OFFLINE_DELAY_H, sim["time_h"].values, sim[name].values)
        nrmse, n = _nrmse(sim_vals, lab)
        m = np.isfinite(lab)
        corr = float(np.corrcoef(sim_vals[m], lab[m])[0, 1]) if m.sum() > 3 else float("nan")
        out[f"{col}"] = {"nrmse_pct": round(nrmse, 2) if np.isfinite(nrmse) else None,
                         "corr": round(corr, 3) if np.isfinite(corr) else None,
                         "n": n}
    return out


def x_shape_metrics(sim, v3):
    """X 通道形态学：峰值时刻 / 峰值 / 尾段衰减率 / 表观净比速率。"""
    t = v3["time_h"].values
    lab = v3["X_offline"].values
    m = np.isfinite(lab)
    if m.sum() < 4:
        return {}
    t_l, x_l = t[m], lab[m]
    ipk = int(np.argmax(x_l))
    sim_x = np.interp(t_l + OFFLINE_DELAY_H, sim["time_h"].values, sim["X"].values)
    ispk = int(np.argmax(sim_x))
    # 尾段衰减：峰后线性斜率（g/L/h）
    def tail_slope(tt, xx, i):
        if len(tt) - i < 3:
            return float("nan")
        return float(np.polyfit(tt[i:], xx[i:], 1)[0])
    return {
        "t_peak_lab": float(t_l[ipk]), "x_peak_lab": round(float(x_l[ipk]), 2),
        "t_peak_sim": float(t_l[ispk]), "x_peak_sim": round(float(sim_x[ispk]), 2),
        "decay_tail_lab": round(tail_slope(t_l, x_l, ipk), 4),
        "decay_tail_sim": round(tail_slope(t_l, sim_x, ispk), 4),
        "x_end_lab": round(float(x_l[-1]), 2), "x_end_sim": round(float(sim_x[-1]), 2),
    }


def run_one(job):
    """job = (batch, params_dict, tag)。返回指标 dict。"""
    from simulate import simulate_open_loop, yield_metrics, classify_crash
    batch, params, tag = job
    try:
        sim, attrs = simulate_open_loop(batch, params)
    except Exception as e:  # 发散/异常显式返回，不静默
        return {"batch": batch, "tag": tag, "error": f"{type(e).__name__}: {e}"}
    v3 = _load_v3(batch)
    ym = yield_metrics(sim, v3)
    err = ym["rel_err_total"]
    level, reasons = classify_crash(sim, yield_err=err)
    ch = channel_metrics(sim, v3, {"X": "X_offline", "P": "P_offline", "S": "S",
                                   "PAA": "PAA_offline", "vis": "Viscosity_offline",
                                   "NH3": "NH3_offline"})
    rec = {
        "batch": batch, "tag": tag,
        "yield_err": None if err is None or not np.isfinite(err) else round(float(err), 4),
        "yield_sim_g": round(float(ym["total_sim_g"]), 1),
        "yield_v3_g": round(float(ym["total_v3"]), 1) if "total_v3" in ym else None,
        "crash": level, "crash_reasons": reasons,
        "channels": ch,
        "x_shape": x_shape_metrics(sim, v3),
        "params": {k: (v if not isinstance(v, (list, tuple)) else list(v)) for k, v in params.items()},
    }
    return rec


def run_jobs(jobs, n_proc=None):
    n_proc = n_proc or min(8, os.cpu_count() or 1)
    with Pool(n_proc) as pool:
        return pool.map(run_one, jobs, chunksize=1)


if __name__ == "__main__":
    import json
    base = {"mux": 0.47, "mup": 0.041, "alpha_kla": 90, "m_s": 0.029,
            "dist_flag": 1, "dist_tcin_asym": 10, "q_co2": 0.12}
    jobs = [(b, dict(base), "smoke") for b in [8, 11, 16, 22]]
    import time
    t0 = time.time()
    res = run_jobs(jobs)
    print(f"elapsed {time.time()-t0:.1f}s for {len(jobs)} jobs")
    print(json.dumps([{k: r.get(k) for k in ("batch", "yield_err", "crash")} for r in res],
                     ensure_ascii=False))
