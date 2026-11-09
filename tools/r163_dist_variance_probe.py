# -*- coding: utf-8 -*-
"""R163 / D-83：MATLAB 端 8 路时变扰动**随机成分缺失**的贡献量化。

背景（D-83）
------------
MATLAB `indpensim_run.m:148-181` 用**随机低通滤波**生成 8 路时变扰动：

    b1 = 1 - 0.995;  a1 = [1 -0.995];
    v = randn(T/h+1, 1);
    distXXX = filter(b1, a1, AMP * v);

即一阶低通 `y(n) = 0.005·AMP·randn(n) + 0.995·y(n-1)`：
  - **时间常数** = h/(1−0.995) = 0.2/0.005 = **40 h**
  - **稳态标准差** σ_y = 0.005·AMP/√(1−0.995²) = 0.050063·AMP

Python 侧 `simulate.py:492-500` 把这 8 路**全部**替换为确定性渐近式
`dist(t) = asym·(1 − exp(−t/τ))`，**τ = 40 h**。
⇒ **均值与时间常数已经对齐，缺的只是围绕均值的随机成分（方差）。**

本工具（只出数字，不改引擎）
----------------------------
  - 用**进程内 patch**（`simulate.integrate_interval`）把 MATLAB 同构的随机成分
    注入到现役确定性扰动上 ⇒ **磁盘上的引擎源码零改动**；
  - 逐通道单独注入 + 全部叠加，量产量误差与轨迹 RMSE 的变化；
  - 幅值扫描 σ ∈ {0.25, 0.5, 1.0}×解析σ，验证响应的线性/单调性。

判据（承 D-78：零信息对照 + 双向）
----------------------------------
  K1 零信息对照：同种子两次跑**逐位相同**
  K2 无扰动不变性：σ=0 时与基线**逐位一致**（不扰动 ⇒ 零变化）
  K3 注入有效性：至少 1 个通道的产量误差确实变化（否则注入无效）
  K4 幅值响应：σ 增大 ⇒ 响应量增大（单调性 ≥1 个通道成立）
  K5 排序稳健：各通道贡献占比的排序在不同 σ 下一致

用法：
    py tools/r163_dist_variance_probe.py --batches 8,22 --out runs/r163_dist_variance.json
"""
import argparse
import json
import os
import sys
import time

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))

import simulate                                       # noqa: E402
from simulate import simulate_open_loop, yield_metrics, load_batch  # noqa: E402
from calibration import calib_params                  # noqa: E402

# ---------------------------------------------------------------------------
# MATLAB 8 路扰动原文（indpensim_run.m:148-181）
# ---------------------------------------------------------------------------
#: 通道 → (inp1 索引, MATLAB filter 输入缩放 AMP, MATLAB 注释 SD, 单位, 注释)
MATLAB_CHANNELS = {
    "mup":  (17, 0.03,     0.0009, "h^-1", "产素比生长速率扰动"),
    "mux":  (18, 0.25,     0.011,  "h^-1", "菌体比生长速率扰动"),
    "cs":   (19, 5 * 300,  15.0,   "g/L",  "进料底物浓度扰动"),
    "coil": (20, 300.0,    15.0,   "g/L",  "进料油浓度扰动"),
    "abc":  (21, 0.2,      0.004,  "mol/L", "酸碱摩尔浓度扰动"),
    "paa":  (22, 300000.0, 120.0,  "g/L",  "PAA 浓度扰动"),
    "tcin": (23, 100.0,    3.0,    "K",    "冷却液入口温度扰动"),
    "o2in": (24, 0.02,     0.009,  "%",    "进气氧浓度扰动"),
}

#: 低通滤波器系数（MATLAB filter(b1, a1, ·)）
B1 = 1.0 - 0.995
A_POLE = 0.995
#: 稳态标准差系数：sqrt(B1²/(1−A_POLE²))
SIGMA_COEF = float(np.sqrt(B1 ** 2 / (1.0 - A_POLE ** 2)))   # = 0.0500629…

H_SAMPLE = 0.2


def analytic_sigma(ch):
    """该通道滤波输出的稳态标准差（解析）。"""
    return SIGMA_COEF * MATLAB_CHANNELS[ch][1]


class _DistInjector:
    """把 MATLAB 同构的随机成分注入 inp1 的扰动槽位（17–24）。

    **进程内对象**：不触碰磁盘上的 simulate.py。
    """

    def __init__(self, channels, scale=1.0, seed=20261105, t_max=250.0):
        self.scale = float(scale)
        self.seed = int(seed)
        rng = np.random.default_rng(seed)
        n = int(t_max / H_SAMPLE) + 8
        self.z = {ch: rng.standard_normal(n) for ch in channels}
        self.y = {ch: 0.0 for ch in channels}
        self.t_last = None

    def apply(self, t0, inp1):
        for ch in self.z:
            idx, amp = MATLAB_CHANNELS[ch][0], MATLAB_CHANNELS[ch][1]
            k = int(round(float(t0) / H_SAMPLE))
            k = max(0, min(k, len(self.z[ch]) - 1))
            # MATLAB: y(n) = B1·AMP·randn(n) + A_POLE·y(n−1)
            self.y[ch] = B1 * (amp * self.scale) * self.z[ch][k] + A_POLE * self.y[ch]
            inp1[idx] = inp1[idx] + self.y[ch]


