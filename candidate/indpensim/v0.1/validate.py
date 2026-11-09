# -*- coding: utf-8 -*-
"""validate.py — V3 黄金集校验框架（M4）。

用法：
  python validate.py                    # 默认名义参数，黄金集全量
  python validate.py --batches 8 11 16  # 指定批次
  python validate.py --params-file runs/params.json  # 指定参数

输出：
  1. 产率偏差（RMSE 口径）：sqrt(mean((y_sim - y_v3)^2)) / mean(y_v3)
  2. 轨迹级指标：MAE/RMSE/R²（S/X/P/DO/T/pH/CO2outgas）
  3. 崩溃检测：CO2d > X_crit_CO2 = 7.57 g/L
  4. 守恒检查：OUR/CER 尾气平衡闭合
"""
import argparse
import json
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics, trajectory_metrics

# Golden set (PROBLEM.md §7.1)
GOLDEN_NORMAL = [8, 11, 16, 22, 23, 27, 36, 55, 60, 80]
GOLDEN_FAULT = [91, 92]

# CO2d crash threshold
CO2D_THRESHOLD = 7.57  # g/L = X_crit_CO2


def load_params(params_file=None):
    """加载参数配置。"""
    if params_file and os.path.exists(params_file):
        with open(params_file, "r", encoding="utf-8") as f:
            return json.load(f)
    # 默认名义参数
    return {"mux": 0.41, "mup": 0.041, "alpha_kla": 85.0,
            "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0}


def validate_batch(batch_no, params):
    """校验单个批次。返回结果 dict。"""
    sim, v3 = simulate_open_loop(batch_no, params)

    # 产率
    ym = yield_metrics(sim, v3)

    # 轨迹级指标
    tm = trajectory_metrics(sim, v3)

    # 崩溃检测
    co2d_max = sim["CO2d"].max() if "CO2d" in sim.columns else 0.0
    crashed = co2d_max > CO2D_THRESHOLD

    # X 估计（A0+A1）
    if "A0" in sim.columns and "A1" in sim.columns:
        sim_x = sim["A0"] + sim["A1"]
        v3_x = pd.to_numeric(v3["X_offline"], errors="coerce")
        # X trajectory metrics
        x_mask = v3_x.notna()
        if x_mask.any():
            v3_x_vals = v3_x[x_mask].to_numpy(float)
            sim_x_interp = np.interp(v3.loc[x_mask, "time_h"], sim["time_h"], sim_x.to_numpy(float))
            x_rmse = np.sqrt(np.mean((sim_x_interp - v3_x_vals) ** 2))
            x_mae = np.mean(np.abs(sim_x_interp - v3_x_vals))
        else:
            x_rmse = float("nan")
            x_mae = float("nan")
    else:
        x_rmse = float("nan")
        x_mae = float("nan")

    return {
        "batch": batch_no,
        "yield_sim": ym["total_sim_g"],
        "yield_v3": ym["total_v3_g"],
        "yield_rel_err": ym["rel_err_total"],
        "crashed": crashed,
        "co2d_max": co2d_max,
        "x_rmse": x_rmse,
        "x_mae": x_mae,
        "trajectory": tm,
    }


# ---------------------------------------------------------------- 86 批并行复验（R135 T7）
# 背景：服务层 golden_set_validate 长期只跑 13 批（calibration.GOLDEN），而引擎回归的
# 真实评估集是 86 批（golden_params.GOLDEN_ALL）——两套口径会让"MCP 报的"与"引擎验的"
# 各说各话。改 86 批后串行 ~40 min，故必须并行。
#
# Windows spawn 约束（踩过的坑）：
#   1) worker 必须是**模块顶层函数**，否则不可 pickle；
#   2) 参数必须是可 pickle 的**元组**，不能靠全局变量（子进程不继承父进程内存）；
#   3) 子进程会重新 import 本模块，故模块级只允许放常量与 sys.path，不得启动服务。
def _golden_worker(job):
    """单批评估 worker（供 multiprocessing 调用）。job = (batch, params_dict|None)。

    params 为 None 时按 calib_params(b) 取逐批校准参数（与引擎回归同源）。
    """
    from simulate import simulate_open_loop, yield_metrics, classify_crash

    b, params = job
    if params is None:
        from calibration import calib_params
        params = calib_params(int(b))
    sim, v3 = simulate_open_loop(int(b), params)
    ym = yield_metrics(sim, v3)
    level, reasons = classify_crash(sim, yield_err=ym["rel_err_total"])
    return {
        "batch": int(b),
        "yield_sim_g": float(ym["total_sim_g"]),
        "yield_v3_g": float(ym["total_v3_g"]),
        "yield_err": float(ym["rel_err_total"]),
        "co2d_max": float(sim["CO2d"].max()),
        "ph_end": float(sim["pH"].iloc[-1]),
        "crash": level,
        "crash_reasons": list(reasons or []),
    }


def _spawn_usable():
    """Windows spawn 的前提：父进程的 __main__ 必须是**真实文件**。

    `python - <<'PY'`（stdin 脚本）、`python -c`、Jupyter 等都拿不到 main 路径，
    spawn 子进程会在 `_fixup_main_from_path` 处直接崩（用 464KB traceback 刷屏的那种）。
    这种情况必须退回串行，否则整个工具在交互式环境里不可用。
    """
    import __main__
    return bool(getattr(__main__, "__file__", None)) and os.path.exists(__main__.__file__)


def golden_all_rows(batches=None, n_jobs=8):
    """并行评估一批批次的产量/崩溃指标，返回 rows（按 batch 升序）。

    batches 默认 86 批（golden_params.GOLDEN_ALL）；n_jobs<=1、只有 1 批、
    或当前 __main__ 不是真实文件（spawn 不可用）时退回串行。
    """
    if batches is None:
        from golden_params import GOLDEN_ALL
        batches = list(GOLDEN_ALL)
    batches = [int(b) for b in batches]
    jobs = [(b, None) for b in batches]

    use_pool = (n_jobs and n_jobs > 1 and len(jobs) > 1 and _spawn_usable())
    if use_pool:
        import multiprocessing as mp
        try:
            ctx = mp.get_context("spawn")   # Windows 默认即 spawn，显式写出以便跨平台一致
            with ctx.Pool(processes=min(int(n_jobs), len(jobs))) as pool:
                rows = pool.map(_golden_worker, jobs, chunksize=1)
        except Exception as e:              # 池化失败不阻塞：退回串行（慢但正确）
            print(f"[golden_all_rows] 并行失败({type(e).__name__}: {e})，退回串行")
            rows = [_golden_worker(j) for j in jobs]
    else:
        rows = [_golden_worker(j) for j in jobs]
    return sorted(rows, key=lambda r: r["batch"])


def summarize_rows(rows):
    """rows → (rmse, within5 批号, catastrophic 批号)。判据与 GOAL §4.1 一致：
    非 catastrophic 且 |yield_err| ≤ 5%。"""
    errs = [r["yield_err"] for r in rows]
    rmse = float(np.sqrt(np.mean(np.square(errs)))) if errs else float("nan")
    within5 = [r["batch"] for r in rows
               if r["crash"] != "catastrophic" and abs(r["yield_err"]) <= 0.05]
    catastrophic = [r["batch"] for r in rows if r["crash"] == "catastrophic"]
    return rmse, sorted(within5), sorted(catastrophic)


def main():
    ap = argparse.ArgumentParser(description="V3 黄金集校验")
    ap.add_argument("--batches", type=int, nargs="*", default=None,
                    help="指定批次（默认黄金集）")
    ap.add_argument("--params-file", type=str, default=None,
                    help="参数 JSON 文件路径")
    ap.add_argument("--output", type=str, default=None,
                    help="输出 CSV 路径")
    ap.add_argument("--all86", action="store_true",
                    help="跑 86 批全量（golden_params.GOLDEN_ALL），并行")
    ap.add_argument("--jobs", type=int, default=8, help="并行进程数（--all86 生效，默认 8）")
    ap.add_argument("--json-out", type=str, default=None, help="汇总结果写入 JSON")
    args = ap.parse_args()

    if args.all86:
        import time
        t0 = time.time()
        rows = golden_all_rows(n_jobs=args.jobs)
        rmse, within5, cat = summarize_rows(rows)
        elapsed = time.time() - t0
        print(f"=== 86 批并行复验（{args.jobs} 进程）===")
        print(f"批数 {len(rows)}｜耗时 {elapsed:.1f}s｜RMSE {rmse*100:.3f}%｜"
              f"within5 {len(within5)}/{len(rows)}｜catastrophic {len(cat)}")
        worst = sorted(rows, key=lambda r: -abs(r["yield_err"]))[:5]
        print("最差 5 批：" + "，".join(
            f"b{r['batch']} {r['yield_err']*100:+.2f}%({r['crash']})" for r in worst))
        if args.json_out:
            with open(args.json_out, "w", encoding="utf-8") as f:
                json.dump({"meta": {"n": len(rows), "jobs": args.jobs,
                                    "elapsed_s": round(elapsed, 1),
                                    "criterion": "非 catastrophic 且 |err|<=5%"},
                           "rmse_pct": round(rmse * 100, 3),
                           "within5": within5, "catastrophic": cat,
                           "rows": rows}, f, ensure_ascii=False, indent=1)
            print(f"已写入 {args.json_out}")
        return

    params = load_params(args.params_file)
    batches = args.batches if args.batches else GOLDEN_NORMAL + GOLDEN_FAULT

    print(f"=== V3 黄金集校验 ===")
    print(f"参数: {params}")
    print(f"批次: {batches}")
    print()

    results = []
    for b in batches:
        r = validate_batch(b, params)
        crash_str = "CRASH" if r["crashed"] else "ok"
        print(f"Batch {b:3d}: yield={r['yield_sim']:>12,.0f} "
              f"(V3={r['yield_v3']:>12,.0f}, err={r['yield_rel_err']:+.1%}) "
              f"X_RMSE={r['x_rmse']:.2f} {crash_str} (CO2d={r['co2d_max']:.2f})")
        results.append(r)

    # 汇总
    ok = [r for r in results if not r["crashed"]]
    crashed = [r for r in results if r["crashed"]]
    print(f"\n=== 汇总 ===")
    print(f"正常: {len(ok)}/{len(results)} 批未崩溃")
    print(f"崩溃: {len(crashed)} 批 (CO2d > {CO2D_THRESHOLD})")
    if ok:
        errs = [r["yield_rel_err"] for r in ok]
        print(f"产率偏差 RMSE: {np.sqrt(np.mean(np.square(errs))):.2%}")
        print(f"产率偏差范围: {min(errs):+.1%} ~ {max(errs):+.1%}")

    # 保存结果
    if args.output:
        rows = []
        for r in results:
            row = {"batch": r["batch"], "yield_sim": r["yield_sim"],
                   "yield_v3": r["yield_v3"], "yield_rel_err": r["yield_rel_err"],
                   "crashed": r["crashed"], "co2d_max": r["co2d_max"],
                   "x_rmse": r["x_rmse"]}
            rows.append(row)
        pd.DataFrame(rows).to_csv(args.output, index=False, encoding="utf-8-sig")
        print(f"结果已保存: {args.output}")


if __name__ == "__main__":
    main()
