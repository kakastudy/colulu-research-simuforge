# 第五次全量回溯 —— 整体研发成果 / 基础工作完备性 / 平台装载缺口

> 日期：2026-11-06　|　轮次：R166 收口之后、平台升级之前
> 性质：**只读回溯**，不修改任何引擎源码、平台源码或治理文本
> 前序：`goal_backtrace_check.md` / `_v3.md` / `_v4.md`；本次是 v5

---

## 0. 回溯源（本次全部纳入）

| 类别 | 文件 |
|---|---|
| 目标与边界 | `GOAL.md` v1.0（含 R166 §2 第 7 行修订）、`PROBLEM.md`、`docs/01_设计讨论_…md`、`docs/M2_method_selection.md` |
| 研发计划 | `docs/deepening_plan.md`（PH1–PH5 + 四层架构 + 拍板清单）、`docs/roadmap_next.md` §8.1–§8.8 |
| 治理层 | `ENGINE_CONTRACT.md` **v1.96**、`docs/m5_review_signoff.md`（R-1…R-16）、`docs/r157_debt_ledger.md`（D-52…D-91）、`state.yaml` |
| 轮次报告 | `docs/r157…r166_round_report.md`、`docs/r166_verdict.md` |
| 实测证据 | `runs/r166_{final_check,ab_gate,v2_optim,mcp_smoke,zero_regression,governance_update}.json`、`runs/r166_ab_gate_first_pass.json` |
| 代码实体 | `candidate/indpensim/v0.1/*.py`、`platform/*`、`requirements.txt` |

相较 v4，本次**首次把 `platform/` 代码实体、MCP 装载链路、`cap` 的治理条件**纳入同一张完备性判定表。

---

## 1. 里程碑与闸门（截至 R166）

| 闸门 | 状态 |
|---|---|
| S0 / M0 / M1 / M2 / M3 / M4 | **PASS** |
| **M5（引擎 + 看板）** | **in_progress** —— 引擎侧完成，看板对外口径待复验（`state.yaml:5,48,83`） |
| `cap` | **L2 prototype (conditional)**；授权范围 = 引擎侧 + 验收层 + X 通道 B 档，**不含看板对外口径** |
| 唯一阻塞 | **D-65**（平台看板口径恒真 + 版本滞后），2026-11-05 用户显式暂缓 |

R166 终检 **54/54 PASS**；86 批逐位零回归 `max|Δ| = 0.00e+00` / RMSE **2.345%** / **86/86** within ±5%；`py -m pytest -q` **33 passed**；MCP 冒烟 **9/9 PASS**；A/B 证据闸门 **18/20 NO_GO**（仅 V2-3 / V2-4 保留原始 FAIL）；V2 多轮寻优 **NO_GO**（8/10）。

---

## 2. GOAL §4 五条成功标准（`docs/roadmap_next.md` §8.1）

| # | 标准 | 判定 |
|---|---|---|
| 1 | 产量 ≤ ±5%（RMSE） | ✅ **PASS**（2.345%、86/86） |
| 2 | 轨迹级逐点指标 | 🟡 **有界 PARTIAL** —— X 由 B 档交付（nRMSE 3.17%、86/86 <15%），S 结构性不可辨识（D-53），P 缺口已定量化 |
| 3 | C/N/O 守恒 + OUR/CER 闭合 | ✅ **PASS** |
| 4 | 故障注入批次可复现特征 | ✅ **PASS（改判）** —— R143 撤销原命题，特征由回放输入解释；幅值不可定量属输入饱和 |
| 5 | I2 失败可见 + I3 覆盖率 | 🟡 **有界 PARTIAL** —— I2 已落地；**D-78 证伪 coverage 是构造性恒真指标**，判决保留但论证撤回 |

> 标准 2 / 5 的 PARTIAL 是**已定案的已知边界**，不是待办；GOAL §5 红线一字未改。

---

## 3. `deepening_plan` PH1–PH5 逐阶段对照

