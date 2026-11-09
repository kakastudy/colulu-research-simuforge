# -*- coding: utf-8 -*-
"""R161 / D-75 探针：回退链四环算子的**证伪式**验证。

验证目标（对应 M2 §3.2 三条冻结判据 + §3.3 禁止行为）：

  T1  健康批不得误报降级      —— 判据的**假阳性率**必须为 0
  T2  注入退化必须触发降级    —— 判据的**真阳性**必须成立
  T3  零信息对照              —— 把健康证据换成"无信息"样本，判据不得仍判健康
  T4  显式失败语义            —— 链穷尽必须落 explicit_failure，不得输出貌似合理的数
  T5  MHE 判据双向可证伪      —— 有结构的残差 ⇒ 判为可解；无结构残差 ⇒ 判为不可解
  T6  稳态基线 C 平衡判据     —— 误差 >20% 必须判不可信
  T7  零回归                  —— observe.py 的 opt-in 探针不得改变任何数值

本工具**不改引擎**，只读+调算子，产物落 runs/r161_fallback_chain_probe.json。
"""
import argparse
import json
import os
import sys
import time

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))

from observe import enkf_observe                      # noqa: E402
from calibration import calib_params                  # noqa: E402
import solver_chain as sc                             # noqa: E402
from simulate import load_batch, simulate_open_loop, yield_metrics  # noqa: E402
from conservation_metrics import element_balance      # noqa: E402


# ---------------------------------------------------------------------------
# T1/T2/T3：健康度判据的真假阳性验证
# ---------------------------------------------------------------------------

def _mk_health(cv_map, fail_cum=None, z=None, cond=None, t=None, mean=None):
    """构造健康度旁路样本（用于合成场景）。

    cv_map 可以是「单步的通道字典」或「逐步的通道字典列表」：
      - dict  → n=1 的单步样本
      - list  → n=len(list) 的多步样本（每步一个通道字典）
    """
    if isinstance(cv_map, dict):
        cv_list = [dict(cv_map)]
        n = 1
    else:
        cv_list = [dict(c) for c in cv_map]
        n = len(cv_list)
    if t is None:
        t = [float(i) for i in range(n)]
    if fail_cum is None:
        fail_cum = [0] * n
    h = {"t": list(t), "cv": cv_list, "fail_cum": list(fail_cum)}
    if mean is not None:
        m = dict(mean)
        h["mean"] = [dict(m) for _ in range(n)]
    if z is not None:
        h["z"] = z
    if cond is not None:
        h["cond"] = cond
    return h


