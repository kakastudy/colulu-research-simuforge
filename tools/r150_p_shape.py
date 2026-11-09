# -*- coding: utf-8 -*-
"""R150 / D-40：P 通道的误差结构 —— 先看形状，再谈标定。

动机
----
R149 判定 pH 通道不可作标定目标，把 D-40 的处置改到 "P / 产量通道"。
但在动手标定 `mu_p / k_deg / Y_sP / Y_sX` 之前，必须先回答三个前置问题，
否则会重复 R149 的错误（先跑一个 32 min 的评估，才发现目标函数本身不可用）：

1. **P 通道现在到底差多少？** 若 relRMSE 中位只有 8%，问题不在"整体标定"，
   而在少数批的局部结构。
2. **P 的下降通道是什么？** 模型 `dy[3] = r_p - p_deg_rate*P - P*dil`，
   而 `r_p` 自身在产素关闭后等于 `-mu_h·P`（水解）。
   ⇒ 模型**已经**有水解通道（`mu_h`），`p_deg_rate` 是**同一个物理过程的第二套参数**。
   这是可辨识性问题，不是标定问题。
3. **实测 P 的峰后下降有多普遍？** R138 报 "53/100 批峰后下降、40 批降幅 >8%"，
   但那是在 `P` 连续列上算的；本轮复核并把模型的同指标并列。

本工具**只读 + 一次标准仿真**，不改任何参数、不改引擎。

用法
----
    python tools/r150_p_shape.py                       # 86 批验证集
    python tools/r150_p_shape.py --all-100             # 100 批全量
    python tools/r150_p_shape.py --batches 22,36,55
    python tools/r150_p_shape.py --workers 6

输出：runs/r150_p_shape.json
"""
import argparse
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
ENG = os.path.join(ROOT, "candidate", "indpensim", "v0.1")
sys.path.insert(0, ENG)

PHASES = (("0-60", 0.0, 60.0), ("60-120", 60.0, 120.0),
          ("120-180", 120.0, 180.0), ("180+", 180.0, 1e9))


def golden_batches():
    """验证集批号。R148 的纪律：必须从 final_validation_v2.json 取，不能用 sorted(COMBINED)。

    `COMBINED` 含 b99/b100（共 88 批），而冻结验证集是 86 批。R146 的 `dist_flag`
    事故与这个是同型问题：拿一个"看起来对"的批集去跑。
    """
    p = os.path.join(ROOT, "runs", "final_validation_v2.json")
    d = json.load(open(p, encoding="utf-8"))
    rows = d.get("rows") or d.get("results") or []
    bs = []
    for r in rows:
        if isinstance(r, dict):
            b = r.get("batch", r.get("batch_no", r.get("b")))
            if b is not None:
                bs.append(int(b))
    return sorted(set(bs))


def phase_resid(t, sim_v, meas_v, scale):
    """分相位相对残差，以实测峰值归一（P 的绝对值跨批差 4 倍，不能用绝对差）。"""
    out = {}
    for name, lo, hi in PHASES:
        m = (t >= lo) & (t < hi)
        if not np.any(m):
            out[name] = {"mean": float("nan"), "n": 0}
            continue
        d = (sim_v[m] - meas_v[m]) / scale
        out[name] = {"mean": float(np.mean(d)), "n": int(np.sum(m)),
                     "absmax": float(np.max(np.abs(d)))}
    return out


def one(batch):
    from golden_params import COMBINED, build_params
    import simulate as s

    p = build_params(COMBINED[batch])
    sim, v3 = s.simulate_open_loop(int(batch), p)
    ym = s.yield_metrics(sim, v3)
    tm = s.trajectory_metrics(sim, v3)
    va = s.validity(sim)

    t = sim["time_h"].to_numpy(float)
    sP = sim["P"].to_numpy(float)
    tv = v3["time_h"].to_numpy(float)
    mP_raw = v3["P"].to_numpy(float)
    # 按**时间轴**对齐，不按行号（R146 教训）：sim 从 0.4 h 起记录（1149 行），
    # v3 从 0.2 h 起（1150 行），按行号截断会整体错一格 0.2 h。
    # 这也会让本工具的 relRMSE 与 `trajectory_metrics()` 有微小差异——后者是按行号采的。
    _ok = np.isfinite(tv) & np.isfinite(mP_raw)
    mP = np.interp(t, tv[_ok], mP_raw[_ok])
    n = len(t)

    # 同一时间栅格下重算 relRMSE，与分相位残差口径一致
    diff = sP - mP
    rmse = float(np.sqrt(np.mean(diff ** 2)))
    denom = float(np.sum((mP - mP.mean()) ** 2))
    r2 = 1.0 - float(np.sum(diff ** 2)) / denom if denom > 0 else float("nan")

    pmax_m, pmax_s = float(mP.max()), float(sP.max())
    ipk_m, ipk_s = int(np.argmax(mP)), int(np.argmax(sP))
    scale = max(pmax_m, 1e-9)

    return {
        "batch": int(batch),
        "n_rows": int(n),
        "p_rmse": rmse,
        "p_relrmse": rmse / float(np.mean(np.abs(mP))) if np.mean(np.abs(mP)) > 0 else float("nan"),
        "p_r2": r2,
        "p_bias": float(np.mean(diff)) / scale,
        "peak_meas": pmax_m, "peak_sim": pmax_s,
        "t_peak_meas": float(t[ipk_m]), "t_peak_sim": float(t[ipk_s]),
        "end_meas": float(mP[-1]), "end_sim": float(sP[-1]),
        "drop_meas": 1.0 - float(mP[-1]) / scale,
        "drop_sim": 1.0 - float(sP[-1]) / max(pmax_s, 1e-9),
        "end_ratio": float(sP[-1]) / max(float(mP[-1]), 1e-9),
        "peak_ratio": pmax_s / max(pmax_m, 1e-9),
        "phase": phase_resid(t, sP, mP, scale),
        "yield_err": float(ym["rel_err_total"]),
        "valid": bool(va["valid"]),
        "flags": list(va["flags"]),
        "p_deg_rate": float(p.get("p_deg_rate", 0.0)),
    }


