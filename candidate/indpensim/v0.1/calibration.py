# -*- coding: utf-8 -*-
"""黄金集校准参数入口 —— R132 起降级为 `golden_params` 的薄适配层。

**本模块不再持有参数数据。** 唯一事实源是 `golden_params.py`（同目录）里的
`COMBINED` + `build_params()`。

历史问题（R132 修复）：本模块的 `CAL`（13 批 × 10 元组）与黄金回归用的
`COMBINED`（88 批 dict）是两份独立数据，靠人肉"同步更新"。后果有实证：
R131 对 b27/b36/b60/b92 的标定只写进了 COMBINED，MCP `golden_set_validate`、
dashboard、observe、optimize 至今仍按 CAL 报旧参数。更早的
`tools/d9_death_term_combined_ctx.py` 头部就记录了同一现象——
"校准在 calib_params 语境（含 PAA_CAL），但黄金回归用 COMBINED dict（不含 PAA_CAL），
语境不同 → 衰亡项效果不同"。R132 把两条路径合并为一条。

保留 `calib_params(b)` 的旧签名（8 个模块在用），但内部改为：
    calib_params(b) = build_params(COMBINED[b]) + PAA 门控模式补缺
其中 PAA 覆盖只**补缺不覆盖**（见 PAA_CAL 注释），确保 SSOT 始终是动力学参数的权威。
"""

from golden_params import COMBINED, build_params, GOLDEN_ALL

# 评估集（86 批）与"有标定参数的批"（88 批）是两个概念：
#   - GOLDEN_ALL：黄金回归 / D6 健康视图的验收集，GOAL §4.1"只增不减"；
#   - COMBINED：有逐批标定的批（88 批，含未进评估集的 b37/b50/b100 等）。
# 本模块下方的 GOLDEN_* 是**历史兼容集**（13 批：早期 A 档校准的那批），
# 被 dashboard 下拉框与若干评估脚本当作默认批列表使用，R132 未改动其成员，
# 避免一次性改变十余个脚本的运行时长与报告口径。要跑全量请用 GOLDEN_ALL。
GOLDEN_NORMAL = [8, 11, 16, 22, 23, 27, 36, 51, 55, 60, 80]
GOLDEN_FAULT = [91, 92]
GOLDEN = GOLDEN_NORMAL + GOLDEN_FAULT

# PAA 门控模式（mode 1）专属覆盖 —— R132 起只补"门控专属键"，其余一概以 SSOT 为准。
#
# PAA_MODE_KEYS 是白名单而非"补缺"：早期这里同时混入了 biomass_death_rate /
# death_start / late_death_rate / m_paa 等动力学参数（R125 估计）。若按"SSOT 缺什么
# 就补什么"处理，R131 为压 X 幅度**主动删除**的 late_death_rate 会被重新加回来，
# 导致 b36/b60/b92 同时跑"恒定衰亡 + 晚期衰亡"两套机制——静默改变黄金回归结果。
# 故只允许两个 rhs 关键字参数通过，其余一律忽略。
#
# 这里的 paa_degrad_rate / paa_maintenance_target 是 rhs() 的关键字参数，不在
# params 默认表里，只有 PAA 门控模式用得上，因此必须由本 dict 补。
# 但历史条目里同时混入了 biomass_death_rate / death_start / late_death_rate 等
# **动力学参数**（R125 当时的估计值），它们与 COMBINED 已经分叉——
# 例：b8 这里 biomass_death_rate=0.005，COMBINED 是 0.001（R130 重标定后）。
# 若继续 update() 覆盖，等于让旧估计反向污染权威表。故 calib_params 改为
# setdefault 语义：SSOT 有的一律以 SSOT 为准，SSOT 没有的才由这里补。
# 这样既不丢 PAA 模式所需参数，也不会静默回退已完成的标定。
PAA_MODE_KEYS = {"paa_degrad_rate", "paa_maintenance_target"}

