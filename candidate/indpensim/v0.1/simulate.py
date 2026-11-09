# -*- coding: utf-8 -*-
"""IndPenSim 批次仿真引擎（M1/M3）：开环回放 + 校验。

对齐 MATLAB indpensim.m 的"采样-积分"两层结构：
  - 每 0.2h 采样区间用 BDF 积分（对齐 ode15s，rtol=1e-3/atol=1e-6）
  - 采样末守卫：states 1-31 (0-based 0-30) ≤0 → 0.001；DO2 <2 → 1
  - k>65 的 mux 自适应（indpensim.m lines 192-198）
  - 初始状态：V3 首行（t=0.2）外部状态 + MATLAB 标称内部状态
    （mup/mux=0、vis=4、A_t1=0、A0/A1=X0/3·2X0/3、液泡=0、CO2d=0）

输出通道对齐 V3：pH=-log10([H+])、Q/1000、OUR/CER 按 indpensim.m 尾气公式。

用法：
  python simulate.py --batch 1                 # 默认名义参数开环回放 + 对照
  python simulate.py --batch 1 --params '{"mux":0.42,"mup":0.040}'
"""
import argparse
import json
import os
import sys
import time
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
# scipy 优先用系统安装；tools/vendor 为源码副本（无编译扩展），仅在系统缺失时兜底
try:
    import scipy  # noqa: F401
except ImportError:
    _vendor = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "tools", "vendor"))
    if os.path.isdir(_vendor):
        sys.path.insert(0, _vendor)
from model import rhs, N_STATES, state_names
from params import make_params

H_SAMPLE = 0.2
H_ODE = 0.01  # h_ode = h/20

IDX = {name: i for i, name in enumerate(state_names())}
# R148 / D-34：守卫审计用（索引 → 状态名），供 classify_crash / 验收按状态报钳位
NAME_BY_IDX = {i: name for name, i in IDX.items()}

# V3 在线通道（对齐 data/processed/batches/batch_XX.csv）
V3_COLS = ["time_h", "Fg", "RPM", "Fs", "Fa", "Fb", "Fc", "Fh", "Fw", "pressure",
           "Fremoved", "S", "DO2", "P", "V", "Wt", "pH", "T", "Q", "CO2outgas",
           "Fpaa", "Foil", "NH3_shots", "OUR", "O2", "CER"]


_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..",
                                         "data", "processed", "batches"))


def load_batch(batch_no):
    """读 V3 批处理 CSV。

    先按当前工作目录的相对路径找（历史行为，逐位不变）；找不到再按**项目根**解析，
    这样从 `candidate/indpensim/v0.1/` 里直接跑 `validate.py` 也不会 FileNotFoundError。
    两者指向同一文件时不改变任何数值。
    """
    f = f"data/processed/batches/batch_{batch_no:02d}.csv"
    if os.path.exists(f):
        return pd.read_csv(f)
    return pd.read_csv(os.path.join(_DATA_DIR, f"batch_{batch_no:02d}.csv"))


def build_initial_state(d, x0_biomass=0.5, paa0=1400.0, nh30=1700.0, x0_force=False):
    """从 V3 首行构造 33 维初始状态（t=0.2）。

    X0（总初始生物量）估计：取首个非 NaN 的 X_offline（若可得），否则 0.5。
    x0_force=True 时强制使用 x0_biomass（绕过 X_offline）。
    """
    row = d.iloc[0]
    s = np.zeros(N_STATES)
    s[IDX["S"]] = float(row["S"])
    s[IDX["DO2"]] = float(row["DO2"])
    s[IDX["O2"]] = float(row["O2"])
    s[IDX["P"]] = float(row["P"])
    s[IDX["V"]] = float(row["V"])
    s[IDX["Wt"]] = float(row["Wt"])
    s[IDX["pH_H"]] = 10 ** (-float(row["pH"]))
    s[IDX["T"]] = float(row["T"])
    s[IDX["Q"]] = 0.001  # V3 导出 Q=1e-6 → 内部 0.001（守卫下限）
    s[IDX["vis"]] = 4.0  # MATLAB x00 固定 4 cP
    s[IDX["A_t1"]] = 0.0
    x0b = x0_biomass
    if not x0_force:
        xoff = pd.to_numeric(d["X_offline"], errors="coerce").dropna()
        if len(xoff) and 0.3 <= xoff.iloc[0] <= 0.8:
            x0b = float(xoff.iloc[0])
    s[IDX["A0"]] = x0b / 3.0
    s[IDX["A1"]] = x0b * 2.0 / 3.0
    s[IDX["A3"]] = 0.0
    s[IDX["A4"]] = 0.0
    # n0..n9, nm, phi0 = 0（液泡准稳态近似，见 model.py 注释）
    s[IDX["CO2"]] = float(row["CO2outgas"])
    s[IDX["CO2d"]] = 0.0
    paa_row = pd.to_numeric(d["PAA_offline"], errors="coerce").dropna()
    s[IDX["PAA"]] = float(paa_row.iloc[0]) if len(paa_row) else paa0
    nh3_row = pd.to_numeric(d["NH3_offline"], errors="coerce").dropna()
    s[IDX["NH3"]] = float(nh3_row.iloc[0]) if len(nh3_row) else nh30
    s[IDX["mup"]] = 0.0  # MATLAB x00 末两位为 0
    s[IDX["mux"]] = 0.0
    return s


def build_inp1(row, inhib=2, dist_flag=0, dist_mux=0.0, dist_mup=0.0,
               dist_cs=0.0, dist_coil=0.0, dist_abc=0.0, dist_paa=0.0,
               dist_tcin=0.0, dist_o2in=0.0):
    """从 V3 行构造 26 维输入向量（顺序对齐 indpensim.m u00）。"""
    return np.array([
        inhib,                       # 0: inhib_flag
        float(row["Fs"]),            # 1: Fs
        float(row["Fg"]),            # 2: Fg (m^3/h → ODE 内 /60)
        float(row["RPM"]),           # 3: RPM
        float(row["Fc"]),            # 4: Fc
        float(row["Fh"]),            # 5: Fh
        float(row["Fb"]),            # 6: Fb
        float(row["Fa"]),            # 7: Fa
        H_ODE,                       # 8: step1 (h_ode)
        float(row["Fw"]),            # 9: Fw
        float(row["pressure"]),      # 10: pressure
        0.0,                         # 11: viscosity (Vis=0 → 用 state)
        float(row["Fremoved"]),      # 12: F_discharge
        float(row["Fpaa"]),          # 13: Fpaa
        float(row["Foil"]),          # 14: Foil
        float(row["NH3_shots"]),     # 15: NH3_shots
        dist_flag,                   # 16: dist_flag
        dist_mup, dist_mux, dist_cs, dist_coil, dist_abc, dist_paa, dist_tcin, dist_o2in,  # 17-24: 扰动
        0.0,                         # 25: Vis flag
    ])


def guards(y, audit=None):
    """采样末守卫（对齐 indpensim.m lines 216-220 + 252-257）。

    audit：可选 list。传入时追加每条改写记录 `(索引, 改写前的值)`；DO2 兜底记为
    `("do2", 改写前的值)`。**纯旁路观测，不改变任何数值**——不传时与原实现逐位相同。
    用途（R148 / D-34）：把"pH 被钳到 3.0"从"靠 pH 阈值猜"变成"按状态索引直接数"。
    """
    y = y.copy()
    for i in range(31):  # states 0-30 (S..NH3)，不含 mup/mux
        if y[i] <= 0:
            if audit is not None:
                audit.append((i, float(y[i])))
            y[i] = 0.001
    if y[IDX["DO2"]] < 2:
        if audit is not None:
            audit.append(("do2", float(y[IDX["DO2"]])))
        y[IDX["DO2"]] = 1.0
    return y


