"""R154 / D-44：S 通道的两种误差必须分开 —— 峰值误差 vs 残糖水平误差。

背景
----
R151 把 S 的 `s_r2` 放进验收，结果 14/86 批 R²<0（最差 b78 −2.216）。但 S 的**方差几乎全部
来自 0–20 h 的初始葡萄糖峰**（1–57 g/L），而 30–120 h 的残糖只有 2 mg/L。于是：

  · R² 只看得到"初始峰对不对"，看不到"残糖水平对不对"；
  · 而 P 的产素门控 `P_inhib = Gauss(s; mean_P=2 mg/L, sd=1.5 mg/L)` 恰恰只由**残糖水平**决定。

⇒ S 通道的"误差大"与"门控错位"是**两件事**，必须分开度量。本工具按两者分别输出。

口径
----
1. `s_peak_{model,meas}`、`s_peak_t_*`：初始峰的高度与时刻（峰定义为 t<40 h 内的最大值）。
2. `s_resid_{model,meas}`：30–120 h 内 S 的中位数 —— 这就是**门控自变量**的实际水平。
3. `gate_{model,meas}_med`：0–60 h 内 `P_inhib` 的中位数，分别用模型 S 与实测 S 代入。
   这是"如果 S 对了，门会开多大"的直接度量。
4. `s_err_peaknorm_{phase}`：`(S_sim − S_meas)/max(S_meas)` 逐点均值 —— 用**峰值**归一，
   避免 2 mg/L 段分母爆炸（R151 对 relRMSE 的同一教训）。
5. `s_r2_hi`：只在 `S_meas > 5%·peak` 的点上算 R² —— 剔掉"全零段"后的真实拟合度。

输出 `runs/r154_s_resid.json`。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENG = os.path.join(ROOT, "candidate", "indpensim", "v0.1")
if ENG not in sys.path:
    sys.path.insert(0, ENG)

MEAN_P = 0.002    # par[4]（g/L）；从 params 现读，见 _gate()
SD_P = 0.0015     # par[3]（g/L）
PHASES = (("0-60", 0, 60), ("60-120", 60, 120), ("120-180", 120, 180), ("180+", 180, 1e9))


def _gate(s, mean_p, sd_p):
    """P_inhib 原式：2.5·sd·N(s; mean, sd) = 0.5·(1+... ) 形式？—— 逐字照 model.py。

    `P_inhib = 2.5 * P_std_dev * ((P_std_dev*sqrt(2*pi))**-1 * exp(-0.5*((s-mean)/sd)^2))`
    = 0.9974 * exp(...)  ⇒ 峰值为 1 的窄高斯。
    """
    return 2.5 * sd_p * ((sd_p * np.sqrt(2 * np.pi)) ** -1
                         * np.exp(-0.5 * ((s - mean_p) / sd_p) ** 2))


def one(b):
    import simulate as S
    from golden_params import COMBINED, build_params
    from params import make_params

    p = make_params(mup=COMBINED[b].get("mup", 0.041))
    mean_p, sd_p = float(p[4]), float(p[3])

    sim, v3 = S.simulate_open_loop(b, build_params(COMBINED[b]))
    t = sim["time_h"].to_numpy(float)
    s_m = sim["S"].to_numpy(float)
    tv = v3["time_h"].to_numpy(float)
    s_v = v3["S"].to_numpy(float)

    # 按时间轴对齐（R150 教训：绝不按行号截断）
    ok = np.isfinite(tv) & np.isfinite(s_v)
    s_vi = np.interp(t, tv[ok], s_v[ok])

    out = {"batch": int(b), "tmax": float(t.max())}

    # 1) 初始峰
    m_early = t < 40.0
    ip = int(np.argmax(s_m[m_early]))
    iv = int(np.argmax(s_vi[m_early]))
    out["s_peak_model"] = float(s_m[m_early][ip])
    out["s_peak_t_model"] = float(t[m_early][ip])
    out["s_peak_meas"] = float(s_vi[m_early][iv])
    out["s_peak_t_meas"] = float(t[m_early][iv])
    out["s_peak_ratio"] = (out["s_peak_model"] / out["s_peak_meas"]
                           if out["s_peak_meas"] > 0 else float("nan"))

    # 2) 残糖水平（门控自变量）
    m_res = (t >= 30) & (t <= 120)
    out["s_resid_model"] = float(np.median(s_m[m_res]))
    out["s_resid_meas"] = float(np.median(s_vi[m_res]))
    out["s_resid_ratio"] = (out["s_resid_model"] / out["s_resid_meas"]
                            if out["s_resid_meas"] > 0 else float("nan"))

    # 3) 门控对比（0–60 h）
    m06 = (t >= 0) & (t < 60)
    g_m = _gate(s_m[m06], mean_p, sd_p)
    g_v = _gate(s_vi[m06], mean_p, sd_p)
    out["gate_model_med"] = float(np.median(g_m))
    out["gate_meas_med"] = float(np.median(g_v))
    out["gate_model_mean"] = float(np.mean(g_m))
    out["gate_meas_mean"] = float(np.mean(g_v))
    # 门控在 0–60 h 的"开度占空"：gate>0.5 的时间比
    out["gate_model_duty"] = float(np.mean(g_m > 0.5))
    out["gate_meas_duty"] = float(np.mean(g_v > 0.5))

    # 4) 分相位误差（峰值归一）
    pk = max(out["s_peak_meas"], 1e-9)
    for name, lo, hi in PHASES:
        m = (t >= lo) & (t < hi)
        out[f"s_err_{name}"] = float(np.mean((s_m[m] - s_vi[m]) / pk)) if m.sum() else float("nan")

    # 5) R²（全域）与 R²_hi（只在有糖段）
    def r2(y, yh):
        ss = float(np.sum((y - y.mean()) ** 2))
        return float(1.0 - np.sum((y - yh) ** 2) / ss) if ss > 0 else float("nan")
    out["s_r2"] = r2(s_vi, s_m)
    m_hi = s_vi > 0.05 * pk
    out["s_r2_hi"] = r2(s_vi[m_hi], s_m[m_hi]) if m_hi.sum() > 5 else float("nan")
    out["n_hi"] = int(m_hi.sum())

    # 6) 实测 S 中该批"残糖"的稳定性（判断 2 mg/L 是否为准稳态平台）
    out["s_resid_meas_sd"] = float(np.std(s_vi[m_res]))
    return out


def _safe(b):
    try:
        return one(b)
    except Exception as e:  # noqa: BLE001
        return {"batch": int(b), "error": f"{type(e).__name__}: {e}"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", type=str, default="")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--json", type=str, default="runs/r154_s_resid.json")
    args = ap.parse_args()

    if args.batches:
        bs = [int(x) for x in args.batches.split(",") if x.strip()]
    else:
        from golden_params import COMBINED
        bs = sorted(k for k in COMBINED if k != 0)

    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        rows = list(ex.map(_safe, bs))

    bad = [r for r in rows if "error" in r]
    rows = [r for r in rows if "error" not in r]
    if args.json:
        os.makedirs(os.path.dirname(args.json) or ".", exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"rows": rows, "errors": bad}, f, ensure_ascii=False, indent=1)

    print(f"n={len(rows)}  errors={len(bad)}")
    if bad:
        for r in bad[:5]:
            print("  ERR", r["batch"], r["error"])

    def stat(key):
        v = np.array([r[key] for r in rows], float)
        v = v[np.isfinite(v)]
        return (np.median(v), np.percentile(v, 10), np.percentile(v, 90)) if len(v) else (np.nan,) * 3

    print("\n指标                        中位      P10       P90")
    for k in ("s_peak_ratio", "s_peak_t_model", "s_peak_t_meas", "s_resid_model",
              "s_resid_meas", "s_resid_ratio", "gate_model_med", "gate_meas_med",
              "gate_model_duty", "gate_meas_duty", "s_r2", "s_r2_hi"):
        a, b_, c = stat(k)
        print(f"  {k:24s} {a:9.4g} {b_:9.4g} {c:9.4g}")

    for name, _, _ in PHASES:
        a, b_, c = stat(f"s_err_{name}")
        print(f"  s_err_{name:16s} {a:+9.4f} {b_:+9.4f} {c:+9.4f}")

    n_bad = sum(1 for r in rows if np.isfinite(r["s_r2"]) and r["s_r2"] < 0)
    print(f"\nS R2<0: {n_bad}/{len(rows)}")


if __name__ == "__main__":
    main()
