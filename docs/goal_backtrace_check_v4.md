# 目标回溯对标 v4（第四次全量回溯，2026-11-05 R163 后 —— **deepening_plan 专项**）

> **本版与 v3 的根本区别**：v3 的回溯源是 GOAL.md + 01_设计讨论 + M2_method_selection 三份，
> **遗漏了 `docs/deepening_plan.md`**（2026-10-29 定案、50 KB、含四层架构 + PH1–PH5 分阶段路线 +
> 「目标重述」三用途）。
> 该文件是 **PH1–PH5 与四层架构的唯一原始出处**，也是 `residual_discovery.py` / `hier_est.py` /
> `observe.py` / `mcp_server.py` 的设计依据 ⇒ **它从 R42 起被实施，却从未被回溯对标**。
> 本版把它补进来，并**首次**把 GOAL §2 的「目标量表」逐项对标（v3 只对标了 §4 五条成功标准）。
>
> **本版所有「现状」字段均经本轮实测复核**，不复述旧文档叙述；凡引用旧文档结论而该结论
> 已被后续轮次推翻的，一律标注「旧文档陈述已失效」并给出现行产物口径。
>
> **本轮未改引擎一行**（`candidate/indpensim/v0.1/*.py` mtime 全部停在 2026-11-05 21:44 及以前）⇒ 零回归基线不受影响。
>
> **配套产物**：本轮结论已排成 **R164 任务清单**（17 项）⇒ `docs/roadmap_next.md` **§8.6**；
> 新增债务 **D-88 / D-89** 已登记进台账 / 签核单（R-14）/ 契约（v1.94）/ README / `state.yaml` / 工具索引 / 工作记忆。

---

## 一、为什么要补这一版：三个此前未被发现的事实

| # | 事实 | 证据 |
|---|---|---|
| **1** | **`deepening_plan.md` 从未被回溯对标过** —— v3 的三份回溯源里没有它 ⇒ PH1–PH5 的完成度、PH5 的服务化缺口、PH1 验收项的失效，**在治理层全部无记录** | `grep -c "deepening_plan"`：`goal_backtrace_check.md` **0**、`goal_backtrace_check_v3.md` **0**、`roadmap_next.md` **0**、台账 **0**、签核单 **0**、README **0**、`tools/INDEX.md` **0**；仅 `ENGINE_CONTRACT.md`（v1.62 版本行）与 `state.yaml`（oq）各 1 处，**且两处都只是把它当作「旧数值的出处」**（"R131/deepening_plan 的旧数值属旧参数口径"）⇒ **它从未作为「研发目标与阶段路线」进入治理层视野** |
| **2** | **GOAL §2 的「目标量表」从未逐项对标** —— v3 只对标了 §4 五条成功标准 ⇒ 七个目标量里有两个（**菌丝区组成 A0/A1/A3/A4**、**μx/μp 的批间分布**）的交付状态一直未知 | `GOAL.md:12-22` 目标量表；v3 全文无「目标量」逐项表 |
| **3** | **`deepening_plan.md` 自身已有 4 处陈述漂移** —— 其 §8 叙述停留在 R131 快照，且 PH1/PH2 的结论已被 R142 推翻 ⇒ 若按它排下一步，会把两个**已证伪的结论**重新排进队列 | 见本文 §五 |

---

## 二、`deepening_plan` §3 四层架构 —— 逐层实测对标

原文（`docs/deepening_plan.md:103-117`）：

```
第 1 层  机理主干 f
第 2 层  批次随机效应层 θ_b：hierarchical MAP/EM，先验 = MATLAB 生成分布
第 3 层  残差结构发现 D(x)：SINDy 式候选库稀疏回归
第 4 层  在线内部观测器 + 控制
```