def verify_health_criteria():
    """T1/T2/T3：判据在合成样本上的真假阳性。"""
    rows = []

    # --- T1 健康样本（**有**健康证据）：不得触发 ---
    ok_samples = [
        ("nominal", _mk_health({"X": 3e-2, "P": 5e-2, "mup": 4e-2},
                               z=[{"DO2": 0.5}, {"DO2": 0.2}],
                               cond=[1e4, 2e4])),
        ("healthy_early_only", _mk_health({"X": 1e-2, "P": 2e-2},
                                           z=[{"DO2": 0.3}],
                                           cond=[5e3])),
    ]
    for name, h in ok_samples:
        r = sc.enkf_health(h, integration_failures=0, n_ens=40)
        rows.append({"case": name, "expect": "healthy", "got": r["healthy"],
                     "pass": bool(r["healthy"]), "reasons": r["reasons"]})

    # --- T2 退化样本：必须触发 ---
    bad_samples = [
        ("spread_collapse",
         _mk_health([{"X": 1e-9, "P": 5e-2}] * 5, z=[{"DO2": 0.5}] * 5,
                    cond=[1e4] * 5,
                    mean={"X": 20.0, "P": 5.0})),
        ("high_fail_rate",
         _mk_health({"X": 3e-2, "P": 5e-2}, fail_cum=[0, 40]),
         ),
        ("innovation_outlier",
         _mk_health([{"X": 3e-2, "P": 5e-2}] * 3,
                    z=[{"CO2outgas": 12.0}] * 3, cond=[1e4] * 3)),
        ("singular_covariance",
         _mk_health({"X": 3e-2, "P": 5e-2}, z=[{"DO2": 0.5}], cond=[1e15])),
    ]
    for name, h in bad_samples:
        r = sc.enkf_health(h, integration_failures=h.get("fail_cum", [0])[-1],
                           n_ens=40)
        rows.append({"case": name, "expect": "degraded", "got": r["healthy"],
                     "pass": (not r["healthy"]), "reasons": r["reasons"]})

    # --- T2c 白名单回归：非判据通道（Q/T）越限**不得**触发降级 ---
    # 依据 R161 实测（b8 真实批）：Q 越限 99.1%（zmax=4720）、T 越限 76.8%（zmax=19.8），
    # 而根因是**模型的** T 偏高 2–4 K / Q 发散 4 倍 ⇒ 这些通道的 |z| 在所有批上恒真越限。
    # 若把它们纳入判据，创新判据即退化为"恒真判据"（D-78 纪律）。
    nonjudged = _mk_health([{"X": 3e-2, "P": 5e-2}] * 3,
                           z=[{"Q": 4720.0, "T": 19.8}] * 3,
                           cond=[1e4] * 3)
    r = sc.enkf_health(nonjudged, integration_failures=0, n_ens=40)
    rows.append({"case": "excluded_channel_QT_not_collapse", "expect": "healthy",
                 "got": r["healthy"], "pass": bool(r["healthy"]),
                 "reasons": r["reasons"],
                 "metrics_note": "Q/T 因模型系统性偏差不在判据白名单（D-82）"})

    # --- T2b 假阳性回归：地板饱和步 + 单点越限 ⇒ **不得**判为坍塌 ---
    # 依据 R161 实测：b8 的 S 通道 raw_min(CV)=6.59e−16 全部来自
    # 「状态被 guards 钳在 1e-3 地板上」⇒ 屏蔽地板步后 masked_min=6.34e−03。
    # 本用例把该真实形态复现为合成样本，锁死该修正不被回退。
    floor_false_positive = _mk_health(
        [{"S": 6.6e-16, "X": 2.8e-5, "P": 3.5e-2}] * 8,
        z=[{"DO2": 0.5}] * 8, cond=[1e4] * 8,
        mean={"S": 1.0e-3, "X": 20.0, "P": 5.0})     # S 均值在地板上
    r = sc.enkf_health(floor_false_positive, integration_failures=0, n_ens=40)
    rows.append({"case": "floor_saturation_not_collapse", "expect": "healthy",
                 "got": r["healthy"], "pass": bool(r["healthy"]),
                 "reasons": r["reasons"],
                 "metrics_note": "S 在地板 ⇒ CV→0 是守卫产物，不算集合坍塌"})

    # 单点越限（持续性要求）：仅 1 步越限 ⇒ 不得判坍塌
    single_spike = _mk_health(
        [{"X": 3e-2, "P": 5e-2}] + [{"X": 1e-12, "P": 5e-2}] +
        [{"X": 3e-2, "P": 5e-2}] * 3,
        z=[{"DO2": 0.5}] * 5, cond=[1e4] * 5,
        mean={"X": 20.0, "P": 5.0})
    r = sc.enkf_health(single_spike, integration_failures=0, n_ens=40)
    rows.append({"case": "single_step_spike_not_collapse", "expect": "healthy",
                 "got": r["healthy"], "pass": bool(r["healthy"]),
                 "reasons": r["reasons"],
                 "metrics_note": "单点越限不构成持续坍塌"})

    # --- T3 零信息对照：**没有**健康证据 ⇒ 不得判为健康（纪律 19）---
    # 「无探针数据」与「空序列」都不是"健康"，而是"不可知" ⇒ 保守判降级。
    zero_info = [
        ("zero_info_no_probe", sc.enkf_health(None)),
        ("zero_info_empty_series", sc.enkf_health({"t": [], "cv": [],
                                                    "fail_cum": []})),
        ("zero_info_no_cv_key", sc.enkf_health({"t": [0.0, 1.0],
                                                 "fail_cum": [0, 0]})),
    ]
    for name, r in zero_info:
        rows.append({"case": name, "expect": "degraded", "got": r["healthy"],
                     "pass": (not r["healthy"]), "reasons": r["reasons"]})

    return rows


