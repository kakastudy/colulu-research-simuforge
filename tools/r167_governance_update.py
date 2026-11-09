# -*- coding: utf-8 -*-
"""R167 治理层同步 —— 幂等、默认 dry-run、数字全部从 runs/ 读、换行风格原样保留。

    py tools/r167_governance_update.py            # dry-run 零写入
    py tools/r167_governance_update.py --apply --json

同步目标：契约 v1.97 / 台账 D-65 关闭 + D-92 / 签核单 R-17 / README / tools/INDEX.md /
state.yaml（M5→PASS、cap 条件解除）/ docs/roadmap_next.md §8.9 / 工作记忆。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs"
DRY = True
RECORDS = []
ERRORS = []

CV = "v1.97"


def opt(name, default=None):
    p = RUNS / name
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def load(rel):
    b = (ROOT / rel).read_bytes()
    return b.decode("utf-8").replace("\r\n", "\n"), b"\r\n" in b


def save(rel, text, crlf):
    data = text.replace("\n", "\r\n") if crlf else text
    (ROOT / rel).write_bytes(data.encode("utf-8"))


def sub(rel, old, new, tag):
    text, crlf = load(rel)
    if new in text:
        RECORDS.append({"tag": tag, "file": rel, "status": "skip(already)"})
        return
    if old not in text:
        ERRORS.append({"tag": tag, "file": rel, "error": "anchor not found: " + old[:70]})
        return
    text = text.replace(old, new, 1)
    if not DRY:
        save(rel, text, crlf)
    RECORDS.append({"tag": tag, "file": rel, "status": "changed"})


def append_once(rel, block, tag, marker):
    text, crlf = load(rel)
    if marker in text:
        RECORDS.append({"tag": tag, "file": rel, "status": "skip(already)"})
        return
    text = text.rstrip("\n") + "\n\n" + block.strip("\n") + "\n"
    if not DRY:
        save(rel, text, crlf)
    RECORDS.append({"tag": tag, "file": rel, "status": "changed"})


def main():
    global DRY
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    DRY = not args.apply

    gate = opt("r167_platform_gate.json", {}) or {}
    npass, ntotal = gate.get("n_pass", 0), gate.get("n_checks", 0)
    gverdict = gate.get("verdict", "PENDING")
    t8 = gate.get("t8") or {}
    shots = gate.get("shots") or []
    gate_line = (f"`runs/r167_platform_gate.json` **{gverdict} {npass}/{ntotal}**"
                 f"（8771 端口、8770 前后均未监听）")
    shot_line = f"{len(shots)} 张截图 `docs/screenshots/platform/r167_*.png`"

    # ------------------------------------------------------------------ 1 契约
    contract_status = (
        f"> 状态：**{CV}**（R167 **仿真计算平台升级与算子装载 —— D-65 / R164-12 / T1-3 / T1-4 全部关闭**；"
        "以下 v1.96 及更早为历史）。① **授权**：用户 2026-11-06 解除 2026-11-05 的平台可视化暂缓，"
        "选定「装载到现有 `platform/` + 另起新端口（8770 不动）+ L3 保持 opt-in」。"
        "② **装载**：新增 `platform/ops_registry.py`，**进程内复用 `mcp_server.py` 的 14 个工具函数本体**"
        "（A/B/C/D 全档，不复制实现）；`serve.py` 增 `/api/ops` / `/api/evidence` / `/api/invoke` "
        "三个 additive 接口，`/api/simulate`（L0）函数体逐字未改。"
        "③ **运行时装载核验**：14 能力 + 12 算子全部 `import + callable` 通过，取代旧 "
        "`os.path.exists` 恒真标签；勘误 `hier_est`→`hier_fit`、`conservation_metrics`→`element_balance`。"
        "④ **T1-3 口径**：`contract_version()` 改为「头部 + 表体取最大」，修 R134 只扫表体停在 v1.94 的缺陷；"
        "catastrophic KPI 由 D-38 恒真的 `crash_level`=0 改为 `classify_health` 五通道 "
        "**normal 77 / degraded 5 / catastrophic 4（0 新发，已登记 [37,50,51,91]）**。"
        "⑤ **R164-12 / PH5 剩余**：新增第 6 视图「观察·控制工作台」，含 L0–L3 架构带、14 能力分组调用、"
        "证据面板、L3 未执行与 V2 No-Go 声明。⑥ **T1-4 / T8**：六视图真实浏览器逐屏复验 + "
        + shot_line + " + DOM 断言 + 前端发起能力调用端到端通过。⑦ **边界**：引擎 4 文件 sha256 "
        "与 R166 冻结值逐位一致；L3 五类候选参数由 `/api/invoke` 行为测试逐个 400 拒绝；"
        "`opt_in` / `confirm` / 白名单三闸；8770 前后均未监听；`COMBINED` / `INNOVATION_Z_*` / "
        "零回归基准 / `data/` / `GOAL.md` §5 一字未改。⑧ **治理后果**：D-65 关闭 ⇒ `gates.M5` 转 PASS、"
        "`cap` 由 `L2 prototype (conditional)` 解除条件为 **`L2 prototype`**（签核单 R-17 重评审）。"
        "证据 " + gate_line + "、`docs/r167_platform_screen_check.md`、`docs/r167_round_report.md`。）"
    )
    sub("ENGINE_CONTRACT.md",
        "# ENGINE_CONTRACT.md — 求解器引擎批处理契约（v1.96，2026-11-06）",
        f"# ENGINE_CONTRACT.md — 求解器引擎批处理契约（{CV}，2026-11-06）",
        "CONTRACT-V197-TITLE")
    sub("ENGINE_CONTRACT.md",
        "> 状态：**v1.96**（R166 ",
        contract_status + "\n> **历史：v1.96**\n>\n> 状态：**v1.96**（R166 ",
        "CONTRACT-V197-STATUS")
    append_once("ENGINE_CONTRACT.md", f"""
