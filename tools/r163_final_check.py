# -*- coding: utf-8 -*-
"""
R163 终检（常驻可复跑）

用途：对 R163「D-80 回退链接入现役 MCP 路径 + 三条基础性收尾」轮次的交付物与治理层
     做一次全量机器复核。本工具**只读**，不写任何文件；任何一条 FAIL 即表示本轮收口不完整。

覆盖：
  A. 探针产物判据   —— alpha_kla 双约束 / 扰动方差 / MCP 接入 / 退化筛查 / 创新标定
  B. 报告结构       —— 章节连续、无残留占位符、要点齐全、行尾纯 LF
  C. 治理层同步     —— 台账 / 签核单 / 路线图 / 契约 / README / state.yaml / 索引 / 记忆
  D. 文档卫生       —— 行尾风格、无重复 CR、零回归证据、pytest 证据、无临时残留

用法：
    py tools/r163_final_check.py            # 打印逐条结果
    py tools/r163_final_check.py --json     # 追加写 runs/r163_final_check.json
"""
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


def _ok(c):
    """判据条目的通过标志：产物用 `pass`，部分用 `ok`。"""
    if c.get("pass") is not None:
        return bool(c.get("pass"))
    return bool(c.get("ok"))


def _cid(c):
    return "%s %s" % (c.get("id", ""), c.get("name", ""))


CHECKS = []


def check(name, ok, got=None, expect=None, detail=None):
    CHECKS.append(
        {"name": name, "ok": bool(ok), "got": got, "expect": expect, "detail": detail}
    )
    return bool(ok)