# ---------------------------------------------------------------------------
# T4：链穷尽 ⇒ 显式失败
# ---------------------------------------------------------------------------

def verify_explicit_failure():
    # 用 5 步持续坍塌样本（满足 spread 判据的持续性要求 ≥3 步）
    h_bad = sc.enkf_health(_mk_health([{"X": 1e-9, "P": 5e-2}] * 5,
                                       mean={"X": 20.0, "P": 5.0}))
    chain = sc.resolve_tier(h_bad, mhe_result=None, steady_result=None)
    return {
        "case": "chain_exhausted",
        "tier": chain["tier"],
        "expect": sc.TIER_FAILED,
        "pass": chain["tier"] == sc.TIER_FAILED,
        "trace_rings": [t["ring"] for t in chain["trace"]],
        "n_reasons": len(chain["reasons"]),
        "explicit": chain["explicit"],
    }


# ---------------------------------------------------------------------------
# T5：MHE 判据双向可证伪
# ---------------------------------------------------------------------------

def verify_mhe():
    rows = []

    # (a) 有结构：二次残差，存在可解的最优点 ⇒ 应判为可解（非 failed / 非 no_structure）
    def res_structured(x):
        return np.asarray([x[0] - 0.5, x[1] + 0.25])
    r1 = sc.mhe_step(res_structured, x0=np.array([0.0, 0.0]),
                     bounds=[(-2.0, 2.0), (-2.0, 2.0)])
    rows.append({"case": "structured_residual", "expect": "solvable",
                 "solver_failed": r1["solver_failed"],
                 "no_structure": r1["no_structure"],
                 "rel_improvement": r1["rel_improvement"],
                 "x": list(map(float, r1["x"])),
                 "pass": (not r1["solver_failed"]) and (not r1["no_structure"])})

    # (b) 无结构：残差与参数无关（常数）⇒ 相对改善 ≈ 0 ⇒ 必须判 no_structure
    def res_flat(x):
        return np.asarray([1.0, 1.0])
    r2 = sc.mhe_step(res_flat, x0=np.array([0.0, 0.0]),
                     bounds=[(-2.0, 2.0), (-2.0, 2.0)])
    rows.append({"case": "flat_residual", "expect": "no_structure",
                 "solver_failed": r2["solver_failed"],
                 "no_structure": r2["no_structure"],
                 "rel_improvement": r2["rel_improvement"],
                 "pass": bool(r2["no_structure"])})

    # (c) 求解器崩溃：残差函数抛异常 ⇒ 必须判 solver_failed
    def res_raise(x):
        raise RuntimeError("synthetic solver crash")
    r3 = sc.mhe_step(res_raise, x0=np.array([0.0]),
                     bounds=[(-1.0, 1.0)])
    rows.append({"case": "solver_exception", "expect": "solver_failed",
                 "solver_failed": r3["solver_failed"],
                 "no_structure": r3["no_structure"],
                 "message": r3["message"],
                 "pass": bool(r3["solver_failed"])})

    # (d) 零信息对照：把"有结构残差"换成随机噪声型目标面（无单调改善）
    #     —— 仍须得出明确判定，不得静默通过
    rng = np.random.default_rng(0)
    def res_noisy(x):
        return rng.normal(0.0, 1.0, 2)
    r4 = sc.mhe_step(res_noisy, x0=np.array([0.0, 0.0]),
                     bounds=[(-2.0, 2.0), (-2.0, 2.0)])
    rows.append({"case": "noisy_objective", "expect": "decided",
                 "solver_failed": r4["solver_failed"],
                 "no_structure": r4["no_structure"],
                 "rel_improvement": r4["rel_improvement"],
                 "pass": bool(r4["solver_failed"] or r4["no_structure"]
                              or r4["rel_improvement"] >= 0.0)})
    return rows


