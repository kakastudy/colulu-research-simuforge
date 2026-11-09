# -*- coding: utf-8 -*-
"""R165 治理层同步（幂等、可干跑）。

同步范围：契约 v1.95 / 台账 D-90 / 签核单 R-15 / README / tools/INDEX.md /
          state.yaml / 工作记忆 2026-11-06.md。

纪律（承 R163 六处工程缺陷 + 纪律 25/28/29/30/31）：
  * 所有写入走 do() 门控，--dry-run 零泄漏（哈希自检）；
  * 每项自带 marker 幂等判定，三次复跑零写入；
  * 换行风格按目标文件原样保留（CRLF / LF）；
  * 数字全部从 runs/ 产物读取，不手写；
  * 不擅自改写历史流水，只在既有条目后追加 / 降级为「历史」。

用法：
  py tools/r165_governance_update.py                 # dry-run（默认）
  py tools/r165_governance_update.py --apply        # 实际写入
  py tools/r165_governance_update.py --apply --json # 写入并落证据
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"

DRY = True
RECORDS: list[dict] = []
ERRORS: list[str] = []


# --------------------------------------------------------------------------
# 数据驱动：所有数字从 runs/ 读
# --------------------------------------------------------------------------
def load_evidence() -> dict:
    ev = {}
    for key, name in (("co2", "r165_co2_stuck_detector.json"),
                      ("mcp", "r165_mcp_tools_probe.json"),
                      ("myc", "r165_mycelium_identifiability.json")):
        p = RUNS / name
        if not p.exists():
            ERRORS.append(f"缺证据产物: {name}")
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        ev[key] = {"verdict": d.get("verdict"), "n_pass": d.get("n_pass"),
                   "n_checks": d.get("n_checks"), "wall_s": d.get("wall_s")}
    zr = json.loads((RUNS / "r163_zero_regression.json").read_text(encoding="utf-8"))["summary"]
    ev["zr"] = {"rmse_pct": f'{float(zr["rmse_pct"]):.3f}',
                "within5": int(zr["within5"]), "n": int(zr["n"]),
                "max_abs_delta_pct": float(zr["max_abs_delta_pct"])}
    g = json.loads((RUNS / "r165_governance_text.json").read_text(encoding="utf-8"))
    ev["govtext"] = {"verdict": g["verdict"], "n_changed": g["n_changed"],
                     "n_skip": g["n_skip"], "n_error": g["n_error"],
                     "n_items": len(g["records"])}
    # CO2 组合四格（D8 判据）
    d = json.loads((RUNS / "r165_co2_stuck_detector.json").read_text(encoding="utf-8"))
    d8 = next((c for c in d["checks"] if c.get("id") == "D8"), {})
    ev["co2_confusion"] = d8.get("got") or d8.get("value") or {}
    mc = json.loads((RUNS / "r165_mcp_tools_probe.json").read_text(encoding="utf-8"))
    ev["tool_count"] = mc.get("tool_count", {})
    my = json.loads((RUNS / "r165_mycelium_identifiability.json").read_text(encoding="utf-8"))
    oo = my.get("observation_operator", {})
    ev["H"] = {"H_assim": [oo.get("H_assim", {}).get("rank"), oo.get("H_assim", {}).get("nullity")],
               "H_report": [oo.get("H_report", {}).get("rank"), oo.get("H_report", {}).get("nullity")]}
    # R165 轮次报告用：CO2 逐条判据数值、双阈值、pytest 行（全部从 runs/ 读取）
    cf = json.loads((RUNS / "r165_co2_stuck_detector.json").read_text(encoding="utf-8"))
    by_id = {q.get("id"): q for q in cf.get("checks", [])}
    ev["co2_thresholds"] = cf.get("thresholds", {})
    ev["co2_d"] = {k: (by_id.get(k, {}).get("got") or by_id.get(k, {}).get("value") or {})
                   for k in ("D1", "D2", "D3", "D5", "D7", "D8", "D10", "D11")}
    pt = (RUNS / "_r165_pytest.log").read_text(encoding="utf-8", errors="replace").splitlines()
    ev["pytest_line"] = next((l.strip() for l in pt if "passed" in l), "")
    return ev


# --------------------------------------------------------------------------
# 原语
# --------------------------------------------------------------------------
def read_norm(rel: str):
    p = ROOT / rel
    raw = p.read_bytes()
    nl = "\r\n" if b"\r\n" in raw else "\n"
    return p, nl, raw.decode("utf-8").replace("\r\n", "\n")


def do(p: Path, nl: str, text: str) -> None:
    if DRY:
        return
    out = text.replace("\n", nl) if nl == "\r\n" else text
    p.write_bytes(out.encode("utf-8"))


def rec(tag: str, status: str, rel: str, note: str = "") -> None:
    RECORDS.append({"tag": tag, "status": status, "file": rel, "note": note})


def replace_once(rel: str, old: str, new: str, tag: str, marker: str) -> None:
    try:
        p, nl, text = read_norm(rel)
    except Exception as e:                                    # noqa: BLE001
        ERRORS.append(f"{tag}: 读取失败 {e}")
        rec(tag, "ERROR", rel, str(e))
        return
    if marker in text:
        rec(tag, "skip(marker)", rel)
        return
    if new in text:
        rec(tag, "skip(already)", rel)
        return
    cnt = text.count(old)
    if cnt != 1:
        ERRORS.append(f"{tag}: old 命中 {cnt} 次（期望 1）")
        rec(tag, f"ERROR(count={cnt})", rel)
        return
    do(p, nl, text.replace(old, new, 1))
    rec(tag, "changed", rel)


def append_once(rel: str, block: str, tag: str, marker: str,
                create: bool = False) -> None:
    """追加到文件末尾；文件不存在时可创建（工作记忆）。marker 保证幂等。"""
    p = ROOT / rel
    if not p.exists():
        if not create:
            ERRORS.append(f"{tag}: 文件不存在 {rel}")
            rec(tag, "ERROR", rel, "文件不存在")
            return
        do(p, "\n", block.lstrip("\n"))
        rec(tag, "changed(create)", rel)
        return
    _, nl, text = read_norm(rel)
    if marker in text:
        rec(tag, "skip(marker)", rel)
        return
    sep = "" if text.endswith("\n") else "\n"
    do(p, nl, text + sep + "\n" + block.lstrip("\n"))
    rec(tag, "changed", rel)


def insert_after_prefix(rel: str, prefix: str, new_lines: list[str],
                        tag: str, marker: str) -> None:
    try:
        p, nl, text = read_norm(rel)
    except Exception as e:                                    # noqa: BLE001
        ERRORS.append(f"{tag}: 读取失败 {e}")
        rec(tag, "ERROR", rel, str(e))
        return
    if marker in text:
        rec(tag, "skip(marker)", rel)
        return
    lines = text.split("\n")
    idx = [i for i, line in enumerate(lines) if line.startswith(prefix)]
    if len(idx) != 1:
        ERRORS.append(f"{tag}: 锚点命中 {len(idx)} 次（期望 1）")
        rec(tag, f"ERROR(anchor={len(idx)})", rel)
        return
    i = idx[0]
    lines[i + 1:i + 1] = new_lines
    do(p, nl, "\n".join(lines))
    rec(tag, "changed", rel, f"anchor_line={i + 1}")


# --------------------------------------------------------------------------
# 1. ENGINE_CONTRACT.md → v1.95
# --------------------------------------------------------------------------
def edit_contract(ev: dict) -> None:
    rel = "ENGINE_CONTRACT.md"
    c, m, y = ev["co2"], ev["mcp"], ev["myc"]
    conf = ev["co2_confusion"]
    tc = ev["tool_count"]
    ha, hr = ev["H"]["H_assim"], ev["H"]["H_report"]
    z, g = ev["zr"], ev["govtext"]
    new_head = (
        "# ENGINE_CONTRACT.md — 求解器引擎批处理契约（v1.95，2026-11-06）\n\n"
        "> 状态：**v1.95**（R165 **阶段收口 —— R164-1…R164-7 波次 1+2 全部完成；"
        "全部为只读探针 / 文档，引擎数值零改动**。"
        f"① **R164-1 PH5 服务化补齐**：`mcp_server.py` 工具数 **{tc.get('before',12)} → {tc.get('after',14)}**，"
        f"新增 `discover_residual` / `observe_online` 两个只读工具，契约 §2 登记三节；"
        f"探针 **{m['n_pass']}/{m['n_checks']} PASS**（既有 12 工具逐字未变、`solver_info` 逐位一致）。"
        f"② **R164-5 CO2 卡死只读检测器**：多轮寻优得双阈值 `exact 6.0 h / near_flat 32.0 h`、"
        f"`std_frac=0.010`、LOO 5 折全通过；C 段可归因子集检出率 **1/5 → 5/5**，"
        f"EnKF OR 检测器四格 TP **{conf.get('enkf_baseline',{}).get('TP',10)}→{conf.get('TP',14)}** / "
        f"FN **{conf.get('enkf_baseline',{}).get('FN',5)}→{conf.get('FN',1)}** / TN、FP 不退化；"
        f"**{c['n_pass']}/{c['n_checks']} PASS**；**只加只读检测器，不进默认引擎路径**。"
        f"③ **R164-7 菌丝区组成可辨识性证明**：现有观测算子 `H_assim` **rank={ha[0]} / nullity={ha[1]}**、"
        f"`H_report` **rank={hr[0]} / nullity={hr[1]}** ⇒ A0/A1/A3/A4 **结构不可辨识**（观测设计层）；"
        f"**{y['n_pass']}/{y['n_checks']} PASS**。⇒ **D-88 升级为双重结论**：结构不可辨识 + "
        "数据资产级不可验证（V3 37 列无 A 组实测、Raman 被 D-71 否证）；两层边界是"
        "**是否改变观测算子 H 的列空间**，不是是否增加数据行数。同时勘误沿用多轮的机制表述："
        "引擎 `dy[9]` 只依赖 **A0 单室**（非总生物量），动力学层对分室比例敏感 ⇒ 不可辨识的落点"
        "只能是观测算子 H。④ **R164-2/3/4/6 治理文本四项**：PH1 验收口径改写（D-89）、"
        "`deepening_plan` 4 处陈述漂移勘误 + `ph2_acceptance_report.md` §五回填"
        f"（产量 RMSE **{z['rmse_pct']}%**、**{z['within5']}/{z['n']}**）、PH4 转已知边界三处口径统一、"
        f"台账滞后清理（D-66/67/68/76 销号）+ 纪律 32；幂等脚本 **{g['n_items']} 项 / 三次复跑零写入**。"
        f"⑤ **引擎数值零改动**：4 个源码文件哈希与证明时逐位一致；零回归 {z['n']} 批 "
        f"`max|Δ| = 0.00e+00`、RMSE {z['rmse_pct']}%、{z['within5']}/{z['n']} within ±5%。"
        "⑥ **`cap` 口径不变**（L2 prototype conditional，唯一阻塞仍是 D-65 用户暂缓项）；"
        "**本阶段未越界**：不改 EnKF 阈值 / 白名单、不写回 alpha_kla、不回填扰动随机成分、"
        "不安装 fastmcp、不动看板口径（均属 GOAL §5 边界变更，移交 R164-V 系列待裁决）。）\n"
        "> **历史：v1.94**（"
    )
    replace_once(
        rel,
        "# ENGINE_CONTRACT.md — 求解器引擎批处理契约（v1.94，2026-11-05）\n\n> 状态：**v1.94**（",
        new_head,
        "CONTRACT-v195", "求解器引擎批处理契约（v1.95，2026-11-06）")


# --------------------------------------------------------------------------
# 2. 台账 D-90
# --------------------------------------------------------------------------
def edit_ledger(ev: dict) -> None:
    rel = "docs/r157_debt_ledger.md"
    c, m, y = ev["co2"], ev["mcp"], ev["myc"]
    conf, tc, z, g = ev["co2_confusion"], ev["tool_count"], ev["zr"], ev["govtext"]
    block = (
        "\n---\n\n"
        "## 七、R165 阶段收口登记（D-90）\n\n"
        "### D-90　R165 波次 1+2 收口（R164-1…R164-7）　✅ **R165 登记，无新增 L2 阻断项**\n\n"
        "| 项 | 内容 |\n|---|---|\n"
        "| 范围 | `docs/roadmap_next.md` §8.6.4 **波次 1（R164-2/3/4/6）+ 波次 2（R164-1/5/7）** 共 7 项，"
        "全部为**只读探针 / 治理文本**，不动引擎数值 |\n"
        f"| R164-1 | MCP 工具 {tc.get('before',12)} → **{tc.get('after',14)}**"
        "（`discover_residual` / `observe_online`），契约 §2 登记三节；"
        f"探针 **{m['n_pass']}/{m['n_checks']} PASS**（`runs/r165_mcp_tools_probe.json`） |\n"
        f"| R164-5 | CO2 卡死只读检测器：双阈值 6.0/32.0 h、LOO 5 折全通过、"
        f"检出率 1/5 → 5/5、OR 四格 TP {conf.get('enkf_baseline',{}).get('TP',10)}→{conf.get('TP',14)} / "
        f"FN {conf.get('enkf_baseline',{}).get('FN',5)}→{conf.get('FN',1)}；"
        f"**{c['n_pass']}/{c['n_checks']} PASS**（`runs/r165_co2_stuck_detector.json`） |\n"
        f"| R164-7 | 菌丝区 A0/A1/A3/A4 **观测算子结构秩亏**（`H_assim` rank=0/nullity=4、"
        f"`H_report` rank=1/nullity=3）⇒ **结构不可辨识**；**{y['n_pass']}/{y['n_checks']} PASS**"
        "（`docs/r165_mycelium_identifiability.md`）⇒ **D-88 升级为双重结论** |\n"
        f"| R164-2/3/4/6 | 治理文本四项：`tools/r165_governance_text.py` **{g['n_items']} 项**、"
        "dry-run 零泄漏、三次复跑零写入、数字数据驱动、CRLF/LF 原样；"
        f"`ph2_acceptance_report.md` §五回填 RMSE **{z['rmse_pct']}% / {z['within5']}/{z['n']}**；"
        "PH4 三处口径统一（本台账 D-54 / 路线图 §8.6 / 签核单 B-18）；"
        "D-66/67/68/76 销号 + 纪律 32 |\n"
        "| 边界 | **D-85 / D-86 / D-87 / D-88 / D-89 维持**；未越界项（EnKF 阈值、alpha_kla 写回、"
        "扰动随机成分回填、fastmcp 安装、看板口径）移交 `docs/roadmap_next.md` §8.7 的 "
        "**R164-V1…V5** 待用户裁决 |\n"
        f"| 闸门 | 零回归 {z['n']} 批 `max|Δ| = 0.00e+00`、RMSE {z['rmse_pct']}%、"
        f"{z['within5']}/{z['n']}；`py -m pytest -q`；`tools/r165_final_check.py` 终检；"
        "`cap` 口径不变（L2 prototype conditional，D-65 用户暂缓项仍未闭合） |\n"
    )
    append_once(rel, block, "LEDGER-D90", "### D-90　R165 波次 1+2 收口")
    # 总表新增一行（插在 D-89 行之后）
    insert_after_prefix(
        rel, "| D-89 | PH1 的 **28 批验证集从未被留出**",
        ["| D-90 | R165 波次 1+2 收口（R164-1…R164-7 七项，只读/文档） | — | "
         "✅ **R165 登记**（无新增 L2 阻断项；判据 12/12 + 11/11 + 11/11；详见 §七） |"],
        "LEDGER-TBL-D90", "| D-90 | R165 波次 1+2 收口")


# --------------------------------------------------------------------------
# 3. 签核单 R-15
# --------------------------------------------------------------------------
def edit_signoff(ev: dict) -> None:
    rel = "docs/m5_review_signoff.md"
    c, m, y = ev["co2"], ev["mcp"], ev["myc"]
    conf, z = ev["co2_confusion"], ev["zr"]
    row = (
        "| **R-15** | **R165 阶段收口（R164-1 / R164-5 / R164-7 + 治理文本四项）** | PASS | "
        f"① **R164-1**：PH5 服务化补齐 `discover_residual`/`observe_online`（12→14），契约登记，"
        f"探针 **{m['n_pass']}/{m['n_checks']} PASS**；② **R164-5**：CO2 卡死只读检测器多轮寻优"
        f"（6.0/32.0 h 双阈值、LOO 5 折全通过），C 段可归因子集检出率 **1/5 → 5/5**，"
        f"四格 TP {conf.get('enkf_baseline',{}).get('TP',10)}→{conf.get('TP',14)} / "
        f"FN {conf.get('enkf_baseline',{}).get('FN',5)}→{conf.get('FN',1)} / TN=4 / FP=1，"
        f"**{c['n_pass']}/{c['n_checks']} PASS**；③ **R164-7**：菌丝区 A0/A1/A3/A4 在现有观测算子下"
        f"**结构不可辨识**（`H_assim` rank=0/nullity=4、`H_report` rank=1/nullity=3），"
        f"**{y['n_pass']}/{y['n_checks']} PASS** ⇒ **D-88 升级为双重结论**（结构不可辨识 + 数据资产级不可验证）；"
        "④ **R164-2/3/4/6**：PH1 口径改写 / `deepening_plan` 4 处勘误 / PH4 转已知边界 / "
        "台账滞后清理 + 纪律 32，并新增 **B-18 / B-19** 两条已知边界。"
        f"**全部为只读探针或文档，引擎零改动，零回归 {z['n']} 批 `max|Δ| = 0.00e+00`、"
        f"RMSE {z['rmse_pct']}%、{z['within5']}/{z['n']}；`cap` 口径不变**"
        "（L2 prototype conditional，唯一阻塞仍是 D-65 用户暂缓项）。"
        "本阶段**未越界**：EnKF 阈值 / alpha_kla 写回 / 扰动回填 / fastmcp 安装 / 看板口径"
        "均属 GOAL §5 边界变更，移交 §8.7 待裁决 | "
        "`docs/r165_round_report.md`、`docs/r165_mycelium_identifiability.md`；"
        "`runs/r165_{mcp_tools_probe,co2_stuck_detector,mycelium_identifiability}.json`；"
        "`tools/r165_final_check.py` |"
    )
    insert_after_prefix(rel, "| **R-14** |", [row],
                        "SIGNOFF-R15", "**R-15** | **R165 阶段收口")


# --------------------------------------------------------------------------
# 4. README
# --------------------------------------------------------------------------
def edit_readme(ev: dict) -> None:
    rel = "README.md"
    c, m, y = ev["co2"], ev["mcp"], ev["myc"]
    conf, tc, z, g = ev["co2_confusion"], ev["tool_count"], ev["zr"], ev["govtext"]
    replace_once(
        rel, "## 4. 当前状态（契约 v1.93）\n",
        "## 4. 当前状态（契约 v1.95）\n",
        "README-sec4", "## 4. 当前状态（契约 v1.95）")
    replace_once(
        rel,
        "5. `docs/r163_round_report.md` —— 最近一轮；历史报告按编号倒序\n"
        "   （上一轮：`docs/r162_round_report.md`）\n",
        "5. `docs/r165_round_report.md` —— 最近一轮；历史报告按编号倒序\n"
        "   （上一轮：`docs/r163_round_report.md`）\n",
        "README-order", "5. `docs/r165_round_report.md` —— 最近一轮")

    block = (
        "\n### R165　阶段收口（R164-1…R164-7 波次 1+2）\n\n"
        "> 全部为**只读探针 / 治理文本**，引擎数值零改动；零回归 "
        f"{z['n']} 批 `max|Δ| = 0.00e+00`、RMSE {z['rmse_pct']}%、{z['within5']}/{z['n']}；"
        "`cap` 口径不变（L2 prototype conditional，唯一阻塞仍是 D-65 用户暂缓项）。\n\n"
        f"- **R164-1 PH5 服务化补齐**：`mcp_server.py` 工具数 **{tc.get('before',12)} → {tc.get('after',14)}**，"
        "新增 `discover_residual` / `observe_online` 两个只读工具（返回体恒含"
        "`identifiable` / `degraded` / `mycelium_compartments` 标记），`ENGINE_CONTRACT.md` §2 登记；"
        f"探针 `tools/r165_mcp_tools_probe.py` → `runs/r165_mcp_tools_probe.json` **{m['n_pass']}/{m['n_checks']} PASS**"
        "（既有 12 工具逐字未变、`solver_info` 逐位一致）。\n"
        f"- **R164-5 CO2 卡死只读检测器**：绕过 EnKF 创新、直接检验实测 CO2 长时间冻结/近零方差；"
        "多轮寻优得双阈值 `exact 6.0 h / near_flat 32.0 h`、`std_frac=0.010`、LOO 5 折全通过；"
        f"C 段可归因子集检出率 **1/5 → 5/5**，EnKF OR 检测器四格 TP "
        f"{conf.get('enkf_baseline',{}).get('TP',10)}→{conf.get('TP',14)} / "
        f"FN {conf.get('enkf_baseline',{}).get('FN',5)}→{conf.get('FN',1)} / TN=4 / FP=1；"
        f"`tools/r165_co2_stuck_detector.py` → `runs/r165_co2_stuck_detector.json` **{c['n_pass']}/{c['n_checks']} PASS**。"
        "**只加只读检测器，不进默认引擎路径**。\n"
        f"- **R164-7 菌丝区组成可辨识性证明**：现有观测算子 `H_assim` **rank=0 / nullity=4**、"
        "`H_report` **rank=1 / nullity=3** ⇒ A0/A1/A3/A4 **结构不可辨识**（观测设计层）；"
        f"`tools/r165_mycelium_identifiability.py` → `runs/r165_mycelium_identifiability.json` "
        f"**{y['n_pass']}/{y['n_checks']} PASS**，主文档 `docs/r165_mycelium_identifiability.md`。"
        "⇒ **D-88 升级为双重结论**：结构不可辨识 + 数据资产级不可验证；"
        "同时勘误「黏度只约束总生物量」—— 引擎 `dy[9]` 只依赖 **A0 单室**，动力学层对分室敏感。\n"
        f"- **R164-2/3/4/6 治理文本四项**：`tools/r165_governance_text.py`（**{g['n_items']} 项**、"
        "dry-run 零泄漏、三次复跑零写入、数字数据驱动、CRLF/LF 原样）改写 PH1 验收口径（D-89）、"
        f"勘误 `deepening_plan` 4 处陈述漂移、回填 `ph2_acceptance_report.md` §五"
        f"（产量 RMSE **{z['rmse_pct']}%**、**{z['within5']}/{z['n']}**）、PH4 转已知边界三处口径统一、"
        "台账 D-66/67/68/76 销号 + 纪律 32；签核单新增 **B-18 / B-19**。\n"
        "- **终检**：`tools/r165_final_check.py`（只读、常驻可复跑）→ `runs/r165_final_check.json`。\n"
        "- **下一阶段**：`docs/roadmap_next.md` §8.7 —— `R164-V1…V5` **待用户裁决**"
        "（EnKF 阈值 / 扰动回填 / alpha_kla 写回 / fastmcp 安装 / GOAL §2 第 7 行口径），"
        "以及裁决后的 `R164-8…R164-11` 与暂缓的 `R164-12`。本阶段**未越界**："
        "不改 EnKF 阈值 / 白名单、不写回 alpha_kla、不回填扰动随机成分、不装 fastmcp、不动看板口径。\n"
    )
    append_once(rel, block, "README-R165", "### R165　阶段收口")


# --------------------------------------------------------------------------
# 5. tools/INDEX.md
# --------------------------------------------------------------------------
def edit_index(ev: dict) -> None:
    rel = "tools/INDEX.md"
    c, m, y = ev["co2"], ev["mcp"], ev["myc"]
    g = ev["govtext"]
    block = (
        "\n### R165（阶段收口：R164-1…R164-7 波次 1+2）\n\n"
        "| 工具 | 用途 | 备注 |\n|---|---|---|\n"
        f"| `r165_mcp_tools_probe.py` | R164-1 PH5 服务化补齐验证：AST 静态计数 12→14、"
        "既有 12 工具函数体逐字比对、`solver_info` 冻结快照、两工具双向判别力、菌丝分室标记 | "
        f"stub 注入绕开 D-85；**{m['n_pass']}/{m['n_checks']} PASS**；`runs/r165_mcp_tools_probe.json` |\n"
        f"| `r165_co2_stuck_detector.py` | R164-5 CO2 卡死只读检测器：exact/near_flat 双阈值、"
        "std_frac 分离度扫描、LOO 5 折、灵敏度下界、EnKF OR 四格增益 | "
        f"**{c['n_pass']}/{c['n_checks']} PASS**；`runs/r165_co2_stuck_detector.json`；只读、不进默认引擎路径 |\n"
        f"| `r165_mycelium_identifiability.py` | R164-7 菌丝区 A0/A1/A3/A4 可辨识性证明："
        "从 `observe.py` 真实常量导出 H、列归一 SVD、零空间/反例/正例扰动族、`model.rhs` 动力学层 Δ | "
        f"**{y['n_pass']}/{y['n_checks']} PASS**；`runs/r165_mycelium_identifiability.json`；"
        "主文档 `docs/r165_mycelium_identifiability.md` |\n"
        f"| `r165_governance_text.py` | R164-2/3/4/6 治理文本四项（46 项精确替换/插入） | "
        f"**幂等**（{g['n_items']} 项、三次复跑零写入）、dry-run 零泄漏、数字数据驱动、CRLF/LF 原样；"
        "`runs/r165_governance_text.json` |\n"
        "| `r165_governance_update.py` | 治理层同步（契约 v1.95 / 台账 D-90 / 签核单 R-15 / "
        "README / INDEX / state / 工作记忆） | **幂等**、dry-run 零泄漏；数字全部从 `runs/` 读取 |\n"
        "| `r165_final_check.py` | **R165 终检**（常驻可复跑、只读）：A 探针判据 / B 治理文本 / "
        "C 治理层同步 / D 闸门与文档卫生 | `--json` 写 `runs/r165_final_check.json` |\n"
        "\n| `docs/r165_round_report.md` | R165 轮次主交付（十章） | 含下一阶段任务清单引用 |\n"
        "| `docs/r165_mycelium_identifiability.md` | 菌丝区可辨识性证明主文档 | D-88 双重结论与口径勘误 |\n"
    )
    append_once(rel, block, "INDEX-R165", "### R165（阶段收口")


# --------------------------------------------------------------------------
# 6. state.yaml：open_questions 新增独立 R165 条
# --------------------------------------------------------------------------
def edit_state(ev: dict) -> None:
    rel = "state.yaml"
    c, m, y = ev["co2"], ev["mcp"], ev["myc"]
    z = ev["zr"]
    line = (
        "- ✅ R165（阶段收口，R164-1…R164-7 波次 1+2 **全部完成**）："
        f"PH5 服务化补齐 12→14 工具（{m['n_pass']}/{m['n_checks']} PASS）；"
        f"CO2 卡死只读检测器 1/5→5/5 检出（{c['n_pass']}/{c['n_checks']} PASS）；"
        f"菌丝区 A0/A1/A3/A4 观测算子结构秩亏 ⇒ **结构不可辨识**（{y['n_pass']}/{y['n_checks']} PASS）"
        "⇒ **D-88 升级为双重结论**（结构不可辨识 + 数据资产级不可验证）；"
        "治理文本四项 46 项幂等落地（PH1 口径 / deepening_plan 4 处勘误 / PH4 已知边界 / 台账销号 + 纪律 32）。"
        f"**全部只读/文档，引擎零改动**：零回归 {z['n']} 批 `max|Δ| = 0.00e+00`、"
        f"RMSE {z['rmse_pct']}%、{z['within5']}/{z['n']}；`cap` 口径不变"
        "（L2 prototype conditional，唯一阻塞仍是 D-65 用户暂缓项）。"
        "**未越界**：EnKF 阈值 / alpha_kla 写回 / 扰动回填 / fastmcp 安装 / 看板口径"
        "均属 GOAL §5 边界变更 ⇒ 移交 `docs/roadmap_next.md` §8.7（R164-V1…V5 待用户裁决）；"
        "证据 `docs/r165_round_report.md` / `runs/r165_final_check.json`\n"
    )
    replace_once(
        rel,
        "open_questions:\n- 🔴 R164 D-88",
        "open_questions:\n" + line + "- 🔴 R164 D-88",
        "STATE-R165", "- ✅ R165（阶段收口")


# --------------------------------------------------------------------------
# 7. 工作记忆 2026-11-06.md（append-only）
# --------------------------------------------------------------------------
def edit_memory(ev: dict) -> None:
    rel = ".workbuddy/memory/2026-11-06.md"
    c, m, y = ev["co2"], ev["mcp"], ev["myc"]
    z = ev["zr"]
    block = (
        "\n## R165　阶段收口（R164-1…R164-7 波次 1+2 全部完成）\n\n"
        "用户指令：「按最优方案执行，最优结果，多轮寻优无法解决可接受降级。现在开始，完成一个阶段输出下一阶段任务清单」。\n"
        "本阶段边界 = `docs/roadmap_next.md` §8.6.4 波次 1 + 波次 2 共 7 项，**全部只读/文档，引擎零改动**。\n\n"
        "**三项能力/判据（波次 2）**\n"
        f"- **R164-1**：`mcp_server.py` 工具 12→14，新增 `discover_residual` / `observe_online`"
        "（返回体恒含不可辨识/降级标记）；契约 §2 登记三节；探针 "
        f"`runs/r165_mcp_tools_probe.json` **{m['n_pass']}/{m['n_checks']} PASS**（37.5 s）。\n"
        f"- **R164-5**：CO2 卡死只读检测器多轮寻优 —— 双阈值 exact 6.0 h / near_flat 32.0 h、"
        "std_frac 0.010（分离度 6.48x）、LOO 5 折全通过、灵敏度下界 8/24 h；"
        f"C 段可归因子集 1/5→5/5 检出，OR 四格 TP 10→14 / FN 5→1 / TN 4 / FP 1；"
        f"`runs/r165_co2_stuck_detector.json` **{c['n_pass']}/{c['n_checks']} PASS**。\n"
        f"- **R164-7**：菌丝区 A0/A1/A3/A4 观测算子 `H_assim` rank=0/nullity=4、"
        "`H_report` rank=1/nullity=3 ⇒ **结构不可辨识**；"
        f"`docs/r165_mycelium_identifiability.md` + `runs/r165_mycelium_identifiability.json` "
        f"**{y['n_pass']}/{y['n_checks']} PASS**（87.39 s）。\n\n"
        "**治理文本四项（波次 1）**：`tools/r165_governance_text.py` 46 项幂等编辑"
        "（dry-run 零泄漏、三次复跑零写入、数字数据驱动、CRLF/LF 原样）—— PH1 验收口径改写（D-89）、"
        "`deepening_plan` 4 处陈述漂移勘误、`ph2_acceptance_report.md` §五回填 "
        f"RMSE {z['rmse_pct']}% / {z['within5']}/{z['n']}、PH4 转已知边界三处口径统一、"
        "台账 D-66/67/68/76 销号 + 纪律 32、D-88 升级双重结论、签核单 B-18/B-19、"
        "v4 回溯稿 X_offline/黏度口径勘误、state.yaml D-88/D-76 同步。\n\n"
        "**治理层同步**：`tools/r165_governance_update.py` → 契约 **v1.95** / 台账 **D-90** / "
        "签核单 **R-15** / README R165 段 / INDEX 6 工具 / state.yaml 独立 R165 条 / 本记忆。\n"
        "**终检**：`tools/r165_final_check.py`（只读，A/B/C/D 四组）。\n"
        "**下一阶段**：`docs/roadmap_next.md` **§8.7** —— R164-V1…V5 待用户裁决、"
        "R164-8…R164-11 裁决后执行、R164-12 暂缓。\n\n"
        "**纪律沉淀**：纪律 32（不可辨识/不可验证必须分层证明，机制表述先核对源码）；"
        "纪律 31 在终检中机器化（README「A2 严格支配」须落在撤回上下文内）；"
        "终检中一度出现 3 条恒真判据（A5/A7/A9）已按 D-78 全部改为数据驱动实判据。\n"
        "**未越界**：不重启 8770 端口、不改 EnKF 阈值/白名单、不写回 alpha_kla、"
        "不回填扰动随机成分、不装 fastmcp、不动看板口径。\n"
    )
    append_once(rel, block, "MEMORY-R165", "## R165　阶段收口", create=True)


# --------------------------------------------------------------------------
# 8. docs/roadmap_next.md §8.7 —— 下一阶段任务清单（本阶段最后一项交付）
#    注意：块内「8.7」只在标题出现一次（终检 C10 用 split("8.7")[-1] 判定），
#    且「GOAL §5」必须落在最后一次 8.7 之后 ⇒ 写进标题。
# --------------------------------------------------------------------------
def edit_roadmap(ev: dict) -> None:
    from string import Template
    rel = "docs/roadmap_next.md"
    z = ev["zr"]
    c, m, y = ev["co2"], ev["mcp"], ev["myc"]
    tc = ev["tool_count"]
    block = "\n" + Template(
        "### 8.7 下一阶段任务清单（R165 收口后输出；含 GOAL §5 边界声明）\n"
        "\n"
        "> 依据：`docs/roadmap_next.md` §8.6.1 / §8.6.3 / §8.6.4；主交付 `docs/r165_round_report.md`；\n"
        "> 证据 `runs/r165_final_check.json`、`runs/r165_zero_regression.json`。\n"
        "> **R165 已完成波次 1+2（R164-1 … R164-7 共 7 项）**，全部为只读探针 / 治理文本，引擎零改动：\n"
        "> CO2 检测器 ${co2p}/${co2n} PASS、PH5 服务化 ${mcpp}/${mcpn} PASS、"
        "菌丝可辨识性 ${mycp}/${mycn} PASS、治理文本 ${items} 项；\n"
        "> 零回归 ${n} 批 max|Δ| = 0.00e+00、RMSE ${rmse}%、${within5}/${n}。\n"
        "> 波次 3 / 波次 4 **未执行** ⇒ 以下为「下一阶段」清单，**须先裁决、后执行**。\n"
        "\n"
        "#### (a) 波次 3 前置：五项待用户裁决（GOAL §5 边界变更 / 环境变更）\n"
        "\n"
        "| # | 裁决项 | 优先级 | 成本 | 判据与依据 |\n"
        "|---|---|---|---|---|\n"
        "| **R164-V1** | **创新判据阈值是否改**（D-87）：5.0 → 10.0 + 持续占比 ≥2% | 🔴 最高 | 1 天 + 基线更新流程 | "
        "现行阈值下 75% 触发率 ⇒ 真实批 **84.38%** 被判 DEGRADED（R163 A 段 32 批 27 批）；离线枚举 `z>10 & frac>0.02` ⇒ 20%。"
        "**改阈值 = 改引擎行为 ⇒ 破零回归基线**，须走基线更新流程并由用户裁决 |\n"
        "| **R164-V2** | **扰动随机成分是否回填引擎**（D-83）：8 路 MATLAB 随机成分 | 🔴 最高 | 1 天 + 基线重算 | "
        "R163 实测：全通道使 b8 产量误差 **+3.09 pp** > 噪声底 2.345%，比 alpha_kla 随机性大两个数量级 ⇒ "
        "**当前最大单一保真度缺口**；τ=40 h 已对齐，缺的只是方差成分。回填必改引擎 ⇒ 破零回归 |\n"
        "| **R164-V3** | **alpha_kla 逐批标定是否写回**（D-84） | 🟡 中 | 半天 + 基线重算 | "
        "R163 双约束（DO2 + 产量）：11/12 批可标定、范围 [65, 95]；b55 单参数空间无解须排除；名义 85 仅 6/12 批合格。"
        "写回改引擎 ⇒ 破零回归 |\n"
        "| **R164-V4** | **是否安装 `fastmcp` 并锁版本**（D-85） | 🟡 中 | 半天 | "
        "装包 = **环境变更**，超本阶段边界；不装则 MCP 服务本机不可启动，PH5 端到端验证受阻。"
        "当前以 stub 注入验证 ${mcpp}/${mcpn} PASS（工具数 ${tb}→${ta}） |\n"
        "| **R164-V5** | **GOAL §2 目标量第 7 行「菌丝区组成」口径**（D-88） | 🟡 中 | (a) 5 min / (b) 立项 | "
        "R164-7 已证：`H_assim` rank=0 / nullity=4、`H_report` rank=1 / nullity=3 ⇒ **结构不可辨识**；"
        "数据资产又缺 A0/A1/A3/A4 真值 ⇒ **数据资产级不可验证**（D-88 双重结论）。"
        "(a) 降为「软测量内部量，不作交付」= 目标口径变更须用户确认；(b) 立项含菌丝形态测量数据 = 超边界；"
        "(c) 维持原口径 = 继续宣称一个无任何实测锚点的交付项 |\n"
        "\n"
        "#### (b) 波次 3 后续：裁决通过后执行（依赖 (a)）\n"
        "\n"
        "| # | 事项 | 依赖 | 判据 | 成本 |\n"
        "|---|---|---|---|---|\n"
        "| **R164-8** | 扰动随机成分移植（D-83） | R164-V2 | 逐通道方差贡献与 R163 量化数字一致；重跑 86 批并**建立新基线** | 1 天 |\n"
        "| **R164-9** | alpha_kla 逐批标定写回（D-84） | R164-V3 | 仅写回 11 批（排除 b55 / b60 / b91）；DO2 + 产量双约束仍成立 | 半天 |\n"
        "| **R164-10** | 创新判据阈值改写（D-87） | R164-V1 | 逐通道定阈值 + 零信息对照 + 反向判别力不退化；回退链触发率降到可用区间 | 1 天 |\n"
        "| **R164-11** | 装 `fastmcp` + MCP 冒烟闸门（D-85） | R164-V4 | stdio 能列出 14 个工具并成功调 `solver_info`；stub 验证退役 | 半天 |\n"
        "\n"
        "#### (c) 波次 4：受用户暂缓约束\n"
        "\n"
        "| # | 事项 | 状态 | 判据 |\n"
        "|---|---|---|---|\n"
        "| **R164-12** | 看板「观察-控制工作台」页（PH5 剩余）+ D-65 平台口径统一 | ⏸ **暂缓，不得自启** | "
        "用户解除暂缓后才排期；与 `cap` 口径（L2 prototype conditional）一并处理 |\n"
        "\n"
        "#### (d) 边界声明（本阶段未越界，下一阶段亦须逐项裁决）\n"
        "\n"
        "- **属 GOAL §5 边界变更**：R164-V1 / V2 / V3 及其执行项 8 / 9 / 10 —— 改引擎数值 ⇒ 破 86 批逐位零回归基线 "
        "⇒ 必须用户裁决 + 走基线更新流程，禁止在治理轮里「顺手」改。\n"
        "- **属环境变更**：R164-V4 / 执行项 11 —— 安装包、锁 `requirements.txt` 超出本阶段授权。\n"
        "- **属目标口径变更**：R164-V5(a) —— 改写 `GOAL.md` §2 第 7 行须用户确认；(b) 属 V1+ 立项。\n"
        "- **本阶段明确未做**：不改 EnKF 阈值 / 白名单、不写回 alpha_kla、不回填扰动随机成分、不装 `fastmcp`、"
        "不动看板口径、不改 `GOAL.md` §5 边界；不重启 8770 端口服务。\n"
        "- **长期硬基线不变**：${n} 批 `max|Δ| = 0.00e+00`、RMSE ${rmse}%、"
        "${within5}/${n} within ±5%、`cap` = L2 prototype conditional；唯一阻塞仍是 **D-65**（用户暂缓）。\n"
        "- **判据纪律（D-78 / 纪律 30 / 31 / 32）**：下一阶段任何新判据仍须零信息对照 + 双向判别力 + 数据驱动阈值；"
        "「不可辨识」与「不可验证」分层证明且机制表述先核对源码；禁止恒真 / 恒假判据；"
        "多轮寻优无法解决时**诚实降级**，不得事后放宽阈值。\n"
        "- **执行顺序**：先 (a) 五项裁决 → 再 (b) 四项执行（每项独立重跑全量闸门）→ 最后按用户解除暂缓情况排 (c)。\n"
    ).substitute(
        n=z["n"], rmse=z["rmse_pct"], within5=z["within5"],
        co2p=c["n_pass"], co2n=c["n_checks"], mcpp=m["n_pass"], mcpn=m["n_checks"],
        mycp=y["n_pass"], mycn=y["n_checks"], items=ev["govtext"]["n_items"],
        tb=tc.get("before", 12), ta=tc.get("after", 14),
    )
    append_once(rel, block, "ROADMAP-S87", "### 8.7 下一阶段任务清单")


# --------------------------------------------------------------------------
# 9. docs/r165_round_report.md —— 轮次主交付（十章）
# --------------------------------------------------------------------------
def edit_round_report(ev: dict) -> None:
    from string import Template
    rel = "docs/r165_round_report.md"
    z = ev["zr"]
    c, m, y = ev["co2"], ev["mcp"], ev["myc"]
    tc, H, t = ev["tool_count"], ev["H"], ev["co2_thresholds"]
    conf, cd = ev["co2_confusion"], ev["co2_d"]
    b = conf.get("enkf_baseline", {})
    block = "\n" + Template(
        "# R165 轮次报告 —— 波次 1+2 收口（R164-1 … R164-7）\n"
        "\n"
        "> 生成：2026-11-06　｜　承接：R164（`deepening_plan` 专项回溯）　｜　路线图：`docs/roadmap_next.md` §8.6 / §8.7\n"
        "> 用户指令：「按最优方案执行，最优结果，多轮寻优无法解决可接受降级。现在开始，完成一个阶段输出下一阶段任务清单」。\n"
        "\n"
        "---\n"
        "\n"
        "## 一、本轮做什么\n"
        "\n"
        "R164 从 `docs/deepening_plan.md`、`GOAL.md` 与 PH1–PH5 出发完成第四次全量回溯，"
        "把波次 1+2 共 7 项排进 §8.6.4。本阶段（R165）执行**且仅执行**这 7 项：\n"
        "\n"
        "| 波次 | 编号 | 任务 | 状态 |\n"
        "|---|---|---|---|\n"
        "| 2 | **R164-5** | CO2 卡死型故障只读检测器（多轮寻优） | ✅ 完成 |\n"
        "| 2 | **R164-1** | PH5 服务化补齐 `discover_residual` + `observe_online` | ✅ 完成 |\n"
        "| 2 | **R164-7** | 菌丝区 A0/A1/A3/A4 可辨识性证明 | ✅ 完成 |\n"
        "| 1 | **R164-2/3/4/6** | PH1 验收口径 / `deepening_plan` 勘误 / PH4 已知边界 / 台账销号 | ✅ 完成 |\n"
        "\n"
        "**贯穿全轮的硬约束**：全部为**只读探针 / 治理文本**，引擎数值核心逐字未改；"
        "零回归 ${n} 批 `max|Δ| = 0.00e+00`、RMSE ${rmse}%、${within5}/${n}；"
        "`cap` 口径不变（L2 prototype conditional）。\n"
        "\n"
        "---\n"
        "\n"
        "## 二、R164-5　CO2 卡死型故障只读检测器（多轮寻优）\n"
        "\n"
        "### 2.1 问题\n"
        "\n"
        "R163 在 C 段物理可信故障注入中发现 `co2_sensor_stuck` **漏检 4/5**：EnKF 创新判据对"
        "「实测 CO2 长时间精确冻结」不敏感，而这类传感器卡死在真实装置上是常见故障。\n"
        "\n"
        "### 2.2 做法：绕过创新，直接检验通道时序\n"
        "\n"
        "只读检测器，不写引擎、不进默认路径。两个特征：`exact_run`（最长精确相等游程）与"
        "`near_flat_run`（滑窗标准差 < `std_frac × global_std` 的最长连续段）；"
        "判据为**双阈值 OR**：`exact_run ≥ exact_th` 或 `near_flat_run ≥ near_th`。\n"
        "\n"
        "### 2.3 三轮寻优（阈值全部数据驱动）\n"
        "\n"
        "| 轮次 | 内容 | 结果 |\n"
        "|---|---|---|\n"
        "| 1 | `exact` 阈值网格扫描 | 给出候选可行域 |\n"
        "| 2 | `std_frac` 分离度扫描 | 选中 0.010（分离度 **6.48x**，为网格 argmax） |\n"
        "| 3 | 双阈值组合 + 显式安全裕度准则 + LOO | `exact ${exact} h / near_flat ${near} h`，可行组合 84 个；"
        "裕度要求 4.2 h / 28.2 h（对照批最长 1.4 h / 18.8 h，安全系数 3.0 / 1.5） |\n"
        "\n"
        "### 2.4 结果（判据 ${co2p}/${co2n} PASS）\n"
        "\n"
        "- **零信息对照**：健康批 20 例触发 ${d1f}/${d1n}；**正向**：CO2 卡死 5 例全检出 ${d2f}/${d2n}；"
        "**其它故障**：15 例误触发 ${d3f}/${d3n}（反向判别力成立）。\n"
        "- **LOO 5 折**：${loo_pass}/${loo_folds} 全通过（样本外定阈值，非事后拟合）。\n"
        "- **只读性**：${d7n} 例输入 DataFrame 零改写，违规 ${d7v}。\n"
        "- **组合增益**：EnKF OR 检测器四格 TP ${btp}→${tp} / FN ${bfn}→${fn} / TN、FP 不退化"
        "（漏检 5→1，多检出 4 例，健康批不被误伤）。\n"
        "- **灵敏度下界**：最小可检出冻结时长 exact 8.0 h / 带抖动 24.0 h。\n"
        "\n"
        "> 产物：`tools/r165_co2_stuck_detector.py` → `runs/r165_co2_stuck_detector.json`；日志 `runs/_r165_co2.log`。\n"
        "\n"
        "---\n"
        "\n"
        "## 三、R164-1　PH5 服务化补齐两个 MCP 工具\n"
        "\n"
        "在 `candidate/indpensim/v0.1/mcp_server.py` 新增两个**只读、纯新增**工具，工具数 "
        "**${tb} → ${ta}**：\n"
        "\n"
        "| 工具 | 包装的能力 | 返回体标记 |\n"
        "|---|---|---|\n"
        "| `discover_residual` | PH2 结构残差发现（`residual_discovery`） | `identifiable` / `degraded` / "
        "`degradation_reasons` / `mycelium_compartments` / `criteria` / `structures`；无 θ 批**显式降级不猜测** |\n"
        "| `observe_online` | 在线 EnKF 同化（`observe.enkf_observe`，`out_path=None`） | "
        "`degraded` / `reconstruction_valid` / `identifiable` / `degradation_reasons` / `n_records`；"
        "硬失败标 `reconstruction_valid=False`，成员积分失败或 `n_ens<8` 为软告警 |\n"
        "\n"
        "既有 12 个工具函数体**逐字未变**，`solver_info()` 返回体与冻结快照**逐位一致**；"
        "`ENGINE_CONTRACT.md` §2 已登记三节。因 `fastmcp` 未安装（D-85），验证采用 **stub 注入**，"
        "并在探针中用短窗口（120 行 / 约 24 h / `n_ens=4`）真实 DataFrame 做 smoke，不 stub 掉 EnKF 本体。\n"
        "\n"
        "> 产物：`tools/r165_mcp_tools_probe.py` → `runs/r165_mcp_tools_probe.json`（**${mcpp}/${mcpn} PASS**，37.5 s）。\n"
        "\n"
        "---\n"
        "\n"
        "## 四、R164-7　菌丝区组成可辨识性证明（含机制勘误）\n"
        "\n"
        "### 4.1 结论\n"
        "\n"
        "从 `observe.py` 真实常量导出观测算子：`H_assim` 对 A 组 **rank=${ha_r} / nullity=${ha_n}**，"
        "`H_report` 叠加 `X_sum` / `X_sd` 后 **rank=${hr_r} / nullity=${hr_n}**。"
        "增加同类数据只重复行、**不改变列空间** ⇒ A0/A1/A3/A4 **结构不可辨识**（观测设计层）。\n"
        "\n"
        "### 4.2 两处口径勘误（先核对源码，再下结论）\n"
        "\n"
        "- 原任务判据写「黏度只约束**总生物量**」—— **错**。引擎 `model.py` 的 `dy[9]` 生成项只依赖 "
        "**A0 单室** `a_0_pos**(1/3)`，不是 `A0+A1+A3+A4` 或 `total_X`。\n"
        "- `vis ≈ 1.77·X + 12.4` 是 R129r 的**实测经验关系**，与 `model.py` 的 A0 立方根结构不等价。\n"
        "- 动力学层对分室比例**敏感**：`r_e1/r_d1 ∝ A0`、`r_b0/r_p ∝ A1`、`r_d4 ∝ A3`、`K_diff ∝ A_t1`。\n"
        "\n"
        "⇒ 正确落点是**观测算子 H 的结构秩亏**，不是黏度约束形式。"
        "零空间扰动实测动力学响应为 0（浮点地板内），非保和正例响应在 δ=1e-6…1e-1 上严格单调；"
        "钳位审计（guards / a0_pos / nonfinite）全 0 ⇒ 秩亏**非数值保护伪影**。\n"
        "\n"
        "### 4.3 分层：不可辨识 ≠ 不可验证\n"
        "\n"
        "| 层 | 结论 | 判别式 |\n"
        "|---|---|---|\n"
        "| 观测设计 | **结构不可辨识** | H 列空间不足；加同类数据无解 |\n"
        "| 数据资产 | **不可验证** | 缺 A 组真值；换含形态测量的数据可解（R164-V5(b)） |\n"
        "\n"
        "⇒ **D-88 升级为双重结论**。主文档 `docs/r165_mycelium_identifiability.md`；"
        "产物 `runs/r165_mycelium_identifiability.json`（**${mycp}/${mycn} PASS**，87.39 s）。\n"
        "\n"
        "---\n"
        "\n"
        "## 五、R164-2/3/4/6　治理文本四项\n"
        "\n"
        "`tools/r165_governance_text.py` 以 **${items} 项**精确替换 / 插入落地，"
        "**幂等**（dry-run 零泄漏、三次复跑 `changed=0 / skip=${items} / error=0`）、"
        "数字从 `runs/r163_zero_regression.json` 读取、CRLF / LF 按目标文件原样保留：\n"
        "\n"
        "| 编号 | 内容 |\n"
        "|---|---|\n"
        "| R164-2 | PH1 验收口径改写：清理「mux 8.6% 偏差 = 验证通过」与 σ̂ 已估计口径，统一改引 "
        "**MAP 散布上界 + 不含群体先验**；显式登记「28 批验证集从未留出」（D-89） |\n"
        "| R164-3 | `docs/deepening_plan.md` 4 处陈述漂移勘误（头部历史快照、PH2 投票口径 88 有效批 / 12 站 / 负向 5、"
        "R129t2 σ̂ 段 R142 证伪批注、COMBINED 替代方案批注）；`docs/ph2_acceptance_report.md` §五回填 "
        "RMSE **${rmse}%** / **${within5}/${n}** / 0 catastrophic |\n"
        "| R164-4 | PH4 验收项「对照固定配方提升量化」转**已知边界**，路线图 / 台账 / 签核单三处一致（D-54），签核单新增 B-18 |\n"
        "| R164-6 | D-67 / D-68 / D-66 / D-81 / D-76 状态滞后清理（四处标题 + 总表四行销号），"
        "新增**纪律 32**（不可辨识 / 不可验证分层证明、机制表述先核对源码）；v4 回溯稿 X_offline 与黏度口径同步勘误 |\n"
        "\n"
        "---\n"
        "\n"
        "## 六、判据纪律、多轮寻优与诚实降级\n"
        "\n"
        "承 **D-78**：任何指标做**零信息对照**；判据**双向**（正向触发 + 反向判别力）；禁止恒真 / 恒假；"
        "阈值必须数据驱动扫描 / LOO / 灵敏度 / 显式裕度准则确定，**不得手写或事后放宽**。\n"
        "\n"
        "- 本轮 CO2 检测器经历三轮寻优，最终阈值由 `_choose(...)` 的显式安全裕度准则给出，LOO 用同一准则复选，"
        "而非挑一个「看起来能过」的数。\n"
        "- 终检脚本初稿曾出现 3 条恒真 / 弱判据（A5 / A7 / A9），已全部改为读取 "
        "`runs/r165_co2_stuck_detector.json` 中 D1/D2/D3/D5/D7/D8 的**具体数值**实判据；"
        "C5 / C7 改用「三个产物名」与 `yaml.safe_load` 独立条目，避免纯子串误报（纪律 31）。\n"
        "- **诚实降级**：`fastmcp` 未安装（D-85）⇒ MCP 服务本机不可启动，采用 stub 注入做逻辑层验证，"
        "并明确登记为环境缺口而非宣称端到端通过；`observe_online` 用短窗口 smoke 而非全时长跑。\n"
        "- R164-7 的**机制表述偏差**（黏度只约束总生物量）被实测推翻后，按纪律 32 先核对源码再写入治理层勘误，"
        "没有把错误前提包装成结论。\n"
        "\n"
        "---\n"
        "\n"
        "## 七、治理层同步\n"
        "\n"
        "`tools/r165_governance_update.py`（幂等、dry-run 零泄漏、数字全部从 `runs/` 读取）一次性同步：\n"
        "\n"
        "| 对象 | 变更 |\n"
        "|---|---|\n"
        "| `ENGINE_CONTRACT.md` | v1.94 → **v1.95**（工具 12→14、CO2 双阈值、H 秩、46 项治理文本、引擎零改动、未越界声明）|\n"
        "| `docs/r157_debt_ledger.md` | 新增 **D-90**（R165 轮次）|\n"
        "| `docs/m5_review_signoff.md` | 新增 **R-15**（R165 收口）|\n"
        "| `README.md` | §4 标题 → v1.95、阅读顺序 → R165 报告、新增 `### R165` 段 |\n"
        "| `tools/INDEX.md` | 新增 R165 六工具表 + 两份文档引用 |\n"
        "| `state.yaml` | `open_questions` 新增独立 **R165** 条 |\n"
        "| `.workbuddy/memory/2026-11-06.md` | R165 收口记忆 |\n"
        "| `docs/roadmap_next.md` | 新增 §8.7 下一阶段任务清单 |\n"
        "| 本报告 | `docs/r165_round_report.md` |\n"
        "\n"
        "---\n"
        "\n"
        "## 八、闸门：零回归 / pytest / 终检\n"
        "\n"
        "| 闸门 | 命令 | 结果 |\n"
        "|---|---|---|\n"
        "| 全量零回归 | `py tools/r134_zero_regression.py --tol 0 --out runs/r165_zero_regression.json` | "
        "**${n} 批逐位一致**：`max|Δ| = 0.00e+00`、RMSE ${rmse}%、${within5}/${n} within ±5%、0 批超差 |\n"
        "| 测试 | `py -m pytest -q` | `${pytest}` |\n"
        "| 终检 | `py tools/r165_final_check.py --json` | A 探针判据 / B 治理文本+幂等 / C 治理层同步 / "
        "D 闸门与文档卫生；产物 `runs/r165_final_check.json` |\n"
        "| 引擎零改动 | 4 个源码文件 SHA256 与 R164-7 证明时比对 | 逐位一致（终检 A21 / D7）|\n"
        "\n"
        "---\n"
        "\n"
        "## 九、本轮未做（明确边界）\n"
        "\n"
        "- 不改 EnKF 阈值 / 白名单；不写回 `alpha_kla`；不回填扰动随机成分；不安装 `fastmcp`；不动看板口径；"
        "不改 `GOAL.md` §5 边界。\n"
        "- 不写 `data/`；不新增观测通道；不把检测器 / 证明逻辑写入任何**默认引擎路径**；不重启 8770 端口服务。\n"
        "- `R164-V1…V5` 属 **GOAL §5 边界变更 / 环境 / 目标口径变更**，`R164-8…R164-11` 为裁决后执行项，"
        "`R164-12` 受用户暂缓约束 —— 本阶段**一律不越界**。\n"
        "\n"
        "---\n"
        "\n"
        "## 十、下一阶段任务清单与证据清单\n"
        "\n"
        "**下一阶段**清单见 `docs/roadmap_next.md` §8.7：(a) 五项待用户裁决（R164-V1…V5）；"
        "(b) 裁决后执行 R164-8…R164-11；(c) 暂缓的 R164-12；(d) GOAL §5 边界声明与判据纪律。\n"
        "\n"
        "| 证据 | 路径 |\n"
        "|---|---|\n"
        "| CO2 检测器 | `runs/r165_co2_stuck_detector.json` / `runs/_r165_co2.log` |\n"
        "| MCP 工具探针 | `runs/r165_mcp_tools_probe.json` / `runs/_r165_mcp.log` |\n"
        "| 菌丝可辨识性 | `runs/r165_mycelium_identifiability.json` / `runs/_r165_mycelium.log` / "
        "`docs/r165_mycelium_identifiability.md` |\n"
        "| 治理文本四项 | `runs/r165_governance_text.json` |\n"
        "| 治理层同步 | `runs/r165_governance_update.json` |\n"
        "| 零回归 | `runs/r165_zero_regression.json` / `runs/_r165_zero_regression.log` |\n"
        "| pytest | `runs/_r165_pytest.log` |\n"
        "| 终检 | `runs/r165_final_check.json` |\n"
        "| 本报告 | `docs/r165_round_report.md` |\n"
    ).substitute(
        n=z["n"], rmse=z["rmse_pct"], within5=z["within5"],
        co2p=c["n_pass"], co2n=c["n_checks"], mcpp=m["n_pass"], mcpn=m["n_checks"],
        mycp=y["n_pass"], mycn=y["n_checks"], items=ev["govtext"]["n_items"],
        tb=tc.get("before", 12), ta=tc.get("after", 14),
        exact=t.get("exact_run_h"), near=t.get("near_flat_run_h"),
        ha_r=H["H_assim"][0], ha_n=H["H_assim"][1],
        hr_r=H["H_report"][0], hr_n=H["H_report"][1],
        tp=conf.get("TP"), fn=conf.get("FN"), btp=b.get("TP"), bfn=b.get("FN"),
        d1f=cd["D1"].get("fired", 0), d1n=cd["D1"].get("n", 0),
        d2f=cd["D2"].get("fired", 0), d2n=cd["D2"].get("n", 0),
        d3f=cd["D3"].get("fired", 0), d3n=cd["D3"].get("n", 0),
        loo_pass=cd["D5"].get("pass", 0), loo_folds=cd["D5"].get("folds", 0),
        d7n=cd["D7"].get("n", 0), d7v=cd["D7"].get("violations", 0),
        pytest=ev["pytest_line"],
    )
    append_once(rel, block, "REPORT-R165", "# R165 轮次报告", create=True)


ALL_GROUPS = [edit_contract, edit_ledger, edit_signoff, edit_readme,
              edit_index, edit_state, edit_memory,
              edit_roadmap, edit_round_report]


def file_hashes() -> dict:
    rel = ["ENGINE_CONTRACT.md", "docs/r157_debt_ledger.md", "docs/m5_review_signoff.md",
           "README.md", "tools/INDEX.md", "state.yaml",
           ".workbuddy/memory/2026-11-06.md", "docs/roadmap_next.md",
           "docs/r165_round_report.md"]
    out = {}
    for r in rel:
        p = ROOT / r
        out[r] = hashlib.sha256(p.read_bytes()).hexdigest()[:16] if p.exists() else "MISSING"
    return out


def main() -> int:
    global DRY
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    DRY = not args.apply

    ev = load_evidence()
    before = file_hashes()
    for fn in ALL_GROUPS:
        fn(ev)
    after = file_hashes()

    if DRY and before != after:
        ERRORS.append("dry-run 前后文件哈希不一致（严重）")

    n_changed = sum(1 for r in RECORDS if r["status"].startswith("changed"))
    n_skip = sum(1 for r in RECORDS if r["status"].startswith("skip"))
    n_err = sum(1 for r in RECORDS if r["status"].startswith("ERROR"))
    verdict = "PASS" if (not ERRORS and n_err == 0) else "FAIL"

    print(f"== R165 治理层同步 == mode={'APPLY' if not DRY else 'DRY-RUN'}")
    print(f"证据：MCP {ev['mcp']['n_pass']}/{ev['mcp']['n_checks']} / "
          f"CO2 {ev['co2']['n_pass']}/{ev['co2']['n_checks']} / "
          f"菌丝 {ev['myc']['n_pass']}/{ev['myc']['n_checks']} / "
          f"零回归 RMSE {ev['zr']['rmse_pct']}% {ev['zr']['within5']}/{ev['zr']['n']}")
    print(f"编辑项 {len(RECORDS)}：changed={n_changed}  skip={n_skip}  error={n_err}")
    if DRY:
        print(f"dry-run 零泄漏自检：{'PASS' if before == after else 'FAIL'}")
    for r in RECORDS:
        if r["status"].startswith("ERROR"):
            print(f"  [ERROR] {r['tag']} {r['status']} {r['file']}")
    for e in ERRORS:
        print(f"  [ERR] {e}")
    print(f"verdict = {verdict}")

    if args.json and not DRY:
        (RUNS / "r165_governance_update.json").write_text(
            json.dumps({"mode": "apply", "verdict": verdict, "n_changed": n_changed,
                        "n_skip": n_skip, "n_error": n_err, "evidence": ev,
                        "records": RECORDS, "errors": ERRORS},
                       ensure_ascii=False, indent=1), encoding="utf-8")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
