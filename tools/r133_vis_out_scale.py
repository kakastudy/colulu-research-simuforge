# -*- coding: utf-8 -*-
"""R133 S1.3 黏度通道：观测口径（化验）与模型表观黏度的解耦标定。

诊断（runs/p3/d6_health_view.json 的统计）
------------------------------------------
- 86 批 `Viscosity_offline` 的化验均值几乎相同：**47.0–56.4 cP**（≈同一条曲线）；
- 而模型黏度的批间离散度很大，因为 `dy[9]` 是 `a0^(1/3)` 的积分，而我们逐批校准过
  `mux/mup`，a0 的批间差异被放大；
- `corr(nRMSE, |相对偏差|) = 0.975`，最差批（b3/b29）就是 sim 高 53% 的那批。

结论：黏度残差**不是形状错，也不是"标度没标"**，而是**观测链路与模型状态量不是同一个量**。
离线黏度计在固定剪切率下测的是"表观黏度"，模型里的 `a0^(1/3)` 是形态学指数——
两者相差一个**批级比例系数**，属测量链参数，不是生物学参数。

处置
----
新增 `vis_out_scale`（默认 1.0）：只作用于**上报通道** `sim["vis"]`，
ODE 内部（进 kla 的 `y[9]`）保持原值 → **对产量零影响**，可验证。
这与 R132 被否掉的 `vis_scale` 有本质区别：`vis_scale` 乘在生成项上，会经
`kla ∝ vis_scaled^(-0.38)` 反馈进产量（86/86 → 63/86），所以不可用。

每批 scale 用最小二乘闭式解（一次仿真即可，无需扫参）：
    s* = Σ(obs·sim) / Σ(sim²)

产物：runs/p3/r133_vis_out_scale.json
用法：python tools/r133_vis_out_scale.py [--apply] [--workers 8]
"""
import argparse
import json
import os
import sys
import time

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from golden_params import COMBINED, GOLDEN_ALL, build_params  # noqa: E402
from simulate import simulate_open_loop, yield_metrics  # noqa: E402


def eval_batch(b):
    v3 = pd.read_csv(os.path.join(ROOT, "data", "processed", "batches",
                                  f"batch_{b:02d}.csv"))
    sim, _ = simulate_open_loop(b, build_params(COMBINED[b]))
    t = v3["time_h"].to_numpy(float)
    v = v3["Viscosity_offline"].to_numpy(float)
    m = np.isfinite(t) & np.isfinite(v) & (v > 0)
    if m.sum() < 5:
        return b, None
    ts = sim["time_h"].to_numpy(float)
    vs = sim["vis"].to_numpy(float)
    pred = np.interp(t[m], ts, vs)
    obs = v[m]
    mean_obs = float(np.mean(obs))

    def nrmse(p):
        return float(np.sqrt(np.mean((p - obs) ** 2)) / mean_obs * 100.0)

    before = nrmse(pred)
    s = float(np.sum(obs * pred) / np.sum(pred * pred))
    after = nrmse(s * pred)

    ym = yield_metrics(sim, v3)
    return b, {
        "scale": round(s, 4),
        "nrmse_before": round(before, 2),
        "nrmse_after": round(after, 2),
        "lab_mean": round(mean_obs, 2),
        "sim_mean": round(float(np.mean(pred)), 2),
        "gain": round(float(np.mean(pred) / mean_obs), 3),
        "shape_residual": round(after, 2),
        "yield_err_pt": round(float(ym["rel_err_total"]) * 100.0, 3),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--out", default=os.path.join(ROOT, "runs", "p3",
                                                  "r133_vis_out_scale.json"))
    args = ap.parse_args()

    t0 = time.time()
    jobs = list(GOLDEN_ALL)
    if args.workers > 1:
        import multiprocessing as mp
        with mp.Pool(args.workers) as pool:
            res = pool.map(eval_batch, jobs, chunksize=1)
    else:
        res = [eval_batch(b) for b in jobs]

    per = {str(b): r for b, r in res if r}
    bef = np.array([r["nrmse_before"] for r in per.values()])
    aft = np.array([r["nrmse_after"] for r in per.values()])
    scales = np.array([r["scale"] for r in per.values()])
    summary = {
        "n": len(per),
        "median_before": round(float(np.median(bef)), 2),
        "median_after": round(float(np.median(aft)), 2),
        "mean_before": round(float(np.mean(bef)), 2),
        "mean_after": round(float(np.mean(aft)), 2),
        "improved_batches": int(np.sum(aft < bef)),
        "scale_median": round(float(np.median(scales)), 4),
        "scale_p5": round(float(np.percentile(scales, 5)), 4),
        "scale_p95": round(float(np.percentile(scales, 95)), 4),
        "n_before_critical": int(np.sum(bef >= 15)),
        "n_after_critical": int(np.sum(aft >= 15)),
        "n_after_healthy": int(np.sum(aft < 5)),
        "elapsed_s": round(time.time() - t0, 1),
    }
    out = {"summary": summary, "per_batch": per}
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print("saved", args.out)


if __name__ == "__main__":
    main()
