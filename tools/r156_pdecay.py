# -*- coding: utf-8 -*-
"""R156 第三问：`ph_fix=1` 之后产量仍在 u 偏离时塌掉——塌的就不是 pH 数值病了。

观察
----
b22 在 `ph_fix=1, u=1.05`：**钳位 0**、pH_max 只有 7.070，但产量 **−99.97%**、P relRMSE 1.20。
R155 在 `ph_fix=0` 下同一格是「pH 崩到 3.000 + 钳位」。两者产量都塌，但机制不同。

要判什么
--------
1. P 是「峰正常、末掉光」还是「峰就没起来」——前者指向水解（`mu_h` 的 pH 项），后者指向产素/底物
2. `mu_h(pH)` 在 6.7 vs 7.07 的比值；以及 `mu_h·P` 与 `r_p` 的量级对比
3. 塌点时刻与 pH 越 7 的时刻是否重合

用法
----
    python tools/r156_pdecay.py --batch 22 --u 1.05 --ph-fix 1
    python tools/r156_pdecay.py --batch 51 --u 1.10 --ph-fix 1
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
ENG = os.path.join(ROOT, "candidate", "indpensim", "v0.1")
sys.path.insert(0, ENG)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=22)
    ap.add_argument("--u", type=float, default=1.0)
    ap.add_argument("--ph-fix", type=int, default=1, choices=[0, 1])
    args = ap.parse_args()

    import simulate as s
    from golden_params import COMBINED, build_params

    bp = dict(build_params(COMBINED[args.batch]))
    bp["ph_fix"] = int(args.ph_fix)
    if abs(args.u - 1.0) > 1e-12:
        bp["fs_ctl"] = {"kp": 0.0, "ki": 0.0, "u_lo": args.u, "u_hi": args.u}
    sim, v3 = s.simulate_open_loop(int(args.batch), bp)

    t = sim["time_h"].to_numpy(float)
    P = sim["P"].to_numpy(float)
    S = sim["S"].to_numpy(float)
    ph = sim["pH"].to_numpy(float)
    # 水解速率 mu_h：直接从 model 的 pH 分支口径反算（只用于量级对比，不改引擎）
    par = None
    try:
        from golden_params import make_params
        par = make_params(**{k: v for k, v in bp.items()
                             if k in ("mup", "mux", "muh", "abc", "K_e")})
    except Exception:  # noqa: BLE001
        par = None

    ym = s.yield_metrics(sim, v3)
    au = sim.attrs.get("guard_audit", {})
    print(f"=== b{args.batch} u={args.u:.2f} ph_fix={args.ph_fix} ===")
    print(f"  yield_err={ym['rel_err_total']*100:+.2f}%  钳位={au.get('tally',{}).get('pH_H',0)}")
    print(f"  P: 峰 {np.nanmax(P):.3f} @ {t[int(np.nanargmax(P))]:.1f} h；末 {P[-1]:.3f}；末/峰 {P[-1]/np.nanmax(P):.3f}")
    print(f"  S: 峰 {np.nanmax(S):.1f} 末 {S[-1]:.1f}")
    print(f"  pH: max {np.nanmax(ph):.3f} @ {t[int(np.nanargmax(ph))]:.1f} h；末 {ph[-1]:.3f}")

    vm = v3.copy()
    print(f"\n  {'t(h)':>7} {'P_sim':>8} {'P_meas':>8} {'S_sim':>9} {'S_meas':>9} {'pH_sim':>7} {'pH_meas':>8}")
    for tt in (24, 48, 72, 96, 120, 144, 168, 192, 216, 240):
        i = int(np.argmin(np.abs(t - tt)))
        j = int(np.argmin(np.abs(vm["time_h"].to_numpy(float) - tt)))
        print(f"  {t[i]:7.1f} {P[i]:8.3f} {vm['P'].to_numpy(float)[j]:8.3f} "
              f"{S[i]:9.1f} {vm['S'].to_numpy(float)[j]:9.1f} {ph[i]:7.3f} "
              f"{vm['pH'].to_numpy(float)[j]:8.3f}")

    # 水解 vs 产素：用 P 的逐点差分反推净速率
    dP = np.gradient(P, t)
    ib = int(np.nanargmax(P))
    print(f"\n  P 峰后前 24 h 的 dP/dt 中位 = {np.nanmedian(dP[ib:min(ib+120, len(dP))]):.4e} g/L/h")
    print(f"  P 峰前 24 h 的 dP/dt 中位     = {np.nanmedian(dP[max(ib-120, 0):ib]):.4e} g/L/h")
    if par is not None:
        print(f"  par 参考：mu_p(par[0])={par[0]:.4f}  mu_v(par[5])={par[5]:.3e}")


if __name__ == "__main__":
    main()
