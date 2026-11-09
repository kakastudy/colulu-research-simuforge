# R167 轮次报告 —— 仿真计算平台升级：算子 / 求解器 / 仿真引擎装载

> 日期：2026-11-06　|　状态：**阶段收口 · 闸门 PASS 25/25 · 终检 PASS 20/20**
> 授权：用户 2026-11-06 三项裁决（装载目标 / 暂缓与端口 / L3 范围）
> 主交付：本报告、`docs/r167_platform_screen_check.md`、`docs/goal_backtrace_check_v5.md`
> 证据：`runs/r167_platform_gate.json`、`runs/r167_final_check.json`

---

## 一、回溯：整体研发成果与基础工作完备性

先做第五次全量回溯（`docs/goal_backtrace_check_v5.md`），首次把 `platform/` 代码实体、
MCP 装载链路、`cap` 治理条件纳入同一张完备性判定表。

| 维度 | 判定 |
|---|---|
| 里程碑 | S0 / M0–M4 **PASS**；M5 原为 `in_progress`；`cap` 原为 **L2 prototype (conditional)**，唯一阻塞 D-65 |
| GOAL §4 五条标准 | 标准 1 产量 / 3 守恒 / 4 故障 **PASS**；标准 2 轨迹 / 5 I2+I3 **有界 PARTIAL**（已定案边界，非待办） |
| `deepening_plan` PH1–PH5 | PH2 达成（≤3.5%，实测 2.345%）；PH3 能力完成、判据层 opt-in；PH4 转已知边界（D-57 阶跃响应）；**PH5 工具侧 14/14 完成、平台页缺**；PH1 验收口径因 D-89 改写 |
| 闸门（承接 R166） | 终检 **54/54 PASS**、86 批逐位零回归 `max|Δ| = 0.00e+00` / RMSE **2.345%** / **86/86**、pytest 33 passed、MCP 冒烟 9/9、A/B **18/20 NO_GO** |
| 代码资产 | 引擎层 6 件 / 求解器层 8 件 / 算子层 12 件 / 服务层 14 工具，**全部存在且可运行** |

**完备性判定**：

- **数值 / 算法 / 验收 / 服务化口径：100% 完成并冻结**，有 54/54 终检与逐位零回归锚作证，不需要再做引擎开发；
- **最终交付平台口径：否，差且只差一项** —— D-65 平台口径 + T1-3 + T1-4 + R164-12，且这一项是用户 2026-11-05 自己显式暂缓的；
- **L3（把 opt-in 候选切成默认生产口径）是另一类决策**，会摧毁 L0 冻结锚，须用户二次确认。

> 关键判断：**这次「更新优化最终平台 + 装载」的动作本身，正是补齐唯一一项基础缺口**。

---

## 二、用户授权与边界

| 裁决 | 选择 | 落地 |
|---|---|---|
| 装载目标 | **现有 `platform/` 平台** | 14 个 MCP 工具对应能力映射进 `serve.py` HTTP API + 前端第 6 视图 + `data.js` 口径同步 |
| 暂缓与端口 | **解除 2026-11-05 暂缓，另起新端口** | 用 **8771**；**8770 前后均未监听**，验证完即停 |
| L3 范围 | **不处理，保持 opt-in** | V1/V2/V3 候选不进注册表；5 类候选参数由 `/api/invoke` 行为测试逐个 400 拒绝 |

---

## 三、平台升级实现

### 3.1 能力装载（新增 `platform/ops_registry.py`）

- **不复制实现**：进程内 `import mcp_server`，直接复用其 **14 个工具函数本体**（A/B/C/D 全档），
  平台能力与 Agent 服务逐字同源，杜绝「平台数字 vs 服务数字」分叉。
- **运行时装载核验**：14 能力 + 12 算子全部要求 `import + callable` 为真，
  取代旧 `app.js:785` 的 `os.path.exists` 恒真标签（D-65 同型）。
- **四道闸门**：工具白名单 / `FORBIDDEN_KEYS`（5 个 L3 候选参数）/ `opt_in` 显式开关 / `confirm` 重调用确认；
  所有拒绝都返回显式原因，不静默降级。
