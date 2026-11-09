# -*- coding: utf-8 -*-
"""R142 / D-2 Part A：DL σ̂ 失效机制诊断（只读 theta 日志，不做仿真）。

背景：`hier_est.dl_sigma` 对 mux/mup/m_s 一致返回 σ_pop=0。
若这是"数据不含批间信息"（真不可辨识），D-2 判定成立；
若这是"后验温度把损失面摊平"（方法缺陷），D-2 判定错误、可修。

判据（本脚本给出）：
  1. `var_w` 是否顶到**网格满铺方差** `sat_var`（均匀权重下的最大方差）。
     顶到 → 后验等于无信息先验，`var_w` 不再度量"估计量的抽样方差"，DL 减法必负。
  2. 有效样本数 `ESS = 1/Σw²` 是否接近组合数 n_combos。
  3. 损失面本身的 SNR：`ΔL_rel = (L_max − L_min)/L_min`（同批同参数 profile）。
     SNR 小 → 真无信息；SNR 大而 ESS 饱和 → 温度口径错。

输出：runs/p3/r142_d2_diagnose.json + stdout 摘要
"""
import json
import os
import sys

import numpy as np

_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
LOG = os.path.join(_ROOT, "runs", "hier_est", "train_theta_v2.jsonl")
OUT = os.path.join(_ROOT, "runs", "p3", "r142_d2_diagnose.json")
PARAMS = ("mux", "mup", "m_s")
LOSS_CAP = 9e5


def _load():
    return [json.loads(l) for l in open(LOG, encoding="utf-8")]


def _sw(rec):
    return [c for c in (rec.get("sweep") or []) if c["loss"] < LOSS_CAP]


def posteriors(sw, param, T):
    """softmax 后验（与 hier_est 同口径）：w ∝ exp(-(L-L_min)/T)。"""
    L = np.array([c["loss"] for c in sw])
    v = np.array([c[param] for c in sw])
    w = np.exp(-(L - L.min()) / T)
    w /= w.sum()
    m = float(w @ v)
    return w, v, m, float(w @ (v - m) ** 2)


def sat_var(sw, param):
    """网格满铺方差：全部组合等权（即"后验 = 无信息"）时的方差。"""
    v = np.array([c[param] for c in sw])
    return float(np.var(v))


def profile(sw, param):
    """profile 损失：对每个 param 取值取其余自由度上的最小损失。"""
    d = {}
    for c in sw:
        k = c[param]
        d[k] = min(d.get(k, np.inf), c["loss"])
    ks = sorted(d)
    return ks, [d[k] for k in ks]


def main():
    recs = _load()
    rows = []
    for r in recs:
        sw = _sw(r)
        if len(sw) < 4:
            continue
        L = np.array([c["loss"] for c in sw])
        T_med = max(float(np.median(L)), 1e-6)   # quick_calibrate 用的温度
        T_1 = 1.0                                 # dl_sigma 用的 T_EB
        for p in PARAMS:
            ks, pl = profile(sw, p)
            Lmin, Lmax = min(pl), max(pl)
            row = {
                "batch": r["batch"], "param": p,
                "n_combos": len(sw),
                "L_min": round(Lmin, 5), "L_med": round(float(np.median(L)), 5),
                "L_prof_range": round(Lmax - Lmin, 5),
                "dL_rel": round((Lmax - Lmin) / max(Lmin, 1e-9), 4),
                "prof_levels": len(ks),
                "sat_var": round(sat_var(sw, p), 8),
                "T_med": round(T_med, 5), "T_eb": T_1,
            }
            for tag, T in (("Tmed", T_med), ("Teb", T_1)):
                w, v, m, vp = posteriors(sw, p, T)
                ess = float(1.0 / np.sum(w ** 2))
                row[f"var_w_{tag}"] = round(vp, 8)
                row[f"ESS_{tag}"] = round(ess, 2)
                row[f"sat_frac_{tag}"] = round(vp / max(row["sat_var"], 1e-12), 4)
                row[f"theta_post_{tag}"] = round(m, 5)
            rows.append(row)

    # 全局摘要
    summary = {}
    for p in PARAMS:
        rp = [r for r in rows if r["param"] == p]
        g = lambda k: float(np.median([r[k] for r in rp]))
        summary[p] = {
            "n": len(rp),
            "dL_rel_med": round(g("dL_rel"), 4),
            "dL_rel_p10": round(float(np.percentile([r["dL_rel"] for r in rp], 10)), 4),
            "sat_frac_Tmed_med": round(g("sat_frac_Tmed"), 4),
            "sat_frac_Teb_med": round(g("sat_frac_Teb"), 4),
            "ESS_Tmed_med": round(g("ESS_Tmed"), 2),
            "ESS_Teb_med": round(g("ESS_Teb"), 2),
            "n_combos_med": int(g("n_combos")),
            "var_w_Teb_med": g("var_w_Teb"),
            "sat_var_med": g("sat_var"),
        }

    # 批间方差（用网格后验均值，即现口径）vs 用 profile 最优（MAP）值
    between = {}
    for p in PARAMS:
        rp = sorted([r for r in rows if r["param"] == p], key=lambda x: x["batch"])
        v_post = np.array([r["theta_post_Teb"] for r in rp])
        between[p] = {
            "var_b_post_Teb": round(float(np.var(v_post, ddof=1)), 8),
            "sigma_b_post": round(float(np.std(v_post, ddof=1)), 5),
            "var_w_Teb": round(float(np.mean([r["var_w_Teb"] for r in rp])), 8),
            "DL_gap": round(float(np.var(v_post, ddof=1)
                                  - np.mean([r["var_w_Teb"] for r in rp])), 8),
        }

    out = {"n_batches": len(recs), "n_rows": len(rows),
           "summary": summary, "between": between, "rows": rows}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"批数 {len(recs)} | 行 {len(rows)}")
    print(f"{'param':>5} {'dL_rel中位':>10} {'p10':>7} {'sat%_Teb':>9} "
          f"{'ESS_Teb':>8} {'ESS/n':>7} {'var_w':>10} {'sat_var':>10} {'var_b':>10} {'DL_gap':>10}")
    for p in PARAMS:
        s, b = summary[p], between[p]
        print(f"{p:>5} {s['dL_rel_med']:>10.3f} {s['dL_rel_p10']:>7.3f} "
              f"{100*s['sat_frac_Teb_med']:>8.1f}% {s['ESS_Teb_med']:>8.1f} "
              f"{s['ESS_Teb_med']/s['n_combos_med']:>7.2f} {b['var_w_Teb']:>10.2e} "
              f"{s['sat_var_med']:>10.2e} {b['var_b_post_Teb']:>10.2e} {b['DL_gap']:>10.2e}")
    print("\n参考：MATLAB σ_gen  mux 0.025 / mup 0.0025  → var_pop 6.25e-04 / 6.25e-06")
    print(f"落盘 {OUT}")


if __name__ == "__main__":
    main()
