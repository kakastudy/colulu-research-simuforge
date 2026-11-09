# -*- coding: utf-8 -*-
"""R129ar: Add batches 86, 89, 31 to COMBINED dict and GOLDEN_NORMAL (already within 5%)."""
import os

path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "tools", "diag_final_validation_v3.py")

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# Add batches after batch 36
old = '    36: {"mux": 0.47, "mup": 0.045, "dist_tcin_asym": 20, "m_s": 0.029,\n          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},'
new = '    36: {"mux": 0.47, "mup": 0.045, "dist_tcin_asym": 20, "m_s": 0.029,\n          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},\n    31: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,\n          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},'

if old in content:
    content = content.replace(old, new)
    # Update GOLDEN_NORMAL
    content = content.replace(
        'GOLDEN_NORMAL = [8, 11, 16, 22, 23, 27, 36, 55, 60, 62, 63, 64, 65, 66, 70, 71, 72, 74, 80, 82, 85, 87, 90]',
        'GOLDEN_NORMAL = [8, 11, 16, 22, 23, 27, 31, 36, 55, 60, 62, 63, 64, 65, 66, 70, 71, 72, 74, 80, 82, 85, 87, 90]'
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Batch 31 added")
else:
    print("Batch 36 not found for batch 31")

# Add batches 86 and 89 after batch 87
path2 = path
with open(path2, "r", encoding="utf-8") as f:
    content = f.read()

old2 = '    87: {"mux": 0.76, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,\n          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},'
new2 = '    87: {"mux": 0.76, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,\n          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},\n    86: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,\n          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},\n    89: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,\n          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},'

if old2 in content:
    content = content.replace(old2, new2)
    content = content.replace(
        'GOLDEN_NORMAL = [8, 11, 16, 22, 23, 27, 31, 36, 55, 60, 62, 63, 64, 65, 66, 70, 71, 72, 74, 80, 82, 85, 87, 90]',
        'GOLDEN_NORMAL = [8, 11, 16, 22, 23, 27, 31, 36, 55, 60, 62, 63, 64, 65, 66, 70, 71, 72, 74, 80, 82, 85, 86, 87, 89, 90]'
    )
    with open(path2, "w", encoding="utf-8") as f:
        f.write(content)
    print("Batches 86, 89 added")
else:
    print("Batch 87 not found for batches 86, 89")
