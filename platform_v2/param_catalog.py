# -*- coding: utf-8 -*-
"""平台 v2 —— 参数目录层：从引擎源码**派生**工况可调面。

为什么必须派生，不能手写
------------------------
本项目的历史教训（D-38 / D-65 / R152）反复是同一类问题：
**「文档/清单说的」与「代码真的做的」分叉**，且分叉方向总是让平台看起来比实际更强。

R167 已经吃过一次：`ops_registry.OPERATORS` 里的 `hier_est` 不是可调用函数、
`conservation_metrics` 是模块名不是函数名，两者都被「文件存在 ⇒ 已装载」掩盖了。

所以本模块**不手写任何参数清单**，而是从 `candidate/indpensim/v0.1/simulate.py`
的 AST 里**解析** `params.get("...")` 调用 —— 那才是引擎真正接受的东西。
源码改了，目录自动跟着改；源码里没有的，平台就调不到。

派生结果按物理分组呈现，并把 L3 候选键单独标出（见 `L3_REJECTED`）。
L3 键是 R166 裁决里「不切换为默认生产口径」的那五类：
用户 2026-11-06 明确裁决 L3 **不处理**，故平台对其**硬拒绝**，
不允许通过前端参数表绕过。

分组依据（按 `simulate.py` 里的用途归并，不是按字母序）
--------------------------------------------------------
dynamics  动力学主干：比生长/比产率/维持/产率系数/化学计量
morphology 形态学衰亡链：菌丝区衰亡、自溶、液泡化
fault      故障注入：D4 三型 + R157 五种模式包络
disturb    时变扰动：8 路低通扰动（MATLAB filter 语义）+ AR(1) 方差注入
operation  操作量：MV 倍率、窗口缩放、补料闭环、碱液限幅
numeric    数值积分器：方法 / 容差 / 最大步长
initial    初值覆盖：生物量初值
ph         pH 通道：修正、模式、产酸口径
soft       软测量/观测：同化、门控

本模块**只读**引擎源码，不 import 引擎（避免拖慢前端首屏与引入副作用）；
由 `platform_v2/serve_v2.py` 在启动时调用一次并缓存。
"""
from __future__ import annotations

import ast
import os
import re
from typing import Any

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ENGINE_DIR = os.path.join(ROOT, "candidate", "indpensim", "v0.1")
SIMULATE_PY = os.path.join(ENGINE_DIR, "simulate.py")
PARAMS_PY = os.path.join(ENGINE_DIR, "params.py")
GOLDEN_PY = os.path.join(ENGINE_DIR, "golden_params.py")

# ---------------------------------------------------------------------------
# L3 拒绝键 —— R166 裁决 (a) 未执行，V1/V2/V3 候选不得进平台
# 口径与 platform/ops_registry.py 的 FORBIDDEN_KEYS 保持一致（同一裁决，同一清单）
# ---------------------------------------------------------------------------
L3_REJECTED: dict[str, str] = {
    "dist_noise_sigma": "R166/V2：8 路 AR(1) 方差注入，多轮寻优判定 NO_GO，未切默认",
    "dist_noise_seed": "R166/V2：方差注入种子，同上",
    "innovation_criteria": "R166/V1：逐通道创新判据，L3 未裁决",
    "k_dual": "R166/V3：alpha_kla 双约束查表，仅评测层，未写回",
    "alpha_kla_override": "R166/V3：写回黄金参数属 L3",
}


