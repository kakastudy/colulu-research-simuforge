# -*- coding: utf-8 -*-
"""R129ak: Investigate why Batch 74 and 72 crash (P_final=0).

These batches produce no penicillin with nominal params.
Need to understand the trajectory to find a fix.
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


NOMINAL = {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
           "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85}


def main():
    print("=" * 80, flush=True)
    print("R129ak: Investigate Batch 74/72 crash", flush=True)
    print("=" * 80, flush=True)

    for b in [74, 72]:
        v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
        cp = dict(NOMINAL)
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
            print("    t={:.0f}h: X={:.1f} S={:.1f} P={:.2f} V={:.0f} pH={:.2f} T={:.1f} DO2={:.1f}".format(
                t, float(sim["X"].iloc[t_idx]), float(sim["S"].iloc[t_idx]),
                float(sim["P"].iloc[t_idx]), float(sim["V"].iloc[t_idx]),
                float(sim["pH"].iloc[t_idx]), float(sim["T"].iloc[t_idx]),
                float(sim["DO2"].iloc[t_idx])), flush=True)

        # Check V3 trajectory
        print("\n  V3 trajectory summary:", flush=True)
        for col in ["X", "S", "P", "pH"]:
            if col in v3.columns:
                v3_vals = v3[col].dropna()
                if len(v3_vals) > 0:
                    print("    {}: min={:.1f} max={:.1f} last={:.1f}".format(
                        col, v3_vals.min(), v3_vals.max(), v3_vals.iloc[-1]), flush=True)

        # Check feeding profile
        print("\n  V3 feeding profile:", flush=True)
        for col in ["Fs", "Fg", "Fc", "Fh", "Fa", "Fw", "Fremoved", "Fpaa", "Foil", "NH3_shots"]:
            if col in v3.columns:
                vals = v3[col].dropna()
                if len(vals) > 0:
                    print("    {}: total={:.0f} max={:.4f} last={:.4f}".format(
                        col, vals.sum(), vals.max(), vals.iloc[-1]), flush=True)

        # Try higher mux
        print("\n  --- mux sweep ---", flush=True)
        for mux in [0.35, 0.40, 0.45, 0.50, 0.55, 0.60]:
            cp2 = dict(cp)
            cp2["mux"] = mux
            params2 = build_params(cp2)
            try:
                sim2, _ = simulate_open_loop(b, params2)
                ym2 = yield_metrics(sim2, v3)
                err = ym2["rel_err_total"]
                p_final = float(sim2["P"].iloc[-1])
                x_final = float(sim2["X"].iloc[-1])
                marker = " ***" if abs(err) < 0.05 else ""
                print("    mux={:.2f}: yield_err={:+.4f} ({:+.1f}%) P_final={:.2f} X_final={:.1f}{}".format(
                    mux, err, err * 100, p_final, x_final, marker), flush=True)
            except Exception as e:
                print("    mux={:.2f}: FAILED - {}".format(mux, str(e)[:50]), flush=True)


if __name__ == "__main__":
    main()
