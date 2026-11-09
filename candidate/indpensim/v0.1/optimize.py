# -*- coding: utf-8 -*-
"""C 档寻优（反设计）：产量目标下的操作条件寻优。

方法：仿真优化（simulator-in-the-loop）。决策变量 = 参考配方（V3 MV 序列）的
倍率缩放因子（Fs 糖补料、Foil 油补料、Fpaa 前体、Fg 通气、RPM 搅拌），
目标 = 最大化仿真收获产量（harvested + 末罐内），约束 = 无灾难性崩溃。

求解器：scipy Nelder-Mead（无梯度、抗噪声，适于 8s/次 的 ODE 引擎）。
证据：输出基线产量、最优解、每次评估数、崩溃分级。
"""
import sys, os, json, time
import numpy as np
import pandas as pd
from scipy.optimize import minimize

sys.path.insert(0, os.path.dirname(__file__))
from simulate import simulate_open_loop, yield_metrics, classify_crash
from calibration import calib_params

MV_VARS = ["Fs", "Foil", "Fpaa", "Fg", "RPM"]


def _eval(batch_no, x, var_names):
    scales = {name: float(v) for name, v in zip(var_names, x)}
    params = dict(calib_params(batch_no), mv_scales=scales)
    sim, v3 = simulate_open_loop(batch_no, params)
    ym = yield_metrics(sim, v3)
    level, reasons = classify_crash(sim, yield_err=ym["rel_err_total"])
    ok = level != "catastrophic"
    return (ym["total_sim_g"] if ok else ym["total_sim_g"] * 0.05), ym, level, reasons


def optimize_feed(batch_no, var_names=("Fs",), x0=None, bounds=None,
                  maxiter=30, verbose=True, save_plan=None, objective="max_yield"):
    """反设计：在给定 MV 倍率维度上按目标寻优。

    var_names : MV 列名子集（Fs/Foil/Fpaa/Fg/RPM）
    x0        : 初值（缺省全 1.0 = V3 参考配方）
    bounds    : [(lo,hi), ...]，缺省 [0.8, 1.3]
    objective : "max_yield"（最大化产量，超 V3 不罚）或
                "track_target"（最小化 |产量 − V3 参考|，反设计对准目标）
    返回 dict（含基线/最优/证据），可写 runs/。
    """
    var_names = list(var_names)
    n = len(var_names)
    x0 = np.asarray(x0 if x0 is not None else [1.0] * n, float)
    bounds = bounds if bounds is not None else [(0.8, 1.3)] * n

    # 基线（逐批校准参数 + V3 参考配方）
    base_params = calib_params(batch_no)
    sim0, v3 = simulate_open_loop(batch_no, base_params)
    ym0 = yield_metrics(sim0, v3)
    lv0, rs0 = classify_crash(sim0, yield_err=ym0["rel_err_total"])
    target_yield = float(ym0["total_v3_g"])

    n_in = 0
    history = []  # C 档收敛曲线（每次评估一条：倍率/产量/崩溃）

    def _eval_safe(x, var_names):
        try:
            return _eval(batch_no, x, var_names)
        except Exception:  # 积分发散/NaN（BDF LU 因子、负值幂）→ 返回失败标记
            return None

    def fobj(x):
        nonlocal n_in
        for v, (lo, hi) in zip(x, bounds):  # 隐式越界惩罚
            if v < lo or v > hi:
                n_in += 1
                history.append({"eval": n_in,
                                "scales": {k: float(v) for k, v in zip(var_names, x)},
                                "yield_g": None, "crash": "out_of_bounds"})
                return 1e9 if objective == "track_target" else -1e6
        pack = _eval_safe(x, var_names)
        n_in += 1
        if pack is None:
            if verbose:
                print(f"    eval#{n_in:02d} {dict(zip(var_names, np.round(x, 4)))} -> DIVERGED", flush=True)
            history.append({"eval": n_in,
                            "scales": {k: float(v) for k, v in zip(var_names, x)},
                            "yield_g": None, "crash": "diverged"})
            return 1e9 if objective == "track_target" else -1e6
        y, ym, level, _ = pack
        history.append({"eval": n_in,
                        "scales": {k: float(v) for k, v in zip(var_names, x)},
                        "yield_g": float(ym["total_sim_g"]), "crash": level})
        if verbose:
            sc = {k: round(float(v), 4) for k, v in zip(var_names, x)}
            print(f"    eval#{n_in:02d} {sc} -> yield={y/1e6:.3f} Mg ({level})", flush=True)
        return (abs(ym["total_sim_g"] - target_yield)) if objective == "track_target" else -y

    t0 = time.time()
    res = minimize(fobj, x0, method="Nelder-Mead",
                   options={"maxiter": maxiter, "xatol": 0.01, "fatol": 1e4})
    wall = time.time() - t0

    # 最终复验（发散则退回基线）
    pack_best = _eval_safe(res.x, var_names)
    if pack_best is None:
        pack_best = (None, ym0, lv0, ["最优解积分发散 → 记录基线兜底"])
    y_best, ym_best, level_best, reasons_best = pack_best
    out = {
        "batch": batch_no,
        "vars": var_names,
        "x_best": {k: float(v) for k, v in zip(var_names, res.x)},
        "baseline_yield_g": float(ym0["total_sim_g"]),
        "baseline_err": float(ym0["rel_err_total"]),
        "opt_yield_g": float(ym_best["total_sim_g"]),
        "opt_err_vs_v3": float(ym_best["rel_err_total"]),
        "improvement": float(ym_best["total_sim_g"] - ym0["total_sim_g"]),
        "improvement_pct": float((ym_best["total_sim_g"] - ym0["total_sim_g"]) / ym0["total_sim_g"]),
        "crash_level": level_best,
        "crash_reasons": reasons_best,
        "objective": objective,
        "history": history,
        "n_evals": int(n_in),
        "wall_s": round(wall, 1),
        "solver": "Nelder-Mead",
        "bounds": [list(map(float, b)) for b in bounds],
    }
    if verbose:
        print(f"\n  baseline: {ym0['total_sim_g']/1e6:.3f} Mg (err {ym0['rel_err_total']:+.1%}, {lv0})")
        print(f"  optimized: {ym_best['total_sim_g']/1e6:.3f} Mg (err vs V3 {ym_best['rel_err_total']:+.1%}, {level_best})")
        print(f"  best scales: {out['x_best']}  improvement: {out['improvement_pct']:+.2%}"
              f"  evals={n_in} wall={wall:.0f}s")
    if save_plan:
        with open(save_plan, "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=2, default=str)
        print(f"  saved: {save_plan}")
    return out


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--vars", default="Fs")
    ap.add_argument("--maxiter", type=int, default=25)
    ap.add_argument("--objective", choices=["max_yield", "track_target"], default="max_yield")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    optimize_feed(a.batch, var_names=a.vars.split(","),
                  maxiter=a.maxiter, objective=a.objective,
                  save_plan=a.out or f"runs/opt_batch_{a.batch:02d}.json")
