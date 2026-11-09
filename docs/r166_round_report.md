
# R166 轮次报告 —— 五项委托裁决 · 冻结基线 + opt-in 候选 + 证据闸门

> 日期：2026-11-06　|　状态：**阶段收口**
> 授权：用户「a 的五项根据你的建议来，核心目标是最优解决方案和最优目标」
> 主交付：本报告、`docs/r166_verdict.md`；证据 `runs/r166_final_check.json`

## 一、结论

R164-V1…V5 **五项全部裁决并落地**，但**否决了 §8.7 原方案「直接改默认引擎 + 重算基线」**。
理由是它会摧毁项目唯一可复现的逐位回归锚，且三条候选路径各自存在已被实证的机制障碍：
V2 的 MATLAB 逐位复现被 R162 `oq#36` 证伪；V1 全局阈值 10 会让 `CO2outgas`
（跨批 max|z| 最大 7.60）判据恒假；V3 写回会改 81 批且落在 33.8–73.9 pp 的产量崖上。

最优解是**四层架构**：L0 冻结基线（默认路径逐字不变）/ L1 opt-in 候选通道 /
L2 证据闸门（D-78 合规）/ L3 切换决策（**下一阶段，本轮不执行**）。
既实质推进五项，又保住硬基线，还把「是否切换生产口径」留给用户二次确认。

其中 **V2 是本轮唯一未达可交付标准的候选**：全幅解析 σ 注入触发 3/6 批灾难性产量崩塌
（max|Δ| = 96.0588 pp）；多轮寻优在 seed=7 下虽找到 5 个可行 scale，
但换种子即失效 ⇒ 按用户授权**诚实降级为 `NO_GO`**，保持 opt-in、不切默认。
V4 的「更优实现」与 V2 的「诚实降级」共同构成本轮最优结果：
**不把未经验证的候选推上生产口径，也不粉饰失败**。

## 二、五项裁决

| 项 | 裁决 | 落地 |
|---|---|---|
| V1 / D-87 | **条件批准，否决全局 5→10** | `solver_chain._enkf_health_r166` opt-in 逐通道阈值 + 持续占比；阈值由扫描给出 |
| V2 / D-83 | **条件批准；执行结果 No-Go** | `simulate.py` `dist_noise_sigma/seed` 8 路 AR(1)，默认关闭；不宣称 MATLAB 复现；全幅 σ 崩塌 + 样本外种子失效 ⇒ 不切默认（详见 §四） |
| V3 / D-84 | **条件批准，不写回黄金参数** | 评测层 `k_dual` 查表，排除崖批 |
| V4 / D-85 | **批准并关闭** | 官方 SDK FastMCP 兼容层 + 锁 `mcp==1.12.0`；零新增依赖 |
| V5 / D-88 | **选 (a) 升级版** | `GOAL.md` §2 第 7 行改标软测量内部量；**§5 红线一字未改** |

## 三、V4 多轮寻优与诚实降级

| 轮 | 尝试 | 结果 |
|---|---|---|
| 1 | `fastmcp==2.14.7` 常规安装 dry-run | 连带升级 30+ 包（pydantic 2.14.3 / anyio 4.16 / mcp 1.30）⇒ 否决 |
| 2 | 同版本 `--no-deps` 安装 | `import` 失败：`RichHandler.__init__()` 不认 `tracebacks_max_frames`（本机 rich 13.7.1）；`pip check` 报 9 缺包 + 4 项版本不满足 ⇒ 已卸载回滚 |
| 3 | `fastmcp==2.0.0`（依赖最轻的 2.x）dry-run | 仍升级 11 包（rich 15 / fastapi 0.162 / starlette 1.7 / anyio 4.16）⇒ 否决 |
| 4 | **官方 SDK 内置 `mcp.server.fastmcp.FastMCP`** | 已装 `mcp==1.12.0` 提供同构 `tool/run/list_tools` ⇒ **采用**；`_OfficialSDKFastMCP` 抹平 `@tool` 无括号与 `run(transport=http, port=...)` 两处差异 |

这不是降级，而是更优实现：D-85 的目标「MCP 服务本机可启动、端到端可验证」已达成，
且依赖锁零污染。**14 个工具函数体与改前逐字一致**；冒烟 S1–S9 **9/9 PASS**。

## 四、A/B 证据闸门（D-78 合规）

`tools/r166_ab_gate.py` → `runs/r166_ab_gate.json`：**18/20 NO_GO**。

- **V1**：采集 25 例完整 `health` 序列（含零信息对照 5 例 + 物理可信故障注入），
  使任意候选判据可完全离线重放。阈值 = 零信息对照 `max|z|` × 网格倍数 +
  持续占比；筛出「对照 0 触发」的可行集，取**最大可行裕度**下最灵敏组合，
  按批 LOO 复核；禁止恒真/恒假；真实重放与离线扫描一致性单独判据。
  选出通道 `CO2outgas,DO2,pH`、裕度 `1.05`；候选四格 `{"TP": 10, "FN": 5, "TN": 4, "FP": 1}` vs 冻结 `{"TP": 10, "FN": 5, "TN": 4, "FP": 1}`。
- **V2**：8 路 σ 基准取 `runs/r163_dist_variance.json` 解析值（τ=40 h 已对齐）；
  固定种子两次注入逐位一致；全幅注入的崩塌、多轮寻优与最终判定见下节与
  `runs/r166_v2_optim.json`。最终 A/B 判据 V2-3 / V2-4：**V2-3 FAIL / V2-4 FAIL（全幅 σ 已按 D-78 判 No-Go，不切默认）**。
