# -*- coding: utf-8 -*-
"""R144 / D-30 Part C：混沌检验 —— b92 的产量是否由奇点触发时刻决定。

原理
----
若 b92 的 yield 差异（+1.36% vs +18.54%）来自"积分器在哪个点撞上
`[H+] -> 0` 的有限时间爆破"，那么**任何微小扰动**只要改变撞点时刻，
就会改变 yield。反之，若 yield 对 1e-6 的输入扰动不敏感，则它是物理量。

做法
----
对指定批次的输入通道（Fa/Fb/Fs/Fw/Fg）乘以 `1 + eps`（eps ~ 1e-6，固定种子），
跑若干次，统计 yield 的极差。同时给一个"健康批"作对照——健康批应当几乎不动。

用法
----
  python tools/r144_d30_chaos.py --batches 92,91,8 --reps 5
"""
import argparse
import json
import os
import sys

import numpy as np

_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(_ROOT, "candidate", "indpensim", "v0.1"))

import simulate as S  # noqa: E402
import golden_params as gp  # noqa: E402

OUT_DIR = os.path.join(_ROOT, "runs", "p3")
CHANNELS = ["Fa", "Fb", "Fs", "Fw", "Fg", "Foil", "Fpaa"]


def run_with_perturbation(b, eps, seed):
    """输入通道乘 (1+eps*U(-1,1))，返回 yield 误差。eps=0 即基线。"""
    orig = S.load_batch
    rng = np.random.default_rng(seed)

    def patched(n):
        d = orig(n).copy()
        if n == b and eps > 0:
            for ch in CHANNELS:
                if ch in d.columns:
                    v = d[ch].to_numpy(dtype=float)
                    v = v * (1.0 + eps * rng.uniform(-1.0, 1.0, size=v.shape))
                    d[ch] = v
        return d

    S.load_batch = patched
    try:
        sim, d0 = S.simulate_open_loop(b, gp.params_for(b))
        ym = S.yield_metrics(sim, d0)
        ph = sim["pH"].to_numpy(float)
        return {
            "yield_err": float(ym["rel_err_total"]),
            "ph_min": float(np.nanmin(ph)),
            "ph_end": float(ph[-1]),
        }
    finally:
        S.load_batch = orig


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", type=str, default="92,91,8")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--eps", type=float, default=1e-6)
    ap.add_argument("--merge", action="store_true",
                    help="并入已有 JSON，而不是覆盖（分批跑时用）")
    args = ap.parse_args()

    batches = [int(x) for x in args.batches.split(",") if x.strip()]
    out = {"eps": args.eps, "reps": args.reps, "by_batch": {}}
    path0 = os.path.join(OUT_DIR, "r144_d30_chaos.json")
    if args.merge and os.path.exists(path0):
        prev = json.load(open(path0, encoding="utf-8"))
        out["by_batch"].update(prev.get("by_batch", {}))
        print(f"并入已有 {len(prev.get('by_batch', {}))} 批")

    for b in batches:
        base = run_with_perturbation(b, 0.0, 0)
        reps = [run_with_perturbation(b, args.eps, 1000 + i) for i in range(args.reps)]
        ys = np.array([base["yield_err"]] + [r["yield_err"] for r in reps])
        spread = (ys.max() - ys.min()) * 100
        out["by_batch"][b] = {
            "base": base,
            "reps": reps,
            "yield_min_pct": float(ys.min() * 100),
            "yield_max_pct": float(ys.max() * 100),
            "spread_pt": float(spread),
        }
        print(f"b{b:<3} 基线 {base['yield_err']*100:>+7.2f}%  "
              f"扰动后 [{ys[1:].min()*100:>+7.2f}%, {ys[1:].max()*100:>+7.2f}%]  "
              f"极差 {spread:>6.2f} pt   pH 末 {base['ph_end']:.2f}", flush=True)

    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, "r144_d30_chaos.json")
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n落盘 {path}")

    # 判读
    print("\n判读：极差 ≫ 5 pt ⇒ 产量由奇点触发时刻决定，不是物理量；"
          "极差 ≪ 1 pt ⇒ 该批产量稳健。")


if __name__ == "__main__":
    main()
