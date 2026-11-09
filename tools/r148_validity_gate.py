# -*- coding: utf-8 -*-
"""R148 / D-34 第 2 步 —— 在 `validity()` 硬约束下诚实统计 86 批。

背景
----
R147 台账 §三 的路径是：①把 pH 越界做成硬约束 → ②在 invalid 判据下重算 86 批，
诚实统计还剩几批合格。本工具做的就是第 ②步。

之前的 `86/86 ±5%` 口径把"守卫钳位后凑出来的产量"也算作模型输出。本工具回答三个问题：

  Q1  86 批里有多少批是 `valid`（未越 7.0 且未钳位）？
  Q2  只看 `valid` 批，RMSE / ±5% 命中是多少？
  Q3  `invalid` 批的产量误差分布是什么样的？（它们此前被算进了 86/86）

用法
----
    python tools/r148_validity_gate.py                 # 全 86 批
    python tools/r148_validity_gate.py --workers 8
    python tools/r148_validity_gate.py --batches 37,91 # 指定批

输出：`runs/r148_validity_gate.json`

口径闸门
--------
`validity()` 依赖 `sim.attrs["guard_audit"]`（R148 新增）。若某批没拿到审计，
`validity()` 会退回 pH ≤ 3.05 的阈值近似并在 `flags` 里标 `no_guard_audit`——
本工具遇到这种情况直接报错退出，**不允许静默降级**。
"""
import argparse
import json
import os
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))


def one(batch):
    """单批：跑默认参数，返回产量误差 + 有效性判定 + 审计明细。"""
    from golden_params import COMBINED, build_params
    from simulate import simulate_open_loop, yield_metrics, validity
    import numpy as np

    sim, v3 = simulate_open_loop(batch, build_params(COMBINED[batch]))
    ym = yield_metrics(sim, v3)
    vd = validity(sim)
    ga = sim.attrs.get("guard_audit", {})
    ph = sim["pH"].to_numpy(float)
    pre = sim["pH_pre"].to_numpy(float)

    # pH 锁死段：连续处于 ≤3.05 的样点数（与"守卫改写次数"是两件事，见报告 §2）
    locked = 0
    best = 0
    for v in ph:
        if v <= 3.05:
            best += 1
            locked = max(locked, best)
        else:
            best = 0

    return {
        "batch": int(batch),
        "yield_err_pct": float(ym["rel_err_total"]) * 100.0,
        "yield_sim_g": float(ym["total_sim_g"]),
        "valid": bool(vd["valid"]),
        "suspect": bool(vd["suspect"]),
        "flags": vd["flags"],
        "ph_max_pre": float(vd["ph_max_pre"]),
        "ph_max_post": float(np.nanmax(ph)),
        "ph_end": float(ph[-1]),
        "n_ph_clamp": int(vd["n_ph_clamp"]),
        "n_ph_over7": int(vd["n_ph_over7"]),
        "n_steps": int(ga.get("n_steps", 0)),
        "n_locked_ph3": int(locked),
        "n_locked_total": int((ph <= 3.05).sum()),
        "ph_nonpos_steps": int(ga.get("ph_nonpos_steps", 0)),
        "other_clamped": vd["other_clamped"],
    }


