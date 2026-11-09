# -*- coding: utf-8 -*-
"""R131 —— X_offline 通道根因定量与"数据驱动衰亡率"机制验证。

背景（R130 收口状态）：X_offline 是 D6 健康视图最后一个结构性 critical 通道
（12/12 critical）。R130 的结论是"晚期衰亡 late_death 是唯一可行改善路径（仅改善衰减段）"，
但 kd 的取值一直靠网格扫描 + 产量约束试错，且 12 批中仅 8 批启用。

本脚本换一个思路：**先从化验数据把"应有的净衰减率"直接算出来，再回填机制参数**，
把"扫参"变成"定参"，并给出可复核的物理量（表观比损失率 kd_app）。

三段：
  diag  —— 纯数据：峰后表观净比损失率 kd_app = -(dlnX/dt + D)，D 为稀释率（V 平滑后）
  base  —— 12 批当前基线（COMBINED）：X 通道 nRMSE / 峰值时刻 / 尾段斜率
  apply —— 逐批 kd = kd_app（death_start = 该批化验峰值时刻），可选 recycle / mup 补偿

用法：
    python tools/r131_xoff_mechanism.py diag
    python tools/r131_xoff_mechanism.py base
    python tools/r131_xoff_mechanism.py probe --batches 8,22,36,60 --kds 0.001,0.002,0.003,0.004,0.006
    python tools/r131_xoff_mechanism.py apply --recycle 0.5 --mup-scale 1.0
"""
import os
import sys
import json
import argparse
import numpy as np
import pandas as pd
from scipy.signal import savgol_filter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))

from golden_params import COMBINED  # noqa: E402
from diag_final_validation_v3 import build_params  # noqa: E402  （唯一参数装配口径）
from r131_harness import run_jobs, _load_v3, OFFLINE_DELAY_H  # noqa: E402

B12 = [8, 11, 16, 22, 23, 27, 36, 55, 60, 80, 91, 92]


# ---------------------------------------------------------------- diag（纯数据）
def diag_batch(b):
    v3 = _load_v3(b)
    V = savgol_filter(v3["V"].values, 201, 2)
    d = v3.dropna(subset=["X_offline"])
    idx = d.index.values
    t = d["time_h"].values
    X = d["X_offline"].values
    dlnX = np.gradient(np.log(X), t)
    D = np.gradient(np.log(V[idx]), t)
    g = dlnX + D                       # 表观净比生长率（稀释校正后）
    ipk = int(np.argmax(X))
    post = g[ipk:]
    # 峰后至少 3 个点才统计
    if len(post) < 3:
        return None
    return {
        "batch": b,
        "t_peak_lab_h": float(t[ipk]),
        "x_peak_lab": round(float(X[ipk]), 2),
        "x_end_lab": round(float(X[-1]), 2),
        "decay_pct_total": round(100 * (X[-1] / X[ipk] - 1), 2),
        "kd_app_median": round(float(-np.median(post)), 5),
        "kd_app_mean": round(float(-np.mean(post)), 5),
        "kd_app_iqr": [round(float(np.percentile(-post, 25)), 5),
                       round(float(np.percentile(-post, 75)), 5)],
        "n_post": int(len(post)),
        "span_post_h": float(t[-1] - t[ipk]),
    }