| 阶段 | 原验收判据 | 当前判定 | 依据 |
|---|---|---|---|
| **PH1** 逆向建模基础设施 | 先验 μ̂≈0.41±0.025 与 MATLAB 生成机制对齐；60/28/12 分层 | ⚠️ **口径改写** —— R142 证伪 σ̂ 温度口径（D-89：`hier_est.py:276` 把 train+validation 合并拟合，**28 批验证集从未留出**）；现行只引 **MAP 散布上界**（σ_pop(mux)≤0.0328 / mup≤0.0056 / m_s≤0.0019，不含群体先验），且**不含独立泛化误差** | `deepening_plan.md:141-148`、`docs/m5_review_signoff.md` B-19 |
| **PH2** 残差结构发现 | 叠加 D(x) 后 RMSE 4.48% → **≤3.5%**、不破坏守恒 | ✅ **达成（实测 2.345%）** —— 死亡项 β R²=0.67、88 有效批 / A_t1 命中 12 站；v0.2 算子等价性 0.00e0；R164-3 已回填 `docs/ph2_acceptance_report.md` §五 | `deepening_plan.md:150-153`、R164-3 |
| **PH3** 在线内部观测器 | 降阶 EnKF + MHE + 稳态碳平衡；X/P/PAA 带 CI；**I3 首次落地** | ✅ **能力完成 / ⚠️ CI 论证撤回** —— 四环算子在 `solver_chain.py` 全部落地，D-80 已由 R163 以 opt-in 接入现役 MCP 路径；但 **D-78** 判定 coverage 构造性恒真、**D-87** 判定创新判据在真实数据触发率 84.38%（近乎恒真）⇒ 判据层仍在 opt-in 候选状态（V1 条件批准、未切默认） | R161 / R163 / R166 |
| **PH4** 控制求解器 | 滚动窗反设计、有效域告警、对照固定配方提升量化 | ⚠️ **转已知边界** —— D-57 判决性实验证明 `sd`/`mean_P`/`Y_sP` 响应是**硬跳变**（跨度恒 99.8–101.5 pp），两侧无可用梯度区分度 ⇒ **运行期连续调控封死**；开环设定点标定保留但落点精度 1e−04…1e−05（标定级非控制级） | `docs/m5_review_signoff.md` B-9 / B-18、D-54 |
| **PH5** 服务化扩展 | MCP 4 新工具 + 看板新增「观察-控制工作台」页 | 🟡 **工具侧完成 / 平台页未完成** —— MCP 工具 **9 → 12 → 14**（R164-1 补齐 `discover_residual` / `observe_online`，12/12 PASS）；**看板「观察-控制工作台」仍缺**，且 D-65 平台口径统一受用户暂缓 | `deepening_plan.md:163-165`、`README.md:427`、`roadmap §8.8 (c)` |

**拍板清单闭环**：P1（R2 混合）✅ / P3（Raman 第二期）✅（后由 D-71 定为不引入交付）/ P4（60/28/12）⚠️ 被 D-89 证伪为未留出 / 新模型版本 v0.2 ✅。

---

## 4. 研发成果盘点（按代码实体分层）

### 4.1 仿真引擎层（A 档，L0 冻结基线）

| 模块 | 角色 | 状态 |
|---|---|---|
| `model.py` | 33 维 ODE 机理主体（Birol 族 MATLAB 移植） | 现役、冻结 |
| `simulate.py` | `simulate_open_loop` / `yield_metrics` / `classify_crash` / `trajectory_metrics`；现役积分器 = `solve_ivp(BDF)` | **全项目枢纽**，被所有上层引用 |
| `golden_params.py` | 86 批 `COMBINED` 黄金参数 + 唯一装配口径 | 冻结，禁止覆盖 |
| `calibration.py` / `params.py` | 校准参数 SSOT / 参数构造 | 现役 |
| `integrators.py` | 纯 numpy RK4 兜底 | **未被任何模块 import**（备用算子，未接线） |
| `contract.py` | `SimRequest` / `SimResult` 插件契约草稿 | **全项目无第二处引用**（未接线） |

### 4.2 求解器层（B/C/D 档逆问题）