- **勘误两处**：旧算子目录 `hier_est` **不是可调用函数**（真名 `hier_fit`）；
  `conservation_metrics` 是模块名而非函数名（真名 `element_balance`）。两者此前被「文件存在 ⇒ 已装载」掩盖。

### 3.2 服务层（`platform/serve.py`，additive）

| 接口 | 用途 |
|---|---|
| `GET /api/health` | 旧键一字未改，增 `contract` / `capabilities` / `all_loaded` / `l3_state` / `build` / `port` |
| `GET /api/ops` | 运行时装载核验全表 |
| `GET /api/evidence` | 只读 `runs/` 产物的证据面板（不重算指标） |
| `POST /api/invoke` | 调用已装载能力 |
| `POST /api/simulate` | **L0 冻结基线，函数体逐字未改** |

### 3.3 口径收口（T1-3）

| 项 | 修前 | 修后 |
|---|---|---|
| 契约版本 | `data.js` **v1.69**；`contract_version()` 只扫表体 ⇒ 停在 **v1.94**（R166 只升头部到 v1.96） | 头部 + 表体取最大 ⇒ **v1.97**，服务与导出器共用同一真源 |
| catastrophic KPI | **0**，来自 D-38 已判 86/86 恒真的 `crash_level` | `classify_health` 五通道：**normal 77 / degraded 5 / catastrophic 4（0 新发，已登记 [37,50,51,91]）** |
| 算子「已装载」 | `os.path.exists(xxx.py)` | 运行时 `import + callable`，**12/12** |
| 批次健康 | `crash_level` | `classify_health`；试算面板的 legacy `classify_crash` 显式标注为恒真旧判据 |

### 3.4 PH5 剩余 / R164-12：第 6 视图「观察·控制工作台」

L0–L3 架构带 + A/B/C/D 四档 **14 能力**分组调用（6/5/2/1）+ 证据面板
（54/54 终检、18/20 NO_GO、V2 No-Go、L3 未执行、cap）+ 显式 opt-in / confirm 勾选。

---

## 四、闸门与 T8 逐屏复验

`tools/r167_platform_gate.py` → `runs/r167_platform_gate.json`：**PASS 25/25**（8771，服务自动停止）。

| 组 | 关键判据 |
|---|---|
| 源码边界 | G1 引擎 4 文件 sha256 与 R166 冻结值**逐位一致**；G2 R166 终检仍 54/54 |
| 数据与口径 | G3 契约 v1.97；G4/G5 catastrophic 4 且来源 classify_health；G6/G7 12/12 运行时装载与两处勘误 |
| 运行时装载 | G10/G11 14 能力 + 12 算子实时 `callable`；G12 `l3_exposed=false` |
| L0 回归 | G13 批 8 产量误差 **−4.039%** 与冻结基线逐位一致；G14 `mux=0.36` 真实生效 |
| 能力实跑 | G15 4 个轻能力经 `/api/invoke` 成功（非仅列目录）；G16 五个 L3 候选参数逐个 400 拒绝；G17 三道闸门 |
| T8 | G20 六视图 + 总览无旧恒真文案；G21 工作台 14 按钮 / 4 架构 / L3 与 v1.97；G22 12/12 运行时装载；G23 **前端 → HTTP → 引擎**调用端到端成功；G24 无 pageerror / console error / 4xx |
| 端口 | G25 **8770 前后均未监听** |

T8 产出 **6 张** `docs/screenshots/platform/r167_*.png`，并抓出且修复 4 处真实缺陷
（实时核验 11/12 漏配、SVG `height="auto"` 非法、favicon 404、总览副标题残留「0 catastrophic」）。
详见 `docs/r167_platform_screen_check.md`。

---

## 五、治理层同步