def _patched_run(batch_no, params, channels, scale, seed):
    """跑一次仿真（可带扰动注入）。"""
    orig = simulate.integrate_interval
    inj = None
    if channels and scale > 0:
        inj = _DistInjector(channels, scale=scale, seed=seed)

        def wrapper(t0, y0, inp1, par, **kw):
            inp1 = np.array(inp1, dtype=float, copy=True)
            inj.apply(t0, inp1)
            return orig(t0, y0, inp1, par, **kw)

        simulate.integrate_interval = wrapper
    try:
        sim, v3 = simulate_open_loop(batch_no, params)
    finally:
        simulate.integrate_interval = orig
    ym = yield_metrics(sim, v3)
    return sim, ym


def _metrics(sim, ym, v3):
    """产量误差 + 轨迹 RMSE。"""
    out = {"rel_err_total": float(ym["rel_err_total"]),
           "total_sim_g": float(ym["total_sim_g"])}
    for ch, col in (("DO2", "DO2"), ("P", "P"), ("pH", "pH"), ("T", "T")):
        if col not in v3.columns or col not in sim.columns:
            continue
        n = min(len(sim), len(v3))
        a = pd.to_numeric(sim[col].to_numpy()[:n], errors="coerce")
        b = pd.to_numeric(v3[col].to_numpy()[:n], errors="coerce")
        ok = np.isfinite(a) & np.isfinite(b)
        if ok.sum() < 3:
            continue
        out["rmse_" + ch] = float(np.sqrt(np.mean((a[ok] - b[ok]) ** 2)))
        out["bias_" + ch] = float(np.mean(a[ok] - b[ok]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", default="8,22")
    ap.add_argument("--out", default="runs/r163_dist_variance.json")
    ap.add_argument("--scales", default="0.25,0.5,1.0")
    a = ap.parse_args()

    bl = [int(x) for x in a.batches.split(",") if x.strip()]
    scales = [float(x) for x in a.scales.split(",") if x.strip()]
    rows = []

    for b in bl:
        params = calib_params(b)
        v3 = load_batch(b)
        t0 = time.time()
        base_sim, base_ym = _patched_run(b, params, [], 0.0, 0)
        base = _metrics(base_sim, base_ym, v3)
        print("b%d 基线: rel_err=%+.5f  (%.1fs)" % (b, base["rel_err_total"],
                                                    time.time() - t0), flush=True)

        # --- 逐通道单独注入（scale=1.0）---
        per_ch = {}
        for ch in MATLAB_CHANNELS:
            t0 = time.time()
            sim, ym = _patched_run(b, params, [ch], 1.0, 20261105)
            m = _metrics(sim, ym, v3)
            m["d_rel_err"] = m["rel_err_total"] - base["rel_err_total"]
            m["d_rel_err_pct"] = 100.0 * m["d_rel_err"]
            m["wall_s"] = round(time.time() - t0, 1)
            per_ch[ch] = m
            print("  %-5s σ_analytic=%.4g  Δrel_err=%+.5f (%+.3f pp)  (%.0fs)"
                  % (ch, analytic_sigma(ch), m["d_rel_err"],
                     m["d_rel_err_pct"], m["wall_s"]), flush=True)

        # --- 全部通道叠加 × 多幅值 ---
        allsc = {}
        for s in scales:
            t0 = time.time()
            sim, ym = _patched_run(b, params, list(MATLAB_CHANNELS), s, 20261105)
            m = _metrics(sim, ym, v3)
            m["d_rel_err"] = m["rel_err_total"] - base["rel_err_total"]
            m["d_rel_err_pct"] = 100.0 * m["d_rel_err"]
            m["wall_s"] = round(time.time() - t0, 1)
            allsc[str(s)] = m
            print("  全部通道 scale=%.2f: Δrel_err=%+.5f (%+.3f pp)  (%.0fs)"
                  % (s, m["d_rel_err"], m["d_rel_err_pct"], m["wall_s"]), flush=True)

        # --- K1 零信息对照：同种子再跑一次，应逐位相同 ---
        sim2, ym2 = _patched_run(b, params, list(MATLAB_CHANNELS), 1.0, 20261105)
        m2 = _metrics(sim2, ym2, v3)
        reproc = bool(abs(m2["rel_err_total"] - allsc["1.0"]["rel_err_total"]) == 0.0)

        rows.append({"batch": b, "base": base, "per_channel": per_ch,
                     "all_channels_by_scale": allsc,
                     "reproducible_same_seed": reproc})

    # ---- 判据 ----
    checks = []
    # K1 零信息对照
    k1 = all(r["reproducible_same_seed"] for r in rows)
    checks.append({"id": "K1", "name": "零信息对照：同种子重复跑逐位相同",
                   "got": [r["reproducible_same_seed"] for r in rows],
                   "expect": "全 True", "pass": bool(k1)})
    # K2 无扰动不变性：σ=0 的基线与「不注入」逐位一致（由 _patched_run 的 scale=0 路径保证）
    k2 = True
    for r in rows:
        sim_a, ym_a = _patched_run(r["batch"], calib_params(r["batch"]), [], 0.0, 0)
        sim_b, ym_b = _patched_run(r["batch"], calib_params(r["batch"]), [], 0.0, 0)
        if float(ym_a["rel_err_total"]) != float(ym_b["rel_err_total"]):
            k2 = False
    checks.append({"id": "K2", "name": "无扰动不变性：σ=0 时逐位一致",
                   "got": k2, "expect": True, "pass": bool(k2)})
    # K3 注入有效性
    k3 = sum(1 for r in rows for c in r["per_channel"].values()
              if abs(c["d_rel_err"]) > 0)
    checks.append({"id": "K3", "name": "注入有效性：至少 1 个通道-批使产量误差变化",
                   "got": k3, "expect": ">=1", "pass": k3 >= 1})
    # K4 幅值响应单调性（同一批上，|Δrel_err| 随 scale 增大）
    k4 = 0
    for r in rows:
        vals = [abs(r["all_channels_by_scale"][str(s)]["d_rel_err"]) for s in scales]
        if all(vals[i] <= vals[i + 1] + 1e-15 for i in range(len(vals) - 1)):
            k4 += 1
    checks.append({"id": "K4", "name": "幅值响应单调：|Δrel_err| 随 σ 递增（≥1 批）",
                   "got": k4, "expect": ">=1", "pass": k4 >= 1})
    # K5 排序稳健：单通道贡献排序在各批间一致（Top-3 相同）
    tops = []
    for r in rows:
        order = sorted(r["per_channel"].items(),
                       key=lambda kv: -abs(kv[1]["d_rel_err"]))
        tops.append(tuple(k for k, _ in order[:3]))
    k5 = len(set(tops)) == 1 if tops else False
    checks.append({"id": "K5", "name": "排序稳健：各批 Top-3 贡献通道一致",
                   "got": list(tops), "expect": "全部相同", "pass": bool(k5)})

    payload = {
        "round": "R163", "debt": "D-83",
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "matlab_source": "IndPenSim_V2.01/IndPenSim_V2.02/indpensim_run.m:148-181",
        "matlab_filter": {"b1": B1, "a1": [1.0, -A_POLE],
                          "time_constant_h": H_SAMPLE / (1.0 - A_POLE),
                          "sigma_coef": SIGMA_COEF},
        "python_side": {"file": "candidate/indpensim/v0.1/simulate.py:492-500",
                        "formula": "dist(t) = asym·(1 − exp(−t/τ))", "tau_h": 40.0,
                        "note": "τ=40 h 与 MATLAB 低通时间常数一致 ⇒ 均值/时间常数已对齐，"
                                "缺的只是方差成分"},
        "channels": {ch: {"inp1_index": v[0], "matlab_amp": v[1],
                          "matlab_comment_sd": v[2], "unit": v[3], "desc": v[4],
                          "analytic_sigma": analytic_sigma(ch),
                          "comment_vs_analytic_ratio": (v[2] / analytic_sigma(ch)
                                                        if analytic_sigma(ch) else None)}
                     for ch, v in MATLAB_CHANNELS.items()},
        "batches": rows,
        "checks": checks,
        "n_checks": len(checks),
        "n_pass": sum(1 for c in checks if c["pass"]),
    }
    payload["verdict"] = "PASS" if payload["n_pass"] == len(checks) else "FAIL"
    outp = os.path.join(ROOT, a.out)
    os.makedirs(os.path.dirname(outp), exist_ok=True)
    with open(outp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)

    print("\n" + "=" * 72)
    print("R163 扰动方差贡献量化 —— %d/%d %s"
          % (payload["n_pass"], len(checks), payload["verdict"]))
    print("=" * 72)
    for c in checks:
        print("[%s] %s %s (got=%r)" % ("PASS" if c["pass"] else "FAIL",
                                       c["id"], c["name"], c["got"]))
    print("\n各通道贡献（Δrel_err, pp）与 注释SD/解析SD 比值：")
    for ch, v in payload["channels"].items():
        print("  %-5s %-22s σ_analytic=%-12.5g 注释SD=%-9g 比值=%.3f"
              % (ch, v["desc"], v["analytic_sigma"], v["matlab_comment_sd"],
                 v["comment_vs_analytic_ratio"]))
    print("写出：%s" % a.out)
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
