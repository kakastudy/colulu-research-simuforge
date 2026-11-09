# -*- coding: utf-8 -*-
"""IndPenSim 机理模型参数表（105 参数），逐项对照 MATLAB Parameter_list.m。

par[0]  : mu_p       青霉素比生长速率 1/h
par[1]  : mux_max    生物量最大比生长速率 1/h
par[2]  : ratio_mu_e_mu_b = 0.4
par[3]  : P_std_dev = 0.0015 g/L
par[4]  : mean_P = 0.002 g/L
par[5]  : mu_v = 1.71e-4 g/g/h
par[6]  : mu_a = 3.5e-3 1/h
par[7]  : mu_diff = 5.36e-3 1/h
par[8]  : beta_1 = 0.006
par[9]  : K_b = 0.05 g/L
par[10] : K_diff = 0.75 g/L
par[11] : K_diff_L = 0.09 g/L
par[12] : K_e = 0.009 g/L
par[13] : K_v = 0.05 g/L
par[14] : delta_r = 0.75e-4 cm
par[15] : k_v = 3.22e-5 cm/h
par[16] : D = 2.66e-11 cm^2/h
par[17] : rho_a0 = 0.35 g/cm^3
par[18] : mu_h_scale = 1.0 (原 rho_d=0.18，因 n_k=0 完全休眠可重用；R129ah)
par[19] : mu_h = 0.003 1/h
par[20] : r_0 = 1.5e-4 cm
par[21] : delta_0 = 1e-4 cm
par[22] : Y_sx = 1.85 g/g
par[23] : Y_sP = 0.9 g/g
par[24] : m_s = 0.029 g/g/h
par[25] : c_oil = 1000 g/L  （MATLAB Parameter_list.m 原值；V3 数据证实油进料携带底物，
        必须用 1000 才能复现 S 早期累积——Foil*c_oil/V ≈ 0.38 g/L/h）
par[26] : c_s = 600 g/L
par[27] : Y_O2_X = 650 mg/g
par[28] : Y_O2_P = 160 mg/g
par[29] : m_O2_X = 17.5 mg/g
par[30] : alpha_kla  (输入)
par[31] : a = 0.38
par[32] : b = 0.34
par[33] : c = -0.38
par[34] : d = 0.25
par[35] : Henrys_c = 0.0251 bar·L/mg
par[36] : n_imp = 3
par[37] : r = 2.1 m
par[38] : r_imp = 0.85 m
par[39] : Po = 5
par[40] : epsilon = 0.1
par[41] : g = 9.81 m/s^2
par[42] : R = 8.314 J/mol/K
par[43] : X_crit_DO2 = 0.1 %
par[44] : P_crit_DO2 = 0.3 %
par[45] : A_inhib = 1
par[46] : Tf = 288 K
par[47] : Tw = 288 K
par[48] : Tcin = 285 K
par[49] : Th = 333 K
par[50] : Tair = 290 K
par[51] : C_ps = 5.9 kJ/kg/K
par[52] : C_pw = 4.18 kJ/g/K
par[53] : delta_H_evap = 2430.7 kJ/kg
par[54] : U_jacket = 36 kW/m^2/K
par[55] : A_c = 105 m^2
par[56] : Eg = 1.488e4 J/mol
par[57] : Ed = 1.7325e5 J/mol
par[58] : k_g = 450
par[59] : k_d = 0.25e30
par[60] : Y_QX = 25 kJ/g
par[61] : abc = 0.033 mol/L
par[62] : gamma1 = 0.0325e-5 mol H+/g
par[63] : gamma2 = 2.5e-11 mol H+/g
par[64] : m_ph = 0.0025 mol H+/g/h
par[65] : K1 = 1e-5 mol/L
par[66] : K2 = 2.5e-8 mol/L
par[67] : N_conc_oil = 20000 mg/L
par[68] : N_conc_paa (输入) g/L
par[69] : N_conc_shot = 400000 mg/kg
par[70] : Y_NX = 10 mg N2/g X
par[71] : Y_NP = 80 mg N2/g P
par[72] : m_N = 0.03 g/L/h
par[73] : X_crit_N = 150 mg/L
par[74] : PAA_c (输入) mg/L
par[75] : Y_PAA_P = 187.5 mg/g P
par[76] : Y_PAA_X = 45 mg/g X
par[77] : m_PAA = 1.05 g/g/h
par[78] : X_crit_PAA = 2400 mg/L
par[79] : P_crit_PAA = 200 mg/L
par[80] : B_1 = -64.29
par[81] : B_2 = -1.825
par[82] : B_3 = 0.3649
par[83] : B_4 = 0.128
par[84] : B_5 = -4.9496e-4
par[85] : delta_c_o = 0.89
par[86] : k_3 = 0.005
par[87] : k1 = 0.001
par[88] : k2 = 0.0001
par[89] : t1 = 1 h
par[90] : t2 = 250 h
par[91] : q_co2 = 0.120 mg CO2/g X
par[92] : X_crit_CO2 = 7570 mg/L
par[93] : alpha_evp = 5.24e-4 L/h
par[94] : beta_T = 2.88
par[95] : pho_g = 1540 kg/m^3
par[96] : pho_oil = 900 kg/m^3
par[97] : pho_w = 1000 kg/m^3
par[98] : pho_paa = 1000 kg/m^3
par[99] : O_2_in = 0.21 %
par[100] : N2_in = 0.79 %
par[101] : C_CO2_in = 0.033 %
par[102] : Tv = 373 K
par[103] : T0 = 273 K
par[104] : alpha_1 = 2451.8 kJ/m^3
"""

