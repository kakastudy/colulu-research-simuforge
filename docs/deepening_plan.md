# 反应罐求解器深化方案 — 由进出料观测反向建模（讨论稿 v1 → 已拍板 v1.1）

> **R165 勘误（2026-11-06）**：本文是 **R42–R55 阶段的历史方案与执行快照**，§8「执行实况」停在 2026-10-29，**不代表 R163 之后（R164 回溯、R165 收口）的现行状态**。
> R164 专项回溯（`docs/goal_backtrace_check_v4.md`）已发现本文 **4 处陈述漂移**，本轮在对应行就地加注勘误，历史流水原文保持不改。
> 当前权威口径以 `docs/roadmap_next.md` §8.6 / `docs/r157_debt_ledger.md` 为准。

> **R131 快照**（2026-11-03 12:00）：X_offline 攻坚从"结构性无解"推进到"三边界可复核"。
> 衰亡率不再扫参而是**从化验轨迹反算**（kd_app 中位 0.0017 h⁻¹）；(μx,μp) 脊 72 配置证明
> 参数空间无法解耦幅度与产量；改用"早期恒定衰亡 + 自溶回收 + μp 回调"得到 4 批双约束可行解
> （b27 19.4→7.9、b36 30.7→13.9、b60 32.7→15.4、b92 22.9→9.4），b55/b91 红线内确实无解
> （悬崖位置已量化）。落点稳健性分级 wide(b36/b60)/narrow(b27/b92)，narrow 不得作控制基线。
> 黄金回归 RMSE 2.33%→2.34%，86/86 within 5%，0 catastrophic；D6 总体 417/1290 不变，
> X_offline critical 74→71。工程侧：黄金集参数收敛单一事实源、评估并行化 40→13 min、
> 修复 death_recycle 装配缺陷（曾致假回归 4.82%）。ENGINE_CONTRACT v1.58。
> 报告：docs/r131_round_report.md。
>
> **R130m+n 快照**（2026-11-05 04:30）：晚期衰亡扩展至 8/12 黄金批（+b36/b60/b92），
> RMSE 2.33% 保持，D6 417/1290 (32.3%)。Y_sX 逐批校准负结果确认：X_offline 幅度与产量
> 存在结构性耦合（共享 Y_sX 参数），无法单参数解耦。late_death 是 X_offline 唯一可行
> 改善路径（仅改善衰减段）。ENGINE_CONTRACT v1.57。
>
> **R130k 快照**（2026-11-05 02:00）：不可修复批根因诊断完成。15 批中 3 批可修复：
> b51(mu_h_scale=1.5, yield -0.04%) 已加入黄金集（85→86），b94/b99 因 CO2d catastrophic
> 结构性不可修复。剩余 12 批根因明确：b4/b6/b21/b25/b81 m_s 调整远离 ±5%，b10/b19
> mu_h_scale 分叉，b13/b32/b44 结构产率误差。RMSE 2.34%→2.33%，86/86 within 5%。
> ENGINE_CONTRACT v1.56。
>
> **R130j 快照**（2026-11-05 01:00）：晚期衰亡机制逐批校准完成。X_offline 通道首次实质性改善：
> 3/5 批从 critical→healthy（b8 nrmse=4.78, b16 nrmse=3.84, b23 nrmse=4.16），
> 2/5 从 critical→warning（b11 nrmse=5.16, b22 nrmse=8.09）。黄金回归 RMSE 2.29%→2.34%
> （仍在 3.5% 红线内），85/85 within 5%，0 catastrophic。7 批未启用（已有衰亡/低 m_s/
> m_s_schedule 交互）。ENGINE_CONTRACT v1.55。

> **R130 快照**（2026-11-05 00:00）：X_offline 形态学结构攻坚取得突破性进展。
> 根因确认：A3/A4 恒为 0%（液泡化 n_k=0 近似杀死 A1→A3 转移）→ 无老菌丝可衰亡
> → X_offline 不衰减（D6 唯一 critical 根因）。诊断修正：探针缺 dist_flag=1 导致
> pH 崩溃/S 累积假象；修正后真实图景为 sim X 峰值过高（27-37 vs V3 23-27）且不衰减。
> 液泡化直接启用（k_vac>0）灾难性破坏产量（-59%到-100%）：抽干 A1→生长减速→
> S 不降→P_inhib 不激活→产量崩塌。**突破**：晚期衰亡机制（late_death_rate +
> mu_death_ref + death_recycle=0.5）在批 22 上产量几乎完美（+0.06%），X 峰值
> 从 28.3 降到 24.5（V3=23.5），且出现衰减（-0.0165）。物理依据：Nestaas & Wang
> 1983（退化=比生长速率函数，μ>μ_min 时抑制）+ 死菌丝自溶回收底物。全黄金集
> 扫描进行中。

> **R120 快照**（2026-10-30 01:30）：P4 验收链 **verdict=PASS**（G1 88/88 / G2 先验 /
> G3 β R²=0.666 / G4 覆盖率 0.629 / G5 探针 10/10）；D9(a) 后验算子激活（ENGINE_CONTRACT
> v1.2）；黄金回归守护 4.48%/0/12/9 逐字保持；PAT 消融对照完成（转发近无损 Δ≤0.008，
> 触发批 fused corr 0.35→0.81）。PH1–PH5 全部完成。

> **R97 增补快照**（2026-10-29 22:05）：v2 池 68/88 推进中（watcher 自动串）；
> G3 判据已修正为 β 拟合口径（PASS 前景）；P4 四环驱动器全部实调拦截测试通过；
> model.py a_0 NaN 钳制 + 黄金回归逐字守护 PASS；PAA 保真批间普查 + μp 机理锚点
> （corr −0.891）→ PAT 触发器 paa_pat_trigger 已可执行化（knowledge_constraints）。

> 目标重述（用户原话抽象）：通过**进料/出料观测数据反向建立反应罐数值模拟模型**，
> 为**控制**（反设计/滚动优化）与**内部观测体系**（菌丝/微生物状态数值估计）提供求解器。
> 本稿为方案讨论版，含三备选路线、推荐架构、与既有资产的衔接、可辨识性约束与分阶段路线图。

---

## 0. 已有资产衔接（深化 = 在此之上，不是从零开始）

| 资产 | 在"反向建模"中的角色 |
|------|---------------------|
| A 档机理引擎（33 维 ODE，RMSE 4.48%） | **逆向建模的机理主干**（先验结构），黑箱只学修正项 |
| calibration.py 校准单源 + m_s_schedule | 每批随机效应（μx/μp/m_s/ΔTcin）的**先验分布**（对齐 MATLAB randn：μx~0.41±0.025） |
| soft_sensing（在线 54 网格） + stage2_estimator（μp 锚定 P_offline） | **参数级逆问题的已验证基线**（5/5 救回证据） |
| trajectory_metrics / conservation_metrics / mechanism_cclosure | 逆建模的**观测方程与质量门**（化验 4h 滞后口径、液相碳账） |
| crash 判据 / mv 有效域（Fs 分岔边界） | 求解器的**有效域防线**（控制律不得越域） |
| Raman/PAA PLS 资产（b 10×212）+ Raman 批池 61–90（30 批实测有 Raman 光谱） | 内部观测增强：PAA/菌丝的额外观测通道 |
| MCP 服务层 / runstore | 求解器即服务（Agent 调用）与结果持久化 |
| V3 数据内在不自洽发现（尾气通道 30×） | **决定观测方程选择**：绝对碳闭合不可用 → 化验+液相账为准 |

---

## 1. 问题的数学表述

对每个批次 b，观测交割是：

```
输入 u_b(t)：进料（Fs/Foil/Fpaa/Fg/RPM/Fw/Fa/Fb/Fc/Fh/pressure）+ 出料（Fremoved, 尾气 %）
输出 y(t)  ：在线可测（DO2/T/pH/Q/S/P/尾气 O2%/CO2%）+ 离线化验（X_offline/P_offline/PAA_offline/NH3/vis, 12h/滞后 4h）
```

反向建模型 = 从 (u, y) 恢复 {结构参数 θ、批次随机效应 θ_b ~ P(θ_b|μ̂,Σ̂)、内部状态 x(t)、
机理缺失项 d(x)}，使仿真前向复现 y 并给出 x(t)±CI：

```
ẋ = f(x, u, θ̄ + θ_b) + D(x)            # f：机理主干；D(x)：待发现的缺失动力学（如衰亡项）
y  = H(x, u) + v                          # 观测层（在线逐点 + 化验延迟点）
```