`observe.py`（EnKF / 集合平滑 / 覆盖检验）、`soft_sensing.py`（54 组合网格反演）、`stage2_estimator.py`（μp 锚定 P_offline）、`optimize.py`（MV 倍率 Nelder-Mead）、`solver_chain.py`（**四环回退链**：EnKF → MHE → 稳态碳平衡 → 显式失败）、`hier_est.py`（分层 MAP/EM）、`calibrate.py`、`residual_discovery.py`（SINDy 稀疏辨识）。**八件全部存在且可运行**。

### 4.3 算子层（项目自定义 12 算子目录，`platform/export_data.py:171-206`）

`model.rhs`(ODE) / `integrate_interval`(积分器) / `simulate_open_loop`(主仿真) / `yield_metrics`(指标) / `classify_crash`(判据) / `build_params`(装配) / `estimate_batch`(B 档反演) / `estimate_stage2`(二阶段) / `optimize_feed`(C 档寻优) / `hier_est`(分层估计) / `conservation_metrics`(守恒) / `trajectory_metrics`(通道指标)；另有 `validate.py`（86 批黄金集并行复验）、`runstore.py`（哈希持久化）、`knowledge_constraints.py`（T1 操作窗硬约束 + PAT 触发）。

### 4.4 服务化层

`candidate/indpensim/v0.1/mcp_server.py` —— **14 个 `@mcp.tool`**，A/B/C/D 全档：
`solver_info` / `simulate_batch` / `evaluate_batch` / `golden_set_validate` / `estimate_batch` / `estimate_batch_stage2` / `reconstruct_batch` / `batch_fallback_tier` / `optimize_feed` / `advise_control` / `trajectory_check` / `element_balance_check` / `discover_residual` / `observe_online`。
R166 用**官方 SDK 内置 `mcp.server.fastmcp.FastMCP`** + `_OfficialSDKFastMCP` 兼容层关闭 D-85（零新增依赖、14 工具函数体逐字未变、冒烟 9/9）。

### 4.5 平台层（`platform/`）

| 实体 | 形态 | 与引擎的连接 |
|---|---|---|
| `index.html` / `app.js` / `style.css` | 五视图静态前端（回归总览 / 过程拓扑 / 批次工作台 / 通道诊断 / 仿真算子库） | 只读 `window.FERM_DATA` 快照 + `fetch("/api/health")` / `fetch("/api/simulate")` |
| `serve.py` | stdlib `ThreadingHTTPServer`，`127.0.0.1:8770` | `sys.path.insert` 直接 `from simulate import simulate_open_loop, yield_metrics, classify_crash`；**只挂 A 档开环回放**，14 个参数覆盖白名单 |
| `export_data.py` | 离线批量导出 → `data.js` + 86 个 `.cache/bNN.json` | 是（离线预生成） |
| `mcp_server.py` | MCP stdio / HTTP 8931 | **与 platform 前端零连线**（`app.js` / `index.html` / `serve.py` grep `mcp|8931|fastmcp` 零命中） |
| `dashboard.py` | Streamlit 三工作台（8501） | 与 `platform/` 无关，且 `streamlit` 未锁进 `requirements.txt` |

---

## 5. 基础工作完备性判定（本回溯的核心结论）

### 5.1 已完成并可冻结（数值/算法/验收层 = **100%**）

- A 档机理引擎移植、86 批黄金参数、`BDF` 积分、有效域/崩溃判据：完成且**逐位冻结**。
- B 档四环回退链、C 档寻优、D 档显式失败、残差发现、分层估计：算子与求解器**全部存在且可运行**。
- PH5 工具侧 **14/14** 工具装载进 MCP，端到端冒烟 9/9。
- 全套证据闸门：终检 54/54、pytest 33、零回归 86 批、A/B D-78 合规。
- 治理文本：契约 v1.96 / 台账 D-91 / 签核单 R-16 / README / INDEX / state / §8.8 全部同步且幂等。

### 5.2 已定案的「不可达 / 已知边界」（**不是待办**，不得当作未完成工作去刷）

