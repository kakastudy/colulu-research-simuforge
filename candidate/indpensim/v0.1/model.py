# -*- coding: utf-8 -*-
"""IndPenSim 机理模型 ODE 主体（Python 移植），逐项对照 MATLAB indpensim_ode.m。

状态向量 y (33 维, 0-based):
  0:S  1:DO2  2:O2  3:P  4:V  5:Wt  6:pH([H+])  7:T  8:Q  9:vis
 10:A_t1  11:A0  12:A1  13:A3  14:A4  15..24:n0..n9  25:nm  26:phi0
 27:CO2  28:CO2d  29:PAA  30:NH3  31:mup  32:mux

输入 inp1 (26 维, 0-based):
  0:inhib 1:Fs 2:Fg 3:RPM 4:Fc 5:Fh 6:Fb 7:Fa 8:step1(h_ode) 9:Fw
 10:pressure 11:viscosity 12:F_discharge 13:Fpaa 14:Foil 15:NH3_shots
 16:dist_flag 17:distMuP 18:distMuX 19:distsc 20:distcoil 21:distabc
 22:distPAA 23:distTcin 24:distO_2_in 25:Vis_flag
"""
import numpy as np

from params import make_params

N_STATES = 33


def rhs(t, y, inp1, par, paa_gate_mode=0, paa_gate_floor=0.0, paa_maintenance_target=0, paa_degrad_rate=0.0, paa_degrad_inverse_gate=False, fault_type=0, fault_start=0.0, fault_end=0.0, fault_magnitude=0.0, fault_profile=None, biomass_death_rate=0.0, death_start=0.0, vis_scale=1.0, k_vac=0.0, death_recycle=0.0, mu_vac_ref=0.1, late_death_rate=0.0, mu_death_ref=0.02,
        vis_k3=None, vis_k1=None, vis_k2=None, vis_t1=None, vis_t2=None,
        vis_decay_rate=0.0, p_deg_rate=0.0,
        death_mode=0, age_rate=0.0, lysis_rate=0.0, lysis_recycle=0.0, age_mu_ref=0.02,
        age_start=None, ph_hyd_acid=False, ph_rp_mode="net",
        mu_p_growth=0.0, ph_fix=0):
    """IndPenSim ODE 右端。t: 仿真时间(h), y: 33 维状态, inp1: 26 维输入, par: 105 维参数。

    paa_gate_mode: D9(b) PAA 相门控增强模式（R121 根因修复）。
      0 = 不门控（默认，黄金回归零回归守护）
      1 = 底物门控 X_1 项（Y_PAA_X * X_1 * f_paa）
      2 = 底物门控 X_1 + dP_dt 项（Y_PAA_X * X_1 * f_paa + Y_PAA_P * dP_dt * f_paa）

    paa_gate_floor: 门控下限（0.0=完全抑制生长相, 0.1~0.3=部分抑制）。
      f_paa = floor + (1-floor) * mean_P / (mean_P + s)
      用于控制幅度过冲：floor 越高，生长相 PAA 消耗越多，累积越少。

    paa_maintenance_target: m_PAA 维护消耗的目标变量（R123 修复）。
      0 = P（青霉素浓度）—— 原始代码行为，保留黄金回归
      1 = total_X（生物量浓度）—— 对齐 MATLAB indpensim_ode.m 原文
      物理依据：m_PAA（1.05 g/g/h）是每克生物量每消耗的 PAA 维护系数，
      应正比于生物量 X 而非产物 P。R123 发现原代码用 y[3]=P 导致生长相
      （P 低）维护消耗过小，与门控叠加后 PAA 幅度过冲。修复后生长相
      m_PAA*X 仍有效消耗 PAA，控制累积幅度。

    paa_degrad_rate: 一阶 PAA 降解速率常数（R123c）。
      0.0 = 不启用（默认，黄金回归守护）
      >0 = 添加 -rate * PAA 项，模拟 PAA 在发酵液中的缓慢降解。
      物理依据：PAA（苯乙酸）在发酵液中会缓慢降解（氧化/水解）。
      门控抑制 Y_PAA_X*X_1 消耗后喂食项持续累积 PAA，降解项作为
      被动消耗补充，防止幅度过冲。需配合 m_PAA 重校准。

    paa_degrad_inverse_gate: 反相门控降解开关（R124）。
      False = 降解恒定激活（R123c 行为，生产相也消耗 PAA → 可能破坏时序）
      True = 降解仅在门控关闭时激活（生长相活跃，生产相关闭）
      物理依据：PAA 的溢出代谢（overflow metabolism）在生长相活跃——
      当青霉素合成途径未启动时，PAA 通过替代酶系被代谢消耗。
      生产相时该途径关闭，PAA 留给青霉素合成前体消耗。
      数学：degrad = rate * PAA * (1 - f_paa)。

    门控函数 f_paa（Michaelis-Menten 型 + floor）：
      s→∞（营养期）→ f_paa→floor：抑制 PAA 消耗
      s→0 （生产期）→ f_paa→1.0：允许 PAA 消耗
    物理依据：PAA（苯乙酸）作为前体，其消耗应发生在生产相（idiophase）
    而非生长相（trophophase）。R121 发现高 μp 批的 PAA 时序严重错位
    （引擎峰值早于化验 144-180h），根因 = X_1（生物量生长速率）在生长相
    过早触发 PAA 消耗。相门控修复此结构缺失。

    fault_type: D4 故障注入算子类型（V1+）。
      0 = 不注入（默认，黄金回归零回归守护）
      1 = 氧限制故障（降低 KLa → DO2 下降 → 氧抑制 → 底物累积 → 低产率）
      2 = pH 扰动故障（注入酸 → pH 下降 → 代谢应激 → 产率下降）
      3 = 喂食减少故障（降低 Fs/Fpaa → 底物不足 → 生长停滞）
    物理依据：批 91 为氧限制故障（S max=115, P max=8, DO2 低）；
    批 92 为 pH 扰动故障（pH min=5.48, 喂食率高）。
    fault_start/end: 故障时间窗（小时）。
    fault_magnitude: 故障强度（0.0-1.0 为 KLa/喂食降低比例；pH 为酸注入速率 mg/L/h）。
    fault_profile: R157 / T3-2 **模式级注入**的时间包络 [(t_h, rel_amp), ...]，
        线性插值得到 t 时刻的相对幅值（0..1），与 `fault_magnitude` 相乘得实际幅值。
        None（默认）⇒ 相对幅值恒为 1 ⇒ **与 R127 逐位一致**。

    biomass_death_rate: ODE 级生物量衰亡速率（R129, D9 扩展）。
      0.0 = 不启用（默认，黄金回归零回归守护）
      >0 = 在生物量 ODE 各组分加 -kd·y[comp] 项，减少总生物量。
      物理依据：R127 D4 探针发现批 91 底物累积根因是生物量衰亡（DO2 恢复后
      S 仍从 t=96h 线性累积至 115——生物量停止消耗底物）。模型现有 r_d1/r_d4
      是组分间迁移（总量守恒），无真正衰亡项。衰亡使生物量下降 → 底物消耗
      减少 → 喂食持续 → S 累积。PH2 后验死亡项（death_correct_X）仅修正 X
      轨迹不参与 ODE 动力学，无法捕获此效应。

    death_start: 衰亡起始时间（h, R129b）。0.0=全程衰亡（默认）。
      >0 = t < death_start 时不衰亡，t >= death_start 时激活 kd。
      物理依据：批 91 P 峰值在 t=92h（衰亡前生物量正常产 P），S 累积在 t=96h 后
      （衰亡后生物量停止消耗底物）。全程衰亡会过早降低 P 产率（P_max 8.1→6.1），
      time-varying 衰亡保留早期产 P 同时实现后期 S 累积。

    death_mode: 衰亡**结构**开关（R141, 闭合 D-8）。
      0 = 现行等比移除（默认）：`-kd·y[i]` 对 a0/a1/a3/a4 同率施加。
          缺陷：形态分区比例恒定，"只移除死菌"无法表达；且 a1 被同率砍掉
          ⇒ 产素主力同步受损（R137 晚期衰亡破线的直接原因）。
      1 = 形态学衰亡链：A1 --(age_rate, 生长率门控)--> A3 --(lysis_rate)--> 出系统。
          老化是 X 内部转移（不动总量），只有溶菌真正降 X；溶菌按 lysis_recycle
          比例把胞内物质回收到 S。死菌池 a3/a4 由此首次非零。
    age_rate: 老化速率（1/h, death_mode=1 生效）。A1→A3，门控 max(0,1-μ/age_mu_ref)。
    lysis_rate: 死菌溶菌速率（1/h, death_mode=1 生效）。作用于 a3+a4。
    lysis_recycle: 溶菌底物回收比例（0~1, death_mode=1 生效）。
    age_mu_ref: 老化生长率阈值（1/h, 默认 0.02 = 与 mu_death_ref 同量级）。

    ph_hyd_acid: 产品水解通道在 **pH 方程**里的酸碱符号（R145, D-32 反事实开关）。
      False（默认）= 与 MATLAB 原文逐字一致：`r_p` 整体乘 `gamma1`，其中 `-mu_h·P`
                     因此是**碱化**贡献；
      True          = 水解单独按**产酸**计入（青霉噻唑酸为一元羧酸），即
                     `gamma1*(r_p + 2·mu_h·P)`，等价于把 `-mu_h·P` 的符号翻正。
      依据：`r145_d32_terms` 实测，86 批中 **30 批**尾段的净产酸项
      `gamma1*(ph_prod + r_p)` 会**转负**（因 `P_inhib` 高斯门控在残糖高时关闭，
      `r_p` 只剩 `-mu_h·P`），使 pH 方程失去唯一的 [H+] 源、被 buffer 项拖向
      pH>7.8 的无平衡区。见 docs/r145_round_report.md。
      默认关闭 ⇒ 86 批逐位不变（零回归）。

    ph_rp_mode: pH 方程里 `r_p` 的**口径**（R147, D-36 算子层）。三选一：
      "net"（默认）= `r_p` 原样计入 —— 产素项产酸、水解项产碱。与 MATLAB 逐字一致。
      "prod_only"  = 只计产素项，**水解在质子平衡中完全不计**：
                     `r_p_ph = r_p + mu_h·P = mu_p·ρ·v·P_inhib·DO2·PAA`。
      "all_acid"   = 水解项按产酸计入（= `ph_hyd_acid=True` 的等价写法）。
      依据：β-内酰胺开环生成青霉噻唑酸（一元羧酸，pKa≈2.7）确实释放一个可解离
      COOH，但同时消耗一分子水，**净质子变化接近零**；MATLAB 把它写成"碱化"
      （`-mu_h·P` 经 `gamma1`）与翻正成"产酸"（R145 已证伪：pH 末掉到 5.0–5.3、
      46 批破线）都不对，"不计"才是两端之间的物理选择。
      与 `ph_hyd_acid` 的关系：`ph_hyd_acid=True` 等价于 `ph_rp_mode="all_acid"`；
      两者同时给出且冲突时以 `ph_rp_mode` 为准（显式优先）。
      默认 "net" ⇒ 86 批逐位不变（零回归）。
    """
    # ---- 参数解包 ----
    mu_p = par[0]
    mux_max = par[1]
    ratio_mu_e_mu_b = par[2]
    P_std_dev = par[3]
    mean_P = par[4]
    mu_v = par[5]
    mu_a = par[6]
    mu_diff = par[7]
    beta_1 = par[8]
    K_b = par[9]
    K_diff = par[10]
    K_diff_L = par[11]
    K_e = par[12]
    K_v = par[13]
    delta_r = par[14]
    k_v = par[15]
    D = par[16]
    rho_a0 = par[17]
    rho_d = par[18]
    mu_h = par[19]
    r_0 = par[20]
    delta_0 = par[21]
    Y_sX = par[22]
    Y_sP = par[23]
    m_s = par[24]
    c_oil = par[25]
    c_s = par[26]
    Y_O2_X = par[27]
    Y_O2_P = par[28]
    m_O2_X = par[29]
    alpha_kla = par[30]
    # D4 故障注入算子（V1+，默认 off）
    # fault_type: 0=none, 1=oxygen_limit(降KLa), 2=ph_perturb(注酸), 3=feed_reduce(减喂食)
    # R157 / T3-2：**模式级**故障注入 —— 用时间包络 `fault_profile` 替代常数幅值。
    #   `fault_profile` = [(t_h, amp), ...] 节点，线性插值得到 t 时刻的**相对幅值**（0..1）。
    #   None（默认）⇒ 幅值恒为 `fault_magnitude` ⇒ **逐位不变**。
    #   动机：R127 的三个算子只有"常数幅值 + 时间窗"，只能表达阶跃型故障；
    #   而真实工艺故障多为渐变（KLa 结垢渐进、阀卡后逐渐漂移）。
    _fault_active = (fault_type > 0) and (t >= fault_start) and (t <= fault_end)
    if _fault_active and fault_profile:
        _fp_t = np.array([float(p[0]) for p in fault_profile], float)
        _fp_a = np.array([float(p[1]) for p in fault_profile], float)
        _env = float(np.interp(t, _fp_t, _fp_a)) if _fp_t.size >= 2 else float(_fp_a[0])
    else:
        _env = 1.0
    if _fault_active and fault_type == 1:
        alpha_kla_eff = alpha_kla * (1.0 - fault_magnitude * _env)
    else:
        alpha_kla_eff = alpha_kla
    a = par[31]
    b = par[32]
    c = par[33]
    d = par[34]
    Henrys_c = par[35]
    n_imp = par[36]
    r = par[37]
    r_imp = par[38]
    Po = par[39]
    epsilon = par[40]
    g = par[41]
    R = par[42]
    X_crit_DO2 = par[43]
    P_crit_DO2 = par[44]
    A_inhib = par[45]
    Tf = par[46]
    Tw = par[47]
    Tcin = par[48]
    Th = par[49]
    Tair = par[50]
    C_ps = par[51]
    C_pw = par[52]
    delta_H_evap = par[53]
    U_jacket = par[54]
    A_c = par[55]
    Eg = par[56]
    Ed = par[57]
    k_g = par[58]
    k_d = par[59]
    Y_QX = par[60]
    abc = par[61]
    gamma1 = par[62]
    gamma2 = par[63]
    m_ph = par[64]
    K1 = par[65]
    K2 = par[66]
    N_conc_oil = par[67]
    N_conc_paa = par[68]
    N_conc_shot = par[69]
    Y_NX = par[70]
    Y_NP = par[71]
    m_N = par[72]
    X_crit_N = par[73]
    PAA_c = par[74]
    Y_PAA_P = par[75]
    Y_PAA_X = par[76]
    m_PAA = par[77]
    X_crit_PAA = par[78]
    P_crit_PAA = par[79]
    B_1 = par[80]
    B_2 = par[81]
    B_3 = par[82]
    B_4 = par[83]
    B_5 = par[84]
    delta_c_0 = par[85]
    # R133：黏度分支参数提升为**批级可覆盖**。None = 沿用 par 向量默认（零行为变化）。
    # 背景：par[88]=k2=1e-4、par[90]=t2=250h，而批长仅 202–230h，
    # 使第二 sigmoid 在全程≈0.5 的常数，衰减支路名义存在、实际失效。
    k3 = par[86] if vis_k3 is None else vis_k3
    k1 = par[87] if vis_k1 is None else vis_k1
    k2 = par[88] if vis_k2 is None else vis_k2
    t1 = par[89] if vis_t1 is None else vis_t1
    t2 = par[90] if vis_t2 is None else vis_t2
    q_co2 = par[91]
    X_crit_CO2 = par[92]
    alpha_evp = par[93]
    beta_T = par[94]
    pho_g = par[95]
    pho_oil = par[96]
    pho_w = par[97]
    pho_paa = par[98]
    O_2_in = par[99]
    N2_in = par[100]
    C_CO2_in = par[101]
    Tv = par[102]
    T0 = par[103]
    alpha_1 = par[104]

    # ---- 输入解包 ----
    inhib_flag = inp1[0]
    Fs = inp1[1]
    Fg = inp1[2] / 60.0  # m^3/s
    RPM = inp1[3]
    Fc = inp1[4]
    Fh = inp1[5]
    Fb = inp1[6]
    Fa = inp1[7]
    step1 = inp1[8]
    Fw = inp1[9]
    if Fw < 0:
        Fw = 0.0
    pressure = inp1[10]
    if inp1[25] == 0:
        viscosity = y[9]
    else:
        viscosity = inp1[11]
    F_discharge = inp1[12]
    Fpaa = inp1[13]
    Foil = inp1[14]
    # D4 喂食减少故障（降低 Fs/Fpaa）
    if _fault_active and fault_type == 3:
        Fs = Fs * (1.0 - fault_magnitude * _env)
        Fpaa = Fpaa * (1.0 - fault_magnitude * _env)
    NH3_shots = inp1[15]
    dist_flag = inp1[16]
    distMuP = inp1[17]
    distMuX = inp1[18]
    distsc = inp1[19]
    distcoil = inp1[20]
    distabc = inp1[21]
    distPAA = inp1[22]
    distTcin = inp1[23]
    distO_2_in = inp1[24]

    # ---- 扰动 ----
    mu_p = mu_p + distMuP
    mux_max = mux_max + distMuX
    c_s = c_s + distsc
    c_oil = c_oil + distcoil
    abc = abc + distabc
    PAA_c = PAA_c + distPAA
    Tcin = Tcin + distTcin
    O_2_in = O_2_in + distO_2_in

    # ---- 过程参数 ----
    pho_b = 1100.0 + y[3] + y[11] + y[12] + y[13] + y[14]
    A_t1 = y[11] / (y[12] + y[13] + y[14] + y[15])
    s = y[0]
    a_1 = y[12]
    a_0 = y[11]
    a_3 = y[13]
    total_X = y[11] + y[12] + y[13] + y[14]

    # 液位与压力
    h_b = (y[4] / 1000.0) / (np.pi * r * r) * (1 - epsilon)
    pressure_bottom = 1 + pressure + (pho_b * h_b) * 9.81 * 1e-5
    pressure_top = 1 + pressure
    log_mean_pressure = (pressure_bottom - pressure_top) / np.log(pressure_bottom / pressure_top)
    total_pressure = log_mean_pressure

    # 黏度下限
    if viscosity < 4:
        viscosity = 1.0
    if viscosity <= 4:
        viscosity = 1.0
    DOstar_tp = (total_pressure * O_2_in) / Henrys_c

    # ---- 抑制开关 ----
    if inhib_flag == 0:
        pH_inhib = 1.0
        NH3_inhib = 1.0
        T_inhib = 1.0
        mu_h = 0.003
        DO_2_inhib_X = 1.0
        DO_2_inhib_P = 1.0
        CO2_inhib = 1.0
        PAA_inhib_X = 1.0
        PAA_inhib_P = 1.0
    elif inhib_flag == 1:
        pH_inhib = 1.0 / (1 + y[6] / K1 + K2 / y[6])
        NH3_inhib = 1.0
        T_inhib = 1.0  # (k_g*exp(...) - k_d*exp(...))*0 + 1
        CO2_inhib = 1.0
        DO_2_inhib_X = 0.5 * (1 - np.tanh(A_inhib * (X_crit_DO2 * DOstar_tp - y[1])))
        DO_2_inhib_P = 0.5 * (1 - np.tanh(A_inhib * (P_crit_DO2 * DOstar_tp - y[1])))
        PAA_inhib_X = 1.0
        PAA_inhib_P = 1.0
        ph_val = -np.log10(np.maximum(y[6], 1e-12))
        k4 = np.exp((B_1 + B_2 * ph_val + B_3 * y[7] + B_4 * ph_val**2) + B_5 * y[7]**2)
        mu_h = k4
    else:  # inhib_flag == 2
        pH_inhib = 1.0 / (1 + y[6] / K1 + K2 / y[6])
        NH3_inhib = 0.5 * (1 - np.tanh(A_inhib * (X_crit_N - y[30])))
        T_inhib = k_g * np.exp(-(Eg / (R * y[7]))) - k_d * np.exp(-(Ed / (R * y[7])))
        CO2_inhib = 0.5 * (1 + np.tanh(A_inhib * (X_crit_CO2 - y[28] * 1000.0)))
        DO_2_inhib_X = 0.5 * (1 - np.tanh(A_inhib * (X_crit_DO2 * DOstar_tp - y[1])))
        DO_2_inhib_P = 0.5 * (1 - np.tanh(A_inhib * (P_crit_DO2 * DOstar_tp - y[1])))
        PAA_inhib_X = 0.5 * (1 + np.tanh(X_crit_PAA - y[29]))
        PAA_inhib_P = 0.5 * (1 + np.tanh(-P_crit_PAA + y[29]))
        ph_val = -np.log10(np.maximum(y[6], 1e-12))
        k4 = np.exp((B_1 + B_2 * ph_val + B_3 * y[7] + B_4 * ph_val**2) + B_5 * y[7]**2)
        mu_h = k4 * par[18]  # R129ah: mu_h_scale (par[18] default 1.0, rho_d dormant since n_k=0)

    # ---- 速率方程 ----
    P_inhib = 2.5 * P_std_dev * ((P_std_dev * np.sqrt(2 * np.pi)) ** -1
                                 * np.exp(-0.5 * ((s - mean_P) / P_std_dev) ** 2))
    mu_a0 = ratio_mu_e_mu_b * mux_max * pH_inhib * NH3_inhib * T_inhib * DO_2_inhib_X * CO2_inhib * PAA_inhib_X
    mu_e = mux_max * pH_inhib * NH3_inhib * T_inhib * DO_2_inhib_X * CO2_inhib * PAA_inhib_X

    K_diff = par[10] - A_t1 * beta_1
    if K_diff < K_diff_L:
        K_diff = K_diff_L

    r_b0 = mu_a0 * a_1 * s / (K_b + s)
    r_sb0 = Y_sX * r_b0
    r_e1 = mu_e * a_0 * s / (K_e + s)
    r_se1 = Y_sX * r_e1
    r_d1 = mu_diff * a_0 / (K_diff + s)
    r_m0 = m_s * a_0 / (K_diff + s)

    # 液泡分布 — 简化近似（n0 动力学时间尺度 ~1e-7h，超出求解器能力）
    # 设 n0..n9, nm, phi0 = 0（不积分），v_2 = 0, v_a1 = a_1/(2*rho_a0)
    phi = np.zeros(11)
    phi[0] = 0.0  # phi0 = 0
    r_mean = np.zeros(11)
    for k in range(2, 11):
        r_mean[k] = r_0 + (k - 2) * delta_r
        phi[k] = (4 * np.pi * r_mean[k]**3 / 3) * 0.0 * delta_r  # n_k = 0
    v_2 = np.sum(phi)  # = 0
    rho_a1 = a_1 / (a_1 / rho_a0 + v_2)
    v_a1 = a_1 / (2 * rho_a1) - v_2

    # R153 / D-48：生长耦合产素（Pirt 型双相 r_p = (α·μ + β)·X）。
    #
    # 缺口：现行实现只有 β 项，且被残糖高斯门控 P_inhib 控制（中心 2 mg/L、宽 1.5 mg/L）。
    #   生长期（残糖 >5 mg/L）P_inhib 恒 ≈0 ⇒ **生长期产素 ≡ 0**，与实测矛盾：
    #   b3 在 40 h 残糖 13 mg/L 时模型产 0.04 g/L，实测 2.49 g/L。
    #   R153 探针（tools/r153_age_probe.py，88 批反解）：0-60 所需 mu_p 倍率中位 1.63、
    #   51/81 批 >1.1；而 60 h 后三相位中位 0.93-1.01（后段本来就对，不需要衰减）。
    #
    # 形式：λ = mu_p_growth = 产素能力中生长耦合所占比例。
    #       gate = (1-λ)·P_inhib + λ·clip(μ_act/μmax, 0, 1)，mu_p 乘 1/(1-λ) 补偿。
    #   idiophase：μ_act→0 ⇒ gate=(1-λ)·P_inhib，乘回 1/(1-λ) 后**逐值等于 P_inhib**
    #              ⇒ 后段产素完全不动。
    #   生长期：  P_inhib→0、μ_act≈μmax ⇒ gate≈λ，乘回 1/(1-λ) ⇒ λ/(1-λ) ⇒ 只在此新增。
    #
    # 必须用**实际**比生长速率 μ_act，不能用 mu_e：mu_e 只含 pH/NH3/T/DO2/CO2/PAA 门控、
    #   **不含 Monod 糖项**，idiophase 仍接近 1，会把增益漏到后段（实测 180+ 从 +0.045 涨到 +0.163）。
    #
    # 已知限制：形状与产量 1:1 耦合（加生长期产素必然加总产量）。12 批实测 λ=0.60 时
    #   产量 Δ 全为正（均值 +5.4pp、max +28pp），撞 86/86 ±5% 红线 ⇒ **默认必须为 0**，
    #   只用于批级标定（D-51），且可行域边界呈崖状（b22 在 mup×0.78 崩到 -67.5%）。
    #
    # λ=0（默认）⇒ 走 else 分支：_mu_p_rp = mu_p、_rp_gate = P_inhib，
    #   r_p 与改动前**逐字相同**（b3/b22 max|Δ| = 0.000e+00）。
    if mu_p_growth:
        _mu_act_rp = ((r_e1 + r_b0 - r_d1) / total_X) if total_X > 1e-9 else 0.0
        _mu_act_rp = min(1.0, max(0.0, _mu_act_rp / mux_max))
        _mu_p_rp = mu_p / (1.0 - mu_p_growth)
        _rp_gate = (1.0 - mu_p_growth) * P_inhib + mu_p_growth * _mu_act_rp
    else:
        _mu_p_rp = mu_p
        _rp_gate = P_inhib
    r_p = _mu_p_rp * rho_a0 * v_a1 * _rp_gate * DO_2_inhib_P * PAA_inhib_P - mu_h * y[3]
    r_m1 = m_s * rho_a0 * v_a1 * s / (K_v + s)
    r_d4 = mu_a * a_3

    # R130: 液泡化修复（形态学结构补全）。原实现 n_k=0 近似使 A1→A3 转移恒为 0
    # → A3/A4 永远为 0 → 无老菌丝可衰亡 → X_offline 不衰减（D6 唯一 critical 根因）。
    # !! R137 审计：本修复**只加了代码路径，参数未接线** —— 86/86 批黄金参数中无 k_vac，
    #    params.get("k_vac", 0.0) 恒取 0，故 r_vac ≡ 0，A3/A4 至今仍恒为 0。
    #    反事实（r137_morphology_probe）显示接线**无收益且有害**：k_vac=0.001 时 debris 仅 8.5%
    #    但产量已 −19.3%，而 peakR 反而 1.093→1.106。原因是 r_vac 是 A1→A3 的内部转移
    #    （da_3=r_vac−r_d4、da_4=r_d4，在 X_1 求和中抵消），而 r_p ∝ v_a1 ∝ a1 ——
    #    产素对 a1 一阶敏感、总生物量二阶敏感。接线需同时重标 μp，不能单独开。
    #    见 docs/r137_round_report.md §1、docs/r137_debt_ledger.md D-7。
    # 物理依据（Birol 2002 形态学结构 + Nestaas & Wang 1983 退化=比生长速率函数）：
    #   A1（活跃菌丝）随时间液泡化 → A3（部分液泡化）→ A4（完全液泡化/衰亡）。
    #   Nestaas & Wang：细胞退化是比生长速率的函数，μ > μ_min 时退化被抑制。
    #   门控用**实际比生长速率** μ_actual = r_e1/a_0 = μ_e·s/(K_e+s)，非最大 μ_e。
    #   S 耗尽时 μ_actual → 0，液泡化启动 → 衰亡 → X_offline 衰减。
    #   青霉素生产由低底物门控（P_inhib, idiophase），液泡化若在生长期启动
    #   会抽干 A1 → 生长减速 → S 不降 → P_inhib 不激活 → 产量崩塌（R130g 扫描证实）。
    #   实际比生长速率用总生物量的实际增长率：μ_actual = (r_e1 + r_b0 - r_d1) / total_X
    #   （排除稀释，反映真实代谢生长）
    _mu_actual = (r_e1 + r_b0 - r_d1) / total_X if total_X > 1e-9 else 0.0
    _vac_gate = max(0.0, 1.0 - _mu_actual / mu_vac_ref) if mu_vac_ref > 0 else 0.0
    r_vac = k_vac * a_1 * _vac_gate

    r_k = r_0 + 8 * delta_r  # k=10 → r_0+(10-2)*delta_r
    r_m = r_0 + 10 * delta_r  # k=12 → r_0+(12-2)*delta_r
    n_k = 0.0  # n9 = 0

    # 液泡 ODE — 不积分

    # ---- 体积/重量 ----
    F_evp = y[4] * alpha_evp * (np.exp(2.5 * (y[7] - T0) / (Tv - T0)) - 1)
    pho_feed = (c_s / 1000.0) * pho_g + (1 - c_s / 1000.0) * pho_w
    dilution = Fs + Fb + Fa + Fw - F_evp + Fpaa
    dV1 = Fs + Fb + Fa + Fw + F_discharge / (pho_b / 1000.0) - F_evp + Fpaa
    dWt = (Fs * pho_feed / 1000.0 + pho_oil / 1000.0 * Foil + Fb + Fa + Fw
           + F_discharge - F_evp + Fpaa * pho_paa / 1000.0)

    # ---- 生物量区 ODE ----
    # R129: ODE 级衰亡项 -kd·y[comp]（各组分比例减少），可选 time-varying（t>=death_start 激活）
    # R130: 液泡化修复 —— A1→A3 转移 r_vac（原 n_k=0 近似恒为 0，A3/A4 永远为 0）
    # R130: 衰亡底物回收 —— 死菌丝经自溶释放胞内物质回底物 S（death_recycle 比例）
    # R130b: 直接晚期衰亡 —— 当实际比生长速率低于阈值时，对总生物量施加衰亡项
    #   物理依据（Nestaas & Wang 1983）：细胞退化是比生长速率的函数，μ > μ_min 时退化被抑制。
    #   死菌丝自溶（autolysis）释放胞内碳源循环利用，非单纯移除。
    #   late_death_rate: 晚期衰亡速率（h⁻¹），0=off 默认
    #   mu_death_ref: 衰亡生长率阈值（h⁻¹），μ_actual < 此值时衰亡启动
    #   death_recycle: 死菌丝底物回收比例（0~1）
    _mu_actual = (r_e1 + r_b0 - r_d1) / total_X if total_X > 1e-9 else 0.0
    _kd_active = biomass_death_rate if t >= death_start else 0.0
    _late_death_gate = max(0.0, 1.0 - _mu_actual / mu_death_ref) if mu_death_ref > 0 else 0.0
    _late_kd = late_death_rate * _late_death_gate
    if death_mode == 1:
        # ---- R141 形态学衰亡链（D-8 闭合）——**叠加**在等比项之上，不替换 ----
        # 关键：黄金参数里 `biomass_death_rate` 本来就非零（b8 kd=0.001/death_start=100），
        # 所以 mode 1 必须保留等比项，否则 age=lysis=0 时也不能逐位回归。
        # 新增的是"老化"（A1→A3，X 内转移，不动总量）与"溶菌"（A3/A4 出系统）。
        # 这样死菌池 a3/a4 首次非零，"只移除死菌"这一机制才可表达。
        _kd_prop = (_kd_active + _late_kd) * total_X
        _age_on = age_rate if t >= (death_start if age_start is None else age_start) else 0.0
        _age_gate = max(0.0, 1.0 - _mu_actual / age_mu_ref) if age_mu_ref > 0 else 0.0
        r_age = _age_on * _age_gate * y[12]                  # A1 → A3（X 内转移）
        r_lys = lysis_rate * (y[13] + y[14])                 # A3+A4 → 出系统
        # 回收量 = 等比项×death_recycle + 溶菌项×lysis_recycle（两通道各用各的系数）
        _kd_total = _kd_prop + r_lys
        _recycle_coef = ((death_recycle * _kd_prop + lysis_recycle * r_lys) / _kd_total
                         if _kd_total > 1e-12 else death_recycle)
        da_0_dt = (r_b0 - r_d1 - y[11] * dilution / y[4]
                   - _kd_active * y[11] - _late_kd * y[11])
        da_1_dt = (r_e1 - r_b0 + r_d1 - r_vac - r_age
                   - y[12] * dilution / y[4] - _kd_active * y[12] - _late_kd * y[12])
        da_3_dt = (r_vac + r_age - r_d4 - r_lys
                   - y[13] * dilution / y[4] - _kd_active * y[13] - _late_kd * y[13])
        da_4_dt = (r_d4 - r_lys - y[14] * dilution / y[4]
                   - _kd_active * y[14] - _late_kd * y[14])
    else:
        # ---- mode 0：现行等比移除（默认，逐位不变） ----
        _kd_total = (_kd_active + _late_kd) * total_X
        _recycle_coef = death_recycle
        da_0_dt = r_b0 - r_d1 - y[11] * dilution / y[4] - _kd_active * y[11] - _late_kd * y[11]
        da_1_dt = (r_e1 - r_b0 + r_d1 - r_vac
                   - y[12] * dilution / y[4] - _kd_active * y[12] - _late_kd * y[12])
        da_3_dt = (r_vac - r_d4
                   - y[13] * dilution / y[4] - _kd_active * y[13] - _late_kd * y[13])
        da_4_dt = r_d4 - y[14] * dilution / y[4] - _kd_active * y[14] - _late_kd * y[14]
    dP_dt = r_p - y[3] * dilution / y[4]
    X_1 = da_0_dt + da_1_dt + da_3_dt + da_4_dt
    X_t = total_X

    # ---- 热量 ----
    Qrxn_X = X_1 * Y_QX * y[4] * Y_O2_X / 1000.0
    Qrxn_P = dP_dt * Y_QX * y[4] * Y_O2_P / 1000.0
    Qrxn_t = Qrxn_X + Qrxn_P
    if Qrxn_t < 0:
        Qrxn_t = 0.0

    N = RPM / 60.0
    D_imp = 2 * r_imp
    unaerated_power = n_imp * Po * pho_b * N**3 * D_imp**5
    P_g = 0.706 * (((unaerated_power**2) * N * D_imp**3) / (Fg**0.56)) ** 0.45
    P_n = P_g / unaerated_power
    variable_power = (n_imp * Po * pho_b * N**3 * D_imp**5 * P_n) / 1000.0

    # ---- 主状态 ODE ----
    dy = np.zeros(N_STATES)

    # S
    dy[0] = (-r_se1 - r_sb0 - r_m0 - r_m1
             - (Y_sP * _mu_p_rp * rho_a0 * v_a1 * _rp_gate * DO_2_inhib_P * PAA_inhib_P)
             + Fs * c_s / y[4] + Foil * c_oil / y[4] - y[0] * dilution / y[4]
             + _kd_total * _recycle_coef)

    # DO2
    V_s = Fg / (np.pi * r * r)
    T = y[7]
    V = y[4]
    V_m = y[4] / 1000.0
    P_air = (V_s * R * T * V_m / (22.4 * h_b)) * np.log(1 + pho_b * 9.81 * h_b / (pressure_top * 1e5))
    P_t1 = variable_power + P_air
    vis_scaled = viscosity / 100.0
    oil_f = Foil / V
    kla = alpha_kla_eff * ((V_s ** a) * ((P_t1 / V_m) ** b) * (vis_scaled ** c)) * (1 - oil_f ** d)
    OUR = -X_1 * Y_O2_X - m_O2_X * X_t - dP_dt * Y_O2_P
    OTR = kla * (DOstar_tp - y[1])
    dy[1] = OUR + OTR - y[1] * dilution / y[4]

    # O2 off-gas
    Vg = epsilon * V_m
    Qfg_in = 60 * Fg * 1000 * 32 / 22.4
    denom = 1 - y[2] - y[27] / 100.0
    if denom < 0.05:
        denom = 0.05  # 防爆炸（O2 浓度接近 N2_in 时分母→0）
    Qfg_out = 60 * Fg * (N2_in / denom) * 1000 * 32 / 22.4
    dy[2] = (Qfg_in * O_2_in - Qfg_out * y[2] - 0.001 * OTR * V_m * 60) / (Vg * 28.97 * 1000 / 22.4)

    # P
    #   R138: 补入青霉素水解降解项（一阶，k_deg 单位 1/h）。
    #   依据：V3 化验 P 在 44 个可估批次上给出 k_deg = 0.00607 /h（半衰期 114 h），
    #   IQR 仅 0.00568–0.00621（跨批变异 <9%），与青霉素 G 在 37°C / pH 6.5 下的
    #   文献水解半衰期一致；而原方程 dy[3]=r_p - dil 只增不减，无法表达峰后下降
    #   （100 批中 53 批存在峰后下降，40 批降幅 >8%）。
    #   默认 p_deg_rate=0.0 → 与原实现逐位一致（零回归），仅显式传参时激活。
    dy[3] = r_p - p_deg_rate * y[3] - y[3] * dilution / y[4]

    # V, Wt
    dy[4] = dV1
    dy[5] = dWt

    # pH（[H+] 表示，basic 分支内部切换为 [OH-] 表示）
    pH_dis = Fs + Foil + Fb + Fa + F_discharge + Fw
    y7 = y[6]
    if -np.log10(np.maximum(y7, 1e-12)) < 7:  # acidic
        cb = -abc
        ca = abc
        y7_use = y7
        pH_balance = 0
    else:  # basic
        cb = abc
        ca = -abc
        y7_use = 1e-14 / y7 - y7
        pH_balance = 1
    B = (y7_use * y[4] + ca * Fa * step1 + cb * Fb * step1) / (y[4] + Fb * step1 + Fa * step1)
    B = -B  # MATLAB indpensim_ode.m line 495: B = -B（符号约定，漏掉会导致 pH 漂移）
    ph_prod = r_b0 + r_e1 + r_d4 + r_d1 + m_ph * total_X
    # R145 / D-32：pH 方程里的 r_p 用的是**净产酸口径**。默认（False）逐字对齐 MATLAB：
    # 水解项 `-mu_h·P` 经 `+gamma1*r_p` 后变成"碱化"。而青霉素 G 水解生成青霉噻唑酸
    # （一元羧酸，pKa≈2.7）应**产酸**。ph_hyd_acid=True 时把该通道翻正：
    #   r_p_ph = r_p + 2·mu_h·P   （等价于 pH 方程里对 mu_h·P 取 +gamma1 而非 -gamma1）
    # 只改 pH 方程，不改 dy[3]（产品量仍按 r_p 走）。默认 False ⇒ 逐位不变。
    # R147 / D-36：把"水解项在 pH 方程里怎么算"提升成显式三态口径。
    #   _adj = 0 → 水解不计入质子平衡（"净质子变化≈0"）
    #   _adj = 1 → 只保留产素项（等价 r_p + mu_h·P）
    #   _adj = 2 → 水解按产酸计入（R145 的 ph_hyd_acid，已证伪但保留作对照臂）
    # 默认 "net" + ph_hyd_acid=False ⇒ _adj=0 ⇒ 与改动前逐位相同。
    if ph_rp_mode == "prod_only":
        _rp_adj = 1.0
    elif ph_rp_mode == "all_acid":
        _rp_adj = 2.0
    elif ph_hyd_acid:  # "net" 默认下仍尊重 R145 的布尔开关（向后兼容）
        _rp_adj = 2.0
    else:
        _rp_adj = 0.0
    r_p_ph = r_p + _rp_adj * mu_h * y[3]
    # D4 pH 扰动故障（注入酸 → 增加 [H+] → pH 下降）
    ph_acid = 0.0
    if _fault_active and fault_type == 2:
        ph_acid = fault_magnitude * _env / y[4]
    # R156 / D-55：`basic` 分支的链式法则修正（ph_fix=1；默认 0 = 逐字原文）。
    #
    # 病灶（tools/r156_ph_probe.py 逐点实测）：状态 y[6] 是 **H+**，但 basic 分支里
    #   y7_use = Kw/H+ - H+ ≈ [OH-]，驱动项 (u_eq - u_now) 也是 OH- 口径，却被直接
    # 当成 d[H+]/dt 用。pH>=7.6 时实测 |dy[6]|/OH- = 0.994（量级完全由 OH- 决定），
    # 而 OH-/H+ = 10^(2(pH-7))：pH 8 时 100 倍、pH 9 时 1e4 倍 => 一步把 H+ 打成负数
    # => guards() 钳到 3.0。pH 6.99-7.05 区间已有 95% 的 dy[6] < 0（该回酸时反而更碱）。
    #
    # 正确关系：u = Kw/H+ - H+  =>  du/dH+ = -(Kw/H+^2 + 1)
    #           d[H+]/dt = (du/dt) / (-(Kw/H+^2 + 1))
    # du/dt 的表达式（产酸/加碱源项 + 平衡回拉）本来就是 u 的导数，除以雅可比即可。
    # **不动点不变**：u = u_eq <=> H+ = H_eq，平衡值与原文完全相同，只改趋近路径的阻尼。
    # 物理意义：碱性条件下 H+ 变化对 pH 的影响被 OH- 缓冲，原式把这个阻尼丢了。
    # 该项不改任何动力学系数，故不属于"标定"，属"解锁"（见 D-55）。
    if ph_fix == 1 and pH_balance == 1:
        _u_eq = (-B - np.sqrt(B**2 + 4e-14)) / 2.0
        _du_dt = (-gamma1 * ph_prod - gamma1 * r_p_ph - gamma2 * pH_dis + ph_acid
                  + (_u_eq - y7_use))
        _h = max(float(y7), 1e-12)
        _jac = -(1e-14 / (_h * _h) + 1.0)
        dy[6] = _du_dt / _jac
    elif pH_balance == 1:  # basic（ph_fix=0：与改动前逐字相同）
        dy[6] = (-gamma1 * ph_prod - gamma1 * r_p_ph - gamma2 * pH_dis + ph_acid
                 + ((-B - np.sqrt(B**2 + 4e-14)) / 2 - y7_use))
    else:  # acidic
        dy[6] = (gamma1 * ph_prod + gamma1 * r_p_ph + gamma2 * pH_dis + ph_acid
                 + ((-B + np.sqrt(B**2 + 4e-14)) / 2 - y7_use))

    # T
    Ws = P_t1
    Qcon = U_jacket * A_c * (y[7] - Tair)
    dQ_dt = (Fs * pho_feed * C_ps * (Tf - y[7]) / 1000.0
             + Fw * pho_w * C_pw * (Tw - y[7]) / 1000.0
             - F_evp * pho_b * C_pw / 1000.0
             - delta_H_evap * F_evp * pho_w / 1000.0
             + Qrxn_t + Ws
             - (alpha_1 / 1000.0) * Fc ** (beta_T + 1)
             * ((y[7] - Tcin) / (Fc / 1000.0 + (alpha_1 * (Fc / 1000.0) ** beta_T) / 2 * pho_b * C_ps))
             - (alpha_1 / 1000.0) * Fh ** (beta_T + 1)
             * ((y[7] - Th) / (Fh / 1000.0 + (alpha_1 * (Fh / 1000.0) ** beta_T) / 2 * pho_b * C_ps))
             - Qcon)
    dy[7] = dQ_dt / ((y[4] / 1000.0) * C_pw * pho_b)
    dy[8] = dQ_dt

    # viscosity
    # R77 健壮性修复：a_0 为负体力试探步（BDF 中间状态）时 3·a_0**(1/3) 会 NaN，
    # 危害远超单批（ stif f LU 直接 ValueError 炸掉任何池级驱动链）。
    # 物理上菌丝量非负 → 贡献钳 0；与 guards() 的后验钳一致。
    a_0_pos = a_0 if a_0 > 0 else 0.0
    # R133：vis_decay_rate 是一阶黏度松弛项（h⁻¹），物理上对应"发酵液稀释/剪切降解"
    # 造成的黏度损失。默认 0.0 = 关闭，与 MATLAB 原文逐字一致（零回归）。
    # 之所以不能用 t2 调：第二 sigmoid 是**乘在生成项上的增益**，向下移动 t2 会同时
    # 压掉前 150 h 的生成（增益从 0.5 掉到 <0.05），无法只压末段。
    vis_state = y[9] if y[9] > 0 else 0.0
    dy[9] = (vis_scale * 3 * (a_0_pos ** (1.0 / 3.0))
             * (1 / (1 + np.exp(-k1 * (t - t1))))
             * (1 / (1 + np.exp(-k2 * (t - t2))))
             - k3 * Fw
             - vis_decay_rate * vis_state)

    # A_t1
    dy[10] = y[11] + y[12] + y[13] + y[14]

    # 菌丝区
    dy[11] = da_0_dt
    dy[12] = da_1_dt
    dy[13] = da_3_dt
    dy[14] = da_4_dt

    # 液泡 — 准稳态近似，不积分
    dy[15] = 0.0  # n0
    dy[16] = 0.0  # n1
    dy[17] = 0.0  # n2
    dy[18] = 0.0  # n3
    dy[19] = 0.0  # n4
    dy[20] = 0.0  # n5
    dy[21] = 0.0  # n6
    dy[22] = 0.0  # n7
    dy[23] = 0.0  # n8
    dy[24] = 0.0  # n9
    dy[25] = 0.0  # nm
    dy[26] = 0.0  # phi0

    # CO2
    total_X_CO2 = y[11] + y[12]
    CER = total_X_CO2 * q_co2 * V
    dy[27] = (((60 * Fg * 44 * 1000 / 22.4) * C_CO2_in + CER
               - (60 * Fg * 44 * 1000 / 22.4) * y[27]) / (Vg * 28.97 * 1000 / 22.4))

    # 溶解 CO2
    Henrys_c_co2 = np.exp(11.25 - 395.9 / (y[7] - 175.9)) / (44 * 100)
    C_star_CO2 = (total_pressure * y[27]) / Henrys_c_co2
    dy[28] = kla * delta_c_0 * (C_star_CO2 - y[28]) - y[28] * dilution / y[4]

    # PAA
    # D9(b) 相门控（R121 根因修复）：PAA 消耗项在生长相（高 s）被抑制，
    # 仅在生产相（低 s）激活。门控函数基于底物浓度 s 的 Michaelis-Menten 型 + floor：
    #   f_paa = floor + (1-floor) * mean_P / (mean_P + s)
    #   s→∞ → f_paa→floor（营养期抑制）  s→0 → f_paa→1.0（生产期允许）
    # R123 修复：m_PAA 维护消耗目标变量（P→total_X），对齐 MATLAB 原文。
    #   原代码用 y[3]=P（青霉素），MATLAB indpensim_ode.m 用 X（生物量）。
    #   m_PAA=1.05 g/g/h 是每克生物量每消耗的 PAA 维护系数 → 应正比于 X。
    # R123c: 一阶 PAA 降解项（paa_degrad_rate），控制门控期间的生长相 PAA 累积。
    #   物理依据：PAA（苯乙酸）在发酵液中会缓慢降解（氧化/水解），一阶速率正比于
    #   PAA 浓度。门控抑制 Y_PAA_X*X_1 消耗后，喂食项 Fpaa*PAA_c/V 持续累积 PAA，
    #   降解项作为「被动消耗」补充，防止幅度过冲。默认 0=不启用（黄金回归守护）。
    # R124: 反相门控降解（paa_degrad_inverse_gate）——降解仅在门控关闭时激活。
    #   物理依据：PAA 的「溢出代谢」（overflow metabolism）在生长相活跃——
    #   当青霉素合成途径（idiophase）未启动时，PAA 通过替代酶系被代谢消耗。
    #   生产相时该途径关闭，PAA 留给青霉素合成前体消耗。
    #   数学：degrad = rate * PAA * (1 - f_paa)——生长相 f_paa≈floor → (1-f_paa)≈1-floor
    #   （降解全速）；生产相 f_paa≈1 → (1-f_paa)≈0（降解关闭）。
    #   修复 R123c 的时序崩溃问题：恒定降解在生产相也消耗 PAA → 峰值提前。
    m_paa_target = total_X if paa_maintenance_target == 1 else y[3]
    # 先计算 f_paa（用于反相门控降解）
    if paa_gate_mode in (1, 2):
        _denom = mean_P + s
        f_paa = paa_gate_floor + (1 - paa_gate_floor) * (mean_P / _denom if _denom > 0 else 1.0)
    else:
        f_paa = 1.0
    # 降解项：反相门控时乘以 (1-f_paa)，仅门控关闭时激活
    if paa_degrad_rate > 0.0:
        if paa_degrad_inverse_gate:
            degrad_paa = paa_degrad_rate * y[29] * (1.0 - f_paa)
        else:
            degrad_paa = paa_degrad_rate * y[29]
    else:
        degrad_paa = 0.0
    if paa_gate_mode == 0:
        dy[29] = (Fpaa * PAA_c / y[4] - Y_PAA_P * dP_dt - Y_PAA_X * X_1
                  - m_PAA * m_paa_target - degrad_paa - y[29] * dilution / y[4])
    elif paa_gate_mode == 1:
        # 仅门控 X_1 项（Y_PAA_X * X_1）
        dy[29] = (Fpaa * PAA_c / y[4] - Y_PAA_P * dP_dt - Y_PAA_X * X_1 * f_paa
                  - m_PAA * m_paa_target - degrad_paa - y[29] * dilution / y[4])
    elif paa_gate_mode == 2:
        # 门控 X_1 + dP_dt 项
        dy[29] = (Fpaa * PAA_c / y[4] - Y_PAA_P * dP_dt * f_paa - Y_PAA_X * X_1 * f_paa
                  - m_PAA * m_paa_target - degrad_paa - y[29] * dilution / y[4])
    else:
        dy[29] = (Fpaa * PAA_c / y[4] - Y_PAA_P * dP_dt - Y_PAA_X * X_1
                  - m_PAA * m_paa_target - degrad_paa - y[29] * dilution / y[4])

    # NH3
    X_C_nitrogen = (-r_b0 - r_e1 - r_d1 - r_d4) * Y_NX
    P_C_nitrogen = -dP_dt * Y_NP
    dy[30] = ((NH3_shots * N_conc_shot) / y[4] + X_C_nitrogen + P_C_nitrogen
              - m_N * total_X + (1.0 * N_conc_paa * Fpaa / y[4])
              + N_conc_oil * Foil / y[4] - y[30] * dilution / y[4])

    # mup, mux
    dy[31] = mu_p
    dy[32] = mu_e

    return dy