| 层 | deepening_plan 原文要求 | 本轮实测状态 | 判定 |
|---|---|---|---|
| **第 1 层** 机理主干 f | 已验证 4.48% | RMSE **2.345%**、**86/86** 在 ±5%、0 catastrophic；黄金集 12 → **86 批**（7.2×） | ✅ **完成并超额**（超出 39 轮） |
| **第 2 层** 批次随机效应 θ_b | hierarchical MAP/EM；先验 = MATLAB 生成分布（μx~N(0.41,0.025²) 等）；CI 天然产生 | MAP 网格后验 ✓；88 批 v2 池 ✓；**σ̂_pop 两条估计路径均被 R142 证伪**（`hier_est.dl_sigma` / `hier_est.dl_sigma_combined` 的 docstring 自带证伪说明）；现可引用的唯一口径是 MAP 散布上界 `σ_pop ≤ √var_b(MAP)` | 🟡 **结构在、分布口径失效** |
| **第 3 层** 残差结构发现 D(x) | SINDy 式候选库稀疏回归 →「发现的缺失动力学」 | `residual_discovery.py`（`sparse_fit` / `discover_batch` / `votes`）✓；`runs/hier_est/residual_discovery_full.json`：**88 有效批、0 发散**；`knowledge_constraints.py` 有 PH2 候选库 ✓；PH2 验收 **verdict = PASS**（G1–G5 全过，β R²=0.6663、n=621、探针改善 10/10、中位 −15.3 pt） | ✅ **已实现且已验收**（唯一弱点：投票仅作「辅助披露」，一致性裁决靠人工定向 β 拟合） |
| **第 4 层** 在线内部观测器 + 控制 | 降阶 EnKF/MHE：状态子集 (S,P,X,A0/A1,PAA,CO2d) + 随机游走增广参数 (μp,m_s)；**化验到达时融合（12h/4h 滞后显式建模）**；CI = 集合离散度；I2 状态诊断；控制 = 滚动 2–8 h 窗 MV 倍率反设计 + Fs 分岔边界硬约束 | 化验融合 ✓（`observe.ASSAY_OFFSET = 4.0` + `assim_online`/`assim_assay`）；MHE ✓（R161/163）；稳态基线 ✓（R163）；I2 ✓（`classify_health` 五通道）；CI ✓（±1.96σ）；`advise_control` ✓ + T1 校验器 ✓ | 🟡 **观测通道子集 ≠ 原文状态子集**；**控制侧验收项未达成**（D-54 判死运行期连续调控） |

### 2.1 第 4 层的「降阶」实际未实现（技术细节）

原文要求「**降阶** EnKF/MHE：状态子集 (S, P, X, A0/A1, PAA, CO2d)」。实测：

- 滤波对象是**全 33 维状态 + 2 个增广参数行**（`observe.PARAM_ROWS = (33, 34)`）⇒ **没有降维**；
- 实际起约束作用的是**局地化增益** `observe.localized_K` + `observe.ALLOWED` 映射表：

| 观测通道 | 可更新的状态块 | 备注 |
|---|---|---|
| `DO2 / T / pH / CO2outgas / O2 / Q` | 对应单状态 | 在线通道 |
| `vis_assay / NH3_assay` | `vis` / `NH3` | 化验 |
| `P_assay / PAA_assay` | `P`+参数行33 / `PAA`+参数行33 | 化验 |
| `X_offline` | 走 `ident_map` 特殊分支（映射到 A 组生物量）—— **⚠ R165 勘误**：`observe.py:243-257` 中 `ident_map["X_offline"]=None` 且 `if ch == "X_offline": continue` ⇒ 该通道被**完全排除同化**，A 组从未被任何观测更新 | 化验（仅事后上报 `X_sum`/`X_sd`，不进 `act_obs`） |
| **S** | **无**（`ALLOWED` 无 `S` 键） | ⇒ **S 从不被任何观测直接更新**，始终跟随模型轨迹 |
| **A0 / A1 / A3 / A4** | **同化层 rank=0**（`H_assim` 无任何 A 组索引）；`X_offline` 被排除同化；仅 `records` 事后上报 `X_sum`/`X_sd` ⇒ `H_report` rank=1 / nullity=3 | ⇒ 四个形态状态**结构不可辨识**（`docs/r165_mycelium_identifiability.md` 11/11 PASS），不是「仅经 X_offline 间接约束」 |

⇒ **S 与 A0–A4 的不可辨识是「观测设计」问题，不是「参数」问题** ——
这解释了 D-53（残糖不可辨识）与本轮新发现的菌丝区组成不可达（§四）为何同源。
原文明列的六个状态里，**只有 X（经 A 组）、P、PAA 三个有真实观测通道**，且 P/PAA 的软测量判决
为 `NOT_IDENTIFIABLE`（R157/T3-1）。

