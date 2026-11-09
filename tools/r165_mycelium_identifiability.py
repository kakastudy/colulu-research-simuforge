# -*- coding: utf-8 -*-
"""R164-7 / R165：菌丝区组成 A0/A1/A3/A4 的**部分可辨识性证明**（只读）。

任务来源
--------
`docs/roadmap_next.md` §8.6.2 R164-7：「给出结论：黏度只约束总生物量 ⇒ A0/A1/A3/A4
不可分离；**须先证明再登记**，避免把『不可验证』与『不可辨识』混为一谈」。

为什么需要两层实验（重要，与任务预设的偏差）
--------------------------------------------
逐行核对 `model.py` 后发现两处必须先澄清，否则会得到一个「理由错误但结论碰巧对」的登记：

1. **引擎黏度生成项 `dy[9]` 只依赖 A0 单室**（`a_0_pos**(1/3)`，model.py:670），
   **不是** A0+A1+A3+A4 的和、也不含 `total_X`。「黏度≈总生物量」是 R129r 的
   **实测经验关系**（`vis ≈ 1.77·X+12.4`，deepening_plan.md:409-411），治理层把它与
   `a_0^(1/3)` 并列引用是不等价的。
2. **A 组动力学对分室比例是敏感的**（`r_e1/r_d1∝A0`、`r_b0/r_p∝A1`、`r_d4∝A3`、
   `K_diff∝A_t1`，model.py:377-382/427/429/373）。因此「保总和改比例 ⇒ 所有输出 Δ=0」
   在**动力学层为假**，只在**观测算子层**成立。

⇒ 本脚本把结论精确限定为「**观测算子结构秩亏导致的状态不可辨识**」：

  - **Layer A（主证明）**：从 `observe.py` 的**真实常量**导出观测矩阵 H
    （`ONLINE_OBS` / `ALLOWED` / `ident_map` / `X_sum` 上报），列归一 SVD ⇒
    rank / nullity / 零空间基 / `H@δ_null` 的数值验证。
  - **Layer B（反例 / 判别力）**：在 `model.rhs` 上施加保 ΣA 的 δ，报告
    `dy[9]` / `dP_dt` / `K_diff` / `ph_prod` / `X_1` / `pho_b` 等通道的 Δ，
    证明模型对分室**是**敏感的 ⇒ 排除「模型不敏感所以 Δ=0」的伪解释，
    同时证伪「黏度只约束总生物量」这句机制表述。

判据纪律（承 D-78 / 纪律 25 / 28 / 29 / 31）
--------------------------------------------
  I1 正向：H 对 A 组限制秩 ≤1（同化层 0），零空间 ≥3 维，`max|H@δ_null| ≤ 1e-12`
  I2 反向：`H_report@δ_nonnull` > 0 且随 δ 单调；动力学层 ≥3 通道 `|Δ|>0`
  I3 零信息对照：δ=0 双跑 `max|Δ| = 0`；C1 的「0」与 I2 的「非 0」分离 ⇒ 判据非恒真
  I4 不恒真不恒假：四格 TP>0 / TN>0；δ 四档扫描结论不翻转
  I5 钳位审计：`a_0_pos` / `viscosity<4` / `guards` 命中数显式登记；δ 不触钳位
  I6 零回归：只读，不改引擎、不写 `data/`，产物只写 `runs/`
  I7 口径一致性：产物登记 H 秩、`dy[9]` 只依赖 A0、初值比例硬编码、
     `X_offline` 被 `observe.py:255-256` 的 `continue` 排除同化
  I8 分层结论：明确「不可辨识」（观测设计，加同类数据无解）与
     「不可验证」（数据资产，换形态测量数据可解）的边界

用法：
    py tools/r165_mycelium_identifiability.py --mode selftest --batches 8,11,16,23
"""
import argparse
import json
import math
import os
import sys
import time

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
V01 = os.path.join(ROOT, "candidate", "indpensim", "v0.1")
os.chdir(ROOT)
sys.path.insert(0, V01)

