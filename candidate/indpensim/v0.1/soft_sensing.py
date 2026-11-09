# -*- coding: utf-8 -*-
"""B 档软测量：从在线量测估计批次级随机参数（网格搜索法）。

对任意批次（含非黄金集），从 V3 在线通道（DO2, CO2d, pH, T, NH3, OUR, CER）
通过粗网格搜索估计批次级随机参数（mux, mup, alpha_kla, m_s, distTcin）。

方法：
1. 粗网格扫描 mux × mup（3×3=9 组合），distTcin=+10 固定
2. 计算在线通道 RMSE（DO2, CO2d, pH, T, NH3）
3. 加崩溃惩罚
4. 取 RMSE 最小的组合
5. 可选：在最佳组合附近做细扫描

输出：估计的参数 + 仿真轨迹 + 在线通道匹配质量
"""
import sys, os, json
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics

CO2D_THRESHOLD = 7.57

# 工程根绝对路径（与进程 CWD 无关）
_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "processed"))# 在线通道（V3 有值的在线量测）
ONLINE_CHANNELS = ["DO2", "CO2d", "pH", "T", "NH3", "OUR", "CER", "CO2outgas"]

# 通道权重
CHANNEL_WEIGHTS = {
    "DO2": 0.3,
    "CO2d": 0.8,
    "pH": 0.3,
    "T": 0.2,
    "NH3": 0.2,
    "OUR": 0.5,
    "CER": 0.5,
    "CO2outgas": 1.0,
}


def online_rmse(sim, v3, t_lo=10, t_hi=200):
    """计算在线通道加权 RMSE（归一化到 V3 均值）。"""
    total_err = 0.0
    total_weight = 0.0
    for ch in ONLINE_CHANNELS:
        if ch not in sim.columns or ch not in v3.columns:
            continue
        s = sim[(sim.time_h >= t_lo) & (sim.time_h <= t_hi)]
        v = v3[(v3.time_h >= t_lo) & (v3.time_h <= t_hi)]
        if len(s) == 0 or len(v) == 0:
            continue
        t_v3 = v["time_h"].to_numpy(float)
        sim_vals = np.interp(t_v3, s["time_h"].to_numpy(float), s[ch].to_numpy(float))
        v3_vals = v[ch].to_numpy(float)
        mask = ~np.isnan(v3_vals) & ~np.isnan(sim_vals)
        if np.sum(mask) < 2:
            continue
        ch_rmse = np.sqrt(np.mean((sim_vals[mask] - v3_vals[mask]) ** 2))
        v3_mean = np.abs(np.nanmean(v3_vals))
        if v3_mean > 1e-6:
            ch_rmse = ch_rmse / v3_mean
        total_err += CHANNEL_WEIGHTS.get(ch, 0.5) * ch_rmse
        total_weight += CHANNEL_WEIGHTS.get(ch, 0.5)
    return total_err / total_weight if total_weight > 0 else 1e9


def crash_penalty(sim):
    co2d_max = sim["CO2d"].max() if "CO2d" in sim.columns else 0.0
    return max(0.0, (co2d_max - CO2D_THRESHOLD)) ** 2 * 50.0


def estimate_batch(batch_no, verbose=True, on_progress=None, grid=None, data_dir=None):
    """从 V3 在线量测估计批次级随机参数（网格 + 发散守卫）。

    on_progress(done, total) : 迭代回调（看板进度条用；CLI 默认 None）
    grid                     : dict 覆盖网格（muxs/mups/mss/tcins；测试用）
    data_dir                 : 绝对数据目录（默认工程根，独立于进程 CWD）
    """
    v3_path = (data_dir or _DATA_DIR) + f"/batches/batch_{batch_no:02d}.csv"
    v3 = pd.read_csv(v3_path)

    g = {"muxs": [0.35, 0.41, 0.47], "mups": [0.030, 0.041, 0.050],
         "mss": [0.020, 0.025], "tcins": [10, 15, 20]}
    if grid:
        g.update(grid)

    combos = [(m_s, dtcin, mux, mup) for m_s in g["mss"] for dtcin in g["tcins"]
              for mux in g["muxs"] for mup in g["mups"]]
    n_total = len(combos)

    results = []
    for idx, (m_s, dtcin, mux, mup) in enumerate(combos):
        params = {
            "mux": mux, "mup": mup, "alpha_kla": 85.0,
            "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
            "dist_flag": 1, "dist_tcin_asym": dtcin, "m_s": m_s,
        }
        try:
            sim, _ = simulate_open_loop(batch_no, params)
            ormse = online_rmse(sim, v3)
            cp = crash_penalty(sim)
            co2d_max = float(sim["CO2d"].max())
            ym_t = yield_metrics(sim, v3)
            combo_yield = float(ym_t["rel_err_total"])
        except Exception:  # 积分发散 / NaN（BDF LU、负值幂）→ 显式劣解不中断
            ormse, cp = 1e6, 0.0
            co2d_max = float("nan")
            combo_yield = float("nan")
        total = ormse + cp * 0.1
        crashed = bool(np.isnan(co2d_max)) or co2d_max > CO2D_THRESHOLD
        results.append({
            "mux": mux, "mup": mup, "m_s": m_s, "dtcin": dtcin,
            "online_rmse": ormse, "crash_pen": cp, "total": total,
            "co2d_max": co2d_max, "yield_err": combo_yield,
            "crashed": crashed,
        })
        if on_progress is not None:
            try:
                on_progress(idx + 1, n_total)
            except Exception:
                pass

    # 排序
    results.sort(key=lambda r: r["total"])
    best = results[0]

    if verbose:
        print(f"\n=== Batch {batch_no}: Grid search ({len(results)} combos) ===")
        print(f"Best: mux={best['mux']:.2f} mup={best['mup']:.4f} m_s={best['m_s']:.4f} dTcin={best['dtcin']:+d}")
        print(f"  online_rmse={best['online_rmse']:.4f} crash_pen={best['crash_pen']:.4f} CO2d={best['co2d_max']:.2f}")
        print(f"  {'CRASH' if best['crashed'] else 'ok'}")

    # 验证产率（同样受发散守卫保护：全网格发散时也可返回，不再抛异常）
    best_params = {
        "mux": best["mux"], "mup": best["mup"], "alpha_kla": 85.0,
        "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
        "dist_flag": 1, "dist_tcin_asym": best["dtcin"], "m_s": best["m_s"],
    }
    try:
        sim, _ = simulate_open_loop(batch_no, best_params)
        ym = yield_metrics(sim, v3)
        yield_err = float(ym["rel_err_total"])
    except Exception:
        yield_err = float("nan")

    return {
        "batch": batch_no,
        "params": best_params,
        "yield_err": yield_err,
        "co2d_max": best["co2d_max"],
        "crashed": bool(best["crashed"]),
        "online_rmse": best["online_rmse"],
        "top5": results[:5],
        "sweep": results,  # 全 54 组合（趋势图用：online_rmse / yield_err vs mup 等）
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--batches", type=str, default="8,11")
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args()

    batches = [int(b) for b in args.batches.split(",")]
    results = []
    for b in batches:
        r = estimate_batch(b)
        results.append(r)
        print(f"  → yield_err={r['yield_err']:+.1%} {'CRASH' if r['crashed'] else 'ok'}")

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False, default=str)
        print(f"\nSaved: {args.output}")
