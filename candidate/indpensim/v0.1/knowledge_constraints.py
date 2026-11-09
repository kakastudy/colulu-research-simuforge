# -*- coding: utf-8 -*-
"""T1 指导性知识：反应罐物理/微生物动力学/化学约束表（PH4 控制层硬约束草案 + PH1 校准 bounds）。

来源分层：
- [M] 机理模型内建（indpensim_ode.m 对齐值，最高权威）
- [L] 文献/生物学常识（Pirt 1990、维持代谢通则、菌丝形态学；标注"文献级"）
- [E] 本工程取证（有效域证据；runs/ 工件背书）

每条约束含：键名、量/单位、约束、来源、校准/控制用途。
"""
CONSTRAINTS = [
    # —— 维持代谢（微生物动力学）——
    {"key": "m_s", "desc": "维持系数", "unit": "g/g/h", "lo": 0.005, "hi": 0.045,
     "src": "L(通则0.01-0.05)+E(黄金校准域0.014-0.029)", "use": "calib_bounds"},
    # —— 比速率（微生物动力学）——
    {"key": "mux", "desc": "比生长基准", "unit": "1/h", "lo": 0.30, "hi": 0.47,
     "src": "E(黄金校准实测域)", "use": "calib_bounds"},
    {"key": "mup", "desc": "比产物基准", "unit": "1/h", "lo": 0.010, "hi": 0.080,
     "src": "E(校准+stage2救回域)", "use": "calib_bounds"},
    {"key": "alpha_kla", "desc": "体积氧传质系数", "unit": "1/h", "lo": 50.0, "hi": 120.0,
     "src": "E(名义85;M2敏感度中等)", "use": "calib_bounds"},
    # —— 化学抑制（cell level）——
    {"key": "X_crit_CO2", "desc": "CO2d 生长抑制阈值", "unit": "g/L", "lo": 7.57, "hi": 7.57,
     "src": "M(模型常数7570)", "use": "control_hard"},
    {"key": "PAA_inhib", "desc": "PAA 前体抑制", "unit": "mg/L", "lo": 500.0, "hi": 600.0,
     "src": "L(进料浓度530g/L 级控制)", "use": "control_watch"},
    {"key": "p_hydrolysis", "desc": "P 水解降解（一阶；37C/pH6 缓慢）", "unit": "1/h",
     "lo": 0.0, "hi": 0.02, "src": "L(Pirt 1990 doi:10.1016/0922-338x(90)90224-k)",
     "use": "ph2_candidate"},  # 机理未含 → PH2 残差候选库
    # —— 物理操作窗口（biology/物理）——
    {"key": "T_op", "desc": "操作温度窗", "unit": "K", "lo": 293.0, "hi": 303.5,
     "src": "L(工业窗)+M(默认298/控温PID)", "use": "control_hard"},
    {"key": "pH_op", "desc": "操作 pH 窗", "unit": "-", "lo": 5.2, "hi": 6.9,
     "src": "L(青霉素发酵窗)+E(V3 批末值 6.3-6.7)", "use": "control_hard"},
    {"key": "DO2_op", "desc": "DO2 操作下限", "unit": "mg/L", "lo": 15.0, "hi": 40.0,
     "src": "M(氧依赖抑制 X_crit_DO2≈15)", "use": "control_watch"},
    {"key": "Fs_bifurcation", "desc": "Fs 倍率分岔边界（批8）", "unit": "×", "lo": 0.90, "hi": 0.97,
     "src": "E(runs/opt_batch_08.json 分岔取证)", "use": "control_hard"},
    # —— 层次先验（MATLAB 生成机制 = 批次随机效应的物理来源）——
    {"key": "mux_prior", "desc": "μx 批次先验", "unit": "1/h", "lo": 0.41 - 3 * 0.025,
     "hi": 0.41 + 3 * 0.025, "src": "M(indpensim.m randn 生成)", "use": "hier_prior"},
    {"key": "mup_prior", "desc": "μp 批次先验", "unit": "1/h", "lo": 0.041 - 3 * 0.0025,
     "hi": 0.041 + 3 * 0.0025, "src": "M(indpensim.m randn 生成)", "use": "hier_prior"},
    {"key": "alpha_kla_prior", "desc": "KLa 批次先验", "unit": "1/h", "lo": 85 - 3 * 10.0,
     "hi": 85 + 3 * 10.0, "src": "M(indpensim.m randn 生成)", "use": "hier_prior"},
    {"key": "PAA_c_prior", "desc": "PAA 进料浓度先验", "unit": "mg/L", "lo": 530000 - 3 * 20000,
     "hi": 530000 + 3 * 20000, "src": "M(indpensim.m randn 生成)", "use": "hier_prior"},
]


