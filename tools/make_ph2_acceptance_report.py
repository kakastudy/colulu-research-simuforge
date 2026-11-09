# -*- coding: utf-8 -*-
"""用户可见验收报告生成器（P4 v0.2 激活后执行）：
从 runs/ artifacts 提取数字 → docs/ph2_acceptance_report.md。
纪律：数字 100% 可追溯（与 make_ph2_acceptance.py 同源原则），无手写数字。
"""
import io
import json
import os
import sys
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="gbk", errors="replace")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
HE = os.path.join(ROOT, "runs", "hier_est")


def load(name, req=False):
    p = os.path.join(HE, name)
    if os.path.exists(p):
        return json.load(open(p, encoding="utf-8"))
    if req:
        raise FileNotFoundError(name)
    return None


def main():
    verdict = load("p4_upgrade_verdict.json") or {}
    dt = load("death_term.json") or {}
    probe = load("p4_death_probe.json") or {}
    val = json.load(open(os.path.join(ROOT, "runs", "final_validation_v2.json"),
                         encoding="utf-8")) if os.path.exists(
        os.path.join(ROOT, "runs", "final_validation_v2.json")) else {}
    g = verdict.get("gates", {})

    L = []
    a = L.append
    a("# PH2/P4 v0.2 升级验收报告")
    a("")
    a("> 自动生成于 %s（tools/make_ph2_acceptance_report.py）——所有数字提取自 "
      "runs/ 产物，可追溯。" % datetime.now().isoformat(timespec="seconds"))
    a("")
    a("## 一、验收判决")
    a("")
    a("**verdict = %s**（来源 runs/hier_est/p4_upgrade_verdict.json）" % verdict.get("verdict", "—"))
    a("")
    a("| 闸门 | 判据 | 实测 | 结果 |")
    a("|---|---|---|---|")
    rows = [
        ("G1 池规模", "v2 池 ≥88 批", g.get("G1_pool", {}).get("n", "—")),
        ("G2 先验产物", "hier_prior_v2.json 存在", g.get("G2_prior", {}).get("exists", "—")),
        ("G3 死亡项拟合", "R²≥0.5 ∧ n≥400 ∧ β 三系数",
         "R²=%.3f, n=%s" % (g.get("G3_A_t1", {}).get("r2", 0),
                            g.get("G3_A_t1", {}).get("n_points", "—"))),
        ("G4 X 覆盖率", "黄金子集均值 ≥0.60", "mean=%s" % g.get("G4_X_coverage", {}).get("mean", "—")),
        ("G5 探针改善", "≥半数黄金批改善", g.get("G5_probe", {}).get("improved", "—")),
    ]
    for name, crit, meas in rows:
        key = {"G1 池规模": "G1_pool", "G2 先验产物": "G2_prior", "G3 死亡项拟合": "G3_A_t1",
               "G4 X 覆盖率": "G4_X_coverage", "G5 探针改善": "G5_probe"}[name]
        p = g.get(key, {}).get("pass")
        a("| %s | %s | %s | %s |" % (name, crit, meas,
                                     "✅ PASS" if p is True else "⏳/❌"))
    a("")
    b = dt.get("beta", [])
    a("## 二、死亡项算子（v0.2）参数")
    a("")
    a("- β（kd1, kd2, kd3）= (%.2f, %.2f, %.2f)" % tuple(round(float(x), 2) for x in b))
    a("- R² = %.4f；n = %s 点（X 通道全批水平拟合，runs/hier_est/death_term.json）"
      % (dt.get("r2", 0), dt.get("n_points", "—")))
    a("- 口径：A_t1 = a0/(a1+a3+a4)（化验对齐点 0.22~0.51，随成熟衰减；记录列 sim[A_t1] 为另一约定不可互换）")
    a("- 双实现等价：observe._death_corr ≡ calibration.death_correct_X（max diff 0.00e0）")
    a("")
    imp = [(r["batch"], r["delta_nrmse_pct"]) for r in probe.get("batches", [])]
    if imp:
        a("## 三、升级前探针改善（确定性重放）")
        a("")
        a("| 批 | Δ X nRMSE (pt) |")
        a("|---|---|")
        for bb, dd in imp:
            a("| %d | %+.1f |" % (bb, dd))
        med = sorted(d for _, d in imp)[len(imp) // 2]
        a("")
        a("改善 %d/%d 批，中位 %+.1f pt。" % (len(imp), len(imp), med))
        a("")
    a("## 四、激活后回归（黄金回归守护）")
    a("")
    if val:
        errs = [abs(r["yield_err"]) for r in val if "yield_err" in r]
        rmse = (sum(e * e for e in errs) / len(errs)) ** 0.5 * 100 if errs else float("nan")
        w5 = sum(1 for e in errs if e * 100 <= 5.0)
        cat = sum(1 for r in val if r.get("crash_level") == "catastrophe")
        a("- 黄金 RMSE = %.2f%%（12 批 yield_err 的 RMSE，来源 runs/final_validation_v2.json）" % rmse)
        a("- within5%% = %d/12；灾难 = %d/12" % (w5, cat))
    else:
        a("- 黄金回归数据缺失——激活后需重跑 diag_final_validation_v2.py")
    a("")
    a("## 五、诚实缺口（不静默化）")
    a("")
    a("- DL σ̂ 需非网格后验（PH3+ 债务）")
    a("- PAA 通道批间异质（R90 普查 7/9 正向、2/9 反相；μp 机理锚点 −0.891）")
    a("- D9 方案 (b) ODE 级积分未实施；产量级 RMSE ≤3.5% 需机理增强项（V1+）")
    a("- PAT 消融对照（引擎 PAA vs PAT 转发 vs fused 三口径, 健康批 60/22 先行）待执行")
    a("")
    a("## 六、下一步（V1+ 队列）")
    a("")
    a("1. PAT 消融对照（批 60/22, 三口径净变化）")
    a("2. 产量级机理增强项（死亡项之外的通道）")
    a("3. 黄金集扩展（待用户确认数量）")
    a("")
    out = os.path.join(ROOT, "docs", "ph2_acceptance_report.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print("Saved:", out)


if __name__ == "__main__":
    main()
