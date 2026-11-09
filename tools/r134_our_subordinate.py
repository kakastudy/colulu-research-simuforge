# -*- coding: utf-8 -*-
"""R134 T4: OUR 是否只是 X 的派生通道（"从属验证"）。

动机：
  OUR 通道 nRMSE 36.8%、R² 0.686、gain 1.267、bias +26.7%，被判 B 类"需机制项"。
  但 OUR 与 X 的**幅度偏差方向与量级几乎相同**（X gain 1.2115 / bias +21.2%），
  提示 OUR 的误差可能是 X 幅度误差的**继承**，而不是独立通道的独立问题。
  若成立，则对 OUR 单独扫参在数学上不成立（计划 §7.1 明确不做），
  OUR 应记为"从属通道"，只能随 X 一起动。

三种检验（预先登记）：
  H1 跨批一致性：86 批的 OUR gain(k_our) 与 X gain(k_x) 的相关系数与回归斜率。
     定义 obs ≈ k·sim。若 corr ≥ 0.6 且斜率 ≈ 1 → 同源。
  H2 幅度继承：把 sim OUR 乘以 k_x（即用 X 的幅度校正量去校正 OUR），
     看 OUR nRMSE 是否大幅下降（≥40% 相对下降 → 主要误差是继承来的）。
  H3 结构派生：批内回归 OUR = a·(dX/dt) + b·X + c
     在 sim 侧 R² 高 → OUR 在模型内部就是 X 的泛函（不携带独立信息）；
     在 obs 侧（用 12h 化验 X 差分）R² 也较高 → 化验侧同样如此。

结论口径：
  subordinate   H2 相对下降 ≥40% 且 H1 corr ≥0.6     → 从属，禁止单独扫参
  partial       仅一项成立                          → 部分从属，需机制项时与 X 联动
  independent   两项都不成立                        → 独立通道，可单独处置
"""
import argparse
import glob
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
CACHE = os.path.join(ROOT, "platform", ".cache")
OFF_DELAY_H = 4.0


def _r2(x, y):
    if len(x) < 3 or np.std(x) < 1e-12 or np.std(y) < 1e-12:
        return None
    b, a = np.polyfit(x, y, 1)
    pred = a + b * x
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    return None if ss_tot < 1e-12 else 1.0 - ss_res / ss_tot


def _nrmse(sim, obs):
    m = float(np.mean(obs))
    if abs(m) < 1e-12:
        return None
    return float(np.sqrt(np.mean((sim - obs) ** 2))) / abs(m) * 100.0


def _gain(sim, obs):
    """obs ≈ k·sim 的最小二乘 k。"""
    d = float(np.sum(sim * sim))
    return None if d < 1e-12 else float(np.sum(sim * obs) / d)


