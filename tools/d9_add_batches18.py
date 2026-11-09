# -*- coding: utf-8 -*-
"""R129bw: Add batches 98, 100 to COMBINED dict and GOLDEN_NORMAL."""
import os

path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "tools", "diag_final_validation_v3.py")

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# Add batches after batch 96
old = '    96: {"mux": 0.50, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,\n          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},'
new = '    96: {"mux": 0.50, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,\n          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},\n    98: {"mux": 0.45, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,\n          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},\n    100: {"mux": 1.00, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,\n          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},'

if old in content:
    content = content.replace(old, new)
    # Update GOLDEN_NORMAL
    content = content.replace(
        'GOLDEN_NORMAL = [1, 2, 5, 7, 8, 9, 11, 14, 15, 16, 17, 20, 22, 23, 24, 26, 27, 28, 30, 33, 34, 35, 36, 41, 43, 46, 47, 49, 52, 53, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 82, 83, 84, 85, 86, 87, 88, 89, 90, 93, 95, 96]',
        'GOLDEN_NORMAL = [1, 2, 5, 7, 8, 9, 11, 14, 15, 16, 17, 20, 22, 23, 24, 26, 27, 28, 30, 33, 34, 35, 36, 41, 43, 46, 47, 49, 52, 53, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 82, 83, 84, 85, 86, 87, 88, 89, 90, 93, 95, 96, 98, 100]'
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Edit successful")
else:
    print("old_string not found")
