# -*- coding: utf-8 -*-
"""R150 / D-40：P 通道的可辨识性 —— `mu_p` / `mu_h` / `k_deg` 能不能分开。

为什么必须先做这一步
--------------------
D-40 的原定处置是"联合标定 `k_deg / Y_sP / Y_sX / mu_p`"。但 R138 已经实测过
**全局启用 `p_deg_rate` 会让每批单向恶化**（b8 −4.04%→−15.28%、b29 −3.43%→−22.24%）。
当时归因为"`k_deg` 估计混入了稀释项"，本轮提出一个更强的解释：

    P 方程 `dy[3] = r_p - k_deg·P - P·D`
    而      `r_p = 产素项 - mu_h·P`
    ⇒        `dP/dt = 产素项 - (mu_h + k_deg + D)·P`

**`mu_h` 与 `k_deg` 在 P 方程里只以和的形式出现。** 那么"单独开 `k_deg`"必然
等价于"把 `mu_h` 乘大"——而 `mu_h` 已经标到让 P 末端对上了，再叠一项就是重复计数。
这不是"k_deg 标错了"，是**结构上不可辨识**。

`mu_h` 唯一能被单独看到的地方是 pH 方程（`r_p_ph = 产素项 + (_adj−1)·mu_h·P`，
默认 `net` 下 `_adj=0` ⇒ 系数 −1），而 R149 已判 pH 不可作标定目标。

本工具做两件事
--------------
1. **数值 Jacobian + SVD**（`--stage svd`）：对 P 轨迹求 `∂P/∂θ`，
   `θ = (ln mu_p, ln mu_h_scale, k_deg)`，报条件数与最小奇异方向。
   若最小方向 ≈ `(0, +, −)`，则"mu_h 与 k_deg 可互换"，不可辨识得到证实。
2. **置换检验**（`--stage swap`）：直接跑 `mu_h` 降 ε、`k_deg` 补等量的组合，
   看 P 轨迹变化是否远小于单独扰动任一个。这是对 (1) 的独立复核，
   不依赖 Jacobian 的线性化。

参数位置（本轮逐个核对过，不是凭记忆）
- `mu_p`   = `par[0]`，基线 **0.012**。引擎里 `mu_p = par[0] + distMuP`
  （`model.py:284`），**没有** `par[0]` 的覆盖口，但 `dist_mup` 是加性扰动入口
  ⇒ 用 `dist_mup = 0.012·δ` 做等效差分，**不需要改引擎**。
  注意 `params["mup"]` 是**状态变量** `IDX["mup"]` 的初值（`simulate.py:101/229`），
  不是 `par[0]`——误用它会让扰动完全无效（R147 的参数未透传事故同型）。
- `mu_h`   = `k4(pH,T) * par[18]`（`inhib=2`，默认），`par[18]` 基线 1.0。
  `params["mu_h_scale"]` → `par[18]` 是原生覆盖口（`simulate.py:261`）。
  `par[19]=0.003` 只是初值，分支里被覆盖，**扰动它无效**。
- `k_deg`  = `params["p_deg_rate"]`（`rhs` 的独立入参，非 `par` 数组），基线 **0.0**。

**自检**：每个扰动方向的轨迹差必须 > 0，否则判为"参数未生效"并报错——
R147 曾因参数没透传到调用点，三条臂跑出完全相同的数字而误判"不可辨识"。

用法
----
    python tools/r150_ident.py --stage svd  --batches 22,36,55,59 --workers 4
    python tools/r150_ident.py --stage swap --batches 22,36,55,59 --workers 4

输出：runs/r150_ident_{svd,swap}.json
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

# 数值差分步长。mu_p / mu_h 用对数尺度（乘性参数，2% 足以跨出数值噪声又不过界）；
# k_deg 基线为 0，不能取对数，用绝对步长 1e-3 /h（≈ mu_h 量级 0.0037 的 27%）。
# 统一扰动幅度：三个参数都扰到"等价于 mu_h 变化 5%"的量级（见 jac_one 的注释）。
EPS = 0.05
MU_P_BASE = 0.012  # par[0] 基线


def mu_h_typical(batch):
    """mu_h 的典型量级 = k4(pH_med, T_med) · par[18]。

    注意 T 的单位是**开尔文**（数据里 297.7–299.1 K ≈ 24.5–26 °C）。
    R147 报告里的 "pH 6.5 → 3.713e-03" 是在另一个 T 下算的；这里现算，不硬编码，
    避免把 swap 的等量补偿量搞错一个量级。
    """
    import simulate as s
    from simulate import make_params
    par = make_params()
    B = [par[i] for i in range(80, 85)]
    d = s.load_batch(int(batch))
    ph = float(np.nanmedian(d["pH"].to_numpy(float)))
    T = float(np.nanmedian(d["T"].to_numpy(float)))
    return float(np.exp(B[0] + B[1] * ph + B[2] * T + B[3] * ph ** 2 + B[4] * T ** 2) * par[18])


def base_params(batch):
    from golden_params import COMBINED, build_params
    return build_params(COMBINED[int(batch)])


def run_full(batch, params, mu_p_scale=1.0, mu_h_scale=1.0, kdeg=0.0):
    """跑一批并带上有效性诊断。

    **必须记录 `valid`**：`mu_h` 不只进 P 方程，还进 pH 方程（默认 `net` 口径下
    系数 −1）。降低 `mu_h` ⇒ `r_p` 增大 ⇒ 产碱增多 ⇒ pH 上抬。R149 已测出
    b22 的 pH 峰 6.798 距 7.0 仅 0.198，所以 `mu_h` 的小扰动就可能把批推到
    越界崩溃。**不记 `valid` 会把"崩溃导致 P 暴跌"误读成"降解减少导致 P 上升"**。
    """
    import simulate as s
    p = dict(params)
    if mu_p_scale != 1.0:
        p["dist_mup"] = MU_P_BASE * (mu_p_scale - 1.0)
    if mu_h_scale != 1.0:
        p["mu_h_scale"] = mu_h_scale
    if kdeg:
        p["p_deg_rate"] = float(kdeg)
    sim, v3 = s.simulate_open_loop(int(batch), p)
    va = s.validity(sim)
    return {
        "t": sim["time_h"].to_numpy(float),
        "P": sim["P"].to_numpy(float),
        "valid": bool(va["valid"]),
        "flags": list(va["flags"]),
        "ph_max": float(va["ph_max_pre"]),
        "yield_err": float(s.yield_metrics(sim, v3)["rel_err_total"]),
    }


def run_with(batch, params, mu_p_scale=1.0, mu_h_scale=1.0, kdeg=0.0):
    """跑一批。

    - `mu_p` 用 `dist_mup` 做**加性**等效差分：`dist_mup = par0 · (scale−1)`，
      效果等于把 `par[0]` 乘 scale，且不需要给引擎加覆盖口。
    - `mu_h` 走原生 `mu_h_scale` → `par[18]`（乘性）。
    - `k_deg` 走原生 `p_deg_rate`。
    """
    p = dict(params)
    if mu_p_scale != 1.0:
        p["dist_mup"] = MU_P_BASE * (mu_p_scale - 1.0)
    if mu_h_scale != 1.0:
        p["mu_h_scale"] = mu_h_scale
    if kdeg:
        p["p_deg_rate"] = float(kdeg)
    return p_traj(batch, p)


def jac_one(batch):
    """单批：base + 三个方向的单侧差分，构成 J（行=时间，列=参数）。"""
    b = int(batch)
    pb = base_params(b)
    mu_h_typ = mu_h_typical(b)
    base = run_full(b, pb)
    y0 = base["P"]
    scale = max(float(np.max(np.abs(y0))), 1e-9)

    # 统一口径：三列都换算成 ∂P/∂ε，其中 ε 是"相对 mu_h 的等效变化率"。
    # 三个参数量纲不同（`mu_p`/`mu_h` 是乘性，`k_deg` 是 1/h 的加性），
    # 直接把 ∂P/∂θ 拼在一起做 SVD 得到的条件数没有意义——第一版就是这么错的：
    # `k_deg` 的 1e-3 步长约等于 `mu_h` 的 38%，而另两列只有 2%，
    # 于是 k_deg 的列范数天然大 19 倍，条件数被步长而不是物理决定。

    arms = {
        "mu_p": run_full(b, pb, mu_p_scale=1.0 + EPS),
        "mu_h": run_full(b, pb, mu_h_scale=1.0 + EPS),
        "k_deg": run_full(b, pb, kdeg=EPS * mu_h_typ),
    }
    for name, r in arms.items():
        if float(np.max(np.abs(r["P"] - y0))) == 0.0:
            # R147 的参数未透传事故：扰动"看起来"做了，实际没进方程，
            # 于是三条臂给出相同轨迹，被误读为"完全不可辨识"。
            raise RuntimeError(
                f"b{b}: 扰动 {name} 未改变 P 轨迹（dmax=0）。参数没有生效，"
                f"不能据此判不可辨识。")

    names = ["mu_p", "mu_h", "k_deg"]
    J = np.column_stack([(arms[n]["P"] - y0) / (EPS * scale) for n in names])

    U, S, Vt = np.linalg.svd(J, full_matrices=False)
    cond = float(S[0] / S[-1]) if S[-1] > 0 else float("inf")
    vmin = Vt[-1]
    colnorm = {n: float(np.linalg.norm(J[:, i])) for i, n in enumerate(names)}
    return {
        "batch": b,
        "peak_P": float(np.max(y0)),
        "mu_h_typ": mu_h_typ,
        "n": int(len(y0)),
        "sv": [float(x) for x in S],
        "cond": cond,
        "v_min": [float(x) for x in vmin],
        "colnorm": colnorm,
        # 关键诊断：若某臂 invalid，则它的 J 列描述的是"崩溃"而不是"敏感性"，
        # 条件数不能用于可辨识性判断。
        "valid_base": base["valid"],
        "valid_arms": {n: arms[n]["valid"] for n in names},
        "phmax_arms": {n: arms[n]["ph_max"] for n in names},
        "phmax_base": base["ph_max"],
    }


def swap_one(args):
    """置换检验：mu_h 降 ε 与 k_deg 补 ε 的组合，P 轨迹变化多大。

    ε 取 `mu_h_typical(batch) · eps_frac`，按批现算（pH/T 逐批不同，k4 差 1.9 倍）。
      A: mu_h_scale = 1 − eps_frac  （mu_h 乘性降）
      B: k_deg = eps_frac · mu_h_typ（k_deg 加性补上等量）
      C: A + B 同时做
    `cancel_ratio = C / max(A,B)` ≈ 0 ⇒ 两者在 P 通道上完全等价（不可辨识）。
    """
    batch, eps_frac = args
    b = int(batch)
    pb = base_params(b)
    mu_h_typ = mu_h_typical(b)
    base = run_full(b, pb)
    y0 = base["P"]

    rA = run_full(b, pb, mu_h_scale=1.0 - eps_frac)
    rB = run_full(b, pb, kdeg=eps_frac * mu_h_typ)
    rC = run_full(b, pb, mu_h_scale=1.0 - eps_frac, kdeg=eps_frac * mu_h_typ)

    scale = max(float(np.max(np.abs(y0))), 1e-9)

    def rel(a):
        return float(np.max(np.abs(a - y0)) / scale)

    def rms(a):
        return float(np.sqrt(np.mean(((a - y0) / scale) ** 2)))

    return {
        "batch": b, "mu_h_typ": float(mu_h_typ), "eps_frac": float(eps_frac),
        "kdeg_added": float(eps_frac * mu_h_typ),
        "rel_A_muh_only": rel(rA["P"]), "rel_B_kdeg_only": rel(rB["P"]),
        "rel_C_both": rel(rC["P"]),
        "rms_A": rms(rA["P"]), "rms_B": rms(rB["P"]), "rms_C": rms(rC["P"]),
        # 抵消比：两者同时做的变化 / 单独任一的变化。≈0 ⇒ 完全等价（不可辨识）
        "cancel_ratio": float(rel(rC["P"]) / max(rel(rA["P"]), rel(rB["P"]), 1e-12)),
        # 有效性：A 臂若因此崩溃，则"降 mu_h"不是干净扰动，抵消比无意义
        "valid_base": base["valid"],
        "valid_A": rA["valid"], "valid_B": rB["valid"], "valid_C": rC["valid"],
        "phmax_base": base["ph_max"], "phmax_A": rA["ph_max"],
        "phmax_B": rB["ph_max"], "phmax_C": rC["ph_max"],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=("svd", "swap"), default="svd")
    ap.add_argument("--batches", type=str, default="22,36,55,59,8,91")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--eps-frac", type=float, default=0.10)
    args = ap.parse_args()

    bs = [int(x) for x in args.batches.split(",") if x.strip()]
    print(f"[r150-ident] stage={args.stage} batches={len(bs)} workers={args.workers}")

    if args.stage == "svd":
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            rows = list(ex.map(jac_one, bs))
        print("\n批  cond     s_max     s_min     v_min(mu_p, mu_h, k_deg)      列范数 mu_p/mu_h/k_deg   有效臂")
        for r in rows:
            v = r["v_min"]
            cn = r["colnorm"]
            va = "".join("Y" if r["valid_arms"][n] else "N" for n in ("mu_p", "mu_h", "k_deg"))
            print(f"{r['batch']:>3d} {r['cond']:8.1f} {r['sv'][0]:9.3e} {r['sv'][-1]:9.3e}  "
                  f"({v[0]:+.3f},{v[1]:+.3f},{v[2]:+.3f})  "
                  f"{cn['mu_p']:.2e}/{cn['mu_h']:.2e}/{cn['k_deg']:.2e}  {va}"
                  f"{'' if r['valid_base'] else ' (base invalid)'}")
        allv = [r for r in rows if r["valid_base"] and all(r["valid_arms"].values())]
        conds = [r["cond"] for r in allv] or [r["cond"] for r in rows]
        print(f"\n  cond 中位 {np.median(conds):.1f}  范围 {min(conds):.1f} – {max(conds):.1f}"
              f"  （仅统计全部臂都有效的批：{len(allv)}/{len(rows)}）")
        bad = [r["batch"] for r in rows if not (r["valid_base"] and all(r["valid_arms"].values()))]
        if bad:
            print(f"  有臂越界的批（其 J 列描述的是崩溃，不是敏感性）：{bad}")
        op = os.path.join(ROOT, "runs", "r150_ident_svd.json")
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            rows = list(ex.map(swap_one, [(b, args.eps_frac) for b in bs]))
        print(f"\n ε = {args.eps_frac:.0%} × mu_h_typ(逐批现算)")
        print("\n批   mu_h_typ     Δk_deg      A:仅mu_h降  B:仅k_deg加  C:两者都做  抵消比  valid A/B/C   pHmax base→A")
        for r in rows:
            va = "".join("Y" if r["valid_" + k] else "N" for k in ("A", "B", "C"))
            print(f"{r['batch']:>3d}  {r['mu_h_typ']:.4e}  {r['kdeg_added']:.4e}  "
                  f"{r['rel_A_muh_only']:.5f}    {r['rel_B_kdeg_only']:.5f}    {r['rel_C_both']:.5f}"
                  f"  {r['cancel_ratio']:6.3f}  {va}      "
                  f"{r['phmax_base']:.3f}→{r['phmax_A']:.3f}")
        clean = [r for r in rows if r["valid_base"] and r["valid_A"] and r["valid_B"] and r["valid_C"]]
        cr = [r["cancel_ratio"] for r in clean] or [r["cancel_ratio"] for r in rows]
        print(f"\n  抵消比 中位 {np.median(cr):.4f}（仅全臂有效的批 {len(clean)}/{len(rows)}）")
        print(f"  A 臂影响 / B 臂影响 中位 = "
              f"{np.median([r['rel_A_muh_only'] / max(r['rel_B_kdeg_only'], 1e-12) for r in clean or rows]):.2f} ×")
        op = os.path.join(ROOT, "runs", "r150_ident_swap.json")

    json.dump({"stage": args.stage, "batches": bs, "rows": rows},
              open(op, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\nwritten: {op}")


if __name__ == "__main__":
    main()