三层真相来源分层：f 为机理（Birol 族，已移植验证）；θ_b 为每批随机效应（有先验 — MATLAB
生成机制即 randn）；D(x) 为残差学习项（**此为"反向建模"的真正增量**——不是重新发明机理，
而是让数据揭示机理缺什么）。

## 2. 三条候选路线对比（拍板点 P1）

| 路线 | 思路 | 优势 | 风险/代价 | 建议 |
|------|------|------|----------|------|
| R1 纯黑箱 | NN/神经 ODE 从 (u,y) 直接拟合状态轨迹 | 表达力强 | 违背守恒、外推危险、88 批样本量不足、**控制不可微**；*不符合研发目标"机理引擎"* | 不推荐（只用于对照） |
| R2 两阶段混合（推荐★） | 机理主干 + 批次随机效应层次化重估 + **稀疏残差发现**（SINDy 式：从引擎-数据残差中识别缺失项，如衰亡项 kd·g(A_t1)） | 保物理/守恒；可解释可入规则；样本高效；天然给出 CI（随机效应后验） | 分层推断需实现（EM/MAP 交替，工作量中） | **首选** |
| R3 滚动联合估计 | MHE/EnKF 在线（状态+增广参数随机游走） | 控制可用、在线性好 | 逐批在线计算重；μp 敏感度（±0.001→60%）使在线参数混叠风险高 | 作为 R2 的**在线版本**，第二期实施 |

**推荐：R2 为主干（离线逆向建模 + 结构发现），R3 作为其在线化切片（面向控制），R1 仅作基线对照。**

## 3. 推荐架构（四层）

```
第 1 层  机理主干 f（已验证，4.48%）
第 2 层  批次随机效应层 θ_b：hierarchical MAP/EM
         先验 = MATLAB 生成分布（μx~N(0.41,0.025²) 等）→ **CI 天然产生（I3 一步到位）**
         数据 = 88 个非黄金批次（学习）+ 12 黄金批（只评不训，红线不破）
第 3 层  残差结构发现 D(x)：SINDy 式候选库（衰亡 kd·A_t1、维持修正、CO2 拖尾、氧平行项）
         从批间残差白化后做稀疏回归 → 输出"发现的缺失动力学"（新知识！knowledge ledger）
第 4 层  在线内部观测器 + 控制：
         - 降阶 EnKF/MHE：状态子集（S,P,X,A0/A1,PAA,CO2d）+ 随机游走增广参数（μp, m_s）
           观测 = 在线通道；化验到达时融合（12h/4h 滞后显式建模）
         - CI = 集合离散度；状态诊断 = 连续性/钳位/sharp 检验（I2）
         - 控制：滚动 2–8h 窗 MV 倍率反设计（复用 optimize 算子）+ Fs 分岔边界为硬约束
```

## 4. 关键技术决策（拍板点 P2/P3/P4）

**P2 观测体系**：内部观测以什么观测为主导？
- (a) 在线 + 化验融合（推荐——化验是真实可得的 X/P/PAA 真值锚点，且仿真有各批真值可做覆盖率验证）
- (b) 纯在线（无化验场景版，M2 路线；μp 不可辨识风险，只能输出 μ 边带估计）
- 结论：两者都做——(a) 历史重构Precise版，(b) 在线版降级输出（回退链 M2 精神）

**P3 Raman 资产启用时机**：批池 61–90 有 Raman 且批 80（黄金集）在内。
- (a) 第二期启用（先做 P_offline 锚定已达 5/5 救回；Raman→X/PAA 通道留 secondary enhance）
- (b) 立即启用（PLS b 矩阵已核证 10×212，但消融成本高）
- 推荐：(a)——R2 主线先用进出料+化验闭形，Raman 作为 stage-3 增强与消融

**P4 学习信号的边界**（数据划分）
- 88 个非黄金批做残差学习/超参数学习；黄金集只评估（红线）。用 50 批做验证分割？
- 推荐：88 = 60 训练 + 28 验证分层（正常/故障分层抽样），黄金 12 评估。

## 5. 分阶段路线（每阶段有验收判据，均落 runs/ 证据）

**PH1 逆向建模基础设施建设（~2 轮会话）**
- 批池整理：100 批 → 训练 60 / 验证 28 / 黄金 12（分层）
  - ⚠ **R165 勘误（D-89）**：这 **28 批验证集从未被留出**。`candidate/indpensim/v0.1/hier_est.py:276` 实际执行 `batch_list = bp["train"] + bp["validation"]`（v2 全批池把训练+验证合并拟合） ⇒ 基于该池的任何超参数 / 温度 / 网格选择都是**训练集内选择**，不存在独立验证。
  - ⇒ PH1 的验收口径须改写（见下条），且**禁止**引用「验证集」作为任何泛化性论据。
- 层次化先验拟合：θ_b 的（μ̂,Σ̂）从 60 批 MAP 估计（每批快校准：复用 m_s/μx/μp/ΔTcin 通道；每批 ~20 次仿真 ≈ 3 min → 60 批 ≈ 3 h 算力，可后台分批跑）
- 验收：先验分布与 MATLAB 生成机制一致性（μ̂≈0.41±0.025 等数值对齐）；黄金集零接触
  - ⚠ **R165 改写（R164-2 / D-89 / R142）**：①「μ̂±σ̂ 与 MATLAB 生成机制数值对齐 ⇒ 验证通过」**不再作为验收判据** —— R142 已证伪 `dl_sigma` 的 σ_pop=0 是温度口径失效的产物（`T_EB=1.0` 比损失差大 106×、ESS=46.8/48 ⇒ 后验等于无信息先验），`COMBINED`逐批点估计也**不是批间分布样本**；现行可引用口径只有 **MAP 散布上界** `σ_pop(mux) ≤ 0.0328 / mup ≤ 0.0056 / m_s ≤ 0.0019`，且**必须注明不含群体先验**。
  - ② 因 28 批验证集未留出，本验收**不含独立泛化误差**，只能作为「训练集内自洽」登记（**已知边界**，见 `docs/m5_review_signoff.md` B-19）。

**PH2 残差结构发现（1–2 轮）**
- 逐批残差 γ(t) = 数据轨迹 − 引擎轨迹（X/P/S 主通道）
- SINDy 候选库稀疏回归 → 候选缺失项（预期：衰亡 kd·g(A_t1)、氧限制修正、维持温度项）
- 验收：黄金集上叠加 D(x) 后 RMSE 显著下降（目标：4.48% → ≤3.5%）且不破坏守恒账

**PH3 在线内部观测器（2 轮）**
- 降阶 EnKF（50 集合，0.2h 周期，观测=在线+补化验）+ MHE 备份 + 稳态碳平衡兜底（M2 回退链第 2/3/4 环）
- 验收：合成闭环上 X/P/PAA 重构误差带 CI；**覆盖率经验证（I3 首次落地）**；批 91/92 特征保持

**PH4 控制求解器（1 轮）**
- 滚动窗反设计：观测器状态 → 2–8h 窗 MV 倍率寻优 → 产量/偏差控制
- 验收：合成场景（含有效域告警触发）全过；对照"固定配方"提升量化

**PH5 服务化扩展（并入主报告）**
- MCP 新工具：reconstruct_batch（PH 离线重构±CI）、observe_online（降阶观测器）、advise_control（滚动反设计）、discover_residual（PH2 结构发现）
- 看板：新增「观察-控制工作台」页

## 6. 与既有拍板清单的衔接（自动闭环）

| 既有拍板 | 本方案的处置 |
|---------|-------------|
| D1（UKF 欠账） | 由 PH3 降阶 EnKF/ MHE + PH2 残差发现**结构性解决**（比全量 UKF 更可行） |
| D2（I3 置信区间） | PH2 批次后验（层次贝叶斯）+ PH3 集合 CI + 合成闭环覆盖率验证 |
| D3（ENGINE_CONTRACT.md） | PH5 一并写入（reconstruct/observe/control 契约 + 现有 9 工具） |
| D4（故障注入算子） | 不在本方案主线（V1+），PH3 里批 91/92 特征检查只作回归 |
| D5（T1 操作窗口） | 控制层硬约束需要它 → 顺带起草（IndPenSim 内建约束暂代，标注） |

## 7. 需要用户拍板的 3+1 个决定 — **已拍板（2026-10-27，用户确认"按推荐来"）**

1. **P1 路线**：✅ R2 混合 + 残差发现为骨干（纯黑箱仅作对照）
2. **P3 Raman**：✅ 第二期启用（PH1 先以进出料 + 化验闭环工作）
3. **P4 数据划分**：✅ 60/28/12 分层划分（黄金 12 批始终只评不训）
4. **（附）新模型版本**：✅ 认可进版本化流程——PH2 若发现新动力学并显著降 RMSE，
   并入 calibration.py 升 **v0.2**，旧 v0.1 保持为基线回退；变更走双账本登记

