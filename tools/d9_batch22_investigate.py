# -*- coding: utf-8 -*-
"""R129ah: Investigate Batch 22 structural yield error (+7.0%).

Batch 22 has yield_err=+7.0% — the model overproduces penicillin.
This is structural (not fixable by parameter tuning alone).

Investigate:
1. V3 reference yield trajectory vs simulation
2. Feeding profile comparison
3. Biomass trajectory comparison
4. Penicillin concentration trajectory comparison
"""
import os
import sys
import json
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))

from simulate import simulate_open_loop, yield_metrics


COMBINED = {
    22: {"mux": 0.35, "mup": 0.065, "dist_tcin_asym": 20, "m_s": 0.029,
          "m_s_schedule": [(110, 0.010)], "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
}


def build_params(cp):
    params = {"mux": cp["mux"], "mup": cp["mup"], "alpha_kla": cp.get("alpha_kla", 85.0),
              "PAA_c": cp.get("PAA_c", 530000.0), "N_conc_paa": 150000.0, "c_oil": 1000.0,
              "dist_flag": 1, "dist_tcin_asym": cp["dist_tcin_asym"], "m_s": cp["m_s"]}
    if "m_s_schedule" in cp:
        params["m_s_schedule"] = cp["m_s_schedule"]
    if "q_co2" in cp:
        params["q_co2"] = cp["q_co2"]
    if "Y_NX" in cp:
        params["Y_NX"] = cp["Y_NX"]
    if "Y_NP" in cp:
        params["Y_NP"] = cp["Y_NP"]
    return params


def main():
    print("=" * 80, flush=True)
    print("R129ah: Batch 22 structural yield error investigation", flush=True)
    print("=" * 80, flush=True)

    b = 22
    v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
    cp = COMBINED[b]
    params = build_params(cp)
    sim, _ = simulate_open_loop(b, params)
    ym = yield_metrics(sim, v3)

    print("\n--- Yield metrics ---", flush=True)
    print("  total_sim: {:.1f} g".format(ym["total_sim_g"]), flush=True)
    print("  total_v3:  {:.1f} g".format(ym["total_v3_g"]), flush=True)
    print("  rel_err:   {:+.4f} ({:+.1f}%)".format(ym["rel_err_total"], ym["rel_err_total"] * 100), flush=True)

    print("\n--- Feeding profile comparison ---", flush=True)
    for col in ["Fs", "Fo", "Fpaa", "Fh", "Fv"]:
        if col in v3.columns and col in sim.columns:
            v3_sum = v3[col].sum()
            sim_sum = sim[col].sum()
            if v3_sum > 0:
                print("  {}: V3 sum={:.1f} sim sum={:.1f} ratio={:.3f}".format(
                    col, v3_sum, sim_sum, sim_sum / v3_sum), flush=True)
            else:
                print("  {}: V3 sum={:.1f} sim sum={:.1f}".format(
                    col, v3_sum, sim_sum), flush=True)

    print("\n--- Biomass trajectory (total_X) ---", flush=True)
    if "X_offline" in v3:
        v3_x = v3["X_offline"].dropna()
        print("  V3 X_offline points: {}".format(len(v3_x)), flush=True)
        sim_x = sim["X"].iloc[:len(v3_x)]
        print("  V3 X: min={:.1f} max={:.1f} final={:.1f}".format(
            v3_x.min(), v3_x.max(), v3_x.iloc[-1]), flush=True)
        print("  Sim X: min={:.1f} max={:.1f} final={:.1f}".format(
            sim_x.min(), sim_x.max(), sim_x.iloc[-1]), flush=True)

    print("\n--- Penicillin trajectory (P) ---", flush=True)
    if "P" in v3:
        v3_p = v3["P"].dropna()
        sim_p = sim["P"].iloc[:len(v3_p)]
        print("  V3 P: min={:.1f} max={:.1f} final={:.1f}".format(
            v3_p.min(), v3_p.max(), v3_p.iloc[-1]), flush=True)
        print("  Sim P: min={:.1f} max={:.1f} final={:.1f}".format(
            sim_p.min(), sim_p.max(), sim_p.iloc[-1]), flush=True)
    if "P_offline" in v3:
        v3_poff = v3["P_offline"].dropna()
        print("  V3 P_offline: min={:.1f} max={:.1f} final={:.1f} count={}".format(
            v3_poff.min(), v3_poff.max(), v3_poff.iloc[-1], len(v3_poff)), flush=True)

    print("\n--- Substrate trajectory (S) ---", flush=True)
    if "S" in v3:
        v3_s = v3["S"].dropna()
        sim_s = sim["S"].iloc[:len(v3_s)]
        print("  V3 S: min={:.4f} max={:.4f} final={:.4f}".format(
            v3_s.min(), v3_s.max(), v3_s.iloc[-1]), flush=True)
        print("  Sim S: min={:.4f} max={:.4f} final={:.4f}".format(
            sim_s.min(), sim_s.max(), sim_s.iloc[-1]), flush=True)

    print("\n--- Volume trajectory ---", flush=True)
    if "V" in v3:
        v3_v = v3["V"].dropna()
        sim_v = sim["V"].iloc[:len(v3_v)]
        print("  V3 V: min={:.1f} max={:.1f} final={:.1f}".format(
            v3_v.min(), v3_v.max(), v3_v.iloc[-1]), flush=True)
        print("  Sim V: min={:.1f} max={:.1f} final={:.1f}".format(
            sim_v.min(), sim_v.max(), sim_v.iloc[-1]), flush=True)

    print("\n--- mup sensitivity ---", flush=True)
    for mup in [0.040, 0.045, 0.050, 0.055, 0.060, 0.065, 0.070]:
        params2 = dict(params)
        params2["mup"] = mup
        sim2, _ = simulate_open_loop(b, params2)
        ym2 = yield_metrics(sim2, v3)
        print("  mup={}: yield_err={:+.4f} ({:+.1f}%)".format(
            mup, ym2["rel_err_total"], ym2["rel_err_total"] * 100), flush=True)

    print("\n--- mux sensitivity ---", flush=True)
    for mux in [0.30, 0.32, 0.35, 0.38, 0.40, 0.42]:
        params2 = dict(params)
        params2["mux"] = mux
        sim2, _ = simulate_open_loop(b, params2)
        ym2 = yield_metrics(sim2, v3)
        print("  mux={}: yield_err={:+.4f} ({:+.1f}%)".format(
            mux, ym2["rel_err_total"], ym2["rel_err_total"] * 100), flush=True)

    print("\n--- m_s sensitivity ---", flush=True)
    for ms in [0.010, 0.015, 0.020, 0.025, 0.029, 0.035]:
        params2 = dict(params)
        params2["m_s"] = ms
        params2["m_s_schedule"] = [(110, ms)]
        sim2, _ = simulate_open_loop(b, params2)
        ym2 = yield_metrics(sim2, v3)
        print("  m_s={}: yield_err={:+.4f} ({:+.1f}%)".format(
            ms, ym2["rel_err_total"], ym2["rel_err_total"] * 100), flush=True)

    # Save results
    results = {
        "yield_metrics": {k: float(v) if isinstance(v, (int, float)) else v for k, v in ym.items()},
        "mup_sensitivity": [],
        "mux_sensitivity": [],
        "ms_sensitivity": [],
    }
    for mup in [0.040, 0.045, 0.050, 0.055, 0.060, 0.065, 0.070]:
        params2 = dict(params)
        params2["mup"] = mup
        sim2, _ = simulate_open_loop(b, params2)
        ym2 = yield_metrics(sim2, v3)
        results["mup_sensitivity"].append({"mup": mup, "yield_err": ym2["rel_err_total"]})
    for mux in [0.30, 0.32, 0.35, 0.38, 0.40, 0.42]:
        params2 = dict(params)
        params2["mux"] = mux
        sim2, _ = simulate_open_loop(b, params2)
        ym2 = yield_metrics(sim2, v3)
        results["mux_sensitivity"].append({"mux": mux, "yield_err": ym2["rel_err_total"]})
    for ms in [0.010, 0.015, 0.020, 0.025, 0.029, 0.035]:
        params2 = dict(params)
        params2["m_s"] = ms
        params2["m_s_schedule"] = [(110, ms)]
        sim2, _ = simulate_open_loop(b, params2)
        ym2 = yield_metrics(sim2, v3)
        results["ms_sensitivity"].append({"m_s": ms, "yield_err": ym2["rel_err_total"]})

    dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "runs", "p3", "d9_batch22_structural.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("\nSaved: %s" % dst, flush=True)


if __name__ == "__main__":
    main()
