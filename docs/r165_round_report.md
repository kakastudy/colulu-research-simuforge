# R165 轮次报告 —— 波次 1+2 收口（R164-1 … R164-7）

> 生成：2026-11-06　｜　承接：R164（`deepening_plan` 专项回溯）　｜　路线图：`docs/roadmap_next.md` §8.6 / §8.7
> 用户指令：「按最优方案执行，最优结果，多轮寻优无法解决可接受降级。现在开始，完成一个阶段输出下一阶段任务清单」。

---

## 一、本轮做什么

R164 从 `docs/deepening_plan.md`、`GOAL.md` 与 PH1–PH5 出发完成第四次全量回溯，把波次 1+2 共 7 项排进 §8.6.4。本阶段（R165）执行**且仅执行**这 7 项：

| 波次 | 编号 | 任务 | 状态 |
|---|---|---|---|
| 2 | **R164-5** | CO2 卡死型故障只读检测器（多轮寻优） | ✅ 完成 |
| 2 | **R164-1** | PH5 服务化补齐 `discover_residual` + `observe_online` | ✅ 完成 |
| 2 | **R164-7** | 菌丝区 A0/A1/A3/A4 可辨识性证明 | ✅ 完成 |
| 1 | **R164-2/3/4/6** | PH1 验收口径 / `deepening_plan` 勘误 / PH4 已知边界 / 台账销号 | ✅ 完成 |

**贯穿全轮的硬约束**：全部为**只读探针 / 治理文本**，引擎数值核心逐字未改；零回归 86 批 `max|Δ| = 0.00e+00`、RMSE 2.345%、86/86；`cap` 口径不变（L2 prototype conditional）。

---

## 二、R164-5　CO2 卡死型故障只读检测器（多轮寻优）

### 2.1 问题

R163 在 C 段物理可信故障注入中发现 `co2_sensor_stuck` **漏检 4/5**：EnKF 创新判据对「实测 CO2 长时间精确冻结」不敏感，而这类传感器卡死在真实装置上是常见故障。

### 2.2 做法：绕过创新，直接检验通道时序

只读检测器，不写引擎、不进默认路径。两个特征：`exact_run`（最长精确相等游程）与`near_flat_run`（滑窗标准差 < `std_frac × global_std` 的最长连续段）；判据为**双阈值 OR**：`exact_run ≥ exact_th` 或 `near_flat_run ≥ near_th`。

### 2.3 三轮寻优（阈值全部数据驱动）

| 轮次 | 内容 | 结果 |
|---|---|---|
| 1 | `exact` 阈值网格扫描 | 给出候选可行域 |
| 2 | `std_frac` 分离度扫描 | 选中 0.010（分离度 **6.48x**，为网格 argmax） |
| 3 | 双阈值组合 + 显式安全裕度准则 + LOO | `exact 6.0 h / near_flat 32.0 h`，可行组合 84 个；裕度要求 4.2 h / 28.2 h（对照批最长 1.4 h / 18.8 h，安全系数 3.0 / 1.5） |

### 2.4 结果（判据 11/11 PASS）

- **零信息对照**：健康批 20 例触发 0/20；**正向**：CO2 卡死 5 例全检出 5/5；**其它故障**：15 例误触发 0/15（反向判别力成立）。
- **LOO 5 折**：5/5 全通过（样本外定阈值，非事后拟合）。
- **只读性**：40 例输入 DataFrame 零改写，违规 0。
- **组合增益**：EnKF OR 检测器四格 TP 10→14 / FN 5→1 / TN、FP 不退化（漏检 5→1，多检出 4 例，健康批不被误伤）。
- **灵敏度下界**：最小可检出冻结时长 exact 8.0 h / 带抖动 24.0 h。

> 产物：`tools/r165_co2_stuck_detector.py` → `runs/r165_co2_stuck_detector.json`；日志 `runs/_r165_co2.log`。

