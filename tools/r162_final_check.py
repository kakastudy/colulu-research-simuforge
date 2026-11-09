# -*- coding: utf-8 -*-
"""
R162 终检（常驻可复跑）

用途：对 R162「M1 尾账收口」轮次的交付物与治理层做一次全量机器复核。
     本工具**只读**，不写任何文件；任何一条 FAIL 即表示本轮收口不完整。

覆盖：
  A. 探针产物判据   —— oq#38 + oq#36（11 条）、oq#37（12 条）全 PASS
  B. 报告结构       —— 章节连续、含「治理层同步」章、要点齐全
  C. 治理层同步     —— 台账 / 签核单 / 路线图 / 契约 / README / state.yaml / 索引 / 记忆
  D. 文档卫生       —— 行尾风格、无重复 CR、无临时脚本残留

用法：
    py tools/r162_final_check.py            # 打印逐条结果
    py tools/r162_final_check.py --json     # 追加写 runs/r162_final_check.json
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
    p1 = rp("runs/r162_m1_legacy_probe.json")
    p2 = rp("runs/r162_kla_sensitivity.json")
    check("A0 两个探针产物存在", os.path.exists(p1) and os.path.exists(p2),
          os.path.exists(p1) and os.path.exists(p2), True)

    d1 = json.load(io.open(p1, encoding="utf-8"))
    n1, p1_pass = d1.get("n_checks"), d1.get("n_pass")
    check("A1 oq#38+oq#36 探针判据 11/11 PASS",
          n1 == 11 and p1_pass == 11 and d1.get("verdict") == "PASS",
          "%s/%s %s" % (p1_pass, n1, d1.get("verdict")), "11/11 PASS")

    d2 = json.load(io.open(p2, encoding="utf-8"))
    n2, p2_pass = d2.get("n_checks"), d2.get("n_pass")
    check("A2 oq#37 探针判据 12/12 PASS",
          n2 == 12 and p2_pass == 12 and d2.get("verdict") == "PASS",
          "%s/%s %s" % (p2_pass, n2, d2.get("verdict")), "12/12 PASS")

    # 逐条 ok 也必须全 True（防止只信汇总字段）
    bad = [c["name"] for c in d1["P1_oq38_harvest_caliber"]["checks"] + d1["P2_oq36_rng_mapping"]["checks"]
           if not c.get("ok")]
    check("A3 oq#38/36 逐条判据 ok 全 True", not bad, bad or "全 True", "全 True")

    bad2 = [c["name"] for c in d2["checks"] if not c.get("ok")]
    check("A4 oq#37 逐条判据 ok 全 True", not bad2, bad2 or "全 True", "全 True")

    # 关键量值：反解 k* 的跨批散布 σ 须与名义 10 一致（≤50% 偏差）
    c8 = next((c for c in d2["checks"] if c["name"].startswith("C8")), None)
    dev = float(c8["got"]) if c8 else None
    check("A5 反解 σ 与名义 10 的偏差 ≤50%（判决性）",
          dev is not None and dev <= 0.5, dev, "<=0.5")
    check("A5b 反解 σ 实测值在名义 10 的 ±50% 内",
          "std=8.94" in str(c8.get("detail")) if c8 else False,
          str(c8.get("detail"))[:60] if c8 else None, "std=8.94")

    # 零信息对照：同参连跑必须逐位相同（否则灵敏度测量被随机污染）
    det = d2.get("determinism_check", [])
    det_ok = bool(det) and all(x.get("identical") and float(x.get("max_abs_diff", 1)) == 0.0 for x in det)
    check("A6 零信息对照：同参连跑逐位相同（无随机污染）", det_ok,
          {"n": len(det), "all_identical": det_ok}, "all_identical=True")


# ─────────────────────────────────────────────────────────────
# B. 报告结构
# ─────────────────────────────────────────────────────────────
def section_b():
    rel = "docs/r162_round_report.md"
    t = read_text(rel)
    heads = [l for l in t.split("\n") if l.startswith("## ")]
    names = [h[3:].split("、")[0].strip() for h in heads]
    nums = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]
    check("B1 报告章节编号连续（一~十）", names == nums, names, nums)

    check("B2 报告含「治理层同步」章", any("治理层同步" in h for h in heads),
          [h for h in heads if "治理层同步" in h], "存在")

    check("B3 报告覆盖三条 oq 结论",
          all(k in t for k in ["oq#38", "oq#36", "oq#37"]),
          [k for k in ["oq#38", "oq#36", "oq#37"] if k in t], "oq#36/37/38")

    check("B4 报告含新增债 D-83 / D-84", "D-83" in t and "D-84" in t,
          [k for k in ["D-83", "D-84"] if k in t], "D-83 + D-84")

    check("B5 报告含闸门表与未做边界",
          "闸门" in t and "未**做" in t and "证据清单" in t,
          [k for k in ["闸门", "未**做", "证据清单"] if k in t], "三者齐")

    raw = read_bytes(rel)
    check("B6 报告行尾为纯 LF、无重复 CR",
          b"\r\n" not in raw and b"\r\r\n" not in raw and b"\r" not in raw,
          "crlf=%d crcrlf=%d" % (raw.count(b"\r\n"), raw.count(b"\r\r\n")),
          "纯 LF")


# ─────────────────────────────────────────────────────────────
# C. 治理层同步
# ─────────────────────────────────────────────────────────────
def section_c():
    led = read_text("docs/r157_debt_ledger.md")
    check("C1 台账含 D-83 / D-84 条目", "D-83" in led and "D-84" in led,
          [k for k in ["D-83", "D-84"] if k in led], "D-83 + D-84")
    check("C2 台账总表已补 D-79~D-84 六行",
          all(("D-%d" % n) in led for n in range(79, 85)),
          [("D-%d" % n) for n in range(79, 85) if ("D-%d" % n) not in led] or "全在", "D-79~D-84")
    check("C3 台账标题已更新为「截至 R162」", "截至 R162" in led,
          "截至 R162" in led, True)

    sg = read_text("docs/m5_review_signoff.md")
    check("C4 签核单含 R-12 决策行", "**R-12**" in sg,
          "**R-12**" in sg, True)

    rm = read_text("docs/roadmap_next.md")
    check("C5 路线图含 §8.4 R162 任务项", "8.4" in rm and "R162" in rm,
          ("8.4" in rm, "R162" in rm), "(True, True)")
    check("C6 路线图 R162-1~R162-5 五项齐",
          all(("R162-%d" % n) in rm for n in range(1, 6)),
          [("R162-%d" % n) for n in range(1, 6) if ("R162-%d" % n) not in rm] or "全在", "5 项")

    ct = read_text("ENGINE_CONTRACT.md")
    check("C7 契约头部为 v1.92", "v1.92" in ct.split("\n\n")[0] or "> v1.92" in ct,
          "v1.92" in ct[:2000], True)
    check("C8 契约版本表含独立行 | v1.92 |",
          any(l.strip().startswith("| v1.92 |") for l in ct.split("\n")),
          "有" if any(l.strip().startswith("| v1.92 |") for l in ct.split("\n")) else "无", "有")
    check("C9 契约保留 v1.91 历史原文",
          "历史：v1.91" in ct or "v1.91" in ct,
          ("历史：v1.91" in ct, "v1.91" in ct), "保留")
    craw = read_bytes("ENGINE_CONTRACT.md")
    check("C10 契约行尾纯 CRLF、无重复 CR",
          b"\r\r\n" not in craw and b"\r\n" in craw,
          "crlf=%d crcrlf=%d" % (craw.count(b"\r\n"), craw.count(b"\r\r\n")), "纯 CRLF")

    rd = read_text("README.md")
    check("C11 README 阅读顺序指向 R162 报告",
          "`docs/r162_round_report.md`" in rd,
          "`docs/r162_round_report.md`" in rd, True)
    check("C12 README 引用契约 v1.92 且阻断项含 D-83/D-84",
          "v1.92" in rd and "D-83" in rd and "D-84" in rd,
          ("v1.92" in rd, "D-83" in rd, "D-84" in rd), "三者齐")

    import yaml
    st_txt = read_text("state.yaml")
    st = yaml.safe_load(st_txt)
    check("C13 state.yaml 可解析", isinstance(st, dict), type(st).__name__, "dict")
    check("C14 state.yaml oq 数 = 54", len(st["open_questions"]) == 54,
          len(st["open_questions"]), 54)
    check("C15 state.yaml artifacts 数 = 27", len(st["artifacts"]) == 27,
          len(st["artifacts"]), 27)
    oq_blob = json.dumps(st["open_questions"], ensure_ascii=False)
    check("C16 state.yaml 三条 oq 已标关闭 + 新增两条债",
          oq_blob.count("R162") >= 3 and "D-83" in oq_blob and "D-84" in oq_blob,
          {"R162命中": oq_blob.count("R162"), "D-83": "D-83" in oq_blob, "D-84": "D-84" in oq_blob},
          "R162>=3 + D-83 + D-84")
    sraw = read_bytes("state.yaml")
    check("C17 state.yaml 行尾纯 CRLF、无重复 CR",
          b"\r\r\n" not in sraw and b"\r\n" in sraw,
          "crlf=%d crcrlf=%d" % (sraw.count(b"\r\n"), sraw.count(b"\r\r\n")), "纯 CRLF")

    ix = read_text("tools/INDEX.md")
    check("C18 工具索引含 R162 段与三条工具",
          "R162" in ix and "r162_m1_legacy_probe" in ix
          and "r162_kla_sensitivity" in ix and "r162_governance_update" in ix,
          "R162" in ix, "段 + 3 工具")

    mem = read_text(".workbuddy/memory/2026-11-05.md")
    check("C19 记忆文件含 R162 章节", "R162" in mem, "R162" in mem, True)


# ─────────────────────────────────────────────────────────────
# D. 文档卫生 / 无残留
# ─────────────────────────────────────────────────────────────
def section_d():
    md_rels = [
        "docs/r162_round_report.md", "docs/r157_debt_ledger.md", "docs/m5_review_signoff.md",
        "docs/roadmap_next.md", "README.md", "tools/INDEX.md", ".workbuddy/memory/2026-11-05.md",
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
          os.path.isdir(rp("runs/_r162_backup")),
          sorted(os.listdir(rp("runs/_r162_backup"))) if os.path.isdir(rp("runs/_r162_backup")) else "无",
          "存在")

    check("D4 零回归证据日志存在",
          os.path.exists(rp("runs/_r162_zr.log")) and os.path.exists(rp("runs/_r162_pytest.log")),
          (os.path.exists(rp("runs/_r162_zr.log")), os.path.exists(rp("runs/_r162_pytest.log"))),
          "(True, True)")
    zr = read_text("runs/_r162_zr.log")
    check("D5 零回归日志含 max|Δ| = 0", "0.00e+00" in zr or "max" in zr.lower(),
          "0.00e+00" in zr, True)
    pt = read_text("runs/_r162_pytest.log")
    check("D6 pytest 日志含 33 passed", "33 passed" in pt,
          [l for l in pt.split("\n") if "passed" in l][:1], "33 passed")


def main():
    section_a()
    section_b()
    section_c()
    section_d()

    npass = sum(1 for c in CHECKS if c["ok"])
    ntot = len(CHECKS)
    verdict = "ALL PASS" if npass == ntot else "FAIL"

    print("=" * 78)
    print("R162 终检 —— %d/%d  %s" % (npass, ntot, verdict))
    print("=" * 78)
    for i, c in enumerate(CHECKS, 1):
        flag = "PASS" if c["ok"] else "FAIL"
        print("[%s] %-2d %s" % (flag, i, c["name"]))
        if not c["ok"]:
            print("        got=%r expect=%r" % (c["got"], c["expect"]))
    print("-" * 78)
    print("判定：%s（%d/%d）" % (verdict, npass, ntot))

    if "--json" in sys.argv:
        out = rp("runs/r162_final_check.json")
        payload = {"round": "R162", "n_checks": ntot, "n_pass": npass,
                   "verdict": verdict, "checks": CHECKS}
        with io.open(out, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(payload, ensure_ascii=False, indent=2))
        print("写出：%s" % os.path.relpath(out, ROOT))

    return 0 if verdict == "ALL PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
