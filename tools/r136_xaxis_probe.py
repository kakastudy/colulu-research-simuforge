# -*- coding: utf-8 -*-
"""R136 T2：X 通道「漂移型」误差的反事实探针 —— 能否只修衰减段 / 能否压幅度。

前置事实（R136 T1，86 批 cache 分解）：
    sim/lab 分段比值  early 1.05 → growth 1.08 → peak 1.18 → late 1.36（单调递增）
    lab 峰→末 −12.8%，sim 仅 −0.7%
  ⇒ X 的误差不是"整体标度错"（否则各段比值应相同），而是**累积漂移**：
    模型不缺一个常数倍数，缺的是"停止增长 + 开始衰亡"这两件晚期行为。

同时 R131 已证：(mux,mup) 脊上 72 个配置在 |yield|≤5% 内 X 峰值比恒 ≥1.17
  ⇒ 峰幅度与产量共享 Y_sX，单靠 (mux,mup) 解不开。本工具不再重复那条脊，改问两个新问题：

    Q1 晚期衰亡门控是否**自锁**？
       model.py: _late_death_gate = max(0, 1 - μ_actual/μ_death_ref)
       若 μ 始终高于 μ_ref，门恒 0 → 衰亡永不启动 → μ 更不会降。这是正反馈死角。
       测法：把 mu_death_ref 抬到 1.0（门≈1，等效"无门控"），扫 late_death_rate。
       若这样能得到"衰亡段追上、产量仍在红线内"的配置，说明死锁是主因。

    Q2 压幅度（Y_sX↓）后，产量损失能否由衰亡回收（death_recycle）补回？
       R130n 的负结果是"降 Y_sX 直接把产量推出红线"，但当时没有配合 death_recycle 的碳回流。

判据（先登记后算）：
    fixable_late : |yield_err| ≤ 5% 且 late_ratio ≤ 1.15 且 decay_gap ≤ 4 pt
    yield_blocked: |yield_err| > 5%（改动把产量推出红线）
    no_gain      : |yield_err| ≤ 5% 但 late_ratio > 1.25（改了没用）
    partial      : 其余

用法：
    python tools/r136_xaxis_probe.py
    python tools/r136_xaxis_probe.py --batches 8,27,59 --tag ld2
    python tools/r136_xaxis_probe.py --reanalyse      # 免重跑，只重算判定
"""
import argparse
import json
import os
import sys
from multiprocessing import Pool

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))


LATE_T = 168.0
OUT = os.path.join(ROOT, "runs", "p3", "r136_xaxis_probe.json")

# 6 个配置：base / 三档"无门控"衰亡 / Y_sX↓ / Y_sX↓+衰亡回收
CONFIGS = {
    "base":      {},
    "ld2":       {"late_death_rate": 0.002, "mu_death_ref": 1.0, "death_recycle": 0.3},
    "ld4":       {"late_death_rate": 0.004, "mu_death_ref": 1.0, "death_recycle": 0.3},
    "ld6":       {"late_death_rate": 0.006, "mu_death_ref": 1.0, "death_recycle": 0.3},
    "ysx85":     {"Y_sX": 1.85 * 0.85},
    "ysx85_ld4": {"Y_sX": 1.85 * 0.85, "late_death_rate": 0.004, "mu_death_ref": 1.0, "death_recycle": 0.5},
    # T2c 维持系数：m_s 消耗底物但不产菌也不产素 → 理论上可"降 X 不降 P"的解耦杠杆
    "ms45":      {"m_s": 0.045},
    "ms55":      {"m_s": 0.055},
    "ms065":     {"m_s": 0.065},
    "ms45_ld2":  {"m_s": 0.045, "late_death_rate": 0.002, "death_recycle": 0.3},
    # T2d 底物再分配：(m_s ↑ 降 X、同时抬高 Y_sP 把多出来的底物"扣回"产品) —— 二维解耦测试
    "ms45_ysp110": {"m_s": 0.045, "Y_sP": 0.90 * 1.10},
    "ms45_ysp115": {"m_s": 0.045, "Y_sP": 0.90 * 1.15},
    "ms45_ysp120": {"m_s": 0.045, "Y_sP": 0.90 * 1.20},
    "ms55_ysp120": {"m_s": 0.055, "Y_sP": 0.90 * 1.20},
    "ms55_ysp130": {"m_s": 0.055, "Y_sP": 0.90 * 1.30},
}


