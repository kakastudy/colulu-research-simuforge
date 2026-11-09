# -*- coding: utf-8 -*-
"""R129ai3: Investigate Batch 27 and 91 yield error - what drives it?

Batch 27: yield_err=+4.8%, P_final=28.8
Batch 91: yield_err=+4.3%, P_final=1.9 (fault batch, low pH_end=3.0)

For Batch 27, the model overproduces total yield. Need to understand:
- harvested vs end-in-vessel split
- What parameters affect this?

For Batch 91, it's a fault batch with pH_end=3.0 (very acidic).
The model handles the fault condition but with 4.3% yield error.
"""
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))

from simulate import simulate_open_loop, yield_metrics


def build_params(cp):
    """Build params dict matching diag_final_validation_v3.py exactly."""
    params = {"mux": cp["mux"], "mup": cp["mup"],
              "alpha_kla": cp.get("alpha_kla", 85.0),
              "PAA_c": cp.get("PAA_c", 530000.0), "N_conc_paa": 150000.0, "c_oil": 1000.0,
              "dist_flag": 1, "dist_tcin_asym": cp["dist_tcin_asym"], "m_s": cp["m_s"]}
    for key in ["m_paa", "m_s_schedule", "biomass_death_rate", "death_start",
                "q_co2", "Y_NX", "Y_NP", "vis_scale", "Y_O2_X", "Y_O2_P",
                "m_O2_X", "mu_h_scale"]:
        if key in cp:
            if key == "biomass_death_rate":
                params["biomass_death_rate"] = cp["biomass_death_rate"]
                params["death_start"] = cp["death_start"]
            else:
                params[key] = cp[key]
    return params


COMBINED = {
    27: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 15, "m_s": 0.029,
         "m_s_schedule": [(140, 0.018)], "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40,
         "alpha_kla": 85, "vis_scale": 0.9,
         "PAA_c": 530000.0, "m_paa": 1.0, "Y_O2_X": 650, "Y_O2_P": 160, "m_O2_X": 15},
    91: {"mux": 0.39, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.029,
         "biomass_death_rate": 0.005, "death_start": 200,
         "q_co2": 0.12, "Y_NX": 10, "Y_NP": 60, "alpha_kla": 90},
}


def main():
    print("=" * 80, flush=True)
    print("R129ai3: Batch 27/91 yield error investigation", flush=True)
    print("=" * 80, flush=True)

    for b in [27, 91]:
        v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
        cp = COMBINED[b]
        params = build_params(cp)

        print("\n--- Batch {} ---".format(b), flush=True)

        sim, _ = simulate_open_loop(b, params)
        ym = yield_metrics(sim, v3)

        print("  Yield metrics:", flush=True)
        for k, v in ym.items():
            if isinstance(v, float):
                print("    {}: {:.4f}".format(k, v), flush=True)
            else:
                print("    {}: {}".format(k, v), flush=True)

        # Print trajectory summary
        print("\n  Trajectory summary:", flush=True)
        for t_idx in [0, len(sim)//4, len(sim)//2, 3*len(sim)//4, len(sim)-1]:
            t = sim["time_h"].iloc[t_idx]
            print("    t={:.0f}h: X={:.1f} S={:.1f} P={:.2f} V={:.0f} pH={:.2f} T={:.1f}".format(
                t, float(sim["X"].iloc[t_idx]), float(sim["S"].iloc[t_idx]),
                float(sim["P"].iloc[t_idx]), float(sim["V"].iloc[t_idx]),
                float(sim["pH"].iloc[t_idx]), float(sim["T"].iloc[t_idx])), flush=True)

        # Check V3 trajectory
        print("\n  V3 trajectory summary:", flush=True)
        for col in ["X", "S", "P", "pH"]:
            if col in v3.columns:
                v3_vals = v3[col].dropna()
                if len(v3_vals) > 0:
                    print("    {}: min={:.1f} max={:.1f} last={:.1f}".format(
                        col, v3_vals.min(), v3_vals.max(), v3_vals.iloc[-1]), flush=True)

        # Check Fremoved (harvested penicillin)
        if "Fremoved" in v3.columns:
            fr = v3["Fremoved"].fillna(0)
            print("\n  V3 Fremoved: total={:.0f} max={:.4f}".format(
                fr.sum(), fr.max()), flush=True)
        if "Fremoved" in sim.columns:
            fr = sim["Fremoved"].fillna(0)
            print("  Sim Fremoved: total={:.0f} max={:.4f}".format(
                fr.sum(), fr.max()), flush=True)


if __name__ == "__main__":
    main()
