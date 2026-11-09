"""R147 / D-36：pH 方程里 r_p 的三口径对比（算子层，opt-in）。

背景：R145 关闭 D-32 时只在两个端点上做了反事实——
  (a) 默认  = 水解经 gamma1 进入 pH 方程，表现为**产碱**（MATLAB 原文）；
  (b) ph_hyd_acid=True = 水解翻正为**产酸**（已证伪：pH 末 5.0–5.3、46 批破线）。
中间那一档（水解在质子平衡里**完全不计**）从未验证。物理上它才是对的：
β-内酰胺开环生成青霉噻唑酸确实多一个可解离 COOH，但同时消耗一分子水，
净质子变化接近零；把它写成"碱化"或"产酸"都是在给一个近似零的量强加符号。

本工具跑三口径：
  net        —— 现行默认（零回归基线）
  prod_only  —— 只计产素项（水解不计）
  all_acid   —— 水解按产酸（复现 R145 的反事实臂，作对照）

判据（按顺序）：
  1. 零回归：net 的 yield 必须与冻结基准逐批一致（max|Δ|=0）
  2. 悬崖：prod_only 是否把 pH max 压回 7.0 以下、钳位样点是否归零
  3. 不改好批：12 批黄金集上 prod_only 的产量偏差是否仍 ±5%

用法：
  python tools/r147_d36_rp_mode.py --workers 4
  python tools/r147_d36_rp_mode.py --batches 37,50,51,91,92 --workers 4
"""

import argparse
import contextlib
import io
import json
import os
import sys
from multiprocessing import Pool

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENG = os.path.join(ROOT, "candidate", "indpensim", "v0.1")
sys.path.insert(0, ENG)

import simulate as S  # noqa: E402
from golden_params import params_for  # noqa: E402

# 5 批被守卫钳位的批（R145 §6 认定）+ 12 批黄金集
CLAMPED = [37, 50, 51, 91, 92]
GOLDEN = [8, 11, 16, 22, 23, 27, 36, 55, 60, 80, 91, 92]
MODES = ["net", "prod_only", "all_acid"]


def run_one(task):
    """跑一批一个口径，返回关键指标。"""
    b, mode = task
    params = dict(params_for(b), ph_rp_mode=mode)
    with contextlib.redirect_stdout(io.StringIO()):
        sim, v3 = S.simulate_open_loop(b, params)
        ym = S.yield_metrics(sim, v3)
    ph = sim["pH"].to_numpy(float)
    P = sim["P"].to_numpy(float)
    t = sim["time_h"].to_numpy(float)
    ok = np.isfinite(ph)
    return {
        "batch": int(b),
        "mode": mode,
        "yield_err": float(ym["rel_err_total"]),
        "ph_min": float(np.nanmin(ph[ok])),
        "ph_max": float(np.nanmax(ph[ok])),
        "ph_end": float(ph[ok][-1]),
        "n_clamp": int(np.sum(ph[ok] <= 3.05)),
        "n_over7": int(np.sum(ph[ok] >= 7.0)),
        "first_over7_t": (float(t[ok][np.argmax(ph[ok] >= 7.0)]) if np.any(ph[ok] >= 7.0) else None),
        "P_end_over_peak": float(P[ok][-1] / max(P[ok].max(), 1e-12)),
        # 产酸源（尾三分之一）中位数在另一个工具里算，这里只留 pH 侧证据
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--batches", type=str, default="", help="逗号分隔；留空=钳位5批+黄金12批")
    ap.add_argument("--out", type=str, default="runs/r147_d36_rp_mode.json")
    args = ap.parse_args()

    if args.batches:
        batches = [int(x) for x in args.batches.split(",") if x.strip()]
    else:
        batches = sorted(set(CLAMPED) | set(GOLDEN))

    tasks = [(b, m) for b in batches for m in MODES]
    with Pool(args.workers) as ex:
        rows = list(ex.map(run_one, tasks))
    grid = {(r["batch"], r["mode"]): r for r in rows}

    # ---- 闸门 1：net 必须等于冻结基准 ----
    frozen_path = os.path.join(ROOT, "runs", "final_validation_v2.json")
    frozen = {}
    if os.path.exists(frozen_path):
        with open(frozen_path, encoding="utf-8") as f:
            for r in json.load(f)["results"]:
                frozen[int(r["batch"])] = float(r["yield_err"])
    deltas = [abs(grid[(b, "net")]["yield_err"] - frozen[b]) * 100
              for b in batches if b in frozen]
    dmax = max(deltas) if deltas else float("nan")
    print(f"[闸门1 零回归] net 口径 vs 冻结基准  max|Δyield| = {dmax:.3e} pt"
          f"（{len(deltas)} 批）")
    if deltas and dmax > 1e-6:
        raise SystemExit("net 口径未能复现冻结基准，先修口径再谈对比")

    # ---- 主表 ----
    hdr = (f"{'b':>4} | {'mode':<10} | {'产率偏差':>9} | {'pHmin':>6} | {'pHmax':>6} | "
           f"{'pH末':>6} | {'钳位':>5} | {'≥7':>4} | {'P末/峰':>7}")
    print("\n" + hdr)
    print("-" * len(hdr))
    for b in batches:
        for m in MODES:
            r = grid[(b, m)]
            print(f"{b:>4} | {m:<10} | {r['yield_err']:>+8.2%} | {r['ph_min']:>6.3f} | "
                  f"{r['ph_max']:>6.3f} | {r['ph_end']:>6.3f} | {r['n_clamp']:>5d} | "
                  f"{r['n_over7']:>4d} | {r['P_end_over_peak']:>7.3f}")
        print("-" * len(hdr))

    # ---- 汇总 ----
    print("\n[汇总]")
    for m in MODES:
        rs = [grid[(b, m)] for b in batches]
        wy = [r for r in rs if {r["batch"]} <= set(GOLDEN)]
        n5 = sum(1 for r in wy if abs(r["yield_err"]) <= 0.05)
        print(f"  {m:<10} pHmax 最大={max(r['ph_max'] for r in rs):.3f}  "
              f"钳位总样点={sum(r['n_clamp'] for r in rs):>5d}  "
              f"≥7 总样点={sum(r['n_over7'] for r in rs):>5d}  "
              f"黄金批 ±5%={n5}/{len(wy)}  "
              f"黄金批 max|err|={max(abs(r['yield_err']) for r in wy):.2%}")

    # ---- 与 net 的逐批产量差（只看变化幅度） ----
    print("\n[相对 net 的产量改变]")
    for b in batches:
        n = grid[(b, "net")]["yield_err"]
        po = grid[(b, "prod_only")]["yield_err"]
        aa = grid[(b, "all_acid")]["yield_err"]
        print(f"  b{b:<3d} net={n:>+8.2%}  prod_only={po:>+8.2%} (Δ{(po-n)*100:>+7.2f}pt)  "
              f"all_acid={aa:>+8.2%} (Δ{(aa-n)*100:>+7.2f}pt)")

    out = {
        "round": "R147",
        "debt": "D-36",
        "batches": batches,
        "modes": MODES,
        "gate_net_vs_frozen_max_abs_delta_pt": dmax,
        "rows": rows,
    }
    op = os.path.join(ROOT, args.out)
    os.makedirs(os.path.dirname(op), exist_ok=True)
    with open(op, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"\n写出 {op}")


if __name__ == "__main__":
    main()
