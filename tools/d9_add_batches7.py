# -*- coding: utf-8 -*-
"""R129ba: Add batches 1, 2, 5 to COMBINED dict and GOLDEN_NORMAL."""
import os

path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "tools", "diag_final_validation_v3.py")

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# Add batches after batch 8
old = '    8:  {"mux": 0.47, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.029,'
new = '    8:  {"mux": 0.47, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.029,'

# Actually, let me find the right place. Let me add after batch 57 (the last one before 78)
# Let me find the end of the COMBINED dict
# Actually, let me just add them before the closing }
# Find the last batch entry
import re
# Find the pattern for the last batch before the closing }
match = re.search(r'\n    (\d+): \{"mux".*?\},?\n', content, re.DOTALL)
if match:
    # Add after the last batch
    last_batch_match = list(re.finditer(r'    (\d+): \{"mux".*?\},?\n', content, re.DOTALL))[-1]
    last_batch = last_batch_match.group(0)
    # Remove the trailing comma if present
    if last_batch.endswith(',\n'):
        last_batch = last_batch[:-2] + '\n'
    
    # Add new batches
    new_batches = '''    1: {"mux": 1.00, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    2: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85,
          "mu_h_scale": 1.2},
    5: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
'''
    
    content = content.replace(last_batch, last_batch + new_batches)
    
    # Update GOLDEN_NORMAL
    content = content.replace(
        'GOLDEN_NORMAL = [8, 11, 16, 22, 23, 27, 36, 55, 57, 60, 62, 63, 64, 65, 66, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 80, 82, 85, 86, 87, 88, 89, 90, 95, 96]',
        'GOLDEN_NORMAL = [1, 2, 5, 8, 11, 16, 22, 23, 27, 36, 55, 57, 60, 62, 63, 64, 65, 66, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 80, 82, 85, 86, 87, 88, 89, 90, 95, 96]'
    )
    
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Edit successful")
else:
    print("Pattern not found")
