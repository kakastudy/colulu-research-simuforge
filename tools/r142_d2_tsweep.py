# -*- coding: utf-8 -*-
"""R142 / D-2 Part D：后验温度敏感性 —— σ_pop 对温度口径的依赖。

Part A–C 已定位两条机制（温度 T_EB=1.0 摊平、网格量化下限）。本脚本给出
**敏感性带**：把 T 从 1e-3 扫到 1.0，逐点重算

    var_b(T) = var(θ̂_b(T))     θ̂_b(T) = softmax(-(L-L_min)/T) 下的后验均值
    var_w(T) = mean(var_post,b(T))
    σ_pop(T) = sqrt(max(var_b - var_w, 0))

并定位 `T_crit`（σ_pop 由 0 转正的临界温度）与 `T_natural`（AIC/BIC 型经验
贝叶斯 T：使池级 σ(T) 与之自洽）。

判读：
  - 若 σ_pop 仅在 T ≪ ΔL 的窄窗内非零 → 该窗内后验只保留极少数点，
    是**伪精度**（后验被单一网格点主导），不可采信。
  - 若在 T ≈ ΔL 的量级上 σ_pop 即非零 → 结论有实质支撑。

输出：runs/p3/r142_d2_tsweep.json
"""
import json
import os

import numpy as np

_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
LOG = os.path.join(_ROOT, "runs", "hier_est", "train_theta_v2.jsonl")
OUT = os.path.join(_ROOT, "runs", "p3", "r142_d2_tsweep.json")
PARAMS = ("mux", "mup", "m_s")
LOSS_CAP = 9e5
TS = [1e-3, 2e-3, 5e-3, 1e-2, 2e-2, 5e-2, 1e-1, 2e-1, 3e-1, 5e-1, 1.0]


def load():
    recs = [json.loads(l) for l in open(LOG, encoding="utf-8")]
    out = []
    for r in recs:
        sw = [c for c in (r.get("sweep") or []) if c["loss"] < LOSS_CAP]
        if len(sw) >= 20:
            out.append(sw)
    return out


def stats(sweeps, param, T):
    th, vw, ess = [], [], []
    for sw in sweeps:
        L = np.array([c["loss"] for c in sw])
        v = np.array([c[param] for c in sw])
        w = np.exp(-(L - L.min()) / T)
        w /= w.sum()
        m = float(w @ v)
        th.append(m)
        vw.append(float(w @ (v - m) ** 2))
        ess.append(float(1.0 / np.sum(w ** 2)))
    th = np.array(th); vw = np.array(vw)
    var_b = float(np.var(th, ddof=1))
    var_w = float(np.mean(vw))
    return {"T": T, "var_b": round(var_b, 9), "var_w": round(var_w, 9),
            "sigma_pop": round(float(np.sqrt(max(var_b - var_w, 0.0))), 6),
            "ESS_med": round(float(np.median(ess)), 2),
            "sigma_b": round(float(np.std(th, ddof=1)), 5),
            "gap": round(var_b - var_w, 9)}


def main():
    sweeps = load()
    out = {"n_batches": len(sweeps), "by_param": {}}
    for p in PARAMS:
        rows = [stats(sweeps, p, T) for T in TS]
        tcrit = None
        for i in range(1, len(rows)):
            if rows[i - 1]["sigma_pop"] == 0 and rows[i]["sigma_pop"] > 0:
                tcrit = rows[i]["T"]
            if rows[i - 1]["sigma_pop"] > 0 and rows[i]["sigma_pop"] == 0:
                pass
        out["by_param"][p] = {"sweep": rows, "T_crit": tcrit}
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    for p in PARAMS:
        print(f"\n=== {p} ===（T_crit: σ_pop 首次转正的温度 = {out['by_param'][p]['T_crit']}）")
        print(f"{'T':>8} {'ESS':>7} {'σ_b':>9} {'var_b':>10} {'var_w':>10} {'gap':>11} {'σ_pop':>8}")
        for r in out["by_param"][p]["sweep"]:
            print(f"{r['T']:>8.3f} {r['ESS_med']:>7.2f} {r['sigma_b']:>9.5f} "
                  f"{r['var_b']:>10.2e} {r['var_w']:>10.2e} {r['gap']:>11.2e} {r['sigma_pop']:>8.5f}")
    print(f"\n参考 σ_gen: mux 0.025 / mup 0.0025")
    print(f"落盘 {OUT}")


if __name__ == "__main__":
    main()