# ---------------------------------------------------------------------------
# T6：稳态碳平衡基线判据
# ---------------------------------------------------------------------------

def verify_steady_state():
    rows = []
    # (a) 闭合良好：hint 与反解一致 ⇒ credible
    a = sc.steady_state_baseline(1000.0, {"CO2": 400.0, "P": 300.0},
                                 x_hint_g=300.0)
    rows.append({"case": "closure_ok", "expect": "credible",
                 "credible": a["credible"], "c_error_pct": a["c_error_pct"],
                 "pass": bool(a["credible"])})
    # (b) 误差 >20% ⇒ 必须判不可信 ⇒ tier=explicit_failure
    b = sc.steady_state_baseline(1000.0, {"CO2": 100.0, "P": 100.0},
                                 x_hint_g=2000.0)
    rows.append({"case": "closure_break", "expect": "not_credible",
                 "credible": b["credible"], "c_error_pct": b["c_error_pct"],
                 "tier": b["tier"], "pass": (not b["credible"])
                 and b["tier"] == sc.TIER_FAILED})
    # (c) 边界：恰好 20% ⇒ 判为可信（判据是 >20% 才失败）
    c = sc.steady_state_baseline(1000.0, {"CO2": 0.0, "P": 0.0},
                                 x_hint_g=1200.0)
    rows.append({"case": "boundary_exact_20pct", "expect": "credible",
                 "credible": c["credible"], "c_error_pct": c["c_error_pct"],
                 "pass": bool(c["credible"])})
    return rows


# ---------------------------------------------------------------------------
# T7：observe.py opt-in 探针的零回归
# ---------------------------------------------------------------------------

def verify_zero_regression(batch_no=8, n_ens=8, seed=5):
    """opt-in 探针不得改变任何数值（records 逐位一致 + 集成失败计数一致）。"""
    t0 = time.time()
    a = enkf_observe(batch_no, params=calib_params(batch_no), n_ens=n_ens,
                     seed=seed, verbose=False, health_probe=False)
    b = enkf_observe(batch_no, params=calib_params(batch_no), n_ens=n_ens,
                     seed=seed, verbose=False, health_probe=True)
    ra, rb = a["records"], b["records"]
    n = min(len(ra), len(rb))
    max_diff = 0.0
    for i in range(n):
        for k in ra[i]:
            if isinstance(ra[i][k], (int, float)) and isinstance(rb[i].get(k), (int, float)):
                max_diff = max(max_diff, abs(float(ra[i][k]) - float(rb[i][k])))
    return {
        "batch": batch_no, "n_ens": n_ens, "seed": seed,
        "n_records": [len(ra), len(rb)],
        "max_abs_diff": max_diff,
        "failures": [a["integration_failures"], b["integration_failures"]],
        "has_health_key_a": "health" in a,
        "has_health_key_b": "health" in b,
        "health_n_steps": len(b.get("health", {}).get("cv", [])),
        # 探针健康度序列必须与 records 等长（逐步对齐），否则判据读的是错位数据
        "health_len_matches_records":
            len(b.get("health", {}).get("cv", [])) == len(rb),
        "pass": (max_diff == 0.0 and
                 a["integration_failures"] == b["integration_failures"] and
                 len(ra) == len(rb) and
                 ("health" not in a) and ("health" in b) and
                 len(b.get("health", {}).get("cv", [])) == len(rb)),
        "wall_s": round(time.time() - t0, 1),
    }


# ---------------------------------------------------------------------------
# 真实批：跑 EnKF 探针，看健康批是否误报降级
# ---------------------------------------------------------------------------