PAA_CAL = {
    8:  {"m_paa": 1.0,  "paa_degrad_rate": 0.008,  "paa_maintenance_target": 1,
          "biomass_death_rate": 0.005, "death_start": 100, "PAA_c": 530000.0,
          "Y_O2_X": 800, "Y_O2_P": 200, "m_O2_X": 15,
          "late_death_rate": 0.005, "mu_death_ref": 0.02, "death_recycle": 0.5},
    11: {"m_paa": 0.7,  "paa_degrad_rate": 0.008,  "paa_maintenance_target": 1,
          "biomass_death_rate": 0.005, "death_start": 100, "PAA_c": 530000.0,
          "Y_O2_X": 800, "Y_O2_P": 80, "m_O2_X": 15,
          "late_death_rate": 0.008, "mu_death_ref": 0.02, "death_recycle": 0.3},
    16: {"m_paa": 0.5,  "paa_degrad_rate": 0.008,  "paa_maintenance_target": 1,
          "biomass_death_rate": 0.005, "death_start": 0, "PAA_c": 400000.0,
          "Y_O2_X": 800, "Y_O2_P": 200, "m_O2_X": 17.5,
          "late_death_rate": 0.008, "mu_death_ref": 0.01, "death_recycle": 0.3},
    22: {"m_paa": 1.0,  "paa_degrad_rate": 0.010,  "paa_maintenance_target": 1,
          "biomass_death_rate": 0.005, "death_start": 0, "PAA_c": 530000.0,
          "mu_h_scale": 3.5,
          "late_death_rate": 0.008, "mu_death_ref": 0.02, "death_recycle": 0.5},
    23: {"m_paa": 1.0,  "paa_degrad_rate": 0.003,  "paa_maintenance_target": 1,
          "PAA_c": 530000.0,
          "Y_O2_X": 650, "Y_O2_P": 200, "m_O2_X": 15,
          "mu_h_scale": 3.5,
          "late_death_rate": 0.002, "mu_death_ref": 0.02, "death_recycle": 0.3},
    51: {"m_paa": 1.0,  "paa_degrad_rate": 0.008,  "paa_maintenance_target": 1,
          "PAA_c": 530000.0,
          "mu_h_scale": 1.5},
    27: {"m_paa": 1.0,  "paa_degrad_rate": 0.008,  "paa_maintenance_target": 1,
          "PAA_c": 530000.0,
          "Y_O2_X": 650, "Y_O2_P": 160, "m_O2_X": 15},
    36: {"m_paa": 0.7,  "paa_degrad_rate": 0.003,  "paa_maintenance_target": 1,
          "biomass_death_rate": 0.003, "death_start": 160, "PAA_c": 530000.0,
          "Y_O2_X": 650, "Y_O2_P": 160, "m_O2_X": 10,
          "late_death_rate": 0.005, "mu_death_ref": 0.005, "death_recycle": 0.0},
    55: {"m_paa": 1.0,  "paa_degrad_rate": 0.003,  "paa_maintenance_target": 1,
          "PAA_c": 530000.0,
          "Y_O2_X": 650, "Y_O2_P": 160, "m_O2_X": 17.5},
    60: {"m_paa": 1.0,  "paa_degrad_rate": 0.0045, "paa_maintenance_target": 1,
          "biomass_death_rate": 0.003, "death_start": 120, "PAA_c": 530000.0,
          "late_death_rate": 0.005, "mu_death_ref": 0.005, "death_recycle": 0.0},
    80: {"m_paa": 0.3,  "paa_degrad_rate": 0.0045, "paa_maintenance_target": 1,
          "biomass_death_rate": 0.005, "death_start": 0, "PAA_c": 400000.0,
          "Y_O2_X": 800, "Y_O2_P": 120, "m_O2_X": 17.5},
    91: {"m_paa": 0.1,  "paa_degrad_rate": 0.003,  "paa_maintenance_target": 1,
          "biomass_death_rate": 0.005, "death_start": 60, "PAA_c": 530000.0},
    92: {"m_paa": 0.7,  "paa_degrad_rate": 0.003,  "paa_maintenance_target": 1,
          "biomass_death_rate": 0.005, "death_start": 200, "PAA_c": 530000.0,
          "Y_O2_X": 650, "Y_O2_P": 160, "m_O2_X": 17.5,
          "late_death_rate": 0.005, "mu_death_ref": 0.005, "death_recycle": 0.0},
}

# ===================== 历史快照（只读，勿用于任何计算）=====================
# 这是 R132 之前的 13 批元组表，字段顺序：
#   (mux, mup, dist_tcin_asym, m_s, m_s_schedule, q_co2, Y_NX, Y_NP, alpha_kla, vis_scale)
# 保留它只为一件事：`tools/r132_calib_merge_check.py` 能算出"合并前后差了多少"，
# 让这次改动可审计。任何生产路径都不得再读它。
CAL_LEGACY = {
    8:  (0.47, 0.041, 10, 0.029, None, 0.12, 10, 80, 90, 0.9),
    11: (0.41, 0.041, 10, 0.020, None, 0.11, 10, 80, 110, 0.9),
    16: (0.41, 0.041, 20, 0.025, None, 0.14, 25, 40, 75, 0.9),
    22: (0.35, 0.065, 20, 0.029, [(110, 0.010)], 0.12, 25, 40, 85, 1.0),
    23: (0.35, 0.070, 10, 0.029, None, 0.10, 15, 60, 110, 0.9),
    27: (0.35, 0.041, 15, 0.029, [(140, 0.018)], 0.12, 25, 40, 85, 0.9),
    36: (0.47, 0.045, 10, 0.010, None, 0.10, 20, 40, 130, 0.8),
    55: (0.47, 0.055, 20, 0.025, None, 0.11, 25, 40, 85, 1.0),
    60: (0.47, 0.035, 15, 0.010, None, 0.10, 20, 40, 85, 1.0),
    80: (0.35, 0.041, 18, 0.029, None, 0.13, 25, 40, 85, 0.9),
    51: (0.41, 0.041, 20, 0.029, None, 0.12, 25, 40, 85, 1.0),
    91: (0.39, 0.041, 10, 0.029, None, 0.12, 10, 60, 90, 1.0),
    92: (0.47, 0.041, 18, 0.029, [(150, 0.015)], 0.11, 12, 60, 130, 0.9),
}