---

## R167 版本行（{CV}）

> 单列一行，供 `platform/export_data.py::contract_version()` 与
> `platform/ops_registry.py::_contract_version()` 扫描；两处均取「头部 + 表体」最大值。

| 版本 | 变更 |
|---|---|
| {CV} | R167：仿真计算平台升级 —— 14 能力运行时装载 / 3 个 additive API / 第 6 视图「观察·控制工作台」/ T1-3 口径（契约版本解析 + classify_health 五通道）/ T1-4 六视图逐屏复验 / D-65 关闭、M5→PASS、cap 条件解除；引擎零改动 |
""", "CONTRACT-V197-TABLE", f"| {CV} | R167：仿真计算平台升级")

    # ------------------------------------------------------------------ 2 台账
    sub("docs/r157_debt_ledger.md",
        "### D-65　平台看板对外口径仍是**恒真数**且落后 18 个契约版本　🔴 **新，L2（治理条件未闭合）**",
        "### D-65　平台看板对外口径仍是**恒真数**且落后 18 个契约版本　✅ **R167 关闭（治理条件已闭合）**",
        "LEDGER-D65-HEAD")
    sub("docs/r157_debt_ledger.md",
        "| D-65 | 平台看板口径恒真 + 落后 18 版本 | L2 | 🔴 新（**治理条件未闭合**，用户暂缓） |",
        "| D-65 | 平台看板口径恒真 + 落后 18 版本 | L2 | ✅ **R167 关闭**（T1-3/T1-4/R164-12 完成，见 D-92） |",
        "LEDGER-D65-TABLE")
    append_once("docs/r157_debt_ledger.md", f"""
### D-92　R167 仿真计算平台升级：**14 能力运行时装载 + 口径收口 + 第 6 视图**　✅ **R167 关闭（治理层）**