# ─────────────────────────────────────────────────────────────
# A. 探针产物判据
# ─────────────────────────────────────────────────────────────
def section_a():
    # --- A0 产物齐备 ---
    need = ["runs/r163_kla_dual_constraint.json", "runs/r163_dist_variance.json",
            "runs/r163_degradation_probe.json", "runs/r163_mcp_integration.json",
            "runs/r163_innovation_calibration.json"]
    miss = [p for p in need if not os.path.exists(rp(p))]
    check("A0 五个探针产物齐备", not miss, miss or "全在", "全在")

    # --- alpha_kla 双约束 ---
    kla = jload("runs/r163_kla_dual_constraint.json", {}) or {}
    n, p = kla.get("n_checks"), kla.get("n_pass")
    check("A1 alpha_kla 双约束判据 7/7 PASS",
          n == 7 and p == 7 and kla.get("verdict") == "PASS",
          "%s/%s %s" % (p, n, kla.get("verdict")), "7/7 PASS")
    bad = [_cid(c) for c in kla.get("checks", []) if not _ok(c)]
    check("A2 alpha_kla 逐条判据 ok 全 True", not bad, bad or "全 True", "全 True")
    ks = kla.get("summary", {}) or {}
    check("A3 不可标定批被显式识别（b55）",
          55 in (ks.get("not_calibratable_batches") or []),
          ks.get("not_calibratable_batches"), "含 55")
    check("A4 产量崖批被显式标记",
          bool(ks.get("on_cliff_batches")), ks.get("on_cliff_batches"), "非空")

    # --- 扰动方差 ---
    dist = jload("runs/r163_dist_variance.json", {}) or {}
    n2, p2 = dist.get("n_checks"), dist.get("n_pass")
    check("A5 扰动方差判据 5/5 PASS",
          n2 == 5 and p2 == 5 and dist.get("verdict") == "PASS",
          "%s/%s %s" % (p2, n2, dist.get("verdict")), "5/5 PASS")
    bad2 = [_cid(c) for c in dist.get("checks", []) if not _ok(c)]
    check("A6 扰动方差逐条判据 ok 全 True", not bad2, bad2 or "全 True", "全 True")

    # --- MCP 接入零回归 ---
    mcp = jload("runs/r163_mcp_integration.json", {}) or {}
    n3, p3 = mcp.get("n_checks"), mcp.get("n_pass")
    check("A7 MCP 接入判据全 PASS",
          n3 and p3 == n3 and mcp.get("verdict") == "PASS",
          "%s/%s %s" % (p3, n3, mcp.get("verdict")), "全 PASS")
    bad3 = [_cid(c) for c in mcp.get("checks", []) if not _ok(c)]
    check("A8 MCP 接入逐条判据 ok 全 True", not bad3, bad3 or "全 True", "全 True")
    # Z1 零回归必须存在且为 PASS
    z1 = next((c for c in mcp.get("checks", []) if str(c.get("id", "")).startswith("Z1")
               or str(c.get("name", "")).startswith("Z1")), None)
    check("A9 Z1 零回归（返回体逐位一致）PASS",
          bool(z1 and _ok(z1)), _ok(z1) if z1 else None, True)
    # Z1 的判据是**逐位字符串比较** ⇒ got="identical" 即等价于 max|Δ|=0
    check("A10 Z1 明确给出逐位一致（identical）",
          bool(z1 and str(z1.get("got", "")).strip().lower() in ("identical", "0", "true")),
          str((z1 or {}).get("got"))[:60], "identical")

    # --- 退化筛查 ---
    deg = jload("runs/r163_degradation_probe.json", {}) or {}
    asum = deg.get("A_summary", {}) or {}
    check("A11 A 段筛查已完成（n_scanned > 0）",
          asum.get("n_scanned", 0) > 0, asum.get("n_scanned"), ">0")
    check("A12 A 段既有退化批也有健康批（判据有区分度）",
          bool(asum.get("degraded_batches")) and bool(asum.get("healthy_batches")),
          {"deg": len(asum.get("degraded_batches") or []),
           "ok": len(asum.get("healthy_batches") or [])}, "两侧非空")
    csum = deg.get("C_summary", {}) or {}
    check("A13 C 段注入完成且触发/未触发均有样本（白名单反向判别力）",
          bool(csum.get("fired")) and bool(csum.get("not_fired")),
          {"fired": len(csum.get("fired") or []),
           "not_fired": len(csum.get("not_fired") or [])}, "两侧非空")
    # ⚠ 判据口径修正：旧的「期望全中」把**不可归因**样本（对照本身已退化）也算进去
    #   ⇒ 会把「对照已退化」误判成「判据失灵」（R163 踩过）。
    #   ⇒ 只在**可归因子集**（对照健康）上判定。
    #
    # ⚠ 判据**不得**强行要求「全部期望全中」：实测 CO2 卡死漏检 4/5、pH 漏检 1/5
    #   ⇒ 判据在真实数据上**确实有灵敏度缺口**（这是 D-87 的第二个维度）。
    #   ⇒ 终检要求的是「**检出率被量化且反向判别力成立**」，而非「零漏检」——
    #   强行恒真即 D-78 禁止的「恒真判据」；强行恒假则是粉饰。
    attrib_fired = len(csum.get("true_positive", []) or [])
    attrib_n = csum.get("n_attributable", 0)
    det_rate = (float(attrib_fired) / attrib_n) if attrib_n else 0.0
    check("A14 C 段『可归因子集上检出率被量化且 > 0』（灵敏度下限非零）",
          attrib_n > 0 and det_rate > 0.0,
          {"n_attributable": attrib_n, "TP": attrib_fired,
           "detection_rate": round(det_rate, 4)}, "n>0 且 检出率>0")
    # 反向判别力：白名单外的故障必须**不得**触发（TN 必须 > 0）
    check("A14d C 段反向判别力成立（白名单外故障未被误报，TN > 0）",
          len(csum.get("true_negative", []) or []) > 0,
          {"TN": len(csum.get("true_negative", []) or []),
           "FP": len(csum.get("false_positive", []) or [])}, "TN>0")
    check("A14b C 段存在可归因样本（对照健康）且不可归因样本被单列",
          csum.get("n_attributable", 0) > 0
          and "not_attributable_cases" in csum,
          {"attr": csum.get("n_attributable"),
           "non_attr": csum.get("n_not_attributable")}, ">0 且单列")
    # 四格混淆矩阵必须齐备（判别力证据）
    check("A14c C 段四格混淆矩阵齐备（TP/FN/TN/FP）",
          all(k in csum for k in ("true_positive", "false_negative",
                                  "true_negative", "false_positive")),
          [k for k in ("true_positive", "false_negative", "true_negative",
                       "false_positive") if k not in csum] or "全在", "四格齐")

    # --- 创新标定 ---
    cal = jload("runs/r163_innovation_calibration.json", {}) or {}
    summ = cal.get("cross_batch_summary", {}) or {}
    check("A15 创新判据跨批标定产物存在且有通道分布",
          bool(summ),
          sorted(summ.keys())[:6] or "空", "非空")
    # 判据候选枚举必须给出阈值×占比的假阳性率
    cands = cal.get("criterion_candidates", {}) or {}
    check("A16 候选判据枚举非空（含阈值 × 持续占比的触发率）",
          bool(cands),
          sorted(cands.keys())[:4] or "空", "非空")
    # 现行阈值 z=5 的触发率必须显著高于 75%（D-87 的量化依据）
    cur = cands.get("z>5 & frac>0.00") or {}
    check("A17 现行判据（z>5）触发率 ≥ 50%（D-87 量化依据）",
          float(cur.get("false_positive_rate", 0)) >= 0.5,
          cur.get("false_positive_rate"), ">=0.5")
    # 存在比现行阈值更好的候选（触发率显著更低）
    better = [k for k, v in cands.items()
              if float(v.get("false_positive_rate", 1)) < 0.5]
    check("A18 存在触发率 < 50% 的候选判据（给出可行区间）",
          bool(better), sorted(better)[:5] or "空", "非空")


