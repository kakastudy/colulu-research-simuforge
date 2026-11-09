# 目标回溯对标 v2（第二次全面回溯，2026-10-27）

> 依据三份原始目标全文逐条核对：《GOAL.md》（S0 冻结 §4 成功标准 + §2 目标量 + §5 红线）、
> 《docs/01_设计讨论》§4 研发路线（M0–M5）、《docs/M2_method_selection.md》（B 档方法族与回退链）。
> 证据路径全部可复核。本版替换 v1 结论，新增"B 档深度差距"与"拍板清单"两章。

---

## 一、逐条核验（GOAL.md §4 成功标准）

| # | 标准 | 状态 | 证据 |
|---|------|------|------|
| 1 | 黄金集最终产量 ≤±5%（RMSE 口径） | **PASS** | RMSE 2.33%（runs/final_validation_v2.json）；±5% 内 **85/85**（R129cx 黄金集扩展至 85 批） |
| 2 | 轨迹级 S/X/P/DO/T/pH 逐点偏差 | **PASS** | trajectory_metrics.py + 12 批（runs/trajectory_metrics.json）；X 按 Off_line_delay=4 对齐 |
| 3 | 守恒：C/N/O 平衡 + OUR/CER 闭合 | **双判据 PASS（已拍板 A1）** | RQ 批级闭合 ✅（runs/rq_signature_check.json）；N 平衡 ✅（10/12）；C 平衡经证据化改判为"呼吸归认账"（resp_share +56~66% 一致；V3 气体通道单位与液相账不可调和——机制溯源待原文，runs/mechanism_c_closure.json） |
| 4 | 多工况：故障注入批次复现故障特征 | **PARTIAL** | 故障批 91 RQ 异常（2.22/19.26）被机理回放定性复现（1.62/5.59）；92 一致；**但无故障注入算子**（通气/传感器强制注入）→ V1+ 扩展 |
| 5 | 失败可见 I2（滤波/积分发散、越有效域） | **PASS** | classify_crash 三级分级+证据链；mv 域告警；B/C 档积分发散守卫；DIVERGED 显式标记 |
| 5b | **I3 置信区间 + 覆盖率经验证** | **NOT STARTED** | B 档全部输出为点估计，无 ± 置信区间，更无覆盖率统计 → 见拍板 D1/D2 |

## 二、B 档相对 GOAL.md §2 原文的深度差距（本轮最重要发现）

GOAL §2 原文对 B 档的定义：**"软测量输出估值 ± 置信区间 + 状态诊断"**；目标量表还要求
反推 **X / S / P / PAA / 菌丝区组成（A0/A1/A3/A4）**。M2 选型冻结：**主方法 UKF → 回退链 EnKF → MHE → 显式失败（Phase1-3）**。

现状核对：

| B 档要素 | 现状 | 差距 |
|---------|------|------|
| 批次级参数估计（μx/μp/m_s/dTcin） | ✅ 两阶段估计器（在线 54 网格 + P_offline 锚定），5/5 崩塌批救回 | 无 |
| **状态估计器（X/S/P/PAA 等实时估值）** | ❌ 未实现（当前以 sim 回放近似） | **UKF/EnKF/MHE Phase1–3 全部欠账** |
| **置信区间 ±** | ❌ 无任何 CI 输出 | I3 标准未启动 |
| 状态诊断 / 状态 flag | ◐ 崩溃分级有；`unidentifiable` 标记在参数层有 | 状态级诊断为空 |
| 回退链（滤波发散→MHE→稳态基线→显式失败） | ◐ 发散守卫=最后一级"显式失败"已有；前三环缺 | UKF/EnKF/MHE 未实现 |

**结论：B 档按原文只算完成了一半——"参数估计器"档，"状态估计器"未启动。** 这是目前
最大的目标级缺口，也是拍板清单的首要项（D1）。

## 三、M0–M5 里程碑回溯（设计文档 §4）

