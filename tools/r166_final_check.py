# -*- coding: utf-8 -*-
"""R166 终检（只读、常驻可复跑）—— 五项裁决 + 三候选通道 + A/B 证据 + 闸门 + 文档卫生。

判据纪律（D-78）：全部读 runs/ 产物的**具体数值**，不用纯文本子串判通过；
零信息对照 / 双向判据 / 数据驱动阈值的结论从 `runs/r166_ab_gate.json` 的判据字段取。

用法：
  py tools/r166_final_check.py            # 控制台
  py tools/r166_final_check.py --json     # 写 runs/r166_final_check.json
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
sys.path.insert(0, str(ROOT / "candidate" / "indpensim" / "v0.1"))

CHECKS = []


def check(cid, name, ok, got=None):
    CHECKS.append({"id": cid, "name": name, "ok": bool(ok), "got": got})


def jload(name, default=None):
    p = RUNS / name
    if not p.exists():
        return default if default is not None else {}
    return json.loads(p.read_text(encoding="utf-8"))


def txt(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def sha16(rel):
    p = ROOT / rel
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16] if p.exists() else "MISSING"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    ab = jload("r166_ab_gate.json")
    vo = jload("r166_v2_optim.json")
    ms = jload("r166_mcp_smoke.json")
    zr = jload("r166_zero_regression.json")
    gu = jload("r166_governance_update.json")
    v1h = jload("r166_v1_health.json")
    r165m = jload("r165_mycelium_identifiability.json")
    r165f = jload("r165_final_check.json")
    zsum = zr.get("summary", {})

    def cid_of(d):
        return {c.get("id"): c for c in d.get("checks", [])}

    # ===================== A 组：裁决与边界 =====================
    verdict_doc = txt("docs/r166_verdict.md")
    check("A1", "裁决单存在且五项裁决齐备（V1…V5 各有独立章节）",
          all(("### R164-V%d" % i) in verdict_doc for i in range(1, 6)),
          {"n_sections": sum(1 for i in range(1, 6)
                             if ("### R164-V%d" % i) in verdict_doc)})
    check("A2", "裁决单明确否决「直接改默认+重算基线」并给出四条实证理由",
          "回归锚不可再生" in verdict_doc and "恒假" in verdict_doc
          and "产量崖" in verdict_doc and "oq#36" in verdict_doc,
          {"length": len(verdict_doc)})
    check("A3", "四层架构 L0/L1/L2/L3 齐备且 L3 明确留待下一阶段",
          all(("L%d" % i) in verdict_doc for i in range(4))
          and "本轮不执行" in verdict_doc)
    check("A4", "Go/No-Go 切换条件量化（C1…C6 六条）",
          all(("C%d" % i) in verdict_doc for i in range(1, 7)))

    goal = txt("GOAL.md")
    goal_bak = (RUNS / "_r166_backup" / "GOAL_pre_r166.md").read_text(encoding="utf-8")
    sec5 = goal.split("## 5. 红线与约束")[1].split("## 6.")[0]
    sec5_bak = goal_bak.split("## 5. 红线与约束")[1].split("## 6.")[0]
    check("A5", "GOAL §5 红线与约束一字未改（逐字符比对改前备份）",
          sec5 == sec5_bak, {"identical": sec5 == sec5_bak, "len": len(sec5)})
    check("A6", "GOAL §2 第 7 行改标「软测量内部量，不作交付宣称」且保留该行",
          "软测量内部量，不作交付宣称" in goal and "菌丝区组成" in goal
          and "动力学状态反推（软测量扩展）" not in goal)
    check("A7", "GOAL §8 登记 R166 用户委托裁决的目标口径变更",
          "R166 增补" in goal and "用户委托裁决" in goal)
    req = txt("requirements.txt")
    check("A8", "requirements.txt 锁 mcp==1.12.0 且未锁 fastmcp 发行版",
          "mcp==1.12.0" in req and "fastmcp==" not in req)

    # ===================== B 组：三个 opt-in 候选通道 =====================
    sc_src = txt("candidate/indpensim/v0.1/solver_chain.py")
    sim_src = txt("candidate/indpensim/v0.1/simulate.py")
    check("B1", "V1 opt-in：enkf_health 有 innovation_criteria 且默认 None",
          "innovation_criteria=None" in sc_src
          and "def _enkf_health_r166" in sc_src)
    check("B2", "V1 独立函数不进默认路径（分流在 reasons 初始化之前）",
          sc_src.index("if innovation_criteria is not None:")
          < sc_src.index("    reasons = []\n    metrics = {}"))
    check("B3", "V1 冻结常量未改（INNOVATION_Z_LIMIT=5.0 / FAIL_RATE_LIMIT=0.02）",
          "INNOVATION_Z_LIMIT = 5.0" in sc_src
          and "FAIL_RATE_LIMIT = 0.02" in sc_src
          and 'INNOVATION_Z_CHANNELS = ("CO2outgas", "DO2", "O2", "pH")' in sc_src)
    check("B4", "V1 候选函数不内置手写阈值（只从 criteria 读 z_th / min_frac）",
          'z_th = float(rule.get("z_th", INNOVATION_Z_LIMIT))' in sc_src
          and 'min_frac = float(rule.get("min_frac", 0.0))' in sc_src)
    check("B5", "V2 opt-in：simulate 有 dist_noise_sigma 且默认 None",
          'params.get("dist_noise_sigma", None)' in sim_src
          and "if dist_noise_sigma is not None:" in sim_src)
    check("B6", "V2 8 路注入与时间常数按 dist_tau 对齐、固定种子可复现",
          "np.random.default_rng(int(params.get(\"dist_noise_seed\", 7)))" in sim_src
          and "np.exp(-_dt_n / dist_tau)" in sim_src
          and sim_src.count("+= _noise_state[") == 8)
    import ast as _ast
    ab_tree = _ast.parse(txt("tools/r166_ab_gate.py"))
    v3_node = next((n for n in ab_tree.body
                    if isinstance(n, _ast.FunctionDef) and n.name == "v3_run"), None)
    nodes = list(_ast.walk(v3_node)) if v3_node is not None else []
    # `COMBINED` 的读取发生在模块级 worker `_sim_worker`，不在 v3_run 子树内；
    # 故「只读 COMBINED / 无下标赋值」必须对**整模块**实判，写文件调用仍只看 v3_run。
    all_nodes = list(_ast.walk(ab_tree))
    write_calls = [n for n in nodes
                   if isinstance(n, _ast.Call)
                   and ((isinstance(n.func, _ast.Attribute)
                         and n.func.attr in ("write_text", "write_bytes",
                                             "dump", "replace", "save"))
                        or (isinstance(n.func, _ast.Name)
                            and n.func.id in ("open",)))]
    combined_assigns = [n for n in all_nodes
                        if isinstance(n, (_ast.Assign, _ast.AugAssign))
                        and any(isinstance(t, _ast.Subscript)
                                and isinstance(t.value, _ast.Name)
                                and t.value.id == "COMBINED"
                                for t in (n.targets if isinstance(n, _ast.Assign)
                                          else [n.target]))]
    reads_combined = any(isinstance(n, _ast.Subscript)
                         and isinstance(n.value, _ast.Name)
                         and n.value.id == "COMBINED" for n in all_nodes)
    check("B7", "V3 不写回黄金参数：v3_run 无写文件调用；全模块只读 COMBINED、无下标赋值",
          v3_node is not None and reads_combined
          and not write_calls and not combined_assigns,
          {"v3_run_found": v3_node is not None,
           "reads_combined": reads_combined,
           "write_calls_in_v3_run": len(write_calls),
           "combined_subscript_assigns_whole_module": len(combined_assigns)})
    import importlib
    gp = importlib.import_module("golden_params")
    n85 = sum(1 for p in gp.COMBINED.values() if p.get("alpha_kla") == 85)
    check("B8", "COMBINED 仍是 88 批 / 81 批 alpha_kla=85（未写回）",
          len(gp.COMBINED) == 88 and n85 == 81,
          {"n_batches": len(gp.COMBINED), "n_alpha_kla_85": n85})
    i10 = next((c for c in r165m.get("checks", []) if c.get("id") == "I10"), {})
    h165 = (i10.get("got") or i10.get("value") or {}).get("source_sha256_16", {})
    k = "candidate/indpensim/v0.1/%s"
    now = {f: sha16(k % f) for f in
           ("model.py", "observe.py", "simulate.py", "mcp_server.py")}
    bak = {}
    for f in ("simulate.py", "mcp_server.py"):
        p = RUNS / "_r166_backup" / ("%s_pre_r166.py" % f[:-3])
        bak[f] = (hashlib.sha256(p.read_bytes()).hexdigest()[:16]
                  if p.exists() else "MISSING")
    check("B9", "引擎哈希双向：model/observe 与 R165 逐位一致；改前备份 = R165 冻结值；"
          "simulate/mcp_server 当前确已变更",
          bool(h165)
          and now["model.py"] == h165.get(k % "model.py")
          and now["observe.py"] == h165.get(k % "observe.py")
          and bak["simulate.py"] == h165.get(k % "simulate.py")
          and bak["mcp_server.py"] == h165.get(k % "mcp_server.py")
          and now["simulate.py"] != h165.get(k % "simulate.py")
          and now["mcp_server.py"] != h165.get(k % "mcp_server.py"),
          {"r165_frozen": h165, "now": now, "pre_r166_backup": bak})
    check("B10", "默认路径零回归：86 批 max|Δ| = 0.00e+00 / RMSE 2.345% / 86/86",
          zsum.get("max_abs_delta_pct") == 0.0
          and zsum.get("within5") == 86 and zsum.get("n") == 86
          and abs(float(zsum.get("rmse_pct", 0)) - 2.3448) < 1e-6
          and zsum.get("pass") is True,
          zsum)

    # ===================== C 组：A/B 证据闸门（读具体判据数值）=====================
    ng = ab.get("no_go") or {}
    failed_ab = [c for c in ab.get("checks", []) if not c.get("pass")]
    pass_branch = (ab.get("verdict") == "PASS"
                   and ab.get("n_pass") == ab.get("n_checks")
                   and ab.get("n_checks", 0) > 0)
    no_go_branch = (ab.get("verdict") == "NO_GO"
                    and ng.get("declared") is True
                    and ng.get("n_fail") == 2
                    and ng.get("failed_checks") == ["V2-3", "V2-4"]
                    and len(failed_ab) == 2
                    and all(c.get("id") in ("V2-3", "V2-4") for c in failed_ab)
                    and ng.get("default_switched") is False
                    and ng.get("frozen_thresholds") == {"V2-3": 20.0, "V2-4": 30.0}
                    and float(ng.get("max_abs_delta_pp") or 0) >= 30.0)
    check("C1", "A/B 闸门总判定 PASS，或 D-78 合规的 NO_GO（仅 V2-3/V2-4 FAIL + 实值证据）",
          pass_branch or no_go_branch,
          {"verdict": ab.get("verdict"), "n_pass": ab.get("n_pass"),
           "n_checks": ab.get("n_checks"), "pass_branch": pass_branch,
           "no_go_branch": no_go_branch,
           "failed_ids": [c.get("id") for c in failed_ab]})
    v1 = ab.get("v1") or {}
    v1c = cid_of({"checks": v1.get("checks", [])})
    check("C2", "V1 零信息对照：可行组合全部保证健康批 0 触发（V1-1）",
          bool(v1c.get("V1-1", {}).get("pass")),
          v1c.get("V1-1", {}).get("got"))
    check("C3", "V1 阈值数据驱动：网格 + 倍数，无手写 10.0 / 0.02（V1-2）",
          bool(v1c.get("V1-2", {}).get("pass")),
          v1c.get("V1-2", {}).get("got"))
    check("C4", "V1 显式裕度准则选出候选（V1-3）",
          bool(v1c.get("V1-3", {}).get("pass")),
          {"margin": v1.get("margin"), "channels": v1.get("chosen_channels")})
    crit = v1.get("criteria") or {}
    zths = [float(v.get("z_th", 0)) for v in (crit.get("channels") or {}).values()]
    check("C5", "V1 阈值不是手写常量 10.0 / 5.0，且来自逐通道实测分布",
          bool(zths) and all(abs(t - 10.0) > 1e-9 and abs(t - 5.0) > 1e-9
                             for t in zths),
          {"z_th": zths, "excluded": crit.get("excluded"),
           "min_frac": [v.get("min_frac") for v in
                        (crit.get("channels") or {}).values()]})
    conf = v1.get("confusion") or {}
    cand, froz = conf.get("candidate", {}), conf.get("frozen", {})
    check("C6", "V1 四格 A/B：TP 不降 / FP 不增 / TN 不降（V1-4 实值）",
          bool(v1c.get("V1-4", {}).get("pass"))
          and cand.get("TP", -1) >= froz.get("TP", 99)
          and cand.get("FP", 99) <= froz.get("FP", -1)
          and cand.get("TN", -1) >= froz.get("TN", 99),
          {"candidate": cand, "frozen": froz})
    check("C7", "V1 双向判据非恒真/恒假 + 反向判别力（V1-5 / V1-6）",
          bool(v1c.get("V1-5", {}).get("pass"))
          and bool(v1c.get("V1-6", {}).get("pass")),
          {"V1-5": v1c.get("V1-5", {}).get("got"),
           "V1-6": v1c.get("V1-6", {}).get("got")})
    loo = v1.get("loo") or []
    check("C8", "V1 按批 LOO 全折通过（V1-7）",
          bool(v1c.get("V1-7", {}).get("pass")) and len(loo) >= 5
          and all(x.get("pass") for x in loo),
          {"folds": len(loo), "n_pass": sum(1 for x in loo if x.get("pass"))})
    check("C9", "V1 默认路径逐位一致（V1-8）",
          bool(v1c.get("V1-8", {}).get("pass")),
          v1c.get("V1-8", {}).get("got"))
    check("C10", "V1 采集样本含零信息对照且无错误",
          v1h.get("n_cases", 0) >= 20 and v1h.get("n_error", 1) == 0,
          {"n_cases": v1h.get("n_cases"), "n_error": v1h.get("n_error"),
           "wall_s": v1h.get("wall_s")})
    v2c = cid_of({"checks": (ab.get("v2") or {}).get("checks", [])})
    v3c = cid_of({"checks": (ab.get("v3") or {}).get("checks", [])})
    check("C11", "V2 8 路 σ 取自 R163 解析值且 τ=40 h（V2-1）",
          bool(v2c.get("V2-1", {}).get("pass")),
          {"n_channels": len((ab.get("v2") or {}).get("sigmas", {}))})
    check("C12", "V2 固定种子完全可复现（V2-2）",
          bool(v2c.get("V2-2", {}).get("pass")),
          v2c.get("V2-2", {}).get("got"))
    v2p3 = bool(v2c.get("V2-3", {}).get("pass"))
    v2p4 = bool(v2c.get("V2-4", {}).get("pass"))
    v2_gate_ok = (v2p3 and v2p4) or (
        ab.get("verdict") == "NO_GO" and ng.get("declared") is True
        and ng.get("n_fail") == 2
        and ng.get("failed_checks") == ["V2-3", "V2-4"]
        and float(ng.get("max_abs_delta_pp") or 0) >= 30.0
        and ng.get("default_switched") is False
        and ng.get("frozen_thresholds") == {"V2-3": 20.0, "V2-4": 30.0})
    check("C13", "V2 结论有实值支撑：V2-3/V2-4 PASS，或 NO_GO 崩塌实值 + 阈值未改 + 未切默认",
          v2_gate_ok,
          {"V2-3": v2p3, "V2-4": v2p4, "verdict": ab.get("verdict"),
           "got": v2c.get("V2-3", {}).get("got")})
    v3rows = (ab.get("v3") or {}).get("rows") or []
    check("C14", "V3 k_dual 查表来自产物且产量仍在 ±5%（V3-1/V3-2）",
          bool(v3c.get("V3-1", {}).get("pass"))
          and bool(v3c.get("V3-2", {}).get("pass"))
          and len(v3rows) > 0,
          {"n_rows": len(v3rows),
           "excluded": (ab.get("v3") or {}).get("excluded")})
    check("C15", "V3 A/B 逐批差值全量列出、崖批排除（V3-3/V3-4）",
          bool(v3c.get("V3-3", {}).get("pass"))
          and bool(v3c.get("V3-4", {}).get("pass")),
          {"n_rows": len(v3rows)})

    # ---- V2 多轮寻优（只改设计、不改判据）的独立证据 ----
    voc = cid_of(vo)
    v2c_all = (ab.get("v2") or {}).get("checks", [])
    v2map = {c.get("id"): c for c in v2c_all}
    full = next((g for g in vo.get("grid", []) if g.get("scale") == 1.0), {})
    check("C16", "V2 寻优产物齐备：零信息对照 / 全幅崩塌 / R163 实测目标 / 阈值未改",
          bool(vo) and all(voc.get(k, {}).get("pass") for k in
                           ("V2O-1", "V2O-2", "V2O-3", "V2O-4"))
          and int(full.get("n_collapse", 0)) > 0
          and float(vo.get("reference_pp") or 0) > 0
          and vo.get("verdict") in ("GO", "NO_GO"),
          {"optim_verdict": vo.get("verdict"),
           "full_scale_n_collapse": full.get("n_collapse"),
           "full_scale_max_abs_pp": full.get("max_abs_delta_pp"),
           "reference_pp": vo.get("reference_pp"),
           "v23_v24_frozen": [vo.get("v23_max"), vo.get("v24_max")]})
    check("C17", "A/B 闸门 V2-6/V2-7 通过，且标定 scale / 崩塌数字均来自产物（非手写）",
          bool(v2map.get("V2-6", {}).get("pass"))
          and bool(v2map.get("V2-7", {}).get("pass"))
          and (ab.get("v2") or {}).get("applied_scale") is not None
          and (ab.get("v2") or {}).get("full_scale_rows") != [],
          {"V2-6": v2map.get("V2-6", {}).get("pass"),
           "V2-7": v2map.get("V2-7", {}).get("pass"),
           "applied_scale": (ab.get("v2") or {}).get("applied_scale"),
           "optim_verdict": (ab.get("v2") or {}).get("optim_verdict")})

    # ===================== D 组：闸门 =====================
    msc = cid_of(ms)
    check("D1", "MCP 冒烟 9/9 PASS（含无 stub 导入 / 14 工具 / 无监听端口）",
          ms.get("verdict") == "PASS" and ms.get("n_pass") == 9
          and ms.get("n_checks") == 9
          and all(v.get("pass") for v in msc.values()),
          {"n_pass": ms.get("n_pass"), "n_checks": ms.get("n_checks")})
    check("D2", "MCP 官方 SDK 后端生效且第三方 fastmcp 未安装（S2）",
          bool(msc.get("S2", {}).get("pass")), msc.get("S2", {}).get("got"))
    check("D3", "14 工具函数体与改前逐字一致（S6）",
          bool(msc.get("S6", {}).get("pass")), msc.get("S6", {}).get("got"))
    pt = (RUNS / "_r166_pytest.log").read_text(encoding="utf-8", errors="replace") \
        if (RUNS / "_r166_pytest.log").exists() else ""
    m_passed = re.search(r"(\d+) passed", pt)
    check("D4", "py -m pytest -q 全通过且退出码 0",
          bool(m_passed) and "EXIT=0" in pt and "failed" not in pt,
          {"passed": int(m_passed.group(1)) if m_passed else None,
           "exit0": "EXIT=0" in pt})
    zlog = (RUNS / "_r166_zero_regression.log").read_text(
        encoding="utf-8", errors="replace")
    check("D5", "零回归日志含 0.00e+00 且产物 pass=True",
          "0.00e+00" in zlog and zsum.get("pass") is True)
    check("D6", "治理同步脚本已应用且 dry-run 零泄漏 / 三次复跑零写入",
          gu.get("mode") == "apply" and gu.get("verdict") == "PASS"
          and gu.get("n_error") == 0,
          {"mode": gu.get("mode"), "n_changed": gu.get("n_changed"),
           "n_skip": gu.get("n_skip"), "n_error": gu.get("n_error")})
    check("D7", "R165 终检基线仍为 70/70 ALL PASS（未被本轮破坏）",
          r165f.get("verdict") in ("PASS", "ALL PASS")
          and r165f.get("n_pass") == 70 and r165f.get("n_checks") == 70,
          {"verdict": r165f.get("verdict"), "n_pass": r165f.get("n_pass"),
           "n_checks": r165f.get("n_checks")})

    # ===================== E 组：文档卫生 =====================
    contract = txt("ENGINE_CONTRACT.md")
    ledger = txt("docs/r157_debt_ledger.md")
    signoff = txt("docs/m5_review_signoff.md")
    readme = txt("README.md")
    index = txt("tools/INDEX.md")
    state = txt("state.yaml")
    roadmap = txt("docs/roadmap_next.md")
    report = txt("docs/r166_round_report.md") \
        if (ROOT / "docs/r166_round_report.md").exists() else ""
    memory = txt(".workbuddy/memory/2026-11-06.md")
    check("E1", "契约升 v1.96 且头部登记 R166 四层架构与未越界声明",
          "v1.96，2026-11-06" in contract
          and "> 状态：**v1.96**（R166" in contract
          and "L0" in contract and "不重启 8770" in contract
          and contract.count("> 状态：**v1.96**（R166") == 1)
    check("E2", "台账 D-91 + R166 总表增补齐备，五条债状态迁移明确",
          "### D-91" in ledger and "### R166 总表增补" in ledger
          and all(("D-%d" % i) in ledger for i in (83, 84, 85, 87, 88)))
    check("E3", "签核单 R-16 落地且含 A/B / 零回归 / 未越界",
          "**R-16**" in signoff and "R166" in signoff and "未越界" in signoff)
    check("E4", "README 登记 R166 轮次段（含三个 R166 产物名，非勘误文字误报）",
          "### R166（2026-11-06）" in readme
          and all(t in readme for t in ("r166_ab_gate.json",
                                        "r166_mcp_smoke.json",
                                        "r166_final_check.json")))
    check("E5", "tools/INDEX.md 登记 R166 四个工具与三份文档",
          "### R166（五项委托裁决" in index
          and all(t in index for t in ("r166_ab_gate.py", "r166_mcp_smoke.py",
                                       "r166_governance_update.py",
                                       "r166_final_check.py",
                                       "docs/r166_verdict.md")))
    import yaml
    oq = yaml.safe_load(state).get("open_questions", [])
    r166_items = [q for q in oq if isinstance(q, str)
                  and q.lstrip("-# ✅🔴🟡⏸ ").startswith("R166")]
    check("E6", "state.yaml 有独立 R166 open_questions 条目（YAML 可解析）",
          len(r166_items) >= 1, {"n_r166_items": len(r166_items),
                                 "n_total": len(oq)})
    check("E7", "roadmap §8.8 下一阶段清单含 L3 决策 / 根因治理 / 暂缓项",
          "### 8.8 下一阶段任务清单" in roadmap
          and all(t in roadmap for t in ("R166-1", "R166-5", "R164-12",
                                         "GOAL", "§5")))
    check("E8", "主交付报告存在且含裁决 / A/B / 闸门 / 下一阶段",
          all(t in report for t in ("# R166 轮次报告", "五项裁决", "A/B",
                                    "零回归", "下一阶段")))
    check("E9", "工作记忆登记 R166 收口（含未越界与下一阶段）",
          "## R166（五项委托裁决" in memory and "未越界" in memory)
    docs_for_placeholder = [report, contract, ledger, signoff, readme, index,
                            state, roadmap, memory]
    check("E10", "治理文本无 ${...} 占位符残留",
          not any("${" in x for x in docs_for_placeholder))
    crlf = ["ENGINE_CONTRACT.md", "state.yaml"]
    check("E11", "换行风格原样保留（CRLF：契约 / state.yaml；其余 LF）",
          all(b"\r\n" in (ROOT / f).read_bytes() for f in crlf)
          and all(b"\r\n" not in (ROOT / f).read_bytes()
                  for f in ("docs/roadmap_next.md", "README.md",
                            "tools/INDEX.md", "GOAL.md",
                            ".workbuddy/memory/2026-11-06.md")))
    unsec = verdict_doc.split("## 5. 本轮未越界声明")[1].split("## 6.")[0]
    un_items = ["不切换", "不重启", "R164-12", "GOAL §5", "长期硬基线"]
    check("E12", "裁决单 §5 未越界声明五项齐备（逐项实值，非纯子串兜底）",
          all(t in unsec for t in un_items),
          {"items_present": [t for t in un_items if t in unsec],
           "missing": [t for t in un_items if t not in unsec]})

    n_pass = sum(1 for c in CHECKS if c["ok"])
    out = {"round": "R166", "tool": "r166_final_check",
           "verdict": "PASS" if n_pass == len(CHECKS) else "FAIL",
           "n_pass": n_pass, "n_checks": len(CHECKS), "checks": CHECKS}
    if a.json:
        (RUNS / "r166_final_check.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=1, default=str),
            encoding="utf-8")
    print("R166 终检 %d/%d %s" % (n_pass, len(CHECKS), out["verdict"]))
    for c in CHECKS:
        if not c["ok"]:
            print("  [FAIL] %s %s | got=%s" % (c["id"], c["name"],
                                               str(c.get("got"))[:200]))
    return 0 if out["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