def analyse(path):
    d = json.load(open(path, encoding="utf-8"))
    t = np.asarray(d["t"], float)
    sim_our = np.asarray(d["sim"]["OUR"], float)
    sim_x = np.asarray(d["sim"]["X"], float)
    obs_our = d["obs"].get("OUR")
    off_x = d["off"].get("X")
    if not obs_our or not off_x:
        return None
    obs_our = np.asarray(obs_our, float)
    n = min(len(t), len(obs_our))
    t, sim_our, sim_x, obs_our = t[:n], sim_our[:n], sim_x[:n], obs_our[:n]

    # ---- OUR 原始误差 ----
    our_nrmse = _nrmse(sim_our, obs_our)
    k_our = _gain(sim_our, obs_our)

    # ---- X 的幅度校正量（化验 X 为 12h 粒度，插值到 2h 网格）----
    xt = np.asarray([p[0] for p in off_x], float)
    xv = np.asarray([p[1] for p in off_x], float)
    x_obs_on_grid = np.interp(t + OFF_DELAY_H, xt, xv)
    m = np.isfinite(x_obs_on_grid)
    k_x = _gain(sim_x[m], x_obs_on_grid[m]) if m.sum() > 3 else None

    # ---- H2：用 X 的幅度校正量校正 OUR ----
    our_nrmse_after = None
    rel_improve = None
    if k_x and k_x > 0:
        our_scaled = sim_our * k_x
        our_nrmse_after = _nrmse(our_scaled, obs_our)
        if our_nrmse and our_nrmse_after is not None:
            rel_improve = (our_nrmse - our_nrmse_after) / our_nrmse * 100.0

    # ---- H3：模型内部/化验侧的"X 泛函"检验 ----
    dX_sim = np.gradient(sim_x, t)
    A = np.column_stack([dX_sim, sim_x, np.ones_like(dX_sim)])
    coef, *_ = np.linalg.lstsq(A, sim_our, rcond=None)
    our_from_x_sim = A @ coef
    r2_sim = _r2(our_from_x_sim, sim_our)

    r2_obs = None
    dX_obs = np.gradient(x_obs_on_grid[m], t[m])
    if m.sum() > 6 and np.std(dX_obs) > 1e-12:
        B = np.column_stack([dX_obs, x_obs_on_grid[m], np.ones_like(dX_obs)])
        cb, *_ = np.linalg.lstsq(B, obs_our[m], rcond=None)
        r2_obs = _r2(B @ cb, obs_our[m])

    return {"n": int(n), "our_nrmse": round(our_nrmse, 2), "our_gain": round(k_our, 4),
            "our_bias_pct": round((float(np.mean(sim_our)) / float(np.mean(obs_our)) - 1) * 100, 2),
            "x_gain": None if k_x is None else round(k_x, 4),
            "our_nrmse_after_x_correction": None if our_nrmse_after is None else round(our_nrmse_after, 2),
            "rel_improve_pct": None if rel_improve is None else round(rel_improve, 2),
            "r2_our_from_x_sim": None if r2_sim is None else round(r2_sim, 4),
            "r2_our_from_x_obs": None if r2_obs is None else round(r2_obs, 4)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "runs", "p3", "r134_our_subordinate.json"))
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(CACHE, "b*.json")))
    print("=" * 100)
    print("R134 T4 OUR 从属验证 —— OUR 的误差是继承自 X，还是独立通道的独立问题")
    print(f"批数 {len(files)}；定义 obs ≈ k·sim（k<1 表示模型偏高）")
    print("=" * 100, flush=True)

    per_batch = {}
    for f in files:
        b = int(os.path.basename(f)[1:3])
        try:
            r = analyse(f)
        except Exception as e:
            r = {"error": str(e)}
        if r:
            per_batch[b] = r

    ok = {b: r for b, r in per_batch.items() if "error" not in r and r.get("x_gain")}
    if not ok:
        print("无可分析批次")
        return

    ko = np.array([r["our_gain"] for r in ok.values()])
    kx = np.array([r["x_gain"] for r in ok.values()])
    imp = np.array([r["rel_improve_pct"] for r in ok.values() if r["rel_improve_pct"] is not None])
    r2s = np.array([r["r2_our_from_x_sim"] for r in ok.values() if r["r2_our_from_x_sim"] is not None])
    r2o = np.array([r["r2_our_from_x_obs"] for r in ok.values() if r["r2_our_from_x_obs"] is not None])

    # H1 跨批一致（只取相关性与"是否同向"，斜率单独作为放大因子报告）
    corr = float(np.corrcoef(ko, kx)[0, 1]) if len(ko) > 3 else None
    slope, intercept = (np.polyfit(kx, ko, 1) if len(ko) > 3 else (None, None))
    amp_ratio = float(np.median(ko / kx)) if len(ko) else None   # 放大因子：>1 表示 OUR 比 X 更偏

    h1 = bool(corr is not None and corr >= 0.6)
    h2 = bool(len(imp) and np.median(imp) >= 40.0)

    print(f"\n{'批':>3s} {'OUR nRMSE':>10s} {'k_our':>7s} {'k_x':>7s} {'校正后':>7s} "
          f"{'改善%':>7s} {'R²(sim)':>8s} {'R²(obs)':>8s}")
    print("-" * 100)
    for b in sorted(ok):
        r = ok[b]
        print(f"{b:>3d} {r['our_nrmse']:>10.1f} {r['our_gain']:>7.3f} {r['x_gain']:>7.3f} "
              f"{(r['our_nrmse_after_x_correction'] if r['our_nrmse_after_x_correction'] is not None else float('nan')):>7.1f} "
              f"{(r['rel_improve_pct'] if r['rel_improve_pct'] is not None else float('nan')):>7.1f} "
              f"{(r['r2_our_from_x_sim'] if r['r2_our_from_x_sim'] is not None else float('nan')):>8.3f} "
              f"{(r['r2_our_from_x_obs'] if r['r2_our_from_x_obs'] is not None else float('nan')):>8.3f}")

    print("\n" + "=" * 100)
    print("三项检验")
    print("=" * 100)
    print(f"  H1 跨批一致性：corr(k_our, k_x) = {corr:.3f}（{'通过' if h1 else '未通过'}）；"
          f"回归 k_our = {slope:.3f}·k_x {intercept:+.3f}")
    print(f"     中位 k_our = {np.median(ko):.3f}，中位 k_x = {np.median(kx):.3f}，"
          f"放大因子 k_our/k_x 中位 = {amp_ratio:.3f}")
    print(f"  H2 幅度继承：用 k_x 校正 OUR 后 nRMSE 相对改善中位 {np.median(imp):.1f}% "
          f"（{sum(imp>=40)}/{len(imp)} 批 ≥40%）→ {'通过' if h2 else '未通过'}")
    print(f"  H3 结构派生：OUR 由 [dX/dt, X] 线性重建 R² 中位 "
          f"sim {np.median(r2s):.4f} / obs {np.median(r2o):.4f}")

    # 三态判定：主从关系成立且能解释大半 → subordinate；只成立一项 → partial
    if h1 and h2:
        verdict, why = "subordinate", "幅度误差与 X 同源且 X 校正可解释大半 → 从属通道，禁止单独扫参"
    elif h1 or h2:
        verdict = "partial"
        why = (f"与 X 同源（corr {corr:.2f}、可由 X 重建 R² {np.median(r2s):.2f}），"
               f"但 X 幅度只能解释 {np.median(imp):.0f}% 误差；且 k_our/k_x 中位 {amp_ratio:.2f}"
               f"（OUR 的幅度偏差比 X 再高约 {(1/amp_ratio-1)*100:.0f}%），边际敏感度 "
               f"dk_our/dk_x = {slope:.2f} → 从属但带放大：不得单独扫参，须待 X 收敛后复评")
    else:
        verdict, why = "independent", "两项均不成立 → OUR 有独立信息，可单独处置"
    print(f"\n  结论：【{verdict}】{why}")

    out = {"meta": {"n": len(ok), "offline_delay_h": OFF_DELAY_H,
                    "hypotheses": {"H1": "corr(k_our,k_x)>=0.6 且斜率≈1",
                                   "H2": "k_x 校正后 nRMSE 相对改善中位 >=40%",
                                   "H3": "R²(OUR ~ dX/dt, X) 参考量"}},
           "summary": {"corr_kour_kx": round(corr, 4) if corr else None,
                       "slope_kour_on_kx": round(float(slope), 4) if slope is not None else None,
                       "median_k_our": round(float(np.median(ko)), 4),
                       "median_k_x": round(float(np.median(kx)), 4),
                       "amplification_kour_over_kx": round(amp_ratio, 4) if amp_ratio else None,
                       "median_improve_pct": round(float(np.median(imp)), 2) if len(imp) else None,
                       "median_r2_sim": round(float(np.median(r2s)), 4) if len(r2s) else None,
                       "median_r2_obs": round(float(np.median(r2o)), 4) if len(r2o) else None,
                       "our_nrmse_med": round(float(np.median([r["our_nrmse"] for r in ok.values()])), 2),
                       "H1_pass": h1, "H2_pass": h2,
                       "verdict": verdict, "why": why},
           "per_batch": {str(k): v for k, v in per_batch.items()}}
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"\nSaved: {args.out}")


if __name__ == "__main__":
    main()
