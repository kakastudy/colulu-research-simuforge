# -*- coding: utf-8 -*-
"""S0.1 审计：CAL → golden_params 合并前后差异核算。

用途：R132 把参数表统一到 `candidate/indpensim/v0.1/golden_params.py` 后，
证明"改了什么、影响哪些批"，而不是只说"合并完成"。

三项检查：
 A. 一致性：对全部 88 批，calib_params(b) 与 build_params(COMBINED[b]) 的差异
    应当**只**出现在 PAA_CAL 补缺键上（paa_degrad_rate / paa_maintenance_target /
    SSOT 缺失时才补的个别键）。
 B. 差异表：13 批历史批在合并前后的逐键 diff（CAL_LEGACY vs 现口径），
    并标注每个差异属于哪一次标定（R130 衰亡 / R131 X_offline / PAA 模式专属）。
 C. 越权检查：确认没有任何 PAA_CAL 条目覆盖了 COMBINED 已有的动力学参数
    （这是本次合并最关键的正确性约束）。

用法：
    python tools/r132_calib_merge_check.py            # 打印 + 落 JSON
    python tools/r132_calib_merge_check.py --out x.json
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))
sys.path.insert(0, HERE)

from golden_params import COMBINED, build_params, GOLDEN_ALL  # noqa: E402
from calibration import (calib_params, calib_params_legacy, CAL_LEGACY,  # noqa: E402
                         PAA_CAL, GOLDEN)

# 硬编码常量：两侧一致，不参与 diff
CONST_KEYS = {"N_conc_paa", "c_oil", "dist_flag"}

# 差异归因规则（用于给 diff 打标签，便于人工复核）
ATTRIB = {
    "mup": "R131 X_offline 联合定参",
    "mux": "R131 X_offline 联合定参",
    "biomass_death_rate": "R130 衰亡项标定",
    "death_start": "R130 衰亡项标定",
    "death_recycle": "R130/R131 自溶回收",
    "late_death_rate": "R129 晚期衰亡",
    "mu_death_ref": "R129 晚期衰亡",
    "paa_degrad_rate": "PAA 门控模式专属（SSOT 不含）",
    "paa_maintenance_target": "PAA 门控模式专属（SSOT 不含）",
}


def diff_dicts(a, b):
    keys = (set(a) | set(b)) - CONST_KEYS
    return {k: [a.get(k), b.get(k)] for k in sorted(keys) if a.get(k) != b.get(k)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "runs", "p3", "r132_calib_merge.json"))
    args = ap.parse_args()

    print("=" * 88)
    print("S0.1 参数表合并审计 —— CAL(13 元组) → golden_params.COMBINED(88 dict)")
    print("=" * 88)

    # ---------- A. 一致性 ----------
    print("\n[A] 一致性：calib_params(b) vs build_params(COMBINED[b])，全部 88 批")
    a_viol = []
    a_overlay_keys = {}
    for b in sorted(COMBINED):
        new = calib_params(b)
        core = build_params(COMBINED[b])
        d = diff_dicts(core, new)
        # 允许的差异只能是"SSOT 没有、PAA_CAL 补上"的键
        illegal = {k: v for k, v in d.items() if k in COMBINED[b]}
        if illegal:
            a_viol.append((b, illegal))
        if d:
            a_overlay_keys[b] = {k: v[1] for k, v in d.items()}
    if a_viol:
        print(f"  ✗ 失败：{len(a_viol)} 批出现 PAA_CAL 覆盖 SSOT 已有键")
        for b, d in a_viol:
            print(f"    b{b}: {d}")
    else:
        print(f"  ✓ 通过：0 批越权；{len(a_overlay_keys)} 批有 PAA 补缺（只补 SSOT 缺失键）")
        for b, k in sorted(a_overlay_keys.items()):
            print(f"    b{b}: 补 {k}")

    # ---------- B. 合并前后差异（13 批历史批）----------
    print(f"\n[B] 合并前后差异（{len(GOLDEN)} 批历史校准批）")
    rows = []
    total_keys = 0
    for b in GOLDEN:
        old = calib_params_legacy(b)
        new = calib_params(b)
        d = diff_dicts(old, new)
        total_keys += len(d)
        if not d:
            print(f"  b{b:<3d} —（无差异）")
            continue
        print(f"  b{b:<3d} {len(d)} 处差异")
        for k, (o, n) in d.items():
            tag = ATTRIB.get(k, "其他")
            print(f"        {k:<24s} {o!r:>12} → {n!r:<12} [{tag}]")
        rows.append({"batch": b,
                     "diffs": {k: {"legacy": v[0], "now": v[1], "attribution": ATTRIB.get(k, "其他")}
                               for k, v in d.items()}})
    print(f"  合计 {total_keys} 处差异，涉及 {len(rows)}/{len(GOLDEN)} 批")

    # ---------- C. 越权检查 ----------
    print("\n[C] PAA_CAL 越权检查：是否存在动力学参数被旧值反向覆盖")
    overrides = []
    for b, ov in PAA_CAL.items():
        if b not in COMBINED:
            continue
        hit = {k: [v, build_params(COMBINED[b]).get(k)] for k, v in ov.items()
               if k in build_params(COMBINED[b]) and build_params(COMBINED[b])[k] != v}
        if hit:
            overrides.append({"batch": b, "overridden": hit})
    if overrides:
        print(f"  ⚠ {len(overrides)} 批存在历史值差异（现已被 setdefault 拦下，不会生效）：")
        for o in overrides:
            ks = ", ".join(f"{k}:{v[0]}→SSOT {v[1]}" for k, v in o["overridden"].items())
            print(f"    b{o['batch']}: {ks}")
    else:
        print("  ✓ 无")

    out = {"checked_at_batches": len(COMBINED),
           "eval_set_size": len(GOLDEN_ALL),
           "consistency_violations": [{"batch": b, "diff": d} for b, d in a_viol],
           "overlay_applied": a_overlay_keys,
           "legacy_diff_total_keys": total_keys,
           "legacy_diff": rows,
           "paa_cal_historical_conflicts": overrides}
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"\nSaved: {args.out}")
    print("=" * 88)


if __name__ == "__main__":
    main()