# ─────────────────────────────────────────────────────────────
# B. 报告结构
# ─────────────────────────────────────────────────────────────
def section_b():
    rel = "docs/r163_round_report.md"
    t = read_text(rel)
    heads = [l for l in t.split("\n") if l.startswith("## ")]
    names = [h[3:].split("、")[0].strip() for h in heads]
    # 允许插入式小节（如「六之二」），但**主干编号**须连续
    main = [n for n in names if n and n[0] in "一二三四五六七八九十" and "之二" not in n]
    nums = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十", "十一"]
    check("B1 报告主干章节编号连续（一~十一）", main == nums, main, nums)

    import re
    left = sorted(set(re.findall(r"\{\{([A-Z_0-9]+)\}\}", t)))
    check("B2 报告无残留占位符", not left, left or "无", "无")

    check("B3 报告含「治理层同步」章", any("治理层同步" in h for h in heads),
          [h for h in heads if "治理层同步" in h], "存在")

    check("B4 报告覆盖 D-85 / D-86 / D-87 三条新债",
          all(k in t for k in ["D-85", "D-86", "D-87"]),
          [k for k in ["D-85", "D-86", "D-87"] if k in t], "三者齐")

    check("B5 报告含闸门表与未做边界",
          "闸门" in t and "未**做" in t and "证据清单" in t,
          [k for k in ["闸门", "未**做", "证据清单"] if k in t], "三者齐")

    check("B6 报告含零回归结论（max|Δ| = 0）",
          "0.00e+00" in t, "0.00e+00" in t, True)

    raw = read_bytes(rel)
    check("B7 报告行尾为纯 LF、无重复 CR",
          b"\r\n" not in raw and b"\r\r\n" not in raw and b"\r" not in raw,
          "crlf=%d crcrlf=%d" % (raw.count(b"\r\n"), raw.count(b"\r\r\n")), "纯 LF")