# ---------------------------------------------------------------------------
# 分组定义：键 -> (分组, 中文名, 单位, 控件类型, 默认值, 低限, 高限, 说明)
# 默认值取自源码中的 params.get(key, <default>)；low/high 是**已知有效域**，
# 不是物理上下限 —— 越域要显式告警而不是静默接受（对齐 I2 失败可见）。
# ---------------------------------------------------------------------------
_SPEC: dict[str, tuple] = {
    # ---- dynamics 动力学主干 ----
    "mux": ("dynamics", "最大比生长速率", "1/h", "slider", 0.41, 0.10, 0.80,
            "批次级随机参数（MATLAB: 0.41+0.025·randn）。鞍点分岔约 0.235–0.24。"),
    "mup": ("dynamics", "比产物速率", "1/h", "slider", 0.041, 0.010, 0.080,
            "批次级随机参数（0.041+0.0025·randn）。±0.001 可致产量摆动 60%（批 92 极端敏感）。"),
    "m_s": ("dynamics", "维持系数", "g/g/h", "slider", 0.029, 0.005, 0.045,
            "维持代谢项 r_m0 = m_s·A0/(K_diff+s)。MATLAB 固定参数；调低使残糖积累→CO2d 上升→崩溃耦合。"),
    "mu_h_scale": ("dynamics", "产物水解倍率", "×", "slider", 1.0, 0.1, 10.0,
            "乘于 mu_h（pH 依赖水解速率）。pH 6.5→3.0 时该因子变化 8.43 倍。"),
    "mu_h": ("dynamics", "产物水解基速", "1/h", "number", None, None, None,
            "par[18] 之外的独立水解基速覆盖口；与 mu_h_scale 通道不同。"),
    "Y_sP": ("dynamics", "底物→产物系数", "g/g", "slider", 0.9, 0.5, 1.2,
            "产品对底物的消耗系数。R136 引入，用于底物在菌体/产物间再分配。"),
    "Y_sX": ("dynamics", "底物→菌体系数", "g/g", "slider", None, None, None,
            "菌体对底物的消耗系数（par[22]）。"),
    "Y_NX": ("dynamics", "氮→菌体化学计量", "g/g", "slider", 10.0, 1.0, 100.0, "氮元素分配系数。"),
    "Y_NP": ("dynamics", "氮→产物化学计量", "g/g", "slider", 80.0, 1.0, 500.0, "氮元素分配系数。"),
    "Y_O2_X": ("dynamics", "氧→菌体化学计量", "g/g", "slider", 800.0, 1.0, 5000.0, "耗氧化学计量。"),
    "Y_O2_P": ("dynamics", "氧→产物化学计量", "g/g", "slider", 200.0, 1.0, 5000.0, "耗氧化学计量。"),
    "m_O2_X": ("dynamics", "菌体耗氧常数", "g/g/h", "slider", 15.0, 1.0, 100.0, "菌体比耗氧速率。"),
    "q_co2": ("dynamics", "单位生物量产CO2", "g/g/h", "slider", 0.12, 0.0, 1.0,
              "呼吸商相关项；影响 CO2d 抑制通道。"),
    "c_oil": ("dynamics", "油浓度", "mg/L", "number", 1000.0, None, None, "补料油浓度。"),
    "PAA_c": ("dynamics", "前体补料浓度", "mg/L", "number", 530000.0, None, None,
              "苯乙酸补料浓度（批次级随机：530000+20000·randn）。"),
    "N_conc_paa": ("dynamics", "前体补料氮浓度", "mg/L", "number", 150000.0, None, None,
                   "批次级随机：150000+2000·randn。"),
    "m_paa": ("dynamics", "前体维持速率", "mg/g/h", "slider", 1.0, 0.0, 10.0, "前体维持项。"),
    "Y_PAA_P": ("dynamics", "前体→产物系数", "g/g", "number", None, None, None, "前体转化系数。"),
    "Y_PAA_X": ("dynamics", "前体→菌体系数", "g/g", "number", None, None, None, "前体转化系数。"),
    "c_co2_in": ("dynamics", "进口CO2浓度", "mg/L", "number", None, None, None, "进气 CO2 背景。"),
    "gamma1": ("dynamics", "产酸系数 γ1", "-", "number", None, None, None,
               "pH 方程产酸侧系数（par[62]）。R149：悬崖在 0.985，一阶平移无振幅旋钮。"),
    "gamma2": ("dynamics", "产碱系数 γ2", "-", "number", None, None, None, "pH 方程碱侧系数（par[63]）。"),
    "m_ph": ("dynamics", "pH 维持系数", "-", "number", None, None, None, "pH 方程维持项（par[64]）。"),
    "abc": ("dynamics", "缓冲容量", "-", "slider", 0.033, 0.001, 0.5,
            "电荷平衡缓冲项（par[61]）。R149：压缩 pH 振幅的干净通道。"),

    # ---- morphology 形态学衰亡链 ----
    "biomass_death_rate": ("morphology", "生物量衰亡率", "1/h", "slider", 0.0, 0.0, 0.1,
                            "基础衰亡项。D-8 前提已被证伪（死菌仍计入 X）。"),
    "death_start": ("morphology", "衰亡起始时刻", "h", "number", 100.0, 0.0, 300.0, "衰亡启动时间。"),
    "death_recycle": ("morphology", "自溶回收率", "-", "slider", 0.0, 0.0, 1.0,
                      "死菌丝自溶回收底物比例（Nestaas & Wang 1983 物理依据）。"),
    "late_death_rate": ("morphology", "晚期衰亡率", "1/h", "slider", 0.0, 0.0, 0.05,
                        "生物龄 > 阈值的衰亡项；R130 引入以修正 X 衰减段。"),
    "mu_death_ref": ("morphology", "衰亡菌龄阈值", "1/h", "slider", 0.02, 0.0, 0.2, "衰亡触发菌龄。"),
    "k_vac": ("morphology", "液泡化速率", "-", "slider", 0.0, 0.0, 1.0,
              "液泡化转移率。R130：启用后灾难破坏产量（−59%~−100%）。"),
    "mu_vac_ref": ("morphology", "液泡化菌龄阈值", "1/h", "slider", 0.1, 0.0, 0.5, "液泡化触发菌龄。"),
    "death_mode": ("morphology", "衰亡模式", "0/1", "select", 0, None, None, "0=历史口径（逐位一致）；1=形态学链（D-8，已关闭不进生产）。"),
    "age_rate": ("morphology", "菌龄增速", "1/h", "number", 0.0, None, None, "菌龄累积速率。"),
    "age_start": ("morphology", "菌龄起点", "h", "number", None, None, None, "菌龄计时起点。"),
    "age_mu_ref": ("morphology", "菌龄参考μ", "1/h", "number", 0.02, None, None, "菌龄衰亡参考比生长速率。"),
    "lysis_rate": ("morphology", "自溶速率", "1/h", "number", 0.0, None, None, "菌丝自溶速率。"),
    "lysis_recycle": ("morphology", "自溶回收系数", "-", "number", 0.0, None, None, "自溶底物回收系数。"),

    # ---- fault 故障注入（D4 三型 + R157 五模式包络）----
    "fault_type": ("fault", "故障类型", "0-3", "select", 0, None, None,
                   "0=无；1=降KLa；2=注酸；3=减喂食。幅值单位见 fault_magnitude。"),
    "fault_start": ("fault", "故障起始", "h", "number", 0.0, 0.0, 300.0, "注入起始时刻。"),
    "fault_end": ("fault", "故障结束", "h", "number", 0.0, 0.0, 300.0, "注入结束时刻。"),
    "fault_magnitude": ("fault", "故障幅值", "模式相关", "number", 0.0, None, None,
                        "R143：fault_type=2 的量纲≈mmol H⁺/h（不是 mg/L/h）；类型1 为 KLa 比例衰减。"),
    "fault_profile": ("fault", "故障时间包络", "[[t,amp],…]", "json", None, None, None,
                      "R157：节点式时间包络，窗内按节点线性延伸。用于表达渐变型故障。"),

    # ---- disturb 时变扰动（8 路）----
    "dist_flag": ("disturb", "启用扰动通道", "0/1", "select", 0, None, None, "1=开启 8 路低通随机扰动（MATLAB filter 语义）。"),
    "dist_tau": ("disturb", "扰动时间常数", "h", "slider", 40.0, 1.0, 200.0,
                 "EMA 时间常数，已对齐 MATLAB filter(b1=0.005,a1=[1,-0.995])。"),
    "dist_mux_asym": ("disturb", "μx 扰动渐近值", "1/h", "slider", 0.0, -0.2, 0.2, "dist(t)=asym·(1−e^(−t/τ))。"),
    "dist_mup_asym": ("disturb", "μp 扰动渐近值", "1/h", "slider", 0.0, -0.05, 0.05, "同上。"),
    "dist_cs_asym": ("disturb", "糖浓度扰动", "mg/L", "number", 0.0, None, None, "同上。"),
    "dist_coil_asym": ("disturb", "油浓度扰动", "mg/L", "number", 0.0, None, None, "同上。"),
    "dist_abc_asym": ("disturb", "碱浓度扰动", "-", "number", 0.0, None, None, "同上。"),
    "dist_paa_asym": ("disturb", "前体浓度扰动", "mg/L", "number", 0.0, None, None, "同上。"),
    "dist_tcin_asym": ("disturb", "冷却水入口温度扰动", "K", "slider", 0.0, -20.0, 20.0,
                       "R12.9：+10 K 可把 CO2d 降到 7.3–7.5 绕过崩溃阈值，副作用是提高生长率。"),
    "dist_o2in_asym": ("disturb", "进气O2扰动", "%", "number", 0.0, None, None, "同上。"),

    # ---- operation 操作量与控制 ----
    "mv_scales": ("operation", "MV 全局倍率", "{col:k}", "json", None, None, None,
                  "把 V3 参考配方按倍率重放。有效域 [0.90,1.25]，越域显式告警。批 8 Fs 有双稳态分岔（0.95/0.97）。"),
    "mv_window_scales": ("operation", "MV 时间窗倍率", "[{t0,t1,scales}]", "json", None, None, None,
                         "只缩放窗内行的 MV。PH4 滚动控制的输入形态。"),
    "fs_ctl": ("operation", "补料闭环", "{sp,kp,ki,…}", "json", None, None, None,
               "R155/D-54：葡萄糖反馈闭环。8 个配置实测全部 −98%~−100%（失败点是 pH 掉到 3.000 钳位，非糖不够）。"),
    "fb_limit": ("operation", "碱液限幅", "{ph_stop,width,mode}", "json", None, None, None,
                 "R155/D-41：pH 高位停碱/回撤。不传则回放 Fb 不限幅（R149 越 7 根因）。"),
    "m_s_schedule": ("operation", "维持系数调度", "[[t,v],…]", "json", None, None, None,
                     "时变 m_s：早期高 m_s 防 CO2d 崩溃、晚期低 m_s 匹配产率。解耦 m_s–CO2d 耦合的关键。"),

    # ---- numeric 数值积分器 ----
    "ode_method": ("numeric", "积分方法", "BDF/Radau/LSODA", "select", "BDF", None, None, "默认 BDF，对齐 MATLAB ode15s。"),
    "ode_rtol": ("numeric", "相对容差", "-", "number", 1e-3, None, None, "积分器容差。"),
    "ode_atol": ("numeric", "绝对容差", "-", "number", 1e-6, None, None, "积分器容差。"),
    "ode_max_step": ("numeric", "最大步长", "h", "number", None, None, None, "R134 起可配；调大可显著提速但改变数值。"),

    # ---- initial 初值覆盖 ----
    "x0_biomass": ("initial", "生物量初值", "g/L", "number", None, None, None, "覆盖初始生物量；需配合 x0_force。"),
    "x0_force": ("initial", "强制覆盖初值", "0/1", "select", 0, None, None, "1=用 x0_biomass 强制替换初值。"),

    # ---- ph pH 通道 ----
    "ph_fix": ("ph", "pH 链式法则修正", "0/1", "select", 0, None, None,
               "R156/D-55：修正 pH≥7 basic 分支的数值病态。0=逐字原文（基线）；1=修正后。"),
    "ph_mode": ("ph", "pH 通道模式", "model/measured", "select", "model", None, None,
                "measured=每采样点用实测 pH 覆盖 [H+]（pH 降级为输入）。"),
    "ph_hyd_acid": ("ph", "水解产酸符号", "0/1", "select", 0, None, None, "R145/D-32：pH 方程里水解通道的酸碱符号。"),
    "ph_rp_mode": ("ph", "产酸口径", "net/prod_only/all_acid", "select", "net", None, None,
                   "R147/D-36：pH 方程里 r_p 的口径。"),
    "mu_p_growth": ("ph", "生长耦合产素 α", "-", "slider", 0.0, 0.0, 1.0,
                    "R153/D-48：Pirt 双相里缺的 α·μ 项。0=默认（逐位不变）；>0 与产量 1:1 耦合。"),

    # ---- soft 软测量 / 门控 ----
    "assimilate": ("soft", "状态同化", "dict", "json", None, None, None,
                   "观测同化配置。R140：接进 ODE 会打穿产量（86/86→6/86），不得作闭环路径。"),
    "paa_gate_mode": ("soft", "PAA 相门控模式", "int", "number", 0, None, None, "R121 根因修复。"),
    "paa_gate_floor": ("soft", "PAA 门控地板", "-", "number", 0.0, None, None, "门控下限。"),
    "paa_maintenance_target": ("soft", "PAA 维持目标", "mg/L", "number", 0, None, None, "维持目标值。"),
    "paa_degrad_rate": ("soft", "PAA 降解率", "1/h", "number", 0.0, None, None, "降解速率。"),
    "paa_degrad_inverse_gate": ("soft", "PAA 逆门控", "0/1", "select", 0, None, None, "逆门控开关。"),
    "vis_scale": ("soft", "黏度生成倍率", "×", "slider", 1.0, 0.1, 10.0, "乘于黏度生成项，经 kla 反馈产量。"),
    "vis_out_scale": ("soft", "黏度上报倍率", "×", "slider", 1.0, 0.1, 10.0,
                      "只乘输出列，ODE 内部不变 ⇒ 对产量零影响。"),
    "vis_decay_rate": ("soft", "黏度衰减率", "1/h", "number", 0.0, None, None, "黏度衰减。"),
    "vis_k1": ("soft", "黏度参数 k1", "-", "number", None, None, None, "黏度模型参数。"),
    "vis_k2": ("soft", "黏度参数 k2", "-", "number", None, None, None, "黏度模型参数。"),
    "vis_k3": ("soft", "黏度参数 k3", "-", "number", None, None, None, "黏度模型参数。"),
    "vis_t1": ("soft", "黏度参数 t1", "-", "number", None, None, None, "黏度模型参数。"),
    "vis_t2": ("soft", "黏度参数 t2", "-", "number", None, None, None, "黏度模型参数。"),
    "p_deg_rate": ("soft", "产物降解率", "1/h", "number", 0.0, None, None,
                   "R150/D-40：与 mu_h 重复计数，全局启用会逐批恶化 ⇒ 保持 0。"),

    # ---- 索引装配口补登（第 ② 类：`if k in params: par[i]=params[k]`）----
    "alpha_kla": ("dynamics", "氧传质系数 αKLa", "1/h", "slider", 85.0, 20.0, 200.0,
                  "批次级随机（85+10·randn）。R162/oq#37 实测散布 σ=8.94；D-84 写回属 L3。"),
    "Tcin": ("dynamics", "冷却水入口温度", "K", "slider", 288.0, 283.0, 298.0,
             "夹套冷却水入口温度（par[48]）。提高 T 提高 Henry 常数 ⇒ 降低 CO2d。"),
    "N_conc_oil": ("dynamics", "补料油氮浓度", "mg/L", "number", None, None, None, "油相氮浓度（par[67]）。"),
    "mean_P": ("soft", "产素门控中心", "g/L", "number", 0.002, None, None,
               "P_inhib 高斯门控中心（par[4]）。注意 par[5] 是 mu_v，不是门控宽度。"),
    "P_std_dev": ("soft", "产素门控宽度", "g/L", "number", 0.0015, None, None,
                  "P_inhib 高斯门控宽度（par[3]）。与 S 的量级相当 ⇒ 是平滑窗不是硬开关。"),
    "P_crit_PAA": ("soft", "PAA 抑制阈值", "mg/L", "number", 200.0, None, None,
                   "PAA 门控阈值（par[79]）。实测 PAA ~1400 mg/L 已使 tanh 饱和。"),
    # 扰动旧名（无 _asym 时为常数型；带 _asym 时为时变渐近型）
    "dist_mux": ("disturb", "μx 扰动(常数型)", "1/h", "slider", 0.0, -0.2, 0.2, "旧名；时变请用 dist_mux_asym。"),
    "dist_mup": ("disturb", "μp 扰动(常数型)", "1/h", "slider", 0.0, -0.05, 0.05, "旧名；时变请用 dist_mup_asym。"),
    "dist_cs": ("disturb", "糖浓度扰动(常数型)", "mg/L", "number", 0.0, None, None, "旧名。"),
    "dist_coil": ("disturb", "油浓度扰动(常数型)", "mg/L", "number", 0.0, None, None, "旧名。"),
    "dist_abc": ("disturb", "碱浓度扰动(常数型)", "-", "number", 0.0, None, None, "旧名。"),
    "dist_paa": ("disturb", "前体扰动(常数型)", "mg/L", "number", 0.0, None, None, "旧名。"),
    "dist_tcin": ("disturb", "冷却水温扰动(常数型)", "K", "slider", 0.0, -20.0, 20.0, "旧名。"),
    "dist_o2in": ("disturb", "进气O2扰动(常数型)", "%", "number", 0.0, None, None, "旧名。"),
}