---

## 三、R164-1　PH5 服务化补齐两个 MCP 工具

在 `candidate/indpensim/v0.1/mcp_server.py` 新增两个**只读、纯新增**工具，工具数 **12 → 14**：

| 工具 | 包装的能力 | 返回体标记 |
|---|---|---|
| `discover_residual` | PH2 结构残差发现（`residual_discovery`） | `identifiable` / `degraded` / `degradation_reasons` / `mycelium_compartments` / `criteria` / `structures`；无 θ 批**显式降级不猜测** |
| `observe_online` | 在线 EnKF 同化（`observe.enkf_observe`，`out_path=None`） | `degraded` / `reconstruction_valid` / `identifiable` / `degradation_reasons` / `n_records`；硬失败标 `reconstruction_valid=False`，成员积分失败或 `n_ens<8` 为软告警 |

既有 12 个工具函数体**逐字未变**，`solver_info()` 返回体与冻结快照**逐位一致**；`ENGINE_CONTRACT.md` §2 已登记三节。因 `fastmcp` 未安装（D-85），验证采用 **stub 注入**，并在探针中用短窗口（120 行 / 约 24 h / `n_ens=4`）真实 DataFrame 做 smoke，不 stub 掉 EnKF 本体。

> 产物：`tools/r165_mcp_tools_probe.py` → `runs/r165_mcp_tools_probe.json`（**12/12 PASS**，37.5 s）。

---

## 四、R164-7　菌丝区组成可辨识性证明（含机制勘误）

### 4.1 结论

从 `observe.py` 真实常量导出观测算子：`H_assim` 对 A 组 **rank=0 / nullity=4**，`H_report` 叠加 `X_sum` / `X_sd` 后 **rank=1 / nullity=3**。增加同类数据只重复行、**不改变列空间** ⇒ A0/A1/A3/A4 **结构不可辨识**（观测设计层）。

### 4.2 两处口径勘误（先核对源码，再下结论）

- 原任务判据写「黏度只约束**总生物量**」—— **错**。引擎 `model.py` 的 `dy[9]` 生成项只依赖 **A0 单室** `a_0_pos**(1/3)`，不是 `A0+A1+A3+A4` 或 `total_X`。
- `vis ≈ 1.77·X + 12.4` 是 R129r 的**实测经验关系**，与 `model.py` 的 A0 立方根结构不等价。
- 动力学层对分室比例**敏感**：`r_e1/r_d1 ∝ A0`、`r_b0/r_p ∝ A1`、`r_d4 ∝ A3`、`K_diff ∝ A_t1`。

⇒ 正确落点是**观测算子 H 的结构秩亏**，不是黏度约束形式。零空间扰动实测动力学响应为 0（浮点地板内），非保和正例响应在 δ=1e-6…1e-1 上严格单调；钳位审计（guards / a0_pos / nonfinite）全 0 ⇒ 秩亏**非数值保护伪影**。

### 4.3 分层：不可辨识 ≠ 不可验证

| 层 | 结论 | 判别式 |
|---|---|---|
| 观测设计 | **结构不可辨识** | H 列空间不足；加同类数据无解 |
| 数据资产 | **不可验证** | 缺 A 组真值；换含形态测量的数据可解（R164-V5(b)） |

⇒ **D-88 升级为双重结论**。主文档 `docs/r165_mycelium_identifiability.md`；产物 `runs/r165_mycelium_identifiability.json`（**11/11 PASS**，87.39 s）。

---

## 五、R164-2/3/4/6　治理文本四项

`tools/r165_governance_text.py` 以 **46 项**精确替换 / 插入落地，**幂等**（dry-run 零泄漏、三次复跑 `changed=0 / skip=46 / error=0`）、数字从 `runs/r163_zero_regression.json` 读取、CRLF / LF 按目标文件原样保留：