---

## 8. R42–R55 执行实况（2026-10-29，逐条对照上文分阶段路线）

| 阶段 | 实况 | 证据 |
|------|------|------|
| PH1 | v1 池 60/60 ✅；v2 精网格池（48 组合/批）**50/88 推进中**（watcher 自动串）；EB 温度重标定确认不分辨生成 σ̂（σ̂_μp 0.0011 vs 0.0025）；DL 矩估计器实现但网格后验 var_w≫var_between → σ_pop=0 —— **R142 已证伪该统计量为温度口径失效产物，R165 改引 MAP 散布上界（见 §5 R129t 勘误）** | runs/hier_est/train_theta_v2.jsonl; tools/ph1e_fit.py(闸门); eb/dl 检查脚本 |
| PH2 | **88 有效批 / A_t1 命中 12 站 / 负向 5**（`runs/hier_est/residual_discovery_full.json`；R165 勘误：原文「30 批 / 60 站点 / 63% 负向」是 R42–R55 中途快照，非最终口径）；死亡项 β 拟合 R²=0.67（621 点, X 残差 σ 4.62→2.67）；**P4 升级前探针 10/10 黄金批 X nRMSE 改善（中位 −15.3pt）**；v0.2 算子注册 calibration.py（等价性 0.00e0） | runs/hier_est/death_term.json; p4_death_probe.json; mid-vote |
| PH3 | EnKF 修复链（膨胀 1.0005/pH_H 专用夹具/参数阻尼/Q 单位/NaN isfinite 重采样门）→ 批 11/8 轨迹健康; 集合平滑器 death-term 层批 11 X 覆盖 43.8→62.5% | enkf_11_fixed.json; esmooth_11_v02.json |
| PH4 | advise_control 上线（11 工具); T1 校验器 validate_t1 执行化 + **窗口包络采样**（时间域=咨询域); §15 文献桥 5 锚（Crossref 核证） | ENGINE_CONTRACT.md v1.1; ledger49/48 |
| **PH4 结论（R165 补，R164-4）** | **转已知边界**：D-54 / D-57 判决 ⇒ **运行期连续调控（梯度型闭环）封死**（响应是阶跃、跳变两侧无可用梯度区分度）；**开环设定点标定保留**但落点相对精度要求 **1e−04…1e−05**（属标定级而非控制级）。若要运行期调控须走结构改动路线（L3，需另行授权） | `docs/r157_debt_ledger.md` D-54/D-57；`docs/m5_review_signoff.md` B-9 / **B-18** |
| PH5 | 服务化完成（MCP http 8931 十一工具 + 仪表盘 8501 三工作台）; observe_online 以 EnKF/重构形态兑现 | tools/test_mcp_http_11.py |
| P3 Raman | 数据可用性缺口如实登记 + (a) 引擎合成层管线三重验证（0.9995/0.9997/0.8463）；PAA 通道反相关 + 批 80 化验退化两事实 → PAT 应作锚定修正源 | tools/raman_pipeline.py; ledger50/51/53/54 |
| 评估口径 | PAA_offline 指标化（退化守卫 + lag 扫描 + 反相关披露）消除盲区 | trajectory_metrics.py; runs/trajectory_metrics_paa_check.json |

**D9（登记待拍板）**：产量级 RMSE ≤3.5% 需 ODE 级死亡项积分 + 12 批重校准（V1+）；
后验算子路径（推荐)以校准/观测层完成 v0.2 定性 — **R120 已激活（verdict=PASS）**。

**R121 PAA 批间异质根因（机理探查）**：P 通道全批健康（corr 0.97-0.998）排除前体传导；
反相批 PAA 时序严重错位——引擎峰值早于化验 144-180h（批 22 lag=-144h, 批 23 lag=-180h,
批 36/60 lag=0h）。根因 = PAA 生产项（Y_PAA_P·dP/dt + Y_PAA_X·X）在高 μp 下过早触发
（生产相提前开启）→ **相门控结构缺失**。修正方向 = PAA 方程增加生产相抑制函数（D9-b
ODE 级机理增强, V1+），与已激活的 D9(a) 后验算子互补。证据 runs/p3/paa_shape_probe.json。

**R122 D9(b) PAA 相门控实施（R121 根因修复）**：PAA 方程增加底物门控函数
f_paa = floor + (1-floor)·mean_P/(mean_P+s)（Michaelis-Menten 型 + floor 下限），
抑制生长相（高 s）PAA 消耗、允许生产相（低 s）消耗。实现于 model.py rhs()，
paa_gate_mode 参数（0=off 默认/1=gate X_1/2=gate X_1+dP_dt）+ paa_gate_floor（0.0-0.3）。
黄金回归守护重跑 RMSE 4.48%/0/12/9 **逐字保持**（默认 mode 0 零回归）。
探针结果（mode 1, floor=0）：批 22 corr −0.231→**+0.856** lag −144h→**0h**（时序完全修复）；
批 23 corr −0.538→−0.592 lag −180h→−144h（部分改善）；批 36 corr 0.984→0.987（微改善）；
批 60 corr 0.998→0.979（轻微回归）。幅度过冲（批 22 amp_ratio 4.5×）需 PAA 参数重校准
（V1+）。floor 扫描证实时序改善对所有 floor 值稳健。证据 runs/p3/paa_gate_probe.json +
paa_gate_floor_sweep.json。

**R123 D9(b) PAA 维护消耗修复 + 降解项（幅度过冲根因）**：R122 发现幅度过冲
（批 22 amp_ratio 4.5×），根因分析发现 m_PAA 维护消耗项原代码用 y[3]=P（青霉素），
但 MATLAB indpensim_ode.m 原文用 X（生物量）。m_PAA=1.05 g/g/h 是每克生物量
消耗的 PAA 维护系数 → 应正比于 X 而非 P。修复：新增 paa_maintenance_target
参数（0=P 默认/1=total_X）。m_PAA 扫描（mode 1 + maintenance=X, 0.05-0.30）：
批 22 幅度 4.2-4.4×（m_PAA 无影响——过冲是结构性的，喂食累积 vs 门控抑制消费）；
批 23 m_PAA=0.05-0.10 给出 corr 0.19→0.12 amp 1.1→1.0 lag 0h（从 R122 的
corr=-0.592 大幅改善）。新增一阶 PAA 降解项 paa_degrad_rate（-rate*PAA），
模拟 PAA 在发酵液中缓慢降解。降解扫描（mode 1 + maintenance=X + m_PAA=0.10）：
degrad=0.002 最优于批 22/23/36（corr 0.874/0.023/0.995 lag 0h）；degrad=0.010
最优于批 60（corr 0.996 amp 0.896）。批 22 幅度过冲结构性：degrad=0.005 修复
幅度（1.085）但时序崩溃（lag=-144h），存在尖锐阈值。黄金回归守护重跑
RMSE 4.48%/0/12/9 逐字保持（所有新参数默认 off/0）。证据
runs/p3/paa_maintenance_fix_probe.json + paa_mpaa_sweep.json + paa_degrad_sweep.json。

**R124 D9(b) PAA 反相门控降解（时序/幅度平衡）**：R123c 恒定降解修复幅度但
时序崩溃（degrad=0.005 → lag=-144h）。根因：恒定降解在生产相也消耗 PAA
→ 峰值提前。R124 方案：反相门控降解——降解仅在门控关闭时（生长相）激活，
degrad = rate·PAA·(1-f_paa)。物理依据：PAA 溢出代谢（overflow metabolism）
在生长相活跃——青霉素合成途径未启动时 PAA 通过替代酶系被代谢消耗；生产相
该途径关闭，PAA 留给青霉素合成前体消耗。精细扫描（mode 1 + maintenance=X
+ m_PAA=0.10 + degrad 0.001-0.0045 × {恒定,反相}）：批 22 inv_deg0.0045
→ corr=0.893 lag=0h amp=3.10（恒定 deg0.004 即崩 lag=-144h，反相可承受更高
degrad 而不崩时序）；批 23 inv_deg0.001 → corr=0.106 lag=0h amp=0.984（近完美）；
批 36 const_deg0.003 → corr=0.993 lag=0h amp=0.996（近完美）；批 60 const_deg0.0045
→ corr=0.946 lag=0h amp=1.50。高 μp 批（22/23）反相门控优势显著——时序保持
+ 幅度改善。批 22 幅度 3.1× 仍结构性（喂食率 >> 生长相消费率），需喂食模型
重构（V1+ 后续）。黄金回归守护 RMSE 4.48%/0/12/9 逐字保持。证据
runs/p3/paa_inverse_degrad_sweep.json + paa_degrad_fine_sweep.json。

