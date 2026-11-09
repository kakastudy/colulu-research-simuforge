# -*- coding: utf-8 -*-
"""R149 探针：模型 X 与实测 X_offline 的偏差是否与 pH 中段残差同相。"""
import os, sys, json
from concurrent.futures import ProcessPoolExecutor
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))

TGRID = [20.0, 60.0, 100.0, 140.0, 180.0, 215.0]

def one(b):
    from golden_params import COMBINED, build_params
    from simulate import simulate_open_loop
    sim, v3 = simulate_open_loop(int(b), build_params(COMBINED[int(b)]))
    t = sim["time_h"].to_numpy(float)
    ph = sim["pH"].to_numpy(float)
    X = sim["X"].to_numpy(float)
    tv = v3["time_h"].to_numpy(float)
    out = {"batch": int(b), "pt": []}
    for col, arr in (("pH", v3["pH"].to_numpy(float)), ("X", v3["X_offline"].to_numpy(float))):
        ok = np.isfinite(arr)
        out.setdefault("meas_" + col, np.interp(TGRID, tv[ok], arr[ok]).tolist())
    out["mod_pH"] = np.interp(TGRID, t, ph).tolist()
    out["mod_X"] = np.interp(TGRID, t, X).tolist()
    return out

if __name__ == "__main__":
    bs = [int(x) for x in sys.argv[1].split(",")]
    with ProcessPoolExecutor(max_workers=min(6, len(bs))) as ex:
        rows = list(ex.map(one, bs))
    print("批  t      pH归  pH测   ΔpH     X归     X测    X比值   产酸项ph_prod代理(m_ph*X)")
    for r in rows:
        for i, t in enumerate(TGRID):
            dp = r["mod_pH"][i] - r["meas_pH"][i]
            rx = r["mod_X"][i] / max(r["meas_X"][i], 1e-9)
            print(f"{r['batch']:>3d} {t:5.0f} {r['mod_pH'][i]:6.3f} {r['meas_pH'][i]:6.3f} {dp:+7.3f}"
                  f" {r['mod_X'][i]:7.3f} {r['meas_X'][i]:7.3f} {rx:6.2f}")
        print()
    json.dump(rows, open(os.path.join(ROOT, "runs", "r149_biomass_probe.json"), "w",
                         encoding="utf-8"), ensure_ascii=False, indent=1)
