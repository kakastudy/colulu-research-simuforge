# -*- coding: utf-8 -*-
"""R157 / D-56：`validity()` 的 pH 越域判据修正 —— 验证 + **分布报告**。

背景
----
R148 的 `validity()` 判据 2 是「守卫前 pH 曾达 7.0 ⇒ invalid」。
它把两件事混为一谈：
  (a) pH 越 7 = 进入 basic 分支；
  (b) basic 分支是**数值病态**的（`−Kw/[H+]` 正反馈，失稳时标 `t* = H⁺²/(2Kw)`，
      pH 7.0 处 ≈ 0.48 h，与 0.2 h 采样步长同量级）——**这才是轨迹不可信的原因**。
R156 证明 (b) 可以消除（`ph_fix=1` 链式法则修正，不动点不变）⇒ **越 7 在修好的分支里无害**。

修正后的判据
------------
`invalid ⇔ 钳位（[H⁺] ≤ 0，数值崩溃）` **或** `越域幅度 ≥ ph_hard`，
其中 `ph_hard` 由 `sim.attrs["ph_basic_fixed"]`（= `ph_fix`）自动决定：
  `ph_fix=0`（默认，basic 分支病态）⇒ `ph_hard = 7.0` ⇒ **与 R148 旧行为逐位一致**；
  `ph_fix=1`（basic 分支已修）       ⇒ `ph_hard = None` ⇒ 越 7 只报告、不判 invalid。

本工具做两件事
--------------
A. **分布报告**（D-44 教训：必须报分布不能只报计数）：
   对每批给出 `n_steps` / `n_ph_clamp` / `n_ph_over7` / `over7_frac` / `ph_max_pre`，
   并报 over7 占比的**分位数**与直方，而不是只报"9 批 invalid"。
B. **前后对照**：同一批同时算「旧判据」与「新判据」，给出 valid 计数与名单差异。

用法
----
    python tools/r157_validity.py --all86                    # 默认基线
    python tools/r157_validity.py --all86 --candidate-v2     # 候选基线 v2
    python tools/r157_validity.py --batches 37,40,49,54,91,92
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
ENG = os.path.join(ROOT, "candidate", "indpensim", "v0.1")
sys.path.insert(0, ENG)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _one(job):
    batch, mode = job
    try:
        import simulate as s
        from golden_params import COMBINED, build_params, apply_candidate_v2

        p = dict(build_params(COMBINED[batch]))
        if mode == "v2":
            p = apply_candidate_v2(p, int(batch))
        sim, v3 = s.simulate_open_loop(int(batch), p)
        ym = s.yield_metrics(sim, v3)

        # 新判据（自动判定 basic 分支状态）
        v_new = s.validity(sim)
        # 旧判据（R148 原样）
        ga = sim.attrs.get("guard_audit", {}) or {}
        n_clamp = int(ga.get("tally", {}).get("pH_H", 0))
        n_over = int(ga.get("n_ph_over7_pre", 0))
        n_steps = int(ga.get("n_steps", 0) or 0)
        valid_old = bool(n_clamp == 0 and n_over == 0)
        # 假设"basic 分支已修"时的判据（用于默认基线的上界参考）
        v_relaxed = s.validity(sim, ph_hard_max=None)

        return {
            "batch": int(batch),
            "mode": mode,
            "yield_err": float(ym["rel_err_total"]),
            "n_steps": n_steps,
            "n_ph_clamp": n_clamp,
            "n_ph_over7": n_over,
            "over7_frac": (float(n_over) / n_steps) if n_steps else float("nan"),
            "ph_max_pre": float(v_new["ph_max_pre"]),
            "ph_end": float(sim["pH"].to_numpy(float)[-1]),
            "basic_branch_fixed": bool(v_new["basic_branch_fixed"]),
            "ph_hard_max_used": v_new["ph_hard_max_used"],
            "valid_old": valid_old,
            "valid_new": bool(v_new["valid"]),
            "valid_if_basic_fixed": bool(v_relaxed["valid"]),
            "flags": list(v_new["flags"]),
        }
    except Exception as e:  # noqa: BLE001
        return {"batch": int(batch), "mode": mode, "error": f"{type(e).__name__}: {e}"}


def _q(a, p):
    return float(np.percentile(a, p)) if len(a) else float("nan")


def report(rows, tag):
    ok = [r for r in rows if "error" not in r]
    bad = [r for r in rows if "error" in r]
    print(f"\n{'='*78}\n=== {tag}　n={len(ok)}（失败 {len(bad)}）===\n{'='*78}")
    if bad:
        for r in bad[:5]:
            print(f"  ERR b{r['batch']}: {r['error'][:150]}")

    n_old = sum(1 for r in ok if r["valid_old"])
    n_new = sum(1 for r in ok if r["valid_new"])
    n_relax = sum(1 for r in ok if r["valid_if_basic_fixed"])
    print(f"\n【A】valid 计数（分母 {len(ok)}）")
    print(f"   旧判据（R148：越 7 即 invalid）      {n_old}/{len(ok)}")
    print(f"   **新判据（本次修正，auto）**          {n_new}/{len(ok)}")
    print(f"   参考：若 basic 分支已修（越 7 不判）   {n_relax}/{len(ok)}")

    diff = [r for r in ok if r["valid_old"] != r["valid_new"]]
    if diff:
        print(f"\n【B】新旧判据差异（{len(diff)} 批）")
        print(f"   {'批':>4} {'旧':>5} {'新':>5} {'钳位':>5} {'越7步':>6} {'占比':>8} {'pH_max_pre':>11} {'产量偏差':>9}")
        for r in sorted(diff, key=lambda r: r["batch"]):
            print(f"   {r['batch']:>4} {str(r['valid_old']):>5} {str(r['valid_new']):>5}"
                  f" {r['n_ph_clamp']:>5} {r['n_ph_over7']:>6} {r['over7_frac']:>8.4%}"
                  f" {r['ph_max_pre']:>11.3f} {r['yield_err']*100:>8.2f}%")
    else:
        print("\n【B】新旧判据：无差异（默认路径逐位一致）")

    over = [r for r in ok if r["n_ph_over7"] > 0]
    clamp = [r for r in ok if r["n_ph_clamp"] > 0]
    print(f"\n【C】越 7 分布（D-44 教训：报分布不只报计数）")
    print(f"   n_steps：min {min((r['n_steps'] for r in ok), default=0)}"
          f" / max {max((r['n_steps'] for r in ok), default=0)}")
    if over:
        fr = np.array([r["over7_frac"] for r in over])
        ph = np.array([r["ph_max_pre"] for r in over])
        print(f"   越 7 批数 {len(over)}；over7 占比：min {fr.min():.4%} / p50 {_q(fr,50):.4%}"
              f" / p90 {_q(fr,90):.4%} / max {fr.max():.4%}")
        print(f"   ph_max_pre：min {ph.min():.3f} / p50 {_q(ph,50):.3f} / max {ph.max():.3f}")
        print(f"   {'批':>4} {'占比':>9} {'pH_max_pre':>11} {'pH_end':>8} {'产量偏差':>9} {'valid_new':>9}")
        for r in sorted(over, key=lambda r: -r["over7_frac"]):
            print(f"   {r['batch']:>4} {r['over7_frac']:>9.4%} {r['ph_max_pre']:>11.3f}"
                  f" {r['ph_end']:>8.3f} {r['yield_err']*100:>8.2f}% {str(r['valid_new']):>9}")
    else:
        print("   无越 7 批")
    print(f"\n   钳位批（[H⁺] ≤ 0 ⇒ 数值崩溃，**不可放宽**）：{[r['batch'] for r in clamp] or '无'}")
    inv_new = [r["batch"] for r in ok if not r["valid_new"]]
    inv_old = [r["batch"] for r in ok if not r["valid_old"]]
    print(f"   新判据 invalid 名单：{inv_new}")
    print(f"   旧判据 invalid 名单：{inv_old}")
    return {"n": len(ok), "valid_old": n_old, "valid_new": n_new,
            "valid_if_basic_fixed": n_relax, "invalid_new": inv_new,
            "invalid_old": inv_old}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all86", action="store_true")
    ap.add_argument("--batches", type=str, default="")
    ap.add_argument("--candidate-v2", action="store_true", help="用候选基线 v2（ph_fix=1 + mup 重标）")
    ap.add_argument("--workers", type=int, default=7)
    ap.add_argument("--json", type=str, default="")
    args = ap.parse_args()

    if args.batches:
        bs = [int(x) for x in args.batches.split(",") if x.strip()]
    else:
        sys.path.insert(0, ENG)
        from golden_params import GOLDEN_ALL
        bs = list(GOLDEN_ALL)
    mode = "v2" if args.candidate_v2 else "base"
    tag = ("候选基线 v2（ph_fix=1 + mup 重标）" if mode == "v2"
           else "默认基线（ph_fix=0，原 mup）")

    print(f"=== R157 / D-56 validity 判据验证：{tag}　{len(bs)} 批 ===", flush=True)
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        rows = list(ex.map(_one, [(b, mode) for b in bs]))

    summ = report(rows, tag)
    if args.json:
        os.makedirs(os.path.dirname(args.json) or ".", exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"mode": mode, "summary": summ, "rows": rows},
                      f, ensure_ascii=False, indent=1)
        print(f"\nwritten: {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