---

## 三、`deepening_plan` §5 分阶段路线（PH1–PH5）—— 逐阶段实测对标

| 阶段 | 原文要求（含验收判据） | 本轮实测 | 判定 |
|---|---|---|---|
| **PH1** 逆向建模基础设施建设 | ① 批池 100 → 训练 60 / 验证 28 / 黄金 12（分层）② θ_b 的 (μ̂,Σ̂) 从 60 批 MAP 估计 ③ **验收：先验分布与 MATLAB 生成机制一致性（μ̂≈0.41±0.025 等数值对齐）；黄金集零接触** | ① `data/processed/batch_pool.json`（sealed 2026-10-27，seed 20261027，`stratify(fault, yield_quartile)`）✓ ② 88 批 v2 池 MAP 拟合 ✓（`runs/hier_est/train_theta_v2.jsonl`，432 KB）③ 黄金集零接触 ✓ | 🟡 **两项验收未达成**：σ̂ 口径被 R142 证伪（见 §五 D2）；**28 批验证集在 v2 池中被并入训练**（`hier_est.py:276`：`batch_list = bp["train"] + bp["validation"]`）⇒ 验证集**从未被留出**（新增 **D-89**） |
| **PH2** 残差结构发现 | 逐批残差 γ(t)= 数据−引擎（X/P/S）；SINDy 候选库稀疏回归；**验收：黄金集叠加 D(x) 后 RMSE 4.48% → ≤3.5% 且不破坏守恒账** | `residual_discovery.py` + 88 批产物 + PH2 验收 **PASS**；RMSE 实测 **2.345%**（**超额达成 ≤3.5% 目标**）；守恒账 C 中位 −1.5% 未破坏 | ✅ **完成（超额）** |
| **PH3** 在线内部观测器 | 降阶 EnKF（50 集合，0.2 h 周期，观测=在线+补化验）+ MHE 备份 + 稳态碳平衡兜底；**验收：合成闭环上 X/P/PAA 重构误差带 CI；覆盖率经验证（I3 首次落地）；批 91/92 特征保持** | EnKF ✓（`observe.enkf_observe`）；MHE ✓（R161 `mhe_step` / R163 `mhe_rolling`）；稳态基线 ✓（R163 `steady_state_for_batch`）；CI ✓（±1.96σ `coverage_check`）；I3 覆盖率经验证 —— **X + 粘度 DELIVERABLE、P/PAA NOT_IDENTIFIABLE**（R157/T3-1）；批 91/92 特征保持 ✓（R143/R157） | 🟡 **有界 PARTIAL**：**P/PAA 的重构误差未达标**（结构性不可辨识，D-64）；「降阶」未实现（§2.1） |
| **PH4** 控制求解器 | 滚动窗反设计：观测器状态 → 2–8 h 窗 MV 倍率寻优 → 产量/偏差控制；**验收：合成场景（含有效域告警触发）全过；对照「固定配方」提升量化** | `advise_control` 上线 ✓；T1 校验器 `knowledge_constraints.validate_t1` ✓（批 8 末态贴边被真实捕获）；**但 D-54 判死运行期连续调控**（连续不可行 / 开环设定点标定可行但精度 1e−04…1e−05） | 🔴 **验收项「对照固定配方提升量化」未达成** ⇒ 应转**已知边界**（与 D-42 同处置） |
| **PH5** 服务化扩展 | MCP 新工具 **4 个**：`reconstruct_batch`（离线重构±CI）、**`observe_online`（降阶观测器）**、`advise_control`（滚动反设计）、**`discover_residual`（PH2 结构发现）**；看板新增「**观察-控制工作台**」页 | 现行 MCP **12 工具**：`solver_info` / `simulate_batch` / `evaluate_batch` / `golden_set_validate` / `estimate_batch` / `estimate_batch_stage2` / `reconstruct_batch` / `batch_fallback_tier` / `optimize_feed` / `advise_control` / `trajectory_check` / `element_balance_check`；`observe_online` **0 处命中**（契约 + 源码）、`discover_residual` **0 处命中**；看板现有三视图 = **运行 / 批次 / 评估-健康**，**无「观察-控制工作台」** | 🔴 **PH5 交付缺 2 工具 + 1 工作台**（`reconstruct_batch` 与 `advise_control` 已交付） |

