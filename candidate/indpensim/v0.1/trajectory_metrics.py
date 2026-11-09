# -*- coding: utf-8 -*-
"""轨迹级偏差指标（GOAL.md §4.2）：S/X/P/DO/T/pH/V/OUR/CER 逐点对照 V3。

口径：
- 在线通道（S/DO2/P/T/pH/V/Wt/OUR/CER）：sim 0.2h 网格 vs V3 同刻逐点直差。
- X（离线）：V3 X_offline(t) = X(t-4h)（indpensim_run.m Off_line_delay=4, T7 登记），
  故比较 sim X(t-4) vs V3 X_off(t)，仅在 X_offline 非 NaN 的化验时点评估。
- 指标：RMSE、bias(带符号均值差)、nRMSE（RMSE / V3 批内均值 ×100%）、R 相关系数。
- 评估窗：t >= 20h（批头启动段不纳入指标，登记为假设 T7）。

CLI: python trajectory_metrics.py [--batches 8,11,...] [--out runs/trajectory_metrics.json]
"""
import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from simulate import simulate_open_loop
from calibration import calib_params, GOLDEN

ONLINE_CH = ["S", "DO2", "P", "T", "pH", "V", "Wt", "OUR", "CER"]
T_EVAL_MIN = 20.0  # h
T_OFF_DELAY = 4.0  # h（indpensim_run.m: Off_line_delay = 4）


def _rmse_bias_corr(sim_v, v3_v):
    e = sim_v - v3_v
    rmse = float(np.sqrt(np.mean(e ** 2))) if len(e) else np.nan
    bias = float(np.mean(e)) if len(e) else np.nan
    if len(e) >= 3 and np.std(v3_v) > 1e-12 and np.std(sim_v) > 1e-12:
        corr = float(np.corrcoef(sim_v, v3_v)[0, 1])
    else:
        corr = np.nan
    return rmse, bias, corr


def _pat_triple(sim, v3, batch_no):
    """PAT 三重判据（R110 接入；口径纪律见 tools/raman_pipeline.py 注释与
    docs/raman_pat_integration_spec.md §2）：
    1) 还原忠实度: paa_pat 对引擎 PAA 状态的相关（通道本身保真）
    2) 循环自洽:   锚定修正层在化验锚点上贴化验（构造保证 ≈1）
    3) 独立口径:   未锚定的 paa_pat 在化验时点对化验的预测力（真实监测口径）
    """
    import sys, os
    ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    if os.path.join(ROOT, "tools") not in sys.path:
        sys.path.insert(0, os.path.join(ROOT, "tools"))
    from raman_pat_channel import build_pat_channel
    po = pd.to_numeric(v3.get("PAA_offline"), errors="coerce")
    anchors = [(float(v3.loc[i, "time_h"]), float(v)) for i, v in po.items()
               if np.isfinite(v) and float(v3.loc[i, "time_h"]) > 20]
    if len(anchors) < 4:
        return {"skipped": True, "reason": f"锚点不足 (n={len(anchors)})——退化批或无化验"}
    from calibration import calib_params
    cal = calib_params(batch_no)
    r = build_pat_channel(sim, [a[0] for a in anchors], [a[1] for a in anchors],
                          trigger_mu_p=cal.get("mup"))
    t = r["time_h"]; pat = r["paa_pat"]
    lab_t = np.array([a[0] for a in anchors]); lab_y = np.array([a[1] for a in anchors])
    # 3) 独立口径：PAT 读数在化验时点 vs 化验值（不插值融合、不锚定）
    pat_at_lab = np.interp(lab_t, t, pat)
    corr_ind = _rmse_bias_corr(pat_at_lab, lab_y)[2]
    rmse_ind = _rmse_bias_corr(pat_at_lab, lab_y)[0]
    fused = r["paa_fused"]
    triple = {
        "batch": int(batch_no),
        "trigger": r["trigger"],
        "trigger_mu_p": float(cal.get("mup", float("nan"))),
        "fidelity_r": round(float(r["self_r"]), 3),
        "independent_r": round(float(corr_ind), 3),
        "independent_nrmse_pct": round(float(rmse_ind / abs(np.mean(lab_y))) * 100.0, 1),
        "fused_built": fused is not None,
        "n_anchors": r["n_anchors"],
        "note": "还原忠实度(fidelity_r)：PAT 对引擎 PAA 的相关；独立预测力(independent_r)：PAT 读数在化验时点"
                "对化验的相关性（批 22 实测 −0.34 与 R90 普查 −0.345 互证——PAT 继承引擎 PAA 状态动态）；"
                "锚定层仅在 trigger=on 启用（触发器见 docs/raman_pat_integration_spec.md §1）。"
                "fused_r_at_anchors 受化验时点与 sim 网格错位插值影响（锚点精确贴合仅在网格点上成立）",
    }
    if fused is not None:
        corr_f = _rmse_bias_corr(np.interp(lab_t, t, fused), lab_y)[2]
        triple["fused_r_at_anchors"] = round(float(corr_f), 3)
    return triple


