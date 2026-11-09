# -*- coding: utf-8 -*-
"""P3 V1+ 工作分解第 1 项：PAT 前向通道库函数（合成 + 锚定修正层 + 条件触发）。

口径纪律（三明治，R51/R53/R91）：
- PAA_pat = synth_batch → predict_paa（引擎状态驱动，忠实度 r=0.9995）
- 触发器: knowledge_constraints.paa_pat_trigger(μp>0.055)（R91 机理锚点）
- 锚定修正层（trigger=on）: PAT 形状 × 化验低频基准（lab 锚点水平耦合）→ fused
- 诚实声明: fused 在锚点必然贴化验（构造保证）；锚点之间保 PAT 相对动态；
  独立预测力上限参考 r=0.8463（V2 demo, R51）。
"""
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import numpy as np
import pandas as pd

from raman_pipeline import synth_batch, predict_paa
from knowledge_constraints import paa_pat_trigger


def build_pat_channel(sim_df, lab_t=None, lab_y=None, trigger_mu_p=None,
                      fused=None):
    """sim_df: simulate_open_loop 输出记录表。
    lab_t/lab_y: 化验锚点（PAA_offline 的化验时点/值，未插值）。
    trigger_mu_p: 校准 μp（决定锚定层 on/off）；None=不触发纯 PAT。
    fused=None 默认独立 PAA 状态；若调用方死亡层另有 PAA 修正可传入。
    返回 dict: {t, paa_pat, paa_fused, trigger, reason, n_anchors}"""
    P = sim_df["P"].to_numpy(float)
    X = sim_df["X"].to_numpy(float)
    vis = sim_df["vis"].to_numpy(float) if "vis" in sim_df.columns else np.ones(len(sim_df))
    S = sim_df["S"].to_numpy(float)
    PAA = sim_df["PAA"].to_numpy(float)
    t = sim_df["time_h"].to_numpy(float)
    spec = synth_batch(np.clip(P, 0, None), np.clip(X, 0, None),
                       np.clip(vis if "vis" in sim_df.columns else np.ones_like(t), 0, None),
                       S, PAA)
    pat = predict_paa(spec)
    trigger, reason = paa_pat_trigger(trigger_mu_p) if trigger_mu_p is not None else (False, "μp 未提供——纯 PAT")
    fused_t = None
    if trigger and lab_t is not None and lab_y is not None and len(lab_t) >= 2:
        lt = np.asarray(lab_t, float)
        ly = np.asarray(lab_y, float)
        t_at_t = t[np.clip(np.searchsorted(t, lt), 0, len(t) - 1)]
        pat_at = np.interp(t_at_t, t, pat)
        # 比例锚定: fused(t) = pat(t) × lab_i / pat(t_i)，逐锚分段插值
        if np.min(np.abs(pat_at)) > 1e-6:
            fused = np.zeros_like(pat)
            edges = np.unique(np.clip(np.searchsorted(t, lt), 1, len(t) - 1))
            order = np.argsort(lt)
            lt_s, ly_s = lt[order], ly[order]
            j = np.clip(np.searchsorted(t, lt_s), 0, len(t) - 1)
            pat_anchor = pat[j]
            for k in range(len(lt_s)):
                seg_a = (k == 0) * 0 + (int(j[k - 1]) if k > 0 else 0)
                seg_b = int(j[k + 1]) if k + 1 < len(j) else len(t)
                ratio = ly_s[k] / pat_anchor[k] if abs(pat_anchor[k]) > 1e-6 else 1.0
                fused[seg_a:seg_b] = pat[seg_a:seg_b] * ratio
            # 尾段
            fused[int(j[-1]):] = pat[int(j[-1]):] * (ly_s[-1] / pat_anchor[-1]
                                                      if abs(pat_anchor[-1]) > 1e-6 else 1.0)
            fused_t = fused
            n_anch = len(lt_s)
        else:
            n_anch = 0
    else:
        n_anch = 0
    return {"time_h": t, "paa_pat": pat, "paa_fused": fused_t,
            "trigger": bool(trigger), "reason": reason,
            "n_anchors": int(n_anch),
            "self_r": float(np.corrcoef(pat, PAA)[0, 1]),
            "fused_r_with_engine": (float(np.corrcoef(fused_t, PAA)[0, 1])
                                     if fused_t is not None else None)}


if __name__ == "__main__":
    # 演示：批 22（μp=0.070 → 触发；lab 锚点真实），对照批 60（μp=0.030 → 不触发）
    import json
    from simulate import simulate_open_loop
    from calibration import calib_params
    results = {}
    for b in (22, 60):
        p = calib_params(b)
        sim, v3 = simulate_open_loop(b, p)
        pv = pd.to_numeric(v3["PAA_offline"], errors="coerce")
        lt = [float(v3.loc[i, "time_h"]) for i, v in pv.items() if np.isfinite(v) and float(v3.loc[i, "time_h"]) > 20]
        ly = [float(v) for i, v in pv.items() if np.isfinite(v) and float(v3.loc[i, "time_h"]) > 20]
        r = build_pat_channel(sim, lt, ly, trigger_mu_p=p["mup"])
        results[b] = {k: (v.tolist() if hasattr(v, "tolist") else v)
                      for k, v in r.items() if k != "paa_pat" and k != "paa_fused"}
        results[b]["fused_built"] = r["paa_fused"] is not None
    out = os.path.join(ROOT, "runs", "p3", "pat_channel_demo.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    sys.stdout.flush()
    try:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    except Exception:
        pass