def integrate_interval(t0, y0, inp1, par, paa_gate_mode=0, paa_gate_floor=0.0, paa_maintenance_target=0, paa_degrad_rate=0.0, paa_degrad_inverse_gate=False, fault_type=0, fault_start=0.0, fault_end=0.0, fault_magnitude=0.0, fault_profile=None, biomass_death_rate=0.0, death_start=0.0, vis_scale=1.0, k_vac=0.0, death_recycle=0.0, mu_vac_ref=0.1, late_death_rate=0.0, mu_death_ref=0.02,
                vis_k3=None, vis_k1=None, vis_k2=None, vis_t1=None, vis_t2=None,
                vis_decay_rate=0.0, p_deg_rate=0.0,
                ode_method="BDF", ode_rtol=1e-3, ode_atol=1e-6, ode_max_step=None,
                death_mode=0, age_rate=0.0, lysis_rate=0.0, lysis_recycle=0.0, age_mu_ref=0.02,
                age_start=None, ph_hyd_acid=False, ph_rp_mode="net",
                mu_p_growth=0.0, ph_fix=0):
    """BDF 积分一个采样区间 [t0, t0+H_SAMPLE]（对齐 ode15s）。

    paa_gate_mode: D9(b) PAA 相门控模式（0=off, 1=gate X_1, 2=gate X_1+dP_dt）。
    paa_gate_floor: 门控下限（0.0=完全抑制, 0.1~0.3=部分抑制）。
    paa_maintenance_target: m_PAA 维护消耗目标（0=P, 1=total_X）。
    paa_degrad_rate: 一阶 PAA 降解速率（0.0=off, >0=启用）。
    paa_degrad_inverse_gate: 反相门控降解（False=恒定, True=仅门控关闭时）。
    fault_type: D4 故障注入类型（0=none, 1=oxygen_limit, 2=ph_perturb, 3=feed_reduce）。
    fault_start/end: 故障时间窗（小时）。
    fault_magnitude: 故障强度。
    fault_profile: R157 / T3-2 模式级注入的时间包络 [(t_h, rel_amp), ...]；None ⇒ 逐位不变。
    biomass_death_rate: ODE 级生物量衰亡速率（R129, 0.0=off 默认）。
    k_vac: 液泡化速率（R130, A1→A3 转移, 0.0=off 默认）。
    death_recycle: 衰亡底物回收比例（R130, 死菌丝自溶回 S, 0.0=off 默认）。
    mu_vac_ref: 液泡化生长速率阈值（R130, μ_actual < 此值时液泡化启动, 0.1 h⁻¹ 默认）。
    late_death_rate: 晚期衰亡速率（R130b, 生长率低于阈值时衰亡, 0.0=off 默认）。
    mu_death_ref: 衰亡生长率阈值（R130b, μ_actual < 此值时衰亡启动, 0.02 h⁻¹ 默认）。
    death_mode / age_rate / lysis_rate / lysis_recycle / age_mu_ref: 形态学衰亡链（R141, D-8）。
        death_mode=0（默认）走现行等比移除，逐位不变；=1 时 A1 按 age_rate 老化进 A3
        （X 内转移），A3/A4 按 lysis_rate 溶菌出系统并按 lysis_recycle 回收底物。
    vis_k3/vis_k1/vis_k2/vis_t1/vis_t2: 黏度分支参数的批级覆盖（R133, None=沿用 par）。
    vis_decay_rate: 黏度一阶松弛速率（R133, 0.0=off 默认, 与 MATLAB 原文一致）。
    ode_method / ode_rtol / ode_atol / ode_max_step: 积分器配置（R134 T5）。
        默认 BDF + rtol 1e-3 + atol 1e-6 + max_step H_ODE，与 R129–R133 完全一致；
        仅供"分岔真伪"判定的多求解器对照使用，不改默认即零回归。
    """
    from scipy.integrate import solve_ivp

    def f(t, y):
        return rhs(t, y, inp1, par, paa_gate_mode=paa_gate_mode,
                   paa_gate_floor=paa_gate_floor, paa_maintenance_target=paa_maintenance_target,
                   paa_degrad_rate=paa_degrad_rate, paa_degrad_inverse_gate=paa_degrad_inverse_gate,
                   fault_type=fault_type, fault_start=fault_start, fault_end=fault_end, fault_magnitude=fault_magnitude, fault_profile=fault_profile,
                   biomass_death_rate=biomass_death_rate, death_start=death_start, vis_scale=vis_scale, p_deg_rate=p_deg_rate,
                   k_vac=k_vac, death_recycle=death_recycle, mu_vac_ref=mu_vac_ref,
                   late_death_rate=late_death_rate, mu_death_ref=mu_death_ref,
                   death_mode=death_mode, age_rate=age_rate, lysis_rate=lysis_rate,
                   lysis_recycle=lysis_recycle, age_mu_ref=age_mu_ref, age_start=age_start,
                   ph_hyd_acid=ph_hyd_acid, ph_rp_mode=ph_rp_mode,
                   vis_k3=vis_k3, vis_k1=vis_k1, vis_k2=vis_k2, vis_t1=vis_t1, vis_t2=vis_t2,
                   vis_decay_rate=vis_decay_rate, mu_p_growth=mu_p_growth,
                   ph_fix=ph_fix)

    t_end = t0 + H_SAMPLE
    sol = solve_ivp(f, [t0, t_end], y0, method=ode_method,
                    rtol=ode_rtol, atol=ode_atol,
                    max_step=H_ODE if ode_max_step is None else ode_max_step)
    if not sol.success:
        raise RuntimeError(f"{ode_method} failed at t={t0}: {sol.message}")
    return sol.y[:, -1]


def compute_our_cer(fg, o2, co2):
    """按 indpensim.m lines 333-339 计算 OUR/CER 导出通道。"""
    o2_in = 0.204
    our = (32.0 * fg / 22.4) * (o2_in - o2 * (0.7902 / (1.0 - o2 - co2 / 100.0)))
    cer = (44.0 * fg / 22.4) * ((0.65 * co2 / 100.0)
                                * (0.7902 / (1.0 - o2_in - co2 / 100.0) - 0.0330))
    return our, cer


