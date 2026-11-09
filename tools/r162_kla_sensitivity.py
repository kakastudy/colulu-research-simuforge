# -*- coding: utf-8 -*-
"""R162 / oq#37 —— alpha_kla 批次间随机性（MATLAB 名义 85+10*randn）的量化。

问题（oq#37 原文）：「alpha_kla 批次间随机性（85±10）对复现精度的影响待量化」。

背景事实（本探针自证，不引用记忆）：
  - MATLAB `indpensim_run.m:135`：`alpha_kla = 85 + 10*randn;`（批次级随机，σ=10）
  - 引擎 `golden_params.py` 中 alpha_kla 86 批里 **81 批恒为 85**（从未参与标定）
    ⇒ 引擎对所有批都假设 alpha_kla = 名义值，而 V3 数据的真实值是随机的。

三个子问题：
  Q1 灵敏度：alpha_kla ±1σ(=10) 会把产量偏差推动多少？
  Q2 反解：用 DO2 通道反解每批的隐含 alpha_kla，跨批散布是否真的 ≈ 10？
  Q3 归因：alpha_kla 偏差被逐批标定（mux/mup）吸收了多少？
      （比较「产量」与「DO2」两个指标对 alpha_kla 的灵敏度之比）

纪律（D-78）：
  - 必须有**零信息对照**（同参重复跑 ⇒ 逐位相同；无扰动对照）；
  - 判据必须**双向**（既要有灵敏度非零的批，也要有灵敏度近零的批，
    否则「恒真灵敏度」与「恒零灵敏度」同样是无信息）；
  - 引擎**零改动**（只改传入 params，不动任何源文件）。

用法：
    py tools/r162_kla_sensitivity.py                 # 全量
    py tools/r162_kla_sensitivity.py --batches 8,11  # 冒烟
    py tools/r162_kla_sensitivity.py --klas 75,85,95
输出：
    runs/r162_kla_sensitivity.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))

OUT = os.path.join(ROOT, "runs", "r162_kla_sensitivity.json")

# 黄金集 10 正常 + 2 故障（覆盖正常/边界/故障三种状态）
DEF_BATCHES = [8, 11, 16, 22, 23, 27, 36, 55, 60, 80, 91, 92]
DEF_KLAS = list(range(30, 141, 10))


def _metrics(sim, v3):
    from simulate import yield_metrics, trajectory_metrics
    ym = yield_metrics(sim, v3)
    tm = trajectory_metrics(sim, v3, channels=("DO2", "P", "S", "T"))
    # DO2 抑制诊断：若 sim DO2 始终远离抑制阈值，alpha_kla 就只改 DO2 数值不改动力学
    s_do2 = sim["DO2"].to_numpy(float)
    v_do2 = v3["DO2"].to_numpy(float)
    n = min(len(s_do2), len(v_do2))
    return {
        "rel_err_total": float(ym["rel_err_total"]),
        "total_sim_g": float(ym["total_sim_g"]),
        "total_v3_g": float(ym["total_v3_g"]),
        "P_relrmse": float(tm["P"]["rel_rmse"]) if "P" in tm else float("nan"),
        "DO2_relrmse": float(tm["DO2"]["rel_rmse"]) if "DO2" in tm else float("nan"),
        "S_relrmse": float(tm["S"]["rel_rmse"]) if "S" in tm else float("nan"),
        "T_relrmse": float(tm["T"]["rel_rmse"]) if "T" in tm else float("nan"),
        "sim_DO2_min": float(np.nanmin(s_do2)),
        "sim_DO2_mean": float(np.nanmean(s_do2)),
        "v3_DO2_min": float(np.nanmin(v_do2[:n])),
        "v3_DO2_mean": float(np.nanmean(v_do2[:n])),
    }


def _run_one(job):
    """worker：跑一个 (batch, alpha_kla) 组合，返回指标字典。"""
    b, k = job
    try:
        from simulate import simulate_open_loop, load_batch
        from golden_params import params_for
        base = dict(params_for(b))
        base_kla = float(base.get("alpha_kla", 85.0))
        p = dict(base)
        p["alpha_kla"] = float(k)
        sim, v3 = simulate_open_loop(b, p)
        m = _metrics(sim, v3)
    except Exception as exc:                                          # noqa: BLE001
        m = dict(rel_err_total=float("nan"), total_sim_g=float("nan"),
                 total_v3_g=float("nan"), P_relrmse=float("nan"),
                 DO2_relrmse=float("nan"), S_relrmse=float("nan"),
                 T_relrmse=float("nan"), error=str(exc))
    m.update(batch=b, alpha_kla=float(k), base_alpha_kla=base_kla)
    return m


def _det_one(b):
    """worker：确定性检查 —— 同参连跑两次，P 轨迹须逐位相同。"""
    try:
        from simulate import simulate_open_loop
        from golden_params import params_for
        p = dict(params_for(b))
        p["alpha_kla"] = float(p.get("alpha_kla", 85.0))
        s1, _ = simulate_open_loop(b, p)
        s2, _ = simulate_open_loop(b, p)
        a = s1["P"].to_numpy(float)
        c = s2["P"].to_numpy(float)
        same = bool(np.array_equal(a, c, equal_nan=True))
        det_max = float(np.max(np.abs(a - c)))
    except Exception as exc:                                          # noqa: BLE001
        same, det_max = False, float("nan")
    return dict(batch=b, identical=bool(same), max_abs_diff=det_max)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", default=",".join(str(b) for b in DEF_BATCHES))
    ap.add_argument("--klas", default=",".join(str(k) for k in DEF_KLAS))
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--analyze-only", action="store_true",
                    help="不重跑仿真，读已有 JSON 重算汇总与判据")
    args = ap.parse_args()

    if args.analyze_only:
        with open(args.out, "r", encoding="utf-8") as fh:
            result = json.load(fh)
        analyze(result)
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2, default=str)
        print_result(result, args.out)
        return 0 if result["verdict"] == "PASS" else 1

    batches = [int(x) for x in args.batches.split(",") if x.strip()]
    klas = [float(x) for x in args.klas.split(",") if x.strip()]

    result = dict(round="R162", part="oq37_kla_sensitivity",
                  batches=batches, klas=klas, runs=[], checks=[])

    import multiprocessing as mp

    jobs = [(b, k) for b in batches for k in klas]
    t0 = time.time()
    workers = max(1, min(args.workers, len(jobs)))
    print(f"[r162] {len(jobs)} jobs, workers={workers}", flush=True)
    if workers > 1:
        ctx = mp.get_context("spawn")
        with ctx.Pool(processes=workers) as pool:
            out = pool.map(_run_one, jobs, chunksize=1)
    else:
        out = [_run_one(j) for j in jobs]
    result["runs"] = out
    for r in sorted(out, key=lambda x: (x["batch"], x["alpha_kla"])):
        print(f"[b{r['batch']}] kla={r['alpha_kla']:6.1f} (base {r['base_alpha_kla']:g})  "
              f"yield_err={r['rel_err_total']:+.4%}  "
              f"P_relRMSE={r['P_relrmse']:.4f}  DO2_relRMSE={r['DO2_relrmse']:.4f}",
              flush=True)
    print(f"[r162] sweep done in {round(time.time()-t0,1)}s", flush=True)

    # --- 零信息对照：同参重复跑必须逐位相同（否则灵敏度不可信）---
    det_jobs = batches[:2] + batches[-1:]      # 3 批足够（代表性 + 两端）
    ctx = mp.get_context("spawn")
    with ctx.Pool(processes=min(workers, len(det_jobs))) as pool:
        det = pool.map(_det_one, det_jobs)
    result["determinism_check"] = det
    for d in det:
        print(f"[b{d['batch']}] determinism: identical={d['identical']} "
              f"max|Δ|={d['max_abs_diff']:.3e}", flush=True)

    analyze(result)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2, default=str)
    print_result(result, args.out)
    return 0 if result["verdict"] == "PASS" else 1


def analyze(result):
    """由 result['runs'] 重算 sensitivity 与判据（可脱离仿真单独执行）。"""
    runs = result["runs"]
    by_b = {}
    for r in runs:
        by_b.setdefault(r["batch"], []).append(r)

    sens = []
    for b, rs in sorted(by_b.items()):
        rs = sorted(rs, key=lambda x: x["alpha_kla"])
        k = np.array([r["alpha_kla"] for r in rs], float)
        ye = np.array([r["rel_err_total"] for r in rs], float)
        do = np.array([r["DO2_relrmse"] for r in rs], float)
        pe = np.array([r["P_relrmse"] for r in rs], float)

        def _slope(x, y):
            m = np.isfinite(x) & np.isfinite(y)
            if m.sum() < 2:
                return float("nan")
            return float(np.polyfit(x[m], y[m], 1)[0])

        base_k = rs[0]["base_alpha_kla"]
        # ---- 局部灵敏度：基线档邻域 ±15（≥3 档）----
        # 全局线性拟合会被端点崩溃档（kla 过低 → DO2 抑制 → 产量崩塌）污染，
        # 而「σ=10 的影响」问的是**现役标定附近的一阶灵敏度**，故必须用局部窗口。
        near = [r for r in rs if abs(r["alpha_kla"] - base_k) <= 15.0]
        if len(near) < 3:                      # 邻域不足则退化为最近 3 档
            near = sorted(rs, key=lambda r: abs(r["alpha_kla"] - base_k))[:3]
        kb = np.array([r["alpha_kla"] for r in near], float)
        yb = np.array([r["rel_err_total"] for r in near], float)
        db = np.array([r["DO2_relrmse"] for r in near], float)
        pb = np.array([r["P_relrmse"] for r in near], float)
        local_yield_slope = _slope(kb, yb)
        local_do2_slope = _slope(kb, db)
        local_p_slope = _slope(kb, pb)

        # --- DO2 反解：抛物线插值求谷点 ---
        m = np.isfinite(do)
        kk, dd = k[m], do[m]
        idx = int(np.argmin(dd)) if dd.size else 0
        k_star = float(kk[idx]) if dd.size else float("nan")
        d_min = float(dd[idx]) if dd.size else float("nan")
        if 0 < idx < len(kk) - 1:
            x0v, x1v, x2v = kk[idx - 1], kk[idx], kk[idx + 1]
            y0v, y1v, y2v = dd[idx - 1], dd[idx], dd[idx + 1]
            den = (x0v - x1v) * (x0v - x2v) * (x1v - x2v)
            if den != 0:
                a = (x2v * (y1v - y0v) + x1v * (y0v - y2v) + x0v * (y2v - y1v)) / den
                bb = (x2v ** 2 * (y0v - y1v) + x1v ** 2 * (y2v - y0v)
                      + x0v ** 2 * (y1v - y2v)) / den
                if a > 0:
                    k_star = float(-bb / (2 * a))
        d_edges = float(np.nanmax([dd[0], dd[-1]])) if dd.size else float("nan")
        d_centre = float(np.nanmin(dd[3:-3])) if dd.size > 7 else d_min
        interior = bool(np.isfinite(k_star) and k.min() < k_star < k.max())
        drop = float((d_edges - d_centre) / d_edges) if d_edges and np.isfinite(d_edges) else float("nan")

        # --- 产量口径的最优 kla 与「悬崖跳变」---
        # 注意：全区间最大跳变会被**低传质崩溃区**（kla≈30~60，DO2 抑制 ⇒ 产量崩塌）
        # 主导 ⇒ 那不是「悬崖」而是崩溃，必须把跳变窗口限制在**现役标定邻域**。
        my = np.isfinite(ye)
        k_yield_best = float(k[my][int(np.argmin(np.abs(ye[my])))]) if my.any() else float("nan")
        in_win = np.array([(abs(kk_ - base_k) <= 15.0) for kk_ in k], bool)
        jy = np.abs(np.diff(ye)) * 100.0
        jy_win = jy[in_win[:-1] & in_win[1:]] if jy.size else np.array([0.0])
        j_at = float(k[int(np.argmax(np.where(in_win[:-1] & in_win[1:], jy, -1.0)))]) \
            if jy.size else float("nan")
        max_jump = float(np.nanmax(jy_win)) if jy_win.size else 0.0      # pp（邻域内）

        sens.append(dict(
            batch=b, base_alpha_kla=base_k,
            slope_yield_per_kla=_slope(k, ye),
            slope_DO2relrmse_per_kla=_slope(k, do),
            slope_Prelrmse_per_kla=_slope(k, pe),
            yield_shift_per_sigma=_slope(k, ye) * 10.0,
            DO2_shift_per_sigma=_slope(k, do) * 10.0,
            # **局部**（基线邻域 ±15）σ=10 影响
            yield_shift_per_sigma_local=local_yield_slope * 10.0,
            DO2_shift_per_sigma_local=local_do2_slope * 10.0,
            P_shift_per_sigma_local=local_p_slope * 10.0,
            local_window=[float(kb.min()), float(kb.max())],
            local_n=len(near),
            yield_range=float(np.nanmax(ye) - np.nanmin(ye)),
            best_kla_for_DO2=k_star,
            best_kla_for_yield=k_yield_best,
            do2_vs_yield_kla_gap=(abs(k_star - k_yield_best)
                                  if np.isfinite(k_star) and np.isfinite(k_yield_best)
                                  else float("nan")),
            yield_max_jump_pp=max_jump,
            yield_jump_at_kla=j_at,
            do2_relrmse_at_best=d_centre,
            do2_interior_min=interior,
            do2_edge_drop_frac=drop,
            sim_DO2_min=float(np.nanmin([r.get("sim_DO2_min", np.nan) for r in rs])),
            sim_DO2_mean=float(np.nanmean([r.get("sim_DO2_mean", np.nan) for r in rs])),
            v3_DO2_mean=float(np.nanmean([r.get("v3_DO2_mean", np.nan) for r in rs])),
            n_ok=int(np.isfinite(ye).sum()),
        ))
    result["sensitivity"] = sens

    sy = np.array([s["yield_shift_per_sigma_local"] for s in sens], float)
    sdo = np.array([s["DO2_shift_per_sigma_local"] for s in sens], float)
    kstar = np.array([s["best_kla_for_DO2"] for s in sens], float)
    interior_mask = np.array([s["do2_interior_min"] for s in sens], bool)
    ratio = np.array([abs(sdo[i]) / max(abs(sy[i]), 1e-12) for i in range(len(sens))])

    # 反解 k* 的散布（剔端点批 —— 端点谷 = 曲线单调，不可反解）
    ki = kstar[interior_mask]
    kstar_stats = dict(
        n_all=int(kstar.size), n_interior=int(ki.size),
        mean_all=float(np.nanmean(kstar)),
        std_all=float(np.nanstd(kstar, ddof=1)) if kstar.size > 1 else float("nan"),
        mean_interior=float(np.nanmean(ki)) if ki.size else float("nan"),
        std_interior=float(np.nanstd(ki, ddof=1)) if ki.size > 1 else float("nan"),
        range_interior=float(np.nanmax(ki) - np.nanmin(ki)) if ki.size else float("nan"),
        rel_dev_vs_nominal_sigma10=(float(abs(np.nanstd(ki, ddof=1) - 10.0) / 10.0)
                                    if ki.size > 1 else float("nan")),
    )
    result["kstar_stats"] = kstar_stats

    det = result.get("determinism_check", [])
    n_interior = int(interior_mask.sum())
    n_low_noise = int(np.nansum(np.abs(sy) < 0.02345))
    n_high = int(np.nansum(np.abs(sy) > 0.10))
    high_batches = [s["batch"] for s in sens if abs(s["yield_shift_per_sigma_local"]) > 0.10]
    jump_batches = [s["batch"] for s in sens if s["yield_max_jump_pp"] > 20.0]
    conflict_batches = [s["batch"] for s in sens if s["do2_vs_yield_kla_gap"] > 30.0]
    # 「统一用名义 85」的失配：DO2 最优 kla 与现役 alpha_kla 的距离
    kla_mismatch = np.array([abs(s["best_kla_for_DO2"] - s["base_alpha_kla"]) for s in sens], float)
    n_mismatch20 = int(np.nansum(kla_mismatch > 20.0))

    checks = [
        dict(name="C1 零信息对照：同参重复跑逐位相同（灵敏度测量有效）",
             got=int(sum(1 for d in det if d["identical"])), expect=len(det),
             ok=bool(det) and all(d["identical"] for d in det),
             detail="max|Δ| max = %.3e" % max((d["max_abs_diff"] for d in det), default=float("nan"))),
        dict(name="C2 反解有效性：DO2 relRMSE 曲线存在内点谷（谷在端点=该批不可反解）",
             got="%d/%d 批内点谷" % (n_interior, len(sens)), expect=">=1 批",
             ok=(n_interior >= 1),
             detail="；".join("b%d: k*=%.1f drop=%.1f%%" % (s["batch"], s["best_kla_for_DO2"],
                                                           s["do2_edge_drop_frac"] * 100) for s in sens)),
        dict(name="C3 判据非恒真：反解 k* 的跨批极差 > 0（不是恒定值）",
             got=float(np.nanmax(kstar) - np.nanmin(kstar)), expect=">0",
             ok=bool(np.nanmax(kstar) > np.nanmin(kstar)),
             detail=("k*: " + ", ".join("b%d=%.0f" % (s["batch"], s["best_kla_for_DO2"]) for s in sens))),
        dict(name="C4 口径对比有判别力：DO2 口径的 σ=10 影响 >> 产量口径（中位比值 > 5）",
             got=float(np.nanmedian(ratio)), expect=">5",
             ok=bool(np.nanmedian(ratio) > 5),
             detail=("产量口径 |Δ|/σ 中位 %.6f，DO2 口径 |Δ|/σ 中位 %.5f"
                     % (np.nanmedian(np.abs(sy)), np.nanmedian(np.abs(sdo))))),
        dict(name="C5 口径对比非恒真：比值的跨批离散度 > 0",
             got=float(np.nanstd(ratio)), expect=">0",
             ok=bool(np.nanstd(ratio) > 0),
             detail="比值 std = %.1f" % np.nanstd(ratio)),
        dict(name="C6a 多数批产量口径 σ=10 影响 < 验收噪声底（2.345%）",
             got="%d/%d 批" % (n_low_noise, len(sens)),
             expect=">=%d 批" % max(1, len(sens) // 2),
             ok=(n_low_noise >= max(1, len(sens) // 2)),
             detail="|Δrel_err/σ| 中位 %.6f" % np.nanmedian(np.abs(sy))),
        dict(name="C6b **存在**批产量口径 σ=10 影响 >> 噪声底（>10pp ⇒ 判据有反向判别力）",
             got="%d 批 %s" % (n_high, high_batches), expect=">=1 批",
             ok=(n_high >= 1),
             detail="；".join("b%d: |Δrel_err/σ|=%.4f" % (s["batch"], abs(s["yield_shift_per_sigma_local"]))
                              for s in sens if s["batch"] in high_batches)),
        dict(name="C7 DO2 口径 σ=10 局部影响不可忽略（中位 ≥1% relRMSE）",
             got=float(np.nanmedian(np.abs(sdo))), expect=">=0.01",
             ok=bool(np.nanmedian(np.abs(sdo)) >= 0.01),
             detail=("DO2 relRMSE 的 σ=10 局部影响中位 %.5f，最大 %.5f"
                     % (np.nanmedian(np.abs(sdo)), np.nanmax(np.abs(sdo))))),
        dict(name="C8 判决性：反解 k* 的跨批散布与 MATLAB 名义 σ=10 一致（偏差 ≤50%）",
             got=float(kstar_stats["rel_dev_vs_nominal_sigma10"]), expect="<=0.5",
             ok=bool(kstar_stats["rel_dev_vs_nominal_sigma10"] <= 0.5),
             detail=("剔端点批后 %d 批 k*：mean=%.2f std=%.2f（名义 10）、极差=%.1f"
                     % (kstar_stats["n_interior"], kstar_stats["mean_interior"],
                        kstar_stats["std_interior"], kstar_stats["range_interior"]))),
        dict(name="C9 现役标定邻域内存在「产量崖」（相邻档跳变 > 20pp）",
             got="%d 批 %s" % (len(jump_batches), jump_batches), expect=">=1 批",
             ok=(len(jump_batches) >= 1),
             detail="；".join("b%d: 邻域内跳变 %.1fpp @ kla=%g" % (s["batch"], s["yield_max_jump_pp"],
                                                                 s["yield_jump_at_kla"])
                              for s in sens if s["batch"] in jump_batches)),
        dict(name="C10 「统一用名义 alpha_kla」在 DO2 口径上失配（\|k*−base\\| 中位 > 10）",
             got=float(np.nanmedian(kla_mismatch)), expect=">10",
             ok=bool(np.nanmedian(kla_mismatch) > 10),
             detail=("%d/%d 批失配 >20；逐批 " % (n_mismatch20, len(sens))
                     + ", ".join("b%d:%.0f" % (s["batch"], abs(s["best_kla_for_DO2"] - s["base_alpha_kla"]))
                                 for s in sens))),
        dict(name="C11 「DO2 拟合最优」与「产量口径最优」不一致（两者 kla 相差 >30 的批 ≥1）",
             got="%d 批 %s" % (len(conflict_batches), conflict_batches), expect=">=1 批",
             ok=(len(conflict_batches) >= 1),
             detail="；".join("b%d: DO2 最优 %.0f vs 产量最优 %.0f"
                              % (s["batch"], s["best_kla_for_DO2"], s["best_kla_for_yield"])
                              for s in sens if s["batch"] in conflict_batches)),
    ]
    result["checks"] = checks
    n_ok = sum(1 for c in checks if c["ok"])
    result["n_checks"] = len(checks)
    result["n_pass"] = n_ok
    result["verdict"] = "PASS" if n_ok == len(checks) else "FAIL"
    return result


def print_result(result, out_path):
    sens = result.get("sensitivity", [])
    print("\n---- 汇总 ----")
    for s in sens:
        print("b%3d base=%g [win %g-%g]  dyield/s=%+.6f  dDO2relRMSE/s=%+.5f  "
              "dPrelRMSE/s=%+.5f  k*_DO2=%6.1f  k*_yield=%6.1f  jump=%6.1fpp  interior=%s"
              % (s["batch"], s["base_alpha_kla"], s["local_window"][0], s["local_window"][1],
                 s["yield_shift_per_sigma_local"], s["DO2_shift_per_sigma_local"],
                 s["P_shift_per_sigma_local"], s["best_kla_for_DO2"], s["best_kla_for_yield"],
                 s["yield_max_jump_pp"], s["do2_interior_min"]))
    ks = result.get("kstar_stats", {})
    if ks:
        print("\n反解 k* 散布（剔端点批 %d/%d）：mean=%.2f std=%.2f 极差=%.1f；"
              "与名义 σ=10 的相对偏差 %.1f%%"
              % (ks["n_interior"], ks["n_all"], ks["mean_interior"], ks["std_interior"],
                 ks["range_interior"], ks["rel_dev_vs_nominal_sigma10"] * 100))
    for c in result.get("checks", []):
        print(("  PASS " if c["ok"] else "  FAIL ") + c["name"]
              + (("  [%s]" % c.get("detail", "")) if c.get("detail") else ""))
    print("\nVERDICT: %s  (%d/%d)%s" % (result["verdict"], result["n_pass"], result["n_checks"],
                                         ("  %ss" % result["elapsed_s"]) if result.get("elapsed_s") else ""))
    print("-> %s" % out_path)


if __name__ == "__main__":
    raise SystemExit(main())
