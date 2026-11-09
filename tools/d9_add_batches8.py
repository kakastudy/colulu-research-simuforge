# -*- coding: utf-8 -*-
"""R129bc: Add batches 7, 9 to COMBINED dict and GOLDEN_NORMAL."""
import os

path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "tools", "diag_final_validation_v3.py")

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# Add batches after batch 5
old = '    5: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,\n          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},'
new = '    5: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,\n          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},\n    7: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,\n          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85,\n          "mu_h_scale": 1.2},\n    9: {"mux": 0.40, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,\n          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},'

if old in content:
    content = content.replace(old, new)
    # Update GOLDEN_NORMAL
    content = content.replace(
        'GOLDEN_NORMAL = [1, 2, 5, 8, 11, 16, 22, 23, 27, 36, 55, 57, 60, 62, 63, 64, 65, 66, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 80, 82, 85, 86, 87, 88, 89, 90, 95, 96]',
        'GOLDEN_NORMAL = [1, 2, 5, 7, 8, 9, 11, 16, 22, 23, 27, 36, 55, 57, 60, 62, 63, 64, 65, 66, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 80, 82, 85, 86, 87, 88, 89, 90, 95, 96]'
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Edit successful")
else:
    print("old_string not found")
