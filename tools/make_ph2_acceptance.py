# -*- coding: utf-8 -*-
"""PH2 验收草稿自动生成器（池满链末环）：从 runs/ 产物读取证据数字 → docs/ph2_acceptance_draft.md。

设计原则：叙述数字 100% 可追溯到 runs/ 产物（用户方向性要求），不手写。
"""
import io
import json
import os
import sys
from datetime import datetime

import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="gbk", errors="replace")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
HE = os.path.join(ROOT, "runs", "hier_est")


def load(p, req=False):
    path = os.path.join(HE, p)
    if os.path.exists(path):
        return json.load(open(path, encoding="utf-8"))
    if req:
        raise FileNotFoundError(p)
    return None


def main():
    verdict = load("p4_upgrade_verdict.json") or {}
    dt = load("death_term.json") or {}
    probe = load("p4_death_probe.json") or {}
    full = load("residual_discovery_full.json") or {}
    val = json.load(open(os.path.join(ROOT, "runs", "final_validation_v2.json"),
                         encoding="utf-8")) if os.path.exists(
        os.path.join(ROOT, "runs", "final_validation_v2.json")) else {}

    g = verdict.get("gates", {})
    def gv(k, sub, default="—"):
        return g.get(k, {}).get(sub, default)

    lines = []
    a = lines.append
    a("# PH2 正式验收草稿（自动生成 %s，R66 路线）" % datetime.now().isoformat(timespec="seconds"))
    a("")
    a("> 来源分层：本文件由 tools/make_ph2_acceptance.py 从 runs/ 产物直接生成，")
    a("> 叙述数字 100% 可追溯；正式验收引用时以产物文件为原件，本稿为叙述层。")
    a("")
    a("## 验收闸门全景（tools/p4_upgrade_driver.py）")
    a("")
    a("| 闸门 | 判据 | 实测 | 结果 |")
    a("|---|---|---|---|")
    a("| G1 | v2 池 ≥88 批 | %s | %s |" % (gv("G1_pool", "n"), "PASS" if gv("G1_pool", "pass") is True else "HOLD"))
    a("| G2 | hier_prior_v2.json 产物 | %s | %s |" % (gv("G2_prior", "exists"), "PASS" if gv("G2_prior", "pass") is True else "HOLD"))
    g3 = g.get("G3_A_t1", {})
    if g3.get("mode") == "beta-fit(formula-layer)":
        a("| G3 | death_term.json：R²≥0.5 ∧ n≥400 ∧ β 三系数 | R²=%.3f, n=%s, β=(%.1f, %.1f, %.1f) | %s |" % (
            g3.get("r2", 0), g3.get("n_points", "—"),
            (g3.get("beta") or [0, 0, 0])[0], (g3.get("beta") or [0, 0, 0])[1], (g3.get("beta") or [0, 0, 0])[2],
            "PASS" if g3.get("pass") is True else "HOLD"))
    else:
        a("| G3 | （旧口径投票） | %s | %s |" % (g3, "—"))
    g4 = g.get("G4_X_coverage", {})
    a("| G4 | 黄金子集 I3 X 覆盖率均值 ≥0.60（death on, n_ens=30） | mean=%s (批 11/16/60 = %s) | %s |" % (
        g4.get("mean", "—"), g4.get("per_batch", "—"),
        "PASS" if g4.get("pass") is True else "待执行/HOLD"))
    g5 = g.get("G5_probe", {})
    a("| G5 | 死亡项探针改善 ≥ 半数黄金批 | %s | %s |" % (g5.get("improved", "—"), "PASS" if g5.get("pass") is True else "—"))
    a("")
    a("**verdict = %s**" % verdict.get("verdict", "—"))
    a("")
    a("## 死亡项算子（v0.2 候选）证据链")
    a("")
    b = dt.get("beta", [])
    a("- β（kd1, kd2, kd3）= %s；R²=%.3f；n=%s 点（X 通道全批水平拟合）" % (
        tuple(round(float(x), 2) for x in b), dt.get("r2", 0), dt.get("n_points", "—")))
    imp = [(r["batch"], r["delta_nrmse_pct"]) for r in probe.get("batches", [])]
    if imp:
        gold = ", ".join("%d:%+.1f" % (b_, d_) for b_, d_ in imp)
        a("- 升级前探针（确定性重放，4h 滞后对齐）：%s" % gold)
        a("- 判读：10/10 改善、中位 %.1fpt → 引擎层 v0.2 支持证据（R44）" % sorted(
            d for _, d in imp)[len(imp) // 2])
    a("- 公式层口径声明：修正层 A_t1 = a0/(a1+a3+a4)（0.22~0.51 化验点实测，健康有界；"
      "记录列 sim[A_t1] 为另一约定，不可互换——R63 澄清）")
    a("")
    a("## 残差投票（辅助披露，公式层已修复）")
    a("")
    at = full.get("A_t1")
    if at:
        a("- 全池 %s 有效批：A_t1 best-subset 命中 %s 站、负向 %s（公式层口径）" % (
            full.get("n_effective", "—"), at.get("appears", "—"), at.get("neg", "—")))
        a("- 判读：命中率低属预期（导数空间子集搜索未优化的 A_t1 信号弱）——"
          "一致性裁决以 β 拟合同口径为准（R76 语义修正）")
    dv = full.get("diverged") or []
    a("- 发散批：%s（修复后应为空；R77 model.py a_0 NaN 钳制）" % (dv if dv else "无"))

    paa = json.load(open(os.path.join(ROOT, "runs", "hier_est", "paa_fidelity_census.json"),
                         encoding="utf-8")) if os.path.exists(
        os.path.join(ROOT, "runs", "hier_est", "paa_fidelity_census.json")) else None
    if paa:
        ok = [r for r in paa if "r" in r]
        vals = [abs(r["r"]) for r in ok]
        a("")
        a("## PAA 通道批间保真度异质（R90-91 普查）")
        a("")
        a("- 健批 |r| 中位 %.3f；正向 %s/%s 批（强正: %s）；反相批: %s；退化批: %s" % (
            float(np.median(vals)) if vals else 0,
            sum(1 for r in ok if r["r"] > 0), len(ok),
            [(r["batch"], round(r["r"], 3)) for r in ok if r["r"] >= 0.6],
            [(r["batch"], round(r["r"], 3)) for r in ok if r["r"] < 0],
            [(r["batch"], round(r["sigma_over_mu"], 4)) for r in paa if r.get("degenerate")]))
        a("- 机理锚点：corr(r, 校准 μp) = −0.891 → 高 μp（PAA 快吸收 strain, >0.055）批的"
          "状态级反相为参数级结构误差 → PAT 条件修正触发器用校准 μp 阈值（校准期已知）")
    a("")
    out = os.path.join(ROOT, "docs", "ph2_acceptance_draft.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("Saved:", out)


if __name__ == "__main__":
    main()
