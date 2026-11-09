# -*- coding: utf-8 -*-
"""
R165 终检（常驻可复跑、只读）

覆盖：
  A. 探针产物判据   —— R164-1 MCP 工具补齐 / R164-5 CO2 卡死检测器 / R164-7 菌丝可辨识性
  B. 治理文本四项   —— R164-2/3/4/6 落地 + 幂等（内存 dry-run，零写入）
  C. 治理层同步     —— 契约 v1.95 / 台账 D-90 / 签核单 R-15 / README / INDEX / state / 记忆 / 报告 / §8.7
  D. 闸门与文档卫生 —— 零回归 / pytest / 换行风格 / YAML / 数值核心哈希 / 纪律 31 上下文判定

只读性：本脚本不写任何文件（--json 除外，仅写 runs/r165_final_check.json 证据）。
用法：
    py tools/r165_final_check.py
    py tools/r165_final_check.py --json
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def rp(*parts):
    return os.path.join(ROOT, *parts)


def read_text(rel):
    with io.open(rp(rel), "r", encoding="utf-8", newline="") as f:
        return f.read()


def read_bytes(rel):
    with io.open(rp(rel), "rb") as f:
        return f.read()


def jload(rel, default=None):
    p = rp(rel)
    if not os.path.exists(p):
        return default
    try:
        with io.open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


CHECKS = []


def check(name, ok, got=None, expect=None, detail=None):
    CHECKS.append({"name": name, "ok": bool(ok), "got": got,
                   "expect": expect, "detail": detail})
    return bool(ok)


def _flag(c):
    """兼容 `pass` / `ok` 两种产物字段。"""
    if c.get("pass") is not None:
        return bool(c.get("pass"))
    return bool(c.get("ok"))


def _cid(c):
    return "%s %s" % (c.get("id", ""), c.get("name", c.get("desc", "")))


def sha16(rel):
    return hashlib.sha256(read_bytes(rel)).hexdigest()[:16]


# --------------------------------------------------------------------------
# A. 探针产物判据
# --------------------------------------------------------------------------
def section_a():
    p_co2 = "runs/r165_co2_stuck_detector.json"
    p_mcp = "runs/r165_mcp_tools_probe.json"
    p_myc = "runs/r165_mycelium_identifiability.json"
    d_co2, d_mcp, d_myc = jload(p_co2), jload(p_mcp), jload(p_myc)

    check("A0 三个 R165 探针产物齐备",
          all(x is not None for x in (d_co2, d_mcp, d_myc)),
          [os.path.exists(rp(p)) for p in (p_co2, p_mcp, p_myc)], "全在")

    if d_co2:
        check("A1 CO2 检测器 verdict PASS / 11/11",
              d_co2.get("verdict") == "PASS" and d_co2.get("n_pass") == d_co2.get("n_checks") == 11,
              "%s %s/%s" % (d_co2.get("verdict"), d_co2.get("n_pass"), d_co2.get("n_checks")),
              "PASS 11/11")
        cs = d_co2.get("checks", [])
        check("A2 CO2 逐条判据全 True", len(cs) == 11 and all(_flag(c) for c in cs),
              "%d/%d" % (sum(1 for c in cs if _flag(c)), len(cs)), "11/11")
        bad = [_cid(c) for c in cs if not _flag(c)]
        check("A3 CO2 无 FAIL 判据", not bad, bad or "无", "无")
        th = d_co2.get("thresholds", {})
        check("A4 CO2 双阈值由多轮寻优给出（exact 6.0 / near 32.0 / std_frac 0.010）",
              th.get("exact_run_h") == 6.0 and th.get("near_flat_run_h") == 32.0
              and abs(float(th.get("std_frac", 0)) - 0.010) < 1e-9,
              th, "6.0 / 32.0 / 0.010")
        by_id = {c.get("id"): c for c in cs}
        check("A5 CO2 零信息对照 0/20 触发 + 正向 5/5 检出 + 其它故障 0/15 误触发",
              all(_flag(by_id[k]) for k in ("D1", "D2", "D3") if k in by_id),
              {k: (by_id[k].get("got") or by_id[k].get("value"))
               for k in ("D1", "D2", "D3") if k in by_id}, "全 True（D1/D2/D3）")
        cf = d_co2.get("confusion", {})
        check("A6 CO2 四格双向（TP>0 且 TN>0，判据不恒真不恒假）",
              len(cf.get("TP", [])) > 0 and len(cf.get("TN", [])) > 0,
              {"TP": len(cf.get("TP", [])), "FN": len(cf.get("FN", [])),
               "TN": len(cf.get("TN", [])), "FP": len(cf.get("FP", []))}, "TP>0 / TN>0")
        d8 = by_id.get("D8", {})
        v8 = d8.get("got") or d8.get("value") or {}
        b8 = v8.get("enkf_baseline", {})
        check("A7 CO2 组合增益实测（EnKF OR 检测器 TP 10→14 / FN 5→1 / TN、FP 不退化）",
              _flag(d8) and v8.get("TP") == 14 and b8.get("TP") == 10
              and v8.get("FN") == 1 and b8.get("FN") == 5
              and v8.get("TN") == b8.get("TN") and v8.get("FP", 99) <= b8.get("FP", -1),
              v8, "TP 10→14 / FN 5→1 / TN=4 / FP≤1")
        d5 = by_id.get("D5", {})
        v5 = d5.get("got") or d5.get("value") or {}
        check("A8 CO2 留一交叉验证 5 折全通过（样本外定阈值）",
              _flag(d5) and v5.get("folds") == 5 and v5.get("pass") == 5,
              v5, "5/5")
        d7 = by_id.get("D7", {})
        v7 = d7.get("got") or d7.get("value") or {}
        check("A9 CO2 只读性：40 例输入 DataFrame 零改写（D7）",
              _flag(d7) and v7.get("n") == 40 and v7.get("violations") == 0,
              v7, "40 例 / 0 违规")

    if d_mcp:
        check("A10 MCP 探针 verdict PASS / 12/12",
              d_mcp.get("verdict") == "PASS" and d_mcp.get("n_pass") == d_mcp.get("n_checks") == 12,
              "%s %s/%s" % (d_mcp.get("verdict"), d_mcp.get("n_pass"), d_mcp.get("n_checks")),
              "PASS 12/12")
        cs = d_mcp.get("checks", [])
        check("A11 MCP 逐条判据全 True", len(cs) == 12 and all(_flag(c) for c in cs),
              "%d/%d" % (sum(1 for c in cs if _flag(c)), len(cs)), "12/12")
        tc = d_mcp.get("tool_count", {})
        check("A12 MCP 工具数 12 → 14，新增恰为两个",
              tc.get("before") == 12 and tc.get("after") == 14
              and sorted(tc.get("added", [])) == ["discover_residual", "observe_online"],
              tc, "12→14 / 两个指定工具")
        check("A13 MCP 既有工具逐字未变 + solver_info 逐位一致（M2/M4）",
              all(_flag(c) for c in cs if c.get("id") in ("M2", "M4")),
              {c.get("id"): _flag(c) for c in cs if c.get("id") in ("M2", "M4")}, "全 True")
        check("A14 MCP 双向判别力（无 θ 批降级 / 有 θ 批出结构，M5–M8）",
              all(_flag(c) for c in cs if c.get("id") in ("M5", "M6", "M7", "M8")),
              {c.get("id"): _flag(c) for c in cs if c.get("id") in ("M5", "M6", "M7", "M8")},
              "全 True")
        check("A15 MCP 菌丝分室恒标 identifiable=False（M11）",
              all(_flag(c) for c in cs if c.get("id") == "M11"),
              {c.get("id"): _flag(c) for c in cs if c.get("id") == "M11"}, "True")

    if d_myc:
        check("A16 菌丝证明 verdict PASS / 11/11",
              d_myc.get("verdict") == "PASS" and d_myc.get("n_pass") == d_myc.get("n_checks") == 11,
              "%s %s/%s" % (d_myc.get("verdict"), d_myc.get("n_pass"), d_myc.get("n_checks")),
              "PASS 11/11")
        cs = d_myc.get("checks", [])
        check("A17 菌丝逐条判据全 True", len(cs) == 11 and all(_flag(c) for c in cs),
              "%d/%d" % (sum(1 for c in cs if _flag(c)), len(cs)), "11/11")
        oo = d_myc.get("observation_operator", {})
        ha, hr = oo.get("H_assim", {}), oo.get("H_report", {})
        check("A18 H_assim rank=0 / nullity=4；H_report rank=1 / nullity=3",
              ha.get("rank") == 0 and ha.get("nullity") == 4
              and hr.get("rank") == 1 and hr.get("nullity") == 3,
              {"H_assim": [ha.get("rank"), ha.get("nullity")],
               "H_report": [hr.get("rank"), hr.get("nullity")]}, "0/4 与 1/3")
        check("A19 零空间响应为 0 且非保和正例严格单调（判据双向）",
              all(_flag(c) for c in cs if c.get("id") in ("I2", "I4", "I5")),
              {c.get("id"): _flag(c) for c in cs if c.get("id") in ("I2", "I4", "I5")}, "全 True")
        ca = d_myc.get("clamp_audit", {})
        check("A20 钳位审计全 0（秩亏非 guards 伪影）",
              all(ca.get(k, 1) == 0 for k in
                  ("a0_pos_clamped", "guards_invoked", "nonfinite")),
              ca, "全 0")
        # I10：数值核心 4 文件哈希与当前磁盘一致
        i10 = next((c for c in cs if c.get("id") == "I10"), {})
        recorded = (i10.get("value") or {}).get("source_sha256_16", {})
        now = {k: sha16(k) for k in recorded}
        check("A21 只读：4 个引擎源码文件哈希与证明时逐位一致",
              bool(recorded) and recorded == now,
              {"recorded": recorded, "now": now}, "逐位一致")
        check("A22 三份产物 round 字段均为 R165",
              all(d.get("round") == "R165" for d in (d_co2, d_mcp, d_myc) if d),
              [d.get("round") for d in (d_co2, d_mcp, d_myc) if d], "全 R165")


# --------------------------------------------------------------------------
# B. 治理文本四项 + 幂等（内存 dry-run，零写入）
# --------------------------------------------------------------------------
def section_b():
    g = jload("runs/r165_governance_text.json")
    check("B0 治理文本脚本产物存在且 PASS / 46 项 / 0 error",
          g is not None and g.get("verdict") == "PASS" and g.get("n_error") == 0,
          None if g is None else {k: g.get(k) for k in ("verdict", "n_changed", "n_skip", "n_error")},
          "PASS / error=0")
    if g:
        check("B1 治理文本 46 项编辑全部有记录且无 ERROR",
              len(g.get("records", [])) == 46
              and not any(r["status"].startswith("ERROR") for r in g["records"]),
              len(g.get("records", [])), 46)
        ev = g.get("evidence", {})
        check("B2 数字数据驱动（RMSE/86 从 runs/ 读取，不手写）",
              ev.get("rmse_pct") == "2.345" and ev.get("within5") == 86 and ev.get("n") == 86,
              {k: ev.get(k) for k in ("rmse_pct", "within5", "n", "zero_regression_ref")},
              "2.345 / 86 / 86")

    dp = read_text("docs/deepening_plan.md")
    check("B3 R164-3① 头部标注「历史快照 / 不代表现行状态」",
          "R165 勘误（2026-11-06）" in dp and "历史方案与执行快照" in dp,
          "R165 勘误（2026-11-06）" in dp, True)
    check("B4 R164-2 PH1 显式登记 28 批验证集未留出（D-89）",
          "28 批验证集从未被留出" in dp and "训练集内选择" in dp,
          "28 批验证集从未被留出" in dp, True)
    check("B5 R164-2 PH1 σ̂ 统一改引 MAP 散布上界 + 注明不含群体先验",
          "MAP 散布上界" in dp and "不含群体先验" in dp and "R142 已证伪" in dp,
          "MAP 散布上界" in dp, True)
    check("B6 R164-3② PH2 投票口径勘误为 88 有效批 / 12 站 / 负向 5",
          "88 有效批 / A_t1 命中 12 站 / 负向 5" in dp,
          "88 有效批 / A_t1 命中 12 站 / 负向 5" in dp, True)
    check("B7 R164-3③ σ̂「8.6% 偏差 = 验证通过」加 R142 证伪批注",
          "原文「验证通过」已由 R142 证伪" in dp and "R165 勘误（R142 / D-28）" in dp,
          "原文「验证通过」已由 R142 证伪" in dp, True)
    check("B8 R164-4 PH4 转已知边界（deepening_plan）",
          "PH4 结论（R165 补，R164-4）" in dp and "运行期连续调控（梯度型闭环）封死" in dp,
          "PH4 结论（R165 补，R164-4）" in dp, True)

    ph2 = read_text("docs/ph2_acceptance_report.md")
    check("B9 R164-3④ ph2 报告 §五回填 RMSE 2.345% / 86/86（数字数据驱动）",
          "R165 回填" in ph2 and "2.345%" in ph2 and "86/86" in ph2,
          {"rmse": "2.345%" in ph2, "ratio": "86/86" in ph2}, True)
    check("B10 ph2 报告同时修 :48 σ̂ 滞后表述",
          "R165 勘误（R142）" in ph2 and "MAP 散布上界" in ph2,
          "R165 勘误（R142）" in ph2, True)

    rdm = read_text("README.md")
    check("B11 R164-2 README :74 DL σ̂ 由「L2 阻断」改为已关闭（R165）",
          "已关闭（D-2 / R142 / R165）" in rdm and "| DL σ̂ 定标 | 未定（D-2） | L2 阻断 |" not in rdm,
          "已关闭（D-2 / R142 / R165）" in rdm, True)

    led = read_text("docs/r157_debt_ledger.md")
    check("B12 R164-6 D-66/67/68/76 四处标题销号",
          all(s in led for s in (
              "D-66　缺 `pytest.ini` / `conftest.py`　✅",
              "✅ **R165 关闭（工具侧已修",
              "✅ **R165 关闭（R156 `ph_fix`",
              "✅ **R165 关闭（上下文判定")),
          [s in led for s in ("D-66　缺 `pytest.ini` / `conftest.py`　✅",
                              "✅ **R165 关闭（工具侧已修",
                              "✅ **R165 关闭（R156 `ph_fix`",
                              "✅ **R165 关闭（上下文判定")], "全 True")
    check("B13 R164-6 总表四行状态同步销号（无 🔴 残留）",
          all(s in led for s in ("✅ **R165 关闭**（与 D-81 重复",
                                 "✅ **R165 关闭**（工具侧已修 + 纪律固化）",
                                 "✅ **R165 关闭**（R156 `ph_fix` 机制侧修复）",
                                 "✅ **R165 关闭**（纪律 31 上下文判定")),
          "见总表 D-66/67/68/76 行", "全 ✅")
    check("B14 R164-6 新增纪律 32（编号连续、非重复）",
          led.count("32. **「不可辨识」与「不可验证」必须分层证明") == 1
          and "31. **文本状态判定" in led,
          led.count("32. **「不可辨识」与「不可验证」必须分层证明"), 1)
    check("B15 D-88 升级为双重结论（结构不可辨识 + 数据资产级不可验证）",
          "R165 升级为双重结论" in led and "H_assim` 对 A 组 **rank=0 / nullity=4**" in led
          and "R164 新增 / R165 升级" in led,
          "R165 升级为双重结论" in led, True)
    check("B16 D-88 机制表述勘误（dy[9] 只依赖 A0 单室）",
          "只依赖 A0 单室" in led and "R165 勘误**：引擎黏度生成项" in led,
          "只依赖 A0 单室" in led, True)
    check("B17 R164-4 D-54 三处口径统一注记",
          "R165 / R164-4 口径统一" in led and "B-18" in led,
          "R165 / R164-4 口径统一" in led, True)

    sg = read_text("docs/m5_review_signoff.md")
    check("B18 签核单新增 B-18（PH4 已知边界）与 B-19（D-89 已知边界）",
          "**B-18**" in sg and "**B-19**" in sg and "R164-4 / D-54 / R165" in sg,
          {"B18": "**B-18**" in sg, "B19": "**B-19**" in sg}, "全在")

    rm = read_text("docs/roadmap_next.md")
    check("B19 路线图 R164-2/3/4/6 完成标注齐备",
          all(("R164-%d** ✅ **R165 完成" % i) in rm for i in (2, 3, 4, 6)),
          [("R164-%d** ✅ **R165 完成" % i) in rm for i in (2, 3, 4, 6)], "全 True")
    check("B20 路线图 R164-7 判据勘误为观测算子结构秩亏",
          "正确判据是**观测算子结构秩亏**" in rm and "~~黏度只约束**总生物量**~~" in rm,
          "正确判据是**观测算子结构秩亏**" in rm, True)

    v4 = read_text("docs/goal_backtrace_check_v4.md")
    check("B21 v4 回溯稿 X_offline 口径勘误（完全排除同化 / rank=0）",
          "R165 勘误**：`observe.py:243-257`" in v4 and "同化层 rank=0" in v4,
          "R165 勘误**：`observe.py:243-257`" in v4, True)
    check("B22 v4 回溯稿黏度口径勘误 + 证据表行勘误",
          "R165 勘误：黏度生成项只依赖 A0 单室" in v4 and "R165 勘误**：引擎 `dy[9]`" in v4,
          "R165 勘误：黏度生成项只依赖 A0 单室" in v4, True)

    st = read_text("state.yaml")
    check("B23 state.yaml D-88 升级双重结论 + D-76 销号",
          "R165 勘误/升级" in st and "R165 关闭 D-76" in st,
          {"d88": "R165 勘误/升级" in st, "d76": "R165 关闭 D-76" in st}, "全 True")

    # 幂等：在内存里以 DRY=True 重跑治理脚本，必须 0 changed（纯只读）
    try:
        spec = importlib.util.spec_from_file_location(
            "r165_govtext", rp("tools", "r165_governance_text.py"))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m.DRY = True
        m.RECORDS.clear()
        m.ERRORS.clear()
        ev = m.load_evidence()
        for fn in m.ALL_GROUPS:
            fn(ev)
        changed = [r["tag"] for r in m.RECORDS if r["status"] == "changed"]
        check("B24 治理脚本幂等（内存 dry-run 重跑 0 changed）",
              not changed and not m.ERRORS,
              {"changed": changed, "errors": m.ERRORS}, "0 changed / 0 error")
    except Exception as e:                                    # noqa: BLE001
        check("B24 治理脚本幂等（内存 dry-run 重跑 0 changed）",
              False, repr(e), "0 changed")


# --------------------------------------------------------------------------
# C. 治理层同步（R165 轮次登记）
# --------------------------------------------------------------------------
def section_c():
    gu = jload("runs/r165_governance_update.json")
    check("C0 治理层同步脚本产物存在且 PASS",
          gu is not None and gu.get("verdict") == "PASS" and gu.get("n_error") == 0,
          None if gu is None else {k: gu.get(k) for k in
                                   ("verdict", "n_changed", "n_skip", "n_error")},
          "PASS / error=0")
    if gu:
        check("C1 治理层同步逐项无 ERROR",
              not any(r["status"].startswith("ERROR") for r in gu.get("records", [])),
              len(gu.get("records", [])), "无 ERROR")

    ec = read_text("ENGINE_CONTRACT.md")
    check("C2 契约升至 v1.95 且登记 R165",
          "v1.95" in ec and "R165" in ec,
          {"v195": "v1.95" in ec, "r165": "R165" in ec}, "全 True")
    led = read_text("docs/r157_debt_ledger.md")
    check("C3 台账登记 D-90（R165 轮次）",
          "D-90" in led and "R165" in led, "D-90" in led, True)
    sg = read_text("docs/m5_review_signoff.md")
    check("C4 签核单新增 R-15（R165 收口）",
          "**R-15**" in sg and "R165" in sg, "**R-15**" in sg, True)
    rdm = read_text("README.md")
    # 不能用纯子串「R165」（勘误段落里也有）⇒ 要求同时出现三个 R165 产物名（纪律 31）
    check("C5 README 登记 R165 轮次段（含三个探针产物名，非勘误文字误报）",
          all(t in rdm for t in ("r165_co2_stuck_detector", "r165_mcp_tools_probe",
                                 "r165_mycelium_identifiability")) and "R165" in rdm,
          [t in rdm for t in ("r165_co2_stuck_detector", "r165_mcp_tools_probe",
                              "r165_mycelium_identifiability")], "全在")
    idx = read_text("tools/INDEX.md")
    check("C6 tools/INDEX.md 登记 5 个 R165 工具",
          all(t in idx for t in ("r165_co2_stuck_detector.py", "r165_mcp_tools_probe.py",
                                 "r165_mycelium_identifiability.py",
                                 "r165_governance_text.py", "r165_governance_update.py",
                                 "r165_final_check.py")),
          [t in idx for t in ("r165_co2_stuck_detector.py", "r165_mcp_tools_probe.py",
                              "r165_mycelium_identifiability.py", "r165_governance_text.py",
                              "r165_governance_update.py", "r165_final_check.py")], "全 True")
    # 不能用纯子串「R165」（D-88/D-76 勘误条目里也有）⇒ 要求 open_questions 里
    # 存在以「R165」开头的**独立条目**（纪律 31：识别上下文）
    try:
        import yaml
        oq = yaml.safe_load(read_text("state.yaml")).get("open_questions", [])
        r165_items = [q for q in oq if isinstance(q, str) and q.lstrip("-# ✅🔴🟡⏸ ").startswith("R165")]
        check("C7 state.yaml open_questions 新增独立 R165 轮次条",
              len(r165_items) >= 1, r165_items[:2], "≥1 条")
    except Exception as e:                                    # noqa: BLE001
        check("C7 state.yaml open_questions 新增独立 R165 轮次条", False, repr(e), "≥1 条")
    mem = rp(".workbuddy", "memory", "2026-11-06.md")
    check("C8 工作记忆 2026-11-06.md 已落 R165 收口",
          os.path.exists(mem) and "R165" in io.open(mem, encoding="utf-8").read(),
          os.path.exists(mem), True)
    rep = rp("docs", "r165_round_report.md")
    ok_rep = os.path.exists(rep)
    check("C9 主交付 docs/r165_round_report.md 存在且章节齐备",
          ok_rep and all(h in io.open(rep, encoding="utf-8").read()
                         for h in ("R165", "R164-1", "R164-5", "R164-7", "零回归", "下一阶段")),
          ok_rep, True)
    rm = read_text("docs/roadmap_next.md")
    check("C10 §8.7 下一阶段任务清单已输出（V1–V5 / 8–11 / 12 / 边界声明）",
          "8.7" in rm and "R164-V5" in rm and "R164-12" in rm
          and "GOAL §5" in rm.split("8.7")[-1],
          {"s87": "8.7" in rm, "v5": "R164-V5" in rm}, "全在")
    check("C11 备份目录 runs/_r165_backup 存在",
          os.path.isdir(rp("runs", "_r165_backup")),
          sorted(os.listdir(rp("runs", "_r165_backup")))[:6]
          if os.path.isdir(rp("runs", "_r165_backup")) else "无", "存在")


# --------------------------------------------------------------------------
# D. 闸门与文档卫生
# --------------------------------------------------------------------------
def section_d():
    zr_log = rp("runs", "_r165_zero_regression.log")
    ok = os.path.exists(zr_log)
    zr = io.open(zr_log, encoding="utf-8", errors="replace").read() if ok else ""
    check("D0 R165 零回归日志存在且含 max|Δ| = 0.00e+00",
          ok and "0.00e+00" in zr, "0.00e+00" in zr, True)
    zrj = jload("runs/r165_zero_regression.json")
    check("D1 R165 零回归产物 86 批逐位一致（max_abs_delta_pct=0 / 0 out of tol）",
          zrj is not None and zrj.get("summary", {}).get("max_abs_delta_pct") == 0.0
          and zrj.get("summary", {}).get("n_out_of_tol") == 0
          and zrj.get("summary", {}).get("n") == 86,
          None if zrj is None else zrj.get("summary"), "0.0 / 0 / 86")
    pt_log = rp("runs", "_r165_pytest.log")
    okp = os.path.exists(pt_log)
    pt = io.open(pt_log, encoding="utf-8", errors="replace").read() if okp else ""
    check("D2 R165 pytest 日志存在且含 passed（无 failed）",
          okp and "passed" in pt and "failed" not in pt,
          [l for l in pt.split("\n") if "passed" in l or "failed" in l][:2], "含 passed")

    # 换行风格
    styles = {"state.yaml": "CRLF", "docs/ph2_acceptance_report.md": "CRLF",
              "ENGINE_CONTRACT.md": "CRLF", "docs/deepening_plan.md": "LF",
              "README.md": "LF", "docs/r157_debt_ledger.md": "LF",
              "docs/m5_review_signoff.md": "LF", "docs/roadmap_next.md": "LF",
              "docs/goal_backtrace_check_v4.md": "LF"}
    bad = []
    for rel, want in styles.items():
        raw = read_bytes(rel)
        got = "CRLF" if b"\r\n" in raw else "LF"
        if got != want:
            bad.append((rel, got, want))
        if b"\r\r\n" in raw:
            bad.append((rel, "double-CR", "无"))
    check("D3 9 个治理文件换行风格原样保留且无重复 CR",
          not bad, bad or "全一致", "全一致")

    try:
        import yaml
        d = yaml.safe_load(read_text("state.yaml"))
        check("D4 state.yaml YAML 可解析且 open_questions 非空",
              isinstance(d.get("open_questions"), list) and len(d["open_questions"]) > 50,
              len(d.get("open_questions", [])), ">50")
    except Exception as e:                                    # noqa: BLE001
        check("D4 state.yaml YAML 可解析且 open_questions 非空", False, repr(e), "可解析")

    leftovers = [f for f in os.listdir(rp("tools")) if f.startswith("_tmp")]
    check("D5 无临时脚本残留（tools/_tmp*）", not leftovers, leftovers or "无", "无")

    # 纪律 31：README 的「A2 严格支配」必须出现在「引用并当场撤回」的上下文里
    lines = read_text("README.md").split("\n")
    hit = [i for i, l in enumerate(lines) if "严格支配" in l]
    ctx_ok = bool(hit) and all(
        any("撤回" in lines[j] for j in range(i, min(i + 6, len(lines)))) for i in hit)
    check("D6 纪律 31 上下文判定：README 的「A2 严格支配」均为否定式引用（非残留）",
          ctx_ok, {"hits": hit, "all_retracted_in_6_lines": ctx_ok}, "全在撤回上下文内")

    # 引擎数值核心未被本轮改动（与 R164-7 I10 记录一致）
    myc = jload("runs/r165_mycelium_identifiability.json")
    i10 = next((c for c in myc.get("checks", []) if c.get("id") == "I10"), {}) if myc else {}
    recorded = (i10.get("value") or {}).get("source_sha256_16", {})
    now = {k: sha16(k) for k in recorded}
    check("D7 引擎 4 个源码文件哈希与 R164-7 证明时逐位一致（引擎零改动）",
          bool(recorded) and recorded == now,
          {"recorded": recorded, "now": now}, "逐位一致")

    check("D8 三个探针日志齐备（_r165_co2 / _r165_mcp / _r165_mycelium）",
          all(os.path.exists(rp("runs", f)) for f in
              ("_r165_co2.log", "_r165_mcp.log", "_r165_mycelium.log")),
          [os.path.exists(rp("runs", f)) for f in
           ("_r165_co2.log", "_r165_mcp.log", "_r165_mycelium.log")], "全在")

    mydoc = read_text("docs/r165_mycelium_identifiability.md")
    undecided = ["未写 `data/`", "未新增观测通道、未改 EnKF 阈值 / 白名单",
                 "未写回 alpha_kla、未回填扰动随机成分", "`fastmcp` 仍未安装",
                 "未把检测器 / 证明逻辑写入任何默认引擎路径"]
    check("D9 本阶段未越界（§七 不改动清单五项齐备）",
          all(k in mydoc for k in undecided),
          [k for k in undecided if k not in mydoc] or "五项齐备", "五项齐备")


def main():
    section_a()
    section_b()
    section_c()
    section_d()
    npass = sum(1 for c in CHECKS if c["ok"])
    ntot = len(CHECKS)
    verdict = "ALL PASS" if npass == ntot else "FAIL"
    print("=" * 80)
    print("R165 终检 —— %d/%d  %s" % (npass, ntot, verdict))
    print("=" * 80)
    for i, c in enumerate(CHECKS, 1):
        print("[%s] %-2d %s" % ("PASS" if c["ok"] else "FAIL", i, c["name"]))
        if not c["ok"]:
            print("        got=%r expect=%r" % (c["got"], c["expect"]))
    print("-" * 80)
    print("判定：%s（%d/%d）" % (verdict, npass, ntot))
    if "--json" in sys.argv:
        out = rp("runs", "r165_final_check.json")
        with io.open(out, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps({"round": "R165", "n_checks": ntot, "n_pass": npass,
                                "verdict": verdict, "checks": CHECKS},
                               ensure_ascii=False, indent=2))
        print("写出：%s" % os.path.relpath(out, ROOT))
    return 0 if verdict == "ALL PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