def simulate_open_loop(batch_no, params=None, inhib=2, x0_biomass=None):
    """开环回放仿真：V3 被控量序列驱动 ODE。返回 (sim_df, v3_df)。

    扰动通道支持时变：dist_*_asym 为渐近值，dist(t) = asym * (1 - exp(-t/tau))
    （tau = 40h ≈ 1/0.005 EMA 时间常数，对齐 MATLAB filter(b1,a1,scale*v)）。
    """
    params = params or {}
    par = make_params(
        alpha_kla=params.get("alpha_kla", 85.0),
        N_conc_paa=params.get("N_conc_paa", 150000.0),
        PAA_c=params.get("PAA_c", 530000.0),
        mup=params.get("mup", 0.041),
        mux=params.get("mux", 0.41),
        c_oil=params.get("c_oil", 1000.0),
    )
    if "Tcin" in params:
        par[48] = params["Tcin"]
    if "m_s" in params:
        par[24] = params["m_s"]
    if "m_paa" in params:
        par[77] = params["m_paa"]
    if "Y_PAA_P" in params:
        par[75] = params["Y_PAA_P"]
    if "Y_PAA_X" in params:
        par[76] = params["Y_PAA_X"]
    if "q_co2" in params:
        par[91] = params["q_co2"]
    if "c_co2_in" in params:
        par[101] = params["c_co2_in"]
    if "Y_NX" in params:
        par[70] = params["Y_NX"]
    if "Y_NP" in params:
        par[71] = params["Y_NP"]
    if "N_conc_oil" in params:
        par[67] = params["N_conc_oil"]
    if "Y_O2_X" in params:
        par[27] = params["Y_O2_X"]
    if "Y_O2_P" in params:
        par[28] = params["Y_O2_P"]
    if "m_O2_X" in params:
        par[29] = params["m_O2_X"]
    if "mu_h" in params:
        par[19] = params["mu_h"]
    if "mu_h_scale" in params:
        par[18] = params["mu_h_scale"]
    if "Y_sX" in params:
        par[22] = params["Y_sX"]
    # R136：产品对底物的消耗系数（g 底物 / g 产品）。默认 0.9 不变；仅在传入时覆盖，
    # 用于检验"底物在菌体/产物之间再分配"能否同时满足 X 与 P 两个观测（见 docs/r136_round_report.md）
    if "Y_sP" in params:
        par[23] = params["Y_sP"]
    # R146 / D-35：pH 方程三个系数（par[62]/[63]/[64]）的批级覆盖。
    # 在 model.py 中 gamma1/gamma2/m_ph **只出现在 dy[6]**（见 model.py:187-189 与 533-548），
    # 故改它们只经 pH 反馈影响产量——这正是 D-35「pH 偏差与产量标定耦合」的可辨识性结构。
    # 只在传入时覆盖 ⇒ 默认路径逐位不变（零回归）。
    if "gamma1" in params:
        par[62] = params["gamma1"]
    if "gamma2" in params:
        par[63] = params["gamma2"]
    if "m_ph" in params:
        par[64] = params["m_ph"]
    # R149 / D-39：缓冲容量 `abc`（par[61]，基线 0.033）的批级覆盖。
    # 动机：pH 振幅是实测的 4-6 倍；但 R149 上扫实测证明 γ1 增大只让峰谷**同向平移**，
    # 不压缩振幅（b22 0.613->0.819、b23 0.417->0.609），故"产酸增益"不是振幅旋钮。
    # 电荷平衡里能压缩振幅的是 buffer 项 `abc*(Fa-Fb)*step1`（加碱的中和能力）。
    # `abc` 在 model.py 只进 dy[6] 的 buffer 项（199/288/535-544 行），
    # 与 γ1 同属"只经 pH 反馈影响产量"的干净通道。默认不传 ⇒ par[61] 不变 ⇒ 逐位一致。
    if "abc" in params:
        par[61] = params["abc"]

    # R152 / D-42：产素门控的三个参数覆盖口，全部默认不传 => 逐位不变。
    #   P_inhib = 2.5/sqrt(2*pi)*exp(-0.5*((s - mean_P)/P_std_dev)^2)
    #   `mean_P` 门控中心（par[4]=0.002 g/L）；`P_std_dev` 门控宽度（par[3]=1.5e-3 g/L）。
    #   注意 par[5] 是 mu_v=1.71e-4，**不是** P_std_dev（R152 首版按相邻行推断踩过这个坑）。
    #   宽度 1.5 mg/L 与 S 的量级（1-5 mg/L）相当 => 门控是平滑窗，不是硬开关。
    #   `P_crit_PAA`（par[79]=200 mg/L）是 PAA 门控阈值，实测 PAA ~1400 mg/L 已使 tanh 饱和。
    if "mean_P" in params:
        par[4] = params["mean_P"]
    if "P_std_dev" in params:
        par[3] = params["P_std_dev"]
    if "P_crit_PAA" in params:
        par[79] = params["P_crit_PAA"]
    # 时变 m_s 调度：list of (t_switch, m_s_value) pairs
    m_s_schedule = params.get("m_s_schedule", None)
    if m_s_schedule is not None:
        m_s_idx = 0  # 当前调度索引
        m_s_current = par[24]  # 当前 m_s 值
    d = load_batch(batch_no)
    # C 档寻优用：MV 缩放（把 V3 参考配方按倍率重放）
    mv_scales = params.get("mv_scales") or {}
    mv_warnings = []
    if mv_scales:
        # 有效域守卫（I2）：倍率越出已验证域 [0.90, 1.25] 显式告警不拦截；
        # 已知分岔证据：批 8Fs×0.97+ 触发双稳态崩塌（PROBLEM.md §13.2）
        VALID_LO, VALID_HI = 0.90, 1.25
        for k, v in mv_scales.items():
            if not (VALID_LO <= float(v) <= VALID_HI):
                mv_warnings.append(f"mv_scales[{k}]={v:.3f} 越出验证域 [{VALID_LO}, {VALID_HI}]")
        d = d.copy()
        for col, k in mv_scales.items():
            if col in d.columns and float(k) != 1.0:
                d[col] = d[col].astype(float) * float(k)
                if col in ("Fs", "Fg", "RPM", "Fremoved"):
                    d[col] = d[col].clip(lower=0.0)
    # PH4 滚动控制用：时间窗 MV 倍率 [{t0, t1, scales:{col:k}}, ...]（t 仅缩放窗内行）
    mv_window_scales = params.get("mv_window_scales") or []
    if mv_window_scales:
        d = d.copy()
        t_arr = d["time_h"].to_numpy(float)
        for wnd in mv_window_scales:
            t0w, t1w = float(wnd["t0"]), float(wnd["t1"])
            msk = (t_arr >= t0w) & (t_arr < t1w)
            for col, k in (wnd.get("scales") or {}).items():
                if col in d.columns:
                    d.loc[msk, col] = d.loc[msk, col].astype(float) * float(k)
                    if col in ("Fs", "Fg", "RPM", "Fremoved"):
                        d.loc[msk, col] = d.loc[msk, col].clip(lower=0.0)
    x0b = x0_biomass if x0_biomass is not None else params.get("x0_biomass")
    y = build_initial_state(d, x0_biomass=x0b, x0_force=params.get("x0_force", False))
    t_current = float(d.iloc[0]["time_h"])

    # D9(b) PAA 相门控模式（R121 根因修复）
    paa_gate_mode = params.get("paa_gate_mode", 0)
    paa_gate_floor = params.get("paa_gate_floor", 0.0)
    paa_maintenance_target = params.get("paa_maintenance_target", 0)
    paa_degrad_rate = params.get("paa_degrad_rate", 0.0)
    paa_degrad_inverse_gate = params.get("paa_degrad_inverse_gate", False)
    # D4 故障注入参数（V1+）
    fault_type = params.get("fault_type", 0)
    fault_start = params.get("fault_start", 0.0)
    fault_end = params.get("fault_end", 0.0)
    fault_magnitude = params.get("fault_magnitude", 0.0)
    # R157 / T3-2：模式级注入的时间包络（默认 None ⇒ 逐位不变）
    fault_profile = params.get("fault_profile", None)
    biomass_death_rate = params.get("biomass_death_rate", 0.0)
    p_deg_rate = params.get("p_deg_rate", 0.0)
    death_start = params.get("death_start", 0.0)
    vis_scale = params.get("vis_scale", 1.0)
    k_vac = params.get("k_vac", 0.0)
    death_recycle = params.get("death_recycle", 0.0)
    mu_vac_ref = params.get("mu_vac_ref", 0.1)
    late_death_rate = params.get("late_death_rate", 0.0)
    mu_death_ref = params.get("mu_death_ref", 0.02)
    # R141 形态学衰亡链（D-8）：默认 death_mode=0 → 与历史逐位一致
    death_mode = params.get("death_mode", 0)
    age_rate = params.get("age_rate", 0.0)
    lysis_rate = params.get("lysis_rate", 0.0)
    lysis_recycle = params.get("lysis_recycle", 0.0)
    age_mu_ref = params.get("age_mu_ref", 0.02)
    age_start = params.get("age_start")
    if age_start is not None:
        age_start = float(age_start)
    # R145 / D-32：产品水解通道在 pH 方程里的酸碱符号（默认 False = 与 MATLAB 逐字一致）
    ph_hyd_acid = bool(params.get("ph_hyd_acid", False))
    # R147 / D-36：pH 方程里 r_p 的口径。"net"（默认，逐位不变）/ "prod_only" / "all_acid"
    ph_rp_mode = str(params.get("ph_rp_mode", "net"))
    # R153 / D-48：生长耦合产素系数 α（默认 0.0 ⇒ 逐位不变）
    mu_p_growth = float(params.get("mu_p_growth", 0.0))
    # R156 / D-55：pH basic 分支链式法则修正（0=逐字原文，1=修正；见 model.py）
    ph_fix = int(params.get("ph_fix", 0))
    # R145 / D-32：pH 通道模式。"model"=按 ODE 预测（默认，逐位不变）；
    # "measured"=每采样点用实测 pH 覆盖 [H+] 状态（pH 降级为输入，见 simulate 内注释）。
    ph_mode = params.get("ph_mode", "model")
    # R133 黏度分支批级覆盖
    vis_k3 = params.get("vis_k3")
    vis_k1 = params.get("vis_k1")
    vis_k2 = params.get("vis_k2")
    vis_t1 = params.get("vis_t1")
    vis_t2 = params.get("vis_t2")
    vis_decay_rate = params.get("vis_decay_rate", 0.0)
    # R133：黏度**上报口径**换算系数。只乘在输出列上，ODE 内部（进 kla 的 y[9]）不变，
    # 因此对产量零影响。与 vis_scale（乘生成项、经 kla 反馈产量）有本质区别。
    vis_out_scale = params.get("vis_out_scale", 1.0)

    # R134 T5：积分器配置（默认值与 R129–R133 逐位一致 → 零回归）
    ode_method = params.get("ode_method", "BDF")
    ode_rtol = params.get("ode_rtol", 1e-3)
    ode_atol = params.get("ode_atol", 1e-6)
    ode_max_step = params.get("ode_max_step", None)

    # 时变扰动参数
    dist_flag = params.get("dist_flag", 0)
    dist_tau = params.get("dist_tau", 40.0)  # EMA 时间常数 (h)

    # ---- R166 / D-83：8 路统计等价方差注入（opt-in，默认 None ⇒ 逐位不变）----
    # 依据 runs/r163_dist_variance.json：MATLAB filter(b1=0.005, a1=[1,-0.995])
    # 的低通时间常数 τ=40 h 已由 dist_tau 对齐，缺的只是方差成分。
    # **明确边界**：这是统计等价注入，**不是 MATLAB 逐位复现** —— R162 oq#36
    # 已证 rng('shuffle') 种子未记录且算法不同 ⇒ 逐位对齐原理上不可达。
    # 通道顺序对应下方 d_mux/d_mup/d_cs/d_coil/d_abc/d_paa/d_tcin/d_o2in。
    dist_noise_sigma = params.get("dist_noise_sigma", None)
    _noise_rng = None
    _noise_state = None
    _sigma_n = None
    if dist_noise_sigma is not None:
        _noise_chans = ("mux", "mup", "cs", "coil", "abc", "paa", "tcin", "o2in")
        _sigma_n = np.array([float(dist_noise_sigma.get(c, 0.0))
                             for c in _noise_chans], float)
        _noise_rng = np.random.default_rng(int(params.get("dist_noise_seed", 7)))
        _noise_state = np.zeros(8, float)

    # 扰动渐近值（从 dist_* 读取，支持 *_asym 时变模式）
    d_mux_asym = params.get("dist_mux_asym", params.get("dist_mux", 0.0))
    d_mup_asym = params.get("dist_mup_asym", params.get("dist_mup", 0.0))
    d_cs_asym = params.get("dist_cs_asym", params.get("dist_cs", 0.0))
    d_coil_asym = params.get("dist_coil_asym", params.get("dist_coil", 0.0))
    d_abc_asym = params.get("dist_abc_asym", params.get("dist_abc", 0.0))
    d_paa_asym = params.get("dist_paa_asym", params.get("dist_paa", 0.0))
    d_tcin_asym = params.get("dist_tcin_asym", params.get("dist_tcin", 0.0))
    d_o2in_asym = params.get("dist_o2in_asym", params.get("dist_o2in", 0.0))

    # ---- R155 / D-54：葡萄糖补料闭环（opt-in；不传 fs_ctl ⇒ 完全走原路径）----
    # 依据 R154：实测 Fs 是 recipe 剖面，开环回放它意味着模型一旦偏离就没有回拉机制，
    # 而 P_inhib 是中心 2 mg/L、半宽 1.5 mg/L 的高斯门控 ⇒ 偏离被放大成"全开/全关"（D-52）。
    # 该模式在回放剖面之外叠加一个糖反馈修正因子：
    #   e   = (S - sp) / scale
    #   I'  = e * w,   w = 1/(1+(S/s_act)^2)（s_act=0 时 w≡1，全域闭环）
    #   u   = clip(1 - w*(kp*e + ki*I), u_lo, u_hi)
    #   Fs  = Fs_rec * u
    # u ≡ 1 时与开环逐位相同；闭环与否只看 fs_ctl 是否为 None。
    fs_ctl = params.get("fs_ctl", None)
    if fs_ctl is not None:
        fs_sp = float(fs_ctl.get("sp", 0.002))
        fs_scale = float(fs_ctl.get("scale", fs_sp))
        fs_kp = float(fs_ctl.get("kp", 0.0))
        fs_ki = float(fs_ctl.get("ki", 0.0))
        fs_u_lo = float(fs_ctl.get("u_lo", 0.0))
        fs_u_hi = float(fs_ctl.get("u_hi", 2.0))
        fs_i_clip = float(fs_ctl.get("i_clip", 50.0))
        fs_s_act = float(fs_ctl.get("s_act", 0.0))
        fs_t_on = float(fs_ctl.get("t_on", 0.0))
        fs_t_off = float(fs_ctl.get("t_off", 1e9))
        fs_i = float(fs_ctl.get("i0", 0.0))
        fs_trace = []
        _u_last = 1.0
    # ---- R155 / D-41 L1：pH 高位停止/回撤加碱（opt-in；不传 fb_limit ⇒ 逐位不变）----
    # 依据 R149：pH 越 7 不可逆的根因是**回放的 Fb 没有限幅** —— 记录值是控制器对
    # 实测 pH 6.50 的输出，模型 pH 已偏离时它照加不误。L1 装置：pH ≥ ph_stop 时
    # 停碱（step），或按 (ph_stop - pH)/width 线性回撤（linear）。
    fb_limit = params.get("fb_limit", None)
    if fb_limit is not None:
        fb_stop = float(fb_limit.get("ph_stop", 6.90))
        fb_width = float(fb_limit.get("width", 0.10))
        fb_mode = str(fb_limit.get("mode", "step"))
        fb_trace = []
    _e_last = 0.0
    _u_last = 1.0
    records = []
    mux_hist = []  # mu_X 状态历史（用于 k>65 自适应）
    # R148 / D-34：守卫审计（按状态索引累计被改写的步数）。纯旁路，不影响数值。
    _guard_tally = {}
    _guard_tally_first = {}   # 第 1 步单独记：初值（A3/A4/n*/phi0 的零初值）天然触发，非崩溃信号
    _guard_n_steps = 0
    _ph_nonpos_steps = 0

    # ---- R140 闭环数据同化（默认 None = 完全走原路径，零回归）----
    # 在每 assimilate["dt"] 小时用 R139 v2 双通道观测器估计 X，把菌丝形态状态按比例校正后
    # 继续积分。p/q 取 R139 交付值（0.599 / 0.713），gate 为批级标度不可辨识阈值。
    assimilate = params.get("assimilate", None)
    if assimilate is not None:
        assim_dt = float(assimilate.get("dt", 12.0))
        assim_warm = float(assimilate.get("warmup", 24.0))
        assim_p = float(assimilate.get("p", 0.599))
        assim_q = float(assimilate.get("q", 0.713))
        assim_gate = float(assimilate.get("gate", 0.45))
        assim_next_t = assim_warm
        assim_lr_our, assim_lr_cer, assim_log = [], [], []
        _t_v3 = d["time_h"].to_numpy(float)
        _our_o = pd.to_numeric(d["OUR"], errors="coerce").to_numpy(float)
        _cer_o = pd.to_numeric(d["CER"], errors="coerce").to_numpy(float)
    k = 1  # 当前样本序号（V3 首行 = k=1）
    # MATLAB f_input 使用 forward-looking MVs：t_current 行的 MV 驱动 [t_current, t_sample]
    # sim 原来用 backward-looking（t_sample 行的 MV 驱动 [t_current, t_sample]），
    # 在 Fs/Fg 递增切换时多输入底物 → 系统偏差。改为 forward-looking 对齐 MATLAB。
    mv_row = d.iloc[0]  # 当前驱动区间使用的 MV 行（初始 = 首行）
    for i in range(1, len(d)):
        row = d.iloc[i]
        t_sample = float(row["time_h"])
        if t_sample <= t_current:
            continue
        k += 1  # 本行驱动区间 [t_current, t_sample]，对应 MATLAB 样本 k
        # k>65 mux 自适应（indpensim.m lines 192-198）
        if k > 65 and len(mux_hist) >= 65:
            recent = np.array(mux_hist[-65:])
            diffs = np.diff(recent)
            if np.sum(diffs < 0) >= 63:
                par[1] = 5.0 * recent[-1]  # p(2) = mu_X(k-1)*5

        # 时变扰动：dist(t) = asym * (1 - exp(-t/tau))
        if dist_flag and t_current > 0:
            growth = 1.0 - np.exp(-t_current / dist_tau)
            d_mux = d_mux_asym * growth
            d_mup = d_mup_asym * growth
            d_cs = d_cs_asym * growth
            d_coil = d_coil_asym * growth
            d_abc = d_abc_asym * growth
            d_paa = d_paa_asym * growth
            d_tcin = d_tcin_asym * growth
            d_o2in = d_o2in_asym * growth
        else:
            d_mux = d_mux_asym
            d_mup = d_mup_asym
            d_cs = d_cs_asym
            d_coil = d_coil_asym
            d_abc = d_abc_asym
            d_paa = d_paa_asym
            d_tcin = d_tcin_asym
            d_o2in = d_o2in_asym

        # ---- R166 / D-83：统计等价方差注入（默认 None ⇒ 上方分支逐位不变）----
        # AR(1) 低通：state = a·state + σ·sqrt(1−a²)·v，a = exp(−Δt/τ)
        # ⇒ 稳态标准差恰为 σ（取 runs/r163_dist_variance.json 的 analytic_sigma），
        # 时间常数 τ 与 dist_tau 一致。固定 seed ⇒ 完全可复现。
        if dist_noise_sigma is not None:
            _dt_n = max(float(t_sample) - float(t_current), 1e-9)
            _a_n = float(np.exp(-_dt_n / dist_tau))
            _noise_state = (_a_n * _noise_state
                            + _sigma_n * np.sqrt(1.0 - _a_n * _a_n)
                            * _noise_rng.standard_normal(8))
            d_mux += _noise_state[0]
            d_mup += _noise_state[1]
            d_cs += _noise_state[2]
            d_coil += _noise_state[3]
            d_abc += _noise_state[4]
            d_paa += _noise_state[5]
            d_tcin += _noise_state[6]
            d_o2in += _noise_state[7]

        # 时变 m_s：在积分前检查是否跨过切换点
        if m_s_schedule is not None:
            while m_s_idx < len(m_s_schedule) and t_current >= m_s_schedule[m_s_idx][0]:
                m_s_current = m_s_schedule[m_s_idx][1]
                par[24] = m_s_current
                m_s_idx += 1

        # ---- R140 闭环同化：到观测时刻就校正菌丝形态（A0/A1/A3/A4 等比缩放）----
        if assimilate is not None and t_current + 1e-9 >= assim_next_t and len(records) >= 2:
            tm = records[-1]
            o_obs = float(np.interp(t_current, _t_v3, _our_o))
            c_obs = float(np.interp(t_current, _t_v3, _cer_o))
            if o_obs > 0 and c_obs > 0 and tm["OUR"] > 0 and tm["CER"] > 0:
                lr_o = float(np.log(np.clip(o_obs / tm["OUR"], 0.5, 2.0)))
                lr_c = float(np.log(np.clip(c_obs / tm["CER"], 0.5, 2.0)))
                mo = float(np.mean(assim_lr_our + [lr_o]))       # 批级标度（截至当前）
                mc = float(np.mean(assim_lr_cer)) if assim_lr_cer else 0.0   # 历史均值（不含当前）
                assim_lr_our.append(lr_o)
                assim_lr_cer.append(lr_c)
                if abs(mo) > assim_gate:
                    assim_log.append({"t": float(t_current), "k": 1.0, "gated": True, "mo": mo})
                else:
                    k_hat = float(np.exp(assim_p * mo + assim_q * (lr_c - mc)))
                    # 限幅：单步校正不得超出 [lo,hi]。无约束时 X 骤缩会让 PAA 相对过量
                    # 积累、触发抑制，把 P 推崩（b16/b51 实测产量 −99.9%）。
                    k_lo = float(assimilate.get("k_lo", 1.0))
                    k_hi = float(assimilate.get("k_hi", 1.0))
                    if k_lo < k_hi:
                        k_hat = float(np.clip(k_hat, k_lo, k_hi))
                    X_mod = y[IDX["A0"]] + y[IDX["A1"]] + y[IDX["A3"]] + y[IDX["A4"]]
                    if X_mod > 1e-9:
                        for _nm in ("A0", "A1", "A3", "A4"):
                            y[IDX[_nm]] *= k_hat
                    assim_log.append({"t": float(t_current), "k": k_hat, "gated": False, "mo": mo})
            assim_next_t += assim_dt

        inp1 = build_inp1(mv_row, inhib=inhib,
                           dist_flag=dist_flag,
                           dist_mux=d_mux,
                           dist_mup=d_mup,
                           dist_cs=d_cs,
                           dist_coil=d_coil,
                           dist_abc=d_abc,
                           dist_paa=d_paa,
                           dist_tcin=d_tcin,
                           dist_o2in=d_o2in)
        # R155 / D-41 L1：pH 高位限碱（只改 inp1[6]，不动其他输入）
        if fb_limit is not None:
            _ph_now = -np.log10(max(float(y[IDX["pH_H"]]), 1e-15))
            if fb_mode == "linear":
                _g_b = float(np.clip((fb_stop - _ph_now) / max(fb_width, 1e-9), 0.0, 1.0))
            else:
                _g_b = 0.0 if _ph_now >= fb_stop else 1.0
            inp1[6] = float(inp1[6]) * _g_b
            fb_trace.append({"t": float(t_current), "ph": _ph_now, "g": _g_b,
                             "Fb_rec": float(mv_row["Fb"]), "Fb_used": float(inp1[6])})
        # R155 / D-54：闭环修正进料（在 build_inp1 之后、积分之前，只改 Fs 分量）
        # 时间窗外 u ≡ 1 ⇒ 与开环逐位相同（便于"只修 0–60 h"这类定点干预）。
        if fs_ctl is not None and fs_t_on <= t_current < fs_t_off:
            _dt_c = max(float(t_sample) - float(t_current), 1e-9)
            _s_now = float(y[IDX["S"]])
            _e_c = (_s_now - fs_sp) / fs_scale
            _w_c = 1.0 / (1.0 + (_s_now / fs_s_act) ** 2) if fs_s_act > 0.0 else 1.0
            fs_i = float(np.clip(fs_i + _e_c * _dt_c * _w_c, -fs_i_clip, fs_i_clip))
            _u_c = float(np.clip(1.0 - _w_c * (fs_kp * _e_c + fs_ki * fs_i), fs_u_lo, fs_u_hi))
            inp1[1] = float(inp1[1]) * _u_c
            _u_last = _u_c
            _e_last = _e_c
            fs_trace.append({"t": float(t_current), "S": _s_now, "e": _e_c,
                             "u": _u_c, "Fs_rec": float(mv_row["Fs"]),
                             "Fs_used": float(inp1[1])})
        elif fs_ctl is not None:
            _u_last = 1.0
        y = integrate_interval(t_current, y, inp1, par, paa_gate_mode=paa_gate_mode, paa_gate_floor=paa_gate_floor, paa_maintenance_target=paa_maintenance_target, paa_degrad_rate=paa_degrad_rate, paa_degrad_inverse_gate=paa_degrad_inverse_gate, fault_type=fault_type, fault_start=fault_start, fault_end=fault_end, fault_magnitude=fault_magnitude, fault_profile=fault_profile, biomass_death_rate=biomass_death_rate, death_start=death_start, vis_scale=vis_scale, p_deg_rate=p_deg_rate, k_vac=k_vac, death_recycle=death_recycle, mu_vac_ref=mu_vac_ref, late_death_rate=late_death_rate, mu_death_ref=mu_death_ref, vis_k3=vis_k3, vis_k1=vis_k1, vis_k2=vis_k2, vis_t1=vis_t1, vis_t2=vis_t2, vis_decay_rate=vis_decay_rate, death_mode=death_mode, age_rate=age_rate, lysis_rate=lysis_rate, lysis_recycle=lysis_recycle, age_mu_ref=age_mu_ref, age_start=age_start, ph_hyd_acid=ph_hyd_acid, ph_rp_mode=ph_rp_mode, mu_p_growth=mu_p_growth, ph_fix=ph_fix,
            ode_method=ode_method, ode_rtol=ode_rtol, ode_atol=ode_atol, ode_max_step=ode_max_step)
        # R148 / D-34：守卫前 pH（模型"想说"的值）。y[6] ≤ 0 时记 NaN，不伪造 pH。
        _y6_pre = float(y[IDX["pH_H"]])
        ph_pre = (-np.log10(_y6_pre)) if _y6_pre > 0 else float("nan")
        _audit = []
        y = guards(y, audit=_audit)
        _guard_n_steps += 1
        if _y6_pre <= 0:
            _ph_nonpos_steps += 1
        # 注意别名陷阱：step>1 时若写成 `_tgt = _guard_tally` 再对两者各 +1，
        # 会把同一次改写记两遍（R148 实测 tally 翻倍）。首步单独记必须显式分支。
        _is_first = (_guard_n_steps == 1)
        for _hit in _audit:
            if isinstance(_hit[0], str):
                _k = "DO2_floor"
            else:
                _k = NAME_BY_IDX.get(_hit[0], f"idx{_hit[0]}")
            _guard_tally[_k] = _guard_tally.get(_k, 0) + 1
            if _is_first:
                _guard_tally_first[_k] = _guard_tally_first.get(_k, 0) + 1
        # R145 / D-32 反事实：pH 按**实测**回放（ph_mode="measured"，默认 "model" 逐位不变）。
        # 依据：pH 是受控变量，Fa/Fb 是控制器的输出而非独立激励；开环回放控制器输出，
        # 会把控制器的跟踪误差写进 pH 状态，使 pH 越出数据从未到过的区间（见 r145 报告）。
        # 该模式下 pH 不再是"预测"，而是与 Fs/Fb 同级的**输入**；
        # 报告时不得再以 pH RMSE 作为模型能力证据。
        ph_openloop = float(-np.log10(max(y[IDX["pH_H"]], 1e-15)))  # 回放前的开环 pH（诊断用）
        if ph_mode == "measured":
            ph_meas = float(row["pH"])
            if np.isfinite(ph_meas) and 0.0 < ph_meas < 14.0:
                y[IDX["pH_H"]] = 10.0 ** (-ph_meas)
        t_current = t_sample
        mv_row = row  # 下一段用当前行的 MV
        mux_hist.append(float(y[IDX["mux"]]))  # state variable (matches MATLAB X.mu_X_calc.y = y_sol(end,33))
        fg = float(row["Fg"])
        our, cer = compute_our_cer(fg, float(y[IDX["O2"]]), float(y[IDX["CO2"]]))
        rec = {
            "time_h": t_sample,
            "Fg": fg, "RPM": float(row["RPM"]), "Fs": float(row["Fs"]),
            "Fa": float(row["Fa"]), "Fb": float(row["Fb"]), "Fc": float(row["Fc"]),
            "Fh": float(row["Fh"]), "Fw": float(row["Fw"]),
            "pressure": float(row["pressure"]), "Fremoved": float(row["Fremoved"]),
            "S": y[IDX["S"]], "DO2": y[IDX["DO2"]], "P": y[IDX["P"]],
            "V": y[IDX["V"]], "Wt": y[IDX["Wt"]],
            "pH": -np.log10(max(y[IDX["pH_H"]], 1e-15)),
            "pH_openloop": ph_openloop,
            "pH_pre": ph_pre,  # R148：守卫**前**的开环 pH（NaN = 解出 y[6] ≤ 0）
            "T": y[IDX["T"]], "Q": y[IDX["Q"]] / 1000.0,
            "CO2outgas": y[IDX["CO2"]], "CO2d": y[IDX["CO2d"]], "Fpaa": float(row["Fpaa"]),
            "Foil": float(row["Foil"]), "NH3_shots": float(row["NH3_shots"]),
            "OUR": our, "O2": y[IDX["O2"]], "CER": cer,
            "PAA": y[IDX["PAA"]], "NH3": y[IDX["NH3"]], "vis": y[IDX["vis"]],
            "mup": y[IDX["mup"]], "mux": y[IDX["mux"]],
            "A0": y[IDX["A0"]], "A1": y[IDX["A1"]], "A3": y[IDX["A3"]], "A4": y[IDX["A4"]],
            "A_t1": y[IDX["A_t1"]],
            # 总菌丝 X = a0 + a1 + a3 + a4（对齐 indpensim.m L322）
            "X": y[IDX["A0"]] + y[IDX["A1"]] + y[IDX["A3"]] + y[IDX["A4"]],
        }
        if fb_limit is not None:
            rec["Fb_ctl"] = float(inp1[6])
            rec["g_fb"] = float(_g_b)
        if fs_ctl is not None:
            rec["Fs_ctl"] = float(inp1[1])
            rec["u_fs"] = float(_u_last)
            rec["S_err_norm"] = float(_e_last)
        records.append(rec)
    sim = pd.DataFrame(records)
    if vis_out_scale != 1.0:
        # 保留 ODE 状态（进 kla 的那个量）到 vis_state，vis 改为化验口径
        sim["vis_state"] = sim["vis"]
        sim["vis"] = sim["vis"] * vis_out_scale
    if fs_ctl is not None:
        sim.attrs["fs_ctl"] = dict(fs_ctl)
        sim.attrs["fs_trace"] = fs_trace
    if fb_limit is not None:
        sim.attrs["fb_limit"] = dict(fb_limit)
        sim.attrs["fb_trace"] = fb_trace
    sim.attrs["mv_warnings"] = mv_warnings  # I2 有效域告警（不拦截，挂元数据）
    # R157 / D-56：记录 **basic 分支是否已被修正**。
    # `ph_fix=1` 时 pH 方程按链式法则修正，pH ≥ 7 的 basic 分支不再有
    # `−Kw/[H+]` 正反馈的数值病态 ⇒ 「越 7」不再等同于「轨迹不可信」。
    # `validity()` 用它决定越域判据；默认 `ph_fix=0` ⇒ 该标志为 False ⇒ 旧行为逐位不变。
    sim.attrs["ph_basic_fixed"] = bool(ph_fix)
    # R148 / D-34：守卫审计。n_steps 为采样步数，tally 为按状态的改写次数。
    # 判"该批是否被钳位"以 `tally 非空` 为准，**不再靠 pH ≤ 3.05 的阈值近似**。
    sim.attrs["guard_audit"] = {
        "n_steps": _guard_n_steps,
        "tally": dict(_guard_tally),
        "tally_first": dict(_guard_tally_first),
        "ph_nonpos_steps": _ph_nonpos_steps,
        "ph_max_pre": (float(np.nanmax(sim["pH_pre"].to_numpy(float)))
                       if sim["pH_pre"].notna().any() else float("nan")),
        "n_ph_over7_pre": int((sim["pH_pre"].to_numpy(float) >= 7.0).sum()),
    }
    # 自检恒等式：guards 的改写条件（y[6] ≤ 0）与 ph_nonpos_steps 的判定条件完全一致，
    # 二者必须相等。不等即说明计数逻辑出错（R148 就靠这条抓到一次别名重复计数）。
    sim.attrs["guard_audit"]["audit_consistent"] = (
        int(_guard_tally.get("pH_H", 0)) == int(_ph_nonpos_steps))
    if assimilate is not None:
        sim.attrs["assim_log"] = list(assim_log)  # R140 校正历史（每观测时刻的 k 与门控状态）
    return sim, d