| 编号 | 结论 |
|---|---|
| D-88 | 菌丝区 A0/A1/A3/A4 **结构不可辨识**（`H_assim` rank=0/nullity=4）+ **数据资产级不可验证** ⇒ GOAL §2 第 7 行改标「软测量内部量」 |
| D-89 | PH1 的 28 批验证集**从未留出** ⇒ 禁止引用「验证集」作泛化性论据 |
| D-54 / D-57 | 运行期连续调控**封死**（响应为阶跃）；PH4 验收项转已知边界 |
| D-53 / D-64 | S / P / PAA 通道结构性不可辨识 |
| D-71 / D-70 / D-72 | Raman/PAA-PLS 无独立信息，不作为交付组件 |
| D-78 | coverage 构造性恒真 ⇒ 不可作达标证据 |
| D-83 / R166 V2 | 全幅解析 σ 注入 3/6 批崩塌（max|Δ|=96.0588 pp）、样本外 seed=11 仍崩（99.8524 pp）⇒ **NO_GO**，保持 opt-in |
| oq#36 | MATLAB `rng('shuffle')` 种子未记录 ⇒ 逐位复现**原理上不可达**（命题证伪） |

### 5.3 未完成（真正的缺口，**恰好就是本次要做的平台工作**）

| # | 事项 | 状态 |
|---|---|---|
| **D-65** | 平台看板对外口径仍是恒真数且版本滞后 | 🔴 **治理条件未闭合**；`cap` 只能是 conditional；用户 2026-11-05 显式暂缓「平台可视化部分先不做」 |
| **R164-12** | 看板「观察-控制工作台」页（PH5 剩余）+ D-65 平台口径统一 | ⏸ **暂缓，不得自启**（`roadmap §8.8 (c)`） |
| **T1-3 / T1-4** | `data.js` 换数据源到 `runs/r156_acceptance.json`、catastrophic KPI 改用 `classify_health` 五通道；T8 五视图逐屏复验 | ⏸ 同批暂缓（`state.yaml:48,83`） |
| **L3 四项** | V1 转默认 / V2 转默认 / V3 写回黄金参数 / 双基线并行制度 | ⏸ **需用户二次确认**（`roadmap §8.8 (a)`），本轮未执行 |
| **R166-5…9** | 根因治理五项（DO2/pH 偏差补偿、MATLAB 种子数据资产、菌丝形态数据立项、HTTP 参数映射、V2 崩塌通道消融） | 增强项，**可并行，不属基础缺口** |

### 5.4 判定

> **「基础性的工作是否已经全部完成」取决于口径：**
>
> - **按数值 / 算法 / 验收 / 服务化口径：是，已 100% 完成并冻结**，且有 54/54 终检与逐位零回归锚作证，不需要再做任何引擎开发。
> - **按「最终交付平台」口径：否，差且只差一项 —— 平台侧的口径同步与能力装载（D-65 / R164-12 / T1-3 / T1-4）**，而这一项是被用户自己显式暂缓的，不是技术没做出来。
> - **L3（把 opt-in 候选切成默认生产口径）是另一类决策**，不属于基础工作，且会摧毁 L0 冻结锚，须用户二次确认。

**因此「如果完成则更新并优化最终仿真计算平台系统」的条件在数值层已满足；而这次升级动作本身，正是补齐 §5.3 那唯一一项缺口。**

---

## 6. 平台现状实测（供升级决策）

| 项 | 实测 | 问题 |
|---|---|---|
| `data.js` 契约快照 | **`v1.69`**，生成于 **2026-11-04 08:48** | 契约已 **v1.96** ⇒ **落后 27 个版本**（D-65 登记时才落后 18 版） |
| `.cache/bNN.json` | 2026-11-03 16:40，86 个 | 缓存早于 R163–R166 全部证据 |
| KPI | `rmse 2.34` / `within 86/86` / `catastrophic 0` / `healthy_pairs 417/1290 (32.3%)` | catastrophic 口径未按 T1-3 改为 `classify_health` 五通道 |
| `serve.py` API | `GET /api/health`、`POST /api/simulate` | **只有 A 档开环回放**；B/C/D 档 12 个求解器/算子、14 个 MCP 工具**平台侧不可达** |
| 设计文档规划 API | `POST /v1/solvers/{id}/simulate` 与 `/estimate`（`docs/01…md:80`） | **未实现** |
| 前端「已装载」标签 | `platform/app.js:785` → `o.exists ? "已装载" : "缺失"`，而 `o.exists = os.path.exists(...)`（`export_data.py:207`） | **是文件存在性，不是运行时装载**，属于口径恒真的一种表现（与 D-65 同型） |
| 工作台页 | 五视图 | **无「观察-控制工作台」**（PH5 剩余） |
| 端口 | 8770（serve.py）/ 8931（MCP HTTP）/ 8501（Streamlit） | 8770 被用户要求**不重启**；三者互不连线 |