def calib_bounds():
    """PH1 快校准 bounds 键集合。"""
    return {c["key"]: (c["lo"], c["hi"]) for c in CONSTRAINTS if c["use"] == "calib_bounds"}


def hier_priors():
    """PH1 层次先验（μ̂, 3σ 界）——MATLAB 生成机制。"""
    return {c["key"]: {"lo": c["lo"], "hi": c["hi"], "unit": c["unit"],
                        "src": c["src"]} for c in CONSTRAINTS if c["use"] == "hier_prior"}


def control_hard():
    """PH4 控制层硬约束（不得越域）。"""
    return [c for c in CONSTRAINTS if "control_hard" in c["use"]]


def ph2_candidates():
    """PH2 残差候选库（机理缺失项的领域来源）。"""
    return [c for c in CONSTRAINTS if c["use"] == "ph2_candidate"]


def validate_t1(state_sample: dict) -> tuple:
    """T1 草案校验器（PH4 控制层的滚动验证用）。

    state_sample: {"T": K, "pH": -, "CO2d": g/L, "DO2": mg/L, "mv_scales": {...}}
    返回 (ok: bool, reasons: list[str]) —— 违规项显式列出（I2）。
    """
    reasons = []
    T = state_sample.get("T")
    if T is not None and not (293.0 <= T <= 303.5):
        reasons.append(f"T={T:.1f}K 越出操作窗 [293, 303.5]")
    pH = state_sample.get("pH")
    if pH is not None and not (5.2 <= pH <= 6.9):
        reasons.append(f"pH={pH:.2f} 越出操作窗 [5.2, 6.9]（病理门槛）")
    co2d = state_sample.get("CO2d")
    if co2d is not None and co2d > 7.57:
        reasons.append(f"CO2d={co2d:.2f} 越过 X_crit_CO2 (7.57)——进入 crash 分级流程")
    do2 = state_sample.get("DO2")
    if do2 is not None and do2 < 15.0:
        reasons.append(f"DO2={do2:.1f} 低于氧抑制下限 (X_crit_DO2≈15)")
    scales = state_sample.get("mv_scales") or {}
    for k, v in scales.items():
        if not (0.90 <= float(v) <= 1.25):
            reasons.append(f"MV[{k}]={v:.3f} 越出验证域 [0.90, 1.25]")
    return (len(reasons) == 0, reasons)


# ---------------------------------------------------------- PAA PAT 通道条件触发器
# R91 机理锚点：引擎 PAA 状态局部保真度与校准 μp 强负相关（corr(r, μp) = −0.891,
# 9 健康批, runs/hier_est/paa_fidelity_census.json）——μp 高（PAA 快吸收 strain）
# 批的状态反相为参数级结构误差 → PAT 条件修正应按校准 μp 阈值触发而非事后逐批算 r。

PAA_PAT_TRIGGER_MUP = 0.055  # 校准 μp 阈值（22/23 = 0.070 反相；36/60 = 0.041/0.030 近完美）


def paa_pat_trigger(mu_p: float) -> tuple:
    """PAA PAT 锚定修正的条件触发（R91 机理锚点）。
    返回 (trigger: bool, reason: str)。校准 μp > 0.055 → 引擎 PAA 状态存在高吸收
    regime 的结构失真风险 → 条件性启用 PAT 锚定修正层（见
    docs/raman_pat_integration_spec.md §1）。"""
    if mu_p is None:
        return (False, "mu_p 缺失——保守不触发")
    if float(mu_p) > PAA_PAT_TRIGGER_MUP:
        return (True, f"μp={mu_p:.3f} > {PAA_PAT_TRIGGER_MUP}（高 PAA 吸收 regime: "
                      f"引擎 PAA 状态结构失真风险, 启用 PAT 锚定修正层）")
    return (False, f"μp={mu_p:.3f} ≤ {PAA_PAT_TRIGGER_MUP}（引擎 PAA 状态可信, PAT 直接前向）")
