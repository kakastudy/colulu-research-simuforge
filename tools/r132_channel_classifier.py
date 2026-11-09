# -*- coding: utf-8 -*-
"""S1.1 通道诊断分流器 —— 把"误差大"拆成可处置的三类。

动机（R131 的教训）：X_offline 上一轮被判为"结构性耦合、无解"，实际是
"幅度偏差 + 缺衰减项"，一轮参数就把 4 批从 19–33% 打到 8–15%。可见
"nRMSE 大"本身不告诉你该做什么。本工具对每个通道算四个不相关量：

    corr      形状相似度（Pearson，滞后对齐后）
    R²        线性可解释度（sim = a·lab + b 的拟合优度）
    gain      a，幅度增益（1.0 = 幅度对）
    lag_h     残余相位滞后（在 4h 化验滞后之外还剩多少）
    spct      相对幅度偏差 (mean_sim − mean_lab)/mean_lab

按 R² 与 |lag| 分流：

    A 标度型   R² ≥ 0.85 且 |lag| ≤ 2h   → 常数/批级标度即可修，**先做**
    B 动力型   0.60 ≤ R² < 0.85          → 需机制项（如 R131 的衰亡项）
    C 结构型   R² < 0.60                 → 登记，不硬凑

注意 R² 高但 gain 偏离，是纯幅度问题（最便宜）；R² 低说明动态形状本身错了，
再多参数也救不回来（R131 已用 72 个 (μx,μp) 配置证明过这一点）。

用法：
    python tools/r132_channel_classifier.py              # 86 批全量（8 进程）
    python tools/r132_channel_classifier.py --batches 8,11,60
    python tools/r132_channel_classifier.py --serial
"""
import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))
sys.path.insert(0, HERE)

from simulate import simulate_open_loop  # noqa: E402
from golden_params import COMBINED, GOLDEN_ALL, build_params  # noqa: E402
from d6_health_view import (CHANNEL_MAP, OFFLINE_CHANNELS,  # noqa: E402
                            OFFLINE_DELAY_H, health_grade)

# 残余相位搜索范围（在 4h 化验滞后之外）。±8h 足够覆盖喂食/取样口径错位，
# 再大就该怀疑通道定义而不是对齐了。
LAG_SEARCH_H = 8.0
LAG_STEP_H = 0.5


def _interp(sim, col, t_q):
    return np.interp(t_q, sim["time_h"].to_numpy(float), sim[col].to_numpy(float))


def _align(sim, v3, sim_col, v3_col, base_lag):
    """返回 (t_lab, lab, sim_at_t_lab)。base_lag 为已知的固定滞后（离线通道 4h）。"""
    t_lab_all = v3["time_h"].to_numpy(float)
    lab_all = v3[v3_col].to_numpy(float)
    m = np.isfinite(lab_all)
    t_lab = t_lab_all[m]
    lab = lab_all[m]
    if len(t_lab) < 4:
        return None
    sim_v = _interp(sim, sim_col, t_lab + base_lag)
    return t_lab, lab, sim_v


def _fit_r2(x, y):
    """y ≈ α + β·x 的 R²。x 为 sim，y 为 lab。退化返回 None。"""
    if np.std(x) < 1e-12 or np.std(y) < 1e-12:
        return None, None
    beta, alpha = np.polyfit(x, y, 1)
    pred = alpha + beta * x
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    if ss_tot < 1e-12:
        return None, None
    return 1.0 - ss_res / ss_tot, float(beta)