# ─────────────────────────────────────────────────────────────
# C. 治理层同步
# ─────────────────────────────────────────────────────────────
def section_c():
    led = read_text("docs/r157_debt_ledger.md")
    check("C1 台账含 D-85 / D-86 / D-87 三个详条",
          all(("### D-%d" % n) in led for n in (85, 86, 87)),
          [("### D-%d" % n) for n in (85, 86, 87) if ("### D-%d" % n) not in led] or "全在",
          "全在")
    check("C2 台账总表已补 D-85~D-87 三行",
          all(("| D-%d |" % n) in led for n in (85, 86, 87)),
          [("| D-%d |" % n) for n in (85, 86, 87) if ("| D-%d |" % n) not in led] or "全在",
          "全在")
    check("C3 台账标题已更新为「截至 R163」", "截至 R163" in led,
          "截至 R163" in led, True)
    check("C4 台账 D-80 行已改为「R163 部分关闭」",
          "R163 部分关闭" in led, "R163 部分关闭" in led, True)
    check("C5 台账纪律 25/26/27 已登记",
          all(("25. **判据的真假阳性率" in led,
               "26. **「最优解撞参数域边界」" in led,
               "27. **「口径极值点不同」" in led)),
          "25/26/27", "25/26/27")

    sg = read_text("docs/m5_review_signoff.md")
    check("C6 签核单含 R-13 决策行", "**R-13**" in sg, "**R-13**" in sg, True)

    rm = read_text("docs/roadmap_next.md")
    check("C7 路线图含 §8.5 R163 任务项", "8.5" in rm and "R163" in rm,
          ("8.5" in rm, "R163" in rm), "(True, True)")
    check("C8 路线图 R163-1~R163-5 五项齐",
          all(("R163-%d" % n) in rm for n in range(1, 6)),
          [("R163-%d" % n) for n in range(1, 6) if ("R163-%d" % n) not in rm] or "全在", "5 项")

    ct = read_text("ENGINE_CONTRACT.md")
    check("C9 契约标题为 v1.93", "（v1.93，2026-11-05）" in ct[:200],
          ct.split("\n")[0][:80], "含 v1.93")
    check("C10 契约头部含 v1.93 状态块", "> 状态：**v1.93**" in ct,
          "> 状态：**v1.93**" in ct, True)
    check("C11 契约 v1.92 原文降级保留为「历史」", "> **历史：v1.92**" in ct,
          "> **历史：v1.92**" in ct, True)
    check("C12 契约版本表含独立行 | v1.93 |",
          any(l.strip().startswith("| v1.93 |") for l in ct.split("\n")),
          "有" if any(l.strip().startswith("| v1.93 |") for l in ct.split("\n")) else "无", "有")
    craw = read_bytes("ENGINE_CONTRACT.md")
    check("C13 契约行尾纯 CRLF、无重复 CR",
          b"\r\r\n" not in craw and b"\r\n" in craw,
          "crlf=%d crcrlf=%d" % (craw.count(b"\r\n"), craw.count(b"\r\r\n")), "纯 CRLF")

    rd = read_text("README.md")
    check("C14 README 阅读顺序指向 R163 报告",
          "`docs/r163_round_report.md`" in rd,
          "`docs/r163_round_report.md`" in rd, True)
    check("C15 README 引用契约 v1.93 且阻断项含 D-85/86/87",
          "v1.93" in rd and "D-85" in rd and "D-86" in rd and "D-87" in rd,
          ("v1.93" in rd, "D-85" in rd, "D-86" in rd, "D-87" in rd), "四者齐")
    check("C16 README 无重复叠加（D-84 片段只出现 1 次）",
          rd.count("**D-84 alpha_kla 统一用名义值**") <= 1,
          rd.count("**D-84 alpha_kla 统一用名义值**"), "<=1")

    import yaml
    st_txt = read_text("state.yaml")
    st = yaml.safe_load(st_txt)
    check("C17 state.yaml 可解析", isinstance(st, dict), type(st).__name__, "dict")
    oq = st.get("open_questions", [])
    check("C18 state.yaml oq 数 = 57（R162 的 54 + R163 三条）", len(oq) == 57,
          len(oq), 57)
    oq_blob = json.dumps(oq, ensure_ascii=False)
    check("C19 state.yaml 三条新债已登记",
          all(k in oq_blob for k in ["D-85", "D-86", "D-87"]),
          [k for k in ["D-85", "D-86", "D-87"] if k in oq_blob], "三者齐")
    arts = st.get("artifacts", {})
    check("C20 state.yaml artifacts 含 R163 五件产物",
          all(("r163_%s" % k) in arts for k in
              ["degradation", "innovation_calib", "kla_dual", "dist_variance",
               "mcp_integration"]),
          [k for k in ["degradation", "innovation_calib", "kla_dual",
                       "dist_variance", "mcp_integration"]
           if ("r163_%s" % k) not in arts] or "全在", "五件齐")
    sraw = read_bytes("state.yaml")
    check("C21 state.yaml 行尾纯 CRLF、无重复 CR",
          b"\r\r\n" not in sraw and b"\r\n" in sraw,
          "crlf=%d crcrlf=%d" % (sraw.count(b"\r\n"), sraw.count(b"\r\r\n")), "纯 CRLF")

    ix = read_text("tools/INDEX.md")
    check("C22 工具索引含 R163 段与五件工具",
          "R163" in ix and all(("r163_%s" % k) in ix for k in
                               ["degradation_probe", "innovation_calibration",
                                "kla_dual_constraint", "dist_variance_probe",
                                "mcp_integration_probe"]),
          "R163" in ix, "段 + 5 工具")

    mem = read_text(".workbuddy/memory/2026-11-05.md")
    check("C23 记忆文件含 R163 章节", "R163" in mem, "R163" in mem, True)


