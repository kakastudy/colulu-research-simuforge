# -*- coding: utf-8 -*-
"""R136 T1/T3：X 通道（生物量）结构分解 + S 通道（底物）独立评估。

背景（为什么这两个通道要一起做）：
  R133 的通道分级表里 **没有 S**，X_offline 虽被列为 A 类，但 nRMSE 24.6%、gain 1.21、
  bias +21% 是全表最大的"水平"偏差。r135 把 OUR（bias +26.7%）与 DO2（bias −14.2%）
  都判为"X 上游误差的像"，所以 X 是全通道误差链的根。测好 X 之前，任何"通道达标"
  的说法都不成立——这就是 L2 阻断项 5。

本工具做两件事（都不改动引擎，纯读 cache）：

  Part A  X 通道三段分解
    nRMSE² = level² + wave²（沿用 r134/r135 的骨架），但 X 的特殊性在于：
    残差不是"整体高低"，而是**峰前偏高 + 峰后不降**。于是把轨迹切成四段：
        early  (0, 24]    接种与起步
        growth (24, 120]  指数/线性生长
        peak   (120, 168] 峰值平台
        late   (>168]     衰亡段
    每段给 sim/lab 比值中位 → 一眼看出"幅度错"还是"衰减错"。
    另外单独取三个结构量（不依赖分段切点）：
        x0_ratio   首个化验点比值（接种量）
        peak_ratio 峰值比值（生长幅度）
        decay      峰→末的相对跌幅（衰亡强度，lab 与 sim 各算一次）

  Part B  S 通道独立评估
    S 在 fed-batch 期恒在 0.001–0.002 g/L（检测限附近），nRMSE 的分母 |mean(lab)|
    被首段 ~1.2 g/L 的批次段拉高，一旦首段错 0.1 g/L 就会掩盖尾段 2 倍的系统偏差。
    所以 S 不能用 nRMSE 单指标，改用四组指标：
        A1 绝对 RMSE (g/L)                     —— 与量纲无关的硬误差
        A2 合格分母 nRMSE（denom = max|lab|）  —— 用峰而不是均值做分母
        A3 分段：batch 期(≤40h) / fed 期(>40h) 的绝对误差与比值
        A4 事件指标：S>0.5 g/L（底物积累/逃逸）的时长占比，lab vs sim 与不一致时长
    判据（先登记后算）：
        informative  : A2 ≤ 10% 且 A3 fed 期绝对误差 ≤ 0.02 g/L 且 A4 不一致 ≤ 5%
        boundary     : 任一侧 S>0.5 占比 ≥ 30%（曲线被判据/边界塑形，误差无信息量）
        insensitive  : A2 > 10% 但 A3 fed 期绝对误差 ≤ 0.02 g/L（误差全在首段，尾段无信息）
        unclear      : 其余

用法：
    python tools/r136_x_s_channel.py               # A+B 全量 86 批，写 runs/p3/r136_x_s_channel.json
    python tools/r136_x_s_channel.py --part a
    python tools/r136_x_s_channel.py --batches 8,27,92 --print
"""
import argparse
import glob
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
CACHE = os.path.join(ROOT, "platform", ".cache")

X_SEGMENTS = [("early", 0.0, 24.0), ("growth", 24.0, 120.0),
              ("peak", 120.0, 168.0), ("late", 168.0, 1e9)]
S_BATCH_END = 40.0          # batch 期/补料期切点（h）
S_ESCAPE = 0.5              # g/L：底物积累判据（超过即视为逃逸/失控）
S_ABS_TOL = 0.02            # g/L：fed 期"无信息"判据的绝对误差阈值
OFFLINE_DELAY_H = 0.0       # 与 r133_channel_class 一致（延迟扫描 −6~+6h 内 nRMSE 变化 <0.8pt）


def _r2(x, y):
    if np.std(x) < 1e-12 or np.std(y) < 1e-12:
        return None
    b, a = np.polyfit(x, y, 1)
    pred = a + b * x
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    return None if ss_tot < 1e-12 else 1.0 - ss_res / ss_tot