| 文件 | 变更 |
|---|---|
| `ENGINE_CONTRACT.md` | **v1.96 → v1.97**，R167 状态行 + 版本表行 |
| `docs/r157_debt_ledger.md` | **D-65 关闭**（治理条件已闭合）+ 新增 **D-92** |
| `docs/m5_review_signoff.md` | **R-17 签核单重评审**：按 R-6 的剩余条件逐项复核 |
| `state.yaml` | **`gates.M5`: in_progress → PASS**；**`cap`: L2 prototype (conditional) → L2 prototype**；`status_ladder` 同步 |
| `README.md` / `tools/INDEX.md` / `docs/roadmap_next.md` §8.9 / 工作记忆 | R167 登记 |
| `docs/goal_backtrace_check_v5.md` | 第五次全量回溯（本轮决策依据） |

> **`cap` 条件解除是授权的治理后果，不是能力等级再升一级**：R-6 明定「M5 平台逐屏复验（T8）
> 与看板口径同步 —— 完成后 M5 可转 PASS、cap 条件解除」，本轮三项条件实测全部满足。
> 若用户不认可该推断，可单独回退这一条，不影响平台功能与引擎基线。

治理脚本 `tools/r167_governance_update.py` **分两批 apply 共 18 项 / 三次 dry-run 复跑
`changed=0 / skip=19 / error=0`**，模板变量全部展开、无占位符残留，CRLF/LF 风格原样保留。
第二批修的是终检 F5 抓出的**幂等 marker 前缀子串 bug**：`status_ladder` / `cap.level`
只写 `"L2 prototype"` 会被 `"L2 prototype (conditional)"` 命中而误判已落地
（与 R166 的 `v1.96（R166` marker 同型）⇒ 改为整行含换行匹配，判据语义未放宽。

---

## 六、未越界声明

- 不切换任何候选为默认生产路径；V1/V2/V3 保持 opt-in、默认关闭；
- 不改 `INNOVATION_Z_*` 默认值 / `COMBINED` / `golden_params.py` / `alpha_kla` /
  零回归基准 `runs/final_validation_v2.json` / `data/` / `GOAL.md` §5 红线；
- **引擎源码零改动**（4 文件 sha256 与 R166 冻结值逐位一致）；
- **不重启 8770**（本轮用 8771，验证完即停）；
- 长期硬基线不变：86 批 `max|Δ| = 0.00e+00`、RMSE 2.345%、86/86 within ±5%；
- A/B 闸门仍为 **18/20 NO_GO**，V2 多轮寻优仍判定 `NO_GO`，不粉饰、不改写为 PASS。

---

## 七、下一阶段（沿用 `docs/roadmap_next.md` §8.8，未变）

- **(a) L3 四项切换决策**：R166-1 V1 转默认 / R166-2 V2 转默认 / R166-3 V3 写回 /
  R166-4 双基线并行制度 —— **仍需用户二次确认 + 独立基线冻结，本轮未执行**；
- **(b) 根因治理 `R166-5…9`**：可并行，R166-9 承接全幅 σ 崩塌的逐通道消融；
- **(c) `R164-12` 已由本轮关闭**，不再是暂缓项。

---

## 八、复现与引用

```
py platform/export_data.py                  # 重生成 data.js（v1.97 / 86 批 / 14 能力）
py tools/r167_platform_gate.py              # 起 8771 + T8 六视图截图 + 自动停止
py tools/r167_governance_update.py --apply  # 幂等治理同步
py tools/r167_final_check.py --json         # 终检
py platform/serve.py --port 8771            # 手动启动工作台（可选）
```

| 类别 | 路径 |
|---|---|
| 回溯 | `docs/goal_backtrace_check_v5.md` |
| 复验 | `docs/r167_platform_screen_check.md`、`docs/screenshots/platform/r167_*.png` |
| 证据 | `runs/r167_platform_gate.json`、`runs/r167_final_check.json`、`runs/r167_governance_update.json` |
| 工具 | `tools/r167_platform_gate.py`、`tools/r167_governance_update.py`、`tools/r167_final_check.py`、`platform/ops_registry.py` |
| 代码 | `platform/serve.py`、`platform/export_data.py`、`platform/index.html`、`platform/app.js`、`platform/style.css` |
| 本报告 | `docs/r167_round_report.md` |