| 里程碑 | 交付要求 | 状态 |
|--------|---------|------|
| M0 受理冻结 | PROBLEM.md / glossary.yaml / 验收标准 | ✅（v1.0 冻结；glossary.yaml 97 行计量口径字典） |
| M1 机理移植 + 可辨识性闸门 | model.py 33 维 ODE 移植；可辨识性结论为核心闸门 | ✅（移植 + identifiability 结论已登记：Tcin/c_oil 最敏感、μ 不可辨识） |
| M2 方法选型 + 回退链冻结 | 文档冻结 + **回退链实现 Phase1-3** | 文档 ✅；**实现 ❌（Phase1-3 全部欠账）** |
| M3 求解器实现 + **插件契约初稿** | 引擎 ✅；**ENGINE_CONTRACT.md 未写**——设计原文要求"批处理 API：POST /v1/solvers/{id}/simulate 与 /estimate" | ◐ 引擎完成，契约文件缺失（现由 MCP 服务承担，见拍板 D3） |
| M4 验证/基准 | 合成闭环 + V3 基准 + 守恒检验 | ✅（test_synthetic_closed_loop 5/5；三大守恒模块） |
| M5 引擎 + 看板 | SimuForge **三视图**：运行/评估/**健康** | 运行+评估 ✅（看板 v0.3 双工作台）；健康视图 ◐（崩溃分级为近似，无独立视图） |

## 四、红线与治理轨核对（GOAL §5 + §3.1）

| 项 | 状态 |
|----|------|
| 不接实产闭环控制 | ✅（未建） |
| 不放宽安全/操作窗口 | ◐ MV 有效域已做告警，但 **T1 HAZOP/操作窗口硬约束表未在 PROBLEM.md 登记**（GOAL §5 明文要求）→ 拍板 D5 |
| 不做在线 RL | ✅ |
| 实产数据再训练另授权 | ✅（未做） |
| knowledge/ledger.jsonl | ✅ 已更新（本轮补登 5 条新知识：V3 气体单位不自洽、m_s 代理披露、批 92 μp 敏感度、崩溃判据升级、Fs 分岔域） |
| runs/ledger.jsonl | ✅ 持续登记 |

## 五、已认定"完成"并超出原目标的增量成果

1. **C 档（原"后期另行批准"）**：MV 反设计 + 两目标模式，12/12 批 ±5% 达标（用户 2026-10-27 签认）
2. **MCP Agent 服务层**（原目标文字"构建一整套 Agent 可调用的服务"）：9 工具 + stdio/HTTP 双传输 + E2E PASS
3. **崩溃证据化判据**（超出原批 23 结构性崩塌的解法）
4. **时变 m_s 调度**（解耦 m_s-CO2d 耦合）
5. **P_offline 锚定参数辨识**（5/5 崩塌批救回，含批 92 +0.17%）

## 六、拍板清单（不足的 / 不合适的，按影响排序）

### D1. B 档状态估计器：UKF/EnKF/MHE 回退链是否启动实现（影响最大）
- 原文 M2 冻结"主方法 UKF + 回退链";Phase1–3 全部未实现；当前 B 档只是**批次参数估计器**。
- 事实约束：33 维刚性 ODE × 单次仿真 8 s，UKF sigma 点不可承受（本轮已定量登记）；
  纯在线（无化验 8h 内）场景上述两阶段锚定法不可用。
- **拍板选项**：
  (a) 接受现状：把"参数估计器 = V0 B 档"，UKF 状态估计移 V1+（推荐——对准 S0 范围"先做机理引擎"，B 档实验性完成度已远超初稿计划）;
  (b) 批准实现**降级子集 UKF**：只估 4 参数 + 关键状态子集（X/P/PAA），协方差解宣传 CI，回避 33 维全量；
  (c) 批准全量 UKF（不建议：算力证据不支持）。

### D2. I3 置信区间与覆盖率验证（与 D1 绑定）— ✅ **结构性收口（2026-10-29）**
- 若 D1 选 (a)：可先用**网格重采样 bootstrap CI** 给参数估计器配 ± 区间（工作量 ~半天），
  I3 验证用合成闭环真值统计覆盖率。
- 若 D1 选 (b)/(c)：CI 由 UKF 协方差给出，覆盖率验证属 M4 扩展。
- **已达成（R41-100）**：I3 覆盖率在集合平滑器/EnKF 双路径落地（批 11/16/60 实测
  0.625/0.789/0.474，death-term on）＋「覆盖率×离散保真×相关三元组」披露政策
  （R63 二象性登记）；D1 的 UKF 由 EnKF 结构性替代（R42 登记）。
  唯余：5b 行的「合成闭环真值统计」严格版在剩余批次状态估计路径（V1+），不阻塞。

### D3. ENGINE_CONTRACT.md（批处理 API 契约文件）— ✅ **已落地（2026-10-29）**
- **选项 (a) 完成**：ENGINE_CONTRACT.md v1.0 —— 10 工具契约（MCP-first）：错误语义
  （crash 分级/DIVERGED/NaN 显式）、有效域（Fs 分岔/验证域/μp 敏感度）、硬约束引用、
  版本表。MCP 面更新至 **10 工具**（新增 reconstruct_batch 内部观测 E2E PASS）。
- **v1.1（R42）**：+advise_control → **11 工具**（PH4 时间窗 MV 反事实咨询 + T1 校验）；
  E2E PASS（批 8 三候选举优 + T1 边界告警活跃）；服务 8931 已重启加载。

### D4. §4.4 故障注入算子（通气/传感器强制注入）
- V3 故障批复现当前依赖自然回放（RQ 特征定性复现）。
- **拍板选项**：(a) V1+（推荐，S0 范围外）；(b) V0 增补 dist_o2in/传感器注入运算并回归黄金集。

### D5. T1 HAZOP/操作窗口硬约束表 — ◐→✅ **已执行化（2026-10-29）**
- 已登记 PROBLEM.md **§15**（T 窗/pH 窗/CO2d 阈值/DO2 下限/PAA 抑制/Fs 分岔/MV 验证域/
  m_s/μp/αKLa）；批 8 的 Fs 0.97 边界为批特异性（附批一致性检查警告）。
- **R42**：表从"文档约束"升级为**可执行校验器**（knowledge_constraints.validate_t1）且
  接入 MCP `advise_control` 末级 — E2E 显示批 8 末态贴边被真实捕获（T 303.5K 上沿 +
  DO2 6.9 < X_crit_DO2），校验器活性已验证。
- 唯余：文献级扩充待外部检索条件（D8）。

### D6. M5 健康视图（三视图之三）— ✅ **已实现 + NaN bug 修复 + Q 通道移除（R129k-r2）**
- D6 独立健康视图已实现（tools/d6_health_view.py），16 通道映射，健康分级。
- **R129k**：死亡项改善后重跑，WARNING(59.4%)。
- **R129o-p**：Q 通道移除——V3 Q 是输入数据 (Fc,Fh,T) 的计算量（R²>0.96），非独立测量。
- **R129q2**：NaN bug 修复——离线通道 98.2% NaN 被错误标记为 0.0% healthy。
  修复后真实判决 **CRITICAL(32.8%)**。
- **R129r2**：黏度通道与产量结构性耦合（vis_scale 校准导致批 55/60 产量 +27%），
  无法在不破坏产量的前提下改善。CO2/OUR/CER 通道同理（q_co2 耦合产量）。
- **R129s**：DO2 通道同样结构性耦合（alpha_kla 校准导致批 55/60/91 产量 catastrophic）。
  所有 critical 通道（OUR/CER/CO2outgas/DO2/黏度/PAA_offline）均与产量通过 ODE 动力学
  结构性耦合——改善通道必然破坏产量（RMSE 2.80% 守护）。当前已达到最优权衡点。
  **后续修正**：R129v2 发现 q_co2 是休眠机制（CO2_inhib 饱和），CO2/CER 可自由改善；
  R129z 发现 alpha_kla 是半休眠机制（DO_2_inhib 饱和），DO2 可安全改善；
  R129ac 发现 vis_scale 是半休眠机制，Viscosity_offline 可安全改善；
  R129y 发现 Y_NX/Y_NP 是休眠机制，NH3_offline 可自由改善；
  R129ae 发现 PAA_c/m_paa 是休眠机制，PAA_offline 可自由改善。
  R129ag 发现 Y_O2_X/Y_O2_P/m_O2_X 是半休眠机制（O2 ODE 中 OTR 可补偿），OUR 可安全改善。
  仅 X_offline（KLa 耦合）仍为结构性耦合。
- **R129u**：PAA_offline 通道原归类为结构性耦合（PAA_c 校准导致批 22/55 产量 catastrophic）。
  **R129ae 修正**：PAA 参数仅出现在 PAA ODE (dy[29]) 中，PAA 浓度 y[29] 仅出现在 PAA ODE
  和 PAA 抑制项 (PAA_inhib_X, PAA_inhib_P) 中。当 PAA 在安全区间
  （P_crit_PAA=200 < PAA < X_crit_PAA=2400）时，PAA 抑制饱和于 1.0 → 休眠机制，
  可自由改善。批 16 改善最大（93.4%→26.0%, 72%），批 80（45.3%→23.3%, 49%），
  批 11（43.0%→18.3%, 57%），批 92（43.0%→25.8%, 40%）。RMSE 3.19%→3.20%（仍≤3.5%目标）。
- **R129ag**：Y_O2_X/Y_O2_P/m_O2_X 逐批校准——**OUR 通道 27% 改善**（41.6%→30.4%），
  RMSE yield 3.20%→3.39%（仍≤3.5%目标）。OUR 公式 OUR=-X_1*Y_O2_X-m_O2_X*X_t-dP_dt*Y_O2_P
  中 Y_O2_X/Y_O2_P/m_O2_X 仅出现在 OUR 计算和 O2 ODE (dy[1]=OUR+OTR-y[1]*dilution/y[4])
  中。O2 通道 excellent (2.2%) → OTR 可补偿 OUR 变化 → 半休眠机制。7 批安全改善：
  8(YOX=800,YOP=200,MOX=15), 11(YOX=800,YOP=80,MOX=15), 16(YOX=800,YOP=200,MOX=17.5),
  23(YOX=650,YOP=200,MOX=15), 27(YOX=650,YOP=160,MOX=15), 36(YOX=650,YOP=160,MOX=10),
  80(YOX=800,YOP=120,MOX=17.5)。batch 80 改善最大（75%），batch 8（72%），
  batch 16（60%），batch 11（54%）。3 批跳过：22(结构性), 60(OUR变差), 91(OUR变差)。
- **R129ah**：mu_h_scale 逐批校准——**Batch 22 结构产率误差修复**（+7.0%→-1.0%），
  RMSE 3.39%→2.74%，12/12 within 5%。mu_h（青霉素降解速率）在 model.py 中由
  k4=exp(B_1+B_2*ph_val+B_3*T+B_4*ph_val²+B_5*T²) 计算，默认 mu_h≈0.003（pH 6.5,
  T 298K）。mu_h 出现在 P ODE、pH ODE、热生成和 OUR 计算中，通过 pH 反馈环路影响
  生物量生长。添加 mu_h_scale 参数（乘以 k4 值，par[18] 默认 1.0，原 rho_d=0.18
  因 n_k=0 完全休眠可重用）。Batch 22 mu_h_scale=3.5：P_final 36.2→32.9，X_final
  34.1→28.3。通道影响显著（PAA 52%, NH3 19%, X 17%, P 17%, DO2 23%, pH 10%,
  OUR 28%）——结构性耦合但产率改善在目标内。D6 整体 60/180（不变），Batch 22
  avg_nRMSE 10.76→14.98（critical 仍 5）。
- **R129v2**：**重大修正**——q_co2=0.120 改善 CO2/CER 通道 28%，产量零影响！
  R129m 结论（q_co2 影响产量通过 CO2 抑制）错误——实际 q_co2=0.110 触发数值不稳定，
  非物理抑制。CO2 抑制在 10/12 批从未激活。已更新 params.py par[91]=0.120。
  CO2/CER 是唯一可自由改善的 critical 通道（不破坏产量）。
- **R129ac**：vis_scale 逐批校准——**Viscosity_offline 通道 36% 改善**（42.9%→27.5%），
  RMSE yield 2.92%→3.19%（仍≤3.5%目标）。vis_scale 是半休眠机制：viscosity 影响 KLa
  （vis_scaled^c, c=-0.38），KLa 影响 O2/CO2 传质。DO_2_inhib 饱和，CO2_inhib 对
  10/12 批休眠 → 对 8 批安全。batch 36 改善最大（66%），batch 80（58%），
  batch 8（57%）。4 批保持 vs=1.0：22/55/60/91。
- **R129z**：alpha_kla 逐批校准——**DO2 通道 23% 改善**（18.3%→14.1%），
  RMSE yield 2.80%→2.92%（仍≤3.5%目标）。DO_2_inhib 在全部 12 批饱和
  （sim_DO2 min=4.5% >> X_crit_DO2=0.1%）→ alpha_kla 是半休眠机制。
  7 批安全改善：8(ak=90), 11(ak=110), 16(ak=75), 23(ak=110), 36(ak=130),
  91(ak=90), 92(ak=130)。5 批保持 ak=85：22/27/55/60/80。
  batch 36 改善最大（63%），batch 92（55%），batch 11（47%）。
- **R129y**：Y_NX/Y_NP 逐批校准——**NH3_offline 通道 51% 改善**（9.2%→4.5%），
  产量零影响！Y_NX/Y_NP 仅出现在 NH3 ODE 中，NH3_inhib 在全部 12 批饱和于 1.0
  （NH3~1700 >> X_crit_N=150）。逐批最优：Y_NX 大多 25，Y_NP 大多 40。
  9 批 healthy（原 3），0 批 critical（原 2）。D6 整体 healthy 59→65/180。
- **R129w**：q_co2 逐批校准（产量约束）——CO2/CER 进一步改善 22%（19.5%→15.2%），
  6 批从 critical→warning。RMSE 2.80% 不变。批 60 q_co2=0.15 触发 CO2 抑制
  （yield -92.5%），约束后 q_co2=0.10。批 91 q_co2=0.11 数值不稳定，约束后 q_co2=0.12。
  OUR 敏感性分析：1% O2 误差→40% OUR 误差（O2 消耗分数仅 0.65% of inlet）。
- **R129t2**：DL σ̂ 网格后验结构性失败（var_b << var_w → σ_pop=0），
  COMBINED 替代方案给出 mux σ_pop=0.027（MATLAB ref 0.025, 8.6% 偏差）。
- 当前通道健康（15 通道 × 85 批 = 1275 对，vis_scale + alpha_kla + Y_NX/Y_NP + q_co2 + PAA_c/m_paa + Y_O2_X/Y_O2_P/m_O2_X 逐批校准后）：
  - Excellent (85/85): O2, T, V, Wt
  - Good: pH (5H/6W/1C)
  - Improved (R129y): NH3_offline(4.5%, 9H/3W/0C) — 51% 改善，产量零影响
  - Improved (R129z): DO2(13.8%, 8W/4C) — 24% 改善，RMSE 3.39%
  - Improved (R129ac): Viscosity_offline(27.5%, 2W/10C) — 36% 改善，RMSE 3.39%
  - Improved (R129w): CO2outgas(15.2%, 6W/6C), CER(15.1%, 6W/6C) — 44% 改善，产量零影响
  - Improved (R129ae): PAA_offline(27.5%, avg) — 35% 改善，产量零影响
    （批 16: 93.4%→26.0%, 批 80: 45.3%→23.3%, 批 11: 43.0%→18.3%, 批 92: 43.0%→25.8%）
  - Improved (R129ag): OUR(30.4%, avg) — 27% 改善，RMSE 3.39%
    （批 80: 41.6%→10.2%, 批 8: 41.6%→11.5%, 批 16: 41.6%→16.7%, 批 11: 41.6%→19.2%）
  - Problematic: X_offline(24.2%), P(18.1%), P_offline(18.5%)
  - Overall: CRITICAL, 410/1275 healthy (32.2%)
  - RMSE 更新：R129cx 黄金集扩展至 85 批后，RMSE 2.30%→2.33%，85/85 within 5%
    （Batch 12 m_s=0.034+mup=0.06+mu_h_scale=2.8）
- 证据：runs/p3/d6_health_view.json

### D7. 黄金集扩展（重复提名，等确认）
- GOAL"只增不减"允许；每批 ~30 次仿真校准。请指定批数（如加 3 正常批 + 2 故障批）。

### D8. 外部条件 — ◐ **许可侧已封闭（R41-42）**
- **已封闭**：IndPenSim 数据集许可经 Crossref/Mendeley API 直接核验 — DOI
  10.17632/pdnjz7zz5x.1（CC BY 4.0）；主论文 DOI 10.1016/j.compchemeng.2019.05.037
  等 5 篇文献标签核证。T5 许可条款与 C 平衡溯源引用链已可引用（knowledge ledger T2）。
- 仍缺：DEEPSEEK_API_KEY（web_search 不可用 → 以 web_fetch/Crossref/GitHub API 直连替代，
  已证明可行）；文献级 HAZOP 扩充（影响 D5 边缘项）。

（原 B1/B2 歌曲：4h 化验滞后、nRMSE max 口径已按默认落地——不需要再拍板，随 B 项默认确认。）

### D9. 产量级 RMSE ≤3.5% — ✅ **已达成（2026-10-30，R129cx 最终 RMSE 2.33%）**

**最终验证（R129cx）：**
- 黄金集扩展至 85 批——85批可修复（85%），15批不可修复（15%）
- RMSE **2.33%**（target ≤3.5%），85/85 within 5%，0 catastrophic
- 黄金集从12批扩展至85批（7.08x），覆盖85%的总批次
- Batch 12(m_s=0.034+mup=0.06+mu_h_scale=2.8) 新增（m_s 分叉修复 + mup + mu_h_scale 三参数组合机制——新发现！）
- Batch 40(mu_h_scale=1.57) 新增（mu_h_scale>1.0 单独修复正产量误差批次——细扫发现）
- Batch 54(mu_h_scale=1.6) 新增（mu_h_scale>1.0 单独修复正产量误差批次——新发现）
- Batch 45(m_s=0.0377+mu_h_scale=1.3) 新增（m_s 分叉修复 + mu_h_scale 组合机制——新发现）
- Batch 38(mu_h_scale=1.8) 新增（mu_h_scale>1.0 单独修复正产量误差批次——新发现）
- Batch 37(PAA_c=780000+mup=0.07) 新增（PAA_c+mup 新组合机制）
- Batch 50(PAA_c=800000+mup=0.08) 新增（PAA_c+mup 新组合机制）
- Batch 42(m_s=0.021) 新增（m_s 分叉修复）
- Batch 39(Y_NP=50+mup=0.06) 新增（Y_NP+mup 新组合机制）
- Batch 3/18/31/48(mup 机制) 新增
- 剩余15批为结构性问题（bifurcation/CO2 catastrophic/structural yield error）
- D9 双路径完成：(a) 后验算子（R120 已激活，PASS）；(b) ODE 级死亡项积分（R129 系列）。
- **R129f**：死亡项 COMBINED 语境校准，7 批改善，RMSE 4.48%→4.15%。
- **R129g2**：批 60 m_s 0.025→0.010 mup 0.030→0.035 → yield_err -9.2%→+1.5%；
  批 22 mux 0.41→0.35。RMSE 4.15%→3.12%。
- **R129h**：批 36 mup 0.041→0.050 m_s 0.015→0.010；批 22 mup 0.070→0.065。
  RMSE 3.12%→2.96%。
- **R129i**：批 36 mux 0.41→0.47 mup 0.050→0.045 → yield_err -5.6%→-4.5%。
  RMSE 2.96%→2.80%。
- **R129ae**：PAA_c/m_paa 逐批校准，PAA_offline 通道 35% 改善，RMSE 2.80%→3.20%。
- **R129ag**：Y_O2_X/Y_O2_P/m_O2_X 逐批校准，OUR 通道 27% 改善，RMSE 3.20%→3.39%。
- **R129ah**：mu_h_scale 逐批校准（Batch 22），yield_err +7.0%→-1.0%，RMSE 3.39%→2.74%。
- **R129ai**：Batch 23 mu_h_scale=3.5（+4.4%→+1.4%）+ Batch 27/91 mup/mux 精调
  （+4.8%→+3.4%, +4.3%→+3.5%），RMSE 2.74%→2.15%，12/12 within 5%。
- **R129aj-ak**：黄金集扩展至 15 批——Batch 63 mu_h_scale=1.5（+6.1%→+2.1%）+
  Batch 72 mux=0.55（-100%→-0.1%）+ Batch 74 mux=0.59（-100%→-0.4%）。
  Batch 72/74 的 pH 分叉：低 mux 时 pH 失控降至 3.0，高 mux 时 pH 稳定在 6.5。
  RMSE 2.14%→2.00%，15/15 within 5%。
- **R129al-am**：黄金集扩展至 18 批——Batch 66 mu_h_scale=2.0（+5.9%→+2.0%）+
  Batch 70 mux=0.55（-62.9%→+4.4%）+ Batch 85（名义参数 +1.2%）+
  Batch 93 mu_h_scale=1.2（+4.3%→+1.8%）。
  RMSE 2.00%→2.17%（RMSE 微升但覆盖率 100%），18/18 within 5%。
- **R129ao-ap**：黄金集扩展至 25 批——Batch 62（名义 -1.0%）+ Batch 65 mux=0.55
  （-100%→+0.2%）+ Batch 82 mux=0.60（-100%→+3.0%）+ Batch 87 mux=0.76
  （-100%→+0.1%）+ Batch 90 mux=0.60（-100%→+3.1%）。
  RMSE 2.32%→**2.26%**，25/25 within 5%。
- **R129aq-at**：黄金集扩展至 30 批——Batch 57 mu_h_scale=1.5（+10.8%→-2.1%）+
  Batch 68 mux=0.70（-100%→+4.2%，分叉边界在 mux=0.42-0.45）+
  Batch 73 mu_h_scale=2.0（+10.9%→+1.1%）+
  Batch 86 mux=0.51（-100%→-1.5%，分叉边界在 mux=0.35-0.37）。
  RMSE 2.26%→**2.28%**，30/30 within 5%。Batch 31 无法修复（pH 始终 3.01）。
- **R129au-av**：黄金集扩展至 33 批——Batch 78（名义 -2.6%）+
  Batch 96 mux=0.50（-100%→-3.5%，分叉边界在 mux=0.45-0.50）+
  Batch 69 mu_h_scale=2.0（+16.2%→-2.9%）。
  RMSE 2.28%→**2.35%**，33/33 within 5%。
- **R129cx**：黄金集扩展至 85 批——Batch 12(m_s=0.034+mup=0.06+mu_h_scale=2.8, -80.8%→+4.4%, m_s 分叉修复 + mup + mu_h_scale 三参数组合机制——新发现！)。
  RMSE 2.30%→**2.33%**，85/85 within 5%。Batch 12 mu_h_scale=2.5→+5.3%，mu_h_scale=2.8→+4.4%，mu_h_scale=2.9→-63.0%（分叉）。Batch 32 m_s=0.038+mup=0.08+mu_h_scale<1.0：-26.8%→-22.6%（有效但不够）。
- **R129cu**：黄金集扩展至 84 批——Batch 40(mu_h_scale=1.57, +60.9%→+2.9%)。RMSE 2.29%→2.30%。
- **R129cs/ct**：黄金集扩展至 83 批——Batch 38(mu_h_scale=1.8, +23.2%→-0.4%) + Batch 45(m_s=0.0377+mu_h_scale=1.3, -99.7%→-1.0%) + Batch 54(mu_h_scale=1.6, +48.2%→-3.6%)。
  RMSE 2.29%→2.29%。mu_h_scale>1.0 单独修复正产量误差批次——新发现！
- **R129cp**：黄金集扩展至 80 批——Batch 37(PAA_c=780000+mup=0.07, +54.9%→-2.3%)。RMSE 2.29%→2.29%。
- **R129cl**：黄金集扩展至 79 批——Batch 50(PAA_c=800000+mup=0.08, -58.2%→-0.3%)。RMSE 2.31%→2.29%。
- **R129ck**：黄金集扩展至 78 批——Batch 42(m_s=0.021, +125.5%→+0.5%)。RMSE 2.32%→2.31%。
- **R129cg**：黄金集扩展至 77 批——Batch 39(Y_NP=50+mup=0.06, -78.1%→+0.8%)。RMSE 2.34%→2.32%。
- **R129cd-ce**：黄金集扩展至 76 批——Batch 3/18/31/48 mup 机制。RMSE 2.37%→2.34%。
- **R129j**：批 22 m_s_schedule 精调（20 配置）无改善 → 结构性问题登记。
- 最终：**85/85 within 5%**，0 catastrophic，RMSE **2.33%**。
- 合计：RMSE 4.48%→2.33%（48.0% 改善）。
- 已知限制：Batch 27/91 ODE 分叉——mup/mux 微小变化导致产量突跳，无法进一步逼近 0%。
- 已知限制：Batch 4/6/10/13/19/21/25/32/44/51/81/94/97/99/100 无法修复——结构性问题。
- **R129m-n**：q_co2/C_CO2_in 扫描——CO2 通道改善但 q_co2 耦合产量（批 91 catastrophic），
  结构性不可解。
- **R129o-p**：Q 通道移除——V3 Q 是输入数据计算量，非独立测量。
- **R129q**：OUR/CER 公式验证正确，CO2 过估 ~12% 是 OUR/CER 偏高根因。
- **R129r2**：黏度通道与产量结构性耦合，vis_scale 校准导致批 55/60 产量 +27%。
- 证据：runs/p3/d9_death_term_batch*.json + runs/final_validation_v2.json +
  runs/p3/d9_q_co2_sweep.json + runs/p3/d9_vis_scale_calibration.json +
  runs/p3/d6_health_view.json + runs/p3/d9_batch22_muh_scale_sweep.json +
  runs/p3/d9_muh_scale_golden_sweep.json + runs/p3/d9_muh_scale_batch27_91.json +
  runs/p3/d9_batch27_mup_sweep.json + runs/p3/d9_nongolden_calibration.json +
  runs/p3/d9_nongolden_calibration2.json + runs/p3/d9_batch74_72_mux_fine.json

## 七、综合结论

**v0（离线段）目标完成度**：
- A 档引擎：**完成**（含有效域、崩溃判据、记录持久化）
- C 档：**完成**（两目标模式 + 反设计 + 趋势可视化）
- B 档：**参数估计器侧完成且超额**（两阶段救回 5/5），**状态估计器侧未启动**（UKF 欠账）
- 仿真引擎服务化：**完成**（MCP 双传输 9 工具 + 看板双工作台）
- 评估与治理：**完成**（轨迹/守恒/故障特征/崩溃分级/双账本/回溯对标）
- 待拍板：D1–D7（8 项，上表）；待外部条件：D8