# 不是参数键的伪匹配：`pH_H` 是状态索引名（model.py 的 IDX 表），不是可调参数。
# 它被 `if "pH_H" in params` 这类无关代码误命中 ⇒ 显式排除。
_NOT_PARAMS = {"pH_H"}

GROUP_META = {
    "dynamics": ("动力学主干", "比生长/比产率/维持/化学计量 —— 决定产量与形态的基本旋钮"),
    "morphology": ("形态学衰亡链", "菌丝区衰亡、自溶回收、液泡化 —— 修正 X 衰减段"),
    "fault": ("故障注入", "在回放输入之外注入的故障：KLa 衰减/注酸/减喂食/传感偏差"),
    "disturb": ("时变扰动", "8 路低通扰动，对齐 MATLAB filter 语义（渐近值型）"),
    "operation": ("操作与控制", "MV 倍率、时间窗、闭环补料、碱液限幅、维持调度"),
    "numeric": ("数值积分器", "方法与容差 —— 影响速度与数值可信度"),
    "initial": ("初值覆盖", "批量初始条件"),
    "ph": ("pH 通道", "pH 方程的修正、模式与产酸口径"),
    "soft": ("软测量与门控", "观测器接入口、门控与黏度上报口径"),
}


# ---------------------------------------------------------------------------
# AST 派生：解析 simulate.py 里的 params.get("key") 与 params.get("key", default)
# ---------------------------------------------------------------------------
def _literal(node: ast.AST) -> Any:
    """只认字面量常量；表达式（如 dict 构造）返回 None。"""
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError, TypeError):
        return None