def _work(job):
    batch, tag, over = job
    import golden_params as gp
    from simulate import simulate_open_loop, yield_metrics, classify_crash
    import pandas as pd

    params = gp.params_for(batch)
    params.update(over)
    try:
        sim, _ = simulate_open_loop(batch, params)
    except Exception as e:
        return {"batch": batch, "tag": tag, "error": f"{type(e).__name__}: {e}"}

    v3 = pd.read_csv(os.path.join(ROOT, "data", "processed", "batches", f"batch_{batch:02d}.csv"))
    ym = yield_metrics(sim, v3)
    err = ym["rel_err_total"]
    level, reasons = classify_crash(sim, yield_err=err)

    t = np.asarray(sim["time_h"], float)
    x = np.asarray(sim["X"], float)
    our = np.asarray(sim["OUR"], float)
    do2 = np.asarray(sim["DO2"], float)
    lab = pd.to_numeric(v3["X_offline"], errors="coerce").to_numpy(float)
    tv = v3["time_h"].to_numpy(float)
    m = np.isfinite(lab)
    tt, yo = tv[m], lab[m]
    sv = np.interp(tt, t, x)

    seg = {}
    for name, lo, hi in (("early", 0, 24), ("growth", 24, 120), ("peak", 120, LATE_T), ("late", LATE_T, 1e9)):
        mm = (tt > lo) & (tt <= hi)
        if mm.sum() >= 2 and np.all(np.abs(yo[mm]) > 1e-9):
            seg[name] = round(float(np.median(sv[mm] / yo[mm])), 3)

    ipk = int(np.argmax(yo))
    decay_lab = float(yo[-1] / yo[ipk] - 1) * 100
    decay_sim = float(sv[-1] / sv[int(np.argmax(sv))] - 1) * 100
    nrmse = float(np.sqrt(np.mean((sv - yo) ** 2)) / np.mean(np.abs(yo)) * 100)

    # OUR / DO2 偏置（在线量测，无滞后）
    def bias(ch_sim, col):
        obs = pd.to_numeric(v3[col], errors="coerce").to_numpy(float)
        ch_sim = np.interp(tv, t, ch_sim)          # sim 与 v3 行数可能差 1（终末点），统一插值对齐
        good = np.isfinite(obs) & np.isfinite(ch_sim)
        if good.sum() < 20 or abs(np.mean(obs[good])) < 1e-9:
            return None
        return round(float(np.mean(ch_sim[good] - obs[good]) / np.mean(np.abs(obs[good])) * 100), 2)
    our_b = bias(our, "OUR")
    do2_b = bias(do2, "DO2")

    rec = {"batch": batch, "tag": tag,
           "yield_err": None if err is None or not np.isfinite(err) else round(float(err) * 100.0, 3),
           "crash": level, "crash_reasons": reasons,
           "x_nrmse": round(nrmse, 2), "x_peak_ratio": round(float(sv[int(np.argmax(sv))] / yo[ipk]), 3),
           "decay_lab": round(decay_lab, 1), "decay_sim": round(decay_sim, 1),
           "decay_gap": round(decay_sim - decay_lab, 1),
           "x_end_ratio": round(float(sv[-1] / yo[-1]), 3),
           "seg": seg, "our_bias": our_b, "do2_bias": do2_b}
    return rec