def trajectory_metrics(sim, v3, pat=False, batch_no=None):
    """返回 {channel: {rmse, bias, nrmse_pct, corr, n}} + x_offline 段。
    pat=True 时附加 PAT 三重判据段（V1+ 分解第 2 项；默认关，零影响主链）。"""
    out = {}
    for ch in ONLINE_CH:
        if ch not in sim.columns or ch not in v3.columns:
            continue
        t3 = v3["time_h"].to_numpy(float)
        w = t3 >= T_EVAL_MIN
        s_i = np.interp(t3[w], sim["time_h"].to_numpy(float), sim[ch].to_numpy(float))
        v3_v = pd.to_numeric(v3.loc[w, ch], errors="coerce").to_numpy(float)
        ok = np.isfinite(v3_v)
        rmse, bias, corr = _rmse_bias_corr(s_i[ok], v3_v[ok])
        base = np.nanmean(v3_v[ok])
        out[ch] = {"rmse": rmse, "bias": bias,
                   "nrmse_pct": 100.0 * rmse / base if base else np.nan,
                   "nrmse_max_pct": 100.0 * rmse / float(np.nanmax(v3_v[ok])) if np.nanmax(v3_v[ok]) else np.nan,
                   "corr": corr, "n": int(ok.sum())}
    # X（离线化验对照，4h 滞后登记）
    xo = pd.to_numeric(v3.get("X_offline"), errors="coerce")
    rows = []
    for i, val in xo.items():
        if not np.isfinite(val):
            continue
        t_lab = float(v3.loc[i, "time_h"])
        if t_lab - T_OFF_DELAY < T_EVAL_MIN:
            continue
        s_x = np.interp(t_lab - T_OFF_DELAY, sim["time_h"].to_numpy(float), sim["X"].to_numpy(float))
        rows.append((s_x, float(val)))
    if rows:
        s_x = np.array([r[0] for r in rows]); v3x = np.array([r[1] for r in rows])
        rmse, bias, corr = _rmse_bias_corr(s_x, v3x)
        out["X_offline"] = {"rmse": rmse, "bias": bias,
                            "nrmse_pct": 100.0 * rmse / float(np.mean(v3x)),
                            "nrmse_max_pct": 100.0 * rmse / float(np.max(v3x)),
                            "corr": corr, "n": len(rows),
                            "note": "sim X(t-4h) vs V3 X_offline(t)（滞后 4h 登记）"}
    # PAA（离线化验对照；R52-53 发现引擎 PAA 与化验可反相关 → 显式披露保真度）
    po = pd.to_numeric(v3.get("PAA_offline"), errors="coerce")
    pr = [(float(v), float(v3.loc[i, "time_h"])) for i, v in po.items()
          if np.isfinite(v) and float(v3.loc[i, "time_h"]) > 20]
    if pr:
        v3p = np.array([r[0] for r in pr])
        tl = np.array([r[1] for r in pr])
        stl = sim["time_h"].to_numpy(float)
        spa = sim["PAA"].to_numpy(float)
        if np.std(v3p) / max(abs(np.mean(v3p)), 1e-9) < 0.02:
            out["PAA_offline"] = {"degenerate": True, "sigma_over_mu": float(np.std(v3p) / abs(np.mean(v3p))),
                                   "n": len(pr), "note": "化验列饱和/退化（σ/μ<2%），相关口径无信息"}
        else:
            best = None
            for lag in (0.0, 2.0, 4.0, 6.0, 8.0, 12.0):
                s_i = np.interp(tl - lag, stl, spa)
                rmse, bias, corr = _rmse_bias_corr(s_i, v3p)
                rec = {"lag_h": lag, "rmse": rmse, "bias": bias,
                       "nrmse_pct": 100.0 * rmse / np.mean(v3p) if np.mean(v3p) else np.nan,
                       "corr": corr, "n": len(pr)}
                if np.isfinite(corr) and (best is None or not np.isfinite(best["corr"])
                                           or abs(corr) > abs(best["corr"])):
                    best = rec
            if best is None:
                best = rec
            out["PAA_offline"] = dict(best,
                                       degenerate=False,
                                       note="lag 扫描 [0,2,...,12]h 取 |corr| 最大者；反相关/绝对值>0.5 提示通道保真缺口")
    # PAT 三重判据（V1+ 分解第 2 项，R110）：还原忠实度/循环自洽/独立口径（锚定后）
    if pat and batch_no is not None:
        out["PAT_triple"] = _pat_triple(sim, v3, batch_no)
    return out


def run(batch_nos, out_path, pat=False):
    results = []
    for b in batch_nos:
        sim, v3 = simulate_open_loop(b, calib_params(b))
        m = trajectory_metrics(sim, v3, pat=pat, batch_no=b)
        results.append({"batch": int(b), "metrics": m})
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        try:
            terr = {k: round(v["nrmse_pct"], 1) for k, v in m.items()
                    if isinstance(v.get("nrmse_pct"), float) and np.isfinite(v.get("nrmse_pct", np.nan))}
            print(f"batch {b:2d}: " + "  ".join(f"{k}={v}%" for k, v in terr.items()), flush=True)
            if pat and "PAT_triple" in m and not m["PAT_triple"].get("skipped"):
                pt = m["PAT_triple"]
                print(f"         PAT: fidelity_r={pt['fidelity_r']} independent_r={pt['independent_r']} "
                      f"trigger={pt['trigger']} fused={pt['fused_built']}", flush=True)
        except Exception:
            pass  # stdout 关闭事故（raman_pipeline 副作用）——数据在 m 中，落盘后仍完整
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2, default=str)
        try:
            print(f"Saved(partial): {out_path} ({len(results)} batches)", flush=True)
        except Exception:
            pass
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    try:
        print(f"Saved: {out_path}")
    except Exception:
        pass
    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", default=",".join(map(str, GOLDEN)))
    ap.add_argument("--out", default="runs/trajectory_metrics.json")
    ap.add_argument("--pat", action="store_true",
                    help="启用 PAT 三重判据段（V1+ 分解第 2 项；默认关）")
    a = ap.parse_args()
    run([int(x) for x in a.batches.split(",")], a.out, pat=a.pat)