def _segs(tt, sim_v, lab_v):
    out = {}
    for name, lo, hi in X_SEGMENTS:
        m = (tt > lo) & (tt <= hi)
        if m.sum() >= 2:
            s, l = sim_v[m], lab_v[m]
            out[name] = {"n": int(m.sum()),
                         "ratio": round(float(np.median(s / np.where(np.abs(l) < 1e-9, np.nan, l))), 3)
                         if np.any(np.abs(l) >= 1e-9) else None,
                         "sim_mean": round(float(np.mean(s)), 2),
                         "lab_mean": round(float(np.mean(l)), 2),
                         "nrmse": round(float(np.sqrt(np.mean((s - l) ** 2)) / max(np.mean(np.abs(l)), 1e-9)) * 100, 1)}
    return out


# ---------------------------------------------------------------- Part A：X
def part_a(d):
    t = np.asarray(d["t"], float)
    sim = np.asarray(d["sim"]["X"], float)
    off = np.asarray(d["off"]["X"], float)
    if off.size == 0 or off.shape[0] < 6:
        return None
    tt, lab = off[:, 0], off[:, 1]
    sv = np.interp(tt + OFFLINE_DELAY_H, t, sim)

    m_lab = float(np.mean(np.abs(lab)))
    if m_lab < 1e-9:
        return None
    res = sv - lab
    nrmse = float(np.sqrt(np.mean(res ** 2))) / m_lab * 100.0
    level = float(np.mean(res)) / m_lab * 100.0
    wave = float(np.std(res)) / m_lab * 100.0
    tot2 = level ** 2 + wave ** 2
    wave_share = (wave ** 2 / tot2 * 100.0) if tot2 > 1e-12 else 0.0

    denom = float(np.sum(sv * sv))
    gain_lab = float(np.sum(sv * lab) / denom) if denom > 1e-12 else float("nan")   # lab = gain*sim
    shape_after_gain = float(np.sqrt(np.mean((gain_lab * sv - lab) ** 2))) / m_lab * 100.0

    # 三个结构量
    ipk_l = int(np.argmax(lab))
    ipk_s = int(np.argmax(sv))
    x0_ratio = float(sv[0] / lab[0]) if abs(lab[0]) > 1e-9 else float("nan")
    peak_ratio = float(sv[ipk_s] / lab[ipk_l]) if lab[ipk_l] > 1e-9 else float("nan")
    decay_lab = float(lab[-1] / lab[ipk_l] - 1.0) * 100.0
    decay_sim = float(sv[-1] / sv[ipk_s] - 1.0) * 100.0

    # 峰后线性斜率（g/L/h），口径与 r131_harness.x_shape_metrics 一致
    def slope(x, i):
        return float(np.polyfit(tt[i:], x[i:], 1)[0]) if len(tt) - i >= 3 else float("nan")
    return {
        "n": int(len(tt)),
        "nrmse": round(nrmse, 2),
        "r2": None if _r2(sv, lab) is None else round(_r2(sv, lab), 3),
        "level_pct": round(level, 2), "wave_pct": round(wave, 2),
        "wave_share": round(wave_share, 1),
        "gain_lab_over_sim": None if not np.isfinite(gain_lab) else round(gain_lab, 3),
        "gain_sim_over_lab": None if not np.isfinite(gain_lab) else round(1.0 / gain_lab, 3),
        "shape_after_gain_pct": round(shape_after_gain, 2),
        "x0_ratio": None if not np.isfinite(x0_ratio) else round(x0_ratio, 3),
        "peak_ratio": None if not np.isfinite(peak_ratio) else round(peak_ratio, 3),
        "peak_lab": round(float(lab[ipk_l]), 2), "peak_sim": round(float(sv[ipk_s]), 2),
        "t_peak_lab": float(tt[ipk_l]), "t_peak_sim": float(tt[ipk_s]),
        "decay_lab_pct": round(decay_lab, 1), "decay_sim_pct": round(decay_sim, 1),
        "decay_gap_pct": round(decay_sim - decay_lab, 1),
        "slope_tail_lab": None if not np.isfinite(slope(lab, ipk_l)) else round(slope(lab, ipk_l), 5),
        "slope_tail_sim": None if not np.isfinite(slope(sv, ipk_s)) else round(slope(sv, ipk_s), 5),
        "segments": _segs(tt, sv, lab),
    }


