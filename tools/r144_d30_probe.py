# -*- coding: utf-8 -*-
"""R144 / D-30：定位 b92 在 t≈217.6 的 pH 崩落（数值奇异）来源。

背景（R143 登记）
----------------
b92 的 pH 在 t≈217.6 从 7.44 直接跳到 **3.000**，随后缓慢回升；
`Radau@1e-8` 在 t=217.4 直接积分失败；`BDF@1e-3` 与 `@1e-6` 在崩落前逐位相同、
崩落后 yield 分别为 +1.36% 与 +18.54% ⇒ b92 的产量结论依赖积分器配置。

本工具要回答的三个问题
--------------------
Q1 `pH = 3.000` 这个**整数值**从哪来？（怀疑：采样末守卫 `y[i] <= 0 -> 0.001`）
Q2 触发前 `y[6]` 是否真的走到非正？走多深？在哪一时刻？
Q3 这是移植偏差还是参考实现自带？（对照 `indpensim.m` 的守卫）

做法：包裹 `simulate.guards` 记录每次采样末的 pre/post 状态，不改引擎、不跑额外仿真。

用法
----
  python tools/r144_d30_probe.py --batch 92        # 单批逐步追踪
  python tools/r144_d30_probe.py --batch 92 --dump 216 218
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

# 关注的状态索引（state_names 0-based）
IDX_PH = 6  # pH_H = [H+]


def trace(batch, t_lo=None, t_hi=None):
    """包裹 guards，记录每次采样末的 y 向量。返回逐点记录。"""
    orig = S.guards
    recs = []

    def wrapped(y):
        pre = np.array(y, dtype=float)
        out = orig(y)
        post = np.array(out, dtype=float)
        recs.append({"pre": pre, "post": post})
        return out

    S.guards = wrapped
    try:
        sim, _ = S.simulate_open_loop(batch, gp.params_for(batch))
    finally:
        S.guards = orig

    names = S.state_names() if hasattr(S, "state_names") else None
    rows = []
    for i, r in enumerate(recs):
        t = round((i + 1) * 0.2, 1)
        if t_lo is not None and not (t_lo <= t <= t_hi):
            continue
        pre, post = r["pre"], r["post"]
        clamped = [j for j in range(31) if pre[j] <= 0]
        rows.append({
            "i": i,
            "t": t,
            "phH_pre": float(pre[IDX_PH]),
            "ph_pre": float(-np.log10(max(pre[IDX_PH], 1e-12))),
            "phH_post": float(post[IDX_PH]),
            "ph_post": float(-np.log10(max(post[IDX_PH], 1e-12))),
            "ph_clamped": bool(pre[IDX_PH] <= 0),
            "clamped_idx": clamped,
        })
    return rows, sim, names


def summarise(rows):
    """找出 pH 崩落点与 y[6] 非正的区间。"""
    neg = [r for r in rows if r["phH_pre"] <= 0]
    jump = None
    for a, b in zip(rows, rows[1:]):
        if b["ph_post"] < 3.5 <= a["ph_post"]:
            jump = {"from_t": a["t"], "to_t": b["t"],
                    "ph_before": a["ph_post"], "phH_pre_at_jump": b["phH_pre"],
                    "ph_after": b["ph_post"]}
            break
    return {
        "n_samples": len(rows),
        "n_ph_nonpos": len(neg),
        "first_nonpos_t": neg[0]["t"] if neg else None,
        "deepest_phH": min((r["phH_pre"] for r in neg), default=None),
        "jump": jump,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=92)
    ap.add_argument("--dump", nargs=2, type=float, default=None,
                    help="只打印该时间窗内的逐点记录")
    ap.add_argument("--no-write", action="store_true")
    args = ap.parse_args()

    t_lo, t_hi = (args.dump if args.dump else (None, None))
    rows, sim, names = trace(args.batch, t_lo, t_hi)
    s = summarise(rows)

    print(f"批 {args.batch}：采样点数 {s['n_samples']}，"
          f"y[6]<=0 的采样末 {s['n_ph_nonpos']} 次")
    if s["first_nonpos_t"] is not None:
        print(f"  首次非正 t={s['first_nonpos_t']}，最深 [H+]={s['deepest_phH']:.3e}")
    if s["jump"]:
        j = s["jump"]
        print(f"  崩落：t {j['from_t']} (pH {j['ph_before']:.3f}) -> "
              f"t {j['to_t']} (pH {j['ph_after']:.3f})，"
              f"崩落前 y[6]={j['phH_pre_at_jump']:.3e}")

    if args.dump:
        print(f"\n{'t':>7} {'y[6] pre':>12} {'pH pre':>8} {'pH post':>8} "
              f"{'钳位':>5}  钳位状态索引")
        for r in rows:
            print(f"{r['t']:>7.1f} {r['phH_pre']:>12.4e} {r['ph_pre']:>8.3f} "
                  f"{r['ph_post']:>8.3f} {'是' if r['ph_clamped'] else '':>5}  "
                  f"{r['clamped_idx']}")

    if not args.no_write:
        os.makedirs(OUT_DIR, exist_ok=True)
        out = os.path.join(OUT_DIR, f"r144_d30_probe_b{args.batch}.json")
        json.dump({"batch": args.batch, "summary": s, "rows": rows},
                  open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"\n落盘 {out}")


if __name__ == "__main__":
    main()