| 编号 | 内容 |
|---|---|
| R164-2 | PH1 验收口径改写：清理「mux 8.6% 偏差 = 验证通过」与 σ̂ 已估计口径，统一改引 **MAP 散布上界 + 不含群体先验**；显式登记「28 批验证集从未留出」（D-89） |
| R164-3 | `docs/deepening_plan.md` 4 处陈述漂移勘误（头部历史快照、PH2 投票口径 88 有效批 / 12 站 / 负向 5、R129t2 σ̂ 段 R142 证伪批注、COMBINED 替代方案批注）；`docs/ph2_acceptance_report.md` §五回填 RMSE **2.345%** / **86/86** / 0 catastrophic |
| R164-4 | PH4 验收项「对照固定配方提升量化」转**已知边界**，路线图 / 台账 / 签核单三处一致（D-54），签核单新增 B-18 |
| R164-6 | D-67 / D-68 / D-66 / D-81 / D-76 状态滞后清理（四处标题 + 总表四行销号），新增**纪律 32**（不可辨识 / 不可验证分层证明、机制表述先核对源码）；v4 回溯稿 X_offline 与黏度口径同步勘误 |

---

## 六、判据纪律、多轮寻优与诚实降级

承 **D-78**：任何指标做**零信息对照**；判据**双向**（正向触发 + 反向判别力）；禁止恒真 / 恒假；阈值必须数据驱动扫描 / LOO / 灵敏度 / 显式裕度准则确定，**不得手写或事后放宽**。

- 本轮 CO2 检测器经历三轮寻优，最终阈值由 `_choose(...)` 的显式安全裕度准则给出，LOO 用同一准则复选，而非挑一个「看起来能过」的数。
- 终检脚本初稿曾出现 3 条恒真 / 弱判据（A5 / A7 / A9），已全部改为读取 `runs/r165_co2_stuck_detector.json` 中 D1/D2/D3/D5/D7/D8 的**具体数值**实判据；C5 / C7 改用「三个产物名」与 `yaml.safe_load` 独立条目，避免纯子串误报（纪律 31）。
- **诚实降级**：`fastmcp` 未安装（D-85）⇒ MCP 服务本机不可启动，采用 stub 注入做逻辑层验证，并明确登记为环境缺口而非宣称端到端通过；`observe_online` 用短窗口 smoke 而非全时长跑。
- R164-7 的**机制表述偏差**（黏度只约束总生物量）被实测推翻后，按纪律 32 先核对源码再写入治理层勘误，没有把错误前提包装成结论。

---

## 七、治理层同步

`tools/r165_governance_update.py`（幂等、dry-run 零泄漏、数字全部从 `runs/` 读取）一次性同步：

| 对象 | 变更 |
|---|---|
| `ENGINE_CONTRACT.md` | v1.94 → **v1.95**（工具 12→14、CO2 双阈值、H 秩、46 项治理文本、引擎零改动、未越界声明）|
| `docs/r157_debt_ledger.md` | 新增 **D-90**（R165 轮次）|
| `docs/m5_review_signoff.md` | 新增 **R-15**（R165 收口）|
| `README.md` | §4 标题 → v1.95、阅读顺序 → R165 报告、新增 `### R165` 段 |
| `tools/INDEX.md` | 新增 R165 六工具表 + 两份文档引用 |
| `state.yaml` | `open_questions` 新增独立 **R165** 条 |
| `.workbuddy/memory/2026-11-06.md` | R165 收口记忆 |
| `docs/roadmap_next.md` | 新增 §8.7 下一阶段任务清单 |
| 本报告 | `docs/r165_round_report.md` |

---

## 八、闸门：零回归 / pytest / 终检

