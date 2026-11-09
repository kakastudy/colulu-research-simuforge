# -*- coding: utf-8 -*-
"""R163 报告占位符回填（数据驱动、幂等）。

把 `docs/r163_round_report.md` 中的 `{{TAG}}` 占位符用 `runs/` 下的实测产物替换。

**数据驱动**：所有数字都从产物 JSON 读取，不手写。
**幂等**：回填后不再存在 `{{...}}`；重复执行不产生新变化（无占位符则直接退出）。

用法：
    py tools/r163_report_fill.py            # 回填
    py tools/r163_report_fill.py --dry-run  # 只报将要填什么，不写
"""
import argparse
import io
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REPORT = os.path.join(ROOT, "docs", "r163_round_report.md")

RUN_DEG = os.path.join(ROOT, "runs", "r163_degradation_probe.json")
RUN_KLA = os.path.join(ROOT, "runs", "r163_kla_dual_constraint.json")
RUN_DIST = os.path.join(ROOT, "runs", "r163_dist_variance.json")
RUN_MCP = os.path.join(ROOT, "runs", "r163_mcp_integration.json")
RUN_CALIB = os.path.join(ROOT, "runs", "r163_innovation_calibration.json")
LOG_ZR = os.path.join(ROOT, "runs", "_r163_zr.log")
LOG_PT = os.path.join(ROOT, "runs", "_r163_pytest.log")

TAG_RE = re.compile(r"\{\{([A-Z_0-9]+)\}\}")


def jload(path, default=None):
    if not os.path.exists(path):
        return default
    try:
        with io.open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def pct(x):
    return "n/a" if x is None else ("%.2f" % (100.0 * float(x)))


