# 待审阅事项清单（2026-10-27 会话后汇总；2026-10-27 用户裁决后更新）

> **裁决状态更新（用户："根据你的建议来，继续"，2026-10-27）**：
> A1/A2/A3/A4 均按推荐选项落地：A1 选项 1（呼吸归认口径）已实现
> （mechanism_cclosure.py，resp_share +56%~+66%）；A2 已采纳为正式验收口径；
> A3 C 档批准已签到（本记录即签认，含 MV 有效域告警已落地 simulate.attrs["mv_warnings"]）；
> A4 已由网格精细化解决（批 92 mup=0.0322 → +0.17%，5/5 救回）。
> 下方清单的"领裁决"一节已全部处置，其余 B/C 项仍待后续裁决/确认。

> **PH2/P4 v0.2 激活完成（R120，2026-10-30）**：P4 五闸 verdict=PASS（G1 88/88、
> G2 hier_prior_v2、G3 β R²=0.666/n=621、G4 覆盖率 0.629、G5 探针 10/10）；
> D9 裁决方案 a（后验算子）激活——ENGINE_CONTRACT.md v1.2；黄金回归守护重跑
> 4.48%/0/12/9 逐字保持（激活零回归）；激活条目已入双账本。产量级 RMSE ≤3.5%
> 目标挂 V1+ 机理增强（D9-b 不实施）；DL σ̂=0 债务挂 PH3+。

---

## A. 需要裁决（影响验收口径或路线）— **已全部处置（见顶部更新）**

### A1. §4.3 元素平衡验收口径 ✅（选项 1 落地）
### A2. 批 23 崩溃判据改判采纳 ✅（正式采纳，catastrophic 0/12）
### A3. C 档正式批准与 MV 算子有效域 ✅（签到；告警已落地）
### A4. B 档路线 ✅（批 92 mup=0.0322 → +0.17%；5/5 救回；MHE/UKF 转"纯在线场景"候补）

---

## B. 建议确认（不阻塞，但需知晓/签字）

1. **m_s 逐批校准的物理披露**：m_s 是"缺失细胞死亡动力学"的代理补偿，
   不是真实维持系数。任何对外报告必须带此披露（防误读物理含义）。
2. **化验滞后 4h 口径**（T7）：X/P/NH3/PAA/ viscosity 对照均按
   `Off_line_delay=4` 对齐（indpensim_run.m L49）。已在 trajectory_metrics
   落地；请确认此口径为准。
3. **nRMSE 双口径**（均值/最大值）：S 通道在批 22/23 的均值口径发散
   （S→0 的批均值小），建议以 max 口径为准（数值见 PROBLEM.md §14.1）。
4. **黄金集扩展**：目前 10 正常 + 2 故障；可增设故障批（GOAL"只增不减"允许），
   但会触发重新回归。
5. **Mendeley 数据许可登记**（T5）：DOI + 许可文本待正式登记进 knowledge ledger。
6. **枢纽环境**：web 检索在当前环境不可用（DEEPSEEK_API_KEY 缺失）；
   如需外网证据链（T2 文献、T5 许可文本）请提供 key 或数据。

---

## C. 已登记的后续路线（无需立即裁决）

1. **V1+ 影子运行**（GOAL §M5→V1、需实产授权、out-of-scope 当前）。
2. **故障特征级专项对比**（GOAL §4.4）：**已出首个定量版（2026-10-27）**——
   sim RQ 复现批 91 异常方向（1.62 vs V3 2.22 相对正常批 0.87-0.91），幅值部分
   复现（p95 5.59 vs 19.26）；证据 runs/rq_signature_check.json。剩余：故障注入
   模式级仿真（通气/传感器强制注入算子）→ V1+。
3. **机理侧 C 平衡自洽核算**：**已落地**（mechanism_cclosure.py，呼吸归认口径
   resp_share +56%~+66%，见 A1 裁决记录）。
4. **M5 看板常驻部署方式**：已验证 headless 可运行（HTTP 200 + health=ok）；
   常驻选型（Streamlit 常驻 vs MCP http 8931）待运维决定。
