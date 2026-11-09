# -*- coding: utf-8 -*-
"""R136 T4：晚期衰亡率逐批定标（**未运行 / 前提已被 T2 证伪，留作 R137 骨架**）

!! 警告：本工具建立在一个已被 R136 T2 推翻的前提上——"打开衰亡可以便宜地修好 X 尾段"。
!! T2 的 8 批 48 配置反事实显示：ld=0.002/0.004/0.006 的中位产量误差为 −21.4/−64.0/−77.1%，
!! 分别有 6/8、8/8、7/8 批越出 ±5% 红线。因此本工具的选点规则（C1 |yield|≤4.5%）
!! 在绝大多数批上无可行候选，定标没有意义，本轮**未运行**。
!! 保留代码是给 R137 的"结构改型后再定标"复用；不要直接跑它来改黄金参数。

原设计意图：晚期衰亡率逐批定标 —— 用 X_offline 尾段定 ld，不用扫参凑误差。

前置证据（R136 T1/T2）：
  T1  86 批 X 通道：分段比值 early 1.05 → late 1.36（单调递增），lab 峰→末 −12.8%、sim −0.7%
      ⇒ 误差是"峰后不降"的**漂移**，不是整体标度。
  T2  8 批反事实：把 late_death_rate 从 0 打开到 0.002–0.006，X nRMSE 41→5（b56/b87）、23→4（b75），
      同时 OUR 偏置 +22.6% → −1.9%、DO2 偏置 −4.6% → +4.2%，**产量中位仅动 −0.2%~−0.8%**
      ⇒ 死衰项是 X 尾段的直接开关，且几乎不碰产量红线。
  T2b 门控**没有**自锁：μ_app 晚期中位 0.0003 h⁻¹ ≪ μ_death_ref 0.02 → gate 中位 0.98（全开）。
      真正的问题是 **77/86 批根本没启用任何衰亡项**（ld=0 且 biomass_death_rate=0）。

本工具：对这批"无衰亡项"的批，逐批在 ld 网格上定标。选点规则**先登记后算**：

    主目标   minimize |decay_gap|            （衰亡率由化验尾段定，不是让 nRMSE 最小）
    约束 C1  |yield_err| ≤ 4.5%              （留 0.5pt 给红线）
    约束 C2  x_nrmse ≤ base_x_nrmse + 1.0     （允许小幅换取机制正确，不允许为降 nRMSE 而过冲）
    约束 C3  |yield_err| ≤ |base_yield| + 0.8 （不许把本来准的产量改坏）
    兜底     无候选满足 → 保留 base（ld 不启用）

已存在衰亡项的批（b8/11/16/22/23 用 late_death，b27/36/60/92/55/91 用 biomass_death）**不动**——
它们已被 R130j/R131 标定过，本轮不覆盖，避免两条衰亡通道互相打架。

用法：
    python tools/r136_ldr_calibrate.py                 # 全量 77 批 × 4 候选
    python tools/r136_ldr_calibrate.py --limit 12      # 先跑 12 批看走势
    python tools/r136_ldr_calibrate.py --reanalyse     # 免重跑，只重算选点
"""
import argparse
import glob
import json
import os
import sys
from multiprocessing import Pool

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))
CACHE = os.path.join(ROOT, "platform", ".cache")
OUT = os.path.join(ROOT, "runs", "p3", "r136_ldr_calibration.json")

GRID = [0.001, 0.002, 0.003, 0.005]
RECYCLE = 0.3
LATE_T = 168.0