# ---------------------------------------------------------------- Part B：S
def part_b(d):
    t = np.asarray(d["t"], float)
    lab = np.asarray(d["obs"]["S"], float)
    sim = np.asarray(d["sim"]["S"], float)
    if lab.size != t.size:
        return None
    m = np.isfinite(lab) & np.isfinite(sim)
    if m.sum() < 50:
        return None
    tt, l, s = t[m], lab[m], sim[m]

    rmse_abs = float(np.sqrt(np.mean((s - l) ** 2)))
    denom = max(float(np.max(np.abs(l))), 1e-9)
    nrmse_peak = rmse_abs / denom * 100.0

    mb = tt <= S_BATCH_END
    mf = ~mb
    out = {"n": int(m.sum()),
           "abs_rmse_gL": round(rmse_abs, 5),
           "nrmse_peak_pct": round(nrmse_peak, 2),
           "r2": None if _r2(s, l) is None else round(_r2(s, l), 3),
           "batch_phase": None, "fed_phase": None}

    for tag, mm in (("batch_phase", mb), ("fed_phase", mf)):
        if mm.sum() >= 2:
            la, si = l[mm], s[mm]
            out[tag] = {"n": int(mm.sum()),
                        "lab_mean": round(float(np.mean(la)), 4),
                        "sim_mean": round(float(np.mean(si)), 4),
                        "abs_rmse_gL": round(float(np.sqrt(np.mean((si - la) ** 2))), 5),
                        "ratio": round(float(np.mean(si) / np.mean(la)), 3) if abs(np.mean(la)) > 1e-9 else None}

    # A4 事件指标：底物逃逸（S>0.5 g/L）时长占比与判据不一致
    esc_l, esc_s = float(np.mean(l > S_ESCAPE)), float(np.mean(s > S_ESCAPE))
    disagree = float(np.mean((l > S_ESCAPE) != (s > S_ESCAPE)))
    out["escape"] = {"lab_frac": round(esc_l, 3), "sim_frac": round(esc_s, 3),
                     "disagree_frac": round(disagree, 3)}

    fed_abs = out["fed_phase"]["abs_rmse_gL"] if out["fed_phase"] else 9.9
    if max(esc_l, esc_s) >= 0.30:
        side, why = "boundary", f"任一侧 S>{S_ESCAPE} 占比 ≥30%（lab {esc_l*100:.0f}%/sim {esc_s*100:.0f}%）→ 由判据/边界塑形"
    elif nrmse_peak <= 10.0 and fed_abs <= S_ABS_TOL and disagree <= 0.05:
        side, why = "informative", f"峰分母 nRMSE {nrmse_peak:.1f}%、fed 期绝对误差 {fed_abs:.4f} g/L、逃逸判据不一致仅 {disagree*100:.1f}% → 可作约束通道"
    elif fed_abs <= S_ABS_TOL:
        side, why = "insensitive", f"峰分母 nRMSE {nrmse_peak:.1f}%（>10%）但 fed 期绝对误差仅 {fed_abs:.4f} g/L → 误差集中在首段，尾段无信息量"
    else:
        side, why = "unclear", f"峰分母 nRMSE {nrmse_peak:.1f}%、fed 期绝对误差 {fed_abs:.4f} g/L、不一致 {disagree*100:.1f}% → 证据不集中"
    out["side"], out["why"] = side, why
    return out