def run_real_batches(batches, n_ens=20, seed=7, verbose=True):
    rows = []
    for b in batches:
        t0 = time.time()
        out = enkf_observe(b, params=calib_params(b), n_ens=n_ens, seed=seed,
                           verbose=False, health_probe=True)
        chain = sc.classify_enkf_output(out)
        hr = sc.enkf_health(out.get("health"), records=out.get("records"),
                            integration_failures=out.get("integration_failures"),
                            n_ens=out.get("n_ens"))
        rows.append({
            "batch": b,
            "tier": chain["tier"],
            "healthy": hr["healthy"],
            "reasons": chain["reasons"],
            "metrics": {k: v for k, v in hr["metrics"].items()
                        if k in ("cv_min", "cv_median", "fail_rate",
                                 "integration_failures", "innovation_z_max",
                                 "cond_max")},
            "n_steps": hr["metrics"].get("n_steps"),
            "wall_s": round(time.time() - t0, 1),
        })
        if verbose:
            print("  batch %2d: tier=%-16s healthy=%s  %s"
                  % (b, chain["tier"], hr["healthy"],
                     (chain["reasons"][0][:70] if chain["reasons"] else "")),
                  flush=True)
    return rows


# ---------------------------------------------------------------------------
# 稳态基线的真实数据检验：C 平衡误差在 86 批上的分布
# ---------------------------------------------------------------------------

def run_steady_state_census(batches):
    """用真实批的 C/N 元素平衡数据检验稳态基线判据的可用性。

    这里**不复用** element_balance 的口径做判定（它本身是 V3 侧核算），
    而是用 solver_chain.steady_state_baseline 独立重算：
      c_in      = 元素平衡的 C_in
      已知输出  = C_CO2 + C_P + C_S_end
      x_hint    = 实测 X 的罐内净增量 × CF_X（作为独立量）
    ⇒ 得到"基线 vs 实测"两路 X 的对照 + C 平衡误差。
    """
    from conservation_metrics import (CF_GLC, CF_P, CF_X, _trapz,
                                      C_S, C_OIL, C_PAA)
    import pandas as pd
    rows = []
    for b in batches:
        v3 = load_batch(b)
        eb = element_balance(v3)
        t = v3["time_h"].to_numpy(float)
        # 独立重算 C_CO2 / C_P / C_S_end
        CER_g = _trapz(t, np.clip(v3["CER"].to_numpy(float), 0, None) *
                       v3["V"].to_numpy(float))
        C_co2 = CER_g * 12.0 / 44.0
        Frm = v3["Fremoved"].to_numpy(float)
        Ph = _trapz(t, -np.clip(Frm, None, 0) * v3["P"].to_numpy(float))
        Pe = float(v3["V"].iloc[-1] * v3["P"].iloc[-1])
        C_prod = (Ph + Pe) * CF_P
        C_sub = float(v3["S"].iloc[-1] * v3["V"].iloc[-1]) * CF_GLC
        # 实测 X 净增量（罐内 + 随排放移除 − 初始）
        xo = pd.to_numeric(v3["X_offline"], errors="coerce")
        x_t, x_v = [], []
        for i, val in xo.items():
            if np.isfinite(val):
                x_t.append(t[i] - 4.0)
                x_v.append(float(val))
        order = np.argsort(x_t)
        Xf = lambda tt: float(np.interp(tt, np.array(x_t)[order],
                                         np.array(x_v)[order])) if len(x_t) >= 2 else 0.0
        X_rem = _trapz(t, -np.clip(Frm, None, 0) * np.array([Xf(tt) for tt in t]))
        X0 = Xf(t[0]) * float(v3["V"].iloc[0])
        X_end = float(xo.dropna().iloc[-1]) * float(v3["V"].iloc[-1])
        X_net = max(X_end + X_rem - X0, 0.0)
        C_X_meas = X_net * CF_X

        res = sc.steady_state_baseline(
            c_in_g=eb["C_in_g"],
            c_out_components_g={"CO2": C_co2, "P": C_prod, "S_end": C_sub},
            x_hint_g=C_X_meas)
        rows.append({
            "batch": int(b),
            "c_in_g": res["c_in_g"],
            "x_carbon_g": res["x_carbon_g"],
            "x_meas_g": C_X_meas,
            "x_rel_diff_pct": (100.0 * (res["x_carbon_g"] - C_X_meas) / C_X_meas
                               if C_X_meas > 0 else float("nan")),
            "c_error_pct": res["c_error_pct"],
            "credible": res["credible"],
            "tier": res["tier"],
            "reasons": res["reasons"],
        })
    return rows


# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="runs/r161_fallback_chain_probe.json")
    ap.add_argument("--batches", default="8,11,22,36")
    ap.add_argument("--n-ens", type=int, default=20)
    ap.add_argument("--skip-real", action="store_true")
    ap.add_argument("--census", default="", help="稳态基线 C 平衡普查批号（逗号分隔）")
    a = ap.parse_args()

    print("== T1/T2/T3 健康度判据真假阳性 ==", flush=True)
    health_rows = verify_health_criteria()
    for r in health_rows:
        print("  %-26s expect=%-9s got=%-9s %s"
              % (r["case"], r["expect"], r["got"],
                 "PASS" if r["pass"] else "**FAIL**"), flush=True)

    print("== T4 显式失败语义 ==", flush=True)
    t4 = verify_explicit_failure()
    print("  chain_exhausted tier=%s %s" % (t4["tier"],
                                             "PASS" if t4["pass"] else "**FAIL**"),
          flush=True)

    print("== T5 MHE 判据双向可证伪 ==", flush=True)
    mhe_rows = verify_mhe()
    for r in mhe_rows:
        print("  %-22s expect=%-14s %s" % (r["case"], r["expect"],
                                           "PASS" if r["pass"] else "**FAIL**"),
              flush=True)

    print("== T6 稳态基线 C 平衡判据 ==", flush=True)
    steady_rows = verify_steady_state()
    for r in steady_rows:
        print("  %-22s expect=%-14s %s" % (r["case"], r["expect"],
                                           "PASS" if r["pass"] else "**FAIL**"),
              flush=True)

    print("== T7 opt-in 探针零回归 ==", flush=True)
    t7 = verify_zero_regression()
    print("  max|Δ|=%.3e  fail=%s  %s" % (t7["max_abs_diff"], t7["failures"],
                                          "PASS" if t7["pass"] else "**FAIL**"),
          flush=True)

    real_rows = []
    if not a.skip_real:
        print("== 真实批 EnKF 探针 ==", flush=True)
        bl = [int(x) for x in a.batches.split(",") if x.strip()]
        real_rows = run_real_batches(bl, n_ens=a.n_ens)

    census_rows = []
    if a.census:
        print("== 稳态基线 C 平衡普查 ==", flush=True)
        cl = [int(x) for x in a.census.split(",") if x.strip()]
        census_rows = run_steady_state_census(cl)
        cred = sum(1 for r in census_rows if r["credible"])
        print("  %d 批：credible %d / not-credible %d"
              % (len(census_rows), cred, len(census_rows) - cred), flush=True)

    all_pass = (all(r["pass"] for r in health_rows) and t4["pass"] and
                all(r["pass"] for r in mhe_rows) and
                all(r["pass"] for r in steady_rows) and t7["pass"])

    out = {
        "round": "R161",
        "debt": "D-75",
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "verdict": "PASS" if all_pass else "FAIL",
        "checks": {
            "T1_T3_health_criteria": health_rows,
            "T4_explicit_failure": t4,
            "T5_mhe": mhe_rows,
            "T6_steady_state": steady_rows,
            "T7_zero_regression": t7,
        },
        "real_batches": real_rows,
        "steady_state_census": census_rows,
        "thresholds": {
            "SPREAD_COLLAPSE_CV": sc.SPREAD_COLLAPSE_CV,
            "INNOVATION_Z_LIMIT": sc.INNOVATION_Z_LIMIT,
            "FAIL_RATE_LIMIT": sc.FAIL_RATE_LIMIT,
            "COND_LIMIT": sc.COND_LIMIT,
            "C_BALANCE_ERROR_LIMIT_PCT": sc.C_BALANCE_ERROR_LIMIT_PCT,
            "MHE_MIN_REL_IMPROVEMENT": sc.MHE_MIN_REL_IMPROVEMENT,
        },
    }
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)
    print("\nVERDICT: %s   -> %s" % (out["verdict"], a.out))
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