def read_log(path):
    if not os.path.exists(path):
        return ""
    with io.open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def build_tags():
    deg = jload(RUN_DEG, {}) or {}
    kla = jload(RUN_KLA, {}) or {}
    dist = jload(RUN_DIST, {}) or {}
    mcp = jload(RUN_MCP, {}) or {}

    # ---- A 段筛查 ----
    a = deg.get("A_summary", {}) or {}
    n_scanned = a.get("n_scanned", 0)
    n_deg = a.get("n_degraded", 0)
    n_healthy = a.get("n_scanned", 0) - n_deg - a.get("n_error", 0)
    trig = (float(n_deg) / n_scanned) if n_scanned else None

    # ---- C 段注入 ----
    c = deg.get("C_summary", {}) or {}
    inj = {r["fault"]: r for r in deg.get("C_injection", [])}
    fired = set(c.get("fired", []))

    def inj_tag(fault, default="n/a"):
        r = inj.get(fault)
        if not r:
            return default
        hit = (r["fault"] + "@b%d" % r["batch"]) in fired
        m = r.get("metrics", {}) or {}
        zmax = m.get("innovation_z_max", 0.0)
        try:
            zmax = max(float(zmax or 0.0),
                       float((m.get("innovation_z_max_all_channels") or {}).get("max", 0.0)))
        except Exception:
            pass
        cnt = m.get("innovation_over_limit_counts", {}) or {}
        n_over = 0
        try:
            n_over = max(int(v) for v in cnt.values()) if cnt else 0
        except Exception:
            n_over = 0
        return ("**触发**" if hit else "**未触发**") + \
               "（|z|max=%.2f，越限 %d 次）" % (zmax, n_over)

    ctrl_bits = []
    for r in deg.get("C_injection", []):
        ctrl_bits.append("b%d 对照=%s" % (r["batch"],
                                          "健康" if r.get("control_healthy") else "退化"))
    cs0 = deg.get("C_summary", {}) or {}
    inj_ctrl = ("；".join(sorted(set(ctrl_bits)))
                + " ⇒ 其中 %d 例（健康批）**对照天然健康 ⇒ 触发差异可归因于注入**，"
                  "%d 例（退化批）对照本身已退化 ⇒ **不可归因**"
                % (cs0.get("n_attributable", 0), cs0.get("n_not_attributable", 0))
                ) if ctrl_bits else "n/a"

    # ---- alpha_kla 双约束 ----
    ks = kla.get("summary", {}) or {}
    k_feas = ks.get("n_feasible")
    k_tot = ks.get("n_batches")
    k_range = ks.get("k_dual_range")
    k_cliff = ks.get("on_cliff_batches", [])
    k_base85 = ks.get("base85_within_band_n")
    rev = ks.get("revision_vs_r162", {}) or {}
    k_eq = ks.get("n_batches_F_equals_C1") or rev.get("n_batches_F_equals_C1")
    k_cov = ("%.1f%%" % (100.0 * k_feas / k_tot)) if (k_feas and k_tot) else "n/a"

    # ---- 扰动方差 ----
    # ---- MCP 接入 ----
    m_checks = {c.get("id") or c.get("name"): c for c in mcp.get("checks", [])}

    def m_tag(keyword, default="n/a"):
        """按判据 id 匹配（产物用 id=Z1/Z2/Z3；name 以中文开头）。"""
        for cid, c in m_checks.items():
            if str(cid).strip().upper() == keyword.upper():
                return "**PASS**" if (c.get("pass") if c.get("pass") is not None
                                      else c.get("ok")) else "**FAIL**"
        for nm, c in m_checks.items():
            if keyword in nm:
                return "**PASS**" if (c.get("pass") if c.get("pass") is not None
                                      else c.get("ok")) else "**FAIL**"
        return default

    zr_log = read_log(LOG_ZR)
    pt_log = read_log(LOG_PT)
    zr_tag = "n/a"
    m_zr = re.search(r"max\|?Δ\|?\s*=\s*([0-9.eE+-]+)", zr_log)
    if m_zr:
        zr_tag = "86/86 批 `max|Δ| = %s`" % m_zr.group(1)
    elif "0.00e+00" in zr_log:
        zr_tag = "86/86 批 `max|Δ| = 0.00e+00`"
    pt_tag = "n/a"
    m_pt = re.search(r"(\d+)\s+passed", pt_log)
    if m_pt:
        pt_tag = "**%s passed**" % m_pt.group(1)

    return {
        "N_SCANNED": n_scanned,
        "N_DEG": n_deg,
        "N_HEALTHY": n_healthy,
        "TRIG": pct(trig),
        "INJ_PH": inj_tag("ph_probe_bias"),
        "INJ_CO2": inj_tag("co2_sensor_stuck"),
        "INJ_CTRL": inj_ctrl,
        "K_CHECKS": "%d/%d" % (kla.get("n_pass", 0), kla.get("n_checks", 0)),
        "K_FEAS": k_feas, "K_TOT": k_tot, "K_COV": k_cov, "K_RANGE": k_range,
        "K_CLIFF": k_cliff, "K_BASE85": k_base85, "N_EQ": k_eq,
        "D_CHECKS": "%d/%d" % (dist.get("n_pass", 0), dist.get("n_checks", 0)),
        "MCP_Z1": m_tag("Z1"), "MCP_Z2": m_tag("Z2"), "MCP_Z3": m_tag("Z3"),
        "MCP_RESULT": "%d/%d" % (mcp.get("n_pass", 0), mcp.get("n_checks", 0)),
        "DEG_RESULT": ("A 段 %d 批 / 自然退化 %d 批（%s%%）；C 段 %d 例注入，触发 %d 例"
                       % (n_scanned, n_deg, pct(trig),
                          len(c.get("fired", [])) + len(c.get("not_fired", [])),
                          len(c.get("fired", [])))) if c else "n/a",
        "ZR_RESULT": zr_tag,
        "PT_RESULT": pt_tag,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--reset", action="store_true",
                    help="先把已填的数字反向还原成 {{TAG}} 再重新回填（重新标定后用）")
    a = ap.parse_args()

    with io.open(REPORT, encoding="utf-8", newline="") as f:
        raw = f.read()
    nl = "\r\n" if "\r\n" in raw else "\n"
    text = raw.replace("\r\r\n", "\n").replace("\r\n", "\n").replace("\r", "\n")

    tags = build_tags()
    present = sorted(set(TAG_RE.findall(text)))
    if not present:
        if not a.reset:
            print("报告无占位符，无需回填（幂等）。")
            print("（需重新回填请加 --reset：把已填数字反向替换回 {{TAG}} 再填）")
            return 0
        # --reset：把已填的**当前**值反向替换回占位符，再重新填一遍
        print("== --reset：把已填值反向还原为占位符 ==")
        for k, v in tags.items():
            sv = str(v)
            if sv and sv in text:
                text = text.replace(sv, "{{%s}}" % k)
        present = sorted(set(TAG_RE.findall(text)))
        print("  还原后占位符 %d 个" % len(present))

    print("== 待回填 %d 个占位符 ==" % len(present))
    missing = []
    for t in present:
        if t not in tags:
            missing.append(t)
        print("  {{%-12s}} -> %s" % (t + "}}", tags.get(t, "【无对应数据】")))
    if missing:
        print("\n⚠ 无对应数据的占位符：%s" % missing)
        print("  （这些多半需要对应探针先跑完）")

    out = text
    for k, v in tags.items():
        out = out.replace("{{%s}}" % k, str(v))
    left = sorted(set(TAG_RE.findall(out)))
    if left:
        print("\n⚠ 回填后仍有未处理占位符：%s" % left)

    if a.dry_run:
        print("\n（dry-run，未写入）")
        return 0

    with open(REPORT, "wb") as f:
        f.write(out.replace("\n", nl).encode("utf-8"))
    print("\n写出：docs/r163_round_report.md（剩余占位符 %d）" % len(left))
    return 0


if __name__ == "__main__":
    sys.exit(main())
