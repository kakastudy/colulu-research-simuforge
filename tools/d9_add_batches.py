# -*- coding: utf-8 -*-
"""R129am: Add batches 70, 85, 93 to COMBINED dict and GOLDEN_NORMAL."""
import os

path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "tools", "diag_final_validation_v3.py")

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# Add batch 93 after batch 74
old = '}\n\nGOLDEN_NORMAL = [8, 11, 16, 22, 23, 27, 36, 55, 60, 63, 66, 72, 74, 80]'
new = '    93: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,\n          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85,\n          "mu_h_scale": 1.2},\n}\n\nGOLDEN_NORMAL = [8, 11, 16, 22, 23, 27, 36, 55, 60, 63, 66, 70, 72, 74, 80, 85]'

if old in content:
    content = content.replace(old, new)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Edit successful")
else:
    print("old_string not found")
    # Show what's around the target area
    idx = content.find("GOLDEN_NORMAL")
    if idx >= 0:
        print("GOLDEN_NORMAL at index", idx)
        print(repr(content[idx-20:idx+80]))
