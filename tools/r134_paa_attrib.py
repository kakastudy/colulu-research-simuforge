# -*- coding: utf-8 -*-
"""R134 T3: PAA_offline 归因 —— "生成侧（摄取/降解动力学）"还是"测量侧（取样/化验口径）"。

背景：
  R132/R133 把 PAA_offline 判为 C 类（R² 0.3775、nRMSE 28.94%、gain 1.053、lag 0.0h），
  结论是"形状本身错，参数救不回"。但"C 类"只说明**不该扫参**，没回答**错在哪一侧**：
    - 生成侧错：模型缺少/搞错了 PAA 的消耗爆发或降解支路 → 要改 ODE（V1+）
    - 测量侧错：模型对、化验口径（取样滞后、母液/总酸区分、单位）不对 → 只改对齐/换算
  这两者的处置完全不同，必须先判侧再决定要不要动结构。

本工具做的分解（沿用 R133 粘均那套"幅度/形状/相位"思路，但按时间分段）：
    nRMSE² = bias² + shape²                     （均值偏差 vs 动态形状）
    shape 再拆：gain 校正后残差 = 真形状残差；gain 校正掉的量 = 纯幅度
    分段：早期(≤60h，摄取高峰) / 中期(60–150h) / 晚期(>150h)
    
  判侧证据（预先登记）：
    (1) 摄取相关：gain 校正后的 |残差| 与该时刻 |dPAA/dt| 的相关系数 ρ_up。
        ρ_up 高（≥0.5）→ 误差随摄取速率放大 → **生成侧**（摄取动力学）
    (2) 凹陷真伪：化验序列是否存在"先降后升"的谷（dip = min/max，前 120h）；
        模型是否同样有谷。化验有谷、模型无 → 生成侧缺消耗爆发；
        模型有谷、化验无 → 测量侧（或模型过度消耗）。
    (3) 分段残差：若残差集中在早期且晚期几乎为零 → 生成侧（起始动力学）；
        若各段等比例 → 标度/口径（测量侧）。
    (4) 平台期水平：晚期（>150h，摄取近零）的 bias 若仍显著 → 口径/单位问题（测量侧）。

用法：
    python tools/r134_paa_attrib.py
    python tools/r134_paa_attrib.py --batches 8,27,92
"""
import argparse
import glob
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
CACHE = os.path.join(ROOT, "platform", ".cache")

SEGMENTS = [("early", 0.0, 60.0), ("mid", 60.0, 150.0), ("late", 150.0, 1e9)]
DIP_WINDOW_H = 120.0


def _r2(x, y):
    if np.std(x) < 1e-12 or np.std(y) < 1e-12:
        return None
    b, a = np.polyfit(x, y, 1)
    pred = a + b * x
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    return None if ss_tot < 1e-12 else 1.0 - ss_res / ss_tot