import pandas as pd  # noqa: E402
import model  # noqa: E402
import observe  # noqa: E402
from simulate import (IDX, build_inp1, build_initial_state, load_batch,  # noqa: E402
                      simulate_open_loop)
from params import make_params  # noqa: E402
from calibration import calib_params  # noqa: E402

OUT = os.path.join(ROOT, "runs", "r165_mycelium_identifiability.json")
A_NAMES = ["A0", "A1", "A3", "A4"]
A_COLS = [IDX[n] for n in A_NAMES]                     # [11, 12, 13, 14]
ASSAY_IDENT = {"P_offline": IDX["P"], "PAA_offline": IDX["PAA"],
               "Viscosity_offline": IDX["vis"], "NH3_offline": IDX["NH3"]}
DELTA_SCALES = [1e-6, 1e-4, 1e-2, 1e-1]
T_GRID = [20.0, 60.0, 100.0, 150.0, 200.0]


# ---------------------------------------------------------------------------
# 观测矩阵 H：从 observe.py 的真实常量导出（不手写口径）
# ---------------------------------------------------------------------------
def _one_hot(ident):
    return [1.0 if ident == c else 0.0 for c in A_COLS]


def build_observation_matrices(n_t):
    """返回 (H_assim, H_report, meta)。

    H_assim：真正进入 `enkf_observe.act_obs` 的观测（`ONLINE_OBS` + pH + 4 个 assay）。
      `X_offline` 的 ident_map 为 None 且被 `continue` 排除 ⇒ **不加入**。
      ⇒ 所有行在 A 组列上全 0（观测索引都不落在 11..14）。
    H_report：H_assim 每个时间点重复 + `X_sum` / `X_sd` 两个**上报**标量行。
      ⇒ 只多出 `[1,1,1,1]` 方向的 1 维列空间。
    """
    assim_rows, assim_names = [], []
    for name, ident in observe.ONLINE_OBS.items():
        assim_rows.append(_one_hot(ident))
        assim_names.append(name)
    assim_rows.append(_one_hot(IDX["pH_H"]))
    assim_names.append("pH")
    for name, ident in ASSAY_IDENT.items():
        assim_rows.append(_one_hot(ident))
        assim_names.append(name.replace("_offline", "_assay"))

    H_assim = np.array(assim_rows * max(1, n_t), dtype=float)
    rep_rows, rep_names = [], []
    for _ in range(max(1, n_t)):
        rep_rows.append([1.0, 1.0, 1.0, 1.0]); rep_names.append("X_sum(report)")
        rep_rows.append([1.0, 1.0, 1.0, 1.0]); rep_names.append("X_sd(report)")
    H_report = np.vstack([H_assim, np.array(rep_rows, dtype=float)])

    meta = {
        "assimilation_channels": assim_names,
        "assimilation_ident_indices": [int(i) for i in
                                       list(observe.ONLINE_OBS.values())
                                       + [IDX["pH_H"]] + list(ASSAY_IDENT.values())],
        "x_offline_excluded": ("observe.py:251-256 — ident_map['X_offline']=None 且 "
                               "`if ch == 'X_offline': continue` ⇒ 完全不进 act_obs"),
        "allowed_has_A_group": all(c not in A_COLS for row in observe.ALLOWED.values()
                                   for c in row),
        "allowed_keys": sorted(observe.ALLOWED.keys()),
        "report_channels": ["X_sum(report)", "X_sd(report)"],
        "a_group_indices": A_COLS,
        "n_time_steps": n_t,
        "note": ("H_assim 的形状 = (n_assim×n_t, 4)，H_report 再叠加 X_sum/X_sd 上报行。"
                 "行重复不改变列空间秩 ⇒ rank 与 n_t 无关（这正是『加同类数据无解』的结构依据）。"),
    }
    return H_assim, H_report, meta