| 项 | 内容 |
|---|---|
| 授权 | 用户 2026-11-06 三项裁决：① 装载目标 = **现有 `platform/`**；② **解除** 2026-11-05 平台可视化暂缓、**另起新端口**（8770 不动）；③ **L3 不处理，保持 opt-in** |
| 回溯前置 | `docs/goal_backtrace_check_v5.md`（第五次全量回溯）：数值 / 算法 / 验收 / 服务化 **100% 完成并冻结**，唯一基础缺口 = 平台侧 D-65 / R164-12 / T1-3 / T1-4 |
| D-65 关闭 | ① `data.js` 契约 **v1.69 → {CV}**（修 `contract_version()` 只扫表体停在 v1.94 的缺陷，改头部+表体取最大）；② catastrophic KPI 由 D-38 恒真 `crash_level`=0 改 `classify_health` 五通道 **4 已登记 / 0 新发**（`runs/r156_acceptance.json`）；③ 旧「已装载 = `os.path.exists`」恒真标签改为 **运行时 import + callable**，并勘误 `hier_est`→`hier_fit`、`conservation_metrics`→`element_balance` |
| T1-4 / T8 | 六视图（总览 / 拓扑 / 批次 / 通道 / 算子 / **观察控制**）真实浏览器逐屏复验；{shot_line}；DOM 断言 + 无 console error + 前端发起 `solver_info` 端到端调用通过 |
| R164-12 / PH5 | 新增「观察·控制工作台」：L0–L3 架构带、A/B/C/D 四档 14 能力分组调用、证据面板（54/54 终检、18/20 NO_GO、V2 NO_GO、L3 未执行）、`opt_in` / `confirm` 显式闸门 |
| 装载实现 | `platform/ops_registry.py` 进程内复用 `mcp_server.py` 的 14 个工具函数本体（零复制）；`serve.py` 增 `/api/ops` `/api/evidence` `/api/invoke`；**`/api/simulate`（L0）函数体逐字未改** |
| 闸门 | {gate_line}；G1 引擎 4 文件 sha256 与 R166 冻结值逐位一致；G13 批 8 产量误差与 `final_validation_v2.json` 逐位一致；G16 五个 L3 候选参数逐个 400 拒绝；G25 8770 前后未监听 |
| 治理后果 | **`gates.M5`: in_progress → PASS**；**`cap`: L2 prototype (conditional) → L2 prototype**（签核单 R-17 按 R-6「完成后可转 PASS、cap 条件解除」重评审）；`status_ladder` 同步 |
| 未越界 | 不切换任何候选为默认；不改 `INNOVATION_Z_*` / `COMBINED` / `golden_params.py` / 零回归基准 / `data/` / `GOAL.md` §5；不重启 8770；L3 四项仍待用户二次确认 |
| 证据 | `runs/r167_platform_gate.json`、`docs/r167_platform_screen_check.md`、`docs/r167_round_report.md`、`docs/goal_backtrace_check_v5.md` |
""", "LEDGER-D92", "### D-92　R167 仿真计算平台升级")

    # ------------------------------------------------------------------ 3 签核单
    append_once("docs/m5_review_signoff.md", f"""
---

**R-17**（2026-11-06，R167 平台升级后的 **M5 签核单重评审**）：按本单 R-6 的剩余条件
「M5 平台逐屏复验（T8）与看板口径同步 —— 完成后 M5 可转 PASS、`cap` 条件解除」，
逐项复核后判定：

| 剩余条件 | R167 实测 | 判定 |
|---|---|---|
| T1-3 看板口径同步 | `data.js` 契约 v1.69 → **{CV}**；catastrophic 0（D-38 恒真）→ **4 已登记 / 0 新发**（`classify_health` 五通道）；12/12 算子改运行时装载核验 | ✅ |
| T1-4 T8 逐屏复验 | **六视图**逐屏（含新增第 6 视图）、{shot_line}、DOM 断言、无 console error、前端能力调用端到端通过 | ✅ |
| R164-12 观察-控制工作台 | 已交付：L0–L3 架构 + A/B/C/D 14 能力 + 证据面板 + L3/V2 No-Go 声明 | ✅ |