def derive_param_keys(simulate_py: str = SIMULATE_PY) -> dict[str, Any]:
    """从 simulate.py 源码派生引擎真实接受的参数键。

    引擎有**两类**参数装配口，必须都覆盖，否则参数表会漏一半：

      ① `params.get("key", default)`            —— 直读式
      ② `if "key" in params: par[i] = params["key"]` —— 索引装配式
         （后者用于把批级覆盖写进 105 维参数向量的指定槽位，
           例如 m_s→par[24]、q_co2→par[91]、gamma1→par[62]）

    自检（首版曾漏掉第 ② 类 ⇒ 18 个动力学键被误判"源码已移除"）：
    派生出的键数必须 ≥ 两类各自去重后的并集大小，且不得出现
    「_SPEC 登记了但源码没有」的键 —— 那说明派生漏了某种装配口。

    返回 {"key": {"default": <源码默认或 None>, "has_default": bool,
                  "via": "get" | "index"}}。
    解析不出来（文件缺失/语法变化）时抛 RuntimeError —— 宁可启动失败，
    也不要给一个空的参数表让前端"看起来正常"。
    """
    if not os.path.exists(simulate_py):
        raise RuntimeError(f"引擎源码不存在：{simulate_py}")
    with open(simulate_py, encoding="utf-8") as f:
        src = f.read()
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        raise RuntimeError(f"simulate.py 语法错误，无法派生参数表：{exc}") from exc

    out: dict[str, Any] = {}

    def _record(key: str, default: Any, has_default: bool, via: str) -> None:
        prev = out.get(key)
        # 已由「有默认值」的口径登记过，则不被后来的无默认值口径覆盖
        if prev and prev["has_default"] and not has_default:
            return
        out[key] = {"default": default, "has_default": has_default, "via": via}

    for node in ast.walk(tree):
        # ---- 第 ① 类：params.get("key", default) ----
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Attribute) and fn.attr == "get" and node.args:
                first = node.args[0]
                if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
                    continue
                recv = fn.value
                recv_ok = (isinstance(recv, ast.Name) and recv.id == "params") or \
                          isinstance(recv, ast.Call)
                if not recv_ok:
                    continue
                default, has_default = None, False
                if len(node.args) >= 2:
                    default = _literal(node.args[1]); has_default = True
                else:
                    for kw in node.keywords:
                        if kw.arg == "default":
                            default = _literal(kw.value); has_default = True
                _record(first.value, default, has_default, "get")

        # ---- 第 ② 类：if "key" in params:  par[i] = params["key"] ----
        elif isinstance(node, ast.If):
            test = node.test
            if not isinstance(test, ast.Compare) or len(test.ops) != 1:
                continue
            if not isinstance(test.ops[0], ast.In):
                continue
            left = test.left
            if not (isinstance(left, ast.Constant) and isinstance(left.value, str)):
                continue
            if not (isinstance(test.comparators[0], ast.Name)
                    and test.comparators[0].id == "params"):
                continue
            _record(left.value, None, False, "index")

    return out