def compute_mu_e(y, inp1, par):
    """计算 mu_e（有效比生长速率），供 k>65 自适应使用。

    与 rhs 中的 mu_e 计算保持一致，但仅返回标量值。
    MATLAB 中 X.mu_X_calc.y 记录的就是这个值。
    """
    # ---- 参数提取（索引与 rhs 一致） ----
    mux_max = par[1] + inp1[18]       # par[1] + distMuX
    K1 = par[65]
    K2 = par[66]
    r = par[37]
    epsilon = par[40]
    R = par[42]                       # 气体常数 8.314
    Henrys_c = par[35]
    X_crit_DO2 = par[43]
    A_inhib = par[45]
    k_g = par[58]
    k_d = par[59]
    Eg = par[56]
    Ed = par[57]
    X_crit_N = par[73]
    X_crit_PAA = par[78]
    X_crit_CO2 = par[92]

    Tcin = par[48] + inp1[23]          # par[48] + distTcin
    O_2_in = par[99] + inp1[24]        # par[99] + distO_2_in

    inhib_flag = inp1[0]
    pressure = inp1[10]

    # ---- 过程参数 ----
    pho_b = 1100.0 + y[3] + y[11] + y[12] + y[13] + y[14]
    h_b = (y[4] / 1000.0) / (np.pi * r * r) * (1 - epsilon)
    pressure_bottom = 1 + pressure + (pho_b * h_b) * 9.81 * 1e-5
    pressure_top = 1 + pressure
    log_mean_pressure = (pressure_bottom - pressure_top) / np.log(pressure_bottom / pressure_top)
    total_pressure = log_mean_pressure

    DOstar_tp = (total_pressure * O_2_in) / Henrys_c

    # ---- 抑制开关 ----
    if inhib_flag == 0:
        return mux_max
    elif inhib_flag == 1:
        pH_inhib = 1.0 / (1 + y[6] / K1 + K2 / y[6])
        NH3_inhib = 1.0
        T_inhib = 1.0
        CO2_inhib = 1.0
        DO_2_inhib_X = 0.5 * (1 - np.tanh(A_inhib * (X_crit_DO2 * DOstar_tp - y[1])))
        PAA_inhib_X = 1.0
    else:  # inhib_flag == 2
        pH_inhib = 1.0 / (1 + y[6] / K1 + K2 / y[6])
        NH3_inhib = 0.5 * (1 - np.tanh(A_inhib * (X_crit_N - y[30])))
        T_inhib = k_g * np.exp(-(Eg / (R * y[7]))) - k_d * np.exp(-(Ed / (R * y[7])))
        CO2_inhib = 0.5 * (1 + np.tanh(A_inhib * (X_crit_CO2 - y[28] * 1000.0)))
        DO_2_inhib_X = 0.5 * (1 - np.tanh(A_inhib * (X_crit_DO2 * DOstar_tp - y[1])))
        PAA_inhib_X = 0.5 * (1 + np.tanh(X_crit_PAA - y[29]))

    return mux_max * pH_inhib * NH3_inhib * T_inhib * DO_2_inhib_X * CO2_inhib * PAA_inhib_X


def default_initial_state():
    """默认初始状态（对齐 MATLAB x0 结构，见 indpensim.m）。"""
    return np.array([
        0.0,      # S
        0.0,      # DO2
        0.0,      # O2
        0.0,      # P
        58000.0,  # V
        62000.0,  # Wt
        10.0 ** -6.5,  # pH → [H+] (pH 6.5)
        298.0,    # T
        0.0,      # Q
        0.0,      # vis
        0.0,      # A_t1
        0.0,      # A0
        0.0,      # A1
        0.0,      # A3
        0.0,      # A4
    ] + [0.0] * 10 + [0.0, 0.0, 0.0, 0.0, 0.0])  # n0..n9, nm, phi0, CO2, CO2d


def state_names():
    return ["S", "DO2", "O2", "P", "V", "Wt", "pH_H", "T", "Q", "vis",
            "A_t1", "A0", "A1", "A3", "A4",
            "n0", "n1", "n2", "n3", "n4", "n5", "n6", "n7", "n8", "n9",
            "nm", "phi0", "CO2", "CO2d", "PAA", "NH3", "mup", "mux"]