---

## 7. 升级依据（严格映射到研发目标 / 方案条款）

| 来源 | 条款 | 对本次升级的要求 |
|---|---|---|
| `GOAL.md:65` §7 | 「SimuForge 看板（panel 记录，M5 交付）」 | 看板是**交付物**，不是选配 |
| `docs/01…md:78-84` | 四层架构：应用层（SimuForge 三视图）/ 引擎层（批处理 API `POST /v1/solvers/{id}/simulate` 与 `/estimate`）/ 求解层 / 数据层 | 平台须能调用求解层，不能只回放 A 档 |
| `docs/01…md:127,164` | M5 = 引擎 + 看板；三视图纳入本项目交付 | M5 闸门未闭的根因 |
| `deepening_plan.md:107-121` | 推荐架构四层（机理主干 / 随机效应 / 残差发现 / **在线观测器 + 控制**） | 平台应暴露 PH3/PH4 能力，而非只挂机理主干 |
| `deepening_plan.md:163-165` | **PH5**：MCP 新工具 + 「看板：新增观察-控制工作台页」 | 工具已 14/14，页仍缺 |
| `deepening_plan.md:71` | 「求解器即服务（Agent 调用）与结果持久化」 | 服务化装载点 = MCP；需与平台连线 |
| `roadmap_next.md:498-508` §8.8 (d) | 不改 `INNOVATION_Z_*` / `COMBINED` / `golden_params.py` / 零回归基准 / `data/` / GOAL §5 红线；不重启 8770；长期硬基线不变 | **升级必须只增不改**：opt-in 新路径，默认路径逐位零回归 |
| `m5_review_signoff.md` R-6 | M5 转 PASS 的剩余条件 = T8 逐屏复验 + 看板口径同步 | 完成后可解除 `cap` 的 conditional |

**升级设计约束（由上述条款推出）**：

1. **L0 冻结基线一字不动**：所有新能力走新增 API / opt-in 参数，`simulate_open_loop` 默认路径保持逐位一致；
2. **口径先行**：`data.js` 数据源与 KPI 口径按 T1-3 同步到 v1.96，修掉「已装载 = 文件存在」这一恒真标签；
3. **装载 = 运行时可达**：平台 API 必须真正 import 并调用求解器/算子模块，而不是列文件清单；
4. **不重启 8770**：新服务起独立端口或离线生成产物；
5. **L3 不夹带**：V1/V2/V3 候选保持 opt-in，不因平台升级自动转默认。

---

## 8. 待用户确认（本回溯不擅自推进）

1. 「将完成的算子/求解器/仿真引擎**装载到**」的**目标实体**（指令在此处被截断）：现有 `platform/` / 新建统一 API 服务层 / 仅刷新数据与口径 / 仅 MCP 服务层。
2. 是否**解除 2026-11-05 的平台可视化暂缓**（`state.yaml:48`、D-65、R164-12「不得自启」），以及是否允许**新起端口**（保持 8770 不重启）。
3. `roadmap §8.8 (a)` 的 **L3 四项切换决策**本轮是否一并处理（建议：否，保持 opt-in，不夹带边界变更）。

---

## 9. 复现

```
py tools/r166_final_check.py --json          # 54/54 PASS
py tools/r166_governance_update.py           # dry-run 幂等零写入
head -2 platform/data.js                     # contract v1.69 / generated 2026-11-04 08:48
head -2 ENGINE_CONTRACT.md                   # v1.96
grep -n "^def \|@mcp.tool" candidate/indpensim/v0.1/mcp_server.py
```