### 3.1 PH5 缺口的性质说明

`residual_discovery.py` 与 `observe.py` 的**能力都已存在**，缺的只是**服务化封装**：

- `discover_residual` ⇒ 应包装 `residual_discovery.discover_batch` + `votes`（88 批产物已有）；
- `observe_online` ⇒ 应包装 `observe.enkf_observe` 的降阶观测形态（R42 记「observe_online 以 EnKF/重构形态兑现」，
  但**从未落成一个独立工具名**，契约里也从未登记）。

⇒ **PH5 的缺口是「交付形态」缺口，不是「能力」缺口** —— 补齐成本低，但不能省。

---

## 四、GOAL §2 目标量表 —— **首次逐项对标**（本版新增）

`GOAL.md:12-22` 的目标量表列了 **7 个目标量**。v3 未逐项对标 ⇒ 逐项实测如下：

| # | 目标量 | 反推途径（原文） | 本轮实测交付状态 | 判定 |
|---|---|---|---|---|
| 1 | **OUR / CER** | 尾气 O₂/CO₂ 质量平衡 | 守恒闭合 **PASS**（C 中位 −1.5%、11/12 进 ±20%）；OUR 通道 nRMSE 30.4%（R129ag 逐批校准后） | ✅ **达标**（口径须带） |
| 2 | **μx / μp** | OUR → 化学计量（Y_O2_X/Y_O2_P） | **作为逐批标定量**已交付（黄金回归 COMBINED dict）；**作为批间分布（σ_pop）不可用** —— `dl_sigma` 与 `dl_sigma_combined` 均被 R142 证伪（mux 散布 8.3×、mup 4.0×、给恒定 `m_s` 凭空造出 sd 0.0033）⇒ 现仅可引 `σ_pop ≤ √var_b(MAP)` | 🟡 **点估计达标 / 分布口径失效** |
| 3 | **X** | OUR/CER + 离线干重化验对齐 | **B 档观测器交付 nRMSE 3.17%、86/86 <15%**；I3 `X` verdict = **DELIVERABLE** | ✅ **达标** |
| 4 | **S** | 进料/消耗平衡 + 离线化验 | **结构性不可辨识**（R154：0.002 g/L 残差需 0.01% 通量精度）；且观测器 `ALLOWED` 中**无 S 键** ⇒ 从不被直接更新 | ❌ **不可辨识（已定边界）** |
| 5 | **P** | 离线 HPLC + 动力学 | A 档 relRMSE 中位 **15.6%**、峰比 1.060 / 末比 1.021 **已达标**，缺 60–120 h 中段（验收均值口径 −0.0625）；**B 档软测量 verdict = NOT_IDENTIFIABLE**（CI 半宽 41.6%，nrmse 14.19%→17.70% 劣于 A 档） | 🟡 **有界 PARTIAL** |
| 6 | **PAA** | 离线化验 + Raman（既有 PLS 资产） | B 档 **NOT_IDENTIFIABLE**；Raman/PAT 通道**不含独立信息**（D-71，增量 R² 0.0199 / t 0.104）；且 V6 批 61–90 的 `PAA_offline` 是**占位值**（D-73，CV < 2%）；PLS 资产**单位非 mg/L**（D-70，差 ~1000 倍） | ❌ **不可辨识 + 数据退化 + 量纲错误** |
| 7 | **菌丝区组成 A0/A1/A3/A4 (g/L)** | **动力学状态反推（软测量扩展）** | 🔴 **V3 数据中无 A 组实测列**（`data/processed/batches/batch_*.csv` 共 37 列，**无任何 A 组列**）⇒ **没有任何可用于验证的实测**；黏度只约束**总生物量**（`a_0^(1/3)` 口径，R129r：实测为线性关系 ⇒ 结构不匹配）；Raman 通道已被 D-71 否证 ⇒ **原设计的「软测量扩展」路径已关闭** | 🔴 **数据资产级不可达**（新增 **D-88**） |