def verdict(r):
    ye = r.get("yield_err")
    if r.get("error"):
        return "error"
    if ye is None:
        return "invalid"
    late = r["seg"].get("late")
    gap = r["decay_gap"]
    if abs(ye) > 5.0:
        return "yield_blocked"
    if late is not None and late <= 1.15 and abs(gap) <= 4.0:
        return "fixable_late"
    if late is not None and late > 1.25:
        return "no_gain"
    return "partial"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", default="8,27,36,59,60,92")
    ap.add_argument("--tags", default=None, help="逗号分隔配置名，默认全部")
    ap.add_argument("--reanalyse", action="store_true")
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()

    tags = list(CONFIGS) if not args.tags else [t.strip() for t in args.tags.split(",")]
    batches = [int(x) for x in args.batches.split(",") if x.strip()]

    if args.reanalyse:
        data = json.load(open(args.out, encoding="utf-8"))
        rows = data["rows"] if isinstance(data, dict) else data
    else:
        jobs = [(b, tag, CONFIGS[tag]) for tag in tags for b in batches]
        with Pool(min(args.jobs, len(jobs))) as pool:
            rows = pool.map(_work, jobs, chunksize=1)

    for r in rows:
        r["verdict"] = verdict(r)

    print("=" * 112)
    print(f"X 反事实探针（{len(batches)} 批 × {len(tags)} 配置）")
    print("=" * 112)
    print(f"{'批':>4} {'配置':<11} {'yield%':>8} {'X_nRMSE':>8} {'peakR':>6} {'endR':>6} "
          f"{'decayS':>7} {'gap':>6} {'lateR':>6} {'OURb':>6} {'DO2b':>6}  verdict")
    print("-" * 112)
    for r in sorted(rows, key=lambda x: (x.get("batch") or 0, list(CONFIGS).index(x["tag"]) if x["tag"] in CONFIGS else 9)):
        if r.get("error"):
            print(f"{r['batch']:>4} {r['tag']:<11} ERROR {r['error'][:60]}")
            continue
        seg = r.get("seg") or {}
        print(f"{r['batch']:>4} {r['tag']:<11} "
              f"{(r['yield_err'] if r['yield_err'] is not None else float('nan')):>+8.2f} "
              f"{r['x_nrmse']:>8.1f} {r['x_peak_ratio']:>6.3f} {r['x_end_ratio']:>6.3f} "
              f"{r['decay_sim']:>7.1f} {r['decay_gap']:>+6.1f} {seg.get('late', float('nan')):>6.3f} "
              f"{(r['our_bias'] if r['our_bias'] is not None else float('nan')):>+6.1f} "
              f"{(r['do2_bias'] if r['do2_bias'] is not None else float('nan')):>+6.1f}  {r['verdict']}")

    # 按配置聚合
    print("\n按配置聚合（中位）：")
    print(f"{'配置':<11} {'yield%':>8} {'X_nRMSE':>8} {'peakR':>6} {'lateR':>6} {'gap':>6} {'OURb':>6} {'DO2b':>6}  verdicts")
    summary = {}
    for tag in tags:
        rs = [r for r in rows if r["tag"] == tag and not r.get("error") and r["yield_err"] is not None]
        if not rs:
            continue
        f = lambda k: round(float(np.median([r[k] for r in rs if r[k] is not None])), 3)
        f2 = lambda k, s="seg": round(float(np.median([r[s].get(k) for r in rs if r[s].get(k)])), 3) \
            if any(r[s].get(k) for r in rs) else None
        vs = {}
        for r in rs:
            vs[r["verdict"]] = vs.get(r["verdict"], 0) + 1
        summary[tag] = {"yield_med": f("yield_err"), "x_nrmse_med": f("x_nrmse"),
                        "peak_ratio_med": f("x_peak_ratio"), "late_ratio_med": f2("late"),
                        "decay_gap_med": f("decay_gap"), "our_bias_med": f("our_bias"),
                        "do2_bias_med": f("do2_bias"), "verdicts": vs}
        s = summary[tag]
        print(f"{tag:<11} {s['yield_med']:>+8.2f} {s['x_nrmse_med']:>8.1f} {s['peak_ratio_med']:>6.3f} "
              f"{(s['late_ratio_med'] if s['late_ratio_med'] is not None else float('nan')):>6.3f} "
              f"{s['decay_gap_med']:>+6.1f} "
              f"{(s['our_bias_med'] if s['our_bias_med'] is not None else float('nan')):>+6.1f} "
              f"{(s['do2_bias_med'] if s['do2_bias_med'] is not None else float('nan')):>+6.1f}  {vs}")

    out = {"meta": {"batches": batches, "tags": tags, "configs": CONFIGS,
                    "criteria": {"fixable_late": "|yield|<=5% 且 late_ratio<=1.15 且 |gap|<=4pt",
                                 "yield_blocked": "|yield|>5%", "no_gain": "late_ratio>1.25"}},
           "summary": summary, "rows": rows}
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"\n已写入 {args.out}")


if __name__ == "__main__":
    main()