def classify_crash(sim, co2d_crit=7.57, yield_err=None):
    """证据化崩溃分级（I2 失败可见；依据 V3 批 23 反例证据）。

    背景：X_crit_CO2 = 7.57 g/L 是机理模型生长抑制阈值。批 23 的仿真在
    t≈260h（共 264h）轻微穿越该阈值，但末产量偏差 -0.4%、pH 未失稳、P 无崩塌；
    V3 数据同样显示批 23 于 ~252h 底物耗尽（S→0）后经稀释自然衰减（X_offline 25→22.5），
    即"生长停止"在 V3 中同样发生。直接以"穿越阈值 = 崩溃"判定会误伤该良性事件。

    分级（以病理证据为准，时间仅作记录）：
      "normal"        — 未穿越阈值
      "benign"        — 穿越；但无病理证据：pH 保持 [5.0, 8.0]，
                        P 无崩塌（末值 ≥ 0.5×峰值），且（若提供）产率偏差 ≤5%
                        （批 23 证据：t_cross/批长=94.9% 即亮度临界也不构成病理；
                        V3 同批显示 S 耗尽型生长停滞，属同象）
      "catastrophic"  — 任一病理证据成立（pH 失稳至守卫钳位 / P 崩塌 / 产率损失）

    返回 (level, reasons)；reasons 为证据字符串列表（显式失败可见，不静默）。
    """
    reasons = []
    co2d = sim["CO2d"]
    if co2d.max() <= co2d_crit:
        return "normal", []

    t_end = float(sim["time_h"].iloc[-1])
    t_cross = float(sim.loc[co2d > co2d_crit, "time_h"].iloc[0])
    reasons.append(f"CO2d={co2d.max():.2f}>{co2d_crit} 于 t={t_cross:.1f}h 穿越 (批长 {t_end:.1f}h, t_cross/批长={t_cross/t_end:.0%})")

    p = sim["P"]
    ph_end = float(sim["pH"].iloc[-1])
    ph_ok = 5.0 <= ph_end <= 8.0
    p_ok = float(p.iloc[-1]) >= 0.5 * float(p.max())
    y_ok = yield_err is None or abs(yield_err) <= 0.05
    if not ph_ok:
        reasons.append(f"pH 末值={ph_end:.2f} 越出 [5.0,8.0]（失稳/守卫钳位）")
    if not p_ok:
        reasons.append(f"P 崩塌（末值 {p.iloc[-1]:.2f} < 0.5×峰值 {p.max():.2f}）")
    if not y_ok:
        reasons.append(f"产率偏差 {yield_err:+.1%} 超出 ±5%")

    if ph_ok and p_ok and y_ok:
        reasons.append("良性穿越：P 无崩塌、pH 在窗内、产率达标 → 与 V3 底物耗尽型生长停滞同象")
        return "benign", reasons
    return "catastrophic", reasons


