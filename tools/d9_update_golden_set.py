# -*- coding: utf-8 -*-
"""R129at: Update golden set — remove Batch 31, add Batch 86(mux=0.51)/68(mux=0.70)/73(mu_h_scale=2.0)/57(mu_h_scale=1.5)."""
import os

path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "tools", "diag_final_validation_v3.py")

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# Remove batch 31 from COMBINED dict
old_31 = '    31: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,\n          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},\n'
if old_31 in content:
    content = content.replace(old_31, '')
    print("Batch 31 removed from COMBINED")
else:
    print("Batch 31 not found in COMBINED")

# Fix batch 86 mux
old_86 = '    86: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,\n          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},'
new_86 = '    86: {"mux": 0.51, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,\n          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},'
if old_86 in content:
    content = content.replace(old_86, new_86)
    print("Batch 86 mux fixed")
else:
    print("Batch 86 not found")

# Add batches 68, 73, 57 after batch 86
old_add = '    86: {"mux": 0.51, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,\n          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},'
new_add = '    86: {"mux": 0.51, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,\n          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},\n    68: {"mux": 0.70, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,\n          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},\n    73: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,\n          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85,\n          "mu_h_scale": 2.0},\n    57: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,\n          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85,\n          "mu_h_scale": 1.5},'
if old_add in content:
    content = content.replace(old_add, new_add)
    print("Batches 68, 73, 57 added to COMBINED")
else:
    print("Batch 86 (fixed) not found for adding 68, 73, 57")

# Update GOLDEN_NORMAL
old_golden = 'GOLDEN_NORMAL = [8, 11, 16, 22, 23, 27, 31, 36, 55, 60, 62, 63, 64, 65, 66, 70, 71, 72, 74, 80, 82, 85, 86, 87, 89, 90]'
new_golden = 'GOLDEN_NORMAL = [8, 11, 16, 22, 23, 27, 36, 55, 57, 60, 62, 63, 64, 65, 66, 68, 70, 71, 72, 73, 74, 80, 82, 85, 86, 87, 89, 90]'
if old_golden in content:
    content = content.replace(old_golden, new_golden)
    print("GOLDEN_NORMAL updated")
else:
    print("GOLDEN_NORMAL not found")

with open(path, "w", encoding="utf-8") as f:
    f.write(content)