def build_catalog() -> dict[str, Any]:
    """构造完整参数目录（供前端渲染工况面板）。

    结构：
      groups   : [{id, label, desc, params:[...]}]
      rejected : {key: reason}   —— L3 硬拒绝
      derived : {key: {default, has_default}}  —— 源码派生的原始事实
      unknown : [key]  —— 源码里有但 _SPEC 未登记的键（需补登记，不是静默丢弃）
      missing : [key]  —— _SPEC 登记了但源码已不支持的键（源码改了，需清理）
    """
    derived = derive_param_keys()
    rejected = dict(L3_REJECTED)

    groups: dict[str, list[dict]] = {g: [] for g in GROUP_META}
    unknown: list[str] = []
    missing: list[str] = []

    for key in sorted(derived):
        if key in rejected or key in _NOT_PARAMS:
            continue
        spec = _SPEC.get(key)
        if spec is None:
            unknown.append(key)
            continue
        gid, name, unit, ctl, dft, lo, hi, desc = spec
        # 源码默认值优先（源码是唯一事实源）
        if derived[key]["has_default"] and derived[key]["default"] is not None:
            dft = derived[key]["default"]
        groups[gid].append({
            "key": key, "label": name, "unit": unit, "control": ctl,
            "default": dft, "low": lo, "high": hi, "desc": desc,
            "src_default": derived[key]["default"],
            "has_src_default": derived[key]["has_default"],
        })

    for key in sorted(_SPEC):
        if key not in derived and key not in rejected and key not in _NOT_PARAMS:
            missing.append(key)

    out_groups = []
    for gid, (label, desc) in GROUP_META.items():
        params = groups[gid]
        if not params:
            continue
        out_groups.append({"id": gid, "label": label, "desc": desc, "params": params})

    return {
        "groups": out_groups,
        "rejected": rejected,
        "derived": derived,
        "unknown": unknown,
        "missing": missing,
        "n_derived": len(derived),
        "n_exposed": sum(len(g["params"]) for g in out_groups),
        "n_rejected": len(rejected),
    }