def analyse_batch(path):
    d = json.load(open(path, encoding="utf-8"))
    t = np.asarray(d["t"], float)
    sim = np.asarray(d["sim"]["PAA"], float)
    off = d["off"].get("PAA") or []
    if len(off) < 6:
        return None
    ot = np.asarray([p[0] for p in off], float)
    ov = np.asarray([p[1] for p in off], float)
    # 离线 4h 化验滞后：t 时刻的化验值对应 t+4h 的模型状态（与 D6/分类器口径一致）
    sv = np.interp(ot + 4.0, t, sim)

    m_off = float(np.mean(ov))
    if abs(m_off) < 1e-9:
        return None
    m_sim = float(np.mean(sv))

    rmse = float(np.sqrt(np.mean((sv - ov) ** 2)))
    nrmse = rmse / abs(m_off) * 100.0
    bias_pct = (m_sim - m_off) / abs(m_off) * 100.0
    r2 = _r2(sv, ov)

    # gain 校正（最小二乘过原点 k：k·sim ≈ off）后的形状残差
    #   k = argmin ||k·sim − off||² ⇒ k = Σ(sim·off)/Σ(sim²)
    #   校正残差取 k·sim − off（把模型缩到化验口径上比，才叫"纯形状"）
    gain = float(np.sum(sv * ov) / max(np.sum(sv * sv), 1e-12))
    res_g = gain * sv - ov          # 校正后残差（对幅度免疫）
    shape_after_gain = float(np.sqrt(np.mean(res_g ** 2))) / abs(m_off) * 100.0
    # 幅度部分：gain 校正前后面貌差异
    amp_component = abs(m_sim / m_off - 1.0) * 100.0

    # ---- 分段（用 gain 校正后残差衡量"纯形状"，同时保留原始段误差）----
    seg = {}
    for name, lo, hi in SEGMENTS:
        m = (ot >= lo) & (ot < hi)
        if m.sum() < 2:
            seg[name] = None
            continue
        seg[name] = {
            "n": int(m.sum()),
            "bias_pct": round(float(np.mean(sv[m] - ov[m])) / abs(m_off) * 100, 2),
            "raw_nrmse": round(float(np.sqrt(np.mean((sv[m] - ov[m]) ** 2))) / abs(m_off) * 100, 2),
            "shape_nrmse": round(float(np.sqrt(np.mean(res_g[m] ** 2))) / abs(m_off) * 100, 2),
        }

    # ---- 摄取相关：残差幅度 vs 该点摄取速率 ----
    dP = np.gradient(sim, t)
    dp_at = np.interp(ot + 4.0, t, np.abs(dP))
    rho_up = None
    if np.std(dp_at) > 1e-12 and np.std(np.abs(res_g)) > 1e-12:
        rho_up = float(np.corrcoef(np.abs(res_g), dp_at)[0, 1])

    # ---- 凹陷真伪（前 120h）----
    mw = ot <= DIP_WINDOW_H
    dip_off = float(ov[mw].min() / max(ov[mw].max(), 1e-9)) if mw.any() else None
    sw = (t + 4.0) <= DIP_WINDOW_H
    dip_sim = float(sim[sw].min() / max(sim[sw].max(), 1e-9)) if sw.any() else None

    # ---- 残差形态：平（常偏置/口径）还是波（结构化动力学）----
    # 把 gain 校正后的相对残差按 12h 分箱取均值：常数偏置 → 箱均值几乎不变；
    # 结构性错 → 箱均值随批次阶段变号、出现波峰波谷。
    binm = []
    for h0 in range(0, 240, 12):
        mbin = (ot >= h0) & (ot < h0 + 12)
        if mbin.sum():
            binm.append(float(np.mean(res_g[mbin]))) 
    res_level = float(np.mean(res_g)) / abs(m_off) * 100.0
    res_wave = float(np.std(binm)) / abs(m_off) * 100.0 if binm else 0.0
    res_rms = float(np.sqrt(np.mean(res_g ** 2))) / abs(m_off) * 100.0
    wave_share = res_wave / max(res_rms, 1e-9)
    res_profile = {int(h0): round(float(np.mean(res_g[(ot >= h0) & (ot < h0 + 12)])) / abs(m_off) * 100, 2)
                   for h0 in range(0, 240, 12) if ((ot >= h0) & (ot < h0 + 12)).sum()}

    # ---- 判侧（按形态，不按误差大小）----
    why = []
    if shape_after_gain <= 12.0:
        side = "scale_only"
        why.append(f"gain 校正后残差 {shape_after_gain:.1f}% ≤12% → 仅幅度/口径，可换算修正")
    elif wave_share >= 0.60 and res_wave >= 8.0:
        side = "generation"
        why.append(f"残差呈结构化波形（箱均值 std {res_wave:.1f}% 占 RMS {wave_share:.0%}，"
                   f"水平分量仅 {res_level:+.1f}%）→ 生成侧动力学形状错")
    else:
        side = "measurement"
        why.append(f"残差近似常数偏置（波形 std {res_wave:.1f}% / RMS {res_rms:.1f}%，"
                   f"水平 {res_level:+.1f}%）→ 测量侧/口径")
    if rho_up is not None and rho_up >= 0.5:
        why.append(f"且残差随摄取速率放大 (ρ={rho_up:.2f})")
    if dip_off is not None and dip_sim is not None:
        if dip_off < 0.85 and dip_sim >= 0.95:
            why.append(f"化验有谷({dip_off:.2f})模型无谷({dip_sim:.2f})")
        elif dip_sim < 0.85 and dip_off >= 0.95:
            why.append(f"模型有谷({dip_sim:.2f})化验无谷({dip_off:.2f})")

    return {
        "n_off": int(len(ov)), "nrmse": round(nrmse, 2), "r2": None if r2 is None else round(r2, 3),
        "bias_pct": round(bias_pct, 2), "gain": round(gain, 3),
        "amp_component_pct": round(amp_component, 2),
        "shape_after_gain_pct": round(shape_after_gain, 2),
        "res_level_pct": round(res_level, 2), "res_wave_pct": round(res_wave, 2),
        "wave_share": round(wave_share, 3),
        "rho_uptake": None if rho_up is None else round(rho_up, 3),
        "dip_off": None if dip_off is None else round(dip_off, 3),
        "dip_sim": None if dip_sim is None else round(dip_sim, 3),
        "segments": seg, "res_profile": res_profile,
        "side": side, "why": "; ".join(why),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", default="")
    ap.add_argument("--out", default=os.path.join(ROOT, "runs", "p3", "r134_paa_attrib.json"))
    args = ap.parse_args()

    if args.batches:
        files = [os.path.join(CACHE, f"b{int(b):02d}.json") for b in args.batches.split(",")]
    else:
        files = sorted(glob.glob(os.path.join(CACHE, "b*.json")))

    print("=" * 104)
    print("R134 T3 PAA_offline 归因 —— 生成侧 vs 测量侧")
    print(f"批数 {len(files)}；离线滞后 4h；误差分解 nRMSE² = bias² + shape²")
    print("=" * 104, flush=True)

    per_batch = {}
    for f in files:
        b = int(os.path.basename(f)[1:3])
        try:
            r = analyse_batch(f)
        except Exception as e:
            r = {"error": str(e)}
        if r:
            per_batch[b] = r

    ok = {b: r for b, r in per_batch.items() if "error" not in r}
    if not ok:
        print("无可分析批次")
        return

    def med(key):
        v = [r[key] for r in ok.values() if r.get(key) is not None]
        return float(np.median(v)) if v else float("nan")

    print(f"\n{'批':>3s} {'nRMSE':>6s} {'R²':>6s} {'bias%':>7s} {'gain':>6s} "
          f"{'shape':>7s} {'ρ_up':>6s} {'谷off':>6s} {'谷sim':>6s} {'early':>7s} {'late':>7s}  侧")
    print("-" * 104)
    for b in sorted(ok):
        r = ok[b]
        e = r["segments"].get("early") or {}
        l = r["segments"].get("late") or {}
        print(f"{b:>3d} {r['nrmse']:>6.1f} {(r['r2'] if r['r2'] is not None else float('nan')):>6.2f} "
              f"{r['bias_pct']:>7.1f} {r['gain']:>6.2f} {r['shape_after_gain_pct']:>7.1f} "
              f"{(r['rho_uptake'] if r['rho_uptake'] is not None else float('nan')):>6.2f} "
              f"{(r['dip_off'] if r['dip_off'] is not None else float('nan')):>6.2f} "
              f"{(r['dip_sim'] if r['dip_sim'] is not None else float('nan')):>6.2f} "
              f"{e.get('shape_nrmse', float('nan')):>7.1f} {l.get('shape_nrmse', float('nan')):>7.1f}  {r['side']}")

    sides = {}
    for r in ok.values():
        sides[r["side"]] = sides.get(r["side"], 0) + 1

    dip_cases = [r for r in ok.values() if r["dip_off"] is not None and r["dip_sim"] is not None]
    dip_off_only = sum(1 for r in dip_cases if r["dip_off"] < 0.85 and r["dip_sim"] >= 0.95)
    dip_sim_only = sum(1 for r in dip_cases if r["dip_sim"] < 0.85 and r["dip_off"] >= 0.95)
    dip_both = sum(1 for r in dip_cases if r["dip_off"] < 0.85 and r["dip_sim"] < 0.85)

    summary = {
        "n": len(ok),
        "nrmse_med": round(med("nrmse"), 2),
        "r2_med": round(med("r2"), 3),
        "gain_med": round(med("gain"), 3),
        "bias_med": round(med("bias_pct"), 2),
        "shape_after_gain_med": round(med("shape_after_gain_pct"), 2),
        "rho_uptake_med": round(med("rho_uptake"), 3),
        "res_level_med": round(med("res_level_pct"), 2),
        "res_wave_med": round(med("res_wave_pct"), 2),
        "wave_share_med": round(med("wave_share"), 3),
        "sides": sides,
        "dip": {"n": len(dip_cases), "off_only": dip_off_only,
                "sim_only": dip_sim_only, "both": dip_both},
    }
    se = [r["segments"]["early"]["shape_nrmse"] for r in ok.values() if r["segments"].get("early")]
    sm = [r["segments"]["mid"]["shape_nrmse"] for r in ok.values() if r["segments"].get("mid")]
    sl = [r["segments"]["late"]["shape_nrmse"] for r in ok.values() if r["segments"].get("late")]
    summary["seg_shape_nrmse_med"] = {"early": round(float(np.median(se)), 2) if se else None,
                                      "mid": round(float(np.median(sm)), 2) if sm else None,
                                      "late": round(float(np.median(sl)), 2) if sl else None}


    # 聚合残差时间轮廓（看清"波"长什么样），只统计有该分箱的批次
    prof_bins = {}
    for r in ok.values():
        for h0, v in r["res_profile"].items():
            prof_bins.setdefault(int(h0), []).append(v)
    prof_med = {str(h): round(float(np.median(v)), 2) for h, v in sorted(prof_bins.items()) if v}
    summary["res_profile_median"] = prof_med

    print("\n" + "=" * 104)
    print("聚合")
    print("=" * 104)
    print(f"  nRMSE 中位 {summary['nrmse_med']:.1f}% | R² 中位 {summary['r2_med']:.3f} | "
          f"gain 中位 {summary['gain_med']:.2f} | bias 中位 {summary['bias_med']:+.1f}%")
    print(f"  分解：水平(常偏置) {summary['res_level_med']:+.1f}% | 波形(结构) {summary['res_wave_med']:.1f}% | "
          f"波形占比 {summary['wave_share_med']:.0%}")
    print(f"  分段形状残差中位：早期 {summary['seg_shape_nrmse_med']['early']}% / "
          f"中期 {summary['seg_shape_nrmse_med']['mid']}% / 晚期 {summary['seg_shape_nrmse_med']['late']}%")
    print(f"  摄取相关 ρ_up 中位 {summary['rho_uptake_med']:.2f}")
    print(f"  凹陷：化验有谷模型无 {dip_off_only}/{len(dip_cases)}、模型有谷化验无 {dip_sim_only}、"
          f"两者都有 {dip_both}")
    print(f"  判侧：{sides}")
    print("\n  聚合残差轮廓（gain 校正后, % of mean，按 12h 分箱中位）:")
    line = "   "
    for h, v in prof_med.items():
        line += f"{h}h:{v:+.0f}  "
        if len(line) > 96:
            print(line)
            line = "   "
    if line.strip():
        print(line)

    out = {"meta": {"n": len(ok), "offline_delay_h": 4.0,
                    "criteria": {"scale_only": "gain 校正后残差 <=12%",
                                 "generation": "箱均值波形 std>=8% 且波形占 RMS>=60%（结构化动力学）",
                                 "measurement": "残差近似常数偏置（波形占比 <60%）"},
                    "segments": [[n, lo, hi] for n, lo, hi in SEGMENTS]},
           "summary": summary, "per_batch": {str(k): v for k, v in per_batch.items()}}
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"\nSaved: {args.out}")


if __name__ == "__main__":
    main()