def classify_health(sim, v3=None, co2d_crit=7.57, ph_crit=7.0, p_floor=0.5,
                    p_floor_rel=0.6, yield_err=None, yield_crit=0.05):
    """五通道健康分级（R155 / D-38）。与 `classify_crash` **并存，不替换**。

    D-38 的事实：`classify_crash` 首句是 `if co2d.max() <= co2d_crit: return normal`，
    而 86/86 批的 CO2d.max() ≤ 7.194 ⇒ 该函数在黄金集上**从未检验任何东西**
    （b91 的 pH 末值 3.001、pH 钳位 129 样点、P 末/峰 0.162，仍报 normal）。
    既然历史验收数字依赖它的返回值，本函数不改它，另立一条并列通道。

    五条病理通道（互相独立，任一成立即降级）：
      A CO2d 越生长抑制阈值      —— `classify_crash` 的唯一通道
      B pH 被守卫钳位            —— `guard_audit.tally['pH_H'] > 0`（R148 口径）
      C pH 越出可行域 / 解出非正  —— `pH_pre` 最大值 ≥ ph_crit，或存在 NaN
      D 产物崩塌                 —— 见下（相对口径优先）

    D 通道的口径（R155 实测修正）：实测 P 的末/峰比在 86 批里落在 0.375–0.826，
    末期水解/收获是**真实过程**，所以绝对阈值会把 12 批判成崩塌而其中 4 批实测本来就低。
    因此 v3 给定时用相对口径 `drop_sim / drop_meas < p_floor_rel`（模型比实测多掉 40%），
    未给 v3 时退回绝对口径 `drop_sim < p_floor`。
      E 产量破线                 —— |yield_err| > yield_crit（需传入）

    等级（D/E 为不可接受，B/C 为有效域破损，A 单独成立为良性）：
      "catastrophic" — D 或 E 成立
      "degraded"     — B 或 C 成立（含 D-41 型：pH 越 7 但产量仍准）
      "benign"       — 仅 A 成立（批 23 型：CO2d 轻越而无病理）
      "normal"       — 五条全不成立

    `flags` 是稳定字符串集合，便于跨轮计数（「degraded 批数」本身就是一条可验收指标）。
    """
    flags, ev = [], []
    au = sim.attrs.get("guard_audit", {}) or {}
    n_clamp = int(au.get("tally", {}).get("pH_H", 0))
    php = sim["pH_pre"].to_numpy(float) if "pH_pre" in sim.columns else np.array([])
    ph_max = float(np.nanmax(php)) if (php.size and np.isfinite(php).any()) else float("nan")
    n_nan = int(np.sum(~np.isfinite(php))) if php.size else 0
    p = sim["P"].to_numpy(float)
    pk = float(np.max(p)) if p.size else float("nan")
    pe = float(p[-1]) if p.size else float("nan")
    drop = pe / pk if pk > 1e-12 else float("nan")
    drop_ref = float("nan")
    if v3 is not None and "P" in getattr(v3, "columns", []):
        vp = v3["P"].to_numpy(float)
        vp = vp[np.isfinite(vp)]
        if vp.size:
            drop_ref = float(vp[-1] / max(float(vp.max()), 1e-12))
    if np.isfinite(drop_ref) and drop_ref > 0.0:
        _drop_bad = bool(drop / drop_ref < p_floor_rel)
    else:
        _drop_bad = bool(np.isfinite(drop) and drop < p_floor)

    ch = {
        "A_co2d": bool(float(sim["CO2d"].max()) > co2d_crit),
        "B_ph_clamp": bool(n_clamp > 0),
        "C_ph_over": bool((np.isfinite(ph_max) and ph_max >= ph_crit) or n_nan > 0),
        "D_p_collapse": _drop_bad,
        "E_yield_break": bool(yield_err is not None and abs(yield_err) > yield_crit),
    }
    if ch["A_co2d"]:
        ev.append(f"CO2d={float(sim['CO2d'].max()):.2f}>{co2d_crit}")
        flags.append("co2d_cross")
    if ch["B_ph_clamp"]:
        ev.append(f"pH 被守卫钳位 {n_clamp} 步")
        flags.append("ph_clamp")
    if ch["C_ph_over"]:
        ev.append(f"pH_pre_max={ph_max:.3f}（NaN {n_nan} 点）≥ {ph_crit}")
        flags.append("ph_over7")
    if ch["D_p_collapse"]:
        if np.isfinite(drop_ref):
            ev.append(f"P 崩塌：末/峰 模型 {drop:.3f} vs 实测 {drop_ref:.3f}"
                      f"（比 {drop / max(drop_ref, 1e-12):.2f} < {p_floor_rel}）")
        else:
            ev.append(f"P 崩塌：末/峰={drop:.3f} < {p_floor}")
        flags.append("p_collapse")
    if ch["E_yield_break"]:
        ev.append(f"产量 {yield_err:+.1%} 越 ±{yield_crit:.0%}")
        flags.append("yield_break")

    if ch["D_p_collapse"] or ch["E_yield_break"]:
        level = "catastrophic"
    elif ch["B_ph_clamp"] or ch["C_ph_over"]:
        level = "degraded"
    elif ch["A_co2d"]:
        level = "benign"
    else:
        level = "normal"
    return {"level": level, "flags": flags, "channels": ch, "evidence": ev,
            "p_drop_ratio": drop, "p_drop_ref": drop_ref,
            "p_drop_rel": (drop / drop_ref if np.isfinite(drop_ref) and drop_ref > 0 else float("nan")),
            "ph_max_pre": ph_max, "n_ph_clamp": n_clamp}

