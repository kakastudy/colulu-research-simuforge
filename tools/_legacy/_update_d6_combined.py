# -*- coding: utf-8 -*-
"""Update D6 health view COMBINED dict to match R129i golden regression."""
import os

path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "tools", "d6_health_view.py")
with open(path, "r", encoding="utf-8") as f:
    text = f.read()

start = text.find("# 黄金回归 COMBINED dict")
end = text.find("}", start) + 1

new_block = (
    '# 黄金回归 COMBINED dict（与 diag_final_validation_v2.py 逐字对齐，R129i 更新）\n'
    'COMBINED = {\n'
    '    8:  {"mux": 0.47, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.029,\n'
    '          "biomass_death_rate": 0.001, "death_start": 100},\n'
    '    11: {"mux": 0.41, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.020},\n'
    '    16: {"mux": 0.41, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.025,\n'
    '          "biomass_death_rate": 0.005, "death_start": 0},\n'
    '    22: {"mux": 0.35, "mup": 0.065, "dist_tcin_asym": 20, "m_s": 0.029,\n'
    '          "m_s_schedule": [(110, 0.010)]},\n'
    '    23: {"mux": 0.35, "mup": 0.070, "dist_tcin_asym": 10, "m_s": 0.029,\n'
    '          "biomass_death_rate": 0.0005, "death_start": 200},\n'
    '    27: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 15, "m_s": 0.029,\n'
    '          "m_s_schedule": [(140, 0.018)]},\n'
    '    36: {"mux": 0.47, "mup": 0.045, "dist_tcin_asym": 10, "m_s": 0.010},\n'
    '    55: {"mux": 0.47, "mup": 0.055, "dist_tcin_asym": 20, "m_s": 0.025,\n'
    '          "biomass_death_rate": 0.001, "death_start": 200},\n'
    '    60: {"mux": 0.47, "mup": 0.035, "dist_tcin_asym": 15, "m_s": 0.010},\n'
    '    80: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 18, "m_s": 0.029,\n'
    '          "biomass_death_rate": 0.005, "death_start": 0},\n'
    '    91: {"mux": 0.39, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.029,\n'
    '          "biomass_death_rate": 0.005, "death_start": 200},\n'
    '    92: {"mux": 0.47, "mup": 0.041, "dist_tcin_asym": 18, "m_s": 0.029,\n'
    '          "m_s_schedule": [(150, 0.015)],\n'
    '          "biomass_death_rate": 0.005, "death_start": 200},\n'
    '}'
)

text = text[:start] + new_block + text[end:]

with open(path, "w", encoding="utf-8") as f:
    f.write(text)

print("OK: COMBINED dict updated in d6_health_view.py")
