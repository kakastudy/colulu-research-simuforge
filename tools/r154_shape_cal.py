"""R154：批级形状标定 —— 开"形状旋钮"的同时**逐批反解 `mup`**，把产量钉回标定值。

为什么这是"标定"而不是"拟合"
--------------------------
R152/R153 的结论是"全局形状旋钮修好形状但产量逐批崩"。本轮核实了一个此前被记错的事实：

  > `params["mup"]` **就是** `mu_p` 的批级覆盖 —— `simulate_open_loop` 里
  > `mup=params.get("mup", 0.041)` → `par[0]`，而 `golden_params.COMBINED`
  > 里 b22 的 `mup = 0.065`，是默认值 0.012 的 **5.4 倍**。

也就是说，本模型的标定范式**本来就是逐批的**（`mup`/`mux`/`mu_h_scale`/`m_s`/`alpha_kla` 全是批级量）。
因此"给每批再解一个 `mup`"不构成新的自由度滥用 —— 它与既有范式一致。
真正被证伪的是"用**一个**全局乘数去修所有批"。

方法（每批 2 次仿真）
--------------------
1. 基线：`mup0`，臂参数全关 ⇒ 与冻结基线逐位相同（`yield_err = e0`）。
2. 探针：开臂、`mup = mup0` ⇒ 得 `e1`。产素积分近似正比于 `mup`，故
   `mup* = mup0 · (1+e0)/(1+e1)` 可把期末产量钉回 `e0`。
3. 复核：臂 + `mup = mup*` ⇒ 报最终 `yield_err / p_relrmse / 相位 / valid`。

判据
----
- 产量回到基线水平：`|yield_err − e0| ≤ 0.005`（0.5 个百分点）
- `valid` 不得下降
- 形状：`p_relrmse` 中位下降、`60-120` 相位向 0 靠、峰比/末比不恶化

用法
----
    python tools/r154_shape_cal.py --arm sd18 --batches 3,22,36 --workers 3
    python tools/r154_shape_cal.py --arms sd18,sd20,lam045 --workers 7
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

# 基线值（R152 已核对：P_std_dev = par[3] = 1.5e-3 g/L，mean_P = par[4] = 2e-3 g/L）
SD0 = 0.0015
MP0 = 0.002

# 每个臂 = 一组"形状旋钮"覆盖。`mup` 一律由工具逐批反解，不在此处给。
ARMS = {
    # R152 的 86 批最佳臂里的两个"形状"分量（当时的 mup×0.66 是全局补偿，本轮改为逐批反解）
    "sd18":   {"P_std_dev": SD0 * 1.8, "mean_P": MP0 * 1.10},
    "sd20":   {"P_std_dev": SD0 * 2.0, "mean_P": MP0 * 1.10},
    # R153 的生长耦合项（第五版形式），作为对照臂
    "lam045": {"mu_p_growth": 0.45},
    "lam060": {"mu_p_growth": 0.60},
    # 组合：宽门控 + 生长耦合
    "sd18_lam030": {"P_std_dev": SD0 * 1.8, "mean_P": MP0 * 1.10, "mu_p_growth": 0.30},
}


def _metrics(sim, v3):
    import simulate as s
    ym = s.yield_metrics(sim, v3)
    sm = s.shape_metrics(sim, v3, channels=("P",))["P"]
    va = s.validity(sim)
    return {
        "yield_err": float(ym["rel_err_total"]),
        "p_relrmse": float(sm["rel_rmse"]),
        "p_r2": float(sm["r2"]),
        "peak_ratio": float(sm["peak_ratio"]),
        "end_ratio": float(sm["end_ratio"]),
        "phase": {k: float(sm["phase"][k]["mean"]) for k in PHASE_KEYS},
        "valid": bool(va["valid"]),
        "flags": list(va["flags"]),
    }


def one(job):
    batch, arms = job
    try:
        import simulate as s
        from golden_params import COMBINED, build_params

        base_p = dict(build_params(COMBINED[batch]))
        mup0 = float(base_p.get("mup", 0.041))

        sim0, v30 = s.simulate_open_loop(int(batch), base_p)
        base = _metrics(sim0, v30)

        out = []
        for name in arms:
            ov = ARMS[name]
            p1 = dict(base_p)
            p1.update(ov)
            sim1, v31 = s.simulate_open_loop(int(batch), p1)
            m1 = _metrics(sim1, v31)

            ratio = (1.0 + base["yield_err"]) / (1.0 + m1["yield_err"]) \
                if abs(1.0 + m1["yield_err"]) > 1e-9 else 1.0
            ratio = float(np.clip(ratio, 0.40, 1.60))

            p2 = dict(p1)
            p2["mup"] = mup0 * ratio
            sim2, v32 = s.simulate_open_loop(int(batch), p2)
            m2 = _metrics(sim2, v32)
            m2["arm"] = name
            m2["mup_scale"] = ratio
            out.append(m2)

        return {"batch": int(batch), "mup0": mup0, "base": base, "arms": out}
    except Exception as e:  # noqa: BLE001
        return {"batch": int(batch), "error": f"{type(e).__name__}: {e}"}


def _pick(rows, name):
    return [(r, a) for r in rows for a in r.get("arms", []) if a["arm"] == name]


def _agg(rows, name):
    pairs = _pick(rows, name)
    if not pairs:
        return None
    d = {"n": len(pairs)}
    for k in ("yield_err", "p_relrmse", "peak_ratio", "end_ratio"):
        v = np.array([a[k] for _, a in pairs], float)
        v = v[np.isfinite(v)]
        d[k + "_median"] = float(np.median(v)) if v.size else float("nan")
        d[k + "_mean"] = float(np.mean(v)) if v.size else float("nan")
    for k in PHASE_KEYS:
        v = np.array([a["phase"][k] for _, a in pairs], float)
        v = v[np.isfinite(v)]
        d[f"phase_{k}"] = float(np.mean(v)) if v.size else float("nan")
    d["n_valid"] = int(sum(1 for _, a in pairs if a["valid"]))
    d["n_yield_ok"] = int(sum(1 for _, a in pairs if abs(a["yield_err"]) <= 0.05))
    d["n_yield_kept"] = int(sum(1 for r, a in pairs
                               if abs(a["yield_err"] - r["base"]["yield_err"]) <= 0.005))
    d["n_relrmse_better"] = int(sum(1 for r, a in pairs
                                    if a["p_relrmse"] < r["base"]["p_relrmse"] - 1e-12))
    d["n_relrmse_med_ok"] = int(sum(1 for r, a in pairs
                                    if abs(a["peak_ratio"] - 1.0)
                                    <= abs(r["base"]["peak_ratio"] - 1.0) + 1e-12))
    return d


def _base_agg(rows):
    d = {"n": len(rows)}
    for k in ("yield_err", "p_relrmse", "peak_ratio", "end_ratio"):
        v = np.array([r["base"][k] for r in rows], float)
        d[k + "_median"] = float(np.median(v))
        d[k + "_mean"] = float(np.mean(v))
    for k in PHASE_KEYS:
        d[f"phase_{k}"] = float(np.mean([r["base"]["phase"][k] for r in rows]))
    d["n_valid"] = int(sum(1 for r in rows if r["base"]["valid"]))
    d["n_yield_ok"] = int(sum(1 for r in rows if abs(r["base"]["yield_err"]) <= 0.05))
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", type=str, default="")
    ap.add_argument("--arm", type=str, default="")
    ap.add_argument("--arms", type=str, default="sd18")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--json", type=str, default="runs/r154_shape_cal.json")
    args = ap.parse_args()

    names = [x.strip() for x in (args.arm or args.arms).split(",") if x.strip()]
    unknown = [x for x in names if x not in ARMS]
    if unknown:
        raise SystemExit(f"未知臂 {unknown}；可选 {sorted(ARMS)}")

    if args.batches:
        bs = [int(x) for x in args.batches.split(",") if x.strip()]
    else:
        from golden_params import COMBINED
        bs = sorted(k for k in COMBINED if k != 0)

    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        rows = list(ex.map(one, [(b, names) for b in bs]))

    bad = [r for r in rows if "error" in r]
    rows = [r for r in rows if "error" not in r]
    if args.json:
        os.makedirs(os.path.dirname(args.json) or ".", exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"rows": rows, "errors": bad, "arms": names}, f,
                      ensure_ascii=False, indent=1)

    print(f"n={len(rows)} errors={len(bad)}")
    for r in bad[:5]:
        print("  ERR", r["batch"], r["error"])

    def line(tag, d):
        print(f"{tag:22s} {d['p_relrmse_median']:8.4f} {d['p_relrmse_mean']:8.4f} "
              f"{d['peak_ratio_median']:6.3f} {d['end_ratio_median']:6.3f} " +
              " ".join(f"{d['phase_' + k]:+7.4f}" for k in PHASE_KEYS) +
              f" | {d['yield_err_median'] * 100:+6.2f}% {d['n_valid']:2d} {d['n_yield_ok']:2d}")

    print("\n臂                     relRMSE中 relRMSE均   峰比   末比   "
          "0-60    60-120  120-180 180+    | 产量中  valid 产量OK")
    line("base", _base_agg(rows))
    for n in names:
        d = _agg(rows, n)
        if d:
            line(n, d)
            print(f"   产量保持(±0.5pp) {d['n_yield_kept']}/{d['n']}  "
                  f"relRMSE 改善 {d['n_relrmse_better']}/{d['n']}  "
                  f"|峰比−1| 未恶化 {d['n_relrmse_med_ok']}/{d['n']}")


if __name__ == "__main__":
    main()
