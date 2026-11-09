# -*- coding: utf-8 -*-
"""FINAL validation v2: 证据化崩溃分级 (benign/catastrophic) + 全批次复验."""
import sys, os, json
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics, classify_crash

COMBINED = {
    8:  {"mux": 0.47, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.029,
          "biomass_death_rate": 0.001, "death_start": 100, "q_co2": 0.12, "Y_NX": 10, "Y_NP": 80, "alpha_kla": 90, "vis_scale": 0.9},
    11: {"mux": 0.41, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.020, "q_co2": 0.11, "Y_NX": 10, "Y_NP": 80, "alpha_kla": 110, "vis_scale": 0.9},
    16: {"mux": 0.41, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.025,
          "biomass_death_rate": 0.005, "death_start": 0, "q_co2": 0.14, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 75, "vis_scale": 0.9},
    22: {"mux": 0.35, "mup": 0.065, "dist_tcin_asym": 20, "m_s": 0.029,
          "m_s_schedule": [(110, 0.010)], "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    23: {"mux": 0.35, "mup": 0.070, "dist_tcin_asym": 10, "m_s": 0.029,
          "biomass_death_rate": 0.0005, "death_start": 200, "q_co2": 0.1, "Y_NX": 15, "Y_NP": 60, "alpha_kla": 110, "vis_scale": 0.9},
    27: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 15, "m_s": 0.029,
          "m_s_schedule": [(140, 0.018)], "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85, "vis_scale": 0.9},
    36: {"mux": 0.47, "mup": 0.045, "dist_tcin_asym": 10, "m_s": 0.010, "q_co2": 0.1, "Y_NX": 20, "Y_NP": 40, "alpha_kla": 130, "vis_scale": 0.8},
    55: {"mux": 0.47, "mup": 0.055, "dist_tcin_asym": 20, "m_s": 0.025,
          "biomass_death_rate": 0.001, "death_start": 200, "q_co2": 0.11, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    60: {"mux": 0.47, "mup": 0.035, "dist_tcin_asym": 15, "m_s": 0.010, "q_co2": 0.1, "Y_NX": 20, "Y_NP": 40, "alpha_kla": 85},
    80: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 18, "m_s": 0.029,
          "biomass_death_rate": 0.005, "death_start": 0, "q_co2": 0.13, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85, "vis_scale": 0.9},
    91: {"mux": 0.39, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.029,
          "biomass_death_rate": 0.005, "death_start": 200, "q_co2": 0.12, "Y_NX": 10, "Y_NP": 60, "alpha_kla": 90},
    92: {"mux": 0.47, "mup": 0.041, "dist_tcin_asym": 18, "m_s": 0.029,
          "m_s_schedule": [(150, 0.015)],
          "biomass_death_rate": 0.005, "death_start": 200, "q_co2": 0.11, "Y_NX": 12, "Y_NP": 60, "alpha_kla": 130, "vis_scale": 0.9},
}

GOLDEN_NORMAL = [8, 11, 16, 22, 23, 27, 36, 55, 60, 80]
FAULT = [91, 92]

print("=" * 72)
print("FINAL Golden Set Validation v2 (evidence-based crash classification)")
print("=" * 72)
print(f"{'Batch':>6s} {'Type':>6s} {'yield_err':>9s} {'CO2d':>6s} {'pH_end':>6s} {'crash':>12s}")
print("-" * 72)

all_errs, results = [], []
for b in GOLDEN_NORMAL + FAULT:
    v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
    cp = COMBINED[b]
    params = {"mux": cp["mux"], "mup": cp["mup"], "alpha_kla": cp.get("alpha_kla", 85.0),
              "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0,
              "dist_flag": 1, "dist_tcin_asym": cp["dist_tcin_asym"], "m_s": cp["m_s"]}
    if "m_s_schedule" in cp:
        params["m_s_schedule"] = cp["m_s_schedule"]
    if "biomass_death_rate" in cp:
        params["biomass_death_rate"] = cp["biomass_death_rate"]
        params["death_start"] = cp["death_start"]
    if "q_co2" in cp:
        params["q_co2"] = cp["q_co2"]
    if "Y_NX" in cp:
        params["Y_NX"] = cp["Y_NX"]
    if "Y_NP" in cp:
        params["Y_NP"] = cp["Y_NP"]
    if "vis_scale" in cp:
        params["vis_scale"] = cp["vis_scale"]
    sim, _ = simulate_open_loop(b, params)
    ym = yield_metrics(sim, v3)
    err = ym["rel_err_total"]
    level, reasons = classify_crash(sim, yield_err=err)
    ph_end = float(sim["pH"].iloc[-1])
    print(f"{b:>6d} {'normal' if b in GOLDEN_NORMAL else 'fault':>6s} {err:>+9.1%} "
          f"{sim['CO2d'].max():>6.2f} {ph_end:>6.2f} {level:>12s}")
    all_errs.append(err)
    results.append({
        "batch": b, "type": "normal" if b in GOLDEN_NORMAL else "fault",
        "yield_sim": ym["total_sim_g"], "yield_v3": ym["total_v3_g"],
        "yield_err": err, "co2d_max": float(sim["CO2d"].max()),
        "ph_end": ph_end, "crash_level": level, "crash_reasons": reasons,
        "params": {k: (v if not isinstance(v, float) or np.isfinite(v) else str(v))
                    for k, v in cp.items()},
    })

with open("runs/final_validation_v2.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False, default=str)

rmse = np.sqrt(np.mean(np.square(all_errs)))
n_cat = sum(1 for r in results if r["crash_level"] == "catastrophic")
n_ben = sum(1 for r in results if r["crash_level"] == "benign")
n_norm = sum(1 for r in results if r["crash_level"] == "normal")
n_within5 = sum(1 for r in results if r["crash_level"] != "catastrophic" and abs(r["yield_err"]) <= 0.05)

print("-" * 72)
print(f"Crash: normal={n_norm}/12 benign={n_ben}/12 catastrophic={n_cat}/12")
print(f"No catastrophic + |yield err| <= 5%: {n_within5}/{12}")
print(f"RMSE of yields: {rmse:.2%}")
print(f"Saved: runs/final_validation_v2.json")
print()
print("History:")
print(f"  Nominal params:              RMSE=70.95%, catastrophic≈9/12, within5%=1/12")
print(f"  Improved (constant m_s):     RMSE= 7.28%, catastrophic 1/12, within5%=6/12")
print(f"  Time-varying m_s:            RMSE= 4.48%, catastrophic 1/12, within5%=8/12")
print(f"  v2 evidence-based crash:     RMSE={rmse:.2%}, catastrophic {n_cat}/12, within5%={n_within5}/12")