### 4.1 第 7 项的含义（这是本版最重要的负面结论）

`deepening_plan.md:66`（§0 已有资产衔接）原写：

> 「Raman/PAA PLS 资产（b 10×212）+ Raman 批池 61–90（30 批实测有 Raman 光谱）｜**内部观测增强：PAA/菌丝的额外观测通道**」

⇒ **deepening_plan 把 Raman 当作菌丝区组成的观测通道**。R158 全池消融证明该通道**不含独立信息**（D-71），
而 V3 数据本身也没有 A 组实测 ⇒ **两条可能的观测通道同时关闭**。

⇒ **GOAL §2 的第 7 个目标量不是「工程欠账」，而是「数据资产级不可达」**：
在本项目可用的数据资产下，菌丝区组成**无法被验证**，只能作为**软测量内部量**存在。
这条在 GOAL 冻结时（2026-10-26）**没有任何记录**，在 163 轮之后**仍然没有记录**。

---

## 五、`deepening_plan` 自身的陈述漂移（4 处）

**若按 deepening_plan 原文排下一步，会把两个已证伪的结论重新排进队列** ⇒ 必须先勘误。

| # | deepening_plan 的陈述 | 现行产物口径 | 处置 |
|---|---|---|---|
| **D1** | §8 PH2 行：「30 批中票 A_t1 = **60 站点 63% 负向**」 | `runs/hier_est/residual_discovery_full.json`：**全池 88 有效批**、A_t1 best-subset **命中 12 站、负向 5**、0 发散；`docs/ph2_acceptance_draft.md` 判读：「命中率低属预期（导数空间子集搜索未优化的 A_t1 信号弱）」，**一致性裁决以 β 拟合同口径为准** | ⚠️ 旧叙述**已失效**（是更早的 30 批口径）；**引用须改为 88 批口径** |
| **D2** | §8 PH1 行 / R129t2 段：「DL σ̂ 替代方案 —— mux: σ_pop=**0.0272**（MATLAB σ_gen=0.025，8.6% 偏差）—— **验证通过**」 | **R142 已证伪该函数可用性**：`hier_est.dl_sigma_combined` 的 docstring 明写「COMBINED 的批间散布是 MATLAB 真值的 **8.3×(mux) / 4.0×(mup)**，且给**恒定参数** `m_s`（真值 0）造出 sd 0.0033 ⇒ 它是『把结构误差吸进参数的补偿器』，**不是批间分布样本**」；mux 的「接近」来自两个错误互相抵消 | 🔴 **旧结论已被推翻** ⇒ deepening_plan 的 PH1 验收判据「数值对齐」**不可达成**，须改口径 |
| **D3** | `docs/ph2_acceptance_report.md` §五：「D9 方案 (b) ODE 级积分未实施；**产量级 RMSE ≤3.5% 需机理增强项（V1+）**」 | **实际已达 RMSE 2.345%**（86 批，0 catastrophic）⇒ 该「诚实缺口」早已闭合，但验收报告**未回填** | ⚠️ 报告待回填（否则读者会以为产量目标仍未达成） |
| **D4** | 头部快照停在 **R131（2026-11-03 12:00）** | 现行契约 **v1.93**（R163）⇒ **落后 32 轮**；期间新增 D-75~D-87 共 13 条债务 | ⚠️ deepening_plan 应补一条「R163 快照」或明确标注「§8 叙述为历史快照，以路线图/台账为准」 |

---

## 六、GOAL §4 五条标准 + M0–M5（承接 v3，更新至 R163）

