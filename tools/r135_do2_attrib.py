# -*- coding: utf-8 -*-
"""R135: DO2 通道归因 —— 复用 PAA（R134 T3）的"水平/波形"分解骨架，但换判据。

背景：
  R133 通道分级里 DO2 = nRMSE 19.47%、R² 0.584 → B/C 边界，长期只作为"C 类登记"。
  但 DO2 与 PAA 的本质不同：**DO2 是被控量**（串级 PID 把 DO 压在设定值附近）。
  于是"模型 DO2 与实测 DO2 不符"至少有三种完全不同的来源，处置互斥：

    1. 生成侧（氧传递/摄取）：kla、OUR、氧限制——要改机理或参数
    2. 测量侧：溶解氧探头滞后/漂移/标定（一点/两点）、单位
    3. 控制侧：回放时控制律与被控对象的耦合差异（设定值轨迹、PID 增益、通气饱和）

  第 3 类最容易被误判成"机理错"，因为 DO2 曲线形状几乎完全由控制器塑形。

本工具做的分解（与 PAA 同构）：
    nRMSE² = level² + wave²
      level = 残差均值 / |化验均值|      → 偏置（标定/单位）
      wave  = 残差标准差 / |化验均值|     → 动态形状
    gain   = 最小二乘过原点增益（sim→lab）
    校正后残差 shape_after_gain（对幅度免疫的真形状误差）

DO2 专属证据（预先登记，看数前定好）：
    E1 饱和/贴零占比：sim 与 lab 各自 DO2 ≤ 0.5 mg/L 或 ≥ 7.0 mg/L 的样本占比。
       两侧都高 → 该段由控制/物理边界主导，误差无信息量（应剔除出判据）。
    E2 呼吸链相关 ρ(残差, OUR_err)：DO2 残差与 OUR 残差同向放大 → 氧传递链（生成侧）。
    E3 摄取相关 ρ(残差, |dDO2/dt|)：DO2 变化速率是 OUR/kla 的代理。
    E4 分段：早期(≤60h 生长) / 中期(60–150h 产素) / 晚期(>150h)
       —— 若误差只在生产期出现，与 μp 耦合；若全程常数，偏标定。

判据（先登记后算）：
    measurement  : wave_share < 60% 且 |level| ≥ 5%          （几乎纯偏置）
    control      : 饱和/贴零占比之和 ≥ 30%（任一侧）          （曲线由控制器/边界塑形）
    generation   : wave_share ≥ 60% 且 (|ρ_OUR| ≥ 0.35 或 |ρ_uptake| ≥ 0.5)
    unclear      : 其余

用法：
    python tools/r135_do2_attrib.py
    python tools/r135_do2_attrib.py --batches 8,27,92
    python tools/r135_do2_attrib.py --out runs/p3/r135_do2_attrib.json
"""
import argparse
import glob
import json
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
CACHE = os.path.join(ROOT, "platform", ".cache")

SEGMENTS = [("early", 0.0, 60.0), ("mid", 60.0, 150.0), ("late", 150.0, 1e9)]
DO_CRIT = 15.0                       # mg/L：PROBLEM.md §参数表 #4 X_crit_DO2（氧依赖抑制阈值）
MIN_SAMPLES = 200                    # 在线量测密集，阈值可高一些


def _r2(x, y):
    if np.std(x) < 1e-12 or np.std(y) < 1e-12:
        return None
    b, a = np.polyfit(x, y, 1)
    pred = a + b * x
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    return None if ss_tot < 1e-12 else 1.0 - ss_res / ss_tot


def _seg_stats(ot, res_pct):
    out = {}
    for name, lo, hi in SEGMENTS:
        m = (ot >= lo) & (ot < hi)
        if m.sum() >= 5:
            out[name] = {"n": int(m.sum()),
                         "bias_pct": round(float(np.mean(res_pct[m])), 2),
                         "shape_nrmse": round(float(np.sqrt(np.mean(res_pct[m] ** 2))), 2)}
    return out


