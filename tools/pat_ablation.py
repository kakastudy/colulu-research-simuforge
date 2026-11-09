# -*- coding: utf-8 -*-
"""PAT 消融对照（spec §3 item 5, R119 前提修正版）：
引擎 PAA vs PAT vs fused 三口径对 I3 PAA 覆盖率与相关系数的净变化。

用法（P4 验收链结束后执行，避免与满池计算抢 CPU）：
    python tools/pat_ablation.py --batches 60,22

每批流程：
1. ensemble_smooth(n_ens=50) → 均值轨迹 + 基线 PAA_offline 覆盖率
2. build_pat_channel(均值轨迹) → paa_pat（引擎 PAA 状态的合成读数）
   —— 注意：这是「转发口径」，PAT 读数继承引擎动态（R111 已证）
3. fused（trigger 批上启用）→ fused_r_at_anchors
4. 输出三口径覆盖率 + 相关系数对比表
"""
import argparse
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import numpy as np
import pandas as pd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", default="60,22")
    ap.add_argument("--ens", type=int, default=50)
    ap.add_argument("--out", default="runs/p3/pat_ablation.json")
    a = ap.parse_args()

    import observe
    from raman_pat_channel import build_pat_channel
    from calibration import calib_params
    from simulate import load_batch

    results = []
    for bstr in a.batches.split(","):
        b = int(bstr)
        print(f"=== batch {b} ===", flush=True)
        r = observe.ensemble_smooth(b, n_ens=a.ens, seed=11, verbose=False)
        mean_df = r["mean"]
        cov_base = r["coverage"]["PAA_offline"]

        # 引擎 PAA 基线相关（均值轨迹 vs 化验）
        v3 = load_batch(b)
        po = pd.to_numeric(v3["PAA_offline"], errors="coerce")
        anchors = [(float(v3.loc[i, "time_h"]), float(v)) for i, v in po.items()
                   if np.isfinite(v) and float(v3.loc[i, "time_h"]) > 20]
        lab_y = np.array([x[1] for x in anchors])
        lab_t = np.array([x[0] for x in anchors])
        eng_paa_at = np.interp(lab_t, mean_df["time_h"].to_numpy(float),
                               mean_df["PAA"].to_numpy(float))
        r_eng = float(np.corrcoef(eng_paa_at, lab_y)[0, 1]) if len(lab_y) > 2 else float("nan")

        # PAT 转发口径（对均值轨迹合成）
        pat = build_pat_channel(mean_df, [x[0] for x in anchors], [x[1] for x in anchors],
                                trigger_mu_p=calib_params(b).get("mup"))
        pat_at = np.interp(lab_t, pat["time_h"], pat["paa_pat"])
        r_pat = float(np.corrcoef(pat_at, lab_y)[0, 1]) if len(lab_y) > 2 else float("nan")

        row = {"batch": b,
               "coverage_engine_paa": cov_base.get("coverage_95ci"),
               "corr_engine_paa": round(r_eng, 3),
               "corr_pat_forward": round(r_pat, 3),
               "pat_trigger": pat["trigger"],
               "pat_fidelity_r": pat["self_r"],
               "n_anchors": pat["n_anchors"]}
        if pat["paa_fused"] is not None:
            fused_at = np.interp(lab_t, pat["time_h"], pat["paa_fused"])
            r_fused = float(np.corrcoef(fused_at, lab_y)[0, 1]) if len(lab_y) > 2 else float("nan")
            row["corr_fused"] = round(r_fused, 3)
            row["fused_r_at_anchors"] = pat.get("fused_r_with_engine")
        results.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    out = os.path.join(ROOT, a.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"Saved: {out}", flush=True)
    print("\n汇总（引擎 PAA vs PAT 转发 vs fused 的相关系数净变化）:")
    for r in results:
        d = r["corr_pat_forward"] - r["corr_engine_paa"]
        tail = "" if "corr_fused" not in r else f" corr_fused={r['corr_fused']}"
        print(f"  batch {r['batch']}: corr_eng={r['corr_engine_paa']} corr_pat={r['corr_pat_forward']} "
              f"Δ={d:+.3f}{tail}", flush=True)


if __name__ == "__main__":
    main()
