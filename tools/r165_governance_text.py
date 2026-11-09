# -*- coding: utf-8 -*-
"""R165 / R164-2,3,4,6 —— 治理文本四项（幂等、可干跑、只读引擎）。

设计纪律（承 R163 六处工程缺陷 + 纪律 25/28/29/30/31）：
  * 所有写入统一走 do() 门控；--dry-run 不得泄漏任何写文件；
  * 每个替换自带 marker 幂等判定；三次复跑零写入；
  * 换行风格按目标文件原样保留（CRLF / LF 各自还原）；
  * 数字数据驱动，从 runs/ 产物读取，不手写；
  * 文本状态判定识别上下文，不做纯子串计数（纪律 31）；
  * 历史流水原文不改，只在对应行就地加注勘误 / 销号。

用法：
  py tools/r165_governance_text.py                 # dry-run（默认，零写入）
  py tools/r165_governance_text.py --apply        # 实际写入
  py tools/r165_governance_text.py --apply --json # 写入并落 runs/ 证据
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
# 数据驱动：数字一律从 runs/ 读，不手写
# --------------------------------------------------------------------------
def load_evidence() -> dict:
    zr = json.loads((RUNS / "r163_zero_regression.json").read_text(encoding="utf-8"))
    s = zr["summary"]
    ev = {
        "rmse_pct": f'{float(s["rmse_pct"]):.3f}',      # 2.3448 -> 2.345
        "within5": int(s["within5"]),                   # 86
        "n": int(s["n"]),                               # 86
        "zero_regression_ref": "runs/r163_zero_regression.json",
        "acceptance_ref": "runs/r156_acceptance.json",
    }
    for name in ("r165_mycelium_identifiability.json",
                 "r165_co2_stuck_detector.json",
                 "r165_mcp_tools_probe.json"):
        p = RUNS / name
        if not p.exists():
            ERRORS.append(f"缺证据产物: {name}")
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        ev[name] = {
            "verdict": d.get("verdict"),
            "n_pass": d.get("n_pass"),
            "n_checks": d.get("n_checks"),
        }
    return ev


# --------------------------------------------------------------------------
# 原语：换行风格保持 + do() 门控 + marker 幂等
# --------------------------------------------------------------------------
def read_norm(rel: str):
    p = ROOT / rel
    raw = p.read_bytes()
    nl = "\r\n" if b"\r\n" in raw else "\n"
    text = raw.decode("utf-8").replace("\r\n", "\n")
    return p, nl, text


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


def insert_after_prefix(rel: str, prefix: str, new_lines: list[str],
                        tag: str, marker: str) -> None:
    """在首个以 prefix 开头的行之后插入 new_lines；marker 保证幂等。"""
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
# R164-2 / R164-3：deepening_plan 自身勘误 + PH1 验收口径改写
# --------------------------------------------------------------------------
def edits_deepening_plan(ev: dict) -> None:
    rel = "docs/deepening_plan.md"
    M = "R165 勘误（2026-11-06）"

    replace_once(
        rel,
        "# 反应罐求解器深化方案 — 由进出料观测反向建模（讨论稿 v1 → 已拍板 v1.1）\n\n",
        "# 反应罐求解器深化方案 — 由进出料观测反向建模（讨论稿 v1 → 已拍板 v1.1）\n\n"
        "> **R165 勘误（2026-11-06）**：本文是 **R42–R55 阶段的历史方案与执行快照**，"
        "§8「执行实况」停在 2026-10-29，**不代表 R163 之后（R164 回溯、R165 收口）的现行状态**。\n"
        "> R164 专项回溯（`docs/goal_backtrace_check_v4.md`）已发现本文 **4 处陈述漂移**，"
        "本轮在对应行就地加注勘误，历史流水原文保持不改。\n"
        "> 当前权威口径以 `docs/roadmap_next.md` §8.6 / `docs/r157_debt_ledger.md` 为准。\n\n",
        "DP-head", M)

    M2 = "R165 勘误（D-89）"
    replace_once(
        rel,
        "- 批池整理：100 批 → 训练 60 / 验证 28 / 黄金 12（分层）\n",
        "- 批池整理：100 批 → 训练 60 / 验证 28 / 黄金 12（分层）\n"
        "  - ⚠ **R165 勘误（D-89）**：这 **28 批验证集从未被留出**。"
        "`candidate/indpensim/v0.1/hier_est.py:276` 实际执行 "
        "`batch_list = bp[\"train\"] + bp[\"validation\"]`（v2 全批池把训练+验证合并拟合）"
        " ⇒ 基于该池的任何超参数 / 温度 / 网格选择都是**训练集内选择**，不存在独立验证。\n"
        "  - ⇒ PH1 的验收口径须改写（见下条），且**禁止**引用「验证集」作为任何泛化性论据。\n",
        "DP-PH1-pool", M2)

    M3 = "R165 改写（R164-2 / D-89 / R142）"
    replace_once(
        rel,
        "- 验收：先验分布与 MATLAB 生成机制一致性（μ̂≈0.41±0.025 等数值对齐）；黄金集零接触\n",
        "- 验收：先验分布与 MATLAB 生成机制一致性（μ̂≈0.41±0.025 等数值对齐）；黄金集零接触\n"
        "  - ⚠ **R165 改写（R164-2 / D-89 / R142）**：①「μ̂±σ̂ 与 MATLAB 生成机制数值对齐 ⇒ 验证通过」"
        "**不再作为验收判据** —— R142 已证伪 `dl_sigma` 的 σ_pop=0 是温度口径失效的产物"
        "（`T_EB=1.0` 比损失差大 106×、ESS=46.8/48 ⇒ 后验等于无信息先验），`COMBINED`"
        "逐批点估计也**不是批间分布样本**；现行可引用口径只有 **MAP 散布上界** "
        "`σ_pop(mux) ≤ 0.0328 / mup ≤ 0.0056 / m_s ≤ 0.0019`，且**必须注明不含群体先验**。\n"
        "  - ② 因 28 批验证集未留出，本验收**不含独立泛化误差**，只能作为「训练集内自洽」登记"
        "（**已知边界**，见 `docs/m5_review_signoff.md` B-19）。\n",
        "DP-PH1-accept", M3)

    replace_once(
        rel,
        "DL 矩估计器实现但网格后验 var_w≫var_between → σ_pop=0（已登记 PH3+ 债务）",
        "DL 矩估计器实现但网格后验 var_w≫var_between → σ_pop=0 —— "
        "**R142 已证伪该统计量为温度口径失效产物，R165 改引 MAP 散布上界（见 §5 R129t 勘误）**",
        "DP-PH1-row", "R165 改引 MAP 散布上界")

    replace_once(
        rel,
        "30 批中票 A_t1 = 60 站点 63% 负向",
        "**88 有效批 / A_t1 命中 12 站 / 负向 5**"
        "（`runs/hier_est/residual_discovery_full.json`；R165 勘误：原文"
        "「30 批 / 60 站点 / 63% 负向」是 R42–R55 中途快照，非最终口径）",
        "DP-PH2-vote", "88 有效批 / A_t1 命中 12 站")

    replace_once(
        rel,
        "| PH4 | advise_control 上线（11 工具); T1 校验器 validate_t1 执行化 + **窗口包络采样**"
        "（时间域=咨询域）; §15 文献桥 5 锚（Crossref 核证） | ENGINE_CONTRACT.md v1.1; ledger49/48 |\n",
        "| PH4 | advise_control 上线（11 工具); T1 校验器 validate_t1 执行化 + **窗口包络采样**"
        "（时间域=咨询域); §15 文献桥 5 锚（Crossref 核证） | ENGINE_CONTRACT.md v1.1; ledger49/48 |\n"
        "| **PH4 结论（R165 补，R164-4）** | **转已知边界**：D-54 / D-57 判决 ⇒ "
        "**运行期连续调控（梯度型闭环）封死**（响应是阶跃、跳变两侧无可用梯度区分度）；"
        "**开环设定点标定保留**但落点相对精度要求 **1e−04…1e−05**（属标定级而非控制级）。"
        "若要运行期调控须走结构改动路线（L3，需另行授权） | "
        "`docs/r157_debt_ledger.md` D-54/D-57；`docs/m5_review_signoff.md` B-9 / **B-18** |\n",
        "DP-PH4-boundary", "PH4 结论（R165 补，R164-4）")

    replace_once(
        rel,
        "- mux: σ_pop=0.0272（MATLAB σ_gen=0.025，8.6% 偏差）——验证通过\n",
        "- mux: σ_pop=0.0272（MATLAB σ_gen=0.025，8.6% 偏差）——**原文「验证通过」已由 R142 证伪**："
        "该 `COMBINED` 逐批点估计的散布是 MATLAB 生成机制真值的 8.3×，且给恒定参数 `m_s` "
        "造出 sd 0.0033 ⇒ **不得作批间分布样本、不得用于估计 σ_pop**"
        "（R165 勘误；现行口径见 §5 PH1 验收改写）\n",
        "DP-sigma-verify", "原文「验证通过」已由 R142 证伪")

    replace_once(
        rel,
        "新增 `hier_est.dl_sigma_combined()` 函数。网格后验 DL 估计结构性失败，\n"
        "COMBINED 替代方案是实用替代。完全非网格后验（MCMC）为后续工作。\n",
        "新增 `hier_est.dl_sigma_combined()` 函数。网格后验 DL 估计结构性失败，\n"
        "COMBINED 替代方案是实用替代。完全非网格后验（MCMC）为后续工作。\n"
        "- ⚠ **R165 勘误（R142 / D-28）**：「COMBINED 是实用替代」**只在「逐批点估计用于复现 86 批产量」"
        "这一用途下成立**；作为 σ_pop 估计量它已被证伪（温度口径失效 + 网格量化下限 + 信息量不足"
        "三层归因）。可引用的只有 MAP 口径上界 `σ_pop ≤ 0.0328/0.0056/0.0019`（不含群体先验），"
        "**禁止**报点估计或「批间参数服从 N(·,·)」。换协议（连续优化 + 剖面似然）前不得重启该项。\n",
        "DP-sigma-combined", "R165 勘误（R142 / D-28）")

    replace_once(
        rel,
        "**诚实缺口台账（活跃项）**：DL σ̂ 网格后验结构性失败已用 COMBINED 替代方案\n"
        "部分解决（mux σ_pop=0.027 vs MATLAB 0.025）；完全非网格后验（MCMC）仍为后续工作；\n",
        "**诚实缺口台账（活跃项）**：⚠ **R165 勘误**：原记「DL σ̂ 网格后验结构性失败已用 COMBINED\n"
        "替代方案部分解决」不成立 —— R142 已证伪 `dl_sigma` 的 σ_pop=0 是温度口径失效产物，"
        "且 COMBINED 的批间散布**不是批间变异**（见 §5 R129t2 勘误）；现行口径为 MAP 散布上界，"
        "且**28 批验证集从未留出（D-89）** ⇒ PH1 验收不含独立泛化误差。"
        "完全非网格后验（MCMC）仍为后续工作；\n",
        "DP-gap-ledger", "R165 勘误**：原记")


# --------------------------------------------------------------------------
# R164-3 ④：ph2_acceptance_report §五回填（CRLF 文件）
# --------------------------------------------------------------------------
def edits_ph2_report(ev: dict) -> None:
    rel = "docs/ph2_acceptance_report.md"
    rmse, w5, n = ev["rmse_pct"], ev["within5"], ev["n"]
    replace_once(
        rel,
        "- DL σ̂ 需非网格后验（PH3+ 债务）\n"
        "- PAA 通道批间异质（R90 普查 7/9 正向、2/9 反相；μp 机理锚点 −0.891）\n"
        "- D9 方案 (b) ODE 级积分未实施；产量级 RMSE ≤3.5% 需机理增强项（V1+）\n",
        "- DL σ̂ 需非网格后验（PH3+ 债务）—— **R165 勘误（R142）**：`dl_sigma` 的 σ_pop=0 "
        "是温度口径失效产物（T_EB=1.0 比损失差大 106×、ESS=46.8/48），`COMBINED` 逐批点估计"
        "亦不得作批间分布样本；现行可引用口径只有 MAP 散布上界 "
        "σ_pop ≤ 0.0328/0.0056/0.0019（不含群体先验）\n"
        "- PAA 通道批间异质（R90 普查 7/9 正向、2/9 反相；μp 机理锚点 −0.891）\n"
        "- D9 方案 (b) ODE 级积分未实施；~~产量级 RMSE ≤3.5% 需机理增强项（V1+）~~\n"
        "  **R165 回填（`docs/goal_backtrace_check_v4.md` §D3）**：该「诚实缺口」**早已闭合** —— "
        f"默认基线 {n} 批产量 **RMSE {rmse}%**（红线 3.5%）、**{w5}/{n} 在 ±5%**、"
        "**0 catastrophic**（证据 `runs/r163_zero_regression.json`："
        f"`summary.rmse_pct={rmse}` / `within5={w5}` / `n={n}`；"
        "`runs/r156_acceptance.json` HARD 全 PASS）⇒ 「需机理增强项」的推断已不成立，"
        "本项从缺口清单移除。\n",
        "PH2-section5", "R165 回填（`docs/goal_backtrace_check_v4.md` §D3）")


# --------------------------------------------------------------------------
# R164-2：README DL σ̂ 滞后行
# --------------------------------------------------------------------------
def edits_readme(ev: dict) -> None:
    rel = "README.md"
    replace_once(
        rel,
        "| DL σ̂ 定标 | 未定（D-2） | L2 阻断 |\n",
        "| DL σ̂ 定标 | **已关闭（D-2 / R142）**：`dl_sigma` 的 σ_pop=0 是温度口径失效产物 ⇒ "
        "只能引用 **MAP 散布上界** `σ_pop(mux)≤0.0328 / mup≤0.0056 / m_s≤0.0019`"
        "（**不含群体先验**）；`COMBINED` 逐批点估计仅用于复现 86 批产量，"
        "**不得作批间分布样本**（D-28） | 不再阻断（`cap` 口径不变） |\n",
        # marker 必须选「后续轮次标注组不会改写」的片段，否则第三次复跑会漏判（R163 幂等锚点纪律）
        "README-sigma", "`COMBINED` 逐批点估计仅用于复现 86 批产量")


# --------------------------------------------------------------------------
# R164-4 / R164-6：台账 D-54 口径统一 + 状态销号 + D-88 升级 + 纪律 32
# --------------------------------------------------------------------------
def edits_ledger(ev: dict) -> None:
    rel = "docs/r157_debt_ledger.md"

    # --- R164-4：D-54 三处口径统一注记（路线图 / 台账 / 签核单 B-18） ---
    insert_after_prefix(
        rel,
        "### D-54　缺葡萄糖闭环",
        ["> **R165 / R164-4 口径统一**：本条与 `docs/roadmap_next.md` §8.6（R164-4）、"
         "`docs/m5_review_signoff.md` **B-18** 三处统一写明：**运行期连续调控封死 / "
         "开环设定点标定保留但精度 1e−04…1e−05**；PH4 的「运行期调控」验收项**转已知边界**，"
         "不再作为待办。",
         ""],
        "LED-D54-unify", "R165 / R164-4 口径统一")

    # --- R164-6：D-66 与 D-81 重复，销号 ---
    replace_once(
        rel,
        "### D-66　缺 `pytest.ini` / `conftest.py`　🟢 **新，L1（小项，未做）**\n",
        "### D-66　缺 `pytest.ini` / `conftest.py`　✅ **R165 关闭（与 D-81 重复，以 D-81 为权威）**\n",
        "LED-D66-title", "R165 关闭（与 D-81 重复")
    replace_once(
        rel,
        "实测不影响根目录运行，但 pytest 缓存与根路径解析不稳。**低优先，未在本轮处理**。\n",
        "实测不影响根目录运行，但 pytest 缓存与根路径解析不稳。**R165 销号**：该缺口已由 **D-81** "
        "以新增项目根 `pytest.ini` 关闭（13+20 全绿）；本条与 D-81 **重复**，统一以 D-81 为权威登记，"
        "不再单列为未做项。\n",
        "LED-D66-body", "R165 销号**：该缺口已由")

    # --- R164-6：D-67 工具侧已修 ---
    replace_once(
        rel,
        "### D-67　故障特征签名必须是**分段**的量，整批口径会被恢复效应主导　🔴 **新，L2（方法）**\n",
        "### D-67　故障特征签名必须是**分段**的量，整批口径会被恢复效应主导　"
        "✅ **R165 关闭（工具侧已修，纪律已固化）**\n",
        "LED-D67-title", "R165 关闭（工具侧已修")
    replace_once(
        rel,
        "| 工具 | `tools/r157_fault_modes.py` 增加 `s_at_window_end` / `p_at_window_end` / "
        "`do2_at_window_end` 三个**窗口内**特征量并逐条打印 |\n",
        "| 工具 | `tools/r157_fault_modes.py` 增加 `s_at_window_end` / `p_at_window_end` / "
        "`do2_at_window_end` 三个**窗口内**特征量并逐条打印 |\n"
        "| **R165 销号** | 工具侧三个窗口内特征量已落 `tools/r157_fault_modes.py` 并逐条打印；"
        "「故障特征必须分段报告」已固化为**纪律**（见 §六）。⇒ 总表由 🔴 转 ✅；"
        "本条不再计为未闭合 L2 |\n",
        "LED-D67-row", "R165 销号** | 工具侧三个窗口内")

    # --- R164-6：D-68 已由 R156 ph_fix 修复 ---
    replace_once(
        rel,
        "### D-68　默认基线下故障注入会触发 pH 数值崩溃 ⇒ 淹没故障特征　"
        "🔴 **新，L2（前置条件）**\n",
        "### D-68　默认基线下故障注入会触发 pH 数值崩溃 ⇒ 淹没故障特征　"
        "✅ **R165 关闭（R156 `ph_fix` 机制侧修复）**\n"
        "> **R165 销号依据**：D-55 的 pH 数值病已由 R156 定位到公式层并以 opt-in `ph_fix` "
        "修复（默认 0 ⇒ 逐位零回归，5 批钳位批 `pH_max` 7.267–9.185 → 7.002–7.072、"
        "钳位 5→0）；本条 §「修法」给出的 `--ph-fix` 开关与「必须在 `ph_fix=1` 口径下做」"
        "已落地 ⇒ 前置条件解除。是否把 `ph_fix` 提为默认仍属 **GOAL §5 边界变更**，"
        "按 R164-V 系列待裁决，不影响本条销号。\n",
        "LED-D68-title", "R165 关闭（R156 `ph_fix`")

    # --- R164-6：D-76 上下文判定（纪律 31） ---
    replace_once(
        rel,
        "### D-76　README **传播了 R158 已被 D-74 撤回的 A2 结论**　"
        "🔴 **R160 新增，L2（对外文档）**\n",
        "### D-76　README **传播了 R158 已被 D-74 撤回的 A2 结论**　"
        "✅ **R165 关闭（上下文判定：引用即当场撤回，非残留）**\n"
        "\n"
        "> **R165 销号依据（纪律 31）**：R160 登记的「README:165-166 仍写 A2 严格支配」经"
        "**逐行上下文复核**：`README.md:167-172` 是「**引用 R158 原话并当场撤回**」的正确表述"
        "（`:168` 引原话、`:169` 起「该支配结论已撤回」并给出剔除退化批后 A2 20.47% "
        "劣于 C0 10.29% 的实测），属**否定式引用**而非残留传播。⇒ 纯子串 grep 会误报"
        "（纪律 31），终检判据须识别上下文。本条关闭；README 对应段落**不改**"
        "（改掉反而会丢失证伪链的原始记录）。\n",
        "LED-D76-title", "R165 关闭（上下文判定")

    # --- R164-6：总表四行状态销号 ---
    replace_once(
        rel,
        "| D-66 | 缺 pytest.ini / conftest.py | L1 | 🟢 新（小项，未做） |\n",
        "| D-66 | 缺 pytest.ini / conftest.py | L1 | ✅ **R165 关闭**（与 D-81 重复，以 D-81 为权威） |\n",
        "LED-TBL-D66", "R165 关闭**（与 D-81 重复")
    replace_once(
        rel,
        "| D-67 | 故障签名必须分段（窗内 / 恢复期） | L2 | 🔴 新（T3-2 实测暴露） |\n",
        "| D-67 | 故障签名必须分段（窗内 / 恢复期） | L2 | ✅ **R165 关闭**（工具侧已修 + 纪律固化） |\n",
        "LED-TBL-D67", "R165 关闭**（工具侧已修")
    replace_once(
        rel,
        "| D-68 | 默认基线下故障注入触发 pH 崩溃 | L2 | 🔴 新（T3-2 实测暴露，已给修法） |\n",
        "| D-68 | 默认基线下故障注入触发 pH 崩溃 | L2 | ✅ **R165 关闭**（R156 `ph_fix` 机制侧修复） |\n",
        "LED-TBL-D68", "R165 关闭**（R156 `ph_fix`")
    replace_once(
        rel,
        "| D-76 | README **传播了 R158 已被 D-74 撤回的 A2 结论** | L2 | "
        "🔴 **R160 新增**（README:165-166） |\n",
        "| D-76 | README **传播了 R158 已被 D-74 撤回的 A2 结论** | L2 | "
        "✅ **R165 关闭**（纪律 31 上下文判定：否定式引用，非残留） |\n",
        "LED-TBL-D76", "R165 关闭**（纪律 31 上下文判定")

    # --- D-88 升级为双重结论（R164-7） ---
    replace_once(
        rel,
        "### D-88　GOAL §2 目标量「菌丝区组成 A0/A1/A3/A4」**数据资产级不可达**　"
        "🔴 **R164 新增，L2（原始目标）\n",
        "### D-88　GOAL §2 目标量「菌丝区组成 A0/A1/A3/A4」**双重不可达**　"
        "🔴 **R164 新增 / R165 升级，L2（原始目标）**\n",
        "LED-D88-title", "R164 新增 / R165 升级")
    replace_once(
        rel,
        "黏度方程只约束**总生物量**（`a_0^(1/3)` 口径，R129r 已证该口径与实测的线性关系不匹配）"
        "⇒ 4 个形态状态**不可分离**",
        "**R165 勘误**：引擎黏度生成项 `dy[9]` **只依赖 A0 单室**"
        "（`a_0_pos**(1/3)`，`model.py:660-674`），既不是 `A0+A1+A3+A4` 也不是 `total_X`；"
        "「黏度 ≈ 1.77·X+12.4」只是 R129r 的实测经验关系（相关性 0.81–0.85），二者不等价；"
        "`VIS_OUT_SCALE` 只提供一个标量比例系数，**不携带分室比例信息**。"
        "⇒ 4 个形态状态在现有观测算子下**结构不可辨识**（见 R164-7 数值秩亏证明）",
        "LED-D88-find", "R165 勘误**：引擎黏度生成项")
    replace_once(
        rel,
        "本轮**不**新增观测通道、**不**改引擎、**不**宣称「菌丝区组成不可辨识」—— "
        "准确表述是「**在本项目可用数据资产下不可验证**」（若有含形态测量的新数据，结论可能改变）。"
        "**不**把「不可验证」与「不可辨识」混为一谈（后者须先做部分可辨识性研究，见路线图 R164-7）",
        "**R165 升级为双重结论**（`docs/r165_mycelium_identifiability.md`，11/11 PASS）："
        "① **结构不可辨识（观测设计层）** —— 现有 `H_assim` 对 A 组 **rank=0 / nullity=4**，"
        "`H_report` **rank=1 / nullity=3**（只暴露 `[1,1,1,1]` 方向）；`X_offline` 被 "
        "`observe.py:243-257` 的 `continue` **完全排除同化** ⇒ 同化层对 A 组从未有任何观测更新。"
        "增加同类批次 / 更密采样 / 更长时程**不改变列空间秩**，不能解决。"
        "② **数据资产级不可验证** —— V3 的 37 列无任何 A 组实测真值，Raman 通道被 D-71 否证 "
        "⇒ 换一份含菌丝形态测量的数据资产可改变这一层结论。两者边界是"
        "**是否改变观测算子 H 的列空间**，而非是否增加数据行数。"
        "**不**把两层混为一谈；本轮仍**不**新增观测通道、**不**改引擎。"
        "动力学层对分室比例**是敏感的**（`dP_dt`/`dS_dt`/`dCO2_dt` 均非零）"
        "⇒ 不可辨识的落点只能是**观测算子结构秩亏**，不是「模型对分室不敏感」",
        "LED-D88-bound", "R165 升级为双重结论")
    replace_once(
        rel,
        "③ 中期可做**部分可辨识性**研究：4 个形态状态 vs 1 个黏度标量 ⇒ 最多给总量约束、**不可分离**",
        "③ **部分可辨识性研究已由 R164-7 完成**（见下「证据」行）：结论是观测算子结构秩亏，"
        "且黏度不是总量约束",
        "LED-D88-sugg", "部分可辨识性研究已由 R164-7 完成")
    replace_once(
        rel,
        "| 证据 | `data/processed/batches/batch_01.csv` 列清单（37 列，无 A 组）；"
        "`candidate/indpensim/v0.1/model.py:6`（A 组状态索引 10–14）；黏度方程 `a_0^(1/3)` 口径"
        "（R129r）；`runs/r158_pat_ablation_scale.json`（D-71/D-72）；`docs/goal_backtrace_check_v4.md` §四 |\n",
        "| 证据 | `data/processed/batches/batch_01.csv` 列清单（37 列，无 A 组）；"
        "`candidate/indpensim/v0.1/model.py:6`（A 组状态索引 10–14）；黏度方程 `a_0^(1/3)` 口径"
        "（R129r）；`runs/r158_pat_ablation_scale.json`（D-71/D-72）；`docs/goal_backtrace_check_v4.md` §四；"
        "**R165 新增**：`runs/r165_mycelium_identifiability.json`（H 秩 / 零空间 / 反向判别力 "
        "11/11 PASS）、`docs/r165_mycelium_identifiability.md` |\n",
        "LED-D88-evid", "R165 新增**：`runs/r165_mycelium_identifiability.json`")
    replace_once(
        rel,
        "| D-88 | GOAL §2 目标量「菌丝区组成 A0/A1/A3/A4」**数据资产级不可达**"
        "（无实测锚点；Raman 通道已否证） | L2 | 🔴 **R164 新增**（口径待裁决） |\n",
        "| D-88 | GOAL §2 目标量「菌丝区组成 A0/A1/A3/A4」**双重不可达**："
        "结构不可辨识（观测算子 rank≤1 / nullity≥3）+ 数据资产级不可验证"
        "（无实测锚点；Raman 已否证） | L2 | 🔴 **R164 新增 / R165 升级**"
        "（R164-7 数值证明；口径待裁决 R164-V5） |\n",
        "LED-TBL-D88", "R164 新增 / R165 升级**（R164-7 数值证明")

    # --- 纪律 32（R164-6 要求新增一条） ---
    replace_once(
        rel,
        "必须能识别上下文（否定词邻域 / 整块语义），或改用**产物级**证据（产物是否存在、\n"
        "    字段是否被消费）而非文本子串。\n",
        "必须能识别上下文（否定词邻域 / 整块语义），或改用**产物级**证据（产物是否存在、\n"
        "字段是否被消费）而非文本子串。\n"
        "\n"
        "32. **「不可辨识」与「不可验证」必须分层证明，且机制表述要先核对源码** —— R164 只登记了\n"
        "    「37 列无 A 组实测列 ⇒ 数据资产级不可验证」，这是**换数据即可解**的资产缺陷；\n"
        "    R165（R164-7）才补上观测算子层的数值秩亏证据（`H_assim` rank=0 / nullity=4、\n"
        "    `H_report` rank=1 / nullity=3）⇒ **只增加同类数据不改变列空间秩**，才是结构不可辨识。\n"
        "    同时本轮纠正了治理层沿用多轮的机制表述：`dy[9]` 只依赖 **A0 单室**，不是总生物量；\n"
        "    且动力学层对分室比例敏感（`dP_dt` 等非零）⇒ 不可辨识的落点只能是**观测算子 H**，\n"
        "    不能写成「模型不敏感」或「所有输出 Δ=0」。⇒ 凡登记「不可辨识」，必须给出\n"
        "    **H 的秩 / 零空间数值**与**反向判别力**；凡引用「机制」，必须给出源码行号并逐字核对。\n",
        "LED-DISC32", "32. **「不可辨识」与「不可验证」必须分层证明")


# --------------------------------------------------------------------------
# R164-4 / R164-2：签核单新增 B-18 / B-19
# --------------------------------------------------------------------------
def edits_signoff(ev: dict) -> None:
    rel = "docs/m5_review_signoff.md"
    insert_after_prefix(
        rel,
        "| **B-14** |",
        [
            "| **B-18** | **PH4 验收项转已知边界（R164-4 / D-54）** | `deepening_plan` PH4 规定"
            "「advise_control + 窗口包络采样」为运行期咨询域；D-57 判决性实验证明 "
            "`sd`/`mean_P`/`Y_sP` 响应是**硬跳变**（跨度恒 99.8–101.5 pp），两侧无可用梯度区分度 | "
            "**D-57 / B-9 / `runs/r157_bistab_escape.json`** | **运行期连续调控（梯度型闭环）封死**；"
            "**开环设定点标定保留**但落点相对精度 **1e−04…1e−05**（标定级非控制级）"
            " ⇒ PH4 的「运行期调控」验收项**转已知边界**，不再作为待办；若要恢复须走结构改动路线"
            "（L3，需另行授权）。三处口径一致：`docs/roadmap_next.md` §8.6 / "
            "`docs/r157_debt_ledger.md` D-54 / 本单 B-18 |",
            "| **B-19** | **PH1 的 28 批验证集从未留出（D-89，R164-2）** | `deepening_plan` PH1 规定"
            "「88 = 60 训练 + 28 验证分层」，`data/processed/batch_pool.json` 确实按 "
            "`stratify(fault, yield_quartile)` 落了 60/28/12；但 "
            "`candidate/indpensim/v0.1/hier_est.py:276` 执行 "
            "`batch_list = bp[\"train\"] + bp[\"validation\"]` ⇒ 28 批验证集被并入训练，从未留出 | "
            "`docs/goal_backtrace_check_v4.md` §三；`hier_est.py:276` | **已知边界**：PH1 验收"
            "「先验分布与 MATLAB 生成机制一致性」的独立性前提不成立，σ̂ 统一改引 **MAP 散布上界**"
            "（不含群体先验）且**不**声称有独立验证；**禁止**引用「验证集」作为任何泛化性论据。"
            "若要闭合须恢复 28 批留出并在留出集复算（R164-2 已改写口径，真正闭合属 V1+） |",
        ],
        "SIGN-B18-B19", "**B-18** | **PH4 验收项转已知边界")


# --------------------------------------------------------------------------
# R164-2/3/4/6：路线图判据勘误 + 完成标注
# --------------------------------------------------------------------------
def edits_roadmap(ev: dict) -> None:
    rel = "docs/roadmap_next.md"
    for tag, old, new, marker in [
        ("RM-164-2", "| **R164-2** | **PH1 验收口径改写**（D-89 关联） |",
         "| **R164-2** ✅ **R165 完成** | **PH1 验收口径改写**（D-89 关联） |",
         "R164-2** ✅ **R165 完成"),
        ("RM-164-3", "| **R164-3** | **`deepening_plan` 自身勘误**（4 处陈述漂移） |",
         "| **R164-3** ✅ **R165 完成** | **`deepening_plan` 自身勘误**（4 处陈述漂移） |",
         "R164-3** ✅ **R165 完成"),
        ("RM-164-4", "| **R164-4** | **PH4 验收项转已知边界** |",
         "| **R164-4** ✅ **R165 完成** | **PH4 验收项转已知边界** |",
         "R164-4** ✅ **R165 完成"),
        ("RM-164-6", "| **R164-6** | **台账状态滞后清理** |",
         "| **R164-6** ✅ **R165 完成** | **台账状态滞后清理** |",
         "R164-6** ✅ **R165 完成"),
    ]:
        replace_once(rel, old, new, tag, marker)

    replace_once(
        rel,
        "| **R164-7** | **菌丝区组成的部分可辨识性研究**（D-88 前置） | 给出结论："
        "黏度只约束**总生物量** ⇒ A0/A1/A3/A4 **不可分离**；**须先证明再登记**，"
        "避免把「不可验证」与「不可辨识」混为一谈 | 半天 |\n",
        "| **R164-7** | **菌丝区组成的部分可辨识性研究**（D-88 前置）✅ **R165 完成** | "
        "~~黏度只约束**总生物量**~~ ⇒ **R165 勘误**：`dy[9]` 只依赖 **A0 单室**、"
        "动力学层对分室敏感；正确判据是**观测算子结构秩亏**（`H_assim` rank=0 / nullity=4、"
        "`H_report` rank=1 / nullity=3）+ 反向判别力，**11/11 PASS**"
        "（`docs/r165_mycelium_identifiability.md`）。避免把「不可验证」（数据资产层）与"
        "「不可辨识」（观测设计层）混为一谈 | 半天 |\n",
        "RM-164-7", "正确判据是**观测算子结构秩亏**")


# --------------------------------------------------------------------------
# D-88 / X_offline 口径勘误（goal_backtrace_check_v4）
# --------------------------------------------------------------------------
def edits_v4(ev: dict) -> None:
    rel = "docs/goal_backtrace_check_v4.md"
    replace_once(
        rel,
        "| `X_offline` | 走 `ident_map` 特殊分支（映射到 A 组生物量） | 化验 |\n",
        "| `X_offline` | 走 `ident_map` 特殊分支（映射到 A 组生物量）—— "
        "**⚠ R165 勘误**：`observe.py:243-257` 中 `ident_map[\"X_offline\"]=None` 且 "
        "`if ch == \"X_offline\": continue` ⇒ 该通道被**完全排除同化**，A 组从未被任何观测更新 | "
        "化验（仅事后上报 `X_sum`/`X_sd`，不进 `act_obs`） |\n",
        "V4-Xoffline", "R165 勘误**：`observe.py:243-257`")
    replace_once(
        rel,
        "| **A0 / A1 / A3 / A4** | 仅经 `X_offline` 间接约束 | ⇒ 四个形态状态**不可分离** |\n",
        "| **A0 / A1 / A3 / A4** | **同化层 rank=0**（`H_assim` 无任何 A 组索引）；"
        "`X_offline` 被排除同化；仅 `records` 事后上报 `X_sum`/`X_sd` ⇒ "
        "`H_report` rank=1 / nullity=3 | ⇒ 四个形态状态**结构不可辨识**"
        "（`docs/r165_mycelium_identifiability.md` 11/11 PASS），不是「仅经 X_offline 间接约束」 |\n",
        "V4-Agroup", "同化层 rank=0**（`H_assim` 无任何 A 组索引）")
    replace_once(
        rel,
        "黏度方程只约束**总生物量** `a_0^(1/3)`（R129r 已证该口径与实测的线性关系不匹配）",
        "**R165 勘误**：引擎 `dy[9]` 只依赖 **A0 单室**（`model.py:660-674`），"
        "既非总生物量亦非 `total_X`；「黏度≈1.77·X+12.4」只是 R129r 实测经验关系"
        "（相关性 0.81–0.85），二者不等价",
        "V4-D88-find", "R165 勘误**：引擎 `dy[9]` 只依赖")
    replace_once(
        rel,
        "| 边界 | 本轮**不**新增观测通道、**不**改引擎；**不**宣称「菌丝区组成不可辨识」—— "
        "准确表述是「**在本项目可用数据资产下不可验证**」（若有含形态测量的新数据，结论可能改变） |\n",
        "| 边界 | **R165 升级为双重结论**：① **结构不可辨识（观测设计层）** —— 现有观测算子 "
        "`H_assim` rank=0 / nullity=4、`H_report` rank=1 / nullity=3，只增加同类数据不改变列空间秩；"
        "② **数据资产级不可验证** —— 37 列无 A 组实测 + Raman 被 D-71 否证，换含形态测量的数据可解。"
        "两者边界是**是否改变 H 的列空间**。本轮仍**不**新增观测通道、**不**改引擎"
        "（详见 `docs/r165_mycelium_identifiability.md`） |\n",
        "V4-D88-bound", "R165 升级为双重结论**：① **结构不可辨识")
    replace_once(
        rel,
        "③ 中期可做**部分可辨识性**研究：4 个形态状态 vs 1 个黏度标量 ⇒ 最多给总量约束，"
        "**不可分离**（须先证明这一点再登记，避免把「不可验证」与「不可辨识」混为一谈）",
        "③ **部分可辨识性研究已由 R164-7 / R165 完成并给出数值证明**（观测算子结构秩亏 "
        "11/11 PASS；黏度不是总量约束，动力学层对分室敏感）",
        "V4-D88-sugg", "部分可辨识性研究已由 R164-7 / R165 完成")
    replace_once(
        rel,
        "| 黏度只约束总生物量 | `candidate/indpensim/v0.1/model.py` 黏度方程 `a_0^(1/3)`；"
        "R129r 实测相关性 0.81–0.85 |\n",
        "| ~~黏度只约束总生物量~~ **R165 勘误：黏度生成项只依赖 A0 单室** | "
        "`model.py:660-674` `dy[9] = vis_scale·3·a_0_pos**(1/3)·…`；`total_X` 定义在 "
        "`model.py:315` 但**不在黏度方程里**；R129r 的 `vis≈1.77·X+12.4`"
        "（相关性 0.81–0.85）是另一条实测经验关系 |\n",
        "V4-visrow", "R165 勘误：黏度生成项只依赖 A0 单室")


# --------------------------------------------------------------------------
# state.yaml（CRLF）：D-88 升级 + D-76 联动销号
# --------------------------------------------------------------------------
def edits_state(ev: dict) -> None:
    rel = "state.yaml"
    replace_once(
        rel,
        "黏度只约束总生物量；Raman 通道已被 D-71 否证 ⇒ 两条候选观测通道同时关闭 ⇒ "
        "口径待裁决（路线图 R164-V5）",
        "**R165 勘误/升级**：引擎 `dy[9]` 只依赖 **A0 单室**（非总生物量）；"
        "R164-7 证明现有观测算子对 A 组 `H_assim` rank=0 / nullity=4、"
        "`H_report` rank=1 / nullity=3 ⇒ **结构不可辨识（观测设计层）**；"
        "V3 37 列无 A 组实测 + Raman 被 D-71 否证 ⇒ **数据资产级不可验证**。"
        "两层边界见 `docs/r165_mycelium_identifiability.md`（11/11 PASS）；"
        "口径待裁决（路线图 R164-V5）",
        "STATE-D88", "R165 勘误/升级**：引擎 `dy[9]`")
    replace_once(
        rel,
        "- R160/D-76 README 传播了 R158 已被 D-74 撤回的 A2 结论（README 第 165 至 166 行仍写 "
        "A2 严格支配与优先做两点校准）⇒ R159 治理层更新清单漏了 README ⇒ 须改写",
        "- ✅ R165 关闭 D-76：按纪律 31 逐行上下文复核，README:167-172 是「引用 R158 原话并当场撤回」"
        "的否定式引用（:168 引原话、:169 起撤回并给出剔除退化批后 A2 20.47% 劣于 C0 10.29%），"
        "非残留传播 ⇒ 纯子串 grep 误报；README 该段不改（保留证伪链原始记录），"
        "终检判据改为上下文判定",
        "STATE-D76", "R165 关闭 D-76")


def edits_round_labels(ev: dict) -> None:
    """给新增的边界/销号段落补 R165 轮次标识（回溯可追溯性，纪律 30）。

    独立成组：既能在「已应用」的文件上单独执行，也能让脚本从零跑一遍得到同一结果。
    """
    replace_once(
        "README.md",
        "**已关闭（D-2 / R142）**", "**已关闭（D-2 / R142 / R165）**",
        "LBL-README", "D-2 / R142 / R165")
    replace_once(
        "docs/m5_review_signoff.md",
        "**PH4 验收项转已知边界（R164-4 / D-54）**",
        "**PH4 验收项转已知边界（R164-4 / D-54 / R165）**",
        "LBL-B18", "R164-4 / D-54 / R165")
    replace_once(
        "docs/m5_review_signoff.md",
        "**PH1 的 28 批验证集从未留出（D-89，R164-2）**",
        "**PH1 的 28 批验证集从未留出（D-89，R164-2 / R165）**",
        "LBL-B19", "R164-2 / R165")


ALL_GROUPS = [
    edits_deepening_plan, edits_ph2_report, edits_readme,
    edits_ledger, edits_signoff, edits_roadmap, edits_v4, edits_state,
    edits_round_labels,
]


def file_hashes() -> dict:
    out = {}
    for rel in ["docs/deepening_plan.md", "docs/ph2_acceptance_report.md", "README.md",
                "docs/r157_debt_ledger.md", "docs/m5_review_signoff.md",
                "docs/roadmap_next.md", "docs/goal_backtrace_check_v4.md", "state.yaml"]:
        out[rel] = hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()[:16]
    return out


def main() -> int:
    global DRY
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="实际写入（默认 dry-run）")
    ap.add_argument("--json", action="store_true", help="落 runs/r165_governance_text.json")
    args = ap.parse_args()
    DRY = not args.apply

    ev = load_evidence()
    before = file_hashes()
    for fn in ALL_GROUPS:
        fn(ev)
    after = file_hashes()

    leak = [] if DRY else [k for k in before if before[k] != after[k]]
    if DRY and leak:
        ERRORS.append(f"dry-run 泄漏写文件: {leak}")
    if DRY and before != after:
        ERRORS.append("dry-run 前后文件哈希不一致（严重）")

    n_changed = sum(1 for r in RECORDS if r["status"] == "changed")
    n_skip = sum(1 for r in RECORDS if r["status"].startswith("skip"))
    n_err = sum(1 for r in RECORDS if r["status"].startswith("ERROR"))
    verdict = "PASS" if (not ERRORS and n_err == 0) else "FAIL"

    print(f"== R165 治理文本四项（R164-2/3/4/6）== mode={'APPLY' if not DRY else 'DRY-RUN'}")
    print(f"证据：RMSE {ev['rmse_pct']}% / {ev['within5']}/{ev['n']}（{ev['zero_regression_ref']}）")
    print(f"编辑项 {len(RECORDS)}：changed={n_changed}  skip={n_skip}  error={n_err}")
    if DRY:
        print(f"dry-run 零泄漏自检：{'PASS（8 个目标文件哈希全未变）' if before == after else 'FAIL'}")
    for r in RECORDS:
        if r["status"].startswith("ERROR"):
            print(f"  [ERROR] {r['tag']} {r['status']} {r['file']}")
    for e in ERRORS:
        print(f"  [ERR] {e}")
    print(f"verdict = {verdict}")

    if args.json and not DRY:
        (RUNS / "r165_governance_text.json").write_text(
            json.dumps({"mode": "apply", "verdict": verdict, "n_changed": n_changed,
                        "n_skip": n_skip, "n_error": n_err, "evidence": ev,
                        "records": RECORDS, "errors": ERRORS},
                       ensure_ascii=False, indent=1), encoding="utf-8")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
