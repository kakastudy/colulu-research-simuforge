# -*- coding: utf-8 -*-
"""R137 T1：形态学退化链（A1→A3→A4）为什么恒为零 —— 装配诊断与一阶效应反事实。

## 前置事实（R136 D-6）
    model.py: r_vac = k_vac * a_1 * _vac_gate      （A1→A3）
              r_d4  = mu_a  * a_3                  （A3→A4, mu_a = par[6] = 3.5e-3）
    实测 b56 全时程 debris=(A3+A4)/X = 0.000。
    原因已在参数层确认：**86/86 批黄金参数中 k_vac 从未出现**，`params.get("k_vac", 0.0)`
    取默认 0 → r_vac ≡ 0 → A3 ≡ 0 → r_d4 ≡ 0 → A4 ≡ 0。R130 的"液泡化修复"从未被启用。

## 本轮要回答的三个问题（先登记判据）

    Q1 `r_vac` / `r_d4` 对总生物量 X 有没有一阶效应？
       代码事实：da_3_dt = r_vac - r_d4，da_4_dt = r_d4，二者是**内部转移**，
       且 OUR 用 X_1（总生长率，含四组分求和）与 X_t（含四组分），
       P 用 v_a1 ∝ a_1。⇒ 预期 X 与 OUR 维持项**几乎不变**，只有 P 下降。
       判据 transfer_only : |ΔX_nRMSE| < 1.0 且 |Δyield| > 2%（有副作用）、|ΔpeakR| < 0.03
       判据 x_reducible  : 出现 |ΔpeakR| ≥ 0.05 或 X_nRMSE 降 ≥2 → R136 D-6 方向成立

    Q2 若 X_offline 实际测的是**活菌**（a0+a1），打开 r_vac 后活菌占比下降，
       X_active/X_lab 是否显著优于 X_total/X_lab？——这是"降 X 不降 P"的唯一物理出路。
       判据 viable_hypothesis : 某配置下 xact_nrmse 比 base 的 x_nrmse 低 ≥5 个百分点，
                                且 |yield| ≤ 5%。

    Q3 kd 是否应该只作用于 A4？（结构缺陷确认，不改引擎，只做文件级断言）
       da_*_dt 里 `-_kd_active*y[i] - _late_kd*y[i]` 对 i=11..14 等比施加，
       ⇒ 死菌与活菌同等衰减，"死菌被移除、活菌保留"在现有实现下**无法表达**。

## 用法
    python tools/r137_morphology_probe.py --batches 8,56 --tags base,kv03
    python tools/r137_morphology_probe.py --batches 8,27,56,59 --jobs 8
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

OUT = os.path.join(ROOT, "runs", "p3", "r137_morphology_probe.json")

# 只调 k_vac / mu_vac_ref（都是已存在的引擎形参，不改 model.py）
CONFIGS = {
    "base":       {},
    # T1 快速扫：k_vac=0.03 已使 debris→80.9%、产量 −98.6%（b56）⇒ 需要小两个量级
    "kv001":      {"k_vac": 0.001},
    "kv003":      {"k_vac": 0.003},
    "kv005":      {"k_vac": 0.005},
    # 原三档（0.01/0.03/0.10）保留复现
    "kv01":       {"k_vac": 0.01},
    "kv03":       {"k_vac": 0.03},
    "kv10":       {"k_vac": 0.10},
    # 抬高门控阈值 → 门更早打开（μ_actual < 0.05 就启动，晚期更像晚期）
    "kv03_mv05":  {"k_vac": 0.03, "mu_vac_ref": 0.05},
    "kv03_mv20":  {"k_vac": 0.03, "mu_vac_ref": 0.20},
    # 参照：直接晚期衰亡（等比扣所有组分，R136 已证破线）
    "ld2":        {"late_death_rate": 0.002, "mu_death_ref": 1.0, "death_recycle": 0.3},
    # T2 Y_sX **正向**扫（R136 只试过 ×0.85 方向反了；par[22]=1.85 g 底物/g 菌，↑=菌少）
    # 附带的非线性：底物耗尽更快 → 低底物门控 P_inhib 更早打开 → 比产率可能不降反升
    "ysx105":     {"Y_sX": 1.85 * 1.05},
    "ysx110":     {"Y_sX": 1.85 * 1.10},
    "ysx115":     {"Y_sX": 1.85 * 1.15},
    "ysx120":     {"Y_sX": 1.85 * 1.20},
    "ysx130":     {"Y_sX": 1.85 * 1.30},
    # T3 (mux, mup) 解耦对：86 批统计里 mux↔peakR r=+0.458（唯一强正相关），
    # mup↔peakR r=−0.283（只驱动 P 不驱动 X）⇒ 降 mux 压 X、升 mup 补 P
    # 注意：键名以 '*' 结尾表示**乘数**（params[k[:-1]] *= v），否则为绝对赋值
    "mx090":      {"mux*": 0.90},
    "mx085":      {"mux*": 0.85},
    "mx080":      {"mux*": 0.80},
    "mx090_mp110": {"mux*": 0.90, "mup*": 1.10},
    "mx085_mp120": {"mux*": 0.85, "mup*": 1.20},
    "mx085_mp130": {"mux*": 0.85, "mup*": 1.30},
    # T4 时间门控晚期衰亡（R136 的 ld 用 mu_death_ref=1.0 强制全开、从 t=0 就扣，
    # 所以在生长期就把 a1 抽干 → 产量 −21~−77%。改用已有参数 death_start 做时间门控，
    # 只在化验峰值（p50=150h）之后启动。kd≈0.003 对应 140h 内 −34%，正好匹配 lab 峰后降幅。）
    "t144_k2":    {"death_start": 144.0, "biomass_death_rate": 0.002},
    "t144_k3":    {"death_start": 144.0, "biomass_death_rate": 0.003},
    "t144_k5":    {"death_start": 144.0, "biomass_death_rate": 0.005},
    "t168_k3":    {"death_start": 168.0, "biomass_death_rate": 0.003},
    "t120_k3":    {"death_start": 120.0, "biomass_death_rate": 0.003},
    "t144_k3_r30": {"death_start": 144.0, "biomass_death_rate": 0.003, "death_recycle": 0.3},
    # T5 X-μp 联合重标定：修好 X 后 P 会偏高，因为黄金参数里的 mup 是按"X 虚高"标定的。
    # 若 X 幅度与 mup 是同一自由度的两次使用，则 mup 同步下调应能把产量拉回红线内。
    "k5_mp92":    {"death_start": 144.0, "biomass_death_rate": 0.005, "mup*": 0.92},
    "k5_mp88":    {"death_start": 144.0, "biomass_death_rate": 0.005, "mup*": 0.88},
    "k5_mp85":    {"death_start": 144.0, "biomass_death_rate": 0.005, "mup*": 0.85},
}


def _work(job):
    batch, tag, over = job
    import golden_params as gp
    from simulate import simulate_open_loop, yield_metrics, classify_crash
    import pandas as pd

    params = gp.params_for(batch)
    for k, v in over.items():
        if k.endswith("*"):                 # 乘数语义：mux* : 0.90 → mux *= 0.90
            base_k = k[:-1]
            params[base_k] = params[base_k] * v
        else:
            params[k] = v
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
    a0 = np.asarray(sim["A0"], float)
    a1 = np.asarray(sim["A1"], float)
    a3 = np.asarray(sim["A3"], float)
    a4 = np.asarray(sim["A4"], float)
    xact = a0 + a1                    # 活菌（未液泡化）
    our = np.asarray(sim["OUR"], float)
    do2 = np.asarray(sim["DO2"], float)
    p = np.asarray(sim["P"], float)

    lab = pd.to_numeric(v3["X_offline"], errors="coerce").to_numpy(float)
    plab = pd.to_numeric(v3["P_offline"], errors="coerce").to_numpy(float) \
        if "P_offline" in v3.columns else None
    tv = v3["time_h"].to_numpy(float)
    m = np.isfinite(lab)
    tt, yo = tv[m], lab[m]
    sv = np.interp(tt, t, x)
    sva = np.interp(tt, t, xact)

    nrmse = float(np.sqrt(np.mean((sv - yo) ** 2)) / np.mean(np.abs(yo)) * 100)
    nrmse_act = float(np.sqrt(np.mean((sva - yo) ** 2)) / np.mean(np.abs(yo)) * 100)

    seg = {}
    for name, lo, hi in (("early", 0, 24), ("growth", 24, 120), ("peak", 120, 168.0), ("late", 168.0, 1e9)):
        mm = (tt > lo) & (tt <= hi)
        if mm.sum() >= 2 and np.all(np.abs(yo[mm]) > 1e-9):
            seg[name] = round(float(np.median(sv[mm] / yo[mm])), 3)

    ipk = int(np.argmax(yo))
    # 形态学占比（末端）
    tot_end = float(x[-1])
    debris_end = round(float((a3[-1] + a4[-1]) / tot_end), 4) if tot_end > 1e-9 else None
    debris_max = round(float(np.max((a3 + a4) / np.maximum(x, 1e-9))), 4)
    act_end = round(float(xact[-1] / tot_end), 4) if tot_end > 1e-9 else None

    def bias(ch_sim, col):
        obs = pd.to_numeric(v3[col], errors="coerce").to_numpy(float)
        cs = np.interp(tv, t, ch_sim)
        good = np.isfinite(obs) & np.isfinite(cs)
        if good.sum() < 20 or abs(np.mean(obs[good])) < 1e-9:
            return None
        return round(float(np.mean(cs[good] - obs[good]) / np.mean(np.abs(obs[good])) * 100), 2)

    p_bias = None
    if plab is not None and np.isfinite(plab).sum() > 5:
        ok = np.isfinite(plab)
        p_bias = round(float((np.interp(tv[ok], t, p) - plab[ok]).mean()
                             / max(abs(plab[ok].mean()), 1e-9) * 100), 2)

    return {"batch": batch, "tag": tag,
            "yield_err": None if err is None or not np.isfinite(err) else round(float(err) * 100.0, 3),
            "crash": level, "crash_reasons": reasons,
            "x_nrmse": round(nrmse, 2), "xact_nrmse": round(nrmse_act, 2),
            "x_peak_ratio": round(float(sv[int(np.argmax(sv))] / yo[ipk]), 3),
            "x_end_ratio": round(float(sv[-1] / yo[-1]), 3),
            "seg": seg,
            "debris_frac_end": debris_end, "debris_frac_max": debris_max,
            "active_frac_end": act_end,
            "p_end": round(float(p[-1]), 4), "p_max": round(float(np.max(p)), 4),
            "p_bias": p_bias,
            "our_bias": bias(our, "OUR"), "do2_bias": bias(do2, "DO2")}


def judge(r, base):
    """相对同批 base 的一阶效应判定。"""
    if r.get("error") or base is None or base.get("error"):
        return "error"
    d_peak = abs(r["x_peak_ratio"] - base["x_peak_ratio"])
    d_nrmse = base["x_nrmse"] - r["x_nrmse"]          # 正=改善
    d_yield = r["yield_err"] - base["yield_err"]
    if d_peak >= 0.05 or d_nrmse >= 2.0:
        return "x_reducible"
    if d_peak < 0.03 and abs(d_yield) > 2.0:
        return "transfer_only"      # 动了产量、没动 X → 纯转移副作用
    return "inert"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", default="8,27,56,59")
    ap.add_argument("--tags", default=None)
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()

    tags = list(CONFIGS) if not args.tags else [x.strip() for x in args.tags.split(",")]
    batches = [int(x) for x in args.batches.split(",") if x.strip()]

    jobs = [(b, tag, CONFIGS[tag]) for tag in tags for b in batches]
    with Pool(min(args.jobs, len(jobs))) as pool:
        rows = pool.map(_work, jobs, chunksize=1)

    byb = {}
    for r in rows:
        if not r.get("error"):
            byb.setdefault(r["batch"], {})[r["tag"]] = r
    for r in rows:
        r["judge"] = judge(r, byb.get(r.get("batch"), {}).get("base"))

    print("=" * 128)
    print(f"R137 T1 形态学退化链反事实（{len(batches)} 批 × {len(tags)} 配置）")
    print("=" * 128)
    hdr = (f"{'批':>4} {'配置':<11} {'yield%':>8} {'X_nRMSE':>8} {'Xact_nRMSE':>10} {'peakR':>6} "
           f"{'endR':>6} {'debris末':>8} {'act末':>6} {'P_end':>7} {'OURb':>6} {'DO2b':>6}  judge")
    print(hdr)
    print("-" * 128)
    for r in sorted(rows, key=lambda x: (x.get("batch") or 0, tags.index(x["tag"]) if x["tag"] in tags else 9)):
        if r.get("error"):
            print(f"{r['batch']:>4} {r['tag']:<11} ERROR {r['error'][:70]}")
            continue
        n = lambda v, w=6, p=1: f"{v:>{w}.{p}f}" if v is not None else " " * (w - 1) + "-"
        print(f"{r['batch']:>4} {r['tag']:<11} {n(r['yield_err'],8,2)} {n(r['x_nrmse'],8,1)} "
              f"{n(r['xact_nrmse'],10,1)} {n(r['x_peak_ratio'],6,3)} {n(r['x_end_ratio'],6,3)} "
              f"{n(r['debris_frac_end'],8,4)} {n(r['active_frac_end'],6,4)} {n(r['p_end'],7,3)} "
              f"{n(r['our_bias'],6,1)} {n(r['do2_bias'],6,1)}  {r['judge']}")

    print("\n按配置聚合（中位）：")
    print(f"{'配置':<11} {'yield%':>8} {'X_nRMSE':>8} {'Xact_nRMSE':>10} {'peakR':>6} {'debris末':>8} "
          f"{'act末':>6} {'OURb':>6}  judges")
    for tag in tags:
        rs = [r for r in rows if r["tag"] == tag and not r.get("error")]
        if not rs:
            continue
        med = lambda k: float(np.median([r[k] for r in rs if r.get(k) is not None])) \
            if any(r.get(k) is not None for r in rs) else float("nan")
        jd = {}
        for r in rs:
            jd[r["judge"]] = jd.get(r["judge"], 0) + 1
        print(f"{tag:<11} {med('yield_err'):>+8.2f} {med('x_nrmse'):>8.1f} {med('xact_nrmse'):>10.1f} "
              f"{med('x_peak_ratio'):>6.3f} {med('debris_frac_end'):>8.4f} {med('active_frac_end'):>6.4f} "
              f"{med('our_bias'):>+6.1f}  {jd}")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    meta = {"tool": "r137_morphology_probe", "batches": batches, "configs": {k: v for k, v in CONFIGS.items()},
            "note": "k_vac/mu_vac_ref 为已存在的引擎形参，默认 0.0/0.1；本工具不修改 model.py"}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "rows": rows}, f, ensure_ascii=False, indent=1)
    print(f"\n已写入 {args.out}")


if __name__ == "__main__":
    main()
