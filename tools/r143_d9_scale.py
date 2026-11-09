# -*- coding: utf-8 -*-
"""R143 · D-9 第一步：b92 pH 故障算子的量纲取证 + 单点验证。

目的：D-9 台账写「b92 pH 故障 mag 100–1000 → yield −1.0（必崩），幅值需重标」，
      但从未检查过 mag 的**量纲**与**故障时间窗**是否和数据一致。
      本节只做两件事：
        A. 从数据反解出「维持观测 pH 凹陷所需的 d[H+]/dt」，换算成算子里的 mag；
        B. 用这个 mag 单点跑一次，看 pH 轨迹是否落在观测上。

不修改引擎。
"""
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))

import numpy as np
import pandas as pd

from simulate import simulate_open_loop, load_batch, yield_metrics
import golden_params as gp

OUT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "runs", "p3", "r143_d9_scale.json"))


def ph_to_h(ph):
    return 10.0 ** (-np.asarray(ph, dtype=float))


def detect_window(d):
    """从数据里自动检出 pH 事件窗（偏离批内中位 pH 超过 0.25 的连续段）。"""
    t = d["time_h"].to_numpy(float)
    ph = pd.to_numeric(d["pH"], errors="coerce").to_numpy(float)
    ok = np.isfinite(ph)
    med = float(np.median(ph[ok]))
    dev = np.where(ok, ph - med, 0.0)
    mask = dev < -0.25
    if not mask.any():
        return None
    idx = np.where(mask)[0]
    # 只取最长连续段
    segs, s = [], idx[0]
    for a, b in zip(idx[:-1], idx[1:]):
        if b - a > 5:
            segs.append((s, a))
            s = b
    segs.append((s, idx[-1]))
    a, b = max(segs, key=lambda ab: ab[1] - ab[0])
    return {
        "t_start": float(t[a]), "t_end": float(t[b]),
        "t_min": float(t[np.nanargmin(ph)]), "ph_min": float(np.nanmin(ph)),
        "ph_median": med, "depth": float(med - np.nanmin(ph)),
    }