def cmd_diag(args):
    res = [diag_batch(b) for b in (args.batches or B12)]
    res = [r for r in res if r]
    print(f"{'b':>4s} {'t_peak':>7s} {'X_peak':>7s} {'X_end':>7s} {'decay%':>7s} "
          f"{'kd_app':>8s} {'IQR':>16s} {'span_h':>7s}")
    for r in res:
        print(f"{r['batch']:>4d} {r['t_peak_lab_h']:>7.0f} {r['x_peak_lab']:>7.2f} "
              f"{r['x_end_lab']:>7.2f} {r['decay_pct_total']:>+7.1f} {r['kd_app_median']:>8.5f} "
              f"{str(r['kd_app_iqr']):>16s} {r['span_post_h']:>7.0f}")
    kds = [r["kd_app_median"] for r in res]
    print(f"\nkd_app 中位={np.median(kds):.5f} 均值={np.mean(kds):.5f} "
          f"范围=[{min(kds):.5f}, {max(kds):.5f}] n={len(res)}")
    out = os.path.join(ROOT, "runs", "p3", "r131_xoff_decay_diag.json")
    json.dump(res, open(out, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print("saved:", os.path.relpath(out, ROOT))


# ---------------------------------------------------------------- base / probe / apply
def _jobs(batches, override_fn, tag):
    jobs = []
    for b in batches:
        p = build_params(COMBINED[b])   # 与黄金回归同一装配口径
        override_fn(b, p)
        jobs.append((b, p, tag))
    return jobs


def _report(res, ref=None):
    print(f"{'b':>4s} {'yield_err':>9s} {'X_nRMSE':>8s} {'ΔX':>7s} {'Xcorr':>6s} "
          f"{'t_pk_sim':>8s} {'tail_sim':>9s} {'tail_lab':>9s} {'crash':>8s}")
    for r in res:
        if "error" in r:
            print(f"{r['batch']:>4d}  ERROR {r['error'][:60]}")
            continue
        ch = r["channels"].get("X_offline", {})
        xs = r.get("x_shape", {})
        d = ""
        if ref:
            rb = next((x for x in ref if x["batch"] == r["batch"]), None)
            if rb and ch.get("nrmse_pct") is not None:
                d = f"{ch['nrmse_pct'] - rb['channels']['X_offline']['nrmse_pct']:+7.1f}"
        ye = r["yield_err"]
        print(f"{r['batch']:>4d} {ye:>+9.2%} {ch.get('nrmse_pct'):>8.1f} {d:>7s} "
              f"{ch.get('corr'):>6.3f} {xs.get('t_peak_sim', float('nan')):>8.0f} "
              f"{xs.get('decay_tail_sim', float('nan')):>9.4f} "
              f"{xs.get('decay_tail_lab', float('nan')):>9.4f} {r['crash']:>8s}")


def cmd_base(args):
    batches = args.batches or B12
    res = run_jobs(_jobs(batches, lambda b, p: None, "base"))
    _report(res)
    out = os.path.join(ROOT, "runs", "p3", "r131_xoff_baseline.json")
    json.dump(res, open(out, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    xs = [r["channels"]["X_offline"]["nrmse_pct"] for r in res if "error" not in r]
    print(f"\nX nRMSE 均值={np.mean(xs):.1f}% 中位={np.median(xs):.1f}%")
    print("saved:", os.path.relpath(out, ROOT))


def cmd_probe(args):
    """kd × recycle 二维探针：看衰亡率对 X 通道与产量的响应面。"""
    batches = args.batches or [8, 22, 36, 60]
    kds = [float(x) for x in args.kds.split(",")]
    recs = [float(x) for x in args.recycle.split(",")]
    jobs = []
    for b in batches:
        for kd in kds:
            for rc in recs:
                p = build_params(COMBINED[b])
                p["biomass_death_rate"] = kd
                p["death_start"] = 150.0
                p["death_recycle"] = rc
                jobs.append((b, p, f"kd{kd}_rc{rc}"))
    res = run_jobs(jobs)
    print(f"\n{'b':>4s} {'tag':>14s} {'yield_err':>9s} {'X_nRMSE':>8s} {'t_pk':>5s} "
          f"{'tail_sim':>9s} {'x_end':>7s} {'crash':>8s}")
    for r in res:
        if "error" in r:
            continue
        xs = r["x_shape"]
        print(f"{r['batch']:>4d} {r['tag']:>14s} {r['yield_err']:>+9.2%} "
              f"{r['channels']['X_offline']['nrmse_pct']:>8.1f} {xs['t_peak_sim']:>5.0f} "
              f"{xs['decay_tail_sim']:>9.4f} {xs['x_end_sim']:>7.2f} {r['crash']:>8s}")
    out = os.path.join(ROOT, "runs", "p3", "r131_xoff_probe.json")
    json.dump(res, open(out, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print("saved:", os.path.relpath(out, ROOT))


def cmd_apply(args):
    """逐批定参：kd = kd_app（数据反算），death_start = 该批化验峰值时刻。"""
    diag = json.load(open(os.path.join(ROOT, "runs", "p3", "r131_xoff_decay_diag.json"),
                          encoding="utf-8"))
    kmap = {d["batch"]: d for d in diag}
    batches = args.batches or B12
    mup_scale = args.mup_scale

    def ov(b, p):
        d = kmap.get(b, {})
        # 单一衰亡通道：清掉 late_death（μ 门控）避免与 kd 叠加重复计数
        for k in ("late_death_rate", "mu_death_ref"):
            p.pop(k, None)
        p["biomass_death_rate"] = float(args.kd_override) if args.kd_override else d.get("kd_app_median", 0.0)
        p["death_start"] = d.get("t_peak_lab_h", 150.0)
        p["death_recycle"] = args.recycle
        if mup_scale != 1.0:
            p["mup"] = p["mup"] * mup_scale

    res = run_jobs(_jobs(batches, ov, f"apply_rc{args.recycle}_mu{mup_scale}"))
    base = None
    bp = os.path.join(ROOT, "runs", "p3", "r131_xoff_baseline.json")
    if os.path.exists(bp):
        base = json.load(open(bp, encoding="utf-8"))
    _report(res, base)
    xs = [r["channels"]["X_offline"]["nrmse_pct"] for r in res if "error" not in r]
    print(f"\nX nRMSE 均值={np.mean(xs):.1f}% 中位={np.median(xs):.1f}%")
    if base:
        xb = [r["channels"]["X_offline"]["nrmse_pct"] for r in base if "error" not in r]
        print(f"基线 X nRMSE 均值={np.mean(xb):.1f}%（改善 {np.mean(xb)-np.mean(xs):+.1f} pt）")
    out = os.path.join(ROOT, "runs", "p3", f"r131_xoff_apply_rc{args.recycle}.json")
    json.dump(res, open(out, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print("saved:", os.path.relpath(out, ROOT))


def cmd_grid(args):
    """(mux, mup) 二维脊扫描：X 幅度与产量双目标。

    假设：高 nRMSE 批（b27/36/55/60/91/92）根因不是"衰减段缺机制"，而是**生长期幅度过高**
    （X_peak ratio 1.2~1.56）。沿 (μx↓, μp↑) 脊移动应能同时压低 X 幅度并保住产量。
    """
    batches = args.batches or [27, 36, 55, 60, 91, 92]
    muxes = [float(x) for x in args.muxes.split(",")]
    mults = [float(x) for x in args.mults.split(",")]
    jobs = []
    for b in batches:
        mup0 = COMBINED[b].get("mup", 0.041)
        for mx in muxes:
            for mf in mults:
                p = build_params(COMBINED[b])
                p["mux"] = mx
                p["mup"] = round(mup0 * mf, 5)
                jobs.append((b, p, f"mux{mx}_mupx{mf}"))
    res = run_jobs(jobs)
    print(f"\n{'b':>4s} {'tag':>18s} {'yield_err':>9s} {'X_nRMSE':>8s} {'xpk_s':>7s} "
          f"{'xpk_l':>7s} {'ratio':>6s} {'t_pk':>5s} {'crash':>8s}")
    best = {}
    for r in sorted(res, key=lambda x: (x["batch"], x.get("channels", {}).get("X_offline", {}).get("nrmse_pct") or 999)):
        if "error" in r:
            print(f"{r['batch']:>4d} {r['tag']:>18s}  ERROR {r['error'][:50]}")
            continue
        ch = r["channels"]["X_offline"]; xs = r["x_shape"]
        ratio = xs["x_peak_sim"] / xs["x_peak_lab"]
        ok = (r["yield_err"] is not None and abs(r["yield_err"]) <= 0.05
              and r["crash"] != "catastrophic")
        print(f"{r['batch']:>4d} {r['tag']:>18s} {r['yield_err']:>+9.2%} {ch['nrmse_pct']:>8.1f} "
              f"{xs['x_peak_sim']:>7.2f} {xs['x_peak_lab']:>7.2f} {ratio:>6.2f} "
              f"{xs['t_peak_sim']:>5.0f} {r['crash']:>8s}{'  <=OK' if ok else ''}")
        if ok and r["batch"] not in best:
            best[r["batch"]] = r
    out = os.path.join(ROOT, "runs", "p3", "r131_mux_mup_grid.json")
    json.dump(res, open(out, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print("\n=== 双约束（|yield|<=5% 且 非 catastrophic）下 X nRMSE 最优 ===")
    for b in batches:
        r = best.get(b)
        if not r:
            print(f"  b{b}: 无可行解")
            continue
        ch = r["channels"]["X_offline"]; xs = r["x_shape"]
        print(f"  b{b}: {r['tag']}  yield={r['yield_err']:+.2%}  X nRMSE={ch['nrmse_pct']:.1f}%  "
              f"ratio={xs['x_peak_sim']/xs['x_peak_lab']:.2f}  t_peak={xs['t_peak_sim']:.0f}")
    print("saved:", os.path.relpath(out, ROOT))


def cmd_ampscan(args):
    """(kd, recycle) 幅度扫描：早期恒定衰亡压低 X 幅度，双约束选优。

    依据：grid 实验证否了 (mux, mup) 脊补偿（72 配置下幅度比恒 ≥1.17）；
    R130o 早衰探针显示强早期衰亡可把峰值从 37→23 而产量仅 −3%。
    """
    batches = args.batches or [27, 36, 55, 60, 91, 92]
    kds = [float(x) for x in args.kds.split(",")]
    recs = [float(x) for x in args.recs.split(",")]
    starts = [float(x) for x in args.starts.split(",")]
    jobs = []
    for b in batches:
        for kd in kds:
            for rc in recs:
                for ds in starts:
                    p = build_params(COMBINED[b])
                    for k in ("late_death_rate", "mu_death_ref"):
                        p.pop(k, None)
                    p["biomass_death_rate"] = kd
                    p["death_start"] = ds
                    p["death_recycle"] = rc
                    jobs.append((b, p, f"kd{kd}_rc{rc}_ds{ds:g}"))
    res = run_jobs(jobs)
    out = os.path.join(ROOT, "runs", "p3", "r131_xoff_ampscan.json")
    json.dump(res, open(out, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"\n{'b':>4s} {'tag':>18s} {'yield_err':>9s} {'X_nRMSE':>8s} {'ratio':>6s} "
          f"{'t_pk':>5s} {'tail_s':>8s} {'crash':>8s}")
    best = {}
    for r in sorted(res, key=lambda x: (x["batch"],
                                        (x.get("channels", {}).get("X_offline", {}).get("nrmse_pct") or 999))):
        if "error" in r:
            print(f"{r['batch']:>4d} {r['tag']:>18s}  ERROR {r['error'][:60]}")
            continue
        ch = r["channels"]["X_offline"]; xs = r["x_shape"]
        ok = (r["yield_err"] is not None and abs(r["yield_err"]) <= 0.05
              and r["crash"] != "catastrophic")
        print(f"{r['batch']:>4d} {r['tag']:>18s} {r['yield_err']:>+9.2%} {ch['nrmse_pct']:>8.1f} "
              f"{xs['x_peak_sim']/xs['x_peak_lab']:>6.2f} {xs['t_peak_sim']:>5.0f} "
              f"{xs['decay_tail_sim']:>8.4f} {r['crash']:>8s}{'  <=OK' if ok else ''}")
        if ok and r["batch"] not in best:
            best[r["batch"]] = r
    print("\n=== 双约束下 X nRMSE 最优 ===")
    for b in batches:
        r = best.get(b)
        if not r:
            print(f"  b{b}: 无可行解")
            continue
        ch = r["channels"]["X_offline"]; xs = r["x_shape"]
        print(f"  b{b}: {r['tag']}  yield={r['yield_err']:+.2%}  X nRMSE={ch['nrmse_pct']:.1f}%  "
              f"ratio={xs['x_peak_sim']/xs['x_peak_lab']:.2f}  t_peak={xs['t_peak_sim']:.0f}")
    print("saved:", os.path.relpath(out, ROOT))


def cmd_joint(args):
    """(kd, mup) 联合网格：衰亡压 X 幅度 → 产量正偏差 → μp 回调。

    机制链（ampscan 已证）：kd↑ ⇒ X 幅度↓（X nRMSE 36→9）但产量↑（底物从生长转向青霉素合成），
    故必须同步下调 μp 才能守住 ±5%。这是"X 通道 × 产量"双目标的真正脊线。
    """
    batches = args.batches or [27, 36, 55, 60, 92]
    kds = [float(x) for x in args.kds.split(",")]
    mfs = [float(x) for x in args.mults.split(",")]
    recs = [float(x) for x in args.recs.split(",")]
    jobs = []
    for b in batches:
        mup0 = COMBINED[b].get("mup", 0.041)
        for kd in kds:
            for mf in mfs:
                for rc in recs:
                    p = build_params(COMBINED[b])
                    for k in ("late_death_rate", "mu_death_ref"):
                        p.pop(k, None)
                    p["biomass_death_rate"] = kd
                    p["death_start"] = 0.0
                    p["death_recycle"] = rc
                    p["mup"] = round(mup0 * mf, 5)
                    jobs.append((b, p, f"kd{kd}_mupx{mf}_rc{rc}"))
    res = run_jobs(jobs)
    out = os.path.join(ROOT, "runs", "p3", args.outname)
    json.dump(res, open(out, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    base = {r["batch"]: r for r in json.load(open(os.path.join(ROOT, "runs", "p3", "r131_xoff_baseline.json"), encoding="utf-8"))}
    print(f"\n{'b':>4s} {'tag':>22s} {'yield_err':>9s} {'X_nRMSE':>8s} {'base':>6s} {'ratio':>6s} {'t_pk':>5s} {'ok':>4s}")
    best = {}
    for r in sorted(res, key=lambda x: (x["batch"], x.get("channels", {}).get("X_offline", {}).get("nrmse_pct") or 999)):
        if "error" in r:
            print(f"{r['batch']:>4d} {r['tag']:>22s}  ERROR {r['error'][:50]}")
            continue
        ch = r["channels"]["X_offline"]; xs = r["x_shape"]
        b0 = base[r["batch"]]["channels"]["X_offline"]["nrmse_pct"]
        ok = (r["yield_err"] is not None and abs(r["yield_err"]) <= 0.05
              and r["crash"] != "catastrophic")
        print(f"{r['batch']:>4d} {r['tag']:>22s} {r['yield_err']:>+9.2%} {ch['nrmse_pct']:>8.1f} "
              f"{b0:>6.1f} {xs['x_peak_sim']/xs['x_peak_lab']:>6.2f} {xs['t_peak_sim']:>5.0f} "
              f"{'OK' if ok else '--':>4s}")
        if ok and r["batch"] not in best:
            best[r["batch"]] = r
    print("\n=== 双约束（|yield|<=5%）下 X nRMSE 最优 ===")
    tot_b, tot_a = 0.0, 0.0
    for b in batches:
        r = best.get(b)
        if not r:
            print(f"  b{b}: 无可行解（保持基线）")
            tot_a += base[b]["channels"]["X_offline"]["nrmse_pct"]
            tot_b += base[b]["channels"]["X_offline"]["nrmse_pct"]
            continue
        ch = r["channels"]["X_offline"]; b0 = base[b]["channels"]["X_offline"]["nrmse_pct"]
        print(f"  b{b}: {r['tag']}  yield={r['yield_err']:+.2%}  X nRMSE {b0:.1f}%→{ch['nrmse_pct']:.1f}% "
              f"({ch['nrmse_pct']-b0:+.1f} pt)")
        tot_b += b0; tot_a += ch["nrmse_pct"]
    print(f"  合计数：{tot_b:.1f}% → {tot_a:.1f}%（{tot_a-tot_b:+.1f} pt, {(tot_a/tot_b-1)*100:+.1f}%）")
    print("saved:", os.path.relpath(out, ROOT))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["diag", "base", "probe", "apply", "grid", "ampscan", "joint"])
    ap.add_argument("--batches", type=str, default="")
    ap.add_argument("--kds", type=str, default="0.001,0.002,0.003,0.004,0.006")
    ap.add_argument("--recs", type=str, default="0.0,0.3")
    ap.add_argument("--starts", type=str, default="0")
    ap.add_argument("--muxes", type=str, default="0.36,0.40,0.44")
    ap.add_argument("--mults", type=str, default="1.0,1.3,1.6,2.0")
    ap.add_argument("--recycle", type=str, default="0.5")
    ap.add_argument("--kd-override", type=float, default=0.0)
    ap.add_argument("--mup-scale", type=float, default=1.0)
    ap.add_argument("--outname", type=str, default="r131_xoff_joint.json")
    args = ap.parse_args()
    if args.batches:
        args.batches = [int(x) for x in args.batches.split(",")]
    if args.cmd == "probe":
        return cmd_probe(args)
    if args.cmd == "apply":
        args.recycle = float(args.recycle)
    return {"diag": cmd_diag, "base": cmd_base, "apply": cmd_apply,
            "grid": cmd_grid, "ampscan": cmd_ampscan, "joint": cmd_joint}[args.cmd](args)


if __name__ == "__main__":
    main()