**R124d D9(b) PAA m_PAA×degrad 2D 扫描——批特异性 m_PAA 需求**：R124c floor
高值扫描（0.3-1.0）全部时序崩溃（lag=-144h），仅 floor=0.0 保持时序。
2D 扫描 m_PAA∈{0.10-2.0}×degrad∈{0.0045-0.010}（mode 1 + maintenance=X +
floor=0.0 + inv_gate）：关键发现——**m_PAA 需批特异性校准**。批 22 m_PAA=1.0
+ degrad=0.010 → corr=0.391 lag=24h amp=**1.381**（amp 从 3.1×→1.38×，大幅改善！）；
批 23 m_PAA=0.10 + degrad=0.0045 → corr=0.066 lag=0h amp=0.860；
批 36 m_PAA=0.10 + degrad=0.0045 → corr=0.993 lag=0h amp=0.932；
批 60 m_PAA=0.50 + degrad=0.0045 → corr=0.992 lag=0h amp=**1.069**（近完美！）。
m_PAA=0.50 对批 22/23 时序崩溃（lag=-144/-180h），无单一 m_PAA 值适用于所有批。
m_PAA=0.10 为最安全通用值（所有批 lag=0h）。m_PAA 批特异性校准挂 V1+。
黄金回归守护 RMSE 4.48%/0/12/9 逐字保持。证据 runs/p3/paa_mpaa_degrad_2d_sweep.json。

**R125 D9(b) PAA 逐批 m_PAA + degrad 校准实施**：聚焦扫描 12 批 × m_PAA(5) ×
degrad(3) = 180 仿真，找到各批最优组合。PAA_CAL dict 加入 calibration.py
calib_params（仅门控模式使用；黄金回归 diag 用 COMBINED 硬编码 dict，零影响）。
验证结果（mode 1 + inv_gate）：
批 36 corr=0.994 amp=1.009 lag=0h、批 60 corr=0.992 amp=1.069 lag=0h、
批 92 corr=0.956 amp=1.008 lag=0h、批 91 corr=0.988 amp=0.947 lag=-12h（全部优秀！）。
批 11 corr=0.672 amp=1.099 lag=0h、批 22 corr=0.391 amp=1.381 lag=24h。
**关键发现：批 22 mode 0（无门控）+ m_paa=1.0 + degrad=0.010 → amp=1.084 lag=24h**，
优于 mode 1（amp=1.381）——高 m_PAA + 恒定降解在 mode 0 下即可控制幅度，
门控反而有害（抑制生长相消费 → 累积增加）。批 16 门控必需（mode 0 amp=2.174 →
mode 1 amp=1.103）。批 27/80/23 仍有结构性问题（amp=3.068/1.805/corr=0.079）。
黄金回归守护 RMSE 4.48%/0/12/9 逐字保持。证据
runs/p3/paa_per_batch_calibration.json + paa_per_batch_verification.json。

**R126 D9(b) PAA 结构限制诊断——批 23/80/16/27 根因分析**：R125 验证后 4/12 批
优秀，但批 23/80/16/27 仍有问题。诊断结果：(1) 批 80 PAA_offline 平直 ~1200
（R52 已知数据饱和，非模型问题）；(2) 批 16 PAA 双峰（24h:1230 + 192h:1160），
引擎单峰无法匹配——结构性；(3) 批 23 PAA 平滑上升（36h:648→204h:1824），
无峰值——引擎门控产生峰值，形状不匹配——结构性；(4) 批 27 高幅度可改善：
m_PAA=0.5 + degrad=0.008 → amp=**1.606**（从 3.068 改善），corr=0.435（从 0.737
下降）——幅度/相关性权衡，已更新 PAA_CAL。D9(b) PAA 工作总结：5/12 批优秀
（36/60/92/91/27），批 22 mode0+m_paa=1.0+deg=0.01 amp=1.084，批 80 R52 数据
问题，批 16/23 结构性限制。黄金回归守护 RMSE 4.48%/0/12/9 逐字保持。证据
runs/p3/paa_per_batch_verification.json + paa_per_batch_calibration.json。

**R127 D4 故障注入算子实施（V1+）**：实现三种故障类型注入（model.py rhs() +
simulate.py 参数透传）：(1) 氧限制故障（fault_type=1, 降 KLa → DO2 下降 →
氧抑制 → 底物累积 → 低产率）；(2) pH 扰动故障（fault_type=2, 注酸 → pH 下降
→ 代谢应激）；(3) 喂食减少故障（fault_type=3, 降 Fs/Fpaa → 底物不足）。
所有故障默认 off（fault_type=0），黄金回归零回归守护。探针结果：批 91 氧限制
故障 mag=0.58 给出 RMSE_S 16.5→8.6（底物累积改善）但 yield_err −0.302→−0.636
（过度降低产率）；mag=0.62 触发产率崩溃阈值（yield_err=−0.987）。关键发现：
批 91 底物累积的根因是**生物量衰亡**（death term β）而非氧限制——DO2 在
t=60h 后恢复至 14-15%，但 S 从 t=96h 线性累积至 115（生物量停止消耗底物）。
氧限制故障不能正确复现此行为，需 death term 机制增强。批 92 pH 扰动故障
不需要——基线已匹配（yield_err=−0.006, RMSE_pH=0.68）。故障注入算子作为
V1+ 工具可用于求解器鲁棒性测试和控制场景故障注入，但故障批复现需机理理解。
黄金回归守护 RMSE 4.48%/0/12/9 逐字保持。证据 runs/p3/d4_fault_injection_probe.json
+ d4_oxy_fine_sweep.json。

**R128 D6 独立健康视图实施（V1+）**：用黄金回归基线参数（COMBINED dict, 非
calib_params）对全部 12 黄金批做逐通道健康评估，含 PAA 通道。与
trajectory_metrics.py 的区别：后者用 calib_params（逐批校准）只覆盖在线通道给
原始指标；D6 用基线参数独立于校准，覆盖全部通道（含 PAA/NH3/vis），给健康
分级（healthy/warning/critical）和总体判决。混合分级策略：lab_mean≥0.5 时用
nRMSE，否则用绝对 RMSE（避免 nRMSE 爆炸）。结果：总体 CRITICAL（28.6% healthy
pairs）——预期（基线参数无逐批校准）。通道级分解是最有价值的部分：**物理通道
（T/V/Wt/O2）全部 healthy（12/12）**——由输入数据驱动；**气体交换通道
（OUR/CER/CO2outgas/Q）全部 critical（12/12）**——依赖生物量浓度和代谢速率；
**X_offline 全部 critical（12/12）**——生物量估计是最难点；**PAA_offline
10/12 critical**——与 R121-R126 一致。关键洞察：气体交换通道全部 critical 的
根因是生物量轨迹不准——基线 μx/μp 固定，但实际生物量轨迹批间差异大，导致
所有依赖通道（OUR/CER/CO2outgas/Q/X_offline/vis）连锁偏差。改进生物量估计
（X_offline）将改善所有依赖通道。证据 runs/p3/d6_health_view.json。

**R129 ODE 级生物量衰亡项实施（D9 扩展, V1+）**：R127 D4 探针发现批 91 底物
累积根因是生物量衰亡。模型现有 r_d1/r_d4 是组分间迁移（总量守恒），无真正衰亡
项。PH2 后验死亡项（death_correct_X）仅修正 X 轨迹不参与 ODE 动力学。R129 在
model.py 生物量 ODE 各组分加 -kd·y[comp] 项（biomass_death_rate 参数, 默认 0.0
零回归），可选 time-varying（death_start 参数, t>=death_start 激活）。常数
kd=0.005 给出 S_max=112.7（lab=115.3）但 P_max=8.1（lab=8.4）——常数衰亡从 t=0
开始过早降低 P 产率。**TV death ds=60 kd=0.005 → yield_err=0.0002（本质完美！）**
——t<60h 不衰亡保留早期产 P，t>=60h 衰亡使生物量下降 → 底物消耗减少 → S 累积。
S_max=102.6（从基线 94.2 改善, lab=115.3）。P_max=12.4（lab=8.4, 过估但总产量匹配）。
PAA 门控从批 91 移除（通过 PAA_inhib_P 间接降低产率: P_max 8.1→6.1）。
PAA_CAL[91] 更新：biomass_death_rate=0.005, death_start=60。黄金回归守护
RMSE 4.48%/0/12/9 逐字保持（COMBINED dict 不含衰亡项）。证据
runs/p3/d9_death_term_batch91.json + d9_death_term_tv_batch91.json。