5. **Raman/PAA PLS（L2 候补组件）**消融验证：资产核证（b 10×212 系数，212 通道，
   PAA_PLS_model.mat）。**数据可用性普查（R48-49，tools/probe_raman_mat*.py）**：
   V6/V7 .mat 仅 Batch_01/02 两个示范批含真实合成光谱（Batch_01 Intensity 2200×1215，
   99.2% 非零）；V3 大 CSV 波长列全零；工作区无批池 61–90 实测光谱；Mendeley 文件级
   列表 API 不可用（400）/S3 直链 403 → **P3 外部数据缺口如实登记**。
   两路径：(a) 引擎侧合成层 —— Raman_Sim.m 以引擎状态前向合成光谱（状态已全可达），
   可作 PAT 前向观测通道（V1+，需翻译 ~200 行 MATLAB+种子噪声复刻）；(b) 等 Mendeley
   Raman 原始文件下载（需人工浏览器获取）。路径 (a) 与 PLS 资产自洽（PLS 本就对
   Raman_Sim 合成谱标定）→ 推荐 (a)。
6. **黄金集扩展**（B4）：待用户确认数量后执行（每批需 ~10-20 次仿真校准）。
7. **Mendeley DOI/许可文本**（B5）：已解除——DOI 10.17632/pdnjz7zz5x.1 核证 **CC BY 4.0**
   （R41-42，Crossref/Mendeley API 直连）；文献桥 5 锚已入 PROBLEM.md §15（R48）。
   仅余 DEEPSEEK_API_KEY（web_search 不可用，直连 API 替代可行——已证明）。
8. **Raman (a)-路径工程化**（V1+）：`tools/raman_pipeline.py` 合成+PLS 复刻已完成三重
   验证（0.9995/0.9997/0.8463）；剩余 = 与引擎状态的大规模接线 + PAA 锚定修正层
   （R53 发现公式层口径问题 → PAT 作校正源）+ 评估三元组范式扩展到 PAT 通道。
9. **PAA 通道保真短板**（R52-54 登记）：引擎 PAA vs 化验 r=−0.34@lag0（批 22）；
   启用路径=PAA 锚定修正（化验驱动）或机理增强（PAA 抑制项结构修订）——V1+。
   **R121 根因确认**：时序错位（引擎峰值早于化验 144-180h, 高 μp 批生产相提前开启）,
   非幅值偏差为主。修正方向 = PAA 方程增加相门控项（D9-b ODE 级机理增强, V1+）。
    证据 runs/p3/paa_shape_probe.json。
    **R122 实施完成**：相门控函数 f_paa = floor+(1-floor)*mean_P/(mean_P+s) 已入 model.py
    **R123 维护消耗修复 + 降解项**：m_PAA 原代码用 P（青霉素）但 MATLAB 原文用 X（生物量）→
    **R124 反相门控降解**：恒定降解修复幅度但时序崩溃 → 新增 paa_degrad_inverse_gate
    **R124d m_PAA 批特异性**: 2D 扫描确认 m_PAA 需批特异性校准。批 22 m_PAA=1.0
    **R125 逐批 m_PAA + degrad 校准实施**: PAA_CAL dict 加入 calib_params。
    **R126 结构限制诊断**: 批 27 校准更新（amp 3.068→1.606）。批 80 R52 数据饱和
    **R127 D4 故障注入算子**: 三种故障类型实现(model.py+simulate.py), 默认off零回归。
    **R128 D6 独立健康视图**: 基线参数×12批逐通道健康评估。物理通道全healthy,
    **R129 ODE级衰亡项**: 批91 TV death ds=60 kd=0.005 → yield_err=0.0002
    (本质完美)。S_max=102.6(从94.2改善)。PAA门控移除。证据
    runs/p3/d9_death_term_tv_batch91.json。
    气体交换通道全critical(根因: 生物量轨迹不准)。PAA 10/12 critical。
    证据 runs/p3/d6_health_view.json。
    批91 氧限制 mag=0.58 RMSE_S改善但yield恶化; mag=0.62崩溃阈值。根因是death term
    非氧限制。批92 pH扰动不需要。证据 runs/p3/d4_fault_injection_probe.json。
    （非模型问题）。批 16 双峰/批 23 平滑上升——结构性限制。D9(b) PAA 工作实质完成。
    证据 runs/p3/paa_per_batch_verification.json。
    4/12 批优秀（批 36/60/92/91 corr>0.95 amp~1.0）。批 22 mode0+m_paa=1.0
    +deg=0.01 → amp=1.084（门控反有害）。批 27/80/23 结构性问题。
    证据 runs/p3/paa_per_batch_verification.json。
    +degrad=0.010 → amp=1.381(从3.1x大幅改善); 批 60 m_PAA=0.50 → amp=1.069(近完美)。
    m_PAA=0.10 为最安全通用值。批特异性 m_PAA 校准挂 V1+。
    证据 runs/p3/paa_mpaa_degrad_2d_sweep.json。
    （degrad=rate*PAA*(1-f_paa)，溢出代谢物理依据）。高 μp 批（22/23）反相门控
    优势显著：批 22 inv_deg0.0045 corr=0.893 lag=0h amp=3.10；批 23 inv_deg0.001
    corr=0.106 amp=0.984（近完美）。批 22 幅度 3.1x 仍结构性（V1+ 喂食模型重构）。
    黄金回归 RMSE 4.48%/0/12/9 逐字保持。证据 runs/p3/paa_degrad_fine_sweep.json。
    新增 paa_maintenance_target（0=P/1=X）+ paa_degrad_rate（一阶降解）+ m_paa 可覆盖。
    批 23/36/60 幅度修复验证通过（degrad=0.002-0.010）。批 22 幅度过冲结构性
    （存在尖锐阈值：修复幅度即崩时序）。黄金回归 RMSE 4.48%/0/12/9 逐字保持。
    证据 runs/p3/paa_maintenance_fix_probe.json + paa_degrad_sweep.json。
    （paa_gate_mode 参数, 默认 0=off 黄金回归零回归）。时序修复验证：批 22 corr -0.231->+0.856
    lag -144h->0h。幅度过冲（4.5x）需 PAA 参数重校准（V1+ 后续）。证据 runs/p3/paa_gate_probe.json。
