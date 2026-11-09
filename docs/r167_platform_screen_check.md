# 仿真平台逐屏复验 T8 —— R167（六视图，v1.97）

> 复验时间：2026-11-06　|　引擎契约：**v1.97**　|　服务：`python platform/serve.py --port 8771`
> **8770 全程未监听**（用户 2026-11-05 要求「不重启 8770」，本轮另起 8771，验证完即停）
> 工具：`tools/r167_platform_gate.py`（内嵌 Playwright + 系统 Chrome headless，1440×940）
> 证据：`runs/r167_platform_gate.json` **PASS 25/25**

---

## 一、环境与接口

| 项 | 结果 |
|---|---|
| 服务可达 | ✅ `127.0.0.1:8771` LISTENING；8770 前后均 **未监听** |
| `GET /api/health` | ✅ `ok:true`、`n_batches:86`、`capabilities:14/14`、`operators_loaded:12/12`、`contract:v1.97`、`build:R167`、`port:8771` |
| `GET /api/ops` | ✅ 14 能力 + 12 算子全部 `loaded:true`，backend `mcp.server.fastmcp`，`l3_exposed:false` |
| `GET /api/evidence` | ✅ 契约 v1.97、终检 54/54、A/B 18/20 NO_GO、V2 `NO_GO`、L3 未执行 |
| `POST /api/simulate`（L0） | ✅ 批 8 产量误差 **−4.039%** 与 `final_validation_v2.json` 逐位一致；`mux=0.36` 覆盖真实生效 |
| `POST /api/invoke` | ✅ 4 个轻能力实跑成功（solver_info / evaluate_batch / element_balance_check / trajectory_check）；5 个 L3 候选参数逐个 400 拒绝 |
| 静态资源 | ✅ `index.html` / `app.js` / `style.css` / `data.js` 全部 200；无 4xx 资源请求 |

---

## 二、逐屏判定（六视图，含新增第 6 视图）

截图目录 `docs/screenshots/platform/r167_*.png`（1440×940，Chrome headless）

| # | 视图 | 判定 | 关键观察 | 截图 |
|---|---|---|---|---|
| 1 | 总览 `#overview` | ✅ | 4 张 KPI 卡：**RMSE 2.34% / 86·86 / catastrophic 4 已登记（0 新发，名单 37·50·51·91）/ 通道健康 417·1290**；副标题不再出现旧恒真的「0 catastrophic」；产量误差棒图 ±5% 红线、健康分布条、86 列热力矩阵全渲染 | `r167_01_overview.png` |
| 2 | 拓扑 `#topology` | ✅ | 种子罐→发酵罐→收获主链 + 6 辅回路 + 沿时剖面 + 回路负载；本轮修掉 SVG `height="auto"` 非法属性 | `r167_02_topology.png` |
| 3 | 批次 `#batch` | ✅ | **86** 批网格、8 通道轨迹、COMBINED 参数表、通道健康；批次徽标改显 `classify_health` | `r167_03_batch.png` |
| 4 | 通道 `#channels` | ✅ | **15** 行通道档案、误差构成散点、单通道逐批分布 | `r167_04_channels.png` |
| 5 | 算子 `#operators` | ✅ | **12/12 运行时装载 · 服务实时核验**；每卡显示 `module.attr(签名)` 与 `import + callable 通过`；`hier_fit`、`element_balance` 勘误可见 | `r167_05_operators.png` |
| 6 | **观察·控制 `#workbench`**（R167 新增） | ✅ | L0–L3 四层架构带；A/B/C/D 四档 **6/5/2/1 = 14** 能力按钮（6/6、5/5、2/2、1/1 已装载）；证据面板 v1.97 / 54·54 PASS / 18·20 NO_GO / 9·9 PASS / L3 保持 opt-in | `r167_06_workbench.png` |

**前端 → HTTP → 引擎端到端调用**：在工作台点选 `solver_info` → 「调用」 → 返回体含 `"ok": true` 与
`"version": "v0.1.0-c5"`，状态栏 `完成 · 0s · A 档`。✅

**浏览器卫生**：六视图 `pageerror` / `console error` / 4xx 资源请求 **均为 0**。

---

## 三、本轮复验发现并修复的缺陷（4 处）

| # | 缺陷 | 性质 | 修复 |
|---|---|---|---|
| 1 | 算子视图实时核验显示 **11/12** | 目录名 `conservation_metrics` 与运行时名 `element_balance` 未映射 ⇒ 实时状态漏配一个 | `export_data.py` 写 `runtime_name`，`app.js` 用 `runtime_name` 对齐 `/api/ops`；复验 **12/12** |
| 2 | `console: Error: <svg> attribute height: Expected length, "auto"` | 拓扑图 `svgEl("svg", {height:"auto"})` 是非法 SVG 长度（潜伏缺陷） | 改 `style:"height:auto"`，保留 `viewBox` 比例 |
| 3 | `console: Failed to load resource: 404` | 浏览器自动请求 `/favicon.ico` | `index.html` 加 `<link rel="icon" href="data:," />` |
| 4 | 总览副标题仍写 **「0 catastrophic」** | KPI 卡已改 `classify_health` 口径但静态文案未同步，仍传播 D-38 恒真数 | 改「catastrophic 4 已登记 / 0 新发（classify_health 五通道）」，并把该项纳入 G20 判据 |

> 缺陷 1 与 4 属 **D-65 同型的口径分叉**；2 与 3 属真实可用性/控制台噪声缺陷。
> 四项均由 T8 逐屏复验抓出并复验通过 —— 这正是 R134 把 T8 列为闸门的意义。

---

## 四、数据一致性交叉核对

| 项 | 平台 | 权威来源 | 一致 |
|---|---|---|---|
| 契约版本 | `v1.97` | `ENGINE_CONTRACT.md` 头部 + 版本表 | ✅ |
| 产量 RMSE / ±5% | 2.34% / 86·86 | `runs/final_validation_v2.json`、`runs/r166_zero_regression.json` | ✅ |
| catastrophic | **4 已登记 / 0 新发** `[37,50,51,91]` | `runs/r156_acceptance.json` `summary.n_health` / `hard.G2` | ✅ |
| degraded | 5 `[40,43,49,54,92]` | 同上 | ✅ |
| 终检 / A/B / MCP 冒烟 | 54·54 PASS / 18·20 NO_GO / 9·9 PASS | `runs/r166_{final_check,ab_gate,mcp_smoke}.json` | ✅ |
| 能力 / 算子 | 14 / 12 运行时装载 | `/api/ops` 进程内 `import + callable` | ✅ |
| 轨迹 / 批次 | 86 / 86 | `platform/.cache/bNN.json` + `data.js` | ✅ |

---

## 五、结论

T1-4（T8 逐屏复验）**完成**：由 v1.61 / 2026-11-03 的五视图复验，
升级为 **v1.97 / 2026-11-06 的六视图复验**，且新增 DOM 断言、浏览器卫生检查、
前端能力调用端到端三项机器可验判据。
与 T1-3（口径同步）、R164-12（观察-控制工作台）合并后，
**D-65 治理条件闭合 ⇒ `gates.M5` 转 PASS、`cap` 由 `L2 prototype (conditional)` 解除条件**
（签核单 R-17 重评审，见 `docs/m5_review_signoff.md`）。

复现：
```
py platform/export_data.py
py tools/r167_platform_gate.py            # 起 8771、截图、自动停止
```
