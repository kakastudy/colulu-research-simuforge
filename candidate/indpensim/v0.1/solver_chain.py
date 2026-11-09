# -*- coding: utf-8 -*-
"""R161 / D-75：B 档方法族回退链的**算子层**实现（M2 §3 冻结链 + §4 实现计划）。

背景（M2 §3 冻结的回退链原文）
--------------------------------
    UKF 收敛 (RMSE < 阈值)
      └→ EnKF (集合协方差)
           └→ MHE + 稳态碳平衡约束
                └→ 稳态基线 / 显式失败

§3.2 冻结的回退判据（三条量化条件）：

    | 环节   | 判据                        | 动作              |
    |--------|-----------------------------|-------------------|
    | UKF    | 协方差 trace > 10×P₀        | 降级到 EnKF       |
    | EnKF   | 集合 spread → 0             | 降级到 MHE        |
    | MHE    | QP 求解失败 / 残差无结构    | 降级到稳态基线    |
    | 稳态基线| C 平衡误差 > 20%           | 显式失败          |

§3.3 冻结的禁止行为（本模块逐条遵守）：
    - 不得静默输出貌似合理的数（I2/I3）⇒ 每级降级**必须**带显式标记与证据
    - 不得在评估批次上调参
    - 不得跳过可辨识性检查直接估计

本轮（R160 回溯发现 D-75）的实测结论
------------------------------------
    - UKF 由 EnKF 结构性替代（R42 登记）⇒ 本模块**不重建 UKF**；
    - EnKF 已实现且为现役主力（observe.py）⇒ 本模块在其上**加装健康度算子**；
    - MHE、稳态基线解算器、三条降级触发器**均不存在** ⇒ 本模块补齐。

**本模块是「基础算子层」**：它提供可单独调用、可证伪、有明确失败语义的算子，
不改动任何现役求解路径（默认不进主链 ⇒ 引擎零回归）。

四环算子一览
------------
    1. enkf_health()      —— EnKF 集合健康度算子（spread/条件数/成员失败率/创新 z）
    2. degradation_guard()—— 降级触发器（三条判据 → 显式 tier 标记）
    3. mhe_step()         —— MHE 约束滚动优化单步（带 QP 失败显式返回）
    4. steady_state_baseline() —— 稳态碳平衡基线解算器（C 平衡误差 > 20% → 显式失败）

设计纪律（继承 D-78 教训，编号延续）
------------------------------------
    **纪律 19**：降级判据必须可被证伪——必须存在一组「本应触发」与「不应触发」的
    构造样本，且判据在「不该触发」样本上不得报警。凡本模块新增判据，
    配套探针 tools/r161_fallback_chain_probe.py 必须做**零信息对照**
    （把输入换成无信息的退化样本，看判据是否仍然"健康"）。
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

# ---------------------------------------------------------------------------
# 冻结阈值（§3.2 原文口径；具体数值在本轮探针中实测标定并记录出处）
# ---------------------------------------------------------------------------

#: 集合相对离散度下界：低于此值视为 spread→0（集合已坍塌，不再携带不确定性信息）
SPREAD_COLLAPSE_CV = 1e-6

#: spread 坍塌的**持续性**要求：低于阈值的最长连续步数须 ≥ 此值。
#: 单点越限不算坍塌——必须"持续"才说明集合真的失去多样性。
SPREAD_COLLAPSE_MIN_STEPS = 3

#: 地板饱和屏蔽：状态均值 |mean| ≤ 此值时，相对离散度无意义
#: （状态被钳在物理地板上，所有成员必然相同 ⇒ CV→0 是守卫的产物，不是集合发散）。
#: 依据：`guards()` 把 ≤0 的状态钳到 1e-3、`phys_clamp` 同。
#: **实测证据（R161）**：b8 的 S 通道 raw_min(CV)=6.59e−16，屏蔽地板步后 masked_min=6.34e−03
#: ⇒ 地板饱和是 S 通道的唯一假阳性来源。
SPREAD_FLOOR_GUARD = 1.5e-3

#: 标准化创新 z 的上界：单通道 |z| 超过此值视为观测与集合系统性不一致
INNOVATION_Z_LIMIT = 5.0

#: **创新判据的通道白名单**（只对这些通道用 |z| 判据）。
#:
#: 依据 R161 实测（b8，n_ens=16，1050 步）：
#:     CO2outgas 越限 0/1050 (zmax=3.1)  | DO2  0/1050 (zmax=4.0)
#:     O2         越限 0/1050 (zmax=0.0)  | pH   0/1050 (zmax=3.5)
#:     **Q        越限 1041/1050 (99.1%, zmax=4720)**
#:     **T        越限 806/1050 (76.8%, zmax=19.8)**
#:     P/PAA/Vis/NH3 化验：越限 2/2（样本极少，且化验值与模型有结构性差）
#:
#: 追查：**Q 与 T 越限不是集合发散，而是模型的系统性偏差**：
#:     - T：模型末态比实测高 **+2.2 ~ +4.1 K**（b8 +4.096 / b11 +3.649 / b22 +2.225）
#!     - Q：模型末态 1095 vs 实测 390（模型发散 **4 倍**），比值自 t=0 的 1.015 掉到 0.289
#!     ⇒ `OBS_R` 给 Q 的 σ=158 kJ/h、T 的 σ=0.05 K 都**远小于模型偏差**
#!     ⇒ 这些通道的 |z| 必然恒真越限，**不能用作集合健康判据**。
#!
#: **纪律（承 D-78）**：判据若在所有批次上恒真越限，即等价于没有判据。
#: 故创新判据**只施加于模型与实测一致（无系统性偏差）的通道**；
#: Q / T 的偏差另立债务跟踪（见 D-82），不在健康度判据里混算。
INNOVATION_Z_CHANNELS = ("CO2outgas", "DO2", "O2", "pH")

#: 成员级积分失败率上界（失败成员数 / 总成员积分次数）
FAIL_RATE_LIMIT = 0.02

#: 协方差条件数上界（Pyy+R 接近奇异 ⇒ 增益不可信）
COND_LIMIT = 1e12

#: 稳态碳平衡基线的 C 平衡误差上限（§3.2 原文 20%）
C_BALANCE_ERROR_LIMIT_PCT = 20.0

#: MHE QP 失败判据：残差相对改善不足则判「残差无结构」（§3.2）
MHE_MIN_REL_IMPROVEMENT = 1e-3

#: 回退链层级标签（显式输出，不静默）
TIER_ENKF = "enkf"
TIER_MHE = "mhe"
TIER_STEADY = "steady_state"
TIER_FAILED = "explicit_failure"


# ---------------------------------------------------------------------------
# 1. EnKF 集合健康度算子
# ---------------------------------------------------------------------------

def enkf_health(health, records=None, integration_failures=None, n_ens=None,
                innovation_criteria=None):
    """由旁路探针数据计算 EnKF 集合健康度。

    **R166 / D-87（opt-in）**：``innovation_criteria=None``（默认）⇒ 判据 3
    完全走 R161 冻结路径，逐位不变；传入逐通道配置时改用「逐通道阈值 +
    持续占比」候选判据。阈值由 ``runs/r166_ab_gate.json`` 的数据驱动扫描给出，
    本模块**不内置任何手写阈值**，且候选判据不进任何默认调用路径。

    参数
    ----
    health : dict
        observe.enkf_observe(health_probe=True) 返回的 ``out["health"]``。
        必需键：``t``（时间）、``cv``（逐通道相对离散度）、``fail_cum``（累计失败数）；
        可选键：``z``（逐通道标准化创新）、``cond``（增益条件数）。
    records : list[dict] | None
        EnKF 输出记录（用于失败率分母推断：步数）。
    integration_failures : int | None
        成员级积分失败总次数。
    n_ens : int | None
        集合成员数。

    返回
    ----
    dict：含 ``healthy``（bool）、``reasons``（触发原因列表）、``metrics``（证据量）。
    **健康判据是「任一失败即不健康」**（保守方向：宁可误报降级，不可静默用坏集合）。
    """
    # R166 / D-87：候选判据走独立函数，默认路径函数体逐字不变（零回归）。
    if innovation_criteria is not None:
        return _enkf_health_r166(health, records, integration_failures,
                                 n_ens, innovation_criteria)
    reasons = []
    metrics = {}

    if not health:
        return {"healthy": False,
                "reasons": ["health_probe 未启用——无健康度证据，不得默认判为健康"],
                "metrics": {}}

    t_arr = np.asarray(health.get("t", []), float)
    cv_list = health.get("cv", []) or []
    n_steps = len(cv_list)
    metrics["n_steps"] = int(n_steps)

    if n_steps == 0:
        return {"healthy": False,
                "reasons": ["集合健康度序列为空"],
                "metrics": metrics}

    # ---- 判据 1：集合 spread → 0（§3.2 EnKF 行）----
    # 逐通道取持续越限的最长连续段；任一通道持续坍塌即判定 spread 坍塌。
    # **两道修正（R161 实测驱动）**：
    #   ① 地板屏蔽：状态均值被钳在物理地板（|mean| ≤ SPREAD_FLOOR_GUARD）时，
    #      所有成员必然相同 ⇒ CV→0 是守卫产物，不是集合发散 ⇒ 该步不计。
    #      证据：b8 的 S 通道 raw_min(CV)=6.59e−16（地板饱和），
    #            屏蔽后 masked_min=6.34e−03（正常量级）。
    #   ② 持续性：单点越限不算坍塌，须连续 ≥ SPREAD_COLLAPSE_MIN_STEPS 步。
    mean_list = health.get("mean", []) or []
    cv_min = {}
    cv_med = {}
    collapse_runs = {}
    for ch in cv_list[0].keys():
        vals = np.asarray([c.get(ch, np.nan) for c in cv_list], float)
        mvals = (np.asarray([m.get(ch, np.nan) for m in mean_list], float)
                 if len(mean_list) == len(vals) else None)
        keep = np.isfinite(vals)
        if mvals is not None:
            keep &= ~(np.abs(mvals) <= SPREAD_FLOOR_GUARD)   # 地板饱和步屏蔽
        vv = vals[keep]
        if vv.size == 0:
            vv = vals[np.isfinite(vals)]
        if vv.size == 0:
            continue
        cv_min[ch] = float(np.min(vv))
        cv_med[ch] = float(np.median(vv))
        # 最长连续越限段（按未屏蔽的原始序列计数，屏蔽步打断连续段）
        run = best = 0
        for i in range(len(vals)):
            if (not np.isfinite(vals[i])) or (mvals is not None
                                             and np.isfinite(mvals[i])
                                             and abs(mvals[i]) <= SPREAD_FLOOR_GUARD):
                run = 0
                continue
            if vals[i] < SPREAD_COLLAPSE_CV:
                run += 1
                best = max(best, run)
            else:
                run = 0
        collapse_runs[ch] = int(best)
    metrics["cv_min"] = cv_min
    metrics["cv_median"] = cv_med
    metrics["cv_collapse_run"] = collapse_runs
    collapsed = [ch for ch, v in collapse_runs.items()
                 if v >= SPREAD_COLLAPSE_MIN_STEPS]
    if collapsed:
        reasons.append(
            "集合 spread→0（spread collapse）：通道 %s 持续 ≥%d 步相对离散度 < %.1e"
            % (",".join(collapsed), SPREAD_COLLAPSE_MIN_STEPS, SPREAD_COLLAPSE_CV))

    # ---- 判据 2：成员级积分失败率（§3.2 精神：数值发散）----
    fail_total = int(integration_failures if integration_failures is not None
                     else (health.get("fail_cum")[-1] if health.get("fail_cum") else 0))
    metrics["integration_failures"] = fail_total
    if n_ens and n_steps:
        denom = float(n_ens) * float(n_steps)
        rate = fail_total / denom if denom > 0 else 0.0
        metrics["fail_rate"] = float(rate)
        if rate > FAIL_RATE_LIMIT:
            reasons.append(
                "成员级积分失败率 %.3f%% > %.3f%%（集合内数值发散）"
                % (100 * rate, 100 * FAIL_RATE_LIMIT))

    # ---- 判据 3：标准化创新越界（观测与集合系统性不一致）----
    # **只对白名单通道判**（见 INNOVATION_Z_CHANNELS 的注释：Q/T 因模型系统性
    # 偏差导致 |z| 在所有批上恒真越限，用它们判定 = 没有判据，承 D-78 纪律）。
    z_list = health.get("z", []) or []
    if z_list:
        z_max = 0.0
        z_max_all = 0.0
        z_over = {}
        z_over_all = {}
        for step in z_list:
            for k, v in step.items():
                if not np.isfinite(v):
                    continue
                av = abs(float(v))
                z_max_all = max(z_max_all, av)
                if k in INNOVATION_Z_CHANNELS:
                    z_max = max(z_max, av)
                    if av > INNOVATION_Z_LIMIT:
                        z_over[k] = z_over.get(k, 0) + 1
                elif av > INNOVATION_Z_LIMIT:
                    z_over_all[k] = z_over_all.get(k, 0) + 1
        metrics["innovation_z_max"] = float(z_max)
        metrics["innovation_z_max_all_channels"] = float(z_max_all)
        metrics["innovation_channels_judged"] = list(INNOVATION_Z_CHANNELS)
        metrics["innovation_over_limit_counts"] = z_over
        metrics["innovation_over_limit_counts_excluded"] = z_over_all
        if z_over:
            worst = max(z_over.items(), key=lambda kv: kv[1])
            reasons.append(
                "标准化创新越界（判据通道 %s）：通道 %s 越限 %d 次（|z|max=%.2f > %.1f）"
                % ("/".join(INNOVATION_Z_CHANNELS), worst[0], worst[1],
                   z_max, INNOVATION_Z_LIMIT))

    # ---- 判据 4：增益条件数（近奇异 ⇒ 增益不可信）----
    cond = np.asarray(health.get("cond", []) or [], float)
    if cond.size:
        cfin = cond[np.isfinite(cond)]
        if cfin.size:
            metrics["cond_max"] = float(np.max(cfin))
            metrics["cond_n_singular"] = int(np.sum(~np.isfinite(cond)))
            if np.max(cfin) > COND_LIMIT:
                reasons.append(
                    "增益协方差近奇异：cond(Pyy+R) max=%.3e > %.1e"
                    % (np.max(cfin), COND_LIMIT))

    # ---- 判据 5：全序列非有限（硬失败）----
    if not np.all(np.isfinite(t_arr)):
        reasons.append("健康度序列含非有限时间戳（数值发散）")

    return {"healthy": len(reasons) == 0,
            "reasons": reasons,
            "metrics": metrics}


def _enkf_health_r166(health, records, integration_failures, n_ens, criteria):
    """R166 / D-87 候选判据（opt-in，独立函数，**绝不进默认路径**）。

    复用冻结 ``enkf_health`` 的判据 1/2/4/5（逐位一致），仅把判据 3 替换为
    「逐通道阈值 + 持续占比」。阈值来自 ``runs/r166_ab_gate.json`` 的数据驱动
    扫描（显式裕度准则 + LOO），本函数**不内置任何手写阈值**。

    设计动因（D-78）：全局 5.0 在真实批上 84.38% 触发（近乎恒真），但直接
    抬到 10.0 会让 `CO2outgas`（跨批 max|z| 最大 7.60）永不触发 ⇒ 恒假；
    `DO2` 15/20 批越 5 属模型系统性偏差（与已排除的 Q/T 同性质），`O2`
    最大 0.167 无判别力 ⇒ 正确解法是逐通道定阈值 + 偏差通道剔除。
    """
    base = enkf_health(health, records, integration_failures, n_ens)
    reasons = [r for r in base["reasons"]
               if not r.startswith("标准化创新越界")]
    metrics = dict(base["metrics"])
    metrics["innovation_r166_applied"] = True
    metrics["innovation_r166_excluded"] = list(criteria.get("excluded", []))
    z_list = health.get("z", []) or []
    chans = dict(criteria.get("channels", {}))

    z_max_all = 0.0
    for step in z_list:
        for k, v in step.items():
            if np.isfinite(v):
                z_max_all = max(z_max_all, abs(float(v)))

    per_ch = {}
    fired = []
    for ch, rule in chans.items():
        z_th = float(rule.get("z_th", INNOVATION_Z_LIMIT))
        min_frac = float(rule.get("min_frac", 0.0))
        n_tot = n_over = 0
        ch_max = 0.0
        for step in z_list:
            if ch not in step:
                continue
            v = float(step[ch])
            if not np.isfinite(v):
                continue
            n_tot += 1
            av = abs(v)
            ch_max = max(ch_max, av)
            if av > z_th:
                n_over += 1
        frac = (n_over / n_tot) if n_tot else 0.0
        hit = bool(n_over > 0 and frac >= min_frac)
        per_ch[ch] = {"n": int(n_tot), "n_over": int(n_over),
                      "frac": float(frac), "z_max": float(ch_max),
                      "z_th": z_th, "min_frac": min_frac, "fired": hit}
        if hit:
            fired.append(ch)

    metrics["innovation_r166_per_channel"] = per_ch
    metrics["innovation_r166_fired"] = fired
    metrics["innovation_channels_judged"] = list(chans)
    metrics["innovation_z_max"] = float(
        max([v["z_max"] for v in per_ch.values()] or [0.0]))
    metrics["innovation_z_max_all_channels"] = float(z_max_all)
    metrics["innovation_over_limit_counts"] = {
        ch: v["n_over"] for ch, v in per_ch.items()}
    if fired:
        reasons.append(
            "R166 候选创新判据触发（逐通道阈值 + 持续占比）：通道 %s"
            % "/".join(fired))
    return {"healthy": len(reasons) == 0,
            "reasons": reasons, "metrics": metrics}


# ---------------------------------------------------------------------------
# 2. 降级触发器
# ---------------------------------------------------------------------------

def degradation_guard(health_result, tier=TIER_ENKF):
    """把健康度判定转成**显式**回退链层级标记。

    §3.3 禁止静默输出貌似合理的数 ⇒ 本函数**永远**返回 tier 与 reasons，
    绝不返回 None / 静默沿用上一环。

    参数
    ----
    health_result : dict
        enkf_health() 的返回值。
    tier : str
        调用方当前所处的层级（用于在 reasons 中标注「从哪一环降级」）。

    返回
    ----
    dict：``{"tier": ..., "degraded": bool, "reasons": [...], "metrics": {...}}``
    """
    reasons = list(health_result.get("reasons", []))
    metrics = dict(health_result.get("metrics", {}))
    healthy = bool(health_result.get("healthy", False))
    return {
        "tier": tier if healthy else TIER_MHE,
        "degraded": not healthy,
        "from_tier": tier,
        "reasons": reasons,
        "metrics": metrics,
        "explicit": True,   # 恒为 True：标记显式，不存在静默路径
    }


# ---------------------------------------------------------------------------
# 3. MHE 约束滚动优化（单步）
# ---------------------------------------------------------------------------

def mhe_step(residual_fn, x0, bounds, tol=1e-6, maxiter=50):
    """MHE 单步：带 box 约束的滚动窗口优化。

    刻意**不内置 QP 求解器**：本项目 §4 Phase 3 要求的 QP 在当前 scipy 依赖面
    （scipy 1.15.3）下最现实的实现是 SLSQP（约束优化器），与其说"QP"不如说
    "受约束最小二乘"。这里把求解器与判据分离：
      - 求解器调用失败 / 不收敛 ⇒ 返回 ``solver_failed=True``（§3.2 MHE 行动作）
      - 求解成功但**相对改善不足** ⇒ 返回 ``no_structure=True``（残差无结构）
    两者都指向 §3.2 的同一个动作：**降级到稳态基线**。

    参数
    ----
    residual_fn : callable
        f(x) -> 1-D array（残差向量）。目标 = 0.5·‖f‖²。
    x0 : array_like
        初值。
    bounds : list[tuple]
        逐变量 (lo, hi)。
    tol, maxiter : float, int
        求解器容差与迭代上限。

    返回
    ----
    dict：``x``（最优解）、``cost``、``n_iter``、``solver_failed``、``no_structure``、
    ``rel_improvement``、``message``。
    """
    from scipy.optimize import minimize

    x0 = np.asarray(x0, float)
    bounds = [(float(lo), float(hi)) for lo, hi in bounds]

    def _f(x):
        r = np.asarray(residual_fn(x), float)
        if r.size == 0:
            return 1e12
        if not np.all(np.isfinite(r)):
            return 1e12
        return 0.5 * float(r @ r)

    try:
        res = minimize(_f, x0, method="SLSQP", bounds=bounds,
                       options={"maxiter": int(maxiter), "ftol": float(tol)})
    except Exception as exc:                      # 求解器本身崩溃 ⇒ 显式失败
        return {"x": x0.copy(), "cost": float("nan"), "n_iter": 0,
                "solver_failed": True, "no_structure": False,
                "rel_improvement": float("nan"),
                "message": "SLSQP 抛出异常：%s: %s" % (type(exc).__name__, exc)}

    c0 = _f(x0)
    c1 = float(res.fun)
    solver_failed = bool(not res.success) or not np.isfinite(c1)
    rel_improvement = float((c0 - c1) / c0) if (np.isfinite(c0) and c0 > 0) else 0.0
    # 残差无结构：优化器自认成功但相对改善微乎其微 ⇒ 目标面无可辨识结构
    no_structure = bool((not solver_failed) and rel_improvement < MHE_MIN_REL_IMPROVEMENT)

    return {"x": np.asarray(res.x, float), "cost": c1, "n_iter": int(res.nit),
            "solver_failed": solver_failed, "no_structure": no_structure,
            "rel_improvement": rel_improvement,
            "message": str(res.message)}


# ---------------------------------------------------------------------------
# 4. 稳态碳平衡基线解算器
# ---------------------------------------------------------------------------

def steady_state_baseline(c_in_g, c_out_components_g, x_hint_g=None):
    """稳态碳平衡基线：给定进料碳与各输出分量碳，反解稳态生物量碳。

    这是 §3 回退链第 3 环的**兜底解算器**：当 EnKF 与 MHE 都不可用时，
    用一条**不依赖集合、不依赖在线积分**的守恒关系给出估计。

    参数
    ----
    c_in_g : float
        进料总碳（gC）。
    c_out_components_g : dict
        各输出分量碳（gC），键如 ``{"CO2": ..., "P": ..., "S_end": ...}``；
        生物量碳项 ``"X"`` 若缺失即为本函数要反解的目标。
    x_hint_g : float | None
        若给出，则以它替代反解值参与闭合校验（用于给出「基线 vs 集合」的对照）。
        注意：**校验误差按 hint 算**（这是"集合估计能否闭合碳账"的检验），
        ``x_carbon_g`` 始终是纯反解值，两者语义不可混用。

    返回
    ----
    dict：``x_carbon_g``（反解的生物量碳 gC）、``x_hint_g``、``c_error_pct``
    （C 平衡误差，§3.2 判据口径，按 hint 或反解值计算）、
    ``c_error_pct_pure``（纯反解口径的误差，即 0，仅作对照）、
    ``credible``（是否可信）、``tier``（可信⇒TIER_STEADY，不信⇒TIER_FAILED）、
    ``reasons``。
    """
    comps = dict(c_out_components_g or {})
    c_in = float(c_in_g)
    known = sum(float(v) for k, v in comps.items() if k != "X")
    x_carbon = c_in - known            # 反解：残下的碳归生物量

    if x_hint_g is not None:
        comps["X"] = float(x_hint_g)
        x_used = float(x_hint_g)
    else:
        comps["X"] = x_carbon
        x_used = x_carbon

    c_out = known + x_used
    c_err = (c_out - c_in) / c_in * 100.0 if c_in > 0 else float("nan")
    # 纯反解口径：按反解值回代 ⇒ 误差恒 0（定义使然）。
    # 保留此字段是为了让读者看到「反解」本身不携带闭合信息，
    # 真正的判据只能用外部提供的独立量（hint / 实测 X）。
    c_err_pure = 0.0 if c_in > 0 else float("nan")

    reasons = []
    credible = True
    if not np.isfinite(c_err):
        credible = False
        reasons.append("C 平衡误差非有限（进料碳为零或非正）")
    elif abs(c_err) > C_BALANCE_ERROR_LIMIT_PCT:
        credible = False
        reasons.append("C 平衡误差 %+.2f%% 越出 ±%.0f%% ⇒ 稳态基线不可信"
                       % (c_err, C_BALANCE_ERROR_LIMIT_PCT))

    return {
        "x_carbon_g": float(x_carbon),
        "x_hint_g": None if x_hint_g is None else float(x_hint_g),
        "c_in_g": c_in,
        "c_out_g": float(c_out),
        "c_error_pct": float(c_err) if np.isfinite(c_err) else float("nan"),
        "c_error_pct_pure": float(c_err_pure),
        "c_error_limit_pct": C_BALANCE_ERROR_LIMIT_PCT,
        "credible": credible,
        "tier": TIER_STEADY if credible else TIER_FAILED,
        "reasons": reasons,
        "explicit": True,
    }


# ---------------------------------------------------------------------------
# 5. 链编排：把四环串起来，显式输出最终层级
# ---------------------------------------------------------------------------

def resolve_tier(health_result, mhe_result=None, steady_result=None):
    """按 §3 链序解析最终层级。

    链序：EnKF 健康 → （不健康）MHE → （QP 失败/残差无结构）稳态基线 → 显式失败。

    返回 dict：``tier``、``trace``（逐环判定链）、``reasons``。
    """
    trace = []
    reasons = []

    h_ok = bool(health_result.get("healthy", False))
    trace.append({"ring": TIER_ENKF, "passed": h_ok,
                  "reasons": list(health_result.get("reasons", []))})
    if h_ok:
        return {"tier": TIER_ENKF, "trace": trace, "reasons": [],
                "explicit": True}

    reasons.extend(health_result.get("reasons", []))

    # ---- 环 2：MHE ----
    if mhe_result is None:
        mhe_result = {"solver_failed": True, "no_structure": True,
                      "message": "MHE 未执行（缺调用）"}
    mhe_ok = (not mhe_result.get("solver_failed", True)) and \
             (not mhe_result.get("no_structure", True))
    mreasons = []
    if mhe_result.get("solver_failed"):
        mreasons.append("MHE 求解器失败：%s" % mhe_result.get("message", ""))
    if mhe_result.get("no_structure"):
        # ⚠ 两条**不同**的触发路径必须给不同措辞（R163 修正）：
        #   ① 边界退化（D-86）：解撞参数域边界 ⇒ 不可辨识；此时相对改善**充足**
        #      （例：0.615 ≫ 1e-3）⇒ 若仍写「相对改善 < 阈值」就是**自相矛盾的假陈述**。
        #   ② 相对改善不足（R161 冻结判据）：相对改善 < MHE_MIN_REL_IMPROVEMENT。
        # 措辞错误会让读者以为判据「不成立」，属 §3.3 同类的「静默输出貌似合理的数」。
        if mhe_result.get("boundary_degenerate"):
            bd = mhe_result.get("boundary_detail") or {}
            mreasons.append(
                "MHE 边界退化：最优解落在参数域边界（%s），该方向不可辨识"
                "（相对改善 %.3e 充足，但解不携带参数信息）"
                % (bd.get("closest", {}).get("name"), mhe_result.get("rel_improvement", float("nan"))))
        else:
            mreasons.append("MHE 残差无结构（相对改善 %.3e < %.1e）"
                            % (mhe_result.get("rel_improvement", float("nan")),
                               MHE_MIN_REL_IMPROVEMENT))
    trace.append({"ring": TIER_MHE, "passed": mhe_ok, "reasons": mreasons})
    if mhe_ok:
        return {"tier": TIER_MHE, "trace": trace, "reasons": reasons,
                "explicit": True}

    reasons.extend(mreasons)

    # ---- 环 3：稳态基线 ----
    if steady_result is None:
        steady_result = {"credible": False,
                         "reasons": ["稳态基线未执行（缺调用）"]}
    s_ok = bool(steady_result.get("credible", False))
    sreasons = list(steady_result.get("reasons", []))
    trace.append({"ring": TIER_STEADY, "passed": s_ok, "reasons": sreasons})
    if s_ok:
        return {"tier": TIER_STEADY, "trace": trace, "reasons": reasons,
                "explicit": True}

    reasons.extend(sreasons)

    # ---- 环 4：显式失败 ----
    trace.append({"ring": TIER_FAILED, "passed": False,
                  "reasons": ["回退链穷尽 ⇒ 显式失败（不输出貌似合理的数）"]})
    return {"tier": TIER_FAILED, "trace": trace, "reasons": reasons,
            "explicit": True}


# ---------------------------------------------------------------------------
# 6. 便捷封装：从 observe.enkf_observe 的输出直接判链
# ---------------------------------------------------------------------------

def classify_enkf_output(enkf_out, mhe_result=None, steady_result=None):
    """从 ``enkf_observe`` 的输出 dict 直接给出回退链层级。

    ``enkf_out`` 需含 ``records``、``integration_failures``；
    若含 ``health``（health_probe=True）则用它做判据，否则**判为不健康**
    （无证据不得默认健康——§3.3 禁止静默）。
    """
    health = enkf_out.get("health")
    hr = enkf_health(health, records=enkf_out.get("records"),
                      integration_failures=enkf_out.get("integration_failures"),
                      n_ens=enkf_out.get("n_ens"))
    return resolve_tier(hr, mhe_result=mhe_result, steady_result=steady_result)


def dump_chain_result(result, out_path):
    """把链判定结果落盘（JSON）。"""
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    return out_path


# ===========================================================================
# 7. 批次级链编排（R163 / D-80）：把四环接到**真实批**上
# ===========================================================================
#
# 背景（D-80）
# ------------
# R161 交付了四环算子，但**未接入现役 MCP 路径** —— `reconstruct_batch` 等仍走原
# EnKF/集合平滑，集合发散时**不会自动降级**，也不会给出显式层级标记。
# 本节补上「批次级编排」：
#
#     EnKF 健康探针 ──(健康)──→ tier=enkf（照常返回，不降级）
#          │
#       (不健康)
#          ↓
#     MHE（真实残差，移动窗）──(可解)──→ tier=mhe
#          │
#       (QP 失败 / 残差无结构)
#          ↓
#     稳态碳平衡基线 ──(闭合)──→ tier=steady_state
#          │
#       (C 平衡误差 > 20%)
#          ↓
#     tier=explicit_failure（**显式失败**，不输出貌似合理的数）
#
# 纪律（承 D-78 / R161 纪律 19）
# -----------------------------
#   - 每一环都必须产出**可证伪的判据**，且在真实批上能触发；
#   - 无证据不得默认健康（无探针数据 ⇒ 直接判不健康）；
#   - 降级标记**必须**出现在返回体（见 `evaluate_batch_fallback` 的返回结构）。
#
# **本节不改动任何现役求解路径**：所有函数都是**旁路调用**，
# 由调用方（MCP 工具）显式 opt-in 才执行 ⇒ 默认路径逐位不变。

#: MHE 的参数化：只解两个批次级参数（其余固定为该批校准值）。
#: 选这两个的理由：μp 直接决定产素速率、m_s 决定维持消耗，
#: 二者对「窗内 P / PAA / DO2 / pH 残差」最敏感，且都有工程先验域。
MHE_THETA_NAMES = ("mup", "m_s")

#: MHE 参数先验域（与 `observe.phys_clamp` 的钳位域一致 ⇒ 不会出现域外解）
MHE_THETA_BOUNDS = {"mup": (0.010, 0.080), "m_s": (0.005, 0.045)}

#: MHE 移动窗长度（h）。4 h = 20 个 0.2 h 采样段。
MHE_WINDOW_H = 4.0

#: MHE 残差权重（相对量纲；残差本身都已归一化）
MHE_WEIGHTS = {"P": 1.0, "PAA": 0.02, "DO2": 0.5, "pH": 8.0,
                "C_balance": 0.2}

#: 化验滞后（h）—— 与 `observe.ASSAY_OFFSET` 同源（indpensim_run.m Off_line_delay）
_ASSAY_OFFSET = 4.0


def _last_assay_before(d, col, t_lab):
    """取 ``t_lab`` 之前最近一次有效化验值（按 4 h 滞后对齐后给出状态时刻）。

    返回 ``np.nan`` 表示该时刻之前没有有效化验。
    """
    import pandas as pd
    t = d["time_h"].to_numpy(float)
    ser = pd.to_numeric(d[col], errors="coerce").to_numpy(float)
    cand = [(float(t[i]) - _ASSAY_OFFSET, float(v))
            for i, v in enumerate(ser)
            if np.isfinite(v) and (t[i] - _ASSAY_OFFSET) <= float(t_lab) + 0.11]
    return cand[-1][1] if cand else float("nan")


def _window_start_state(d, t_start):
    """用 V3 **实测**构造窗口起点状态（33 维）。

    MHE 是「移动窗估计」：窗起点状态必须来自实测（否则要额外跑一次长积分）。
    这里用窗口起点行的在线量 + 窗起点**之前最近一次化验**（按 4 h 滞后对齐）。
    """
    import pandas as pd
    from simulate import IDX, N_STATES

    t = d["time_h"].to_numpy(float)
    i0 = int(np.argmin(np.abs(t - float(t_start))))
    row = d.iloc[i0]
    s = np.zeros(N_STATES)
    s[IDX["S"]] = float(row["S"])
    s[IDX["DO2"]] = float(row["DO2"])
    s[IDX["O2"]] = float(row["O2"])
    s[IDX["P"]] = float(row["P"])
    s[IDX["V"]] = float(row["V"])
    s[IDX["Wt"]] = float(row["Wt"])
    s[IDX["pH_H"]] = 10 ** (-float(row["pH"]))
    s[IDX["T"]] = float(row["T"])
    s[IDX["Q"]] = 0.001
    s[IDX["vis"]] = 4.0
    s[IDX["A_t1"]] = 0.0
    s[IDX["CO2"]] = float(row["CO2outgas"]) if "CO2outgas" in d.columns else 0.0
    s[IDX["CO2d"]] = 0.0

    def _last_before(col, t_lab):
        return _last_assay_before(d, col, t_lab)

    x = _last_before("X_offline", t[i0])
    if not np.isfinite(x):
        x = 0.5
    s[IDX["A0"]] = x / 3.0
    s[IDX["A1"]] = x * 2.0 / 3.0
    s[IDX["A3"]] = 0.0
    s[IDX["A4"]] = 0.0

    paa = _last_before("PAA_offline", t[i0])
    s[IDX["PAA"]] = float(paa) if np.isfinite(paa) else 1400.0
    nh3 = _last_before("NH3_offline", t[i0])
    s[IDX["NH3"]] = float(nh3) if np.isfinite(nh3) else 1700.0
    s[IDX["mup"]] = 0.0
    s[IDX["mux"]] = 0.0
    return s, float(t[i0])


def mhe_batch_residual(batch_no, t_start, t_end, params=None, window_h=MHE_WINDOW_H):
    """构造**真实批**的 MHE 残差函数 r(θ)（移动窗内 模型 vs 实测）。

    参数
    ----
    batch_no : int
        批号。
    t_start, t_end : float
        移动窗起止时刻（h）。
    params : dict | None
        该批校准参数（提供除 μp / m_s 外的固定参数，如 alpha_kla）。
    window_h : float
        窗长（h）；用于「窗末端化验对齐」与「窗内在线量均值」的划分。

    返回
    ----
    ``(residual_fn, meta)``。``residual_fn(x)`` 接受 ``x = [mup, m_s]``，
    返回 1-D 残差向量；``meta`` 记录口径与诊断量。

    残差构成（全部归一化，无量纲）：
      - ``P``    窗末端模型 P 与实测化验 P 的相对偏差（化验按 4 h 滞后对齐）
      - ``PAA``  同上
      - ``DO2``  窗内模型 DO2 均值与实测均值的差（除以实测量级）
      - ``pH``   窗内模型 pH 均值与实测均值的差（pH 已是对数量纲）
    """
    import pandas as pd
    from simulate import (load_batch, build_inp1, guards, integrate_interval,
                          make_params, IDX)

    d = load_batch(int(batch_no))
    t = d["time_h"].to_numpy(float)
    i0 = int(np.argmin(np.abs(t - float(t_start))))
    i1 = int(np.argmin(np.abs(t - float(t_end))))
    if i1 <= i0:
        i1 = min(i0 + 1, len(d) - 1)
    y0, t0 = _window_start_state(d, t[i0])
    win = d.iloc[i0:i1 + 1]

    base = dict(params or {})
    alpha_kla = float(base.get("alpha_kla", 85.0))
    mup0 = float(base.get("mup", 0.041))
    mux0 = float(base.get("mux", 0.41))
    dist_tcin_asym = float(base.get("dist_tcin_asym", 10))

    def _sim(x):
        par = make_params(alpha_kla=alpha_kla,
                          N_conc_paa=float(base.get("N_conc_paa", 150000.0)),
                          PAA_c=float(base.get("PAA_c", 530000.0)),
                          mup=float(x[0]), mux=mux0,
                          c_oil=float(base.get("c_oil", 1000.0)))
        par[24] = float(x[1])          # rhs 契约：par[0]=μp, par[24]=m_s
        y = y0.copy()
        tc = t0
        do2_model, ph_model, cer_model = [], [], []
        for _, row in win.iterrows():
            inp1 = build_inp1(row, inhib=2, dist_flag=1,
                              dist_tcin=dist_tcin_asym * min(1, tc / 40.0) or 10)
            y = guards(integrate_interval(tc, y, inp1, par))
            tc = float(row["time_h"])
            do2_model.append(float(y[IDX["DO2"]]))
            ph_model.append(float(-np.log10(max(y[IDX["pH_H"]], 1e-15))))
            cer_model.append(float(y[IDX["CER"]]) if IDX.get("CER") is not None
                             else float("nan"))
        return y, np.asarray(do2_model, float), np.asarray(ph_model, float), \
            np.asarray(cer_model, float)

    # 实测窗内量
    do2_obs = pd.to_numeric(win["DO2"], errors="coerce").to_numpy(float)
    ph_obs = pd.to_numeric(win["pH"], errors="coerce").to_numpy(float)
    cer_obs = pd.to_numeric(win["CER"], errors="coerce").to_numpy(float) \
        if "CER" in win.columns else None
    p_lab_t = float(t[i1]) - _ASSAY_OFFSET
    p_obs = _last_assay_before(d, "P_offline", p_lab_t)
    paa_obs = _last_assay_before(d, "PAA_offline", p_lab_t)

    def residual_fn(x):
        x = np.asarray(x, float)
        y, do2_m, ph_m, cer_m = _sim(x)
        r = []
        if np.isfinite(p_obs):
            denom = max(abs(float(p_obs)), 1e-6)
            r.append(MHE_WEIGHTS["P"] * (float(y[IDX["P"]]) - float(p_obs)) / denom)
        if np.isfinite(paa_obs):
            denom = max(abs(float(paa_obs)), 1e-6)
            r.append(MHE_WEIGHTS["PAA"] * (float(y[IDX["PAA"]]) - float(paa_obs)) / denom)
        ok = np.isfinite(do2_obs)
        if ok.any():
            scale = max(abs(float(np.mean(do2_obs[ok]))), 1e-3)
            r.append(MHE_WEIGHTS["DO2"] * (float(np.mean(do2_m[ok])) -
                                           float(np.mean(do2_obs[ok]))) / scale)
        okp = np.isfinite(ph_obs)
        if okp.any():
            r.append(MHE_WEIGHTS["pH"] * (float(np.mean(ph_m[okp])) -
                                          float(np.mean(ph_obs[okp]))))
        # ---- 稳态碳平衡软约束（§3.2 原文「MHE + 稳态碳平衡约束」）----
        # 窗口内模型 CER 积分碳 vs 实测 CER 积分碳的相对偏差。
        # 权重小：碳平衡是**软**约束（硬判据在稳态基线环，见 C_BALANCE_ERROR_LIMIT_PCT）。
        if cer_obs is not None and np.isfinite(cer_m).any():
            okc = np.isfinite(cer_obs)
            if okc.sum() >= 2:
                dt = np.diff(win["time_h"].to_numpy(float))
                m_c = float(np.sum(np.clip(cer_m[okc], 0, None) * dt[:len(cer_m) - 1]))
                o_c = float(np.sum(np.clip(cer_obs[okc], 0, None) * dt[:len(cer_obs) - 1]))
                denom = max(abs(o_c), 1e-6)
                r.append(MHE_WEIGHTS["C_balance"] * (m_c - o_c) / denom)
        return np.asarray(r, float) if r else np.asarray([0.0])

    meta = {
        "batch": int(batch_no), "t_start": float(t[i0]), "t_end": float(t[i1]),
        "n_window_steps": int(i1 - i0 + 1),
        "theta_names": list(MHE_THETA_NAMES),
        "theta0": [mup0, float(base.get("m_s", 0.029))],
        "bounds": [list(MHE_THETA_BOUNDS[n]) for n in MHE_THETA_NAMES],
        "has_P_obs": bool(np.isfinite(p_obs)),
        "has_PAA_obs": bool(np.isfinite(paa_obs)),
        "n_residual": 0,
    }
    return residual_fn, meta


def mhe_estimate_batch(batch_no, t_start=None, t_end=None, params=None,
                       window_h=MHE_WINDOW_H, tol=1e-6, maxiter=50):
    """MHE 单步（真实残差）：移动窗内反演 (μp, m_s)。

    默认取窗口 = 批末前 ``window_h``（末端有化验对齐 ⇒ 残差最丰富）。
    返回 `mhe_step` 的结果 + ``meta``。
    """
    import pandas as pd
    from simulate import load_batch

    d = load_batch(int(batch_no))
    tmax = float(d["time_h"].iloc[-1])
    if t_end is None:
        t_end = tmax - 0.5
    if t_start is None:
        t_start = max(float(t_end) - float(window_h), float(d["time_h"].iloc[0]))

    residual_fn, meta = mhe_batch_residual(batch_no, t_start, t_end,
                                           params=params, window_h=window_h)
    x0 = np.asarray(meta["theta0"], float)
    bounds = [tuple(b) for b in meta["bounds"]]
    res = mhe_step(residual_fn, x0, bounds, tol=tol, maxiter=maxiter)
    res["meta"] = meta
    res["theta_names"] = list(MHE_THETA_NAMES)
    try:
        res["x_named"] = {n: float(v) for n, v in zip(MHE_THETA_NAMES, res["x"])}
    except Exception:
        res["x_named"] = None
    return res


def mhe_boundary_degenerate(result, bounds=None, tol=1e-6):
    """MHE 解的**边界退化**判据：解落在参数域边界 ⇒ 该方向不可辨识。

    为什么需要（承 D-78 判别力纪律）
    --------------------------------
    R161 冻结的 MHE 判据是「QP 求解失败 / **相对改善不足** ⇒ 残差无结构」。
    但 R163 在**真实批**上实测到：某些窗口的最优解被推到参数域边界
    （例：b8 末端窗 μp 解 = 0.010 = 域下界），而**相对改善仍有 0.397**，
    ⇒ 旧判据会把一个「其实不可辨识」的解判成「可解」。

    边界退化是「残差无结构」的另一面：目标面在越界方向上没有有效梯度信息，
    优化器只是在域边界上「停住」，此时解**不携带**参数信息。

    本函数**只做判定，不改 `mhe_step` 的冻结语义**（R161 的 T5 判据不受影响）；
    由链编排层（`evaluate_batch_fallback`）决定是否据此降级。

    返回 ``(degenerate: bool, detail: dict)``。
    """
    x = np.asarray(result.get("x", []), float)
    if x.size == 0:
        return False, {"reason": "无解"}
    bnds = bounds
    if bnds is None:
        bnds = (result.get("meta") or {}).get("bounds")
    if not bnds:
        return False, {"reason": "无边界信息"}
    detail = {"theta_names": (result.get("meta") or {}).get("theta_names"),
              "bounds": bnds, "x": [float(v) for v in x], "at": {}}
    worst = None
    for i, (lo, hi) in enumerate(bnds):
        lo, hi = float(lo), float(hi)
        span = max(hi - lo, 1e-12)
        d_lo = (float(x[i]) - lo) / span
        d_hi = (hi - float(x[i])) / span
        near = min(d_lo, d_hi)
        name = (detail["theta_names"] or [])[i] if detail["theta_names"] else "x%d" % i
        detail["at"][name] = {"lo": lo, "hi": hi, "dist_to_lo_frac": d_lo,
                              "dist_to_hi_frac": d_hi}
        if worst is None or near < worst[1]:
            worst = (name, near)
    detail["closest"] = {"name": worst[0], "dist_frac": worst[1]}
    return bool(worst[1] <= float(tol)), detail


def mhe_rolling(batch_no, t_start=None, t_end=None, step_h=8.0,
                window_h=MHE_WINDOW_H, params=None, warm_start=True,
                maxiter=50, on_failure="stop", boundary_tol=1e-6):
    """MHE **滚动时序调度**（receding horizon）—— R163-5 的主体。

    与 `mhe_estimate_batch`（单窗口单次优化）的区别：
      - 窗口沿时间轴**滚动前进**（步长 `step_h`），每个窗口**重新优化**；
      - **warm start**：本次优化的初值取上一次窗口的解 ⇒ 迭代数更少、更稳定；
      - 输出**参数时序轨迹**（μp(t)、m_s(t)），而不是单点估计；
      - 任一窗口不可解 ⇒ **显式标记**并按 `on_failure` 处理（不静默跳过）。

    返回
    ----
    dict：``windows``（逐窗记录）、``n_windows`` / ``n_ok`` / ``n_failed``、
    ``theta_series``（``t`` / ``mup`` / ``m_s``）、``final``、``stopped_early``。
    """
    from simulate import load_batch

    d = load_batch(int(batch_no))
    t_all = d["time_h"].to_numpy(float)
    t_max = float(t_all[-1])
    if t_end is None:
        t_end = t_max - 0.5
    if t_start is None:
        t_start = max(float(t_all[0]) + float(window_h), 40.0)
    step_h = float(step_h)
    window_h = float(window_h)

    windows = []
    theta_t, theta_mup, theta_ms = [], [], []
    x_prev = None
    stopped_early = False
    stop_reason = None
    tk = float(t_start)
    while tk + window_h <= float(t_end) + 1e-9:
        w_end = min(tk + window_h, float(t_end))
        try:
            residual_fn, meta = mhe_batch_residual(batch_no, tk, w_end,
                                                   params=params, window_h=window_h)
            x0 = np.asarray(meta["theta0"], float)
            if warm_start and x_prev is not None and x_prev.size == x0.size:
                # warm start：夹回域内（上一解可能落在边界外一点点）
                bnds = [tuple(b) for b in meta["bounds"]]
                x0 = np.array([min(max(x_prev[i], bnds[i][0]), bnds[i][1])
                               for i in range(x0.size)], float)
            res = mhe_step(residual_fn, x0, [tuple(b) for b in meta["bounds"]],
                           tol=1e-6, maxiter=int(maxiter))
            res["meta"] = meta
            res["t_window"] = [float(tk), float(w_end)]
            deg, bdetail = mhe_boundary_degenerate(res, bounds=meta["bounds"],
                                                    tol=boundary_tol)
            res["boundary_degenerate"] = bool(deg)
            res["boundary_detail"] = bdetail
            res["no_structure"] = bool(res["no_structure"] or deg)
            res["theta_names"] = list(MHE_THETA_NAMES)
            try:
                res["x_named"] = {n: float(v) for n, v in zip(MHE_THETA_NAMES, res["x"])}
            except Exception:
                res["x_named"] = None
            ok = (not res["solver_failed"]) and (not res["no_structure"])
            windows.append({
                "t_start": float(tk), "t_end": float(w_end),
                "x": [float(v) for v in res["x"]],
                "x_named": res["x_named"],
                "cost": float(res["cost"]) if np.isfinite(res["cost"]) else float("nan"),
                "rel_improvement": float(res["rel_improvement"]),
                "solver_failed": bool(res["solver_failed"]),
                "no_structure": bool(res["no_structure"]),
                "boundary_degenerate": bool(deg),
                "n_iter": int(res["n_iter"]),
                "ok": bool(ok),
            })
            if ok:
                x_prev = np.asarray(res["x"], float)
                theta_t.append(float(w_end))
                theta_mup.append(float(res["x"][0]))
                theta_ms.append(float(res["x"][1]))
            else:
                stop_reason = ("solver_failed" if res["solver_failed"]
                               else ("boundary_degenerate" if deg else "no_structure"))
                if on_failure == "stop":
                    stopped_early = True
                    break
        except Exception as exc:
            windows.append({"t_start": float(tk), "t_end": float(w_end),
                            "ok": False, "error": "%s: %s" % (type(exc).__name__, exc),
                            "solver_failed": True, "no_structure": False,
                            "boundary_degenerate": False})
            stop_reason = "exception"
            if on_failure == "stop":
                stopped_early = True
                break
        tk += step_h

    n_ok = sum(1 for w in windows if w.get("ok"))
    return {
        "batch": int(batch_no),
        "t_start": float(t_start), "t_end": float(t_end),
        "step_h": step_h, "window_h": window_h,
        "warm_start": bool(warm_start),
        "on_failure": on_failure,
        "windows": windows,
        "n_windows": len(windows),
        "n_ok": n_ok,
        "n_failed": len(windows) - n_ok,
        "stopped_early": bool(stopped_early),
        "stop_reason": stop_reason,
        "theta_series": {"t": theta_t, "mup": theta_mup, "m_s": theta_ms},
        "final": (windows[-1] if windows else None),
        "explicit": True,
    }


def steady_state_for_batch(batch_no):
    """稳态碳平衡基线（真实批口径）：C_in 来自元素平衡，x_hint 来自实测 X 净增量。

    与 R161 探针 `run_steady_state_census` 的口径**逐字一致**（避免两处口径分叉）。
    """
    import pandas as pd
    from simulate import load_batch
    from conservation_metrics import (CF_GLC, CF_P, CF_X, _trapz, element_balance)

    v3 = load_batch(int(batch_no))
    eb = element_balance(v3)
    t = v3["time_h"].to_numpy(float)
    CER_g = _trapz(t, np.clip(v3["CER"].to_numpy(float), 0, None) *
                   v3["V"].to_numpy(float))
    C_co2 = CER_g * 12.0 / 44.0
    Frm = v3["Fremoved"].to_numpy(float)
    Ph = _trapz(t, -np.clip(Frm, None, 0) * v3["P"].to_numpy(float))
    Pe = float(v3["V"].iloc[-1] * v3["P"].iloc[-1])
    C_prod = (Ph + Pe) * CF_P
    C_sub = float(v3["S"].iloc[-1] * v3["V"].iloc[-1]) * CF_GLC

    xo = pd.to_numeric(v3["X_offline"], errors="coerce")
    x_t, x_v = [], []
    for i, val in xo.items():
        if np.isfinite(val):
            x_t.append(t[i] - _ASSAY_OFFSET)
            x_v.append(float(val))
    order = np.argsort(x_t)
    Xf = (lambda tt: float(np.interp(tt, np.array(x_t)[order], np.array(x_v)[order]))
          if len(x_t) >= 2 else 0.0)
    X_rem = _trapz(t, -np.clip(Frm, None, 0) * np.array([Xf(tt) for tt in t]))
    X0 = Xf(t[0]) * float(v3["V"].iloc[0])
    X_end = float(xo.dropna().iloc[-1]) * float(v3["V"].iloc[-1])
    X_net = max(X_end + X_rem - X0, 0.0)
    C_X_meas = X_net * CF_X

    res = steady_state_baseline(c_in_g=eb["C_in_g"],
                                 c_out_components_g={"CO2": C_co2, "P": C_prod,
                                                      "S_end": C_sub},
                                 x_hint_g=C_X_meas)
    res["batch"] = int(batch_no)
    res["x_meas_g"] = C_X_meas
    res["x_rel_diff_pct"] = (100.0 * (res["x_carbon_g"] - C_X_meas) / C_X_meas
                              if C_X_meas > 0 else float("nan"))
    return res


def evaluate_batch_fallback(batch_no, n_ens=20, seed=7, params=None,
                            run_mhe=True, run_steady=True,
                            mhe_t_start=None, mhe_t_end=None, mhe_maxiter=50,
                            health=None, enkf_out=None):
    """**批次级回退链编排**（R163 / D-80 的落点）。

    流程见本节顶部注释。返回结构（**降级标记必现在返回体**）：

    ``{"tier": str, "degraded": bool, "from_tier": str, "reasons": [str],
       "trace": [dict], "explicit": True, "evidence": {...},
       "fallback": {...} | None}``

    参数
    ----
    health : dict | None
        外部已算好的 EnKF 健康度旁路数据（``enkf_observe`` 的 ``out["health"]``）。
        传 ``None`` ⇒ 本函数**自行跑一次** EnKF 探针（较慢，n_ens 控制）。
    enkf_out : dict | None
        外部已算好的 EnKF 输出（提供 records / integration_failures / n_ens）。
    """
    from calibration import calib_params

    batch_no = int(batch_no)
    if params is None:
        try:
            params = calib_params(batch_no)
        except KeyError:
            params = {"alpha_kla": 85.0}

    # ---- 环 1：EnKF 健康度 ----
    if enkf_out is None:
        from observe import enkf_observe
        enkf_out = enkf_observe(batch_no, params=params, n_ens=int(n_ens),
                                seed=int(seed), verbose=False, health_probe=True)
    hr = enkf_health(enkf_out.get("health"), records=enkf_out.get("records"),
                     integration_failures=enkf_out.get("integration_failures"),
                     n_ens=enkf_out.get("n_ens"))
    dg = degradation_guard(hr)

    mhe_result = None
    steady_result = None
    if dg["degraded"]:
        # ---- 环 2：MHE（真实残差）----
        if run_mhe:
            try:
                mhe_result = mhe_estimate_batch(batch_no, t_start=mhe_t_start,
                                                 t_end=mhe_t_end, params=params,
                                                 maxiter=int(mhe_maxiter))
                # **边界退化 ⇒ 不可辨识 ⇒ 按「残差无结构」降级**（R163 新增判据）。
                # 依据：真实批上出现「解被推到参数域边界、但相对改善仍 > 阈值」的情形
                # （b8 末端窗 μp 解 = 0.010 = 域下界，相对改善 0.397）
                # ⇒ R161 冻结的「相对改善不足」判据在此**不具判别力**，必须补一条。
                # 本判定**不改** `mhe_step` 的冻结语义，只在链编排层生效。
                if mhe_result is not None and not mhe_result.get("solver_failed"):
                    deg, bdetail = mhe_boundary_degenerate(mhe_result)
                    mhe_result["boundary_degenerate"] = bool(deg)
                    mhe_result["boundary_detail"] = bdetail
                    if deg:
                        mhe_result["no_structure"] = True
                        mhe_result["message"] = (
                            (mhe_result.get("message") or "") +
                            " ｜边界退化：解落在参数域边界（%s），该方向不可辨识"
                            % bdetail.get("closest", {}).get("name"))
            except Exception as exc:
                mhe_result = {"solver_failed": True, "no_structure": False,
                              "message": "MHE 编排异常：%s: %s" % (type(exc).__name__, exc),
                              "rel_improvement": float("nan")}
        # ---- 环 3：稳态基线 ----
        if run_steady:
            try:
                steady_result = steady_state_for_batch(batch_no)
            except Exception as exc:
                steady_result = {"credible": False,
                                 "reasons": ["稳态基线异常：%s: %s"
                                             % (type(exc).__name__, exc)]}

    chain = resolve_tier(hr, mhe_result=mhe_result, steady_result=steady_result)

    fallback = None
    if chain["tier"] == TIER_MHE and mhe_result is not None:
        fallback = {"kind": "mhe", "theta_names": mhe_result.get("theta_names"),
                    "x_named": mhe_result.get("x_named"),
                    "cost": mhe_result.get("cost"),
                    "rel_improvement": mhe_result.get("rel_improvement"),
                    "message": mhe_result.get("message")}
    elif chain["tier"] == TIER_STEADY and steady_result is not None:
        fallback = {"kind": "steady_state",
                    "x_carbon_g": steady_result.get("x_carbon_g"),
                    "x_meas_g": steady_result.get("x_meas_g"),
                    "c_error_pct": steady_result.get("c_error_pct")}

    return {
        "tier": chain["tier"],
        "degraded": bool(chain["tier"] != TIER_ENKF),
        "from_tier": TIER_ENKF,
        "reasons": chain["reasons"],
        "trace": chain["trace"],
        "explicit": True,
        "evidence": {
            "health": {"healthy": bool(hr["healthy"]),
                       "reasons": hr["reasons"],
                       "metrics": hr["metrics"]},
            "mhe": None if mhe_result is None else {
                "solver_failed": mhe_result.get("solver_failed"),
                "no_structure": mhe_result.get("no_structure"),
                "rel_improvement": mhe_result.get("rel_improvement"),
                "message": mhe_result.get("message"),
                "x_named": mhe_result.get("x_named"),
                "meta": mhe_result.get("meta")},
            "steady_state": None if steady_result is None else {
                "credible": steady_result.get("credible"),
                "c_error_pct": steady_result.get("c_error_pct"),
                "x_carbon_g": steady_result.get("x_carbon_g"),
                "x_meas_g": steady_result.get("x_meas_g"),
                "reasons": steady_result.get("reasons")},
        },
        "fallback": fallback,
    }


if __name__ == "__main__":
    # 自检：四条判据各自的最小可复现样本
    demo_health_ok = enkf_health({"t": [0.0, 1.0],
                                  "cv": [{"X": 1e-2, "P": 1e-2}],
                                  "fail_cum": [0, 0],
                                  "z": [{"DO2": 0.1}],
                                  "cond": [1e3]})
    demo_health_bad = enkf_health({"t": [0.0, 1.0],
                                   "cv": [{"X": 1e-9, "P": 1e-2}],
                                   "fail_cum": [0, 5],
                                   "z": [{"DO2": 9.0}],
                                   "cond": [1e15]},
                                  integration_failures=5, n_ens=2)
    print(json.dumps({
        "healthy_sample": demo_health_ok,
        "collapsed_sample": demo_health_bad,
        "chain_on_healthy": resolve_tier(demo_health_ok),
        "chain_on_collapsed": resolve_tier(demo_health_bad),
        "steady_ok": steady_state_baseline(1000.0, {"CO2": 400.0, "P": 300.0}),
        "steady_bad": steady_state_baseline(1000.0, {"CO2": 100.0, "P": 100.0},
                                            x_hint_g=2000.0),
    }, ensure_ascii=False, indent=2, default=str))