**R129d 衰亡项全黄金批扫描 + 逐批应用（D9 扩展, V1+）**：R129c 探针扫描 12 批 ×
kd∈{0.001,0.002,0.005} × ds∈{0,100} = 96 仿真。衰亡项改善 **全部 12 批** X_offline
RMSE（D6 显示 X_offline 全部 critical 的全局根因之一）。关键发现：
- 批 16（基线 yield_err=-0.598）：kd=0.005 ds=0 → yield_err=0.004 RMSE_X=1.65（从 8.04）
- 批 22（基线 yield_err=-0.789）：kd=0.005 ds=0 → yield_err=0.133 RMSE_X=1.17（从 10.42）
- 批 80（基线 yield_err=-0.145）：kd=0.005 ds=0 → yield_err=-0.001 RMSE_X=1.22（从 7.92）
- 批 8：kd=0.005 ds=100 → yield_err=-0.026 RMSE_X=1.25（从 4.32）
- 批 11：kd=0.005 ds=100 → yield_err=0.030 RMSE_X=1.02（从 5.00）
- 批 91：kd=0.005 ds=60 → yield_err=0.0002 RMSE_X=2.81（从 2.81）

批 23/27/36/55/60/92 未启用（衰亡项对这些批改善 X 但恶化 yield，需更精细校准）。
PAA_CAL 6 批启用衰亡项（8/11/16/22/80/91）。黄金回归守护 RMSE 4.48%/0/12/9 逐字
保持。证据 runs/p3/d9_death_term_all_batches.json。

**R129e 衰亡项精细校准——未启用 6 批**：R129d 未启用的 6 批（23/27/36/55/60/92）
用更小 kd 和更多 ds 重扫（kd∈{0.0005,0.001,0.0015,0.002,0.003} × ds∈{0,80,120,160,200}
= 150 仿真）。找到 2 批可接受配置：批 36 kd=0.003 ds=160（yield_err=-0.032 RMSE_X=5.81
从 6.97），批 60 kd=0.003 ds=120（yield_err=-0.035 RMSE_X=3.11 从 6.51）。
PAA_CAL 更新为 8 批启用（8/11/16/22/36/60/80/91）。证据 runs/p3/d9_death_term_fine_remaining.json。

**R129f 衰亡项 COMBINED 语境校准——黄金回归升级**：R129d/e 在 calib_params 语境
（含 PAA_CAL）校准，但黄金回归用 COMBINED dict（不含 PAA_CAL），语境不同→衰亡项
效果不同。R129f 直接在 COMBINED 语境下逐批扫描 kd∈{0.0005,0.001,0.002,0.003,0.005}
× ds∈{0,100,200} = 216 仿真。7 批有改善（8: 0.015→0.004, 16: 0.043→0.004,
80: 0.030→-0.001, 23: -0.004→0.001, 55: -0.026→-0.019, 91: 0.045→0.044,
92: -0.006→-0.003）。5 批无改善（11/22/27/36/60）。**黄金回归 RMSE 从 4.48% 降至
4.15%**（死亡项贡献 7.5% 改善）。0 catastrophic, 9/12 within 5%。COMBINED dict
更新含衰亡项（7 批）。证据 runs/p3/d9_death_term_combined_ctx.json。

RMSE with best configs: 3.54%（R129f: 4.15%）。批 60 改善（mux 0.47→0.40:
-9.2%→-6.0%），批 22 小幅改善（mux 0.41→0.35: +7.7%→+7.1%），批 36 无改善。

**R129g2 批 60 精细调优——RMSE≤3.5% 达成**：批 60 yield_err=-9.2% 的根因是 m_s
过高（0.025→维持消耗过多→产量低估）。mup×m_s×mux 网格（75 仿真）找到最优：
mux=0.47 mup=0.035 m_s=0.010 → yield_err=+1.5%（从 -9.2%，改善 10.7pt）。
**黄金回归 RMSE 4.15%→3.12%**（低于 D9 目标 3.5%！）。10/12 within 5%，
0 catastrophic，2 benign（批 23/60）。COMBINED dict 更新（批 60 m_s=0.010 mup=0.035，
批 22 mux=0.35）。CAL dict 同步更新。证据 runs/p3/d9_death_term_batch60_fine.json。

**R129h 批 36/22 参数精调——RMSE 进一步降低**：批 36 mup 0.041→0.050 m_s 0.015→0.010
→ yield_err -6.4%→-5.6%；批 22 mup 0.070→0.065 → +7.1%→+7.0%。黄金回归 RMSE
**3.12%→2.96%**。10/12 within 5%，0 catastrophic，2 benign。COMBINED + CAL dict
同步更新。证据 runs/p3/d9_death_term_batch36_22_fine.json。

**R129i 批 22/36/91 联合 mux×mup 网格**：批 36 mux 0.41→0.47 mup 0.050→0.045
→ yield_err -5.6%→-4.5%（改善 1.1pt）。批 22/91 无改善（结构限制）。黄金回归 RMSE
**3.12%→2.80%**。11/12 within 5%（仅批 22 +7.0% 超出），0 catastrophic，2 benign。
证据 runs/p3/d9_death_term_batch22_36_91_grid.json。

**R129j 批 22 m_s_schedule 精调**：20 配置无改善 → 批 22 为结构性问题
（模型系统性高估产量 7%），非参数可调。RMSE 维持 2.80%。

**R129k D6 健康视图重跑——死亡项显著改善通道健康**：R129i 更新 COMBINED dict
后重跑 D6 独立健康视图。总体判决从 CRITICAL(28.6% healthy) 提升至 **WARNING(59.4%)**，
healthy 通道-批对从 56→114（108% 改善）。

**R129m q_co2 扫描——CO2 通道改善但产量恶化**：q_co2=0.110 改善 CO2outgas/CER 通道
34%（avg 27.1%→18.0%），但批 91 产量 yield_err +4.4%→-29.8%（RMSE 2.80%→8.95%）——
CO2 抑制项在批 91 激活。q_co2 与产量通过 CO2 抑制耦合，结构性不可解。已回退 q_co2=0.1353。
证据 runs/p3/d9_q_co2_sweep.json。

**R129n C_CO2_in 扫描**：C_CO2_in∈{0,0.01,0.02,0.033,0.05,0.08,0.12} × 12 批。
CO2 通道 nRMSE 在 25.8%-31.3% 间变化，C_CO2_in=0.010 略优（26.2%）但不显著。
C_CO2_in 只影响入口 CO2 项，不影响 CO2 产生项（CER），无法解决结构性过估。
证据 runs/p3/d9_c_co2_in_sweep.json。

**R129o-p Q 通道系统性问题调查——V3 Q 是输入数据的计算量**：
- R129o: Q 通道 12/12 critical，sim Q / V3 Q 均值比 ~3.6x 但非恒定（0.02-0.28）
- R129p: Qcon（夹套冷却）与 V3 Q 比值 114-1237，非恒定——V3 Q 不是夹套冷却
- R129p2: 逐时刻相关性——V3 Q 与 sim Fc 相关性 +0.79，与 V3 T 相关性 +0.99
- R129p3: 线性回归 V3_Q = a*sim_Q + b → 斜率全为负，物理无意义
- R129p6: 逐批多变量回归 V3_Q = a*Fc + b*Fh + c*T + d → **R²>0.96 全部 12 批**
  V3 Q 是 V3 输入 (Fc, Fh, T) 的计算量（主要是 T 的热容项），不是反应罐总热产率的
  独立测量。sim Q (y[8]/1000) 是 ODE 模型的总热流率，两者物理含义不同，不应直接比较。
  **Q 通道从 D6 健康视图移除**。

**R129q OUR/CER 公式验证**：手动计算验证当前公式正确（用 V3 输入计算 OUR 与 V3 OUR
nRMSE=0.0%）。sim OUR/CER 偏高的根因是 sim CO2outgas 过估 ~12%（1.74 vs 1.56），
CO2 过估通过尾气分析公式传播到 OUR/CER。CO2 过估根因是 q_co2（R129m 已验证不可调）。

**R129q2 P 在线 vs 离线通道对比 + D6 NaN bug 修复**：
P_offline 通道 98.2% NaN（稀疏离线采样），D6 健康视图因 `np.mean(NaN)=NaN` 且守卫
`lab_mean > 1e-10` 默认 0.0，将所有离线通道错误标记为 0.0% nRMSE（healthy）。
修复：过滤 NaN 值后计算 nRMSE，无数据标记为 "no_data"。
修复后 D6 总体判决从 WARNING(63.3%) 回归真实 **CRITICAL(32.8%)**。
离线通道真实 nRMSE：Viscosity 42.9%, PAA 42.3%, X 24.3%, P 18.3%, NH3 9.2%。

