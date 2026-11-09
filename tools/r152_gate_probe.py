# -*- coding: utf-8 -*-
"""R152 / D-42：产素门控诊断 —— 60–120 h 缺 22% 是「门控未开」还是「速率低」。

假设的由来
----------
`r_p = mu_p · rho_a0 · v_a1 · P_inhib · DO_2_inhib_P · PAA_inhib_P`，而
`v_a1 = a_1/(2·rho_a0)`（`v_2 ≡ 0`，`rho_a0` 完全抵消）⇒ `r_p ∝ a_1 · P_inhib · DO2 · PAA`。

R150 已排除 `a_1`：同相位 X **+10.7%**（生物量高），而 A1/X 只低 4–5% ⇒ `a_1` 不低。
`PAA_inhib_P = 0.5·(1+tanh(y[29] − P_crit_PAA))`，`P_crit_PAA = 200` mg/L 而实测 PAA ~1400 mg/L
⇒ tanh 饱和，`PAA_inhib_P ≡ 1`，PAA 高 33% **不影响**。DO2 同理在通气的批里饱和。

剩下的就是 **`P_inhib`（残糖高斯门控）**：

    P_inhib = 2.5·sd·(sd·√(2π))^-1 · exp(−0.5·((s − mean_P)/sd)²)
            = 2.5/√(2π) · exp(−0.5·((s − 0.002)/1.71e−4)²)

**`P_std_dev = par[3] = 1.5e−3 g/L`（1.5 mg/L）**，`mean_P = par[4] = 0.002 g/L`。
（首版误取 par[5]=mu_v=1.71e−4 并据此得出"硬开关"结论，**已作废**；索引必须从 `model.py` 参数解包段读。）
宽度 1.5 mg/L 与 S 的量级相当 ⇒ 门控是**平滑窗**：`s=0.002`→1.00、`0.0014`→0.92、`0.005`→0.14、`0.008`→3e−4。

而 S 的**相对**残差在 60–120 h 只有 +0.4%（R150）—— 但分母是 |S| 均值，绝对差哪怕只有 1 mg/L
就足以让门控整体翻转。**这就是"糖对、前体过剩、生物量过剩，产物却低"的候选解释。**

本工具**只读 + 标准仿真**，不改引擎、不改参数：用 `sim["S"]` 与 `v3["S"]`（同一 `mean_P/sd`）
分别算 `P_inhib`，比较两条门控曲线。若 `P_inhib_meas >> P_inhib_sim` 于 60–120 h，
则根因是**门控占空比**，不是产素速率 —— 一阶旋钮（`mu_p`）当然改不动。

用法
----
    python tools/r152_gate_probe.py                 # 86 批
    python tools/r152_gate_probe.py --batches 3,22,36,55,59
    python tools/r152_gate_probe.py --workers 6
"""
import argparse
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
ENG = os.path.join(ROOT, "candidate", "indpensim", "v0.1")
sys.path.insert(0, ENG)

PHASE_KEYS = ("0-60", "60-120", "120-180", "180+")
PHASES = (("0-60", 0.0, 60.0), ("60-120", 60.0, 120.0),
          ("120-180", 120.0, 180.0), ("180+", 180.0, 1e9))


def pinhib(s, mean_P, sd):
    """与 model.rhs 逐字相同的门控式（2.5·sd 与 1/(sd·√2π) 相消，但保留原式便于对读）。"""
    return 2.5 * sd * ((sd * np.sqrt(2 * np.pi)) ** -1) * np.exp(-0.5 * ((s - mean_P) / sd) ** 2)


def golden_batches():
    p = os.path.join(ROOT, "runs", "final_validation_v2.json")
    d = json.load(open(p, encoding="utf-8"))
    rows = d.get("rows") or d.get("results") or []
    return sorted({int(r["batch"]) for r in rows if isinstance(r, dict) and "batch" in r})


