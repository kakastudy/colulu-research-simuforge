# -*- coding: utf-8 -*-
"""R142 / D-2 Part B：损失面的信噪比分解（噪声尺度由数据自身给出）。

问题：`dl_sigma` 用 T_EB=1.0 做 softmax，而实际 ΔL 只有 1e-2 量级 → 后验摊平（ESS/n=0.98）。
但"温度设错"不等于"数据有信息"：若 ΔL 本身就淹没在噪声里，σ_pop 依然不可辨识。

本脚本用方差分解定标：
  组间（signal）  : 同一参数不同水平之间的 profile 损失差
  组内（noise）   : 同一参数水平下、其余两个自由度变化造成的损失散布
                   —— 它度量"模型错配 + 数值"对损失的扰动，是似然标度的自然单位

判据 `SNR = 组间 / 组内`：
  SNR ≲ 1  → 参数不可分辨，DL 只能用 σ_pop=0（D-2 现状判定成立，但原因需改写）
  SNR ≳ 3  → 参数可分辨，应改用 T ≈ 组内 SD 重估后验（D-2 可修）

输出：runs/p3/r142_d2_snr.json
"""
import json
import os
import sys

import numpy as np

_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
LOG = os.path.join(_ROOT, "runs", "hier_est", "train_theta_v2.jsonl")
OUT = os.path.join(_ROOT, "runs", "p3", "r142_d2_snr.json")
PARAMS = ("mux", "mup", "m_s")
LOSS_CAP = 9e5


def analyse(sw, param):
    """返回该批该参数的 (组间差, 组内SD, 各水平中位损失)。"""
    by = {}
    for c in sw:
        by.setdefault(c[param], []).append(c["loss"])
    lv = sorted(by)
    if len(lv) < 2:
        return None
    med = [float(np.median(by[k])) for k in lv]
    n = [len(by[k]) for k in lv]
    # 组内：各水平内的稳健散布（MAD → SD），按自由度加权
    sd_in = []
    for k in lv:
        a = np.array(by[k])
        if len(a) >= 3:
            mad = np.median(np.abs(a - np.median(a)))
            sd_in.append(1.4826 * mad)
    sd_within = float(np.mean(sd_in)) if sd_in else float("nan")
    span_between = float(max(med) - min(med))
    return {"levels": lv, "n_per_level": n, "median_by_level": [round(x, 6) for x in med],
            "span_between": round(span_between, 6),
            "sd_within": round(sd_within, 6),
            "snr": round(span_between / sd_within, 3) if sd_within and sd_within > 0 else None}


def main():
    recs = [json.loads(l) for l in open(LOG, encoding="utf-8")]
    out = {"n_batches": len(recs), "by_param": {}, "rows": []}
    for p in PARAMS:
        snrs, spans, sds = [], [], []
        for r in recs:
            sw = [c for c in (r.get("sweep") or []) if c["loss"] < LOSS_CAP]
            if len(sw) < 6:
                continue
            a = analyse(sw, p)
            if not a:
                continue
            a["batch"] = r["batch"]; a["param"] = p
            out["rows"].append(a)
            if a["snr"] is not None and np.isfinite(a["snr"]):
                snrs.append(a["snr"]); spans.append(a["span_between"]); sds.append(a["sd_within"])
        snrs = np.array(snrs)
        out["by_param"][p] = {
            "n": len(snrs),
            "snr_med": round(float(np.median(snrs)), 3),
            "snr_p10": round(float(np.percentile(snrs, 10)), 3),
            "snr_p90": round(float(np.percentile(snrs, 90)), 3),
            "frac_snr_gt_1": round(float(np.mean(snrs > 1)), 3),
            "frac_snr_gt_3": round(float(np.mean(snrs > 3)), 3),
            "span_between_med": round(float(np.median(spans)), 6),
            "sd_within_med": round(float(np.median(sds)), 6),
        }
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"批数 {len(recs)}")
    print(f"{'param':>5} {'SNR中位':>8} {'p10':>7} {'p90':>7} {'>1占比':>8} {'>3占比':>8} "
          f"{'组间差':>10} {'组内SD':>10}")
    for p in PARAMS:
        s = out["by_param"][p]
        print(f"{p:>5} {s['snr_med']:>8.2f} {s['snr_p10']:>7.2f} {s['snr_p90']:>7.2f} "
              f"{s['frac_snr_gt_1']:>8.2f} {s['frac_snr_gt_3']:>8.2f} "
              f"{s['span_between_med']:>10.4f} {s['sd_within_med']:>10.4f}")
    print(f"\n落盘 {OUT}")


if __name__ == "__main__":
    main()