def summarise(rows):
    a = np.array([[r["p_relrmse"], r["p_r2"], r["drop_meas"], r["drop_sim"],
                   r["yield_err"], r["peak_ratio"], r["end_ratio"]] for r in rows])
    def q(name, v):
        return {name: {"median": float(np.median(v)), "p90": float(np.percentile(v, 90)),
                       "max": float(np.max(v)), "min": float(np.min(v))}}
    out = {}
    out.update(q("p_relrmse", a[:, 0]))
    out.update(q("p_r2", a[:, 1]))
    out.update(q("drop_meas", a[:, 2]))
    out.update(q("drop_sim", a[:, 3]))
    out.update(q("yield_err", a[:, 4]))
    out.update(q("peak_ratio", a[:, 5]))
    out.update(q("end_ratio", a[:, 6]))
    out["n"] = len(rows)
    out["n_valid"] = int(sum(1 for r in rows if r["valid"]))
    out["n_yield_ok"] = int(sum(1 for r in rows if abs(r["yield_err"]) <= 0.05))
    out["n_drop_meas_gt5"] = int(sum(1 for r in rows if r["drop_meas"] > 0.05))
    out["n_drop_meas_gt20"] = int(sum(1 for r in rows if r["drop_meas"] > 0.20))
    out["n_drop_sim_gt5"] = int(sum(1 for r in rows if r["drop_sim"] > 0.05))
    # P 通道差 与 实测降幅 的相关（若结构性缺项，应当强正相关）
    if len(rows) > 2:
        out["corr_relrmse_dropmeas"] = float(np.corrcoef(a[:, 0], a[:, 2])[0, 1])
        out["corr_relrmse_yielderr"] = float(np.corrcoef(a[:, 0], np.abs(a[:, 4]))[0, 1])
        out["corr_relrmse_valid"] = float(np.corrcoef(a[:, 0],
                                         np.array([1.0 if r["valid"] else 0.0 for r in rows]))[0, 1])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", type=str, default="")
    ap.add_argument("--all-100", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    if args.batches:
        bs = [int(x) for x in args.batches.split(",") if x.strip()]
        src = "manual"
    elif args.all_100:
        bs = list(range(1, 101))
        src = "all100"
    else:
        bs = golden_batches()
        src = "golden86"
    if args.limit:
        bs = bs[: args.limit]
    print(f"[r150] batches = {len(bs)} ({src}); workers = {args.workers}")

    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        rows = list(ex.map(one, bs))

    summ = summarise(rows)
    out = {"source": src, "batches": bs, "summary": summ, "rows": rows}
    op = os.path.join(ROOT, "runs", "r150_p_shape.json")
    json.dump(out, open(op, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"\n=== 汇总（{summ['n']} 批）===")
    print(f"  P relRMSE   中位 {summ['p_relrmse']['median']:.4f}  P90 {summ['p_relrmse']['p90']:.4f}"
          f"  max {summ['p_relrmse']['max']:.4f}")
    print(f"  P R2        中位 {summ['p_r2']['median']:.4f}  min {summ['p_r2']['min']:.4f}")
    print(f"  实测降幅    中位 {summ['drop_meas']['median']:.3f}  >5%: {summ['n_drop_meas_gt5']}/{summ['n']}"
          f"  >20%: {summ['n_drop_meas_gt20']}/{summ['n']}")
    print(f"  模型降幅    中位 {summ['drop_sim']['median']:.3f}  >5%: {summ['n_drop_sim_gt5']}/{summ['n']}")
    print(f"  产量误差    中位 {summ['yield_err']['median']:+.4f}  |err|<=5%: {summ['n_yield_ok']}/{summ['n']}")
    print(f"  valid {summ['n_valid']}/{summ['n']}")
    print(f"  峰比 中位 {summ['peak_ratio']['median']:.3f}  末比 中位 {summ['end_ratio']['median']:.3f}")
    print(f"  相关: relRMSE~实测降幅 {summ.get('corr_relrmse_dropmeas', float('nan')):+.3f}"
          f"  ~|产量误差| {summ.get('corr_relrmse_yielderr', float('nan')):+.3f}"
          f"  ~valid {summ.get('corr_relrmse_valid', float('nan')):+.3f}")

    print("\n=== P relRMSE 最差的 15 批 ===")
    print(" 批  relRMSE  R2     实测降 模型降 峰比  末比   产量%   valid  分相位残差 0-60/60-120/120-180/180+")
    for r in sorted(rows, key=lambda r: -r["p_relrmse"])[:15]:
        ph = " ".join(f"{r['phase'][k]['mean']:+.3f}" for k, _, _ in PHASES)
        print(f"{r['batch']:>3d}  {r['p_relrmse']:.4f}  {r['p_r2']:+.3f}  "
              f"{r['drop_meas']:5.1%} {r['drop_sim']:5.1%}  {r['peak_ratio']:5.2f} {r['end_ratio']:5.2f}  "
              f"{r['yield_err']*100:+6.2f}  {'Y' if r['valid'] else 'N'}    {ph}")
    print(f"\nwritten: {op}")


if __name__ == "__main__":
    main()