| 闸门 | 命令 | 结果 |
|---|---|---|
| 全量零回归 | `py tools/r134_zero_regression.py --tol 0 --out runs/r165_zero_regression.json` | **86 批逐位一致**：`max|Δ| = 0.00e+00`、RMSE 2.345%、86/86 within ±5%、0 批超差 |
| 测试 | `py -m pytest -q` | `33 passed in 456.19s (0:07:36)` |
| 终检 | `py tools/r165_final_check.py --json` | A 探针判据 / B 治理文本+幂等 / C 治理层同步 / D 闸门与文档卫生；产物 `runs/r165_final_check.json` |
| 引擎零改动 | 4 个源码文件 SHA256 与 R164-7 证明时比对 | 逐位一致（终检 A21 / D7）|

---

## 九、本轮未做（明确边界）

- 不改 EnKF 阈值 / 白名单；不写回 `alpha_kla`；不回填扰动随机成分；不安装 `fastmcp`；不动看板口径；不改 `GOAL.md` §5 边界。
- 不写 `data/`；不新增观测通道；不把检测器 / 证明逻辑写入任何**默认引擎路径**；不重启 8770 端口服务。
- `R164-V1…V5` 属 **GOAL §5 边界变更 / 环境 / 目标口径变更**，`R164-8…R164-11` 为裁决后执行项，`R164-12` 受用户暂缓约束 —— 本阶段**一律不越界**。

---

## 十、下一阶段任务清单与证据清单

**下一阶段**清单见 `docs/roadmap_next.md` §8.7：(a) 五项待用户裁决（R164-V1…V5）；(b) 裁决后执行 R164-8…R164-11；(c) 暂缓的 R164-12；(d) GOAL §5 边界声明与判据纪律。

| 证据 | 路径 |
|---|---|
| CO2 检测器 | `runs/r165_co2_stuck_detector.json` / `runs/_r165_co2.log` |
| MCP 工具探针 | `runs/r165_mcp_tools_probe.json` / `runs/_r165_mcp.log` |
| 菌丝可辨识性 | `runs/r165_mycelium_identifiability.json` / `runs/_r165_mycelium.log` / `docs/r165_mycelium_identifiability.md` |
| 治理文本四项 | `runs/r165_governance_text.json` |
| 治理层同步 | `runs/r165_governance_update.json` |
| 零回归 | `runs/r165_zero_regression.json` / `runs/_r165_zero_regression.log` |
| pytest | `runs/_r165_pytest.log` |
| 终检 | `runs/r165_final_check.json` |
| 本报告 | `docs/r165_round_report.md` |

---

## 补记　闸门最终结果（收口时回填）

- **全量零回归**：`runs/r165_zero_regression.json` —— 86 批 `max|Δ| = 0.00e+00`、RMSE 2.345%、86/86 within ±5%、0 批超差（`EXIT=0`，1273.5 s）。日志因与压缩前遗留后台任务共用同一路径出现字节交错，已按**实际产物**规范化重写（数字全部取自该 JSON）。
- **测试**：`py -m pytest -q` → `33 passed in 456.19s (0:07:36)`（`runs/_r165_pytest.log`）。
- **终检**：`tools/r165_final_check.py --json` → **70/70 ALL PASS**（`runs/r165_final_check.json`），A 探针判据 / B 治理文本+幂等 / C 治理层同步 / D 闸门与文档卫生四组全通过。
- **元数据统一（透明记录）**：终检 A22 要求三份探针产物 `round == "R165"`，初版 MCP / 菌丝产物写为 `"R165 / R164-1"` / `"R165 / R164-7"`。按 D-78 **未放宽判据**，改为修正两个生成脚本的元数据输出（`round="R165"`、任务号移入独立 `task` 字段）并**重跑三个探针**（均确定性：CO2 `rng(11)`、MCP `seed=7`、菌丝无随机），复跑仍为 11/11、12/12、11/11 PASS，数值证据零改动。
- **本阶段状态**：波次 1+2 共 7 项全部完成，引擎数值零改动、`cap` 口径不变；波次 3/4 未执行，清单见 `docs/roadmap_next.md` §8.7。