def metrics_from_arrays(t, x, our, do2, v3):
    lab = np.asarray(v3["X_offline"], float)
    tv = np.asarray(v3["time_h"], float)
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

    def bias(ch, col):
        obs = np.asarray(v3[col], float)
        ch = np.interp(tv, t, ch)
        g = np.isfinite(obs) & np.isfinite(ch)
        if g.sum() < 20 or abs(np.mean(obs[g])) < 1e-9:
            return None
        return round(float(np.mean(ch[g] - obs[g]) / np.mean(np.abs(obs[g])) * 100), 2)

    return {"x_nrmse": round(float(np.sqrt(np.mean((sv - yo) ** 2)) / np.mean(np.abs(yo)) * 100), 2),
            "x_peak_ratio": round(float(sv[int(np.argmax(sv))] / yo[ipk]), 3),
            "decay_sim": round(decay_sim, 1), "decay_lab": round(decay_lab, 1),
            "decay_gap": round(decay_sim - decay_lab, 1),
            "x_end_ratio": round(float(sv[-1] / yo[-1]), 3),
            "seg": seg, "our_bias": bias(our, "OUR"), "do2_bias": bias(do2, "DO2")}


def _cache_base(batch):
    d = json.load(open(os.path.join(CACHE, f"b{batch:02d}.json"), encoding="utf-8"))
    import pandas as pd
    v3 = pd.read_csv(os.path.join(ROOT, "data", "processed", "batches", f"batch_{batch:02d}.csv"))
    r = metrics_from_arrays(np.asarray(d["t"], float), np.asarray(d["sim"]["X"], float),
                            np.asarray(d["sim"]["OUR"], float), np.asarray(d["sim"]["DO2"], float), v3)
    r.update({"batch": batch, "ld": None, "yield_err": None})
    return r


def _work(job):
    batch, ld = job
    import golden_params as gp
    from simulate import simulate_open_loop, yield_metrics, classify_crash
    import pandas as pd

    params = dict(gp.params_for(batch))
    params["late_death_rate"] = ld
    params["death_recycle"] = RECYCLE
    params.setdefault("mu_death_ref", 0.02)
    try:
        sim, _ = simulate_open_loop(batch, params)
    except Exception as e:
        return {"batch": batch, "ld": ld, "error": f"{type(e).__name__}: {e}"}
    v3 = pd.read_csv(os.path.join(ROOT, "data", "processed", "batches", f"batch_{batch:02d}.csv"))
    ym = yield_metrics(sim, v3)
    err = ym["rel_err_total"]
    level, _ = classify_crash(sim, yield_err=err)
    r = metrics_from_arrays(np.asarray(sim["time_h"], float), np.asarray(sim["X"], float),
                            np.asarray(sim["OUR"], float), np.asarray(sim["DO2"], float), v3)
    r.update({"batch": batch, "ld": ld,
              "yield_err": None if err is None or not np.isfinite(err) else round(float(err), 4),
              "crash": level})
    return r