def calib_params(b: int) -> dict:
    """批次 b 的完整参数 dict（可直接传 simulate_open_loop）。

    R132 起**逐字等于** `build_params(COMBINED[b])`，不掺任何覆盖——
    这是本次合并的核心约束：MCP / dashboard / observe / optimize 报出来的参数，
    必须与黄金回归用的参数是同一份，否则"引擎达标"与"服务对外口径"会各说各话。

    历史上的 PAA 覆盖（PAA_CAL）**不再自动生效**：它含 paa_maintenance_target=1，
    而 `model.rhs` 里该键直接决定 m_PAA 的维护目标是 total_X 还是 P（与 paa_gate_mode
    无关）。无差别注入会让 b92 产量从 +1.4% 跳到 +72.9%（实测，runs/p3/r132_mcp_path.json）。
    需要 PAA 门控模式的调用方请显式用 `paa_mode_params(b)`。

    未标定批抛 KeyError —— 调用方需自行决定回退（如 MCP 的 {"alpha_kla": 85.0}）。
    """
    if b not in COMBINED:
        raise KeyError(f"batch {b} not calibrated (not in golden_params.COMBINED)")
    return build_params(COMBINED[b])


def paa_mode_params(b: int) -> dict:
    """PAA 门控模式（paa_gate_mode=1/2）专用参数：基线 + 门控模式键。

    仅当调用方显式启用门控时才可用；默认路径请用 calib_params。
    """
    p = calib_params(b)
    for k, v in PAA_CAL.get(b, {}).items():
        if k in PAA_MODE_KEYS:
            p.setdefault(k, v)
    return p


def calib_params_legacy(b: int) -> dict:
    """R132 之前的口径，仅供合并审计对照（tools/r132_calib_merge_check.py）。"""
    if b not in CAL_LEGACY:
        raise KeyError(f"batch {b} not in CAL_LEGACY")
    mux, mup, dt, ms, sched, q_co2, y_nx, y_np, alpha_kla_cal, vis_scale_cal = CAL_LEGACY[b]
    p = {"mux": mux, "mup": mup, "alpha_kla": alpha_kla_cal, "PAA_c": 530000.0,
         "N_conc_paa": 150000.0, "c_oil": 1000.0,
         "dist_flag": 1, "dist_tcin_asym": dt, "m_s": ms,
         "q_co2": q_co2, "Y_NX": y_nx, "Y_NP": y_np, "vis_scale": vis_scale_cal}
    if sched:
        p["m_s_schedule"] = sched
    if b in PAA_CAL:
        p.update(PAA_CAL[b])
    return p


# ---------------------------------------------------------------- v0.2 候选算子
# PH2 残差发现 + P4 升级前探针（R44，runs/hier_est/p4_death_probe.json）：
# 死亡项后验修正 X_corr = max(X − (kd1·X + kd2·X·A_t1 + kd3·X·A_t1²)/100, 0) 在全部
# 10 个正常黄金批上改善 X 轨迹 nRMSE（Δ −3.3 ~ −23.9 pt）→ 支持引擎层升级。
# 设计（"只增不减"）：本算子默认**关闭**，调用方显式启用（如观测层 ensemble_smooth/
# 探针/未来 v0.2 验证器）；β 运行时从 runs/hier_est/death_term.json 读取 —
# 全池（88 批）重拟合后此文件无需改动。v0.1 的 calib_params/黄金回归路径零改动。

def load_death_beta():
    """PH2 死亡项 β（kd1,kd2,kd3）；缺失时返回 None（算子保持 v0.1 行为）。"""
    import json
    import os
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..",
                     "runs", "hier_est", "death_term.json")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    return (d["beta"][0], d["beta"][1], d["beta"][2])


def death_correct_X(sim_df, beta=None):
    """对 sim 记录表（simulate_open_loop 输出的 DataFrame）做死亡项后验 X 修正。
    A_t1 = A0/(A1+A3+A4)（model.py 培养龄比状态）；返回新列 X（不改动原 DataFrame）。
    参数：beta=(kd1,kd2,kd3)；None 时自动 load_death_beta()，仍缺则原样返回。"""
    import numpy as np
    import pandas as pd
    if beta is None:
        beta = load_death_beta()
    if beta is None:
        return sim_df["X"]
    kd1, kd2, kd3 = beta
    a0 = sim_df["A0"].to_numpy(float)
    a1 = sim_df["A1"].to_numpy(float)
    a3 = sim_df["A3"].to_numpy(float)
    a4 = sim_df["A4"].to_numpy(float)
    at1 = a0 / np.maximum(a1 + a3 + a4, 1e-9)
    X = sim_df["X"].to_numpy(float)
    corr = (kd1 * X + kd2 * X * at1 + kd3 * X * at1 ** 2) / 100.0
    return pd.Series(np.maximum(X - corr, 0.0), index=sim_df.index)