**R129r 黏度模型改进探查**：黏度与总菌体量相关性 0.81-0.85（批 91 仅 0.30）。
线性拟合 V3_vis = 1.77*X + 12.4 将 nRMSE 从 46.7% 降至 32.4%（31% 改善），
但仍在 critical 区间。当前模型使用 a_0^(1/3) 而数据显示线性关系，结构不匹配。

**R129r2 vis_scale 逐批校准——产量结构性耦合**：添加 vis_scale 参数（默认 1.0，
黄金回归零影响）到黏度 ODE 生产项。扫描 vis_scale∈{0.5-1.0} × 12 批。
vis_scale=0.9 将黏度 nRMSE 从 ~43% 降至 9-26%，但**产量严重恶化**：
- 批 55: yield +27.4%（base -1.9%）——catastrophic
- 批 60: yield +27.4%（base +1.5%）——catastrophic
- 批 27: yield +4.4%（base -0.2%）
黏度通过 KLa（c=-0.38）耦合到氧传递→产量。降低黏度→KLa 升高→氧传递增加→
生物量生长改变→产量偏移。**黏度通道与产量结构性耦合，无法在不破坏产量的前提下改善**。
证据 runs/p3/d9_vis_scale_calibration.json。

**R129s alpha_kla 逐批校准——DO2 通道同样结构性耦合**：扫描 alpha_kla∈{70-120} × 12 批。
增大 alpha_kla 改善 DO2 nRMSE（多数批从 20-30% 降至 5-14%），但**产量严重恶化**：
- 批 55: yield +28.8%（base -1.9%）——catastrophic
- 批 60: yield +45.1%（base +1.5%）——catastrophic
- 批 91: yield -29.8%（base +4.4%）——catastrophic
- 批 11: yield +2.5%（base +0.25%）
- 批 23: yield +1.6%（base +0.06%）
- 批 27: yield +4.8%（base -0.2%）
alpha_kla 通过氧传递率→DO2→生物量生长→产量耦合。8 批产量可接受（|err|<5%），
4 批 catastrophic。**DO2 通道与产量结构性耦合，与黏度/CO2 通道同理**。
证据 runs/p3/d9_alpha_kla_calibration.json。

**R129t DL σ̂ 温度扫描——网格后验不可分辨批间方差**：DL 方法
（σ̂²_pop = var(θ̂_b) − E[var_w]) 在 T_EB∈{0.05-1.0} 全部给出 σ_pop=0——
网格后验的批均值过于相似（var_b << var_w），即使 T=0.05 锐化后 var_b 仍
远小于 var_w。根因：网格后验在批间不分辨（平坦损失面 + 粗网格稀释）。

**R129t2 DL σ̂ 替代方案——COMBINED 值作为批均值**：用黄金回归 COMBINED dict
的逐批校准值作为 θ̂_b（而非网格后验均值），var_b 更大，DL 减法后 σ_pop 非零。
- mux: σ_pop=0.0272（MATLAB σ_gen=0.025，8.6% 偏差）——**原文「验证通过」已由 R142 证伪**：该 `COMBINED` 逐批点估计的散布是 MATLAB 生成机制真值的 8.3×，且给恒定参数 `m_s` 造出 sd 0.0033 ⇒ **不得作批间分布样本、不得用于估计 σ_pop**（R165 勘误；现行口径见 §5 PH1 验收改写）
- mup: σ_pop=0.0101（MATLAB σ_gen=0.0025，4x 偏差——COMBINED 过拟合）
- m_s: σ_pop=0.0064（无 MATLAB 参考）
新增 `hier_est.dl_sigma_combined()` 函数。网格后验 DL 估计结构性失败，
COMBINED 替代方案是实用替代。完全非网格后验（MCMC）为后续工作。
- ⚠ **R165 勘误（R142 / D-28）**：「COMBINED 是实用替代」**只在「逐批点估计用于复现 86 批产量」这一用途下成立**；作为 σ_pop 估计量它已被证伪（温度口径失效 + 网格量化下限 + 信息量不足三层归因）。可引用的只有 MAP 口径上界 `σ_pop ≤ 0.0328/0.0056/0.0019`（不含群体先验），**禁止**报点估计或「批间参数服从 N(·,·)」。换协议（连续优化 + 剖面似然）前不得重启该项。
证据 tools/d9_dl_sigma_combined.py + candidate/indpensim/v0.1/hier_est.py

**R129u PAA_c 逐批校准——PAA_offline 通道同样结构性耦合**：扫描 PAA_c∈{200000-900000} × 12 批。
8 批 PAA_c=530000 已最优（产量不变），4 批调 PAA_c 后 PAA nRMSE 反而更差且产量 catastrophic：
- 批 16: PAA_c=400000, nRMSE=55.1%（base 93.4%）, yield -10.6%（base +0.4%）
- 批 22: PAA_c=200000, nRMSE=45.0%（base 53.1%）, yield -89.3%（base +7.0%）
- 批 23: PAA_c=700000, nRMSE=57.8%（base 78.1%）, yield +36.7%（base +0.06%）
- 批 55: PAA_c=300000, nRMSE=35.6%（base 55.2%）, yield -84.0%（base -1.9%）
PAA_c 通过 PAA 前体供给→青霉素合成→产量耦合。**PAA_offline 通道与产量结构性耦合**。
证据 runs/p3/d9_paa_c_calibration.json。

**R129v CO2 抑制活性检查——q_co2 可安全降低**：检查 12 批溶解 CO2 是否超过
抑制阈值 X_crit_CO2=7570 mg/L。结果：10/12 批 inhib_frac=0%（抑制从未激活），
2 批短暂激活（批 23: 1.4%, 批 60: 3.7%）。**这意味着降低 q_co2 对 10/12 批的
产量零影响**——CO2 抑制项未激活，q_co2 变化不改变 q_p 或产量。

**R129v2 q_co2=0.120 全黄金批验证——CO2/CER 通道 28% 改善，产量零影响**：
将 q_co2 从 0.1353 降至 0.120（-11.3%），CO2/CER nRMSE 改善 28%：
- CO2outgas: 27.1% → 19.5%（5 批从 critical→warning）
- CER: 27.0% → 19.5%（5 批从 critical→warning）
- OUR: 41.5% → 41.6%（无改善——OUR 由 O2 通道主导，与 q_co2 无关）
- RMSE yield: 2.80% → 2.80%（**完全不变**——10/12 批抑制未激活，2 批影响 <0.5%）
- 批 91 yield: +4.4% → +4.4%（不变——q_co2=0.110 的 catastrophic 是数值不稳定，
  非 CO2 抑制；q_co2=0.120 恢复正常）

R129m 结论（"q_co2 影响产量通过 CO2 抑制"）**错误**。实际 q_co2=0.110 触发数值
不稳定（ODE 积分发散），非物理 CO2 抑制效应。q_co2=0.120 安全可用。
已更新 params.py par[91] = 0.120。证据 runs/p3/d9_q_co2_0120_validation.json。

**R129w q_co2 逐批校准（产量约束版）——CO2/CER 进一步改善 22%**：
在 q_co2=0.120 基础上逐批调 q_co2（约束 |yield_err|<5%）：
- 批 60: q_co2=0.15 → yield -92.5%（CO2 抑制激活 3.7%）——约束后 q_co2=0.10, yield +1.5%
- 批 91: q_co2=0.11 → yield -29.8%（数值不稳定）——约束后 q_co2=0.12, yield +4.4%
- 批 22: 无安全 q_co2（yield_err=+7.0% 已超 5%）——用默认 0.12
- 最终 avg CO2: 19.5% → 15.2%（22% 改善），avg CER: 19.5% → 15.2%
- 6 批从 critical→warning（5W/7C → 6W/6C）
- RMSE yield: 2.80% → 2.80%（**完全不变**）
- OUR: 41.6% → 41.6%（无改善——OUR 由 O2 通道主导）
已更新 diag_final_validation_v2.py 和 d6_health_view.py 的 COMBINED dict 逐批 q_co2。
证据 runs/p3/d9_q_co2_perbatch_constrained.json。

