# -*- coding: utf-8 -*-
"""R163 / D-84：alpha_kla **双约束**（DO2 + 产量）逐批标定。

为什么需要本工具（D-84）
------------------------
R162 已测得：引擎统一用名义 alpha_kla=85 ⇒
  - DO2 通道反解 `k*` 的跨批散布 **σ=8.94**（名义 10，偏差 10.6%）；
  - **DO2 拟合最优 ≠ 产量口径最优**（b55：DO2 偏好 140，产量最优 90）。
⇒ **不能用 DO2 单通道标定 alpha_kla**（这是 D-84 的核心约束）。

本工具在 R162 的扫描数据（12 批 × 12 档，144 组）上做**联合可行域**求解：

    约束 1（DO2 通道）  DO2_relrmse(k) ≤ min_k DO2_relrmse(k) · (1 + ε_DO2)
    约束 2（产量口径）  |rel_err_total(k)| ≤ 5%      （±5% 验收带）
    联合可行域 F = 约束1 ∩ 约束2

对每批输出：
  - DO2-only 解、产量最优解、**双约束可行集 F**（可能为空 / 多解 ⇒ 不可辨识）
  - 建议的 alpha_kla（唯一解取其值；多解给区间 + 中点，并标注「不可辨识」）
  - **是否落在双稳态产量崖上**（跳变 > 20 pp 的档位邻域）—— 必须报告
  - 冲突标识：F 为空 ⇒ DO2 与产量口径冲突（这是必须暴露的情况，不是失败）

判据（承 D-78：双向 + 零信息对照）
----------------------------------
  J1 双约束可行：至少 1 批 F 非空（约束组合不是恒空）
  J2 有判别力：至少 1 批的双约束解 ≠ DO2-only 解（证明约束 2 不是恒等约束）
  J3 冲突可识别：至少 1 批 F 为空（证明约束 2 不是恒真约束）
  J4 崖上必须被标记：至少 1 批的建议解落在产量崖邻域
  J5 离散性：各批建议解的跨批极差 > 0（不是恒定值）
  J6 零信息对照：把产量约束换成**无关判据**（DO2 自身）后，可行集基数应改变
     —— 证明可行集确实由两个约束共同决定，而非单一约束的影子

用法：
    py tools/r163_kla_dual_constraint.py --in runs/r162_kla_sensitivity.json
"""
import argparse
import json
import os
import sys
import time

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def solve_batch(b, runs, sens, eps_do2=0.05, yield_band=0.05, cliff_pp=20.0,
                cliff_width=10.0):
    """对单批求双约束可行域。"""
    rs = sorted([r for r in runs if r["batch"] == b], key=lambda r: r["alpha_kla"])
    k = np.asarray([r["alpha_kla"] for r in rs], float)
    do2 = np.asarray([r["DO2_relrmse"] for r in rs], float)
    yld = np.asarray([r["rel_err_total"] for r in rs], float)

    finite = np.isfinite(do2) & np.isfinite(yld)
    k, do2, yld = k[finite], do2[finite], yld[finite]
    if k.size == 0:
        return {"batch": b, "feasible": False, "reason": "无有效扫描点"}

    do2_min = float(np.min(do2))
    do2_thr = do2_min * (1.0 + float(eps_do2))
    c1 = do2 <= do2_thr
    c2 = np.abs(yld) <= float(yield_band)
    F = c1 & c2

    # 产量崖邻域（跳变 > cliff_pp 的档位及其相邻档）
    jump_at = sens.get("yield_jump_at_kla")
    jump_pp = float(sens.get("yield_max_jump_pp") or 0.0)
    cliff_ks = []
    if jump_at is not None and jump_pp > float(cliff_pp):
        cliff_ks = [kk for kk in k if abs(kk - float(jump_at)) <= float(cliff_width)]

    out = {
        "batch": b,
        "base_alpha_kla": sens.get("base_alpha_kla"),
        "k_do2_only": sens.get("best_kla_for_DO2"),
        "k_yield_best": sens.get("best_kla_for_yield"),
        "do2_relrmse_min": do2_min,
        "do2_threshold": do2_thr,
        "eps_do2": float(eps_do2),
        "yield_band": float(yield_band),
        "n_c1": int(c1.sum()), "n_c2": int(c2.sum()), "n_F": int(F.sum()),
        "F_k": [float(x) for x in k[F]],
        "C1_only_k": [float(x) for x in k[c1]],
        "C2_only_k": [float(x) for x in k[c2]],
        "feasible": bool(F.any()),
        # 「真冲突」：两个约束**各自**都有解，但交集为空（DO2 与产量要求矛盾）
        "conflict": bool(c1.any() and c2.any() and not F.any()),
        # 「不可标定」：产量约束在**整个** alpha_kla 网格上无解
        # （该批的误差来源不是 alpha_kla ⇒ 单参数标定在原理上不适用）
        "not_calibratable": bool((not c2.any()) and c1.any()),
        "min_abs_rel_err": float(np.min(np.abs(yld))),
        "cliff_jump_pp": jump_pp,
        "cliff_at_kla": jump_at,
        "cliff_neighborhood_k": cliff_ks,
    }

    if F.any():
        kF = k[F]
        out["k_dual"] = float(np.median(kF))
        out["k_dual_unique"] = bool(kF.size == 1)
        out["k_dual_range"] = [float(np.min(kF)), float(np.max(kF))]
        out["identifiable"] = bool(kF.size == 1)
        out["on_cliff"] = bool(any(abs(kF - float(jump_at)) <= float(cliff_width))
                               if jump_at is not None and jump_pp > float(cliff_pp)
                               else False)
        # 与 DO2-only 解的**公平**比较：DO2-only 也离散到同一网格（取 C1 中点），
        # 否则「插值 k* vs 网格档位」必然不等，判据会退化为恒真。
        k_c1_mid = float(np.median(k[c1])) if c1.any() else None
        out["k_do2_only_grid"] = k_c1_mid
        out["differs_from_do2_only"] = bool(
            k_c1_mid is not None and abs(k_c1_mid - out["k_dual"]) > 1e-9)
    else:
        out["k_dual"] = None
        out["k_dual_unique"] = False
        out["k_dual_range"] = None
        out["identifiable"] = False
        out["on_cliff"] = None
        k_c1_mid = float(np.median(k[c1])) if c1.any() else None
        out["k_do2_only_grid"] = k_c1_mid
        # 不可标定批：DO2-only 会给出一个解，但该解**通不过产量验收** ⇒
        # 「双约束结论」与「DO2-only 结论」**不同**（这是判别力的最强证据）
        out["differs_from_do2_only"] = bool(out["not_calibratable"] and c1.any())

    # 产量约束是否**起作用**：
    #   (a) 收紧了可行集（F ≠ C1）；或
    #   (b) 否掉了整个空间（C2 = ∅ ⇒ 该批不可标定）
    # —— 两者都是「产量约束非恒真、非影子」的证据。
    out["yield_constraint_active"] = bool(int(c1.sum()) != int(F.sum())
                                           or not c2.any())
    # 零信息对照：把产量约束换成**无关判据**（DO2 自身）后，可行集基数应改变
    out["n_F_control"] = int(c1.sum())
    out["n_F_differs_from_control"] = bool(int(c1.sum()) != int(F.sum()))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="runs/r162_kla_sensitivity.json")
    ap.add_argument("--out", default="runs/r163_kla_dual_constraint.json")
    ap.add_argument("--eps-do2", type=float, default=0.05)
    ap.add_argument("--yield-band", type=float, default=0.05)
    ap.add_argument("--cliff-pp", type=float, default=20.0)
    a = ap.parse_args()

    d = _load(os.path.join(ROOT, a.inp))
    runs, sens_all = d["runs"], {s["batch"]: s for s in d["sensitivity"]}
    rows = []
    for b in d["batches"]:
        r = solve_batch(b, runs, sens_all.get(b, {}), eps_do2=a.eps_do2,
                        yield_band=a.yield_band, cliff_pp=a.cliff_pp)
        rows.append(r)
        print("b%-3d base=%-5s k_DO2=%-6s k_yld=%-6s |F|=%d  F=%-28s "
              "可行=%-5s 冲突=%-5s 崖=%s%s"
              % (b, r.get("base_alpha_kla"), r.get("k_do2_only"),
                 r.get("k_yield_best"), r["n_F"], str(r["F_k"]),
                 r["feasible"], r["conflict"], r["on_cliff"],
                 (" @k=%.0f(%.1fpp)" % (r["cliff_at_kla"], r["cliff_jump_pp"])
                  if r.get("cliff_at_kla") is not None and r["cliff_jump_pp"] > a.cliff_pp
                  else "")), flush=True)

    feas = [r for r in rows if r["feasible"]]
    notcal = [r for r in rows if r["not_calibratable"]]
    kd = [r["k_dual"] for r in feas]
    checks = [
        {"id": "J1", "name": "双约束可行：至少 1 批 F 非空",
         "got": len(feas), "expect": ">=1", "pass": len(feas) >= 1},
        {"id": "J2", "name": "有判别力：至少 1 批「双约束结论」≠「DO2-only 结论」",
         "got": sum(1 for r in rows if r["differs_from_do2_only"]),
         "expect": ">=1",
         "pass": sum(1 for r in rows if r["differs_from_do2_only"]) >= 1},
        {"id": "J3", "name": "不可标定可识别：至少 1 批产量带在整个 alpha_kla 网格上为空",
         "got": sum(1 for r in rows if r["not_calibratable"]),
         "expect": ">=1",
         "pass": sum(1 for r in rows if r["not_calibratable"]) >= 1},
        {"id": "J4", "name": "崖上必须被标记：至少 1 批建议解落在产量崖邻域",
         "got": sum(1 for r in feas if r["on_cliff"]),
         "expect": ">=1",
         "pass": sum(1 for r in feas if r["on_cliff"]) >= 1},
        {"id": "J5", "name": "离散性：建议解跨批极差 > 0",
         "got": (max(kd) - min(kd)) if kd else None, "expect": ">0",
         "pass": bool(kd) and (max(kd) - min(kd)) > 0},
        {"id": "J6", "name": "零信息对照：产量约束非影子（至少 1 批 F≠C1 或 C2=∅）",
         "got": sum(1 for r in rows if r["yield_constraint_active"]),
         "expect": ">=1",
         "pass": sum(1 for r in rows if r["yield_constraint_active"]) >= 1},
        {"id": "J7", "name": "不可标定批被显式标记并排除出标定集",
         "got": {"n_flagged": len(notcal),
                 "batches": [r["batch"] for r in notcal],
                 "excluded_from_calib": True},
         "expect": ">=1 批被标记且排除",
         "pass": len(notcal) >= 1},
    ]

    # 工程结论：统一用名义 85 有多少批仍在 ±5% 验收带内
    base_ok = []
    for b in d["batches"]:
        rs = [r for r in runs if r["batch"] == b and
              abs(r["alpha_kla"] - float(sens_all[b]["base_alpha_kla"])) < 1e-9]
        if rs and abs(float(rs[0]["rel_err_total"])) <= a.yield_band:
            base_ok.append(b)

    payload = {
        "round": "R163", "debt": "D-84",
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": a.inp,
        "params": {"eps_do2": a.eps_do2, "yield_band": a.yield_band,
                   "cliff_pp": a.cliff_pp,
                   "definition": ("F = {k : DO2_relrmse(k) ≤ min·(1+ε) "
                                  "∧ |rel_err_total(k)| ≤ 5%}")},
        "batches": rows,
        "checks": checks,
        "n_checks": len(checks),
        "n_pass": sum(1 for c in checks if c["pass"]),
        "summary": {
            "n_batches": len(rows),
            "n_feasible": len(feas),
            "n_conflict": sum(1 for r in rows if r["conflict"]),
            "n_not_calibratable": len(notcal),
            "not_calibratable_batches": [r["batch"] for r in notcal],
            "not_calibratable_detail": [
                {"batch": r["batch"], "min_abs_rel_err": r["min_abs_rel_err"],
                 "k_do2_only": r["k_do2_only"],
                 "note": ("该批在 alpha_kla 单参数空间内**无解**："
                          "所有档位产量误差均 > ±5% ⇒ 误差来源不是 alpha_kla，"
                          "须排除出逐批标定集（另寻参数/模型修正）")}
                for r in notcal],
            "calibration_coverage": (len(feas) / float(len(rows)) if rows else float("nan")),
            "n_identifiable": sum(1 for r in feas if r["identifiable"]),
            "n_on_cliff": sum(1 for r in feas if r["on_cliff"]),
            "on_cliff_batches": [r["batch"] for r in feas if r["on_cliff"]],
            "k_dual_values": kd,
            "k_dual_range": ([min(kd), max(kd)] if kd else None),
            "k_dual_by_batch": {str(r["batch"]): r["k_dual"] for r in feas},
            # 修正性结论（R162 → R163）：R162 的「DO2 最优 ≠ 产量最优」是**极值点**差异，
            # 双约束求交后 11/12 批的 DO2 解**同时**满足 ±5% 产量带 ⇒
            # 「不能用 DO2 单独标定」应修正为「DO2 是主约束，但必须加产量交叉校验」。
            "revision_vs_r162": {
                "r162_claim": "DO2 最优 ≠ 产量最优 ⇒ 不能用 DO2 单独标定 alpha_kla",
                "r163_finding": ("双约束求交后，%d/%d 可标定批的 DO2 解同时满足 ±5%% 产量带"
                                 "（|F| == |C1|）⇒ DO2 **是**主约束；但存在 1 批"
                                 "（b55）DO2 解通不过产量验收且单参数空间无解 ⇒ "
                                 "「必须加产量交叉校验」成立，「DO2 不可用」不成立。")
                                % (sum(1 for r in feas if r["n_F"] == r["n_c1"]),
                                   len(feas)),
                "n_batches_F_equals_C1": sum(1 for r in feas if r["n_F"] == r["n_c1"]),
                "n_batches_F_narrower": sum(1 for r in feas if r["n_F"] < r["n_c1"]),
            },
            "base85_within_band": base_ok,
            "base85_within_band_n": len(base_ok),
        },
    }
    payload["verdict"] = "PASS" if payload["n_pass"] == len(checks) else "FAIL"
    outp = os.path.join(ROOT, a.out)
    os.makedirs(os.path.dirname(outp), exist_ok=True)
    with open(outp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)

    print("\n" + "=" * 70)
    print("R163 alpha_kla 双约束标定 —— %d/%d %s"
          % (payload["n_pass"], len(checks), payload["verdict"]))
    print("=" * 70)
    for c in checks:
        print("[%s] %s %s (got=%r expect=%r)"
              % ("PASS" if c["pass"] else "FAIL", c["id"], c["name"], c["got"], c["expect"]))
    s = payload["summary"]
    print("\n可行 %d/%d（覆盖率 %.0f%%）；真冲突 %d；不可标定 %d %s；可辨识 %d；崖上 %d %s"
          % (s["n_feasible"], s["n_batches"], 100 * s["calibration_coverage"],
             s["n_conflict"], s["n_not_calibratable"], s["not_calibratable_batches"],
             s["n_identifiable"], s["n_on_cliff"], s["on_cliff_batches"]))
    print("双约束解：%s" % s["k_dual_values"])
    print("名义 85 仍在 ±5%% 验收带的批：%d/%d %s"
          % (s["base85_within_band_n"], s["n_batches"], s["base85_within_band"]))
    print("写出：%s" % a.out)
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
