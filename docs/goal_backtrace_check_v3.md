# 目标回溯对标 v3（第三次全面回溯，2026-11-05 R160）

> 依据三份原始方案全文逐条核对：
> - 《GOAL.md》v1.0（S0 冻结，2026-10-26 用户确认）—— §2 目标量表、§4 成功标准五条、§5 红线、§6 out-of-scope
> - 《docs/01_设计讨论》§4 研发路线（M0–M5 里程碑）
> - 《docs/M2_method_selection.md》§3 回退链冻结 + §4 Phase 1–3 实现计划
>
> **本版与 v2（2026-10-27）的区别**：v2 之后发生了 R129–R159 共 31 轮变更，
> 其中 **R156–R159 四轮是结论性变更**（D-55 机制侧关闭 → D-57 定案 → R158 否定式 → R159 撤回）。
> v2 的多处"现状"字段已失效。本版**所有"现状"均经本轮实测复核**，不复述旧文档。
>
> 证据路径全部可复核（见 §七）。

---

## 一、GOAL.md §4 五条成功标准 —— 逐条实测核验

| # | 标准（原文口径） | 状态 | 本轮实测证据 | 判定 |
|---|---|---|---|---|
| 1 | 黄金集最终产量 ≤±5%（RMSE 口径） | `runs/r156_acceptance.json` | RMSE **2.345%**、**86/86** 在 ±5%、0 新发 catastrophic | ✅ **PASS** |
| 2 | 轨迹级 S/X/P/DO2/T/pH 逐点偏差 | `runs/r156_acceptance*.json`、R151–R156 | **X**：A 档不可修复（R137 五类杠杆 72 配置全破线）→ **B 档观测器交付 nRMSE 3.17%、86/86 <15%**；**S**：残糖型状态**结构性不可辨识**（R154，0.002 g/L 残差需 0.01% 通量精度）；**P**：relRMSE 中位 15.6%，峰比 1.060 / 末比 1.021 **已达标**，缺中段 60–120 h（验收均值口径 **−0.0625** / 跨批中位数口径 **−0.0923**） | 🟡 **有界 PARTIAL** |
| 3 | 守恒：C/N/O 元素平衡 + OUR/CER 闭合 | `runs/element_balance_v2.json`、R140 | C 中位 **−1.5%**（11/12 进 ±20%，CO₂ 占 C_out 53–68%）；N **模型口径 +9.9%**（85/86 进 ±35%，b91 −60.3%）；真实计量口径 −58.1%（D-22 登记） | ✅ **PASS（须带口径）** |
| 4 | 多工况：故障注入批次可复现故障特征 | `docs/r143_round_report.md`、R157 T3-2 | b92 的 pH 凹陷经 R143 逐值反算证实来自**回放输入里的 `Fb` 撞下限**（140–160 h 恒 10.00 mL/h），非注入算子；方向可复现、**幅值不可定量**（b98 独立复现）；R127/R157 已实现 3+7 个注入算子（默认 off、零回归） | ✅ **PASS（改判）** |
| 5 | 失败可见：I2 显式输出 + **I3 置信区间覆盖率经验证** | `runs/r157_i3_channels.json`、R139/R157 | **I2**：`classify_health` 五通道（CO2d/pH 钳位/pH 越域/P 崩塌/产量破线），86/86 全部有归属（normal 77 / degraded 5 / catastrophic 4）。**I3**：`r157_i3_channels.json` 实测已验证通道 = **X + 粘度**（X 覆盖 **0.8995**、CI 半宽 5.96%、verdict=DELIVERABLE；vis DELIVERABLE）；**P** verdict=**NOT_IDENTIFIABLE**（CI 半宽 41.6%，nrmse 14.19%→17.70% 劣于 A 档）；**PAA** 同样 NOT_IDENTIFIABLE | 🟡 **有界 PARTIAL** |

**结论：标准 1 / 3 / 4 PASS；标准 2 / 5 为"有界 PARTIAL"（未达标部分已被证明不可修复 + 有量化边界 + 已登记为已知边界 B-1/B-3/B-4）。**