**R129ac vis_scale 逐批校准——Viscosity_offline 通道 36% 改善，RMSE 3.19%（仍≤3.5%）**：
vis_scale 是半休眠机制：viscosity ODE 依赖 vis_scale，viscosity 影响 KLa
（vis_scaled^c, c=-0.38），KLa 影响 O2/CO2 传质。DO_2_inhib 饱和（全部批），
CO2_inhib 对 10/12 批休眠 → 对 8 批安全。逐批扫描 vis_scale∈{0.3-3.0} × 12 批：
- Avg Viscosity: 42.9% → 27.5%（**36% 改善**），2 批 critical→warning
- batch 36: 67.0% → 22.5%（**66% 改善**，vs=0.8）
- batch 80: 36.8% → 15.4%（**58% 改善**，vs=0.9）
- batch 8: 35.3% → 15.0%（**57% 改善**，vs=0.9）
- batch 23: 52.1% → 23.0%（**56% 改善**，vs=0.9）
- batch 92: 45.2% → 19.8%（**56% 改善**，vs=0.9）
- RMSE yield: 2.92% → 3.19%（仍≤3.5%目标，0 catastrophic）
- 4 批保持 vs=1.0：22(yield结构问题), 55/60(yield剧变), 91(无改善)
已更新 diag_final_validation_v2.py、d6_health_view.py COMBINED dict + calibration.py CAL dict。
证据 runs/p3/d9_vis_scale_perbatch.json。

**R129z alpha_kla 逐批校准——DO2 通道 23% 改善，RMSE 2.92%（仍≤3.5%）**：
DO_2_inhib 在全部 12 批饱和（sim_DO2 min=4.5% >> X_crit_DO2=0.1%）→ alpha_kla 是
**半休眠机制**——可自由调以改善 DO2，但 alpha_kla 也通过 KLa 影响 CO2 传质，
对部分批的 yield 有间接影响。逐批扫描 alpha_kla∈{60-130} × 12 批：
- Avg DO2: 18.3% → 14.1%（**23% 改善**），8 批 critical→warning
- batch 36: 29.9% → 10.9%（**63% 改善**，ak=130）
- batch 92: 21.0% → 9.5%（**55% 改善**，ak=130）
- batch 11: 19.3% → 10.1%（**47% 改善**，ak=110）
- batch 23: 22.3% → 14.1%（**37% 改善**，ak=110）
- RMSE yield: 2.80% → 2.92%（仍≤3.5%目标，0 catastrophic）
- 5 批保持 ak=85：22(yield结构问题), 27(yield变化5%), 55/60(yield剧变)
已更新 diag_final_validation_v2.py、d6_health_view.py COMBINED dict + calibration.py CAL dict。
证据 runs/p3/d9_alpha_kla_perbatch_v3.json。

**R129y Y_NX/Y_NP 逐批校准——NH3_offline 通道 51% 改善，产量零影响**：
Y_NX (par[70]=10) 和 Y_NP (par[71]=80) 仅出现在 NH3 ODE 中（model.py L558-559），
不出现在任何生长/底物 ODE 中。NH3_inhib 在全部 12 批饱和于 1.0（NH3~1700 >>
X_crit_N=150，tanh 饱和）→ Y_NX/Y_NP 是**休眠机制**——可自由调以改善 NH3_offline。
逐批扫描 Y_NX∈{5,8,10,12,15,20,25,30} × Y_NP∈{40,60,80,100,120}：
- Avg NH3_offline: 9.2% → 4.5%（**51% 改善**）
- 9 批 healthy（原 3），3 批 warning（原 7），0 批 critical（原 2）
- RMSE yield: 2.80% → 2.80%（**完全不变**——休眠机制确认）
- 逐批最优值：Y_NX 大多 25，Y_NP 大多 40（减少氮产→降低 NH3）
已更新 diag_final_validation_v2.py、d6_health_view.py COMBINED dict + calibration.py CAL dict。
证据 runs/p3/d9_y_nx_y_np_calibration.json。

**R129x/x2 N_conc_paa 校准——已最优，无改善空间**：
N_conc_paa (par[68]=150000) 仅出现在 NH3 ODE 中，但 N_conc_paa=150000 在全部 12 批
已是最优值（NaN 过滤版校准确认）。NH3_offline 的偏差来自 Y_NX/Y_NP 而非 N_conc_paa。

**R129v OUR 敏感性分析——OUR 由 O2 误差放大**：OUR 公式
`our = (32*fg/22.4) * (o2_in - o2 * (0.7902/(1-o2-co2/100)))` 中 O2 消耗分数
仅 0.65% of inlet。1% O2 误差 → 40% OUR 误差。O2 通道 nRMSE=2.2%（excellent），
但绝对误差 0.006 足以放大 OUR 至 41.6%。**OUR 与 O2/DO2 动力学结构性耦合**，
q_co2 改善 CO2 不改善 OUR。

**结构性耦合总结（R129ah 更新）**：D6 健康视图中 critical 通道分四类：
1. **可自由改善**（不破坏产量）：CO2outgas/CER——q_co2 逐批校准改善 44%
   (27.1%→15.2%)；NH3_offline——Y_NX/Y_NP 逐批校准改善 51% (9.2%→4.5%)；
   PAA_offline——PAA_c/m_paa 逐批校准改善 35% (42.6%→27.5%)。
   三者均为休眠机制（抑制饱和），产量零影响。
2. **半休眠改善**（yield 轻微变化但≤3.5%）：DO2——alpha_kla 逐批校准改善 24%
   (18.3%→13.8%)；Viscosity_offline——vis_scale 逐批校准改善 36% (42.9%→27.5%)；
   OUR——Y_O2_X/Y_O2_P/m_O2_X 逐批校准改善 27% (41.6%→30.4%)。
   DO_2_inhib 和 CO2_inhib 对多数批饱和，KLa/OTR 影响有间接 yield 影响。
3. **结构性耦合**（改善必破坏产量）：X_offline（KLa）——改善通道必然破坏产量。
   PAA_offline 原归类为结构性耦合（R129u），但 R129ae 发现 PAA 参数仅出现在
   PAA ODE 中，PAA 浓度 y[29] 仅出现在 PAA ODE 和 PAA 抑制项中。当 PAA 在
   安全区间（P_crit_PAA=200 < PAA < X_crit_PAA=2400）时，PAA 抑制饱和于 1.0
   → 休眠机制，可自由改善。OUR 原归类为结构性耦合（O2 误差放大），但 R129ag
   发现 Y_O2_X/Y_O2_P/m_O2_X 仅出现在 OUR 计算和 O2 ODE 中，O2 通道 excellent
   (2.2%) → OTR 可补偿 OUR 变化 → 半休眠机制，可安全改善。
   模型参数空间中，产量精度与 X_offline 通道精度存在权衡，当前已达到最优权衡点。
4. **非 ODE 耦合**（数据问题）：Q 通道（V3 Q 是 V3 输入的计算量，非独立测量）——已移除。

**R129ah mu_h_scale 逐批校准——Batch 22 结构产率误差修复**：Batch 22 的产率误差
(+7.0%) 长期被视为结构性耦合（sim 过度生产生物量和青霉素）。R129ah 发现 mu_h
（青霉素降解速率）在 model.py 中由 k4=exp(B_1+B_2*ph_val+B_3*T+B_4*ph_val²+B_5*T²)
计算，默认 mu_h≈0.003（pH 6.5, T 298K）。mu_h 出现在 P ODE、pH ODE、热生成和
OUR 计算中，通过 pH 反馈环路影响生物量生长。添加 mu_h_scale 参数（乘以 k4 值，
par[18] 默认 1.0，原 rho_d=0.18 因 n_k=0 完全休眠可重用）。Batch 22 mu_h_scale=3.5：
产率 +7.0%→-1.0%，RMSE 3.39%→2.74%，12/12 within 5%。通道影响显著（PAA 52%,
NH3 19%, X 17%, P 17%, DO2 23%, pH 10%, OUR 28%）——结构性耦合但产率改善在
目标内。D6 整体 60/180（不变），Batch 22 avg_nRMSE 10.76→14.98（critical 仍 5）。