def main():
    b = 92
    d = load_batch(b)
    win = detect_window(d)

    # ---- A. 量纲取证 ----
    t = d["time_h"].to_numpy(float)
    ph = pd.to_numeric(d["pH"], errors="coerce").to_numpy(float)
    V = pd.to_numeric(d["V"], errors="coerce").to_numpy(float)

    # 凹陷段内 [H+] 的净上升速率（数据反解）
    m = (t >= win["t_start"]) & (t <= win["t_end"]) & np.isfinite(ph)
    H = ph_to_h(ph[m])
    tt = t[m]
    VV = V[m]
    dh_dt = np.polyfit(tt, H, 1)[0]          # mol/L/h
    V_med = float(np.median(VV))

    # 算子：ph_acid = mag / V(y[4] 单位 mL) 直接加在 dy[H+]/dt 上
    # ⇒ mag = dh_dt * V  （数值等价于 mmol H+/h，当 V 以 L 计时）
    mag_equiv = dh_dt * V_med

    # 旧扫描范围对照
    OLD = [100.0, 200.0, 500.0, 1000.0]

    rec = {
        "batch": b,
        "window": win,
        "unit_forensics": {
            "dh_dt_mol_per_L_per_h": dh_dt,
            "V_median_mL": V_med,
            "mag_equiv": mag_equiv,
            "mag_equiv_formula": "mag = d[H+]/dt * V  (数值 ≈ mmol H+/h，V 以 L 计)",
            "old_scan_range": OLD,
            "ratio_old_over_equiv": [o / mag_equiv for o in OLD] if mag_equiv else None,
        },
    }

    # ---- B. 单点验证：观测窗 + mag_equiv ----
    base, _ = simulate_open_loop(b, gp.params_for(b))
    rec["baseline"] = _score(base, d, win)

    p = dict(gp.params_for(b))
    p.update({"fault_type": 2, "fault_start": win["t_start"],
              "fault_end": win["t_end"], "fault_magnitude": mag_equiv})
    sim, _ = simulate_open_loop(b, p)
    rec["single_point"] = _score(sim, d, win)
    rec["single_point"]["fault"] = {"start": win["t_start"], "end": win["t_end"],
                                    "magnitude": mag_equiv}

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(rec, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=float)

    print("=" * 78)
    print("b92 pH 事件窗（数据自动检出）")
    print("=" * 78)
    print(f"  起点 t={win['t_start']:.1f}h  终点 t={win['t_end']:.1f}h  "
          f"最低点 t={win['t_min']:.1f}h pH={win['ph_min']:.3f}  "
          f"批内中位 {win['ph_median']:.3f}  凹陷深度 {win['depth']:.3f}")
    print()
    print("=" * 78)
    print("量纲取证")
    print("=" * 78)
    print(f"  数据反解 d[H+]/dt = {dh_dt:.4e} mol/L/h   V(中位) = {V_med:.0f} mL")
    print(f"  ⇒ 等价 mag = {mag_equiv:.4e}")
    print(f"  旧扫描 mag = {OLD} ⇒ 放大 " +
          ", ".join(f"{o / mag_equiv:.0f}×" for o in OLD))
    print()
    print("=" * 78)
    print("单点验证（观测窗 + 等价 mag）")
    print("=" * 78)
    hdr = f"{'arm':>10} {'yield_obs':>9} {'yield_sim':>9} {'err%':>7} {'rmse_pH':>8} {'rmse_S':>8} {'rmse_P':>8}"
    print(hdr)
    for k in ("baseline", "single_point"):
        s = rec[k]
        print(f"{k:>10} {s['yield_obs']:>9.3f} {s['yield_sim']:>9.3f} "
              f"{s['yield_err']*100:>7.2f} {s['rmse_pH']:>8.3f} {s['rmse_S']:>8.2f} {s['rmse_P']:>8.2f}")
    print(f"\n落盘 {OUT}")


def _score(sim, d, win):
    """pH / S / P 通道 RMSE（对齐化验滞后 4h，与 d4 探针口径一致）+ 产量误差。"""
    t_sim = sim["time_h"].to_numpy(float)
    t_lab = pd.to_numeric(d["time_h"], errors="coerce").to_numpy(float)
    t_al = t_lab - 4.0
    mask = (t_lab > 20) & (t_lab < 260)
    out = {}
    for ch in ("pH", "S", "P"):
        lab = pd.to_numeric(d[ch], errors="coerce").to_numpy(float)
        m = mask & np.isfinite(lab)
        if m.sum() < 2:
            out["rmse_" + ch] = float("nan")
            continue
        sv = np.interp(t_al[m], t_sim, sim[ch].to_numpy(float))
        out["rmse_" + ch] = float(np.sqrt(np.mean((sv - lab[m]) ** 2)))
    # 凹陷窗内 pH 表现（更贴近故障特征）
    mm = (t_lab >= win["t_start"]) & (t_lab <= win["t_end"]) & np.isfinite(
        pd.to_numeric(d["pH"], errors="coerce").to_numpy(float))
    lab_ph = pd.to_numeric(d["pH"], errors="coerce").to_numpy(float)
    sv = np.interp(t_al[mm], t_sim, sim["pH"].to_numpy(float))
    out["rmse_pH_in_window"] = float(np.sqrt(np.mean((sv - lab_ph[mm]) ** 2)))
    out["ph_min_sim"] = float(np.nanmin(np.interp(t_al[mask], t_sim, sim["pH"].to_numpy(float))))
    out["ph_min_lab"] = float(np.nanmin(lab_ph[mask]))
    ym = yield_metrics(sim, d)
    out["yield_obs"] = float(ym["total_v3_g"])
    out["yield_sim"] = float(ym["total_sim_g"])
    out["yield_err"] = float(ym["rel_err_total"])
    return out


if __name__ == "__main__":
    main()
