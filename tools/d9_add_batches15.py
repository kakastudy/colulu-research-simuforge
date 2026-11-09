# -*- coding: utf-8 -*-
"""R129bq: Add batches 52, 53, 56 to COMBINED dict and GOLDEN_NORMAL."""
import os

path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "tools", "diag_final_validation_v3.py")

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# Add batches after batch 55
old = '    55: {"mux": 0.47, "mup": 0.055, "dist_tcin_asym": 20, "m_s": 0.025,\n          "biomass_death_rate": 0.001, "death_start": 200, "q_co2": 0.11, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85, "PAA_c": 530000.0, "m_paa": 1.0, "Y_O2_X": 650, "Y_O2_P": 160, "m_O2_X": 17.5},'
new = '    55: {"mux": 0.47, "mup": 0.055, "dist_tcin_asym": 20, "m_s": 0.025,\n          "biomass_death_rate": 0.001, "death_start": 200, "q_co2": 0.11, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85, "PAA_c": 530000.0, "m_paa": 1.0, "Y_O2_X": 650, "Y_O2_P": 160, "m_O2_X": 17.5},\n    52: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,\n          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85,\n          "mu_h_scale": 2.0},\n    53: {"mux": 0.60, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,\n          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},\n    56: {"mux": 0.75, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,\n          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},'

if old in content:
    content = content.replace(old, new)
    # Update GOLDEN_NORMAL
    content = content.replace(
        'GOLDEN_NORMAL = [1, 2, 5, 7, 8, 9, 11, 14, 15, 16, 17, 20, 22, 23, 24, 26, 27, 28, 30, 33, 34, 35, 36, 41, 43, 46, 47, 49, 55, 57, 60, 62, 63, 64, 65, 66, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 80, 82, 85, 86, 87, 88, 89, 90, 95, 96]',
        'GOLDEN_NORMAL = [1, 2, 5, 7, 8, 9, 11, 14, 15, 16, 17, 20, 22, 23, 24, 26, 27, 28, 30, 33, 34, 35, 36, 41, 43, 46, 47, 49, 52, 53, 55, 56, 57, 60, 62, 63, 64, 65, 66, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 80, 82, 85, 86, 87, 88, 89, 90, 95, 96]'
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Edit successful")
else:
    print("old_string not found")