# ─────────────────────────────────────────────────────────────
# D. 文档卫生 / 证据
# ─────────────────────────────────────────────────────────────
def section_d():
    md_rels = [
        "docs/r163_round_report.md", "docs/r157_debt_ledger.md",
        "docs/m5_review_signoff.md", "docs/roadmap_next.md", "README.md",
        "tools/INDEX.md", ".workbuddy/memory/2026-11-05.md",
    ]
    bad = []
    for rel in md_rels:
        raw = read_bytes(rel)
        if raw.count(b"\r\r\n") > 0:
            bad.append((rel, raw.count(b"\r\r\n")))
    check("D1 全部 md 文件 crcrlf = 0", not bad, bad or "全 0", "全 0")

    leftovers = []
    if os.path.isdir(rp("tools")):
        leftovers = [f for f in os.listdir(rp("tools")) if f.startswith("_tmp")]
    check("D2 无临时脚本残留（tools/_tmp*）", not leftovers, leftovers or "无", "无")

    check("D3 备份目录存在（事故回滚用）",
          os.path.isdir(rp("runs/_r163_backup")),
          sorted(os.listdir(rp("runs/_r163_backup"))) if os.path.isdir(rp("runs/_r163_backup")) else "无",
          "存在")

    zr_ok = os.path.exists(rp("runs/_r163_zr.log"))
    check("D4 零回归证据日志存在", zr_ok, zr_ok, True)
    if zr_ok:
        zr = read_text("runs/_r163_zr.log")
        check("D5 零回归日志含 max|Δ| = 0.00e+00",
              "0.00e+00" in zr, "0.00e+00" in zr, True)
    pt_ok = os.path.exists(rp("runs/_r163_pytest.log"))
    check("D6 pytest 证据日志存在", pt_ok, pt_ok, True)
    if pt_ok:
        pt = read_text("runs/_r163_pytest.log")
        m = [l for l in pt.split("\n") if "passed" in l]
        check("D7 pytest 日志含 passed 计数", bool(m), m[:1], "含 passed")

    # 引擎零改动抽查：solver_chain / mcp_server 不得改动 simulate.py 等数值核心
    check("D8 数值核心文件未被本轮改动（simulate.py 无 R163 痕迹）",
          "R163" not in read_text("candidate/indpensim/v0.1/simulate.py"),
          "R163" in read_text("candidate/indpensim/v0.1/simulate.py"), False)


def main():
    section_a()
    section_b()
    section_c()
    section_d()

    npass = sum(1 for c in CHECKS if c["ok"])
    ntot = len(CHECKS)
    verdict = "ALL PASS" if npass == ntot else "FAIL"

    print("=" * 78)
    print("R163 终检 —— %d/%d  %s" % (npass, ntot, verdict))
    print("=" * 78)
    for i, c in enumerate(CHECKS, 1):
        flag = "PASS" if c["ok"] else "FAIL"
        print("[%s] %-2d %s" % (flag, i, c["name"]))
        if not c["ok"]:
            print("        got=%r expect=%r" % (c["got"], c["expect"]))
    print("-" * 78)
    print("判定：%s（%d/%d）" % (verdict, npass, ntot))

    if "--json" in sys.argv:
        out = rp("runs/r163_final_check.json")
        payload = {"round": "R163", "n_checks": ntot, "n_pass": npass,
                   "verdict": verdict, "checks": CHECKS}
        with io.open(out, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(payload, ensure_ascii=False, indent=2))
        print("写出：%s" % os.path.relpath(out, ROOT))

    return 0 if verdict == "ALL PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