| # | 标准 | v3 判定（R160） | **R163 后现状** | 变化 |
|---|---|---|---|---|
| 1 | 产量 ≤±5% | ✅ PASS | ✅ PASS（RMSE 2.345%、86/86、0 catastrophic；R163 零回归 `max|Δ|=0.00e+00`） | — |
| 2 | 轨迹级 | 🟡 有界 PARTIAL | 🟡 有界 PARTIAL | — |
| 3 | 守恒 | ✅ PASS | ✅ PASS | — |
| 4 | 故障特征 | ✅ PASS（改判） | ✅ PASS（改判） | — |
| 5 | I2 + I3 | 🟡 有界 PARTIAL | 🟡 有界 PARTIAL；**I3 的 coverage 论证已撤回**（D-78），改引区间半宽 + nRMSE 改善 | 论证收紧 |
| — | **M2 回退链** | 单环（D-75） | **四环算子齐备 + 已接入现役 MCP 路径**（R163-1，opt-in 默认关、逐位零回归、Z1–Z3 PASS）；**但判据可信度存疑**（D-87：真实数据上触发率 **84.38%**） | 🟡 形式完成、判别力待修 |
| — | **M5 看板** | in_progress（D-65 暂缓） | 同左 | — |

**`cap` 口径不变（L2 prototype conditional）**：唯一阻塞项仍是 **D-65 平台看板对外口径**（用户 2026-11-05 显式暂缓）。

---

## 七、M2 §3 回退链冻结原文 vs 现行实现

| 环节 | M2 §3.2 判据 | 现行实现 | 状态 |
|---|---|---|---|
| UKF（主方法） | 协方差 trace > 10×P₀ ⇒ 降级 EnKF | **未实现**（R42 由 EnKF 结构性替代） | ⛔ 已被替代（历史遗留，非待办） |
| EnKF | 集合 spread → 0 ⇒ 降级 MHE | `observe.enkf_observe` + `solver_chain` 健康度 5 条判据 | ✅ 已实现（**但创新判据 D-87 近乎恒真**） |
| MHE | QP 失败 / 残差无结构 ⇒ 降级稳态基线 | `solver_chain.mhe_step` / `mhe_estimate_batch` / `mhe_rolling` + **边界退化判据（D-86）** | ✅ 已实现（R161/R163） |
| 稳态基线 | C 平衡误差 > 20% ⇒ 显式失败 | `solver_chain.steady_state_for_batch`；b91 实测 **−20.10%** ⇒ 显式失败 | ✅ 已实现（R163） |
| 降级标记 | 不得静默输出貌似合理的数 | `reconstruct_batch(fallback_chain=True)` 返回体含 `tier`/`degraded`/`reasons`/`trace`/`reconstruction_valid` | ✅ 已实现（R163-1，Z1–Z3 PASS） |

⇒ **M2 §3 的回退链已从「单环」变成「四环 + 现役接入」** —— 这是 R161–R163 三轮的主要成果，
**但它建立在一个在真实数据上触发率 84.38% 的健康度判据之上**（D-87）⇒ 形式完备 ≠ 可用。

---

## 八、新登记的两条债务

### D-88　GOAL §2 目标量「菌丝区组成 A0/A1/A3/A4」**数据资产级不可达**　🔴 **R164 新增，L2（原始目标）**

| 项 | 内容 |
|---|---|
| 发现 | `GOAL.md` §2 目标量表列了 7 个目标量，其中第 7 项「菌丝区组成 A0/A1/A3/A4 g/L」，反推途径写「动力学状态反推（软测量扩展）」。实测：`data/processed/batches/batch_*.csv`（100 批 × 37 列）**无任何 A 组实测列**；**R165 勘误**：引擎 `dy[9]` 只依赖 **A0 单室**（`model.py:660-674`），既非总生物量亦非 `total_X`；「黏度≈1.77·X+12.4」只是 R129r 实测经验关系（相关性 0.81–0.85），二者不等价；`deepening_plan` §0 指望的 Raman 通道已被 R158 消融否证（D-71：增量 R² 0.0199 / t 0.104）。⇒ **两条候选观测通道同时关闭** |
| 后果 | 该目标量**无法被验证**（不是「做得不够」，是「没有可对照的实测」）；而 `deepening_plan` §0 把它列为 Raman 资产的用途 ⇒ 资产与目标之间的映射已随 D-71 失效。**163 轮以来治理层从未记录此缺口** |
| 边界 | **R165 升级为双重结论**：① **结构不可辨识（观测设计层）** —— 现有观测算子 `H_assim` rank=0 / nullity=4、`H_report` rank=1 / nullity=3，只增加同类数据不改变列空间秩；② **数据资产级不可验证** —— 37 列无 A 组实测 + Raman 被 D-71 否证，换含形态测量的数据可解。两者边界是**是否改变 H 的列空间**。本轮仍**不**新增观测通道、**不**改引擎（详见 `docs/r165_mycelium_identifiability.md`） |
| 建议 | ① GOAL §2 目标量表第 7 行**改口径**：由「目标量」降为「软测量内部量（无实测锚点，不作交付）」，并在 §4 成功标准中显式说明；② 若要保留该目标，需立项获取含菌丝形态测量的数据（V1+，超本轮边界）；③ **部分可辨识性研究已由 R164-7 / R165 完成并给出数值证明**（观测算子结构秩亏 11/11 PASS；黏度不是总量约束，动力学层对分室敏感） |
| 证据 | `data/processed/batches/batch_01.csv` 列清单（37 列，无 A 组）；`candidate/indpensim/v0.1/model.py:6`（A 组状态索引 10–14）；`model.py` 黏度方程 `a_0^(1/3)`；`runs/r158_pat_ablation_scale.json`；`docs/r158_round_report.md`（D-71/D-72） |

