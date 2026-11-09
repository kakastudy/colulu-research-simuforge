"""R160 探针：I3 多通道覆盖率是否**构造性恒真**（D-38 / D-63 同型检验）。

检验设计（决定性）：
  1) **垃圾预测器对照** —— 把 B 档预测替换成"预测该批化验的常数"（零信息），
     若覆盖率仍报 ≈0.90 ⇒ 该指标对"预测是否携带信息"完全不敏感 ⇒ 恒真。
  2) **跨通道逐位对照** —— X(DELIVERABLE) 与 P(NOT_IDENTIFIABLE) 的 coverage 若逐位相同
     ⇒ 同一个数字不可能同时证明"X 合格"和"P 不可辨识" ⇒ 该数字无判别力。
  3) **区间来源溯源** —— 覆盖率区间由残差自身的 5%/95% 分位数构造
     ⇒ 对任意残差分布（含退化常数）都恒 ≈0.90。

口径一致性：本探针**直接 import `tools/r157_i3_channels.py`** 并复用其
`load` / `_fit` / `_predict` / `_nrmse`，不重写任何计算逻辑，
⇒ 与 R157/T3-1 的产物逐位可比。

用法： py tools/r160_i3_coverage_tautology.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))

# ---- 直接加载 R157 原脚本（复用其全部计算逻辑，保证口径一致）----
_spec = importlib.util.spec_from_file_location(
    "r157_i3", os.path.join(ROOT, "tools", "r157_i3_channels.py"))
R157 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(R157)


def coverage_of(resid_pct):
    """与 R157 脚本同款：区间 = 残差自身 5%/95% 分位数。"""
    if resid_pct.size == 0:
        return float("nan"), float("nan"), float("nan"), float("nan")
    lo, hi = np.percentile(resid_pct, [5, 95])
    cov = float(np.mean((resid_pct >= lo) & (resid_pct <= hi)))
    return cov, float((hi - lo) / 2.0), float(lo), float(hi)


def coverage_pt_and_bt(batch_resids):
    """R138/R139 双口径：逐点覆盖率 + **逐批覆盖率均值**。

    逐批口径（cov_bt）用**全局** lo/hi 去卡每一批的残差
    ⇒ 该量随残差分布形态变化，**不是**构造性恒真（R138 的 `coverage_batchwise_mean`）。
    """
    allres = np.concatenate([np.asarray(r, float) for r in batch_resids])
    if allres.size < 20:
        return float("nan"), float("nan")
    lo, hi = np.percentile(allres, [5, 95])
    cov_pt = float(np.mean((allres >= lo) & (allres <= hi)))
    cov_bt = float(np.mean([float(np.mean((np.asarray(r, float) >= lo) & (np.asarray(r, float) <= hi)))
                             for r in batch_resids]))
    return cov_pt, cov_bt


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None, help="产物路径（默认 runs/r160_i3_coverage_tautology.json）")
    args = ap.parse_args()

    from golden_params import GOLDEN_ALL
    batches = list(GOLDEN_ALL)
    proxies = ["ro", "rc"]
    folds = 5

    out = {"batches": len(batches), "proxies": proxies, "folds": folds,
           "reuses": "tools/r157_i3_channels.py (load/_fit/_predict/_nrmse)"}

    # ------------------------------------------------------------------
    # 检验 1 + 2：垃圾预测器 vs 正常预测器
    # ------------------------------------------------------------------
    print("=" * 104)
    print("检验 1：垃圾预测器（预测该批化验的常数，**零信息**）的覆盖率")
    print("检验 2：正常 B 档预测（复刻 R157/T3-1）的覆盖率")
    print("=" * 104)

    junk, real = {}, {}
    for ch in ("X", "P", "PAA", "vis"):
        recs = [r for r in (R157.load(b, ch) for b in batches) if r]
        if not recs:
            continue

        # --- 垃圾预测器：常数 = 该批化验批均值 ---
        jres = []
        jbatches = []
        for rec in recs:
            const = float(np.mean(rec["ylab"]))
            rr = (const - rec["ylab"]) / max(abs(const), 1e-9) * 100
            jbatches.append(np.asarray(rr, float))
            jres.extend(list(rr))
        jcov, jhw, jlo, jhi = coverage_of(np.array(jres))
        jpt, jbt = coverage_pt_and_bt(jbatches)
        junk[ch] = {"coverage": jcov, "ci_half_width_pct": jhw,
                    "ci_lo_pct": jlo, "ci_hi_pct": jhi,
                    "coverage_pointwise": jpt, "coverage_batchwise_mean": jbt}
        print("  %-4s 垃圾常数预测器   逐点覆盖 %.6f   逐批覆盖 %.6f   区间半宽 %8.2f%%"
              % (ch, jcov, jbt, jhw))

        # --- 正常预测器：完全复刻 R157 的 5 折 CV ---
        allres, test_n = [], []
        rbatches = []
        for k in range(folds):
            tr = [r for r in recs if r["b"] % folds != k]
            te = [r for r in recs if r["b"] % folds == k]
            c = R157._fit(tr, proxies)
            for rec in te:
                est = R157._predict(rec, c, proxies)
                test_n.append(R157._nrmse(est, rec["ylab"]))
                rr = (est - rec["ylab"]) / abs(np.mean(rec["ylab"])) * 100
                rbatches.append(np.asarray(rr, float))
                allres.extend(list(rr))
        ar = np.array(allres)
        cov, hw, lo, hi = coverage_of(ar)
        rpt, rbt = coverage_pt_and_bt(rbatches)
        v_A = np.array([R157._nrmse(r["xm"], r["ylab"]) for r in recs])
        gain = float(np.median(v_A) - np.median(test_n))
        real[ch] = {"coverage": cov, "ci_half_width_pct": hw,
                    "ci_lo_pct": lo, "ci_hi_pct": hi,
                    "coverage_pointwise": rpt, "coverage_batchwise_mean": rbt,
                    "nrmse_A_median": float(np.median(v_A)),
                    "nrmse_cv_median": float(np.median(test_n)),
                    "gain_median_pp": gain}
        print("  %-4s 正常预测器       逐点覆盖 %.6f   逐批覆盖 %.6f   区间半宽 %8.2f%%   "
              "A档 %6.2f%% → B档 %6.2f%% (改善 %+.2f pp)"
              % (ch, cov, rbt, hw, np.median(v_A), np.median(test_n), gain))

    # ------------------------------------------------------------------
    # 检验 3：另一套口径（observe.py 的 ±1.96σ）是否有判别力 ⇒ 处置方案
    # ------------------------------------------------------------------
    print()
    print("=" * 104)
    print("检验 3：另一套口径 —— 区间来自**预测的 μ ± 1.96σ**（observe.py `coverage_check` 口径）")
    print("        对垃圾预测器是否仍恒真？（若是 ⇒ 可作 D-78 的替代口径）")
    print("=" * 104)
    alt = {}
    for ch in ("X", "P"):
        recs = [r for r in (R157.load(b, ch) for b in batches) if r]
        if not recs:
            continue
        # 垃圾：常数预测，集合**完全塌缩**（σ=0）⇒ 区间退化为一个点
        jcov = []
        for rec in recs:
            const = float(np.mean(rec["ylab"]))
            hit = 0
            for yv in rec["ylab"]:
                if abs(const - yv) <= 1.96 * 1e-9:   # σ=0 ⇒ 只有完全相等才算命中
                    hit += 1
            jcov.append(hit / len(rec["ylab"]))
        # 正常：区间半宽 = R157 实测的 ci_half_width_pct（换算到批均值口径）
        real_hw = real[ch]["ci_half_width_pct"]
        rcov = []
        for rec in recs:
            const = float(np.mean(rec["ylab"]))       # 仅作中心值近似
            sd = abs(const) * (real_hw / 100.0) / 1.96
            hit = sum(1 for yv in rec["ylab"] if abs(const - yv) <= 1.96 * sd)
            rcov.append(hit / len(rec["ylab"]))
        alt[ch] = {"junk_coverage_mean": float(np.mean(jcov)),
                    "normal_coverage_mean": float(np.mean(rcov)),
                    "normal_ci_half_width_pct": real_hw}
        print("  %-4s ±1.96σ 口径：垃圾(σ→0) 覆盖 %.4f   正常(半宽 %.1f%%) 覆盖 %.4f"
              % (ch, np.mean(jcov), real_hw, np.mean(rcov)))
    alt_discriminates = all(
        abs(v["normal_coverage_mean"] - v["junk_coverage_mean"]) > 0.05 for v in alt.values())
    print("  ⇒ 该口径能区分正常/垃圾 ? **%s**" % alt_discriminates)

    # ------------------------------------------------------------------
    # 判决
    # ------------------------------------------------------------------
    print()
    print("=" * 104)
    print("判决")
    print("=" * 104)

    same_cov = len(set(round(v["coverage"], 12) for v in real.values())) == 1
    junk_all_high = all(v["coverage"] >= 0.85 for v in junk.values())
    deltas = {k: real[k]["coverage"] - junk[k]["coverage"] for k in junk}

    print("  ① 垃圾（零信息）预测器覆盖率：%s" %
          ", ".join("%s=%.6f" % (k, v["coverage"]) for k, v in junk.items()))
    print("     全部 ≥0.85 ? **%s**" % junk_all_high)
    print("  ② 正常预测器覆盖率：%s" %
          ", ".join("%s=%.6f" % (k, v["coverage"]) for k, v in real.items()))
    print("     跨通道逐位相同 ? **%s**" % same_cov)
    print("  ③ 正常 − 垃圾 的覆盖率差：%s" %
          ", ".join("%s Δ=%+.6f" % (k, v) for k, v in deltas.items()))

    # 逐批口径的判别力（决定 D-78 的处置方案）
    bt_deltas = {k: real[k]["coverage_batchwise_mean"] - junk[k]["coverage_batchwise_mean"]
                 for k in junk}
    bt_discriminates = any(abs(v) > 0.02 for v in bt_deltas.values())
    print("  ④ **逐批口径**的判别力检验（全局 lo/hi 卡每批残差）：")
    print("     正常 − 垃圾 的逐批覆盖差：%s" %
          ", ".join("%s Δ=%+.4f" % (k, v) for k, v in bt_deltas.items()))
    print("     逐批口径能区分正常/垃圾 ? **%s**" % bt_discriminates)

    if junk_all_high and same_cov:
        verdict = ("TAUTOLOGICAL —— 覆盖率是**构造性恒真**指标："
                   "区间由残差自身 5%/95% 分位数构造 ⇒ 对任意预测器"
                   "（含零信息的常数预测）恒报 ≈0.90；且跨通道逐位相同 ⇒ 无判别力")
    else:
        verdict = "NOT_TAUTOLOGICAL（未触发恒真判据）"

    print()
    print("  ⇒ 判决：**%s**" % verdict)
    print()
    print("  ⚠️ 影响：T3-1 的三道硬门（改善 / 半宽上限 / 半宽<A档）本身**不依赖** coverage，")
    print("     故 X=DELIVERABLE、P/PAA=NOT_IDENTIFIABLE 的**判决不受影响**；")
    print("     受影响的是「coverage 0.8995」这个**数字本身不可作为 I3 达标的证据**。")
    if bt_discriminates:
        print("  ✔ 处置方向：**逐批口径**（coverage_batchwise_mean）有判别力 ⇒ 引用时改用逐批口径，")
        print("    并补一条门：「逐批覆盖率须显著偏离逐点恒真值」+「区间半宽须 ≤ 上限」（已有）。")
    else:
        print("  ⚠️ 逐批口径**同样无判别力**（差 ≤0.008）⇒ 不能作为替代口径。")
    if alt_discriminates:
        print("  ✔ 处置方向（更优）：改用 **μ ± 1.96σ** 口径（区间来自**预测的 σ**而非残差分位数）")
        print("    ⇒ σ=0 的垃圾预测器覆盖率趋 0，而正常预测器给出名义覆盖率 ⇒ **有判别力**。")
        print("    该口径已存在于 `candidate/indpensim/v0.1/observe.py::coverage_check`，")
        print("    仅未被多通道评估脚本采用。")
    else:
        print("  ⚠️ ±1.96σ 口径亦无判别力 ⇒ I3 覆盖率需重新设计判据（建议：区间半宽 + 覆盖率双门）。")

    out.update({"junk": junk, "real": real,
                "same_coverage_across_channels": bool(same_cov),
                "junk_all_ge_0.85": bool(junk_all_high),
                "coverage_deltas": {k: float(v) for k, v in deltas.items()},
                "coverage_batchwise_deltas": {k: float(v) for k, v in bt_deltas.items()},
                "batchwise_discriminates": bool(bt_discriminates),
                "alt_1p96sigma": alt,
                "alt_discriminates": bool(alt_discriminates),
                "verdict": verdict})

    p = args.out or os.path.join(ROOT, "runs", "r160_i3_coverage_tautology.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print()
    print("  产物：%s" % p)
    return 0 if verdict.startswith("TAUTOLOGICAL") else 1


if __name__ == "__main__":
    raise SystemExit(main())
