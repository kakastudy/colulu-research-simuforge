# -*- coding: utf-8 -*-
"""R150 / D-40 附件：60–120 h 的 P 偏低，是"糖不对"还是"门控不对"。

R150 主结果表明 P 通道的误差不是全局水平问题：86 批分相位相对残差的中位数是
    0–60 h −0.042 · **60–120 h −0.092** · 120–180 h +0.019 · 180+ h +0.022
即**只有 60–120 h 段系统偏低约 9%**，其余相位在 ±5% 内。

接下来要分清两种解释：

    (a) 底物轨迹不对 —— 这一段的残糖 `S` 偏高/偏低，产素的门控（`P_inhib` 是
        残糖的高斯函数）因此不在正确的开度上；
    (b) 门控/产率系数不对 —— `S` 这一段是对的，但产素项本身偏小。

判据很直接：若 `S` 在同一相位也显著偏，则 (a)；若 `S` 的相位残差可忽略而 `P`
偏 9%，则 (b)。`X`（生物量）一并报，因为产素项正比于 X，X 偏了也会让 P 偏。

用法：python tools/r150_phase_probe.py --batches 22,36,55,59,7,38 --workers 3
输出：runs/r150_phase_probe.json
"""
import argparse
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))

PHASES = (("0-60", 0.0, 60.0), ("60-120", 60.0, 120.0),
          ("120-180", 120.0, 180.0), ("180+", 180.0, 1e9))

# 通道 → 实测列名。X 用化验列（连续列 X 是参考模型的内部态，化验才是"观测"）。
# PAA 是产素的直接前体（`r_p` 里 `PAA_inhib_P` 的门控变量），必须一起看：
# 若 60–120 h 的 PAA 也偏低，则"产素不足"有前体层面的解释，而不是单纯的产率系数。
CHANNELS = (("P", "P"), ("S", "S"), ("X", "X_offline"), ("PAA", "PAA_offline"),
            ("DO2", "DO2"), ("OUR", "OUR"))


def one(b):
    from golden_params import COMBINED, build_params
    import simulate as s

    b = int(b)
    sim, v3 = s.simulate_open_loop(b, build_params(COMBINED[b]))
    t = sim["time_h"].to_numpy(float)
    out = {"batch": b, "phase": {}, "ok": {}}
    for name, col in CHANNELS:
        if name not in sim.columns or col not in v3.columns:
            continue
        sv = sim[name].to_numpy(float)
        mv_raw = v3[col].to_numpy(float)
        tv = v3["time_h"].to_numpy(float)
        ok = np.isfinite(mv_raw)
        if np.sum(ok) < 10:
            out["ok"][name] = 0
            continue
        mv = np.interp(t, tv[ok], mv_raw[ok])
        scale = max(float(np.mean(np.abs(mv))), 1e-9)
        ph = {}
        for pname, lo, hi in PHASES:
            m = (t >= lo) & (t < hi)
            ph[pname] = float(np.mean((sv[m] - mv[m]) / scale)) if np.any(m) else float("nan")
        out["phase"][name] = ph
        out["ok"][name] = int(np.sum(ok))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", type=str, default="22,36,55,59,7,38")
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args()
    bs = [int(x) for x in args.batches.split(",") if x.strip()]
    print(f"[r150-probe] batches={len(bs)} workers={args.workers}")

    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        rows = list(ex.map(one, bs))

    names = [n for n, _ in CHANNELS if n in rows[0]["phase"]]
    print("\n分相位相对残差（(sim−meas)/mean|meas|），正=模型偏高")
    print("批   通道  " + "  ".join(f"{p:>8s}" for p, _, _ in PHASES))
    for r in rows:
        for n in names:
            ph = r["phase"].get(n)
            if not ph:
                continue
            print(f"{r['batch']:>3d}  {n:<4s}  " + "  ".join(f"{ph[p]:+8.3f}" for p, _, _ in PHASES))
        print()

    # 汇总：哪些通道在同一相位也偏
    print("各通道 60–120 h 残差（跨批均值）：")
    for n in names:
        v = [r["phase"][n]["60-120"] for r in rows if n in r["phase"]]
        v = [x for x in v if np.isfinite(x)]
        if v:
            print(f"  {n:<4s} 均值 {np.mean(v):+.4f}  逐批 " + " ".join(f"{x:+.3f}" for x in v))

    op = os.path.join(ROOT, "runs", "r150_phase_probe.json")
    json.dump({"batches": bs, "rows": rows}, open(op, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\nwritten: {op}")


if __name__ == "__main__":
    main()
