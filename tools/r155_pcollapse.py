# -*- coding: utf-8 -*-
"""R155：16 批（12 catastrophic + 4 degraded）重算 P 末/峰，判别"模型病"还是"过程真实"。"""
import json, os, sys
from concurrent.futures import ProcessPoolExecutor
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))

BS = [3, 9, 18, 30, 33, 37, 43, 45, 50, 51, 91, 95, 40, 49, 54, 92]


def one(b):
    import simulate as s
    from golden_params import COMBINED, build_params
    p = build_params(COMBINED[b])
    sim, v3 = s.simulate_open_loop(int(b), p)
    ym = s.yield_metrics(sim, v3)
    hl = s.classify_health(sim, yield_err=ym["rel_err_total"])
    pm = np.asarray(sim["P"], float)
    vp = pd_np = np.asarray(v3["P"], float)
    vp = vp[np.isfinite(vp)]
    return {"batch": int(b), "health": hl["level"], "flags": hl["flags"],
            "yield_err": float(ym["rel_err_total"]),
            "drop_sim": float(pm[-1] / max(pm.max(), 1e-12)),
            "drop_meas": float(vp[-1] / max(vp.max(), 1e-12)),
            "peak_sim": float(pm.max()), "end_sim": float(pm[-1]),
            "peak_meas": float(vp.max()), "end_meas": float(vp[-1]),
            "ph_max_pre": hl["ph_max_pre"], "n_ph_clamp": hl["n_ph_clamp"]}


if __name__ == "__main__":
    with ProcessPoolExecutor(max_workers=6) as ex:
        rows = list(ex.map(one, BS))
    rows.sort(key=lambda r: r["batch"])
    print(f"{'b':>4s}{'health':>13s}{'yield%':>9s}{'drop_sim':>10s}{'drop_meas':>10s}{'sim/meas':>9s}  verdict")
    n_bad = 0
    for r in rows:
        v = ("模型病" if (r["drop_sim"] < 0.5 <= r["drop_meas"]) else
             "过程真实" if r["drop_meas"] < 0.5 else "两边都高")
        n_bad += (v == "模型病")
        print(f"{r['batch']:>4d}{r['health']:>13s}{r['yield_err']*100:9.2f}"
              f"{r['drop_sim']:10.3f}{r['drop_meas']:10.3f}{r['drop_sim']/max(r['drop_meas'],1e-9):9.3f}  {v}"
              f"   flags={','.join(r['flags'])}")
    print(f"\n模型病 {n_bad}/{len(rows)}")
    json.dump(rows, open(os.path.join(ROOT, "runs", "r155_pcollapse.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("-> runs/r155_pcollapse.json")