> **⚠️ 本轮重大修正（R160 新发现，见 §五 U-2f / D-78）**：
> 标准 5 里的 **「coverage 0.8995 / 0.8992」这个数字本身是构造性恒真的，不可作为 I3 达标的证据**。
> 该区间由**残差自身的 5%/95% 分位数**构造 ⇒ 对任意预测器（含**零信息**的常数预测）都报 ≈0.90。
> **但 T3-1 的三道硬门（改善 / 半宽上限 / 半宽<A档）不依赖 coverage**
> ⇒ **X=DELIVERABLE、P/PAA=NOT_IDENTIFIABLE 的判决本身不受影响**，
> 受影响的只是「用覆盖率数字来证明 I3 达标」这一步论证。
> 详见 `docs/r160_round_report.md` 与 `runs/r160_i3_coverage_tautology.json`。

---

## 二、里程碑 M0–M5 对照（设计文档 §4 原文路线）

```
S0 PASS ─ M0 PASS ─ M1 PASS ─ M2 PASS ─ M3 PASS ─ M4 PASS(有条件) ─ M5 in_progress
                                        │
                                        └─ cap = L2 prototype (conditional)
```

| 里程碑 | 原始交付要求 | 本轮实测状态 | 未完成部分 |
|---|---|---|---|
| **M0** 受理冻结 | PROBLEM.md / glossary.yaml / 验收标准（H 闸） | ✅ v1.0 冻结；glossary.yaml 计量口径字典；T1 操作窗硬约束表已登记 PROBLEM.md §15 并**可执行化**（`knowledge_constraints.validate_t1`，接入 MCP `advise_control`） | 无 |
| **M1** 机理移植 + 可辨识性闸门 | model.py 33 维 ODE 移植；**可辨识性结论 = 核心闸门** | ✅ 移植完成（逐点回归守护）；可辨识性结论已登记（Tcin/c_oil 最敏感、μ 不可辨识） | ⚠️ **3 项遗留未做**（见 §四 M1-遗留） |
| **M2** 方法选型 + 机理基线 + **回退链冻结** | 文档冻结 + **回退链实现 Phase 1–3** | ⚠️ **文档 ✅，实现只完成 2/3 环** | ⚠️ **MHE 约束优化（Phase 3）未实现**；回退链**降级触发器**缺失（见 §三） |
| **M3** V0 求解器实现 + 插件契约初稿 | 引擎 + 批处理 API 契约 | ✅ 引擎完成；`ENGINE_CONTRACT.md` 已到 **v1.89**（10+ 工具契约，错误语义/有效域/硬约束/版本表齐备）；MCP 服务 stdio/HTTP 双传输 | 无 |
| **M4** 验证/基准 | 合成闭环 + V3 基准复现 + 守恒检验 | ✅ 合成闭环 5/5；三大守恒模块；**M4 签核单已于 R157 重评审**（4 个 L2 阻断项实质关闭） | 无 |
| **M5** 引擎 + 看板（SimuForge **三视图**：运行/评估/**健康**） | 三视图齐备 | 🟡 **引擎 ✅ / 看板双工作台 ✅ / 健康视图 ✅（D6，`tools/d6_health_view.py`）**；但**看板对外口径未同步** | ⏸ **T1-3 + T1-4 被用户显式暂缓** ⇒ D-65 未闭合（见 §五 U-1） |

**⇒ M0–M4 实质完成；M5 的唯一欠账是"看板对外口径"，且是被用户主动暂缓的那一项。**

---

## 三、B 档方法族实现盘点（`docs/M2_method_selection.md` §3 回退链原文）

M2 冻结的回退链原文：

```
UKF 收敛 (RMSE < 阈值)
  └→ EnKF (集合协方差)
       └→ MHE + 稳态碳平衡约束
            └→ 稳态基线 / 显式失败
```

降级触发条件（原文 §3.2）：UKF 协方差 trace > 10×P₀ ⇒ 降级 EnKF；EnKF 集合 spread→0 ⇒ 降级 MHE；MHE QP 失败 ⇒ 降级稳态基线。

### 本轮实测（源码扫描 + 接口清点）

| 环节 | M2 原文要求 | 本轮实测 | 状态 |
|---|---|---|---|
| **UKF（主方法）** | 无需 Jacobian、33 维中等规模 | 源码**无** `UKF` / `unscented` / `sigma_point` 实现 | ❌ **未实现**（R42 登记「由 EnKF 结构性替代」） |
| **EnKF（回退第 1 环）** | 集合协方差、高维状态 | `observe.py`：`enkf_observe` / `enkf_update` / `_initial_ensemble` / `localized_K` / `phys_clamp` —— **完整实现**，且做了物理钳位与局地化协方差 | ✅ **已实现且为现役主力** |
| **MHE（回退第 2 环）** | 滚动优化显式处理约束 | 源码**无** `MHE` / `moving_horizon` / QP 求解器 | ❌ **未实现** |
| **稳态碳平衡基线（第 3 环）** | 降级兜底 | `mechanism_cclosure.py`（呼吸归认口径，resp_share +56%~66%）+ `conservation_metrics.py` | ⚠️ **碳账有、稳态基线解算器无** |
| **降级触发器** | 三条量化降级条件（trace/spread/QP） | `observe.py` / `soft_sensing.py` / `mcp_server.py` 中 grep `fallback` / `degrade` / `降级` **全空** | ❌ **未实现**（D-38 同型的"失败可见"缺口） |
| **显式失败** | 最后一级 | `classify_crash` / `classify_health` 五通道 + `crash_penalty` | ✅ **已实现** |
| **CI 输出 + 覆盖率** | 软测量输出估值 ± CI | `observe.py`：`coverage_check()`、`coverage_95ci`、±1.96σ 区间；`runs/r157_i3_channels.json` 三门（gain/CI 半宽上下界） | ✅ **已实现**（通道覆盖见标准 5） |

### 结论

**M2 的"回退链"当前实际是一条"单环 + 显式失败"，不是四环链。**
EnKF 收敛时可用、发散时**没有自动降级路径**，只能由调用方手工改走别的工具。
这是 GOAL §4 标准 5 里"I2 失败可见"的**结构性缺口**——失败可见做到了，但"失败后还有降级"没有。

> **⚠️ 本条为 v2 未登记的新发现。** v2 记「D1 的 UKF 由 EnKF 结构性替代（R42 登记）」，
> 但**没有系统盘点过 MHE 环、稳态基线解算器与降级触发器**这三项。
> 本轮用源码 grep 确认三者均不存在，故登记为 **D-75**。

---

## 四、未完成任务清单（按阻塞性排序）

### U-0　阻塞 `cap` 升级的**唯一**治理条件未闭合项

| # | 事项 | 实测证据 | 阻塞什么 |
|---|---|---|---|
| **U-0** | **D-65 平台看板对外口径仍是恒真数** | `platform/data.js` 实测：`"contract":"v1.69"`（生成于 2026-11-04 08:48，1.12 MB）、`"catastrophic":0` —— 而该 0 来自 D-38 已判**恒真**的 `crash_level`；现行口径应为 `classify_health` 五通道 **normal 77 / degraded 5 / catastrophic 4**。契约已 **v1.89** ⇒ **落后 20 个版本** | `cap` 从 **L2 prototype (conditional)** 升为无条件 L2；`gates.M5` 从 `in_progress` 转 PASS |

**⏸ 状态：用户 2026-11-05 显式暂缓（「平台可视化部分先不做」）。**
拆分后的确权（供解除暂缓时直接开工）：
- **T1-3**：`platform/data.js` 换数据源（`runs/final_validation_v2.json` + `d6_health_view.json` → `runs/r156_acceptance.json`）+ catastrophic KPI 改用 `classify_health` 五通道 + 契约版本自动跟随
- **T1-4**：T8 逐屏复验重跑（5 视图逐屏 + 3 交叉核对 + 新增"catastrophic KPI 与 acceptance json 一致"）

---

### U-1　目标级欠账（GOAL 原文要求，但从未实现）

| # | 事项 | 原始依据 | 本轮实测 | 建议处置 |
|---|---|---|---|---|
| **U-1a** | **B 档回退链 Phase 3：MHE 约束优化未实现** | M2 §4「Phase 3（M5+）：MHE 约束优化」 | 源码无 MHE / moving_horizon / QP | **建议记为 V1+ 显式边界**，理由：① 闭环数据同化已判不可行（R140，产量 86/86→6/86）；② EnKF 已结构性替代 UKF；③ MHE 的价值在"带约束的滚动优化"，而本项目控制路线已被 D-54 判死（连续调控封死）⇒ **MHE 的原始用途已消失**。但**降级触发器**仍有价值（见 U-1c） |
| **U-1b** | **稳态碳平衡基线解算器未实现** | M2 §3 回退链第 3 环 | `mechanism_cclosure.py` 只做**归认核算**（呼吸归认账），不是"稳态基线解算器"（不能作为降级目标输出） | 随 U-1a 一并记为 V1+ 边界 |
| **U-1c** | **回退链降级触发器缺失** | M2 §3.2 三条量化降级条件 | `observe.py` / `soft_sensing.py` / `mcp_server.py` grep `fallback`/`degrade` **全空** | ✅ **建议本轮就做**（低成本、高价值）：EnKF 集合 spread→0 或 RMSE 越阈时**显式**输出 `degraded_to_steady_baseline` 标记而非静默继续。**这与 I2「失败可见」是同一条纪律的延伸**（不许静默降级） |

---

### U-2　治理层 / 文档一致性（本轮实测发现的**新**缺陷，v2 与现行 roadmap 均未登记）

| # | 事项 | 实测证据 | 影响 |
|---|---|---|---|
| **U-2a** | **README 残留 R158 已被撤回的 A2 表述** | `README.md` 第 165–166 行仍写：「被**两点校准**（A2，中位 **0.49%**）**严格支配** ⇒ **处理失真批应优先做两点校准**」—— 这正是 **D-74 已撤回**的结论（R159 五道证伪门四门触发，剔除退化批后 A2 20.47% 劣于 C0 10.29%） | 🔴 **对外文档传播已撤回结论**。README 是交接第一入口，比台账/签核单更早被读 |
| **U-2b** | **README §4 标题写「契约 v1.87」，§5 指向 r156 报告/台账** | 实测契约已到 **v1.89**；最新应为 `docs/r159_round_report.md` + `docs/r157_debt_ledger.md` | 🟡 读者会以为落后两轮 |
| **U-2c** | **`ENGINE_CONTRACT.md` 头部状态块停在 v1.82** | 第 3 行 `> 状态：**v1.82**`，但版本表已到 v1.89（v1.83–v1.89 共 7 版未反映在头部） | 🟡 头部是"读最新一条"的入口之一 |
| **U-2d** | **`state.yaml` oq#6 的 I3 描述已过时** | oq#6 仍写「I3 覆盖率**只覆盖 X 通道**」，但 R157/T3-1 实测已扩展为 **X + 粘度**（`r157_i3_channels.json` 有 vis 通道且 verdict=DELIVERABLE） | 🟡 与签核单 R-4 口径不一致 |
| **U-2e** | **平台 `data.js` 与契约版本差 20 版** | 同 U-0 | 🔴 与 U-0 同源 |
| **U-2f** | 🔴 **I3「覆盖率 0.8995 / 0.8992」是构造性恒真数字**（R160 新发现，见 §五 D-78） | `tools/r157_i3_channels.py:212` + `tools/r138_our_observer.py:162` + `tools/r139_observer_v2.py:173` 三处**同一构造**：区间 = 残差自身 5%/95% 分位数；本轮探针 `tools/r160_i3_coverage_tautology.py` 实测：**零信息的常数预测器**与正常预测器的覆盖率**逐位相同**（Δ=0.000000，跨 4 通道均 0.899549）；逐批口径同样无判别力（Δ≤0.008） | 🟡 **判决不受影响**（T3-1 三道硬门不依赖 coverage）；🔴 但「coverage 0.8992 ⇒ I3 达标」这一步**论证须撤回**，改引区间半宽 + nRMSE 改善。**处置**：改用 `observe.py::coverage_check` 的 **μ ± 1.96σ** 口径（实测有判别力：垃圾 0.0000 vs 正常 0.1072/0.3160） |

---

### U-3　机制层欠账（已定性，多为**已知边界**而非待办）

| # | 事项 | 状态 | 说明 |
|---|---|---|---|
| U-3a | **D-52** 产素—残糖正反馈 | 🟡 维持 | `Y_sP` 直旋钮已定位，但响应是**硬阈值**（跳变跨度恒 99.83–99.99 pp） |
| U-3b | **D-54** 缺葡萄糖闭环 | 🟡 **L3** | 天花板已定：连续调控**不可行** / 开环设定点标定可行但精度 **1e−04…1e−05** ⇒ 需另行授权 |
| U-3c | **D-53** 残糖结构性不可辨识 | 🟡 维持 | 已被 D-64 独立佐证 ⇒ 转交付口径，S 通道不再作独立约束 |
| U-3d | **D-64** P/PAA 软测量结构性不可辨识 | ✅ **有量化证据的否定结论** | 不是欠账，是**已完成的边界判定**（R157/T3-1：P/PAA verdict=NOT_IDENTIFIABLE） |
| U-3e | **D-42** 60–120 h 产素缺口 | ✅ **已转已知边界** | 验收均值口径 −0.0625 / 中位数口径 −0.0923，引用须带口径（B-1） |
| U-3f | **D-41** 回放 `Fb` 无限幅 | 🟡 维持（L1） | 已降级为下游症状 |
| U-3g | **D-36** 钳位是产量标定的支撑结构 | 🟡 维持 | 候选 v2 即其解 |
| U-3h | **D-31 / D-26 / D-22 / D-27–29 / D-45 / D-47** | 🟡 待处理 | 台账未逐条展开 |

---

### U-4　小项（低风险，可立即做）

| # | 事项 | 实测证据 |
|---|---|---|
| U-4a | **D-66 缺 `pytest.ini` / `conftest.py`** | 实测项目根与 `candidate/indpensim/v0.1/` **均无**；不影响根目录跑 13/13，但 pytest 缓存与根路径解析不稳 |
| U-4b | **M1-遗留 3 项**：`state.yaml` oq#33/34/35 | ① **MATLAB rng 序列 → numpy `default_rng` 映射**待对照实验（MATLAB `indpensim_run.m:77` 等 6 处 `rng(Seed_ref+Batch_no+Rand_ref)`；Python 侧仅 `observe.py` 用 `default_rng(seed)`，**无映射对照**）；② **alpha_kla 批次间随机性（85±10）对复现精度的影响待量化**（`tools/` 下无对应产物）；③ **终末收获后处理步骤的复现方式**—— 口径**已在 PROBLEM.md §7.2 定案**（`harvested = −Σ(Fremoved·P)·h`；`end = V_last·P_last`，见 `simulate.py:945`），但 **oq#35 的表述已过时**，可关闭或改写 |
| U-4c | **`state.yaml` oq#30 已过时** | 仍写「I3 覆盖率仅 3/12 批实测，X 合并 0.630」—— R138/R139 已给 **0.8995**、R157 已扩到 X+vis |

---

## 五、本轮新登记的债务

| 编号 | 内容 | 层级 | 依据 |
|---|---|---|---|
| **D-75** | **B 档回退链实为单环**：MHE（Phase 3）、稳态基线解算器、三条降级触发器**均未实现** ⇒ EnKF 发散时无自动降级路径 | L2 | M2 §3/§4 原文 + 本轮源码 grep（`mhe`/`moving_horizon`/`fallback`/`degrade` 全空） |
| **D-76** | **README 传播了 R158 已被 D-74 撤回的 A2 结论** | L2 | `README.md:165–166` 实测 |
| **D-77** | **README §4/§5 与契约头部（v1.82）、`state.yaml` oq#6/#30 的版本滞后** | L1 | 本轮实测 |
| **D-78** | **I3「置信区间覆盖率」是构造性恒真指标**：区间由残差自身 5%/95% 分位数构造 ⇒ 对任意预测器（含零信息常数预测）恒报 ≈0.90；跨通道逐位相同 ⇒ 无判别力。**覆盖 R138 / R139 / R157 三处同一构造** | L2 | 本轮探针 `tools/r160_i3_coverage_tautology.py`（零信息预测器对照 Δ=0.000000）；三处同源代码行已定位。**判决层不受影响**（T3-1 三道硬门不依赖 coverage），受影响的是「用覆盖率证明 I3 达标」这一步论证 |

---

## 六、红线与治理轨核对（GOAL §5 + §3.1）

| 项 | 本轮实测状态 |
|---|---|
| 不接实产闭环控制 | ✅ 未建（且 D-54 判死运行期连续调控） |
| 不放宽安全/操作窗口 | ✅ T1 表已可执行化并接入 MCP `advise_control` 末级（R42，批 8 末态贴边被真实捕获） |
| 不做在线 RL | ✅ 未做 |
| 实产数据再训练另授权 | ✅ 未做 |
| `knowledge/ledger.jsonl` + `runs/ledger.jsonl` | ✅ 持续登记（双账本） |
| `knowledge_coverage` | T2 2/2 · T5 1/1（DOI 10.17632/pdnjz7zz5x.1，CC BY 4.0 已核证）· **T3 待锁定** · T7 6 条假设已登记 |
| `status_ladder` | **仅一行 `L2 prototype (conditional)`** —— 无 L3/validated/production 阶梯定义（属 V1+ 范畴） |

---

## 七、本轮回溯用的证据（可复核）

| 事实 | 复核方式 |
|---|---|
| 五条标准判定 | `runs/r156_acceptance.json`、`runs/r156_acceptance_v2.json`、`runs/element_balance_v2.json`、`docs/r143_round_report.md`、`runs/r157_i3_channels.json` |
| I3 通道逐项 | `py` 读 `runs/r157_i3_channels.json` ⇒ `channels/X.coverage=0.899548532731377`、`channels/X.verdict=DELIVERABLE`、`channels/P.verdict=NOT_IDENTIFIABLE` |
| **覆盖率构造性恒真** | `py tools/r160_i3_coverage_tautology.py` ⇒ 垃圾（零信息常数）预测器与正常预测器覆盖率**逐位相同** Δ=0.000000（X/P/PAA/vis 均为 0.899549）；逐批口径 Δ≤0.008 无判别力；**μ±1.96σ 口径有判别力**（垃圾 0.0000 vs 正常 0.1072/0.3160）⇒ 处置方案已确定 |
| B 档回退链实现盘点 | `grep -rn "UKF\|unscented\|sigma_point\|EnKF\|ensemble\|MHE\|moving_horizon" candidate/indpensim/v0.1/*.py tools/*.py`；`grep -n "^def " candidate/indpensim/v0.1/observe.py`（15 个导出函数，无 UKF/MHE） |
| 降级触发器缺失 | `grep -rn "mhe\|MHE\|moving_horizon\|fallback\|degrade\|降级" candidate/indpensim/v0.1/{observe,soft_sensing,mcp_server}.py` ⇒ **全空** |
| 平台口径滞后 | `py` 读 `platform/data.js` ⇒ `"contract":"v1.69"`、`"catastrophic":0`；`ls -la` ⇒ 2026-11-04 08:48、1.12 MB |
| README 残留撤回结论 | `grep -n "A2\|两点校准" README.md` ⇒ 第 165–166 行 |
| README/契约/state 滞后 | `grep -n "契约 v1\|r15[0-9]_round_report" README.md`；`head -1 ENGINE_CONTRACT.md` + `grep -o "| v1\.8[0-9] |"`；`yaml.safe_load(state.yaml)` 取 `open_questions[5]`、`[29]` |
| D-66 未做 | `ls pytest.ini conftest.py candidate/indpensim/v0.1/{pytest.ini,conftest.py}` ⇒ 4 个均 No such file |
| **闸门** | 零回归 `tools/r134_zero_regression.py --tol 0` ⇒ RMSE **2.345%**（红线 3.5%）、**86/86** 在 ±5%、**max\|Δ\| = 0.00e+00%**（572 s，exit 0）；pytest `py -m pytest candidate/indpensim/v0.1 -q` ⇒ **13 passed in 510.31s**（exit 0）；**引擎零改动** |
| M1-遗留 3 项 | `grep -rn "rng(" IndPenSim_V2.01/IndPenSim_V2.02/indpensim_run.m`（6 处）；`grep -rn "default_rng" candidate/indpensim/v0.1/*.py`；`grep -n "harvested" candidate/indpensim/v0.1/simulate.py` |
| 契约版本 | `grep -o "| v1\.8[0-9] |" ENGINE_CONTRACT.md` ⇒ v1.84…v1.89（头部仍写 v1.82） |

---

## 八、综合结论

**初始方案（A+B+C 全量、分阶段）的完成度：**

| 档 | 初始承诺 | 本轮实测完成度 | 缺口性质 |
|---|---|---|---|
| **A 仿真引擎** | 正问题：全状态轨迹 + 批次统计 + 诊断 | **完成并超额**（RMSE 2.345%、86/86、有效域、崩溃判据、记录持久化；C 档反设计 12/12 达标） | — |
| **B 软测量** | 逆问题：**估值 ± CI + 状态诊断** | **参数估计器侧完成并超额**（两阶段救回 5/5）；**状态估计器侧**：EnKF 已实现且交付 X + 粘度（nRMSE 3.17%、I3 0.8995）；**但回退链只完成 1/3 环**（D-75） | 🔴 **D-75：MHE / 稳态基线 / 降级触发器缺失** |
| **C 寻优** | 反设计，需另行批准 | **已批准且完成**（MV 反设计 + 两目标模式，12/12 ±5%） | — |
| **看板（M5）** | SimuForge 三视图 | 三视图齐备，但**对外口径停在 v1.69**（恒真数） | 🔴 **D-65：唯一治理条件未闭合项**（用户暂缓） |

**一句话结论：**
初始方案里**唯一真正阻塞 `cap` 升级的，是被你暂缓的平台看板口径（D-65）**；
除此之外的真实欠账是 **D-75（B 档回退链单环）**、**D-78（I3 覆盖率是构造性恒真数字）** 与 **U-2 的文档一致性缺陷**（其中 D-76 是对外传播已撤回结论，属最高优先的小项）。
A 档与 C 档不欠账 —— 157 轮的技术投入已把它们做到超预期。

---

## 九、R160 新发现的判据恒真问题（D-78）—— 补记

**发现经过**：本轮回溯时读到 `runs/r157_i3_channels.json`，注意到 **X / P / PAA / vis 四个通道的 `coverage` 浮点数逐位相同**（`0.899548532731377`），
而这四个通道的 verdict 分别是 DELIVERABLE / NOT_IDENTIFIABLE / NOT_IDENTIFIABLE / DELIVERABLE
⇒ **同一个数字不可能同时证明「X 合格」和「P 不可辨识」** ⇒ 该数字无判别力。

**根因**：三处代码是**同一构造** —— 置信区间 = 残差分布自身的 5%/95% 分位数，
再统计「有多少残差落在这个区间内」。**由构造，对任意残差分布都必然 ≈0.90。**

| 位置 | 代码 |
|---|---|
| `tools/r157_i3_channels.py:212` | `cov = float(np.mean((ar >= lo) & (ar <= hi)))`，其中 `lo, hi = np.percentile(ar, [5, 95])` |
| `tools/r138_our_observer.py:162–168` | 同款（`coverage_pointwise` / `coverage_batchwise_mean`） |
| `tools/r139_observer_v2.py:173–179` | 同款 |

**决定性检验**（`tools/r160_i3_coverage_tautology.py`，复用 R157 脚本的 `load/_fit/_predict/_nrmse`，口径逐位可比）：

| 预测器 | 逐点覆盖率 | 逐批覆盖率 | 区间半宽 |
|---|---|---|---|
| **垃圾常数预测器（零信息）** X / P / PAA / vis | **0.899549 / 0.899549 / 0.899549 / 0.899549** | 0.8970 / 0.8971 / 0.9020 / 0.8952 | 60.1% / 92.6% / 77.8% / 68.3% |
| 正常 B 档预测器 | **0.899549 / 0.899549 / 0.899549 / 0.899549** | 0.9009 / 0.8994 / 0.9031 / 0.9031 | 5.96% / 41.6% / 56.4% / 11.2% |
| **差值** | **Δ = 0.000000（全部）** | Δ ≤ 0.0078 | **Δ ≥ 31 pp（半宽有判别力）** |

⇒ **覆盖率对「预测是否携带信息」完全不敏感**（Δ 恰为 0）；
⇒ 但**区间半宽有判别力**（垃圾 60.1% vs 正常 5.96%，差 10 倍）——
这正是 T3-1 三道硬门里的第 2/3 道在起作用。

**影响面（精确界定）**：

| 项 | 是否受影响 | 说明 |
|---|---|---|
| T3-1 的 **X=DELIVERABLE / vis=DELIVERABLE** 判决 | ❌ 不受影响 | 三道硬门（改善 >1pp / 半宽 ≤ 上限 / 半宽 < A档误差）**均不依赖 coverage** |
| T3-1 的 **P / PAA = NOT_IDENTIFIABLE** 判决 | ❌ 不受影响 | 同上；且它们的否决理由（改善为负 + 半宽 41.6%/56.4% 超限）本就来自硬门 |
| 「coverage 0.8995 ⇒ I3 达标」这一步**论证** | ✅ **须撤回** | 该数字是构造产物，不构成独立证据 |
| 签核单 B-3 / R-4 与 README 中的 **「X 逐点覆盖 0.8992」** | ⚠️ **须改口径** | 0.8992 同源于 R138/R139 的同一构造（`runs/p3/r138_our_observer.json` 的 `ci.coverage_pointwise = 0.8992`）⇒ **同受 D-78 覆盖** |
| 标准 5 的**总体判定**（有界 PARTIAL） | ❌ 不变 | 本来就是 PARTIAL；D-78 进一步**收紧**了它缺什么 |

**处置方案（已实测确定可行）**：改用 `candidate/indpensim/v0.1/observe.py::coverage_check` 的
**μ ± 1.96σ** 口径 —— 区间来自**预测的 σ**（而非残差分位数）⇒ 垃圾预测器 σ→0 时覆盖率趋 **0.0000**，
正常预测器给出名义覆盖率（X 0.1072 / P 0.3160）⇒ **有判别力**。
该函数已存在，只是多通道评估脚本（`r157_i3_channels.py`）没有采用它。

**纪律（本轮第 15 条）**：
> **由分位数构造的区间，其覆盖率必然等于名义值 —— 这不是「达标」，是同义反复。**
> 凡引用覆盖率，必须同时引用**区间半宽**与**相对更简单基线的改善**；
> 且必须做一次**零信息预测器对照**（把预测换成常数，看指标是否还"达标"）。
> 本轮即用这个对照把一个跨三轮、支撑过 M4 阻断项 6 销号的数字证伪。