- **V3**：`k_dual` 取 `runs/r163_kla_dual_constraint.json`，仅可辨识 / 非崖批；
  逐批 A/B 差值全量列出，如实报告改善与劣化批数。

#### V2 多轮寻优（D-83；只改注入设计，不改 V2-3 / V2-4 判据阈值）

首轮把 `runs/r163_dist_variance.json` 的 8 路 `analytic_sigma` **全幅**注入
（scale = 1.0），在 3/6 批触发灾难性产量崩塌，最大 |Δ| = 96.0588 pp ⇒
`runs/r166_ab_gate.json` 的 V2-3 / V2-4 首轮 FAIL。这是**可复现的真实物理结果**，
不是脚本缺陷，故按用户「多轮寻优，无法解决可接受降级」授权执行以下轮次：

| 轮 | 动作 | 结果 |
|---|---|---|
| 1 | σ = 0 零信息对照 | 与冻结路径逐位一致（V2O-1） |
| 2 | scale = 1.0 全幅复现 | 3 批崩塌，max|Δ| = 96.0588 pp（V2O-2） |
| 3 | scale 网格 [0.02, 0.05, 0.1, 0.2, 0.35, 0.6, 1.0] × 6 批 | 逐批 Δ 全量记录在 `runs/r166_v2_optim.json` |
| 4 | 显式目标：rms(Δ) 距 R163 实测 3.0879 pp 最近（阈值 20 / 30 pp 原样不动） | 5 个可行 scale（V2O-3…V2O-6） |
| 5 | 按批 LOO 重选 + 额外种子样本外 + 同种子复跑 | 见 V2O-7 / V2O-8 / V2O-9 |

**寻优判定**：`NO_GO`；网格内可行 scale 共 5 个，seed=7 下按显式目标选出 `0.35`（**样本外失效，未采用**）；寻优判据 8/10 PASS。

**轮 5 样本外结果**：seed=11 → max|Δ|=99.8524 pp / 崩塌 2 批；seed=23 → max|Δ|=2.1284 pp / 崩塌 0 批。

**诚实降级（用户授权「多轮寻优无法解决可接受降级」）**：虽然网格内存在 5 个
在 seed=7 下满足冻结判据的 scale（最优 0.35），但**换种子即失效** ——
崩塌不是 σ 幅值的单调函数，而是**双稳态批对扰动实现路径的敏感依赖**。
因此不能把某个「恰好不崩」的 scale 当作可交付设计：那等于用单一种子过拟合，
正是 D-78 禁止的恒真/事后放宽。V2 判定 **No-Go**：保持 opt-in、默认关闭、
**不切默认生产路径**；全幅 σ 与多种子崩塌实值作为债务证据登记（转 §8.8 R166-9 根因治理）。
V2-3 / V2-4 阈值 20 / 30 pp **一字未改**，`runs/r166_ab_gate.json` 保留原始 FAIL，
不删除失败判据、不改写为 PASS。

## 五、闸门

| 项 | 结果 |
|---|---|
| 86 批逐位零回归 | `max|Δ| = 0.00e+00`、RMSE **2.345%**、**86/86** within ±5%、0 超差 |
| `py -m pytest -q` | `33 passed in 509.47s (0:08:29)`（引擎文件自 11:52 后未改动，本次证据有效） |
| MCP 冒烟 | 9/9 PASS |
| A/B 证据闸门 | **18/20 NO_GO**（仅 V2-3 / V2-4 FAIL，其余 18 项 PASS） |
| V2 多轮寻优 | `runs/r166_v2_optim.json` **NO_GO**，8/10 PASS；首轮原始证据留档 `runs/r166_ab_gate_first_pass.json` |
| R166 终检 | `runs/r166_final_check.json` **54/54 PASS** |
| 治理脚本幂等 | `tools/r166_governance_update.py` apply 11 项、dry-run 零泄漏、三次复跑 `changed=0 / skip=11 / error=0` |

## 六、治理层同步

契约 **v1.96**、台账 **D-91** + R166 总表、签核单 **R-16**、README / `tools/INDEX.md` /
`state.yaml` / `GOAL.md` §2 第 7 行 / `requirements.txt` / `.workbuddy/memory/2026-11-06.md` /
`docs/roadmap_next.md` **§8.8**。

## 七、未越界声明

不切换任何候选为默认生产路径；不改 `INNOVATION_Z_*` 默认值 / `COMBINED` /
`golden_params.py` / 零回归基准 / `data/` / `GOAL.md` §5 红线；不重启 8770 端口服务；
`R164-12` 暂缓不变；`cap` = L2 prototype conditional（唯一阻塞仍是 D-65）。

## 八、下一阶段

`docs/roadmap_next.md` **§8.8**：(a) L3 切换决策四项（需用户二次确认）、
(b) 根因治理五项 `R166-5…9`（可并行，其中 R166-9 承接 V2 崩塌机制）、
(c) `R164-12` 暂缓项、(d) 边界声明与执行顺序。

## 九、复现与引用

| 类别 | 路径 |
|---|---|
| 裁决 | `docs/r166_verdict.md`、`docs/roadmap_next.md` §8.7 / §8.8 |
| 证据 | `runs/r166_v1_health.json`、`runs/r166_ab_gate.json`、`runs/r166_ab_gate_first_pass.json`、`runs/r166_v2_optim.json`、`runs/r166_mcp_smoke.json`、`runs/r166_zero_regression.json`、`runs/r166_governance_update.json`、`runs/r166_final_check.json` |
| 工具 | `tools/r166_ab_gate.py`、`tools/r166_v2_optim.py`、`tools/r166_mcp_smoke.py`、`tools/r166_governance_update.py`、`tools/r166_final_check.py` |
| 本报告 | `docs/r166_round_report.md` |