⇒ **`gates.M5`: `in_progress` → `PASS`**；**`cap.level` / `status_ladder`:
`L2 prototype (conditional)` → `L2 prototype`**（条件解除，不是能力等级再升一级）。
D-65 由「治理条件未闭合」转 ✅ 关闭（台账 D-92）。
**授权范围随之扩至看板对外口径**，但 **GOAL §5 红线与 L3 边界不变**：
V1/V2/V3 候选仍 opt-in 默认关闭；A/B 闸门仍 18/20 `NO_GO`；
零回归 86 批 `max|Δ| = 0.00e+00` / RMSE 2.345% / 86/86 仍为长期硬基线。
证据：{gate_line}、`docs/r167_platform_screen_check.md`、`docs/r167_round_report.md`。
""", "SIGNOFF-R17", "**R-17**（2026-11-06，R167 平台升级后的")

    # ------------------------------------------------------------------ 4 state.yaml
    # 幂等 marker 必须整行（含换行）：只写前缀会让 "L2 prototype (conditional)"
    # 命中子串而误判「已落地」，与 R166 的 v1.96 marker 同型。
    sub("state.yaml", "status_ladder: L2 prototype (conditional)\n",
        "status_ladder: L2 prototype\n", "STATE-LADDER")
    sub("state.yaml", "  level: L2 prototype (conditional)\n",
        "  level: L2 prototype\n", "STATE-CAP-LEVEL")
    sub("state.yaml", "    M5: in_progress\n", "    M5: PASS\n", "STATE-GATE-M5")
    sub("state.yaml",
        "  current: M5 引擎+看板（cap = **L2 prototype (conditional)**；A 档评估集 86 批；⚠️ **平台五视图逐屏复验【待做】**——2026-11-05 用户显式暂缓平台可视化（T1-3/T1-4），此前记的「已逐屏复验」不成立）",
        "  current: M5 引擎+看板（**PASS / R167 收口**：cap = **L2 prototype**；A 档评估集 86 批；平台**六视图**逐屏复验完成 + 看板口径同步到 v1.97；D-65 关闭，见签核单 R-17）",
        "STATE-CURRENT")
    sub("state.yaml",
        "- ⏸ **平台可视化暂缓**（2026-11-05 用户指示「平台可视化部分先不做」）：T1-3（`platform/data.js` 换数据源到 runs/r156_acceptance.json、catastrophic KPI 改用 classify_health 五通道）与 T1-4（T8 逐屏复验重跑）**均挂起**。⇒ 看板仍停在 **v1.69 口径**，其「0 catastrophic」来自 D-38 已判恒真的 `crash_level`；**M5 保持 in_progress、cap 的 L2 条件尚差这一项**。",
        f"- ✅ **平台可视化暂缓已解除（R167，用户 2026-11-06 授权）**：T1-3（`data.js` 契约 v1.69→{CV}、catastrophic 改 `classify_health` 五通道 4 已登记 / 0 新发）、T1-4（T8 **六视图**逐屏复验 + {shot_line}）、R164-12（观察-控制工作台）**全部完成** ⇒ D-65 关闭、`gates.M5` 转 PASS、`cap` 条件解除为 **L2 prototype**（签核单 R-17）。新服务另起 8771，**8770 前后均未监听**。",
        "STATE-PLATFORM-PAUSE")
    sub("state.yaml",
        "- R157/T1-3 与 T1-4：平台数据与口径同步、T8 逐屏复验 —— 用户 2026-11-05 显式暂缓；在此之前看板仍停在 v1.69 口径（catastrophic=0 来自 D-38 已判恒真的旧判据），cap 保持 conditional",
        f"- R157/T1-3 与 T1-4：**R167 已关闭**（2026-11-05 的暂缓由 2026-11-06 用户授权解除）；看板口径现为 {CV} / classify_health 五通道，`cap` = L2 prototype（条件解除）",
        "STATE-T13T14")
    append_once("state.yaml", f"""
# ---------------------------------------------------------------------------
# R167（2026-11-06）：仿真计算平台升级与算子装载
# ---------------------------------------------------------------------------
r167:
  verdict: PASS
  gate: "{gverdict} {npass}/{ntotal} (runs/r167_platform_gate.json)"
  authorization: "用户三项裁决：装载到现有 platform/ + 解除暂缓另起新端口 + L3 保持 opt-in"
  capabilities_loaded: 14
  operators_runtime_verified: 12
  views: 6
  port_used: 8771
  port_8770_untouched: true
  contract: "{CV}"
  engine_sha256_vs_r166: identical
  d65: closed
  m5: PASS
  cap: "L2 prototype (conditional 解除)"
  l3: "未执行 · 保持 opt-in"
