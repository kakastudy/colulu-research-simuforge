"""R154：产素—残糖正反馈导致的**双稳态**验证（为什么所有全局旋钮都失败）。

机制假设
--------
1. 产素门控 `P_inhib` 是中心 2 mg/L、半宽 1.5 mg/L 的高斯 ⇒ 相当于"残糖 < 3.5 mg/L"的硬开关。
2. 产素本身是**糖汇**：`dy[0]` 里有 `− Y_sP · r_p`（Y_sP = 0.9 g糖/g产物）。
3. 进料是**数据回放的固定剖面** `Fs(t)`，模型没有葡萄糖控制器。

⇒ 三条合起来构成正反馈：`r_p↓ → 耗糖↓ → S↑ → 门关 → r_p↓`。
若产素占糖汇的比例足够大，这条环路就有增益 >1，系统出现**双稳态/迟滞**：
`mup` 稍有下降就越过鞍结分岔，产素整体熄火（不是缓慢下降）。

本工具做两件事
--------------
A. **糖汇占比**：用 P 平衡 `r_p = dP/dt + (mu_h + D)·P` 反解产素通量，
   与进料糖通量 `I = Fs·c_s/V + Foil·c_oil/V` 相比，给出 `Y_sP·r_p / I` 的时间剖面。
   > 1 的部分说明"产素耗糖超过了进料"，S 必然下降 ⇒ 反馈是实质性的。
B. **mup 扫描**：对若干批把 `mup` 从 0.6× 扫到 1.2×，看产量/形状是**连续**还是**跳变**。
   连续 ⇒ 参数敏感；跳变 ⇒ 双稳态，任何全局旋钮都不可用。

用法
----
    python tools/r154_bistable.py --batches 3,55,59,60 --workers 4
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

PHASE_KEYS = ("0-60", "60-120", "120-180", "180+")


def _gate(s, mean_p=0.002, sd_p=0.0015):
    return 2.5 * sd_p * ((sd_p * np.sqrt(2 * np.pi)) ** -1
                         * np.exp(-0.5 * ((s - mean_p) / sd_p) ** 2))


def _sink_share(sim, par_scalar):
    """产素耗糖 / 进料糖 的时间剖面。只读 sim 列，不碰引擎内部。"""
    t = sim["time_h"].to_numpy(float)
    P = sim["P"].to_numpy(float)
    V = sim["V"].to_numpy(float)
    Fs = sim["Fs"].to_numpy(float)
    Foil = sim["Foil"].to_numpy(float)
    Fb = sim["Fb"].to_numpy(float)
    Fa = sim["Fa"].to_numpy(float)
    Fw = sim["Fw"].to_numpy(float)
    Fpaa = sim["Fpaa"].to_numpy(float)
    pH = sim["pH"].to_numpy(float)
    T = sim["T"].to_numpy(float)

    c_s, c_oil = 600.0, 1000.0
    inflow = Fs * c_s / V + Foil * c_oil / V

    # mu_h：inhib_flag=2 分支，逐字照 model.py
    B = [float(par_scalar[i]) for i in range(80, 85)]
    par18 = float(par_scalar[18])
    k4 = np.exp((B[0] + B[1] * pH + B[2] * T + B[3] * pH ** 2) + B[4] * T ** 2)
    mu_h = k4 * par18
    D = (Fs + Fb + Fa + Fw + Fpaa) / V
    r_p = np.gradient(P, t) + mu_h * P + P * D        # 产素通量（含水解抵消）
    r_p = np.maximum(r_p, 0.0)
    return t, inflow, 0.9 * r_p, inflow


def one(job):
    batch, scales = job
    try:
        import simulate as s
        from golden_params import COMBINED, build_params
        from params import make_params

        base_p = dict(build_params(COMBINED[batch]))
        mup0 = float(base_p.get("mup", 0.041))

        sim0, v30 = s.simulate_open_loop(int(batch), base_p)
        par = make_params(mup=mup0)

        t, inflow, psink, _ = _sink_share(sim0, par)
        out = {"batch": int(batch), "mup0": mup0, "sweep": []}
        m = (t >= 20) & (t < 200) & (inflow > 1e-6)
        if m.sum() > 10:
            share = psink[m] / inflow[m]
            out["sink_share_med"] = float(np.median(share))
            out["sink_share_max"] = float(np.percentile(share, 90))
            out["inflow_med"] = float(np.median(inflow[m]))
            out["psink_med"] = float(np.median(psink[m]))
            # 分相位
            out["sink_share_phase"] = {}
            for k, lo, hi in (("0-60", 0, 60), ("60-120", 60, 120),
                              ("120-180", 120, 180), ("180+", 180, 1e9)):
                mm = (t >= lo) & (t < hi) & (inflow > 1e-6)
                out["sink_share_phase"][k] = (float(np.median(psink[mm] / inflow[mm]))
                                              if mm.sum() > 3 else float("nan"))

        for sc in scales:
            p = dict(base_p)
            p["mup"] = mup0 * sc
            sim, v3 = s.simulate_open_loop(int(batch), p)
            ym = s.yield_metrics(sim, v3)
            sm = s.shape_metrics(sim, v3, channels=("P",))["P"]
            va = s.validity(sim)
            out["sweep"].append({
                "scale": float(sc),
                "yield_err": float(ym["rel_err_total"]),
                "p_relrmse": float(sm["rel_rmse"]),
                "phase": {k: float(sm["phase"][k]["mean"]) for k in PHASE_KEYS},
                "valid": bool(va["valid"]),
            })
        return out
    except Exception as e:  # noqa: BLE001
        return {"batch": int(batch), "error": f"{type(e).__name__}: {e}"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", type=str, default="3,55,59,60")
    ap.add_argument("--scales", type=str, default="0.60,0.70,0.80,0.85,0.90,0.95,1.00,1.05,1.10,1.20")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--json", type=str, default="runs/r154_bistable.json")
    args = ap.parse_args()

    bs = [int(x) for x in args.batches.split(",") if x.strip()]
    scales = [float(x) for x in args.scales.split(",") if x.strip()]

    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        rows = list(ex.map(one, [(b, scales) for b in bs]))

    bad = [r for r in rows if "error" in r]
    rows = [r for r in rows if "error" not in r]
    if args.json:
        os.makedirs(os.path.dirname(args.json) or ".", exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"rows": rows, "errors": bad, "scales": scales}, f,
                      ensure_ascii=False, indent=1)

    print(f"n={len(rows)} errors={len(bad)}")
    for r in bad:
        print("  ERR", r["batch"], r["error"])

    print("\n【A】产素耗糖 / 进料糖（中位，>1 表示产素本身就在拉低残糖）")
    print("   批   mup0    全段    0-60   60-120  120-180   180+")
    for r in rows:
        sp = r["sink_share_phase"]
        print(f"  b{r['batch']:<3d} {r['mup0']:.4f} {r['sink_share_med']:7.3f} " +
              " ".join(f"{sp[k]:+7.3f}" for k in PHASE_KEYS))

    print("\n【B】mup 扫描（产量 %）—— 连续=敏感；跳变=双稳态")
    print("   scale   " + "  ".join(f"b{r['batch']:>3d}" for r in rows))
    for i, sc in enumerate(scales):
        line = f"  {sc:5.2f}   "
        for r in rows:
            v = r["sweep"][i]["yield_err"] * 100
            line += f"{v:+7.2f}  "
        print(line)
    print("\n   relRMSE")
    for i, sc in enumerate(scales):
        line = f"  {sc:5.2f}   "
        for r in rows:
            line += f"{r['sweep'][i]['p_relrmse']:7.3f}  "
        print(line)
    print("\n   valid")
    for i, sc in enumerate(scales):
        line = f"  {sc:5.2f}   "
        for r in rows:
            line += f"{'Y' if r['sweep'][i]['valid'] else 'N':>7s}  "
        print(line)

    # 跳变检测：相邻 scale 之间产量差 > 20pp 即视为跳变
    print("\n【C】跳变检测（相邻 scale 产量差 >20pp）")
    for r in rows:
        jumps = []
        for i in range(1, len(scales)):
            d = (r["sweep"][i]["yield_err"] - r["sweep"][i - 1]["yield_err"]) * 100
            if abs(d) > 20:
                jumps.append((scales[i - 1], scales[i], d))
        print(f"  b{r['batch']:<3d} " + ("; ".join(f"[{a:.2f}->{b:.2f}] {d:+.1f}pp"
                                                  for a, b, d in jumps) if jumps else "无跳变"))


if __name__ == "__main__":
    main()
