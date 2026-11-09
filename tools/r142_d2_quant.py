# -*- coding: utf-8 -*-
"""R142 / D-2 Part C：网格量化下限检验 —— σ_pop 不可辨识是否由估计协议造成。

Part B2 已排除"温度口径"作为唯一原因：改用 T=残差SD 后 σ_pop 仍为 0。
本脚本检验更根本的一条：**网格分辨率本身**。

两条量化判据：
  1. 量化误差下限 `var_quant = d²/12`（d = 网格步距，均匀量化最优情形）。
     若 `var_quant ≥ var_b_observed`，则该参数上的 DL 减法**必然**为负，
     无论数据多好、温度多准 —— σ_pop 只能报 0。
  2. 量化对 **var_b 本身**的压制：真实批间散布 σ_true 被量化到粗网格后，
     批间方差会被系统压低（模拟验证）。若模拟给出的 var_b_quant 与实测
     var_b 一致、且都远小于 σ_true²，则说明"var_b 也失真"。

输出：runs/p3/r142_d2_quant.json
"""
import json
import os
import sys

import numpy as np

_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(_ROOT, "candidate", "indpensim", "v0.1"))
import golden_params as gp  # noqa: E402  仅用于 COMBINED 散布对照
LOG = os.path.join(_ROOT, "runs", "hier_est", "train_theta_v2.jsonl")
DIAG = os.path.join(_ROOT, "runs", "p3", "r142_d2_diagnose.json")
SNR = os.path.join(_ROOT, "runs", "p3", "r142_d2_snr2.json")
OUT = os.path.join(_ROOT, "runs", "p3", "r142_d2_quant.json")

# v2 协议网格（hier_est.GRID_V2）
GRID_V2 = {
    "mux": [0.35, 0.41, 0.47],
    "mup": [0.034, 0.036, 0.038, 0.040, 0.042, 0.044, 0.046, 0.048],
    "m_s": [0.020, 0.029],
}
# MATLAB 生成机制的真实批间散布（已核对源码，勿再凭记忆填）
#   indpensim_run.m:82  x0.mux = 0.41  + 0.025 *randn   → σ = 0.025
#   indpensim_run.m:85  x0.mup = 0.041 + 0.0025*randn   → σ = 0.0025
#   Parameter_list.m:30 m_s   = 0.029 （**常数，无 randn**）→ σ = 0（真值散布为零）
SIGMA_TRUE = {"mux": 0.025, "mup": 0.0025, "m_s": 0.0}


def step(g):
    d = np.diff(sorted(g))
    return float(np.mean(d))


def quantise(v, g):
    g = np.array(sorted(g))
    return g[np.argmin(np.abs(g[None, :] - np.asarray(v)[:, None]), axis=1)]


def main():
    rng = np.random.default_rng(20261104)
    diag = json.load(open(DIAG, encoding="utf-8"))["between"]
    # MAP 口径的批间方差（不受后验温度影响，用于把"温度效应"与"量化效应"分开）
    recs = [json.loads(l) for l in open(LOG, encoding="utf-8")]
    var_b_map = {p: float(np.var([r["theta_map"][p] for r in recs], ddof=1)) for p in GRID_V2}
    out = {"grid_v2": GRID_V2, "sigma_true_ref": SIGMA_TRUE, "by_param": {}}

    for p, g in GRID_V2.items():
        d = step(g)
        var_quant = d ** 2 / 12.0
        var_b_obs = diag[p]["var_b_post_Teb"]   # T=1.0 口径（受温度压制）
        sigma_b_obs = diag[p]["sigma_b_post"]

        # 模拟：真实 θ ~ N(μ, σ_true²)，量化到网格后的批间方差
        st = SIGMA_TRUE[p]
        sim = []
        for _ in range(2000):
            th = rng.normal(0.41 if p == "mux" else (0.041 if p == "mup" else 0.029),
                            st, size=88) if st > 0 else np.full(88, 0.029)
            q = quantise(th, g)
            sim.append(np.var(q, ddof=1))
        sim = np.array(sim)
        var_b_quant = float(np.mean(sim))

        # 检测下限：需要 var_b > var_quant + σ²_pop 才能被识别
        sigma_detect = float(np.sqrt(max(var_quant, 0.0)))

        out["by_param"][p] = {
            "n_levels": len(g),
            "grid_step": round(d, 6),
            "sigma_true_ref": st,
            "step_over_sigma": round(d / st, 2) if st > 0 else None,
            "var_quant_floor": round(var_quant, 9),
            "var_b_observed": round(var_b_obs, 9),
            "sigma_b_observed": round(sigma_b_obs, 5),
            "var_quant_ge_var_b": bool(var_quant >= var_b_obs),
            "var_b_map": round(var_b_map[p], 9),
            "sigma_b_map": round(float(np.sqrt(var_b_map[p])), 5),
            "var_quant_ge_var_b_map": bool(var_quant >= var_b_map[p]),
            "var_b_sim_quantised": round(var_b_quant, 9),
            "var_true_implied": round(st ** 2, 9),
            "var_b_observed_over_true": (round(var_b_obs / (st ** 2), 4) if st > 0 else None),
            "sigma_detect_floor": round(sigma_detect, 5),
            "verdict_forced_zero": bool(var_quant >= var_b_obs),
            "verdict_forced_zero_map": bool(var_quant >= var_b_map[p]),
        }

    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # COMBINED 逐批标定值的散布 vs 生成机制真值（判定 COMBINED 能否当 σ_pop 的批均值）
    out["COMBINED_vs_true"] = {}
    for p in GRID_V2:
        v = np.array([gp.COMBINED[b][p] for b in gp.COMBINED])
        st = SIGMA_TRUE[p]
        out["COMBINED_vs_true"][p] = {
            "n": len(v), "mean": round(float(v.mean()), 5),
            "sd": round(float(v.std(ddof=1)), 5),
            "min": round(float(v.min()), 5), "max": round(float(v.max()), 5),
            "sigma_true": st,
            "inflation": round(float(v.std(ddof=1) / st), 2) if st > 0 else None,
        }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"{'param':>5} {'水平':>4} {'步距':>7} {'步距/σ':>7} {'量化下限':>10} "
          f"{'var_b(MAP)':>10} {'var_b(T=1)':>10} {'量化≥MAP?':>9} {'量化≥T1?':>8}")
    for p in GRID_V2:
        s = out["by_param"][p]
        sos = f"{s['step_over_sigma']:.2f}" if s["step_over_sigma"] else "—"
        print(f"{p:>5} {s['n_levels']:>4} {s['grid_step']:>7.4f} {sos:>7} "
              f"{s['var_quant_floor']:>10.2e} {s['var_b_map']:>10.2e} {s['var_b_observed']:>10.2e} "
              f"{'是' if s['var_quant_ge_var_b_map'] else '否':>9} "
              f"{'是' if s['verdict_forced_zero'] else '否':>8}")
    print("\n--- COMBINED 逐批标定值的散布 vs 生成机制真值 ---")
    print(f"{'param':>5} {'COMBINED sd':>12} {'真值 σ':>9} {'膨胀倍数':>9} {'范围':>18}")
    for p in GRID_V2:
        c = out["COMBINED_vs_true"][p]
        inf = f"{c['inflation']:.1f}×" if c["inflation"] else "∞(真值0)"
        print(f"{p:>5} {c['sd']:>12.5f} {c['sigma_true']:>9.4f} {inf:>9} "
              f"[{c['min']:.3f}, {c['max']:.3f}]")
    print(f"\n落盘 {OUT}")


if __name__ == "__main__":
    main()