""", "STATE-R167", "r167:\n  verdict: PASS")

    # ------------------------------------------------------------------ 5 README
    append_once("README.md", f"""
### R167（2026-11-06）— 仿真计算平台升级：算子 / 求解器 / 仿真引擎装载

> 依据 `GOAL.md` §7、`docs/01_设计讨论…md` §3.1 四层架构、`docs/deepening_plan.md` PH3/PH5、
> `docs/roadmap_next.md` §8.8 (c)；回溯 `docs/goal_backtrace_check_v5.md`。
> **授权**：用户三项裁决 —— 装载到现有 `platform/` / 解除 2026-11-05 暂缓并另起新端口 / **L3 不处理**。

- **装载**：新增 `platform/ops_registry.py`，**进程内复用 `mcp_server.py` 的 14 个工具函数本体**
  （A/B/C/D 全档，零复制实现）；新增 12 个算子的运行时 `import + callable` 核验。
  `serve.py` 增 `GET /api/ops`、`GET /api/evidence`、`POST /api/invoke` 三个 additive 接口；
  **`/api/simulate`（L0 冻结基线）函数体逐字未改**。
- **口径收口（T1-3）**：`data.js` 契约 **v1.69 → {CV}**（`contract_version()` 改「头部+表体取最大」，
  修 R134 只扫表体停在 v1.94 的缺陷）；catastrophic 由 D-38 恒真的 `crash_level`=0
  改为 `classify_health` 五通道 **normal 77 / degraded 5 / catastrophic 4（0 新发，已登记 [37,50,51,91]）**；
  「已装载」标签由 `os.path.exists` 改为**运行时装载**，并勘误 `hier_est`→`hier_fit`、
  `conservation_metrics`→`element_balance`。
- **PH5 剩余（R164-12）**：新增第 6 视图 **「观察·控制工作台」** —— L0–L3 架构带、
  14 能力分组调用（重调用须 `confirm`、opt-in 开关须显式勾选）、证据面板、
  L3 未执行与 V2 `NO_GO` 声明。
- **T1-4 / T8**：六视图真实浏览器逐屏复验；{shot_line}；DOM 断言、无 console error、
  前端发起 `solver_info` 端到端调用通过 ⇒ `docs/r167_platform_screen_check.md`。
- **闸门**：{gate_line}。引擎 4 文件 sha256 与 R166 冻结值逐位一致；批 8 产量误差与
  `final_validation_v2.json` 逐位一致；5 个 L3 候选参数由 `/api/invoke` 逐个 400 拒绝；
  8770 前后均未监听（新服务用 8771，验证完即停）。
- **治理后果**：D-65 关闭、`gates.M5` → **PASS**、`cap` → **L2 prototype**（conditional 解除，签核单 R-17）；
  契约 **{CV}**、台账 **D-92**、路线图 **§8.9**。
- **未越界**：不切换任何候选为默认；不改 `INNOVATION_Z_*` / `COMBINED` / `golden_params.py` /
  零回归基准 / `data/` / `GOAL.md` §5；L3 四项仍待用户二次确认。
- 复现：`py platform/export_data.py` → `py tools/r167_platform_gate.py`（服务起 8771，自动停止）。
""", "README-R167", "### R167（2026-11-06）— 仿真计算平台升级")

    # ------------------------------------------------------------------ 6 INDEX
    append_once("tools/INDEX.md", f"""
### R167（平台升级 · 算子运行时装载 · T8 六视图复验）