def validity(sim, ph_crit=7.0, ph_hard_max="auto"):
    """R148 / D-34：批次**有效性**判定（与 `classify_crash` 并列，不替换它）。

    动机：`classify_crash` 在 `CO2d.max() <= co2d_crit` 时直接返回 normal（D-38），
    因此看不见 pH 崩塌；而「0 catastrophic」曾由这个分级器给出。本函数只回答一个更硬的问题：
    **这一批的产量是不是模型真的"算"出来的**，而不是守卫把状态钳住之后凑出来的。

    判据（两条，缺一即 `invalid`）：
      1. `pH_H` 从未被守卫改写（`y[6] ≤ 0` ⇒ 数值已崩，物理上 [H+] 不可能为负）；
      2. **数值病态的** basic 分支未被进入 —— 见下。

    R157 / D-56 修正（判据 2 的口径）
    -------------------------------
    R148 的判据 2 是「守卫前 pH 曾达 7.0」。它把两件事混为一谈：
      (a) pH 越 7（进入 basic 分支）——**只说明进入过分支**；
      (b) basic 分支是**数值病态**的（`−Kw/[H+]` 正反馈，失稳时标 `t* = H⁺²/(2Kw)`；
          pH 7.0 处 t* ≈ 0.48 h，与 0.2 h 采样步长同量级）——**这才是轨迹不可信的原因**。
    R156 证明 (b) **可以被消除**：`ph_fix=1` 按链式法则修正（不动点不变）后，
    5 个钳位批的 pH_max 9.19 → 7.07、**钳位 5 → 0**，且 86 批产量仍 86/86 在 ±5%、
    catastrophic 4 → 0、P relRMSE max 0.848 → 0.430 ⇒ **越 7 在修好的分支里无害**。

    ⇒ 新判据：**越 7 是否判 invalid，取决于 basic 分支是否处于数值病态**，
    由 `sim.attrs["ph_basic_fixed"]`（= `ph_fix`）自动决定：
      `ph_fix=0`（默认，basic 分支病态）⇒ 越 7 即 invalid（**与 R148 旧行为逐位一致**）；
      `ph_fix=1`（basic 分支已修）        ⇒ 越 7 只**报告**不判 invalid，只有**钳位**判 invalid。

    实测后果（86 批，见 docs/r157_round_report.md）：
      默认基线（`ph_fix=0`）：valid 77 → **81/86**，残余 5 批 invalid **全部是真空位批**
        （b37/50/51/91/92，`[H⁺]` 曾 ≤ 0 ⇒ 数值崩溃，不可放宽）；
      候选基线 v2（`ph_fix=1`）：valid 77 → **86/86**（钳位已清零 ⇒ 越 7 不再判 invalid）。

    参数
    ----
    sim : DataFrame      含 `pH` 列；若由本模块生成则带 `attrs["guard_audit"]`
    ph_crit : float      pH 越界阈值，默认 7.0（不与 `classify_crash` 的 CO2d 阈值混用）
    ph_hard_max : "auto" | float | None
        "auto"（默认）= 按 `attrs["ph_basic_fixed"]` 自动选（见上）；
        float = 显式给越域**幅度**硬阈值（`ph_max_pre ≥ 阈值` 即 invalid）；
        None = 越域一律不判 invalid（只有钳位判）。

    返回
    ----
    dict：`valid` / `flags` / `ph_max_pre` / `n_ph_clamp` / `n_ph_over7` / `other_clamped`
          + **分布字段**（D-44 教训：必须报分布不能只报计数）
          `n_steps` / `over7_frac` / `ph_hard_max_used` / `basic_branch_fixed`
    """
    flags = []
    ga = sim.attrs.get("guard_audit", None)
    # R157 / D-56：basic 分支是否已被修正（`ph_fix=1`）
    basic_fixed = bool(sim.attrs.get("ph_basic_fixed", False))
    if ph_hard_max == "auto":
        ph_hard = None if basic_fixed else ph_crit
    else:
        ph_hard = ph_hard_max
    if ga is None:
        # 兼容没有审计的旧数据：退回 pH 阈值近似，并显式声明精度降级，不伪装成精确判定
        flags.append("no_guard_audit(fallback:pH<=3.05)")
        ph = sim["pH"].to_numpy(float)
        n_ph_clamp = int((ph <= 3.05).sum())
        ph_max_pre = float(np.nanmax(ph))
        n_ph_over7 = int((ph >= ph_crit).sum())
        other = {}
        n_steps = int(len(ph))
    else:
        tally = dict(ga.get("tally", {}))
        n_ph_clamp = int(tally.pop("pH_H", 0))
        ph_max_pre = float(ga.get("ph_max_pre", float("nan")))
        n_ph_over7 = int(ga.get("n_ph_over7_pre", 0))
        n_steps = int(ga.get("n_steps", 0) or 0)
        # 扣掉第 1 步：A3/A4/n0..nm/phi0 的零初值必然触发守卫，88/88 批都有，
        # 是初始化现象而非崩溃信号。不扣掉会让 suspect 变成"全批命中"，失去鉴别力。
        first = dict(ga.get("tally_first", {}))
        other = {k: v - first.get(k, 0) for k, v in tally.items()}
        other = {k: v for k, v in other.items() if v > 0}

    # 越域"硬"判据：幅度（`ph_max_pre`）而非步数计数。
    # ph_hard is None ⇒ basic 分支已修 ⇒ 越 7 不判 invalid。
    over7_frac = (float(n_ph_over7) / n_steps) if n_steps else float("nan")
    if ph_hard is None:
        over_hard = False
    elif ga is None:
        over_hard = bool(n_ph_over7 > 0)
    else:
        over_hard = bool(np.isfinite(ph_max_pre) and ph_max_pre >= ph_hard)

    if n_ph_clamp > 0:
        flags.append(f"pH 被守卫钳位 {n_ph_clamp} 步（y[6]≤0，[H+] 不可为负）")
    if n_ph_over7 > 0:
        if over_hard:
            flags.append(f"pH 守卫前达 {ph_max_pre:.3f} ≥ {ph_hard} 共 {n_ph_over7} 步"
                         f"（basic 分支 + −Kw/[H+] 正反馈）")
        else:
            flags.append(f"pH 守卫前达 {ph_max_pre:.3f}（越 7 共 {n_ph_over7} 步，"
                         f"占比 {over7_frac:.3%}）—— basic 分支已修正（ph_fix=1），"
                         f"**不判 invalid**，仅登记")

    valid = (n_ph_clamp == 0) and (not over_hard)
    # 非 pH 钳位：只报不判，但若涉及产物/体积这类不可能为负的量，升级为 suspect
    critical_states = {"P", "V", "Wt", "A0", "A1", "A3", "A4"}
    suspect = {k: v for k, v in other.items() if k in critical_states and v > 0}
    if suspect:
        flags.append("非 pH 关键量被钳位（suspect）：" +
                     ", ".join(f"{k}×{v}" for k, v in sorted(suspect.items())))

    return {
        "valid": bool(valid),
        "suspect": bool(suspect),
        "flags": flags,
        "ph_max_pre": ph_max_pre,
        "n_ph_clamp": n_ph_clamp,
        "n_ph_over7": n_ph_over7,
        "other_clamped": dict(sorted(other.items(), key=lambda kv: -kv[1])),
        # ---- R157 / D-56：分布字段（D-44 教训：必须报分布不能只报计数）----
        "n_steps": n_steps,
        "over7_frac": over7_frac,
        "ph_hard_max_used": ph_hard,
        "basic_branch_fixed": basic_fixed,
    }