def select(base, cands):
    """先登记后算的选点规则（见模块 docstring）。返回 (best_record, reason)。"""
    ok = []
    for c in cands:
        if c.get("error") or c.get("yield_err") is None:
            continue
        if c.get("crash") not in (None, "ok", "none", "normal"):
            continue
        ye, by = abs(c["yield_err"]), abs(base.get("yield_err") or 0.0)
        if ye > 4.5:
            continue
        if c["x_nrmse"] > base["x_nrmse"] + 1.0:
            continue
        if ye > by + 0.8:
            continue
        ok.append(c)
    if not ok:
        return None, "no_candidate（全部违反 C1/C2/C3）"
    ok.sort(key=lambda c: (abs(c["decay_gap"]), c["x_nrmse"]))
    if abs(ok[0]["decay_gap"]) >= abs(base["decay_gap"]) - 0.5:
        return None, f"base 已是最优（gap {base['decay_gap']:+.1f} vs 最佳候选 {ok[0]['decay_gap']:+.1f}）"
    return ok[0], "gap 最小且满足 C1–C3"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--reanalyse", action="store_true")
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()

    import golden_params as gp
    import pandas as pd

    # 只处理"无任何衰亡项"的批
    targets = []
    for b in gp.GOLDEN_ALL:
        p = gp.params_for(b)
        if float(p.get("late_death_rate", 0.0) or 0.0) > 0:
            continue
        if float(p.get("biomass_death_rate", 0.0) or 0.0) > 0:
            continue
        targets.append(b)
    targets = sorted(targets)
    if args.limit:
        targets = targets[:args.limit]
    print(f"目标批（无衰亡项）：{len(targets)} 批 → {targets}")

    if args.reanalyse:
        data = json.load(open(args.out, encoding="utf-8"))
        rows, bases = data["rows"], data["base"]
    else:
        jobs = [(b, ld) for ld in GRID for b in targets]
        with Pool(min(args.jobs, len(jobs))) as pool:
            rows = pool.map(_work, jobs, chunksize=1)
        bases = {str(b): _cache_base(b) for b in targets}
        # 用现参数重新仿真 base 太贵；cache 即当前参数下的引擎输出（R135 平台导出），
        # 与 T2 探针 base 逐位一致（b56 41.0 / b75 23.4 / b87 41.0）已验证可替代。
        for b in targets:
            bases[str(b)]["yield_err"] = _base_yield(b, gp, pd)

    picks, skipped = {}, {}
    for b in targets:
        base = bases[str(b)]
        cands = [r for r in rows if r["batch"] == b and not r.get("error")]
        best, why = select(base, cands)
        if best:
            picks[str(b)] = {"ld": best["ld"], "decay_gap": best["decay_gap"],
                             "x_nrmse": best["x_nrmse"], "yield_err": best["yield_err"],
                             "base_x_nrmse": base["x_nrmse"], "base_gap": base["decay_gap"],
                             "base_yield": base["yield_err"]}
        else:
            skipped[str(b)] = why

    print("\n" + "=" * 100)
    print(f"{'批':>4} {'ld':>7} {'X nRMSE':>14} {'decay gap':>16} {'yield%':>13}")
    print("-" * 100)
    for b, p in sorted(picks.items(), key=lambda kv: int(kv[0])):
        print(f"{b:>4} {p['ld']:>7.4f} {p['base_x_nrmse']:>6.1f}→{p['x_nrmse']:<6.1f} "
              f"{p['base_gap']:>+7.1f}→{p['decay_gap']:<+7.1f} {p['base_yield']:>+6.2f}→{p['yield_err']:<+6.2f}")
    print(f"\n选中 {len(picks)} 批 / 保留 base {len(skipped)} 批")

    if picks:
        def med(k, src=picks):
            return round(float(np.median([v[k] for v in src.values()])), 2)
        print("选中批中位：X nRMSE %.1f%% → %.1f%%（Δ%+.1f）| gap %+.1f → %+.1f | yield %+.2f%% → %+.2f%%"
              % (med("base_x_nrmse"), med("x_nrmse"), med("x_nrmse") - med("base_x_nrmse"),
                 med("base_gap"), med("decay_gap"), med("base_yield"), med("yield_err")))

    out = {"meta": {"targets": targets, "grid": GRID, "recycle": RECYCLE,
                    "rule": {"primary": "min |decay_gap|",
                             "C1": "|yield_err|<=4.5%", "C2": "x_nrmse<=base+1.0",
                             "C3": "|yield_err|<=|base|+0.8", "fallback": "keep base"}},
           "picks": picks, "skipped": skipped, "base": bases, "rows": rows}
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"已写入 {args.out}")


def _base_yield(b, gp, pd):
    """base 的产量误差：从 r135_golden86.json 读（本轮不动参数，数值仍有效）。"""
    p = os.path.join(ROOT, "runs", "p3", "r135_golden86.json")
    if os.path.exists(p):
        d = json.load(open(p, encoding="utf-8"))
        rows = d["rows"] if isinstance(d, dict) else d
        for r in rows:
            if int(r.get("batch", -1)) == int(b):
                v = r.get("yield_err", r.get("err"))
                return None if v is None else round(float(v), 4)
    return None


if __name__ == "__main__":
    main()