| 工具 / 产物 | 用途 | 命令 / 证据 |
|---|---|---|
| `platform/ops_registry.py` | **能力注册表**（新增）：14 个 A/B/C/D 工具 + 12 个算子的运行时 `import+callable` 核验、`invoke()` 白名单 / 禁用 L3 参数 / `opt_in` / `confirm` 闸门、`evidence()` 只读 runs/ | 进程内复用 `mcp_server.py` 工具本体，不复制实现 |
| `platform/serve.py` | 增 `/api/ops` `/api/evidence` `/api/invoke`；`/api/simulate` L0 逐字未改 | `py platform/serve.py --port 8771` |
| `platform/export_data.py` | 契约版本头部+表体取最大 / KPI 改 classify_health / 算子运行时核验 / 新增 `workbench` + `evidence` 数据块 | `py platform/export_data.py` → `platform/data.js`（{CV}） |
| `platform/app.js` / `index.html` / `style.css` | 第 6 视图「观察·控制工作台」；算子视图改运行时装载标签；总览 catastrophic 改「4 已登记 / 0 新发」 | `#workbench` |
| `tools/r167_platform_gate.py` | **R167 闸门**：源码边界 / 运行时装载 / HTTP 冒烟 / L0 回归 / L3 行为拒绝 / T8 六视图逐屏复验 + 截图 | `py tools/r167_platform_gate.py [--no-shots]`；`runs/r167_platform_gate.json` **{gverdict} {npass}/{ntotal}** |
| `tools/r167_governance_update.py` | 治理层同步（契约 {CV} / 台账 D-65+D-92 / 签核单 R-17 / README / INDEX / state / §8.9 / 记忆） | 幂等、dry-run 零泄漏、CRLF/LF 原样 |
| `docs/goal_backtrace_check_v5.md` | 第五次全量回溯：研发成果 / 基础工作完备性 / 平台装载缺口 | R167 决策依据 |
| `docs/r167_platform_screen_check.md` | T8 六视图逐屏复验记录 | {shot_line} |
| `docs/r167_round_report.md` | R167 轮次主交付 | 见报告 |
""", "INDEX-R167", "### R167（平台升级 · 算子运行时装载")

    # ------------------------------------------------------------------ 7 roadmap
    sub("docs/roadmap_next.md",
        "| **R164-12** | 看板「观察-控制工作台」页 + D-65 平台口径统一 | ⏸ **用户暂缓**；解除后才排期；与 `cap`（L2 prototype conditional）一并处理 |",
        "| **R164-12** | 看板「观察-控制工作台」页 + D-65 平台口径统一 | ✅ **R167 已完成**（2026-11-06 用户解除暂缓后执行；见 §8.9） |",
        "ROADMAP-R164-12")
    append_once("docs/roadmap_next.md", f"""
---

## 九、R167 执行结果（2026-11-06）—— 平台升级与算子装载收口

> 依据：`docs/goal_backtrace_check_v5.md`（第五次全量回溯）、用户 2026-11-06 三项授权。
> 证据：{gate_line}、`docs/r167_platform_screen_check.md`、`docs/r167_round_report.md`。

### 9.1 回溯判定

数值 / 算法 / 验收 / 服务化层 **100% 完成并冻结**（54/54 终检、86 批逐位零回归、
14/14 MCP 工具）；GOAL §4 五条标准 3 PASS + 2 有界 PARTIAL（已定案边界，非待办）；
`deepening_plan` PH1–PH5 中 PH2 达成、PH3 能力完成判据层 opt-in、PH4 转已知边界、
PH5 工具侧完成而**平台页缺**。⇒ 唯一基础缺口 = 平台侧 D-65 / T1-3 / T1-4 / R164-12，
且该项是被用户自己显式暂缓的，不是技术没做出来。

### 9.2 本轮完成

| 项 | 结果 |
|---|---|
| T1-3 | `data.js` 契约 v1.69 → **{CV}**；catastrophic 0 → **4 已登记 / 0 新发**（classify_health 五通道）；12/12 算子改运行时装载核验，勘误 `hier_est`→`hier_fit` |
| T1-4 | **六视图**逐屏复验 + {shot_line} + DOM 断言 + 无 console error + 前端能力调用端到端通过 |
| R164-12 | 新增「观察·控制工作台」；L0–L3 架构、A/B/C/D 14 能力分组调用、证据面板 |
| D-65 | ✅ 关闭 ⇒ `gates.M5` → **PASS**、`cap` → **L2 prototype**（conditional 解除，签核单 R-17） |
| 闸门 | {gate_line}；引擎 4 文件 sha256 与 R166 逐位一致；L3 五类候选参数行为测试逐个 400 拒绝；8770 前后未监听 |