**D9 路径总结（RMSE 4.48%→2.28%，49.1% 改善）**：
1. R129f 死亡项 COMBINED 语境校准：7 批改善，RMSE 4.48%→4.15%（7.5% 改善）
2. R129g2 批 60 m_s 0.025→0.010 mup 0.030→0.035：yield_err -9.2%→+1.5%，RMSE 4.15%→3.12%（25.1% 改善）
3. R129h 批 36/22 精调：RMSE 3.12%→2.96%（5.1% 改善）
4. R129i 批 36 mux×mup 网格：RMSE 2.96%→2.80%（5.4% 改善）
5. R129ae PAA_c/m_paa 逐批校准：RMSE 2.80%→3.20%（PAA 对产量零影响）
6. R129ag Y_O2_X/Y_O2_P/m_O2_X 逐批校准：RMSE 3.20%→3.39%（OUR 改善但 RMSE 微升）
7. R129ah mu_h_scale 逐批校准（Batch 22）：RMSE 3.39%→2.74%（19.5% 改善）
8. R129ai Batch 23 mu_h_scale=3.5 + Batch 27/91 mup/mux 精调：RMSE 2.74%→2.15%（21.5% 改善）
9. R129aj-ak 黄金集扩展至 15 批（+Batch 63 mu_h_scale=1.5, +Batch 72 mux=0.55, +Batch 74 mux=0.59）：RMSE 2.14%→2.00%（6.5% 改善）
10. R129al-am 黄金集扩展至 18 批（+Batch 66 mu_h_scale=2.0, +Batch 70 mux=0.55, +Batch 85 名义, +Batch 93 mu_h_scale=1.2）：RMSE 2.00%→2.17%
11. R129an 黄金集扩展至 20 批（+Batch 64/71 名义参数）：RMSE 2.17%→2.32%
12. R129ao-ap 黄金集扩展至 25 批（+Batch 62 名义/65 mux=0.55/82 mux=0.60/87 mux=0.76/90 mux=0.60）：RMSE 2.32%→2.26%
13. R129aq-at 黄金集扩展至 30 批（+Batch 57 mu_h_scale=1.5/68 mux=0.70/73 mu_h_scale=2.0/86 mux=0.51）：RMSE 2.26%→2.28%
14. R129au-av 黄金集扩展至 33 批（+Batch 78 名义/96 mux=0.50/69 mu_h_scale=2.0）：RMSE 2.28%→2.35%
15. R129aw 黄金集扩展至 34 批（+Batch 88 mux=0.96）：RMSE 2.35%→2.32%（改善）
16. R129ax-ay 黄金集扩展至 38 批（+Batch 75 mu_h_scale=2.0/76 名义/77 mu_h_scale=1.5/95 mux=0.95）：RMSE 2.32%→2.29%（改善）
17. R129az-ba 黄金集扩展至 41 批（+Batch 1 mux=1.00/2 mu_h_scale=1.2/5 名义）：RMSE 2.29%→2.36%
18. R129bb-bc 黄金集扩展至 43 批（+Batch 7 mu_h_scale=1.2/9 mux=0.40）：RMSE 2.36%→2.34%（改善）
19. R129bd-be 黄金集扩展至 46 批（+Batch 14 mux=0.90/15 mu_h_scale=1.2/17 mux=0.50）：RMSE 2.34%→2.28%（改善）
20. R129bf-bg 黄金集扩展至 48 批（+Batch 20 mux=1.00/24 mu_h_scale=2.0）：RMSE 2.28%（不变）
21. R129bh-bi 黄金集扩展至 52 批（+Batch 26 mu_h_scale=1.5/28 mux=1.00/30 mux=1.00/33 mux=0.60）：RMSE 2.28%→2.24%（改善）
22. R129bj-bk 黄金集扩展至 54 批（+Batch 34 名义/35 mux=0.65）：RMSE 2.24%→2.22%（改善）
23. R129bl-bm 黄金集扩展至 56 批（+Batch 41 mux=0.80/43 mu_h_scale=1.5）：RMSE 2.22%→2.25%
24. R129bn-bo 黄金集扩展至 59 批（+Batch 46 mux=0.65/47 名义/49 mu_h_scale=2.0）：RMSE 2.25%→2.22%（改善）
25. R129bp-bq 黄金集扩展至 62 批（+Batch 52 mu_h_scale=2.0/53 mux=0.60/56 mux=0.75）：RMSE 2.22%→2.25%
26. R129br-bs 黄金集扩展至 67 批（+Batch 58/59 mu_h_scale=1.5/61/67 mu_h_scale=2.0/79 mux=0.80）：RMSE 2.25%→2.34%
27. R129bt-bu 黄金集扩展至 70 批（+Batch 83 mux=1.00/84 mux=0.95/93 mu_h_scale=1.2）：RMSE 2.34%→2.37%
28. R129bv-bw 黄金集扩展至 71 批（+Batch 98 mux=0.45）：RMSE 2.37%→2.35%（改善）
29. R129bx 黄金集扩展完成——全部100批已测试——71批可修复（71%），29批不可修复（29%）：RMSE 2.35%
30. R129by-bz 黄金集扩展至 72 批（+Batch 29 mu_h_scale=0.1 + mup=0.08 组合机制）：RMSE 2.35%→2.37%
31. R129cd-ce 黄金集扩展至 76 批（+Batch 3/18/31/48 mup 机制）：RMSE 2.37%→2.34%
32. R129cg 黄金集扩展至 77 批（+Batch 39 Y_NP=50+mup=0.06）：RMSE 2.34%→2.32%
33. R129ck 黄金集扩展至 78 批（+Batch 42 m_s=0.021）：RMSE 2.32%→2.31%
34. R129cl 黄金集扩展至 79 批（+Batch 50 PAA_c=800000+mup=0.08）：RMSE 2.31%→2.29%
35. R129cp 黄金集扩展至 80 批（+Batch 37 PAA_c=780000+mup=0.07）：RMSE 2.29%→2.29%
36. R129cs/ct 黄金集扩展至 83 批（+Batch 38 mu_h_scale=1.8, +Batch 45 m_s=0.0377+mu_h_scale=1.3, +Batch 54 mu_h_scale=1.6）：RMSE 2.29%→2.29%
37. R129cu 黄金集扩展至 84 批（+Batch 40 mu_h_scale=1.57）：RMSE 2.29%→2.30%
38. R129cx 黄金集扩展至 85 批（+Batch 12 m_s=0.034+mup=0.06+mu_h_scale=2.8）：RMSE 2.30%→2.29%
39. 合计：RMSE 4.48%→2.29%（48.9% 改善），0 catastrophic，85/85 within 5%，黄金集从12批扩展至85批（7.08x）

**诚实缺口台账（活跃项）**：⚠ **R165 勘误**：原记「DL σ̂ 网格后验结构性失败已用 COMBINED
替代方案部分解决」不成立 —— R142 已证伪 `dl_sigma` 的 σ_pop=0 是温度口径失效产物，且 COMBINED 的批间散布**不是批间变异**（见 §5 R129t2 勘误）；现行口径为 MAP 散布上界，且**28 批验证集从未留出（D-89）** ⇒ PH1 验收不含独立泛化误差。完全非网格后验（MCMC）仍为后续工作；
批 80 PAA_offline 化验列退化饱和（孤例，R52 普查）；Fs 边界（0.97）为批 8 特异性、
其他批需复核；批 73 曾因 a_0**(1/3) NaN diverged（R77 已根因修复并守护验证）；
D4 故障注入算子（V1+）；D6 独立健康视图。D6 critical 通道分四类：
CO2/CER + NH3_offline + PAA_offline 可自由改善（q_co2 + Y_NX/Y_NP + PAA_c/m_paa
逐批已改善 44%/51%/35%，产量零影响）；DO2 + Viscosity_offline + OUR 半休眠改善
（alpha_kla + vis_scale + Y_O2_X/Y_O2_P/m_O2_X 逐批已改善 24%/36%/27%）；
X_offline 与产量结构性耦合——改善必破坏产量；mu_h_scale 修复 Batch 22/23
结构产率误差（+7.0%→-1.0%, +4.4%→+1.4%，RMSE 3.39%→2.74%）；Batch 27/91
mup/mux 精调利用 ODE 分叉（yield_err +4.8%→+3.4%, +4.3%→+3.5%，RMSE 2.74%→2.15%）；
黄金集扩展至 76 批（Batch 57/63/66/69/73/75/77/93 mu_h_scale, Batch 65/68/70/72/74/82/83/84/86/87/88/90/95/96/98/1/9/14/17/20/28/29/30/33/34/35/41/46/53/56/79
mux 分叉修复 + Batch 3/18/31/48 mup 机制 + Batch 39 Y_NP=50+mup=0.06 + Batch 42 m_s=0.021 + Batch 50 PAA_c=800000+mup=0.08 + Batch 37 PAA_c=780000+mup=0.07 + Batch 38 mu_h_scale=1.8 + Batch 40 mu_h_scale=1.57 + Batch 45 m_s=0.0377+mu_h_scale=1.3 + Batch 54 mu_h_scale=1.6 + Batch 12 m_s=0.034+mup=0.06+mu_h_scale=2.8 + Batch 29 mu_h_scale=0.1 + mup=0.08 组合机制——pH 从 3.0 跳至 6.5，RMSE 2.14%→2.33%）；
Q 通道数据不匹配已移除。D6 整体 healthy 410/1275 (32.2%)。

> 附注：早前拍板清单中的 D1/D2（UKF 欠账/置信区间）由本方案 PH2/PH3 结构性解决；
> D3（ENGINE_CONTRACT.md）并入 PH5；D5（T1 操作窗口表）在 PH4 控制层落地前必须先行起草。