def validate_overrides(overrides: dict, catalog: dict | None = None) -> tuple[dict, list[str]]:
    """校验前端传来的参数覆盖。

    拒绝四类问题（每一类都**显式报出**，不静默丢弃）：
      ① L3 候选键          —— R166 裁决未切默认
      ② 未知键            —— 前端误传
      ③ 非有限数          —— NaN / Inf
      ④ **越出已知量程**   —— 超出参数表登记的 [low, high]

    第 ④ 条的必要性：`mux=1e308` 这种"有限但荒谬"的值若放行，
    引擎会跑出一个看似正常的轨迹 —— 那是最坏的一类失败
    （「恒真的判据等于没有判据」的近亲：失败不可见）。
    量程取自 `_SPEC` 登记的**已知有效域**，不是物理上下限。

    返回 (清洗后的合法覆盖, 问题列表)。问题列表非空 ⇒ 上层必须拒绝提交。
    """
    catalog = catalog or build_catalog()
    valid_keys = {p["key"] for g in catalog["groups"] for p in g["params"]}
    by_key = {p["key"]: p for g in catalog["groups"] for p in g["params"]}
    clean: dict[str, Any] = {}
    problems: list[str] = []

    for k, v in (overrides or {}).items():
        if k in catalog["rejected"]:
            problems.append(f"{k}：L3 候选参数，平台硬拒绝（{catalog['rejected'][k]}）")
            continue
        if k not in valid_keys:
            problems.append(f"{k}：不在引擎参数表内（可能被前端误传）")
            continue
        if isinstance(v, bool):
            clean[k] = v
            continue
        if isinstance(v, (int, float)):
            import math
            f = float(v)
            if not math.isfinite(f):
                problems.append(f"{k}：非有限数值（{v}），已忽略")
                continue
            spec = by_key[k]
            lo, hi = spec.get("low"), spec.get("high")
            if lo is not None and hi is not None and not (float(lo) <= f <= float(hi)):
                problems.append(
                    f"{k}={f:g}：越出已知有效域 [{lo:g}, {hi:g}]（{spec.get('label', k)}）")
                continue
            clean[k] = f
            continue
        if isinstance(v, (dict, list)):
            clean[k] = v
            continue
        if isinstance(v, str):
            spec = by_key[k]
            if spec["control"] == "json":
                import json
                try:
                    clean[k] = json.loads(v)
                    continue
                except (ValueError, TypeError):
                    problems.append(f"{k}：JSON 解析失败")
                    continue
            clean[k] = v
            continue
        problems.append(f"{k}：不支持的类型 {type(v).__name__}")
    return clean, problems


if __name__ == "__main__":  # 自检入口：python platform_v2/param_catalog.py
    cat = build_catalog()
    print(f"派生键 {cat['n_derived']} / 暴露 {cat['n_exposed']} / 拒绝 {cat['n_rejected']}")
    print(f"未登记 {cat['unknown']}")
    print(f"源码已移除 {cat['missing']}")
    for g in cat["groups"]:
        print(f"  {g['id']:11s} {len(g['params']):3d}  {g['label']}")