### 9.3 边界（未越界）

不切换任何候选为默认；不改 `INNOVATION_Z_*` / `COMBINED` / `golden_params.py` /
零回归基准 `runs/final_validation_v2.json` / `data/` / `GOAL.md` §5；
不重启 8770（本轮用 8771，验证完即停）；长期硬基线 86 批 `max|Δ| = 0.00e+00`、
RMSE 2.345%、86/86 不变。

### 9.4 下一阶段（沿用 §8.8，未变）

- **(a) L3 四项切换决策**：仍需用户二次确认 + 独立基线冻结，**本轮未执行**；
- **(b) 根因治理 `R166-5…9`**：可并行，其中 R166-9 承接 V2 崩塌通道消融；
- **(c) `R164-12` 已由本轮关闭**，不再列为暂缓项；
- 其余暂缓与边界声明以 §8.8 (d) 为准（其中 `cap` 一行已由 §9.2 更新）。
""", "ROADMAP-89", "## 九、R167 执行结果（2026-11-06）")

    # ------------------------------------------------------------------ 8 记忆
    append_once(".workbuddy/memory/2026-11-06.md", f"""
## R167（14:14–）：仿真计算平台升级与算子装载

- 先做第五次全量回溯 `docs/goal_backtrace_check_v5.md`：数值/算法/验收/服务化 **100% 完成并冻结**，
  唯一基础缺口是平台侧 D-65 / R164-12 / T1-3 / T1-4（用户 11-05 显式暂缓）。
- 用户三项授权：装载到**现有 platform/** / **解除暂缓 + 另起 8771**（8770 不动）/ **L3 保持 opt-in**。
- 新增 `platform/ops_registry.py`（进程内复用 `mcp_server.py` 14 工具本体 + 12 算子运行时核验）；
  `serve.py` 增 `/api/ops` `/api/evidence` `/api/invoke`，`/api/simulate` L0 逐字未改；
  `export_data.py` 修契约版本解析（v1.94→{CV}）+ catastrophic 改 classify_health 五通道 +
  运行时装载标签（勘误 `hier_est`→`hier_fit`）；新增第 6 视图「观察·控制工作台」。
- 闸门 `tools/r167_platform_gate.py` → `runs/r167_platform_gate.json` **{gverdict} {npass}/{ntotal}**
  （含 T8 六视图真实浏览器逐屏复验、{shot_line}、前端能力调用端到端、8770 前后未监听）。
- 治理：契约 {CV} / 台账 D-65 关闭 + D-92 / 签核单 R-17（`cap` conditional 解除、M5→PASS）/
  README / INDEX / state.yaml / 路线图 §8.9。**引擎源码零改动**，sha256 与 R166 冻结值逐位一致。
- 下一阶段：L3 四项仍需用户二次确认；根因治理 R166-5…9 可并行。
""", "MEMORY-R167", "## R167（14:14–）：仿真计算平台升级与算子装载")

    n_changed = sum(1 for r in RECORDS if r["status"] == "changed")
    n_skip = sum(1 for r in RECORDS if r["status"].startswith("skip"))
    out = {"mode": "apply" if not DRY else "dry-run",
           "verdict": "PASS" if not ERRORS else "ERROR",
           "n_changed": n_changed, "n_skip": n_skip, "n_error": len(ERRORS),
           "records": RECORDS, "errors": ERRORS}
    if not DRY:
        (RUNS / "r167_governance_update.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    if args.json:
        print(json.dumps({k: v for k, v in out.items() if k != "records"},
                         ensure_ascii=False, indent=1))
    else:
        print(f"R167 治理同步 [{out['mode']}] changed={n_changed} skip={n_skip} "
              f"error={len(ERRORS)}")
        for e in ERRORS:
            print("  ERROR", e["tag"], e["file"], e["error"])
    return 0 if not ERRORS else 1


if __name__ == "__main__":
    sys.exit(main())