def yield_metrics(sim, v3, h=H_SAMPLE):
    """产率口径（PROBLEM.md §7.2）：harvested = -sum(Fremoved·P)·h；end = V_last·P_last。"""
    harvested = float(-(v3["Fremoved"] * sim["P"]).sum()) * h
    end_in_vessel = float(sim["V"].iloc[-1] * sim["P"].iloc[-1])
    v3_harvested = float(-(v3["Fremoved"] * v3["P"]).sum()) * h
    v3_end = float(v3["V"].iloc[-1] * v3["P"].iloc[-1])
    return {
        "harvested_sim_g": harvested, "end_in_vessel_sim_g": end_in_vessel,
        "total_sim_g": harvested + end_in_vessel,
        "harvested_v3_g": v3_harvested, "end_in_vessel_v3_g": v3_end,
        "total_v3_g": v3_harvested + v3_end,
        "rel_err_total": (harvested + end_in_vessel) / (v3_harvested + v3_end) - 1.0,
    }


SHAPE_PHASES = (("0-60", 0.0, 60.0), ("60-120", 60.0, 120.0),
                ("120-180", 120.0, 180.0), ("180+", 180.0, float("inf")))


def _align_series(sim, v3, ch):
    """把 v3 的 ch 按 time_h 插值到 sim 的时间栅格。

    R146 教训：`sim` 从 0.4 h 起记录、`v3` 从 0.2 h 起，按行号截断会让整体
    残差偏一个采样点（0.2 h）。形状指标一律按时间轴对齐。
    """
    t = sim["time_h"].to_numpy(float)
    tv = v3["time_h"].to_numpy(float)
    v = v3[ch].to_numpy(float)
    ok = np.isfinite(tv) & np.isfinite(v)
    if not np.any(ok):
        return None, None
    return t, np.interp(t, tv[ok], v[ok])