# ---------------------------------------------------------------- Part C：X/OUR 跨通道自洽
def part_c(d, batch):
    """独立检验："模型 X 偏高"是模型问题还是化验标度问题？

    OUR 是在线量测，X 是离线化验，两者物理上强关联（OUR ≈ Y_O2_X·dX/dt + m_O2_X·X + ...）。
    若模型只是把 X 整体放大了 k 倍，而比呼吸速率（OUR/X）是准的，那么
        OUR_sim / X_sim  ≈  OUR_lab / X_lab     （比值→1）
    这说明"比活性没错、菌量错了"，且错的方向在两侧一致（在线 OUR 也高）。
    反之若比值显著偏离 1，说明是比呼吸速率本身错（模型机制问题），不能靠缩放 X 解决。
    """
    import pandas as pd
    t = np.asarray(d["t"], float)
    x = np.asarray(d["sim"]["X"], float)
    our = np.asarray(d["sim"]["OUR"], float)
    v3 = pd.read_csv(os.path.join(ROOT, "data", "processed", "batches", f"batch_{batch:02d}.csv"))
    tv = v3["time_h"].to_numpy(float)
    xl = pd.to_numeric(v3["X_offline"], errors="coerce").to_numpy(float)
    ol = pd.to_numeric(v3["OUR"], errors="coerce").to_numpy(float)
    ok = np.isfinite(xl) & np.isfinite(ol)
    if ok.sum() < 6:
        return None
    xl_i = np.interp(tv, tv[ok], xl[ok])
    xs = np.interp(tv, t, x)
    os_ = np.interp(tv, t, our)
    m = ok & (xl_i > 2.0) & (xs > 1e-6)          # 只在菌量已起来的段比，避开接种段小分母
    if m.sum() < 6:
        return None
    r_lab = float(np.median(ol[m] / xl_i[m]))
    r_sim = float(np.median(os_[m] / xl_i[m]))
    return {"n": int(m.sum()),
            "our_per_x_lab": round(r_lab, 4), "our_per_x_sim": round(r_sim, 4),
            "ratio_sim_over_lab": round(r_sim / r_lab, 3) if r_lab > 1e-9 else None,
            "our_amp": round(float(np.mean(os_[m]) / np.mean(ol[m])), 3) if np.mean(ol[m]) > 1e-9 else None,
            "x_amp": round(float(np.mean(xs[m]) / np.mean(xl_i[m])), 3),
            }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", default=None)
    ap.add_argument("--part", default="both", choices=["a", "b", "c", "both", "all"])
    ap.add_argument("--print", dest="do_print", action="store_true")
    ap.add_argument("--out", default=os.path.join(ROOT, "runs", "p3", "r136_x_s_channel.json"))
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(CACHE, "b*.json")))
    if args.batches:
        keep = {int(x) for x in args.batches.split(",") if x.strip()}
        files = [f for f in files if int(os.path.basename(f)[1:-5]) in keep]

    A, B, C = {}, {}, {}
    for f in files:
        b = int(os.path.basename(f)[1:-5])
        d = json.load(open(f, encoding="utf-8"))
        if args.part in ("a", "both", "all"):
            try:
                r = part_a(d)
                if r:
                    A[b] = r
            except Exception as e:
                print(f"  ! A b{b}: {e}")
        if args.part in ("c", "both", "all"):
            try:
                r = part_c(d, b)
                if r:
                    C[b] = r
            except Exception as e:
                print(f"  ! C b{b}: {e}")
        if args.part in ("b", "both", "all"):
            try:
                r = part_b(d)
                if r:
                    B[b] = r
            except Exception as e:
                print(f"  ! B b{b}: {e}")

    def med(rows, key):
        v = [r[key] for r in rows if r.get(key) is not None]
        return round(float(np.median(v)), 3) if v else None

    summary = {}

    if A:
        rows = list(A.values())
        seg_keys = [s[0] for s in X_SEGMENTS]
        summary["X"] = {
            "n": len(rows),
            "nrmse_med": med(rows, "nrmse"), "r2_med": med(rows, "r2"),
            "level_med": med(rows, "level_pct"), "wave_med": med(rows, "wave_pct"),
            "wave_share_med": med(rows, "wave_share"),
            "gain_sim_over_lab_med": med(rows, "gain_sim_over_lab"),
            "shape_after_gain_med": med(rows, "shape_after_gain_pct"),
            "x0_ratio_med": med(rows, "x0_ratio"),
            "peak_ratio_med": med(rows, "peak_ratio"),
            "decay_lab_med": med(rows, "decay_lab_pct"),
            "decay_sim_med": med(rows, "decay_sim_pct"),
            "decay_gap_med": med(rows, "decay_gap_pct"),
            "seg_ratio_med": {k: round(float(np.median([r["segments"][k]["ratio"] for r in rows
                                                        if k in r["segments"] and r["segments"][k]["ratio"]])), 3)
                              if any(k in r["segments"] and r["segments"][k]["ratio"] for r in rows) else None
                              for k in seg_keys},
            "frac_peak_ratio_ge_1p15": round(float(np.mean([r["peak_ratio"] >= 1.15 for r in rows
                                                            if r["peak_ratio"]])), 3),
            "frac_decay_gap_ge_5pt": round(float(np.mean([r["decay_gap_pct"] >= 5.0 for r in rows])), 3),
        }
        print("=" * 104)
        print(f"Part A　X 通道结构分解（{len(rows)} 批）")
        print("=" * 104)
        print(f"{'批':>4} {'nRMSE':>7} {'R²':>6} {'gain':>6} {'level':>7} {'wave':>6} {'shape':>6} "
              f"{'X0r':>6} {'peakR':>6} {'decayL':>7} {'decayS':>7}")
        print("-" * 104)
        worst = sorted(rows, key=lambda r: -(r["peak_ratio"] or 0))
        show = rows[:6] + worst[:4] if args.do_print else []
        for r in show:
            print(f"... {r['nrmse']:>6.1f} {r['r2']:>6.3f} {r['gain_sim_over_lab']:>6.3f} "
                  f"{r['level_pct']:>+7.2f} {r['wave_pct']:>6.2f} {r['shape_after_gain_pct']:>6.2f} "
                  f"{r['x0_ratio']:>6.3f} {r['peak_ratio']:>6.3f} {r['decay_lab_pct']:>7.1f} {r['decay_sim_pct']:>7.1f}")
        s = summary["X"]
        print("\n  汇总：nRMSE 中位 %.1f%% | R² %.3f | gain(sim/lab) %.3f" % (s["nrmse_med"], s["r2_med"], s["gain_sim_over_lab_med"]))
        print("  水平 %+.1f%% / 波形 %.1f%%（波形占 RMS %.0f%%）| 去增益后形状残差 %.1f%%"
              % (s["level_med"], s["wave_med"], s["wave_share_med"], s["shape_after_gain_med"]))
        print("  三段结构量：X0 比 %.3f | 峰值比 %.3f | 衰亡 lab %.1f%% vs sim %.1f%%（缺口 %+.1f pt）"
              % (s["x0_ratio_med"], s["peak_ratio_med"], s["decay_lab_med"], s["decay_sim_med"], s["decay_gap_med"]))
        print("  分段比值中位：" + " | ".join(f"{k} {v}" for k, v in s["seg_ratio_med"].items()))
        print("  峰值比 ≥1.15 的批：%.0f%% | 衰亡缺口 ≥5pt 的批：%.0f%%"
              % (s["frac_peak_ratio_ge_1p15"] * 100, s["frac_decay_gap_ge_5pt"] * 100))

    if B:
        rows = list(B.values())
        sides = {}
        for r in rows:
            sides[r["side"]] = sides.get(r["side"], 0) + 1
        summary["S"] = {
            "n": len(rows),
            "abs_rmse_med": med(rows, "abs_rmse_gL"),
            "nrmse_peak_med": med(rows, "nrmse_peak_pct"),
            "r2_med": med(rows, "r2"),
            "fed_abs_rmse_med": round(float(np.median([r["fed_phase"]["abs_rmse_gL"] for r in rows
                                                       if r["fed_phase"]])), 5),
            "fed_ratio_med": round(float(np.median([r["fed_phase"]["ratio"] for r in rows
                                                    if r["fed_phase"] and r["fed_phase"]["ratio"]])), 3),
            "escape_lab_med": med(rows, "escape") if False else round(float(np.median([r["escape"]["lab_frac"] for r in rows])), 3),
            "escape_sim_med": round(float(np.median([r["escape"]["sim_frac"] for r in rows])), 3),
            "escape_disagree_med": round(float(np.median([r["escape"]["disagree_frac"] for r in rows])), 3),
            "sides": sides,
        }
        print("\n" + "=" * 104)
        print(f"Part B　S 通道独立评估（{len(rows)} 批）")
        print("=" * 104)
        s = summary["S"]
        print("  绝对 RMSE 中位 %.5f g/L | 峰分母 nRMSE 中位 %.1f%% | R² 中位 %.3f"
              % (s["abs_rmse_med"], s["nrmse_peak_med"], s["r2_med"]))
        print("  fed 期绝对误差中位 %.5f g/L | 均值比 %.3f | 逃逸占比 lab %.1f%% / sim %.1f%% / 判据不一致 %.1f%%"
              % (s["fed_abs_rmse_med"], s["fed_ratio_med"],
                 s["escape_lab_med"] * 100, s["escape_sim_med"] * 100, s["escape_disagree_med"] * 100))
        print("  判侧：" + str(sides))

    if C:
        rows = list(C.values())
        summary["C"] = {"n": len(rows),
                        "our_per_x_lab_med": round(float(np.median([r["our_per_x_lab"] for r in rows])), 4),
                        "our_per_x_sim_med": round(float(np.median([r["our_per_x_sim"] for r in rows])), 4),
                        "ratio_med": round(float(np.median([r["ratio_sim_over_lab"] for r in rows
                                                            if r["ratio_sim_over_lab"]])), 3),
                        "ratio_iqr": [round(float(np.percentile([r["ratio_sim_over_lab"] for r in rows
                                                                 if r["ratio_sim_over_lab"]], q)), 3) for q in (25, 75)],
                        "our_amp_med": round(float(np.median([r["our_amp"] for r in rows if r["our_amp"]])), 3),
                        "x_amp_med": round(float(np.median([r["x_amp"] for r in rows])), 3),
                        "frac_ratio_in_0p9_1p1": round(float(np.mean([0.9 <= r["ratio_sim_over_lab"] <= 1.1
                                                                     for r in rows if r["ratio_sim_over_lab"]])), 3)}
        print("\n" + "=" * 104)
        print(f"Part C　X / OUR 跨通道自洽（{len(rows)} 批，X>2 g/L 段）")
        print("=" * 104)
        c = summary["C"]
        print("  OUR/X 中位：化验 %.4f vs 模型 %.4f → 比值 %.3f（IQR %.3f–%.3f）"
              % (c["our_per_x_lab_med"], c["our_per_x_sim_med"], c["ratio_med"], *c["ratio_iqr"]))
        print("  幅度：OUR 放大 %.3f×，X 放大 %.3f× | 比值落在 0.9–1.1 的批占 %.0f%%"
              % (c["our_amp_med"], c["x_amp_med"], c["frac_ratio_in_0p9_1p1"] * 100))

    out = {"meta": {"n": len(files), "offline_delay_h": OFFLINE_DELAY_H,
                    "x_segments": [[n, lo, hi] for n, lo, hi in X_SEGMENTS],
                    "s_batch_end_h": S_BATCH_END, "s_escape_gL": S_ESCAPE, "s_abs_tol_gL": S_ABS_TOL,
                    "note": "S 未进入 r133 通道分级表：nRMSE 的分母 |mean(lab)| 被首段 1.2 g/L 拉高，"
                            "尾段 0.001 g/L 量级的误差被稀释；本 Part B 改用峰分母 + 绝对误差 + 逃逸事件口径"},
           "summary": summary,
           "per_batch_X": {str(k): v for k, v in A.items()},
           "per_batch_S": {str(k): v for k, v in B.items()},
           "per_batch_C": {str(k): v for k, v in C.items()}}
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"\n已写入 {args.out}")


if __name__ == "__main__":
    main()