def diagnose_channel(sim, v3, sim_col, v3_col, base_lag):
    """单通道单批 → 诊断量。数据不足返回 None。

    两件事**必须分开**，这是首版写错的地方：
      - nRMSE 只在 base_lag（假定口径）下算，才是可与 D6 对账的误差；
      - lag_h 是独立诊断量（残余相位），只在幅度无关的意义上比较形状。
    首版把 nRMSE 算在"最佳滞后"位置上，等于用搜索到的错位去算误差，
    导致 P 通道报出 119%（D6 实为 15.4%）——搜索本身污染了度量。
    """
    al = _align(sim, v3, sim_col, v3_col, base_lag)
    if al is None:
        return None
    t_lab, lab, sim_base = al

    lab_mean = float(np.mean(lab))
    if abs(lab_mean) < 1e-9:
        return None

    # ---- 误差：只在假定口径下算 ----
    rmse = float(np.sqrt(np.mean((sim_base - lab) ** 2)))
    nrmse = rmse / abs(lab_mean) * 100
    r2_base, beta_base = _fit_r2(sim_base, lab)

    # ---- 残余相位：用 R² 为目标（对幅度免疫，但对错位敏感）----
    # 用 corr 会被单调通道欺骗（任何位移 corr 都 ≈1，argmax 落到区间边界）。
    taus = np.arange(-LAG_SEARCH_H, LAG_SEARCH_H + 1e-9, LAG_STEP_H)
    r2s = []
    for tau in taus:
        v = _interp(sim, sim_col, t_lab + base_lag + tau)
        r2, _ = _fit_r2(v, lab)
        r2s.append(-2.0 if r2 is None else r2)
    r2s = np.asarray(r2s)
    best = float(np.max(r2s))
    # 近似最优集合里取 |τ| 最小的（避免贴边界），容差 0.005 R²
    near = np.abs(r2s - best) <= 0.005
    best_tau = float(taus[near][np.argmin(np.abs(taus[near]))]) if near.any() else 0.0
    # 曲率提示：最优值比端点高出多少（太小说明"滞后不可辨识"）
    edge = max(r2s[0], r2s[-1])
    lag_identifiable = bool(best - edge > 0.01)

    # 对齐到残余相位后的误差："相位能解释多少误差"的量化。
    # 注意它**不是**误差指标（否则等于给通道免费发一个自由度），只用来判断
    # 该通道的问题主要是"错位"还是"形状"。
    v_al = _interp(sim, sim_col, t_lab + base_lag + best_tau)
    nrmse_best = float(np.sqrt(np.mean((v_al - lab) ** 2))) / abs(lab_mean) * 100

    # ---- 形状残差：均值归一并除掉幅度后比 RMSE ----
    mv = float(np.mean(sim_base))
    if abs(mv) < 1e-9:
        shape_err = float("nan")
    else:
        shape_err = float(np.sqrt(np.mean((sim_base / mv - lab / lab_mean) ** 2)) * 100)

    return {"n": int(len(lab)),
            "nrmse": round(nrmse, 2),
            "nrmse_best": round(nrmse_best, 2),
            "r2": round(r2_base, 3) if r2_base is not None else None,
            "gain": round(mv / lab_mean, 3) if abs(lab_mean) > 1e-9 else None,
            "lag_h": round(best_tau, 2),
            "lag_identifiable": lag_identifiable,
            "lag_gain": round(best - edge, 3),
            "bias_pct": round((mv - lab_mean) / abs(lab_mean) * 100, 2),
            "shape_err": None if not np.isfinite(shape_err) else round(shape_err, 2),
            "health": health_grade(nrmse)}


def eval_batch(job):
    """job = (批号, 是否施加 4h 基准滞后)。用元组传参以兼容 Windows spawn。"""
    b, use_base = job
    v3 = pd.read_csv(os.path.join(ROOT, "data", "processed", "batches", f"batch_{b:02d}.csv"))
    sim, _ = simulate_open_loop(b, build_params(COMBINED[b]))   # 必须走 build_params：
    # 直接用 dict(COMBINED[b]) 会漏掉 dist_flag/N_conc_paa/c_oil 等默认装配，
    # b27 因此一度报出 X_off 51.0%（D6 实为 7.9%）。
    out = {}
    for ch, (sc, vc) in CHANNEL_MAP.items():
        if sc not in sim.columns or vc not in v3.columns:
            continue
        base_lag = OFFLINE_DELAY_H if (use_base and ch in OFFLINE_CHANNELS) else 0.0
        r = diagnose_channel(sim, v3, sc, vc, base_lag)
        if r:
            out[ch] = r
    return b, out