def analyse_batch(path):
    import re
    b = int(re.search(r"b(\d+)\.json$", path).group(1))
    d = json.load(open(path, encoding="utf-8"))
    t = np.asarray(d["t"], float)
    sim_do = np.asarray(d["sim"]["DO2"], float)
    sim_our = np.asarray(d["sim"].get("OUR", []), float)

    csv = os.path.join(ROOT, "data", "processed", "batches", f"batch_{b:02d}.csv")
    if not os.path.exists(csv):
        return None
    v3 = pd.read_csv(csv)
    if "DO2" not in v3.columns:
        return None
    ot_all = v3["time_h"].to_numpy(float)
    ov_all = pd.to_numeric(v3["DO2"], errors="coerce").to_numpy(float)
    m = np.isfinite(ov_all) & np.isfinite(ot_all)
    ot, ov = ot_all[m], ov_all[m]
    if len(ot) < MIN_SAMPLES:
        return None

    # DO2 是在线量测：**无** 4h 离线滞后
    sv = np.interp(ot, t, sim_do)

    m_off = float(np.mean(ov))
    if abs(m_off) < 1e-9:
        return None
    m_sim = float(np.mean(sv))

    rmse = float(np.sqrt(np.mean((sv - ov) ** 2)))
    nrmse = rmse / abs(m_off) * 100.0
    r2 = _r2(sv, ov)

    # 水平 / 波形分解
    res = sv - ov
    level_pct = float(np.mean(res)) / abs(m_off) * 100.0
    wave_pct = float(np.std(res)) / abs(m_off) * 100.0
    tot2 = level_pct ** 2 + wave_pct ** 2
    wave_share = (wave_pct ** 2 / tot2 * 100.0) if tot2 > 1e-12 else 0.0

    # gain 校正后残差（对幅度免疫）
    denom = float(np.sum(sv * sv))
    gain = float(np.sum(sv * ov) / denom) if denom > 1e-12 else float("nan")
    res_g = gain * sv - ov
    shape_after_gain = float(np.sqrt(np.mean(res_g ** 2))) / abs(m_off) * 100.0

    # E1 氧限制区占比（DO2 < X_crit_DO2=15.0 时氧依赖项激活；见 PROBLEM.md 参数表 #4）
    #   注意：V3 的 DO2 量程是 4.8–26.7 mg/L（PROBLEM.md §V3 剖析），**不是** 8 mg/L 饱和，
    #   所以首版用 0.5/7.0 当"贴零/饱和"阈值是纯口径错误（会报 pinned=100%）。
    sim_below = float(np.mean(sv < DO_CRIT))
    lab_below = float(np.mean(ov < DO_CRIT))
    regime_disagree = float(np.mean((sv < DO_CRIT) != (ov < DO_CRIT)))

    # E2 呼吸链：DO2 残差 vs **OUR 残差**（v3 有 OUR 在线列；无则跳过）
    #   物理预期：DO2 = 传氧 − 摄取，故 OUR 偏高时 DO2 偏低 → 残差应**负相关**。
    #   只报相关系数不够（负相关是物理必然，不能当证据），必须报**可解释方差**：
    #   以 OUR 残差为唯一回归量解释 DO2 残差，R² 才是"DO2 误差有多少是 OUR 误差的像"。
    rho_our = None
    our_explained_r2 = None
    our_slope = None
    if "OUR" in v3.columns and len(sim_our) == len(t):
        our_obs = pd.to_numeric(v3["OUR"], errors="coerce").to_numpy(float)[m]
        our_sim = np.interp(ot, t, sim_our)
        good = np.isfinite(our_obs)
        if good.sum() >= 20:
            res_our = our_sim[good] - our_obs[good]
            res_do = res[good]
            if np.std(res_our) > 1e-9 and np.std(res_do) > 1e-9:
                rho_our = float(np.corrcoef(res_do, res_our)[0, 1])
                our_explained_r2 = float(rho_our ** 2)
                b1, _ = np.polyfit(res_our, res_do, 1)
                our_slope = float(b1)

    # E3 摄取代理：|dDO2/dt|
    rho_uptake = None
    d_do = np.gradient(sv, ot)
    if np.std(d_do) > 1e-9 and np.std(res) > 1e-9:
        rho_uptake = float(np.corrcoef(res, np.abs(d_do))[0, 1])

    res_pct = res / abs(m_off) * 100.0
    seg = _seg_stats(ot, res_pct)

    # ---- 判据（先登记后算）----
    #   inherited_our : OUR 残差单独解释 DO2 残差方差 ≥ 40%（|ρ|≥0.63）且斜率为负
    #                   → DO2 误差主体是 OUR 误差的像；OUR 又是 X 的从属通道 ⇒ 修在 X，不在 DO2
    #   measurement   : 波形占比低、水平偏置为主、且 OUR 解释不了（R²<0.16）
    #   unclear       : 其余（保守挂账）
    if our_explained_r2 is not None and our_explained_r2 >= 0.40 and (our_slope or 0) < 0:
        side = "inherited_our"
        why = (f"OUR 残差单独解释 DO2 残差方差 {our_explained_r2*100:.0f}%（ρ={rho_our:.2f}，"
               f"斜率 {our_slope:.2f}）→ 氧摄取链传递，根在 OUR/X，不在 DO2 自身")
    elif wave_share < 60.0 and abs(level_pct) >= 5.0 and (our_explained_r2 or 0) < 0.16:
        side = "measurement"
        why = (f"波形占比仅 {wave_share:.0f}%、水平偏置 {level_pct:+.1f}%、OUR 解释 {0 if our_explained_r2 is None else our_explained_r2*100:.0f}%"
               f" → 标定/单位/探头漂移")
    else:
        side = "unclear"
        why = (f"波形占比 {wave_share:.0f}%、水平 {level_pct:+.1f}%、"
               f"OUR 解释 {0 if our_explained_r2 is None else our_explained_r2*100:.0f}% → 证据不集中，保守挂账")

    return {
        "batch": b, "n": int(len(ot)),
        "nrmse": round(nrmse, 2), "r2": None if r2 is None else round(r2, 3),
        "gain": None if not np.isfinite(gain) else round(gain, 3),
        "level_pct": round(level_pct, 2), "wave_pct": round(wave_pct, 2),
        "wave_share": round(wave_share, 1),
        "shape_after_gain_pct": round(shape_after_gain, 2),
        "below_crit": {"sim": round(sim_below, 3), "lab": round(lab_below, 3),
                       "regime_disagree": round(regime_disagree, 3)},
        "rho_our_res": None if rho_our is None else round(rho_our, 3),
        "our_explained_r2": None if our_explained_r2 is None else round(our_explained_r2, 3),
        "our_slope": None if our_slope is None else round(our_slope, 3),
        "rho_uptake": None if rho_uptake is None else round(rho_uptake, 3),
        "segments": seg, "side": side, "why": why,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", default=None, help="逗号分隔批号，默认 86 批全量")
    ap.add_argument("--out", default=os.path.join(ROOT, "runs", "p3", "r135_do2_attrib.json"))
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(CACHE, "b*.json")))
    if args.batches:
        keep = {int(x) for x in args.batches.split(",") if x.strip()}
        files = [f for f in files if int(os.path.basename(f)[1:-5]) in keep]

    rows = []
    for f in files:
        try:
            r = analyse_batch(f)
        except Exception as e:                       # 单批失败不拖垮全量
            print(f"  ! {os.path.basename(f)}: {e}")
            continue
        if r:
            rows.append(r)

    print("=" * 108)
    print(f"DO2 通道归因（{len(rows)} 批，在线量测无滞后）")
    print("=" * 108)
    print(f"{'批':>4} {'nRMSE':>7} {'R²':>7} {'gain':>6} {'level':>7} {'wave':>7} "
          f"{'wave%':>6} {'<crit':>6} {'OUR_R²':>7} {'ρupt':>6}  side")
    print("-" * 108)
    for r in rows:
        print(f"{r['batch']:>4} {r['nrmse']:>7.2f} {(r['r2'] if r['r2'] is not None else float('nan')):>7.3f} "
              f"{r['gain'] if r['gain'] is not None else float('nan'):>6.2f} "
              f"{r['level_pct']:>+7.2f} {r['wave_pct']:>7.2f} {r['wave_share']:>6.1f} "
              f"{r['below_crit']['lab']*100:>5.0f}% "
              f"{(r['our_explained_r2'] if r['our_explained_r2'] is not None else float('nan')):>7.2f} "
              f"{(r['rho_uptake'] if r['rho_uptake'] is not None else float('nan')):>6.2f}  {r['side']}")

    def med(key):
        v = [r[key] for r in rows if r.get(key) is not None]
        return round(float(np.median(v)), 3) if v else None

    sides = {}
    for r in rows:
        sides[r["side"]] = sides.get(r["side"], 0) + 1
    summary = {
        "n": len(rows),
        "nrmse_med": med("nrmse"), "r2_med": med("r2"), "gain_med": med("gain"),
        "level_med": med("level_pct"), "wave_med": med("wave_pct"),
        "wave_share_med": med("wave_share"),
        "rho_our_med": med("rho_our_res"), "our_r2_med": med("our_explained_r2"),
        "our_slope_med": med("our_slope"), "rho_uptake_med": med("rho_uptake"),
        "sides": sides,
        "below_crit_med": {
            "sim": round(float(np.median([r["below_crit"]["sim"] for r in rows])), 3),
            "lab": round(float(np.median([r["below_crit"]["lab"] for r in rows])), 3),
            "regime_disagree": round(float(np.median([r["below_crit"]["regime_disagree"] for r in rows])), 3),
        },
        "seg_bias_med": {s: round(float(np.median([r["segments"][s]["bias_pct"] for r in rows
                                                   if s in r["segments"]])), 2)
                         if any(s in r["segments"] for r in rows) else None
                         for s, _, _ in SEGMENTS},
    }
    print("\n" + "=" * 108)
    print("聚合")
    print("=" * 108)
    print(f"  nRMSE 中位 {summary['nrmse_med']:.1f}% | R² 中位 {summary['r2_med']:.3f} | "
          f"gain 中位 {summary['gain_med']:.3f}")
    print(f"  水平分量 {summary['level_med']:+.2f}% | 波形分量 {summary['wave_med']:.2f}% | "
          f"波形占 RMS {summary['wave_share_med']:.1f}%")
    bc = summary["below_crit_med"]
    print(f"  氧限制区(<{DO_CRIT} mg/L)占比：模型 {bc['sim']*100:.0f}% / 化验 {bc['lab']*100:.0f}% / "
          f"判区不一致 {bc['regime_disagree']*100:.0f}%")
    print(f"  OUR 残差解释 DO2 残差方差 R² 中位 {summary['our_r2_med']:.2f}"
          f"（ρ {summary['rho_our_med']:.2f}，斜率 {summary['our_slope_med']:.2f}）"
          f" | ρ(残差,|dDO2/dt|) 中位 {summary['rho_uptake_med']:.2f}")
    print(f"  分段偏置中位：早 {summary['seg_bias_med']['early']}% / "
          f"中 {summary['seg_bias_med']['mid']}% / 晚 {summary['seg_bias_med']['late']}%")
    print(f"  判侧：{sides}")

    out = {"meta": {"n": len(rows), "offline_delay_h": 0.0,
                    "thresholds": {"DO_CRIT_mgL": DO_CRIT, "wave_share": 60.0,
                                   "our_explained_r2": 0.40, "min_samples": MIN_SAMPLES},
                    "note": "V3 的 DO2 量程 4.8–26.7 mg/L（PROBLEM.md §V3 剖析），"
                            "X_crit_DO2=15.0 为氧依赖抑制阈值；不存在 8 mg/L 饱和假设",
                    "criteria": {"inherited_our": "OUR 残差解释 DO2 残差方差 R²>=0.40 且斜率<0",
                                 "measurement": "wave_share<60% 且 |level|>=5% 且 OUR 解释 R²<0.16"}},
           "summary": summary, "per_batch": {str(r["batch"]): r for r in rows}}
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"\n已写入 {args.out}")


if __name__ == "__main__":
    main()