10. **A_t1 双约定符号治理**（R65/R73-76）：代码内三处 docstring/注释已声明口径；
    记录列 `sim["A_t1"]`（60→4500）与公式层 a0/(a1+a3+a4)（0.51→0.22）不可互换——
    后续任何使用者先读注释再动手（T7 记录在案）。
11. **集合带「窄而偏/宽而盖」二象性**（R63）：spread 校准需偏倚修正与膨胀分离；
    覆盖率三元组披露政策已在台账。V1+ 候选：不依赖网格后验的 DL σ̂ 复权（PH3+ 债务）。
12. **model.py a_0 NaN 边界**（R77）：已修复（a_0_pos 钳 0）+ 黄金回归守护 PASS；
    后续 batch 若再现 diverged 应直接走 `tools/debug_batch73_rd.py` 的根因链模板。

---

## D. 本会话工件索引（快速复核入口）

| 工件 | 内容 |
|------|------|
| runs/final_validation_v2.json | 12 批复验（RMSE 4.48%、crash 分级证据链；R77 补丁后重生成精确保持） |
| runs/hier_est/death_term.json | PH2 死亡项 β（R²=0.666, 621 点）——G3 权威口径 |
| runs/hier_est/p4_death_probe.json | P4 升级前探针（10/10 黄金批 X nRMSE 改善中位 −15.3pt） |
| runs/hier_est/p4_upgrade_verdict.json | P4 闸门判决快照（**verdict=PASS**，G1-G5 全过，R120 激活） |
| runs/hier_est/paa_fidelity_census.json | PAA 保真度批间普查（批异质 + μp 机理锚点 −0.891） |
| runs/hier_est/pat_triple_census.json | PAT 三重判据全黄金批普查（10/10 批与引擎 PAA 逐批对账一致） |
| runs/p3/raman_pat_batch80.json | PAT 前向通道演示（诚实口径 note） |
| docs/ph2_acceptance_draft.md | PH2 验收草稿（tools/make_ph2_acceptance.py 自动生成） |
| docs/raman_pat_integration_spec.md | Raman (a)-路径 V1+ 设计稿（三元组判据 + 工作分解） |
| candidate/indpensim/v0.1/ | calibration.py（校准 SSOT + v0.2 算子）+ mcp_server.py（11 工具） + knowledge_constraints.py（T1 校验器 + PAA PAT 触发器） |
| candidate/indpensim/v0.1/model.py | 引擎（含 R77 a_0 NaN 健壮性钳制） |
| docs/goal_backtrace_check.md | GOAL §4 逐条核验（D3/D5/D8 状态已于 R42-49 更新） |
| PROBLEM.md §13/§15 | 技术叙事 + T1 操作窗硬约束表（含文献桥 5 锚） |