def summarise(rows, label):
    import numpy as np
    n = len(rows)
    err = np.array([r["yield_err_pct"] for r in rows], float)
    rmse = float(np.sqrt(np.mean(err ** 2)))
    within5 = int((np.abs(err) <= 5.0).sum())
    print(f"  {label:<26s} n={n:3d}  RMSE={rmse:7.3f}%  ±5%={within5:3d}/{n:<3d} "
          f"max|err|={np.abs(err).max():7.2f}%")
    return {
        "label": label, "n": n, "rmse_pct": round(rmse, 4),
        "within5": within5, "max_abs_err_pct": round(float(np.abs(err).max()), 4),
        "batches": [r["batch"] for r in rows],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--batches", type=str, default="", help="逗号分隔；默认全 86 批")
    ap.add_argument("--out", default=os.path.join(ROOT, "runs", "r148_validity_gate.json"))
    args = ap.parse_args()

    # 批集必须与零回归口径一致：`COMBINED` 有 88 个键，但 `runs/final_validation_v2.json`
    # 的验收集是 86 批（不含 b99/b100）。直接用 sorted(COMBINED) 会把样本数变成 88，
    # 让 "x/86" 与 "x/88" 两个分母混在一起——R146 的 dist_flag 事故同型。
    from golden_params import COMBINED
    if args.batches:
        batches = [int(x) for x in args.batches.split(",") if x.strip()]
    else:
        with open(os.path.join(ROOT, "runs", "final_validation_v2.json"), encoding="utf-8") as f:
            batches = sorted(int(r["batch"]) for r in json.load(f)["results"])
    missing = [b for b in batches if b not in COMBINED]
    if missing:
        raise SystemExit(f"❌ 以下批号不在 COMBINED 中：{missing}")

    print("=" * 96)
    print(f"R148 有效性闸门（D-34）：{len(batches)} 批")
    print("判据：pH 守卫前从未 ≥ 7.0  且  pH_H 从未被守卫改写")
    print("=" * 96, flush=True)

    t0 = time.time()
    from multiprocessing import Pool
    with Pool(min(args.workers, os.cpu_count() or 1)) as pool:
        rows = pool.map(one, batches, chunksize=1)
    rows.sort(key=lambda r: r["batch"])

    # ---- 口径闸门：不允许静默退回阈值近似 ----
    degraded = [r["batch"] for r in rows
                if any("no_guard_audit" in f for f in r["flags"])]
    if degraded:
        raise SystemExit(f"❌ 以下批次没有 guard_audit，validity 退回近似口径：{degraded}")

    valid = [r for r in rows if r["valid"]]
    invalid = [r for r in rows if not r["valid"]]
    suspect = [r for r in rows if r["valid"] and r["suspect"]]

    # ---- 逐批明细 ----
    print(f"\n[1] 逐批明细（按批号）")
    print(f"  {'批':>3s} {'valid':>6s} {'产率':>9s} {'pHmax前':>9s} {'pH末':>7s} "
          f"{'钳':>4s} {'越7':>4s} {'锁死':>5s}  说明")
    for r in rows:
        mark = "✅" if r["valid"] else "❌"
        note = "" if r["valid"] else r["flags"][0][:44]
        print(f"  {r['batch']:>3d} {mark:>6s} {r['yield_err_pct']:>+8.2f}% "
              f"{r['ph_max_pre']:>9.3f} {r['ph_end']:>7.3f} "
              f"{r['n_ph_clamp']:>4d} {r['n_ph_over7']:>4d} {r['n_locked_ph3']:>5d}  {note}")

    # ---- 汇总 ----
    print(f"\n[2] 汇总")
    s_all = summarise(rows, "全部（旧 86/86 口径）")
    s_val = summarise(valid, "仅 valid") if valid else None
    s_inv = summarise(invalid, "仅 invalid（此前被算进）") if invalid else None

    print(f"\n  valid {len(valid)}/{len(rows)} 批；其中 suspect（非 pH 关键量被钳）{len(suspect)} 批")
    if invalid:
        print(f"  invalid 批号：{', '.join(str(r['batch']) for r in invalid)}")

    # ---- 精度有多少来自 invalid 批 ----
    if valid and invalid:
        import numpy as np
        tot = sum(r["yield_err_pct"] ** 2 for r in rows)
        val = sum(r["yield_err_pct"] ** 2 for r in valid)
        print(f"\n[3] 平方误差构成：invalid 批占 {100*(1-val/tot):.1f}% "
              f"（{len(invalid)}/{len(rows)} 批）")

    out = {
        "meta": {
            "criterion": "pH_pre < 7.0 AND n_ph_clamp == 0",
            "ph_crit": 7.0, "n": len(rows),
            "elapsed_s": round(time.time() - t0, 1),
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        },
        "summary": {
            "all": s_all,
            "valid": s_val,
            "invalid": s_inv,
            "n_valid": len(valid), "n_invalid": len(invalid),
            "invalid_batches": [r["batch"] for r in invalid],
            "suspect_batches": [r["batch"] for r in suspect],
        },
        "rows": rows,
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"\n写出 {args.out}  ({time.time()-t0:.0f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