import numpy as np


def make_params(x0=None, alpha_kla=90.0, N_conc_paa=0.5, PAA_c=200.0,
                mup=0.012, mux=0.1, c_oil=1000.0):
    """返回 105 维参数向量（对齐 MATLAB Parameter_list.m 顺序）。

    x0: dict，含 mup/mux（初始比速率）；alpha_kla/N_conc_paa/PAA_c/c_oil 为输入量。
    c_oil: 油进料底物浓度 g/L。MATLAB Parameter_list.m 写 1000；V3 数据 S 通道
           早期累积速率证实必须用 1000（Foil*c_oil/V ≈ 0.38 g/L/h 是 S 早期上升的主因）。
    """
    mup = mup if x0 is None else x0.get("mup", mup)
    mux = mux if x0 is None else x0.get("mux", mux)
    p = np.array([
        mup, mux, 0.4, 0.0015, 0.002, 1.71e-4, 3.5e-3, 5.36e-3, 0.006, 0.05,
        0.75, 0.09, 0.009, 0.05, 0.75e-4, 3.22e-5, 2.66e-11, 0.35, 1.0, 0.003,
        1.5e-4, 1e-4,
        1.85, 0.9, 0.029, c_oil, 600.0, 650.0, 160.0, 17.5, alpha_kla,
        0.38, 0.34, -0.38, 0.25,
        0.0251, 3, 2.1, 0.85, 5, 0.1, 9.81, 8.314, 0.1, 0.3, 1,
        288.0, 288.0, 285.0, 333.0, 290.0, 5.9, 4.18, 2430.7, 36.0, 105.0,
        1.488e4, 1.7325e5, 450.0, 0.25e30, 25.0, 0.033, 0.0325e-5, 2.5e-11,
        0.0025, 1e-5, 2.5e-8, 20000.0, N_conc_paa, 400000.0, 10.0, 80.0, 0.03,
        150.0, PAA_c,
        187.5, 45.0, 1.05, 2400.0, 200.0,
        -64.29, -1.825, 0.3649, 0.128, -4.9496e-4,
        0.89, 0.005, 0.001, 0.0001, 1.0, 250.0, 0.120, 7570.0, 5.24e-4, 2.88,
        1540.0, 900.0, 1000.0, 1000.0, 0.21, 0.79, 0.033, 373.0, 273.0, 2451.8,
    ], dtype=float)
    assert p.size == 105, f"params size {p.size} != 105"
    return p


# 参数名映射（索引 → 名称），供诊断输出
PARAM_NAMES = [
    "mu_p", "mux_max", "ratio_mu_e_mu_b", "P_std_dev", "mean_P", "mu_v", "mu_a",
    "mu_diff", "beta_1", "K_b", "K_diff", "K_diff_L", "K_e", "K_v", "delta_r",
    "k_v", "D", "rho_a0", "mu_h_scale", "mu_h", "r_0", "delta_0",
    "Y_sx", "Y_sP", "m_s", "c_oil", "c_s", "Y_O2_X", "Y_O2_P", "m_O2_X",
    "alpha_kla", "a", "b", "c", "d",
    "Henrys_c", "n_imp", "r", "r_imp", "Po", "epsilon", "g", "R",
    "X_crit_DO2", "P_crit_DO2", "A_inhib",
    "Tf", "Tw", "Tcin", "Th", "Tair", "C_ps", "C_pw", "delta_H_evap",
    "U_jacket", "A_c", "Eg", "Ed", "k_g", "k_d", "Y_QX",
    "abc", "gamma1", "gamma2", "m_ph", "K1", "K2",
    "N_conc_oil", "N_conc_paa", "N_conc_shot", "Y_NX", "Y_NP", "m_N",
    "X_crit_N", "PAA_c",
    "Y_PAA_P", "Y_PAA_X", "m_PAA", "X_crit_PAA", "P_crit_PAA",
    "B_1", "B_2", "B_3", "B_4", "B_5",
    "delta_c_o", "k_3", "k1", "k2", "t1", "t2", "q_co2", "X_crit_CO2",
    "alpha_evp", "beta_T",
    "pho_g", "pho_oil", "pho_w", "pho_paa", "O_2_in", "N2_in", "C_CO2_in",
    "Tv", "T0", "alpha_1",
]
assert len(PARAM_NAMES) == 105