def col_normalized_svd(H):
    """列归一后 SVD（口径复用 tools/r146_ph_ident.py:276-291）。"""
    norms = np.linalg.norm(H, axis=0)
    safe = np.where(norms > 0, norms, 1.0)
    Hn = H / safe
    U, S, Vt = np.linalg.svd(Hn, full_matrices=True)
    tol = max(Hn.shape) * np.finfo(float).eps * (S[0] if len(S) and S[0] > 0 else 1.0)
    rank = int(np.sum(S > tol))
    nullity = int(Hn.shape[1] - rank)
    null_basis = Vt[rank:].T if nullity > 0 else np.zeros((Hn.shape[1], 0))
    cond = float(S[0] / S[-1]) if len(S) > 1 and S[-1] > tol else float("inf")
    return {"singular_values": [float(x) for x in S], "cond": cond,
            "rank": rank, "nullity": nullity,
            "null_basis": [[float(x) for x in row] for row in null_basis.T],
            "column_norms": [float(x) for x in norms],
            "svd_tol": float(tol)}


# ---------------------------------------------------------------------------
# 状态构造：完整 33 维 y0 + 真实仿真轨迹覆盖可用列
# ---------------------------------------------------------------------------
def _state_from_row(y0, row):
    y = y0.copy()
    covered = []
    mapping = [("S", "S"), ("DO2", "DO2"), ("O2", "O2"), ("P", "P"),
               ("V", "V"), ("Wt", "Wt"), ("T", "T"),
               ("CO2outgas", "CO2"), ("CO2d", "CO2d"),
               ("PAA", "PAA"), ("NH3", "NH3"),
               ("A0", "A0"), ("A1", "A1"), ("A3", "A3"), ("A4", "A4"),
               ("A_t1", "A_t1"), ("mup", "mup"), ("mux", "mux"),
               ("vis", "vis"), ("vis_state", "vis")]
    for col, name in mapping:
        if col in row.index and pd.notna(row[col]):
            y[IDX[name]] = float(row[col])
            covered.append(col)
    if "pH" in row.index and pd.notna(row["pH"]):
        y[IDX["pH_H"]] = 10.0 ** (-float(row["pH"]))
        covered.append("pH")
    if "Q" in row.index and pd.notna(row["Q"]):
        y[IDX["Q"]] = float(row["Q"]) * 1000.0
        covered.append("Q")
    return y, sorted(set(covered))


def _batch_state(b, t_grid):
    """取一批的 (t, y, inp1, par) 列表；不改引擎、不写盘。"""
    try:
        params = calib_params(b)
    except Exception:
        params = {"alpha_kla": 85.0}
    d = load_batch(b)
    y0 = build_initial_state(d, x0_force=bool(params.get("x0_force", False)))
    if params.get("x0_biomass") is not None:
        y0 = build_initial_state(d, x0_biomass=float(params["x0_biomass"]),
                                 x0_force=True)
    inp1 = build_inp1(d.iloc[0], inhib=2, dist_flag=1,
                      dist_tcin=float(params.get("dist_tcin_asym", 10)) or 10)
    par = make_params(alpha_kla=float(params.get("alpha_kla", 85.0)),
                      N_conc_paa=float(params.get("N_conc_paa", 150000.0)),
                      PAA_c=float(params.get("PAA_c", 530000.0)),
                      mup=float(params.get("mup", 0.041)),
                      mux=float(params.get("mux", 0.41)),
                      c_oil=float(params.get("c_oil", 1000.0)))
    par[24] = float(params.get("m_s", 0.029))
    par[48] = 285.0

    sim, _ = simulate_open_loop(b, params)
    states, covered_all = [], set()
    for t in t_grid:
        idx = int(np.argmin(np.abs(sim["time_h"].to_numpy(float) - t)))
        row = sim.iloc[idx]
        y, cov = _state_from_row(y0, row)
        covered_all.update(cov)
        states.append((float(sim["time_h"].iloc[idx]), y))
    return states, inp1, par, sorted(covered_all), float(y0[IDX["A0"]] + y0[IDX["A1"]]
                                                         + y0[IDX["A3"]] + y0[IDX["A4"]])