### D-89　PH1 的 **28 批验证集从未被留出**（v2 池把 train+validation 合并拟合）　🟡 **R164 新增，L2（方法）**

| 项 | 内容 |
|---|---|
| 发现 | `deepening_plan` P4 与 PH1 均规定「88 = 60 训练 + 28 验证分层（正常/故障分层抽样）」，`data/processed/batch_pool.json` 也确实按 `stratify(fault, yield_quartile)` 落了 60/28/12。但 `candidate/indpensim/v0.1/hier_est.py:276` 实际执行 `batch_list = bp["train"] + bp["validation"]  # v2 全批池（训练+验证）` ⇒ **28 批验证集被并入训练**，从未被留出 ⇒ 基于该池的任何超参数/温度/网格选择都是**训练集内选择** |
| 后果 | PH1 验收判据「先验分布与 MATLAB 生成机制一致性」的**独立性前提不成立**；σ̂ 估计（D-88 之外的 D2 议题）即便换协议重估，若仍用同一池也**无法给出独立的泛化误差** |
| 边界 | 本轮**不**重跑 88 批池（成本高且结论已被 R142 证伪覆盖）；**不**改 `hier_est.py` |
| 建议 | ① 明确登记为「验证集未使用（已知边界）」，并**改写 PH1 的验收口径**（σ̂ 用 MAP 散布上界 + 注明不含群体先验，且**不**声称有独立验证）；② 若要真正闭合，须：(a) 恢复 28 批留出，(b) 在留出集上复算 v2 池的收敛性与 σ̂，(c) 或改协议为连续优化 + 剖面似然/Laplace（R142 指定），并先解 D-29；③ 在此之前，**禁止**引用「验证集」作为任何泛化性论据 |
| 证据 | `candidate/indpensim/v0.1/hier_est.py:276`；`data/processed/batch_pool.json`（`split_policy` 字段）；`candidate/indpensim/v0.1/hier_est.py` `dl_sigma` / `dl_sigma_combined` 的 docstring（R142 证伪说明） |

---

## 九、结论：初始研发目标的完成度（四份原始方案合并口径）

| 档 / 阶段 | 初始承诺 | 完成度 | 缺口性质 |
|---|---|---|---|
| **A 仿真引擎** | 全状态轨迹 + 批次统计 + 诊断 | **完成并超额**（RMSE 2.345%、86/86、有效域、崩溃判据、持久化） | — |
| **B 软测量 · 参数级** | 逆问题：估值 ± CI + 状态诊断 | **完成并超额**（两阶段救回 5/5、EnKF/MHE/稳态基线四环齐备并接入现役路径） | — |
| **B 软测量 · 状态级** | X / S / P / PAA / 菌丝区组成 | **X + 黏度达标；P/PAA/S 不可辨识；菌丝区组成不可验证** | 🔴 **D-88**（数据资产级） |
| **C 寻优（反设计）** | 反设计，需另行批准 | **已批准且完成**（MV 反设计 12/12 ±5%） | — |
| **控制（PH4）** | 滚动 2–8 h 窗 MV 倍率反设计 + 提升量化 | **工具已上线，提升量化未达成**（D-54 判死运行期连续调控） | 🔴 应转**已知边界** |
| **PH5 服务化** | MCP 4 工具 + 观察-控制工作台 | **2/4 工具 + 0/1 工作台** | 🔴 交付形态缺口（能力已在） |
| **PH1 层次先验** | σ̂ 与 MATLAB 机制对齐 | **口径失效**（R142 证伪两种估计量）+ 验证集未留出 | 🟡 **D-89** |
| **PH2 残差发现** | SINDy + RMSE ≤3.5% | **完成且超额**（RMSE 2.345%） | — |
| **PH3 在线观测器** | 六状态子集 + CI + I3 | **三通道达标、三通道不可辨识**；「降阶」未实现 | 🟡 有界 PARTIAL |
| **看板（M5）** | SimuForge 三视图 | 三视图齐备，对外口径停在 v1.69 | 🔴 **D-65**（唯一阻塞 cap 的治理项，用户暂缓） |