def shape_metrics(sim, v3, channels=("P", "S"), phases=SHAPE_PHASES):
    """形状口径（D-43）：时间对齐 relRMSE + 分相位相对残差 + 峰/末形态。

    存在的理由
    ----------
    `yield_metrics()` 的 `rel_err_total` 是一个标量和，只约束一个自由度：
    峰高尾低可以完全抵消（R150 b50 就是如此）。86/86 批产量达标而 P 的
    relRMSE 中位 15.6%、相关仅 +0.0113 —— 验收体系缺形状维度。本函数补这一维。

    与 `trajectory_metrics()` **并存，不替换**：后者按行号采 `n=min(len)`，
    改动会牵动全部历史可比性（D-43 口径待办未关闭）。本函数一律按 `time_h` 对齐。

    相位相对残差以**实测峰值**归一：P 的绝对值跨批差 4 倍，绝对差值不可跨批比较。
    """
    out = {}
    for ch in channels:
        if ch not in sim.columns or ch not in v3.columns:
            continue
        t, m = _align_series(sim, v3, ch)
        if t is None:
            continue
        s = sim[ch].to_numpy(float)
        diff = s - m
        rmse = float(np.sqrt(np.mean(diff ** 2)))
        denom = float(np.sum((m - m.mean()) ** 2))
        mean_abs = float(np.mean(np.abs(m)))
        peak_m, peak_s = float(np.max(m)), float(np.max(s))
        scale = max(abs(peak_m), 1e-9)
        ph = {}
        for name, lo, hi in phases:
            msk = (t >= lo) & (t < hi)
            if not np.any(msk):
                ph[name] = {"mean": float("nan"), "absmax": float("nan"), "n": 0}
                continue
            d = diff[msk] / scale
            ph[name] = {"mean": float(np.mean(d)),
                        "absmax": float(np.max(np.abs(d))),
                        "n": int(msk.sum())}
        out[ch] = {
            "rel_rmse": rmse / mean_abs if mean_abs > 0 else float("nan"),
            "r2": 1.0 - float(np.sum(diff ** 2)) / denom if denom > 0 else float("nan"),
            "bias": float(np.mean(diff)) / scale,
            "peak_meas": peak_m, "peak_sim": peak_s,
            "peak_ratio": peak_s / scale,
            "t_peak_meas": float(t[int(np.argmax(m))]),
            "t_peak_sim": float(t[int(np.argmax(s))]),
            "end_meas": float(m[-1]), "end_sim": float(s[-1]),
            "end_ratio": float(s[-1]) / float(m[-1]) if abs(m[-1]) > 1e-12 else float("nan"),
            "drop_meas": 1.0 - float(m[-1]) / scale,
            "drop_sim": 1.0 - float(s[-1]) / max(peak_s, 1e-9),
            "phase": ph,
        }
    return out


def trajectory_metrics(sim, v3, channels=("S", "DO2", "P", "V", "Wt", "pH", "T",
                                         "CO2outgas", "O2", "OUR", "CER"), align="row"):
    """逐通道 MAE/RMSE/R²。

    align="row"（默认）—— 按行号截断 `n=min(len)`。R150 及以前全部历史数字的口径，
        改动会牵动可比性，因此保留为默认（D-45）。
    align="time"        —— 按 `time_h` 插值对齐（复用 `_align_series`），与
        `shape_metrics()` 同口径。sim 从 0.4 h 起、v3 从 0.2 h 起，row 口径整体错一格
        （R146 在 b55 上量到 0.2673→0.2659）。
    """
    out = {}
    for ch in channels:
        if ch not in sim.columns or ch not in v3.columns:
            continue
        s = sim[ch].to_numpy(float)
        if align == "time":
            t_al, v_al = _align_series(sim, v3, ch)
            if t_al is None:
                continue
            v = v_al
            n = len(s)
        else:
            v = v3[ch].to_numpy(float)
            n = min(len(s), len(v))
        if n == 0:
            continue
        diff = s[:n] - v[:n]
        mae = float(np.mean(np.abs(diff)))
        rmse = float(np.sqrt(np.mean(diff ** 2)))
        denom = np.sum((v[:n] - np.mean(v[:n])) ** 2)
        r2 = 1.0 - np.sum(diff ** 2) / denom if denom > 0 else float("nan")
        out[ch] = {"mae": mae, "rmse": rmse, "r2": r2,
                   "rel_rmse": rmse / float(np.mean(np.abs(v[:n]))) if np.mean(np.abs(v[:n])) > 0 else float("nan"),
                   "align": align}
    return out


def print_report(batch_no, sim, v3, params=None, shape=False):
    print(f"=== batch {batch_no} : sim {len(sim)} rows vs V3 {len(v3)} rows ===")
    if params:
        print("params:", json.dumps(params))
    for ch, m in trajectory_metrics(sim, v3).items():
        print(f"  {ch:9s}: MAE={m['mae']:.4g} RMSE={m['rmse']:.4g} R2={m['r2']:.3f} "
              f"relRMSE={m['rel_rmse']:.3f}")
    ym = yield_metrics(sim, v3)
    print(f"  yield: sim_total={ym['total_sim_g']:.0f} g  v3_total={ym['total_v3_g']:.0f} g  "
          f"rel_err={ym['rel_err_total']:+.3%}")
    if shape:
        for _ch, _m in shape_metrics(sim, v3).items():
            _ph = "  ".join(f"{k}:{v['mean']:+.3f}" for k, v in _m["phase"].items())
            print(f"  shape[{_ch}]: relRMSE={_m['rel_rmse']:.3f} R2={_m['r2']:.3f} "
                  f"peak_ratio={_m['peak_ratio']:.3f} end_ratio={_m['end_ratio']:.3f}")
            print(f"         phase {_ph}")
    return ym


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=1)
    ap.add_argument("--params", type=str, default="", help="JSON: mux/mup/alpha_kla/PAA_c/N_conc_paa/c_oil")
    ap.add_argument("--params-file", type=str, default="", help="JSON 文件（同上）")
    ap.add_argument("--inhib", type=int, default=2)
    ap.add_argument("--out", type=str, default="")
    ap.add_argument("--shape", action="store_true",
                    help="额外打印形状口径（D-43）：时间对齐 relRMSE + 分相位残差 + 峰/末比")
    args = ap.parse_args()
    if args.params_file:
        with open(args.params_file, "r", encoding="utf-8") as fh:
            params = json.load(fh)
    else:
        params = json.loads(args.params) if args.params else None
    t0 = time.time()
    sim, v3 = simulate_open_loop(args.batch, params=params, inhib=args.inhib)
    elapsed = time.time() - t0
    print(f"[elapsed {elapsed:.1f}s]")
    ym = print_report(args.batch, sim, v3, params, shape=args.shape)
    _csv = args.out or f"data/processed/sim_batch_{args.batch:02d}.csv"
    os.makedirs(os.path.dirname(_csv) or ".", exist_ok=True)
    sim.to_csv(_csv, index=False)
    print("saved:", _csv)
    # 保存指标
    import json as _json
    _mj = f"data/processed/sim_batch_{args.batch:02d}_metrics.json"
    os.makedirs(os.path.dirname(_mj) or ".", exist_ok=True)
    with open(_mj, "w", encoding="utf-8") as fh:
        _blob = {"yield": ym, "trajectory": trajectory_metrics(sim, v3),
                 "params": params or {}, "elapsed_s": elapsed}
        if args.shape:
            _blob["shape"] = shape_metrics(sim, v3)
        _json.dump(_blob, fh, indent=2, ensure_ascii=False)