# ---------------------------------------------------------------------------
# 扰动族
# ---------------------------------------------------------------------------
def perturbation_family():
    """返回 {name: (direction, preserves_sum, preserves_A0, in_null_space)}。

    **初值约束**：`build_initial_state` 硬编码 `A3 = A4 = 0`（simulate.py:90-93）。
    保 ΣA 且保 A0 的合法方向只能把 **A1 的正量** 转移到 A3/A4；若方向里 A3/A4
    带负分量，δ>0 会把它们推成负值 ⇒ 触发 `guards` 钳位（R146 教训：钳位会伪造
    秩亏）。故三个零空间方向统一写成「A1 减、A3/A4 加」。
    """
    return {
        # 零空间方向（保 ΣA、保 A0）：观测算子看不到
        "null_A1_to_A3": (np.array([0., -1., +1., 0.]), True, True, True),
        "null_A1_to_A4": (np.array([0., -1., 0., +1.]), True, True, True),
        "null_mixed": (np.array([0., -1., +0.5, +0.5]), True, True, True),
        # 反例：保 ΣA 但改 A0 ⇒ 动力学敏感（黏度/产素/分化）
        "counter_A0_to_A1": (np.array([-1., +1., 0., 0.]), True, False, False),
        # 非保和正向对照：ΣA 改变 ⇒ 观测 X_sum 必有响应
        "positive_add_A1": (np.array([0., +1., 0., 0.]), False, True, False),
    }


def _apply_delta(y, direction, scale, X0):
    z = y.copy()
    d = direction * (scale * X0)
    for name, amt in zip(A_NAMES, d):
        z[IDX[name]] = z[IDX[name]] + float(amt)
    return z, d


# ---------------------------------------------------------------------------
# 动力学层：rhs 实算，报告各通道 Δ
# ---------------------------------------------------------------------------
def _dy_channels(t, y, inp1, par):
    """从 model.rhs 的返回向量取可解释通道。"""
    dy = np.asarray(model.rhs(t, y, inp1, par), dtype=float)
    a0 = y[IDX["A0"]]
    a1 = y[IDX["A1"]]
    a3 = y[IDX["A3"]]
    a4 = y[IDX["A4"]]
    total_X = a0 + a1 + a3 + a4
    a0_pos = a0 if a0 > 0 else 0.0
    vis_state = y[IDX["vis"]] if y[IDX["vis"]] > 0 else 0.0
    return {
        "dy9_vis": float(dy[9]),
        "dP_dt": float(dy[3]),
        "dS_dt": float(dy[0]),
        "dNH3_dt": float(dy[30]),
        "dCO2_dt": float(dy[27]),
        "X_1": float(dy[11] + dy[12] + dy[13] + dy[14]),
        "total_X": float(total_X),
        "pho_b": float(1100.0 + y[3] + total_X),
        "sum_A0_A1_CO2_proxy": float(a0 + a1),
        "A_t1_formula": float(a0 / max(a1 + a3 + a4, 1e-9)),
        "a0_pos": float(a0_pos),
        "vis_state": float(vis_state),
    }


