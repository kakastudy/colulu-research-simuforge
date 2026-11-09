# -*- coding: utf-8 -*-
"""R142 / D-2 Part B2：可加模型方差分解（主效应 vs 残差噪声）。

Part B 的缺陷：把"同一 mux 水平下 mup/m_s 的真实主效应"算进了 mux 的噪声，
系统性低估 SNR（mux 0.32 明显可疑）。

正确口径（multi-way ANOVA）：
    L(b, i, j, k) = μ + a_i(mux) + b_j(mup) + c_k(m_s) + ε
用最小二乘（哑变量、和为零约束）拟合，则
    σ_ε     = 残差 SD  ← 交互项 + 数值/错配噪声，这才是"损失差的噪声单位"
    span(a) = max_i a_i − min_i a_i
    SNR     = span(a) / σ_ε

同时给出 **profile span**（取其余参数最优后的跨度）作为上界参考，
并给出以 σ_ε 为温度的等效后验（var_w、ESS）——这是修好温度后的应然数字。

输出：runs/p3/r142_d2_snr2.json
"""
import json
import os

import numpy as np

_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
LOG = os.path.join(_ROOT, "runs", "hier_est", "train_theta_v2.jsonl")
OUT = os.path.join(_ROOT, "runs", "p3", "r142_d2_snr2.json")
PARAMS = ("mux", "mup", "m_s")
LOSS_CAP = 9e5


def additive_fit(sw, params=PARAMS):
    """拟合可加模型，返回各因子水平效应、残差 SD。"""
    levels = {p: sorted({c[p] for c in sw}) for p in params}
    idx = {p: {v: i for i, v in enumerate(levels[p])} for p in params}
    rows, y = [], []
    for c in sw:
        rows.append([1.0] + [1.0 if c[p] == v else 0.0 for p in params for v in levels[p][1:]])
        y.append(c["loss"])
    X = np.array(rows); y = np.array(y)
    if X.shape[1] >= len(y):
        return None
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    # 自由度：n - (1 + Σ(levels-1))
    dof = len(y) - X.shape[1]
    sd_e = float(np.sqrt(np.sum(resid ** 2) / max(dof, 1)))
    eff = {}
    pos = 1
    for p in params:
        L = levels[p]
        raw = [0.0] + [beta[pos + i] for i in range(len(L) - 1)]
        pos += len(L) - 1
        m = float(np.mean(raw))
        eff[p] = {v: float(raw[i] - m) for i, v in enumerate(L)}
    return {"levels": levels, "effects": eff, "sd_resid": sd_e,
            "dof": dof, "n": len(y)}


def profile_span(sw, p):
    d = {}
    for c in sw:
        d[c[p]] = min(d.get(c[p], np.inf), c["loss"])
    if len(d) < 2:
        return None
    return float(max(d.values()) - min(d.values()))


def posterior_with_sw(sw, p, T):
    L = np.array([c["loss"] for c in sw])
    v = np.array([c[p] for c in sw])
    w = np.exp(-(L - L.min()) / T); w /= w.sum()
    m = float(w @ v)
    return float(1.0 / np.sum(w ** 2)), float(w @ (v - m) ** 2), m


def main():
    recs = [json.loads(l) for l in open(LOG, encoding="utf-8")]
    rows = []
    for r in recs:
        sw = [c for c in (r.get("sweep") or []) if c["loss"] < LOSS_CAP]
        if len(sw) < 20:
            continue
        fit = additive_fit(sw)
        if not fit or not np.isfinite(fit["sd_resid"]) or fit["sd_resid"] <= 0:
            continue
        for p in PARAMS:
            a = fit["effects"][p]
            span = max(a.values()) - min(a.values())
            rec = {"batch": r["batch"], "param": p,
                   "span_main": round(span, 6),
                   "sd_resid": round(fit["sd_resid"], 6),
                   "snr": round(span / fit["sd_resid"], 3),
                   "profile_span": round(profile_span(sw, p) or 0.0, 6),
                   "n": fit["n"], "dof": fit["dof"]}
            # 以残差 SD 为温度重算后验（应然口径）
            ess, vw, th = posterior_with_sw(sw, p, fit["sd_resid"])
            rec.update({"ESS_at_sdresid": round(ess, 2), "var_w_at_sdresid": round(vw, 8),
                        "theta_post": round(th, 5)})
            rows.append(rec)

    by = {}
    for p in PARAMS:
        rp = [r for r in rows if r["param"] == p]
        g = lambda k: np.array([r[k] for r in rp])
        th = g("theta_post")
        vw = g("var_w_at_sdresid")
        by[p] = {
            "n": len(rp),
            "snr_med": round(float(np.median(g("snr"))), 3),
            "snr_p10": round(float(np.percentile(g("snr"), 10)), 3),
            "snr_p90": round(float(np.percentile(g("snr"), 90)), 3),
            "frac_snr_gt1": round(float(np.mean(g("snr") > 1)), 3),
            "frac_snr_gt3": round(float(np.mean(g("snr") > 3)), 3),
            "span_main_med": round(float(np.median(g("span_main"))), 6),
            "sd_resid_med": round(float(np.median(g("sd_resid"))), 6),
            "profile_span_med": round(float(np.median(g("profile_span"))), 6),
            "ESS_med": round(float(np.median(g("ESS_at_sdresid"))), 2),
            "var_b_post": round(float(np.var(th, ddof=1)), 8),
            "sigma_b_post": round(float(np.std(th, ddof=1)), 5),
            "var_w_med": round(float(np.mean(vw)), 8),
            "DL_gap": round(float(np.var(th, ddof=1) - np.mean(vw)), 8),
            "sigma_pop_DL": round(float(np.sqrt(max(np.var(th, ddof=1) - np.mean(vw), 0.0))), 5),
        }
    out = {"n_batches": len(recs), "by_param": by, "rows": rows}
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"批数 {len(recs)}（可分解 {len({r['batch'] for r in rows})}）")
    print(f"{'param':>5} {'SNR中位':>8} {'p10':>7} {'p90':>7} {'>1':>6} {'>3':>6} "
          f"{'主效应跨度':>10} {'残差SD':>9} {'ESS':>7} {'var_b':>10} {'var_w':>10} {'σ_pop':>8}")
    for p in PARAMS:
        s = by[p]
        print(f"{p:>5} {s['snr_med']:>8.2f} {s['snr_p10']:>7.2f} {s['snr_p90']:>7.2f} "
              f"{s['frac_snr_gt1']:>6.2f} {s['frac_snr_gt3']:>6.2f} "
              f"{s['span_main_med']:>10.4f} {s['sd_resid_med']:>9.4f} {s['ESS_med']:>7.1f} "
              f"{s['var_b_post']:>10.2e} {s['var_w_med']:>10.2e} {s['sigma_pop_DL']:>8.4f}")
    print("\n参考：MATLAB σ_gen  mux 0.025 / mup 0.0025")
    print(f"落盘 {OUT}")


if __name__ == "__main__":
    main()
