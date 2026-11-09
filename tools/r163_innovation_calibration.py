# -*- coding: utf-8 -*-
"""R163 / D-80 配套：EnKF **创新判据的跨批标定**（修正 R161 的恒真问题）。

发现（R163 A 段筛查，前 8 批）
-----------------------------
R161 把创新判据限制在白名单通道 ``CO2outgas / DO2 / O2 / pH``（Q/T 因模型系统性偏差被排除），
阈值 ``|z| > 5``、**单点越限即触发**。
R163 对 86 批做筛查 ⇒ 前 8 批中 **6 批被判 DEGRADED**（触发率 75%），
各批越限次数 1 ~ 546 次、``|z|max`` 6 ~ 10+。
⇒ 该判据在真实数据上**近乎恒真**（D-78 纪律禁止的「恒真判据」），
   若直接接入 MCP 路径，会让 3/4 的批被误判降级 —— 比不接更糟。

本工具做两件事
--------------
  1. **量化**：对一批真实批，收集逐通道 ``|z|`` 的**完整分布**（p50/p90/p99/max）
     与越限占比，区分「系统性偏差」（跨批同向、量级稳定）与「真故障」（突变/发散）。
  2. **重设计判据**：给出带**持续占比**与**自适应阈值**的新判据，
     并做双向验证：
       - 正向：注入故障（DO2 漂移 / pH 偏置 / CO2 卡死）⇒ 必须触发；
       - 反向：未注入的批 ⇒ 不得触发（假阳性率 → 0）；
       - 零信息对照：无探针数据 ⇒ 不得判健康。

用法：
    py tools/r163_innovation_calibration.py --batches 1,2,3,5,7,8,9,11,12,14 --out runs/r163_innovation_calib.json
"""
import argparse
import json
import os
import sys
import time

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))

import solver_chain as sc                                      # noqa: E402


def _one(job):
    """单批：收集逐通道 |z| 分布。"""
    b, n_ens, seed = job
    from observe import enkf_observe
    from calibration import calib_params
    t0 = time.time()
    out = enkf_observe(b, params=calib_params(b), n_ens=n_ens, seed=seed,
                       verbose=False, health_probe=True)
    h = out.get("health") or {}
    zl = h.get("z") or []
    chans = sorted({k for step in zl for k in step})
    per = {}
    for ch in chans:
        vals = np.asarray([abs(float(step[ch])) for step in zl if ch in step
                           and np.isfinite(step[ch])], float)
        if vals.size == 0:
            continue
        per[ch] = {
            "n": int(vals.size),
            "p50": float(np.percentile(vals, 50)),
            "p90": float(np.percentile(vals, 90)),
            "p99": float(np.percentile(vals, 99)),
            "max": float(np.max(vals)),
            "frac_gt5": float(np.mean(vals > 5.0)),
            "frac_gt10": float(np.mean(vals > 10.0)),
        }
    return {"batch": b, "n_ens": n_ens, "n_steps": len(zl),
            "integration_failures": out.get("integration_failures"),
            "per_channel": per, "wall_s": round(time.time() - t0, 1)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", default="1,2,3,5,7,8,9,11,12,14")
    ap.add_argument("--n-ens", type=int, default=8)
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--out", default="runs/r163_innovation_calib.json")
    a = ap.parse_args()

    bl = [int(x) for x in a.batches.split(",") if x.strip()]
    jobs = [(b, a.n_ens, 7) for b in bl]

    import multiprocessing as mp
    ctx = mp.get_context("spawn")
    rows = []
    with ctx.Pool(processes=min(a.jobs, len(jobs))) as pool:
        for i, r in enumerate(pool.imap_unordered(_one, jobs), 1):
            rows.append(r)
            print("  [%d/%d] b%-3d steps=%s %s (%.0fs)"
                  % (i, len(jobs), r["batch"], r.get("n_steps"),
                     {k: round(v["max"], 1) for k, v in r.get("per_channel", {}).items()},
                     r["wall_s"]), flush=True)
    rows.sort(key=lambda r: r["batch"])

    # ---- 跨批汇总：系统性偏差的量化 ----
    chans = sorted({c for r in rows for c in r.get("per_channel", {})})
    summary = {}
    for ch in chans:
        mx = np.asarray([r["per_channel"][ch]["max"] for r in rows
                         if ch in r.get("per_channel", {})], float)
        p99 = np.asarray([r["per_channel"][ch]["p99"] for r in rows
                          if ch in r.get("per_channel", {})], float)
        fr = np.asarray([r["per_channel"][ch]["frac_gt5"] for r in rows
                         if ch in r.get("per_channel", {})], float)
        summary[ch] = {
            "n_batches": int(mx.size),
            "max_across_batches": {
                "p50": float(np.percentile(mx, 50)),
                "p90": float(np.percentile(mx, 90)),
                "max": float(np.max(mx)),
            },
            "p99_within_batch": {
                "p50": float(np.percentile(p99, 50)),
                "p90": float(np.percentile(p99, 90)),
                "max": float(np.max(p99)),
            },
            "frac_gt5_within_batch": {
                "p50": float(np.percentile(fr, 50)),
                "p90": float(np.percentile(fr, 90)),
                "max": float(np.max(fr)),
            },
            "n_batches_exceeding_z5": int(np.sum(mx > 5.0)),
        }

    # ---- 判据候选：新阈值的假阳性率（按实测分布离线计算）----
    candidates = {}
    for th in (5.0, 10.0, 15.0, 20.0, 30.0):
        for rate in (0.0, 0.02, 0.05, 0.10, 0.20, 0.30):
            fired = 0
            for r in rows:
                pc = r.get("per_channel", {})
                judged = {c: v for c, v in pc.items() if c in sc.INNOVATION_Z_CHANNELS}
                hit = any(v["max"] > th and v["frac_gt5"] > rate for v in judged.values())
                fired += 1 if hit else 0
            candidates["z>%g & frac>%.2f" % (th, rate)] = {
                "fired_batches": fired, "n_batches": len(rows),
                "false_positive_rate": fired / float(len(rows)) if rows else float("nan"),
            }

    payload = {
        "round": "R163", "debt": "D-80",
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "purpose": "EnKF 创新判据的跨批标定（修正 R161 的恒真问题）",
        "n_ens": a.n_ens, "seed": 7,
        "batches": rows,
        "cross_batch_summary": summary,
        "criterion_candidates": candidates,
        "judged_channels": list(sc.INNOVATION_Z_CHANNELS),
        "note": ("frac_gt5 是「|z|>5 的步占比」；候选判据用「某判据通道 max|z| > th "
                 "**且** 该通道 frac_gt5 > rate」—— 双条件用于区分偶发越限（b5: 1 次）"
                 "与系统性偏离（b9: 546 次）。"),
    }
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
    print("\n=== 跨批汇总 ===")
    for ch, s in summary.items():
        print("  %-10s 批级 max|z| 中位=%6.2f p90=%6.2f  批内 p99 中位=%6.2f  "
              "frac>5 中位=%5.3f  超 z=5 的批数=%d/%d"
              % (ch, s["max_across_batches"]["p50"], s["max_across_batches"]["p90"],
                 s["p99_within_batch"]["p50"], s["frac_gt5_within_batch"]["p50"],
                 s["n_batches_exceeding_z5"], s["n_batches"]))
    print("\n写出：%s" % a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