def classify(agg):
    """通道级分流。agg 为 86 批该通道诊断量的中位聚合。"""
    r2, lag, gain = agg["r2"], agg["lag_h"], agg["gain"]
    if r2 is None:
        return "C", "R² 不可算（数据退化）"
    if r2 >= 0.85 and abs(lag) <= 2.0:
        why = f"R²={r2:.2f} 高、残余相位 {lag:+.1f}h 小"
        if gain is not None and abs(gain - 1.0) > 0.08:
            why += f"、幅度 {gain:.2f}× 偏离"
            return "A", why + " → **纯标度问题，一轮可修**"
        return "A", why + " → 已接近，仅需微调"
    if r2 >= 0.60:
        return "B", f"R²={r2:.2f}、相位 {lag:+.1f}h → 动力学形状有偏，需机制项"
    return "C", f"R²={r2:.2f}、相位 {lag:+.1f}h → 形状本身错，参数救不回"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", default="")
    ap.add_argument("--serial", action="store_true")
    ap.add_argument("--no-base-lag", action="store_true",
                    help="不给离线通道施加 4h 基准滞后，让残余相位搜索自己找等效滞后")
    ap.add_argument("--out", default=os.path.join(ROOT, "runs", "p3", "r132_channel_class.json"))
    args = ap.parse_args()

    batches = ([int(x) for x in args.batches.split(",")] if args.batches
               else list(GOLDEN_ALL))
    use_base = not args.no_base_lag

    print("=" * 96)
    print("S1.1 通道诊断分流 —— 误差是'标度'、'动力'还是'结构'")
    print(f"批数 {len(batches)}；离线通道基准滞后 {OFFLINE_DELAY_H if use_base else 0.0:.0f}h；"
          f"残余相位搜索 ±{LAG_SEARCH_H}h/{LAG_STEP_H}h")
    print("=" * 96)

    jobs = [(b, use_base) for b in batches]
    if args.serial:
        out = [eval_batch(j) for j in jobs]
    else:
        from multiprocessing import Pool
        with Pool(min(8, os.cpu_count() or 1)) as pool:
            out = pool.map(eval_batch, jobs, chunksize=1)

    per_batch = {str(b): rec for b, rec in out}

    # ---- 通道级聚合 ----
    channels = sorted({c for _, rec in out for c in rec})
    summary = {}
    print(f"\n{'通道':>18s} {'n':>3s} {'中位nRMSE':>9s} {'中位R²':>7s} "
          f"{'中位gain':>8s} {'中位lag':>7s} {'中位shape':>9s} {'类':>2s}")
    print("-" * 96)
    rows = []
    for ch in channels:
        recs = [rec[ch] for _, rec in out if ch in rec]
        if not recs:
            continue
        def med(k):
            v = [r[k] for r in recs if r.get(k) is not None]
            return float(np.median(v)) if v else None
        agg = {"n": len(recs), "nrmse": med("nrmse"), "r2": med("r2"),
               "gain": med("gain"), "lag_h": med("lag_h"),
               "shape_err": med("shape_err"), "corr": med("corr"),
               "bias_pct": med("bias_pct"),
               "health": {k: sum(1 for r in recs if r["health"] == k)
                          for k in ("healthy", "warning", "critical")}}
        cls, why = classify(agg)
        agg["class"], agg["why"] = cls, why
        summary[ch] = agg
        rows.append((cls, agg["nrmse"] or 0, ch))
        print(f"{ch:>18s} {agg['n']:>3d} {agg['nrmse']:>9.1f} {agg['r2']:>7.2f} "
              f"{agg['gain']:>8.2f} {agg['lag_h']:>+7.1f} {agg['shape_err']:>9.1f} {cls:>2s}")

    print("\n" + "=" * 96)
    print("分流结论（A 先做 → B 需机制 → C 只登记）")
    print("=" * 96)
    for cls in ("A", "B", "C"):
        items = [(c, s) for c, s in summary.items() if s["class"] == cls]
        if not items:
            continue
        print(f"\n[{cls}] {len(items)} 个通道")
        for c, s in sorted(items, key=lambda x: -(x[1]["nrmse"] or 0)):
            print(f"  {c:<18s} nRMSE {s['nrmse']:5.1f}  {s['why']}")

    result = {"meta": {"batches": len(batches),
                       "offline_delay_h": OFFLINE_DELAY_H if use_base else 0.0,
                       "lag_search_h": LAG_SEARCH_H, "lag_step_h": LAG_STEP_H},
              "channels": summary, "per_batch": per_batch}
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print(f"\nSaved: {args.out}")


if __name__ == "__main__":
    main()