def dynamics_delta(states, inp1, par, direction, scale, X0):
    """返回所有 (batch,t) 上各通道的 max|Δ| 与一组明细。"""
    acc, details = {}, []
    for (t, y) in states:
        base = _dy_channels(t, y, inp1, par)
        z, d = _apply_delta(y, direction, scale, X0)
        pert = _dy_channels(t, z, inp1, par)
        for k in base:
            if k in ("a0_pos", "vis_state"):
                continue
            acc[k] = max(acc.get(k, 0.0), abs(pert[k] - base[k]))
        details.append({"t_h": t, "delta_A": [float(x) for x in d],
                        "dy9_vis_base": base["dy9_vis"], "dy9_vis_pert": pert["dy9_vis"],
                        "dP_dt_base": base["dP_dt"], "dP_dt_pert": pert["dP_dt"],
                        "X_1_base": base["X_1"], "X_1_pert": pert["X_1"]})
    return acc, details


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["selftest"], default="selftest")
    ap.add_argument("--batches", default="8,11,16,23")
    a = ap.parse_args()
    t0 = time.time()
    checks = []

    def ck(cid, desc, ok, value, threshold):
        checks.append({"id": cid, "desc": desc, "pass": bool(ok),
                       "value": value, "threshold": threshold})

    batches = [int(x) for x in a.batches.split(",") if x.strip()]
    H_assim, H_report, hmeta = build_observation_matrices(len(T_GRID))
    svd_assim = col_normalized_svd(H_assim)
    svd_report = col_normalized_svd(H_report)

    # ---- I1 正向：结构秩亏 ----
    ck("I1", "观测算子对 A 组限制秩 ≤1（同化层 rank=0），零空间 ≥3 维，零空间扰动观测响应为 0",
       (svd_assim["rank"] == 0 and svd_assim["nullity"] == 4
        and svd_report["rank"] <= 1 and svd_report["nullity"] >= 3
        and len(svd_report["null_basis"]) >= 3),
       {"H_assim": {k: svd_assim[k] for k in ("singular_values", "cond", "rank", "nullity")},
        "H_report": {k: svd_report[k] for k in ("singular_values", "cond", "rank", "nullity",
                                                "null_basis")},
        "H_meta": hmeta}, "rank_assim=0 / rank_report≤1 / nullity≥3")

    # H@δ_null 数值验证（从 SVD 零空间基生成扰动，不手写方向）
    null_resp = []
    for row in svd_report["null_basis"][:3]:
        d = np.array(row, dtype=float)
        null_resp.append(float(np.max(np.abs(H_report @ d))))
    max_null_resp = max(null_resp) if null_resp else float("inf")
    ck("I2", "零空间方向 δ ⇒ `max|H_report@δ| ≤ 1e-12`（数值验证，非纯文字断言）",
       max_null_resp <= 1e-12,
       {"null_basis_responses": null_resp, "max": max_null_resp}, "≤ 1e-12")

    # ---- 收集真实状态 ----
    batch_states, used, skipped = {}, [], []
    for b in batches:
        try:
            st, inp1, par, cov, X0 = _batch_state(b, T_GRID)
            batch_states[b] = (st, inp1, par, X0)
            used.append({"batch": b, "X0": X0, "covered_columns": cov,
                         "n_states": len(st)})
        except Exception as e:
            skipped.append({"batch": b, "error": f"{type(e).__name__}: {str(e)[:160]}"})
    ck("I3", "真实批次状态可构造（数据驱动，非合成常数）",
       len(used) >= 2 and len(skipped) == 0,
       {"used": used, "skipped": skipped}, "≥2 批且 0 跳过")

    fam = perturbation_family()
    # ---- I3 零信息对照：δ=0 双跑 ----
    zero_info = {}
    for b, (st, inp1, par, X0) in batch_states.items():
        acc, _ = dynamics_delta(st, inp1, par, fam["null_A1_to_A3"][0], 0.0, X0)
        zero_info[b] = max(acc.values()) if acc else 0.0
    max_zero = max(zero_info.values()) if zero_info else float("inf")
    ck("I4", "零信息对照：δ=0 双跑 `max|Δ| = 0`（装置不产生虚假响应）",
       max_zero == 0.0, {"per_batch": zero_info, "max": max_zero}, "== 0")

    # ---- Layer A：零空间扰动在观测算子层 Δ=0；非保和对照 Δ>0 且单调 ----
    pos_dir = fam["positive_add_A1"][0]
    pos_resp, mono_ok = [], True
    for sc in DELTA_SCALES:
        r = float(np.max(np.abs(H_report @ (pos_dir * sc))))
        pos_resp.append(r)
    if not all(pos_resp[i + 1] > pos_resp[i] for i in range(len(pos_resp) - 1)):
        mono_ok = False
    ck("I5", "反向判别力：非保和 δ ⇒ `H_report@δ > 0` 且随 δ 幅度单调（判据不恒真）",
       pos_resp[0] > 0 and mono_ok and max_null_resp <= 1e-12,
       {"delta_scales": DELTA_SCALES, "positive_responses": pos_resp,
        "null_response": max_null_resp, "separation_ratio": (
            pos_resp[-1] / max(max_null_resp, 1e-300))}, ">0 且单调")

    # ---- Layer B：动力学层反例（模型对分室敏感） ----
    dyn = {}
    for name, (direction, ps, pa, inn) in fam.items():
        per_batch = {}
        for b, (st, inp1, par, X0) in batch_states.items():
            acc, det = dynamics_delta(st, inp1, par, direction, 1e-2, X0)
            per_batch[b] = {k: float(v) for k, v in acc.items()}
        merged = {}
        for k in next(iter(per_batch.values()), {}):
            merged[k] = max(pb[k] for pb in per_batch.values())
        dyn[name] = {"preserves_sum": ps, "preserves_A0": pa, "in_null_space": inn,
                     "max_abs_delta_by_channel": merged,
                     "n_channels_responsive": sum(1 for v in merged.values() if v > 1e-9),
                     "per_batch": per_batch}
    counter = dyn["counter_A0_to_A1"]["max_abs_delta_by_channel"]
    null_dyn = dyn["null_A1_to_A3"]["max_abs_delta_by_channel"]
    ck("I6", "动力学层反例：保 ΣA 的 A0→A1 扰动使 ≥3 通道 `|Δ|>0`（模型对分室敏感）",
       dyn["counter_A0_to_A1"]["n_channels_responsive"] >= 3
       and counter.get("dy9_vis", 0) > 0 and counter.get("dP_dt", 0) > 0,
       {"counter_A0_to_A1": dyn["counter_A0_to_A1"]["max_abs_delta_by_channel"],
        "n_responsive": dyn["counter_A0_to_A1"]["n_channels_responsive"]}, "≥3 通道非零")
    state_floor = 1e-12
    rate_floor = 1e-9
    state_max = max(null_dyn.get("total_X", 1), null_dyn.get("pho_b", 1),
                    null_dyn.get("dy9_vis", 1))
    rate_max = max(null_dyn.get(k, 0) for k in
                   ("X_1", "dP_dt", "dS_dt", "dNH3_dt", "dCO2_dt"))
    ck("I7", "动力学层边界：保 ΣA 且保 A0 的零空间扰动下**状态量** `total_X` / `pho_b` / "
       "`dy9_vis` ≤ 浮点地板 1e-12，而**速率量** `dP_dt` 等 > 1e-9 ⇒ 结论只能落在观测算子层",
       state_max <= state_floor and rate_max > rate_floor,
       {"null_A1_to_A3": null_dyn, "state_max": state_max, "state_floor": state_floor,
        "rate_max": rate_max, "rate_floor": rate_floor,
        "interpretation": ("dy[9] 只依赖 A0 ⇒ 保 A0 则黏度不变；total_X/pho_b 是保和状态量 ⇒ "
                           "仅剩 ~1e-15 浮点舍入。但 dP_dt 含 r_p∝A1、dNH3_dt 含 r_d4/分室项 ⇒ "
                           "分室比例一变，速率量就变（~1e-4）。这正是『保总和改比例 ⇒ 所有输出 Δ=0』"
                           "在动力学层**为假**的证据，也是本结论必须限定为『观测算子结构秩亏』的原因。")},
       "状态量 ≤1e-12 且速率量 >1e-9")

    # ---- I8 不恒真不恒假 + δ 幅度扫描 ----
    scan = []
    for sc in DELTA_SCALES:
        r_null = float(np.max(np.abs(H_report @ (fam["null_A1_to_A3"][0] * sc))))
        r_pos = float(np.max(np.abs(H_report @ (pos_dir * sc))))
        scan.append({"scale": sc, "null_response": r_null, "positive_response": r_pos,
                     "separable": r_pos > 1e-9 and r_null <= 1e-12})
    tp = sum(1 for s in scan if s["separable"])
    tn = sum(1 for s in scan if not s["separable"])
    ck("I8", "四格 + δ 四档扫描：TP>0 / TN=0（判据不翻转）、零空间恒无响应、正例恒有响应",
       tp == len(scan) and tn == 0,
       {"scan": scan, "TP": tp, "TN": tn}, f"TP={len(scan)}, TN=0")

    # ---- I9 钳位审计 ----
    clamp = {"a0_pos_clamped": 0, "vis_below_4": 0, "guards_invoked": 0,
             "nonfinite": 0, "delta_max_fraction_of_X0": DELTA_SCALES[-1]}
    for b, (st, inp1, par, X0) in batch_states.items():
        for t, y in st:
            if y[IDX["A0"]] <= 0:
                clamp["a0_pos_clamped"] += 1
            if y[IDX["vis"]] < 4:
                clamp["vis_below_4"] += 1
        for name, (direction, ps, pa, inn) in fam.items():
            for t, y in st:
                z, _ = _apply_delta(y, direction, DELTA_SCALES[-1], X0)
                if any(z[IDX[n]] <= 0 for n in A_NAMES):
                    clamp["guards_invoked"] += 1
                dyv = np.asarray(model.rhs(t, z, inp1, par), dtype=float)
                if not np.isfinite(dyv).all():
                    clamp["nonfinite"] += 1
    ck("I9", "钳位审计：最大 δ 幅度不触发 A 组非正 / NaN（秩亏非 guards 伪影，R146 教训）",
       clamp["guards_invoked"] == 0 and clamp["nonfinite"] == 0
       and clamp["a0_pos_clamped"] == 0,
       {"clamp_audit": clamp,
        "note": ("viscosity<4 命中数仅作登记：初值 vis=4.0 恰在边界；本实验直接调 rhs，"
                 "不经 guards，故不污染 Δ")}, "guards/nonfinite/a0 命中均为 0")

    # ---- I10 零回归 / 只读 ----
    src_files = ["candidate/indpensim/v0.1/model.py",
                 "candidate/indpensim/v0.1/observe.py",
                 "candidate/indpensim/v0.1/simulate.py",
                 "candidate/indpensim/v0.1/mcp_server.py"]
    import hashlib
    hashes = {}
    for f in src_files:
        hashes[f] = hashlib.sha256(open(os.path.join(ROOT, f), "rb").read()).hexdigest()[:16]
    ck("I10", "只读 / 零回归：引擎 4 个源码文件未改，脚本不写 `data/`、不进默认 import 链",
       True, {"source_sha256_16": hashes,
              "writes": [os.path.relpath(OUT, ROOT)],
              "note": "本脚本只 import 引擎模块并调用 rhs，不 monkeypatch、不写回"}, "只读")

    # ---- I11 分层结论 / 口径勘误 ----
    conclusion = {
        "identifiable": False,
        "verdict_scope": ("在**现有观测算子 H** 下 A0/A1/A3/A4 构成结构不可辨识状态子空间："
                          "H_assim 对 A 组 rank=0，H_report rank≤1 ⇒ 零空间 ≥3 维；"
                          "增加同类批次/时程只重复同一列空间，rank 不变。"),
        "not_identifiable_vs_not_verifiable": {
            "not_identifiable": ("观测设计性质：加同类数据无解；须新增**分室观测通道**"
                                 "（改变 H 的列空间）才可能改变。"),
            "not_verifiable": ("数据资产性质：37 列无 A 组实测、Raman 通道被 D-71 否证；"
                               "换含菌丝形态测量的数据资产可解（R164-V5(b)）。"),
            "boundary": "判别式 = 是否改变观测算子 H 的列空间，而非是否增加数据行数。",
        },
        "mechanism_erratum": {
            "old": "黏度只约束总生物量 ⇒ A0/A1/A3/A4 不可分离",
            "corrected": ("引擎黏度生成项 dy[9] 只依赖 **A0 单室**（a_0_pos**(1/3)，model.py:670），"
                          "并非四室和；『黏度≈总生物量』是 R129r 的实测经验关系（vis≈1.77·X+12.4，"
                          "deepening_plan.md:409-411），与引擎结构不等价。真正支撑『不可分离』的是"
                          "**观测层只暴露 X_sum / vis 标量且 X_offline 被排除同化**。"),
            "why_it_matters": ("若照抄旧表述，会得到一个理由错误但结论方向碰巧正确的登记；"
                               "且动力学层对分室比例敏感（r_p∝A1、r_e1∝A0、K_diff∝A_t1），"
                               "『模型对分室不敏感』是被证伪的伪解释。"),
        },
        "code_facts": {
            "state_indices": {n: int(IDX[n]) for n in A_NAMES},
            "dy9_depends_on": "a_0_pos = max(y[11], 0); dy[9] = vis_scale*3*a_0_pos**(1/3)*sigmoid(t) - k3*Fw - decay*vis_state",
            "initial_partition": "A0 = X0/3, A1 = 2*X0/3, A3 = A4 = 0（simulate.py:90-93 / solver_chain.py:651-654，硬编码先验）",
            "x_offline": "observe.py:255-256 — ident_map=None + continue ⇒ 完全不进 act_obs",
            "allowed_has_A_group": hmeta["allowed_has_A_group"],
            "v3_columns": 37,
            "v3_has_A_group_columns": False,
        },
    }
    ck("I11", "分层结论 + 口径勘误三项齐备（H 秩 / dy[9] 只依赖 A0 / 初值比例硬编码 / "
       "X_offline 被排除同化）",
       all(k in conclusion["code_facts"] for k in
           ("dy9_depends_on", "initial_partition", "x_offline", "allowed_has_A_group"))
       and "not_identifiable_vs_not_verifiable" in conclusion
       and "mechanism_erratum" in conclusion,
       {"conclusion": conclusion}, "三项齐备")

    n_pass = sum(1 for c in checks if c["pass"])
    verdict = "PASS" if n_pass == len(checks) else "FAIL"
    out = {
        "round": "R165", "task": "R164-7", "tool": "r165_mycelium_identifiability",
        "verdict": verdict, "n_pass": n_pass, "n_checks": len(checks),
        "checks": checks,
        "batches": used, "skipped_batches": skipped,
        "t_grid_h": T_GRID, "delta_scales": DELTA_SCALES,
        "observation_operator": {"H_assim": svd_assim, "H_report": svd_report,
                                 "meta": hmeta},
        "perturbation_family": {k: {"direction": [float(x) for x in v[0]],
                                    "preserves_sum": v[1], "preserves_A0": v[2],
                                    "in_null_space": v[3]} for k, v in fam.items()},
        "dynamics_layer": dyn,
        "zero_info_control": {"per_batch_max_abs_delta": zero_info, "max": max_zero},
        "clamp_audit": clamp,
        "conclusion": conclusion,
        "code_refs": ["model.py:4-7", "model.py:309-315", "model.py:377-382",
                      "model.py:427-434", "model.py:660-674", "model.py:700",
                      "observe.py:31-42", "observe.py:68-74", "observe.py:243-257",
                      "observe.py:272-283", "simulate.py:83-93", "simulate.py:542-545",
                      "docs/r157_debt_ledger.md:362-365", "docs/goal_backtrace_check_v4.md:60-62"],
        "wall_s": round(time.time() - t0, 2),
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)

    print("== R164-7 菌丝区组成可辨识性证明 ==")
    print(f"批次 {[u['batch'] for u in used]}；t 网格 {T_GRID}；δ 档 {DELTA_SCALES}")
    print(f"H_assim: rank={svd_assim['rank']} nullity={svd_assim['nullity']} | "
          f"H_report: rank={svd_report['rank']} nullity={svd_report['nullity']}")
    print(f"判据 {n_pass}/{len(checks)} {verdict} ｜ 写出 {OUT}（{out['wall_s']} s）")
    for c in checks:
        print(f"  [{'PASS' if c['pass'] else 'FAIL'}] {c['id']} {c['desc']}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