**一句话结论**：
**在「产能模型」维度上，初始方案已经超额完成（86 批、2.345%、四环回退链接入现役路径）；
真正的剩余缺口集中在三处 —— ①「内部观测体系」的一半目标量（S/P/PAA/菌丝区组成）被证明在现有数据资产下不可辨识或不可验证；
②「控制」用途被 D-54 判死而 PH4 的验收判据从未按此改写；
③ deepening_plan 自身从未被回溯对标，导致它的 PH1 验收项（已失效）、PH5 交付缺口（2 工具 + 1 工作台）
与 GOAL §2 第 7 项目标量（不可达）三件事在治理层长期无记录。**

---

## 十、本轮回溯用的证据（可复核）

| 事实 | 复核方式 |
|---|---|
| deepening_plan 从未在回溯源中 | `grep -n "deepening_plan" docs/goal_backtrace_check_v*.md` ⇒ 0 命中 |
| MCP 12 工具清单 | `grep -n "^def " candidate/indpensim/v0.1/mcp_server.py` ⇒ 12 个工具级函数 |
| `observe_online` / `discover_residual` 缺失 | `grep -c` 于 `ENGINE_CONTRACT.md` 与 `mcp_server.py` ⇒ **均为 0** |
| 看板三视图、无观察-控制工作台 | `grep -n "工作台\|视图\|<h2" platform/index.html` ⇒ 运行 / 批次工作台 / 评估-健康 |
| ALLOWED 无 S 键、无 A 组 | `candidate/indpensim/v0.1/observe.py:68-74` |
| V3 无 A 组实测列 | `pd.read_csv("data/processed/batches/batch_01.csv").columns` ⇒ 37 列，无 A 组 |
| ~~黏度只约束总生物量~~ **R165 勘误：黏度生成项只依赖 A0 单室** | `model.py:660-674` `dy[9] = vis_scale·3·a_0_pos**(1/3)·…`；`total_X` 定义在 `model.py:315` 但**不在黏度方程里**；R129r 的 `vis≈1.77·X+12.4`（相关性 0.81–0.85）是另一条实测经验关系 |
| σ̂ 两估计量被证伪 | `candidate/indpensim/v0.1/hier_est.py` 的 `dl_sigma` / `dl_sigma_combined` docstring（R142） |
| 验证集被并入训练 | `candidate/indpensim/v0.1/hier_est.py:276` |
| PH2 全池 88 批产物 | `runs/hier_est/residual_discovery_full.json` ⇒ n_batches 88、n_effective 88、diverged []、A_t1 命中 12 站 / 负向 5 |
| 死亡项 β 拟合 | `runs/hier_est/death_term.json` ⇒ R² 0.6663、n 621、std 4.616→2.6667 |
| PH2 验收 verdict | `docs/ph2_acceptance_report.md` ⇒ PASS（G1–G5 全过） |
| 契约与零回归基线 | `ENGINE_CONTRACT.md` 头部 v1.93 / 版本表最大 v1.93；`runs/r163_zero_regression.json` ⇒ RMSE 2.345%、86/86、`max|Δ| = 0.00e+00` |
| 本轮未改引擎 | `ls -la candidate/indpensim/v0.1/*.py` ⇒ mtime 全部 ≤ 2026-11-05 21:44 |