def one(batch):
    from golden_params import COMBINED, build_params
    import simulate as s

    p = build_params(COMBINED[batch])
    sim, v3 = s.simulate_open_loop(int(batch), p)

    # 门控参数：make_params() 的默认值（build_params 不覆盖 par[4]/par[5]）
    par = s.make_params()
    mean_P, sd = float(par[4]), float(par[3])   # par[3]=P_std_dev=0.0015（par[5] 是 mu_v）

    t = sim["time_h"].to_numpy(float)
    sS = sim["S"].to_numpy(float)
    tv = v3["time_h"].to_numpy(float)
    mS = np.interp(t, tv[np.isfinite(tv)], v3["S"].to_numpy(float)[np.isfinite(tv)])

    g_sim = pinhib(sS, mean_P, sd)
    g_meas = pinhib(mS, mean_P, sd)

    # PAA 门控的饱和程度：PAA_inhib_P = 0.5*(1+tanh(y[29] - par[79]))，par[79]=200 mg/L
    # DO 门控不重算（DOstar_tp 是随压力/进气氧分率变化的动态量），改用相位最低溶氧作替代证据
    aa = float(par[79])
    PAA_inhib = 0.5 * (1 + np.tanh(-aa + sim["PAA"].to_numpy(float)))
    do2 = sim["DO2"].to_numpy(float)

    out = {"batch": int(batch), "mean_P": mean_P, "p_std_dev": sd,
           "s_mean_meas": float(np.mean(mS)), "s_mean_sim": float(np.mean(sS))}
    for name, lo, hi in PHASES:
        m = (t >= lo) & (t < hi)
        if not np.any(m):
            out[name] = {"s_sim": float("nan"), "s_meas": float("nan"),
                         "g_sim": float("nan"), "g_meas": float("nan"),
                         "duty_sim": float("nan"), "duty_meas": float("nan")}
            continue
        out[name] = {
            "s_sim": float(np.mean(sS[m])), "s_meas": float(np.mean(mS[m])),
            "s_p10_sim": float(np.percentile(sS[m], 10)),
            "g_sim": float(np.mean(g_sim[m])), "g_meas": float(np.mean(g_meas[m])),
            "duty_sim": float(np.mean(g_sim[m] > 0.5)), "duty_meas": float(np.mean(g_meas[m] > 0.5)),
            "paa_inhib": float(np.mean(PAA_inhib[m])), "do2_min": float(np.min(do2[m])),
        }
    # 全批积分门控占空（产素"有效时长"）
    out["g_int_sim"] = float(np.trapezoid(g_sim, t)) if hasattr(np, "trapezoid") else float(np.trapz(g_sim, t))
    out["g_int_meas"] = float(np.trapezoid(g_meas, t)) if hasattr(np, "trapezoid") else float(np.trapz(g_meas, t))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", type=str, default="")
    ap.add_argument("--all-100", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    if args.batches:
        bs = [int(x) for x in args.batches.split(",") if x.strip()]
    elif args.all_100:
        bs = list(range(1, 101))
    else:
        bs = golden_batches()
    if args.limit:
        bs = bs[: args.limit]
    print(f"[r152] batches = {len(bs)}; workers = {args.workers}", flush=True)

    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        rows = list(ex.map(one, bs))

    op = os.path.join(ROOT, "runs", "r152_gate_probe.json")
    json.dump({"batches": bs, "rows": rows}, open(op, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    print(f"\nmean_P = {rows[0]['mean_P']:.4g} g/L   P_std_dev = {rows[0]['p_std_dev']:.4g} g/L")
    print("\n=== 分相位（86 批跨批均值）===")
    print("相位      s_sim    s_meas   g_sim  g_meas  占空_sim 占空_meas  PAA门  DO2min")
    for k in PHASE_KEYS:
        v = [r[k] for r in rows if np.isfinite(r[k]["g_sim"])]
        f = lambda key: float(np.mean([x[key] for x in v]))
        print(f"{k:8s} {f('s_sim'):8.5f} {f('s_meas'):8.5f} {f('g_sim'):7.4f} {f('g_meas'):7.4f}"
              f"  {f('duty_sim'):7.3f}  {f('duty_meas'):7.3f}  {f('paa_inhib'):5.3f} {f('do2_min'):6.2f}")

    gi = np.array([r["g_int_sim"] for r in rows])
    gm = np.array([r["g_int_meas"] for r in rows])
    print(f"\n全批积分门控 g_int: sim 中位 {np.median(gi):.1f}  meas 中位 {np.median(gm):.1f}"
          f"  ⇒ meas/sim 中位 **{np.median(gm / np.maximum(gi, 1e-9)):.2f}×**")

    print("\n=== 60–120 h 最缺的 12 批 ===")
    print(" 批  s_sim   s_meas   g_sim  g_meas  占空_sim 占空_meas  g_int比")
    for r in sorted(rows, key=lambda r: r["60-120"]["g_sim"] - r["60-120"]["g_meas"])[:12]:
        x = r["60-120"]
        print(f"{r['batch']:>3d} {x['s_sim']:7.5f} {x['s_meas']:7.5f} {x['g_sim']:7.4f} {x['g_meas']:7.4f}"
              f"  {x['duty_sim']:7.3f}  {x['duty_meas']:7.3f}  {r['g_int_meas'] / max(r['g_int_sim'], 1e-9):6.2f}")
    print(f"\nwritten: {op}")


if __name__ == "__main__":
    main()
