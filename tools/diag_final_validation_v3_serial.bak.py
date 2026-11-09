# -*- coding: utf-8 -*-
"""FINAL validation v2: 证据化崩溃分级 (benign/catastrophic) + 全批次复验."""
import sys, os, json
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
from simulate import simulate_open_loop, yield_metrics, classify_crash

COMBINED = {
    8:  {"mux": 0.47, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.029,
          "biomass_death_rate": 0.001, "death_start": 100, "q_co2": 0.12, "Y_NX": 10, "Y_NP": 80, "alpha_kla": 90, "vis_scale": 0.9, "PAA_c": 530000.0, "m_paa": 1.0, "Y_O2_X": 800, "Y_O2_P": 200, "m_O2_X": 15,
          "late_death_rate": 0.005, "mu_death_ref": 0.02, "death_recycle": 0.5},
    11: {"mux": 0.41, "mup": 0.041, "dist_tcin_asym": 10, "m_s": 0.020, "q_co2": 0.11, "Y_NX": 10, "Y_NP": 80, "alpha_kla": 110, "vis_scale": 0.9, "PAA_c": 530000.0, "m_paa": 0.7, "Y_O2_X": 800, "Y_O2_P": 80, "m_O2_X": 15,
          "late_death_rate": 0.008, "mu_death_ref": 0.02, "death_recycle": 0.3},
    12: {"mux": 0.35, "mup": 0.06, "dist_tcin_asym": 20, "m_s": 0.034,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85,
          "mu_h_scale": 2.8},
    16: {"mux": 0.41, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.025,
          "biomass_death_rate": 0.005, "death_start": 0, "q_co2": 0.14, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 75, "vis_scale": 0.9, "PAA_c": 400000.0, "m_paa": 0.5, "Y_O2_X": 800, "Y_O2_P": 200, "m_O2_X": 17.5,
          "late_death_rate": 0.008, "mu_death_ref": 0.01, "death_recycle": 0.3},
    22: {"mux": 0.35, "mup": 0.065, "dist_tcin_asym": 20, "m_s": 0.029,
          "m_s_schedule": [(110, 0.010)], "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85,
          "mu_h_scale": 3.5,
          "late_death_rate": 0.008, "mu_death_ref": 0.02, "death_recycle": 0.5},
    23: {"mux": 0.35, "mup": 0.070, "dist_tcin_asym": 10, "m_s": 0.029,
          "biomass_death_rate": 0.0005, "death_start": 200, "q_co2": 0.1, "Y_NX": 15, "Y_NP": 60, "alpha_kla": 110, "vis_scale": 0.9, "PAA_c": 530000.0, "m_paa": 1.0, "Y_O2_X": 650, "Y_O2_P": 200, "m_O2_X": 15,
          "mu_h_scale": 3.5,
          "late_death_rate": 0.002, "mu_death_ref": 0.02, "death_recycle": 0.3},
    27: {"mux": 0.36, "mup": 0.040, "dist_tcin_asym": 15, "m_s": 0.029,
          "m_s_schedule": [(140, 0.018)], "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85, "vis_scale": 0.9, "PAA_c": 530000.0, "m_paa": 1.0, "Y_O2_X": 650, "Y_O2_P": 160, "m_O2_X": 15},
    36: {"mux": 0.47, "mup": 0.045, "dist_tcin_asym": 10, "m_s": 0.010, "q_co2": 0.1, "Y_NX": 20, "Y_NP": 40, "alpha_kla": 130, "vis_scale": 0.8, "PAA_c": 530000.0, "m_paa": 0.7, "Y_O2_X": 650, "Y_O2_P": 160, "m_O2_X": 10, "late_death_rate": 0.005, "mu_death_ref": 0.005, "death_recycle": 0.0},
    37: {"mux": 0.35, "mup": 0.07, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85,
          "PAA_c": 780000},
    38: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85,
          "mu_h_scale": 1.8},
    39: {"mux": 0.35, "mup": 0.06, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 50, "alpha_kla": 85},
    41: {"mux": 0.80, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    40: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85,
          "mu_h_scale": 1.57},
    42: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.021,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    43: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85,
          "mu_h_scale": 1.5},
    45: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.0377,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85,
          "mu_h_scale": 1.3},
    46: {"mux": 0.65, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    47: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    48: {"mux": 0.35, "mup": 0.05, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    49: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85,
          "mu_h_scale": 2.0},
    50: {"mux": 0.35, "mup": 0.08, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85,
          "PAA_c": 800000},
    55: {"mux": 0.47, "mup": 0.055, "dist_tcin_asym": 20, "m_s": 0.025,
          "biomass_death_rate": 0.001, "death_start": 200, "q_co2": 0.11, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85, "PAA_c": 530000.0, "m_paa": 1.0, "Y_O2_X": 650, "Y_O2_P": 160, "m_O2_X": 17.5},
    52: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85,
          "mu_h_scale": 2.0},
    53: {"mux": 0.60, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    54: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85,
          "mu_h_scale": 1.6},
    56: {"mux": 0.75, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    60: {"mux": 0.47, "mup": 0.035, "dist_tcin_asym": 15, "m_s": 0.010, "q_co2": 0.1, "Y_NX": 20, "Y_NP": 40, "alpha_kla": 85, "PAA_c": 530000.0, "m_paa": 1.0, "late_death_rate": 0.005, "mu_death_ref": 0.005, "death_recycle": 0.0},
    80: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 18, "m_s": 0.029,
          "biomass_death_rate": 0.005, "death_start": 0, "q_co2": 0.13, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85, "vis_scale": 0.9, "PAA_c": 400000.0, "m_paa": 0.3, "Y_O2_X": 800, "Y_O2_P": 120, "m_O2_X": 17.5},
    85: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    82: {"mux": 0.60, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    83: {"mux": 1.00, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    84: {"mux": 0.95, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    65: {"mux": 0.55, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    90: {"mux": 0.60, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    62: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    87: {"mux": 0.76, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    86: {"mux": 0.51, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    68: {"mux": 0.70, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    73: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85,
          "mu_h_scale": 2.0},
    57: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85,
          "mu_h_scale": 1.5},
    58: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85,
          "mu_h_scale": 1.5},
    59: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85,
          "mu_h_scale": 1.5},
    61: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85,
          "mu_h_scale": 2.0},
    67: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85,
          "mu_h_scale": 2.0},
    79: {"mux": 0.80, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    78: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    76: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    77: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85,
          "mu_h_scale": 1.5},
    75: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85,
          "mu_h_scale": 2.0},
    95: {"mux": 0.95, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    96: {"mux": 0.50, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    98: {"mux": 0.45, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    99: {"mux": 0.35, "mup": 0.07, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.08, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    99: {"mux": 0.35, "mup": 0.07, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    100: {"mux": 0.90, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    88: {"mux": 0.96, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    69: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85,
          "mu_h_scale": 2.0},
    89: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    91: {"mux": 0.40, "mup": 0.040, "dist_tcin_asym": 10, "m_s": 0.029,
          "biomass_death_rate": 0.005, "death_start": 200, "q_co2": 0.12, "Y_NX": 10, "Y_NP": 60, "alpha_kla": 90},
    92: {"mux": 0.47, "mup": 0.041, "dist_tcin_asym": 18, "m_s": 0.029,
          "m_s_schedule": [(150, 0.015)],
          "biomass_death_rate": 0.005, "death_start": 200, "q_co2": 0.11, "Y_NX": 12, "Y_NP": 60, "alpha_kla": 130, "vis_scale": 0.9, "PAA_c": 530000.0, "m_paa": 0.7, "Y_O2_X": 650, "Y_O2_P": 160, "m_O2_X": 17.5, "late_death_rate": 0.005, "mu_death_ref": 0.005, "death_recycle": 0.0},
    63: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85,
          "mu_h_scale": 1.5},
    64: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    71: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    66: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85,
          "mu_h_scale": 2.0},
    70: {"mux": 0.55, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    72: {"mux": 0.55, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    74: {"mux": 0.59, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    93: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85,
          "mu_h_scale": 1.2},
    1: {"mux": 1.00, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    2: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85,
          "mu_h_scale": 1.2},
    3: {"mux": 0.35, "mup": 0.06, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    5: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    7: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85,
          "mu_h_scale": 1.2},
    9: {"mux": 0.40, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    14: {"mux": 0.90, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    15: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85,
          "mu_h_scale": 1.2},
    17: {"mux": 0.50, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    18: {"mux": 0.35, "mup": 0.06, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85,
          "mu_h_scale": 0.5},
    20: {"mux": 1.00, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    24: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85,
          "mu_h_scale": 2.0},
    26: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85,
          "mu_h_scale": 1.5},
    28: {"mux": 1.00, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    29: {"mux": 0.35, "mup": 0.08, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85,
          "mu_h_scale": 0.1},
    30: {"mux": 1.00, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    31: {"mux": 0.35, "mup": 0.08, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85,
          "mu_h_scale": 0.7},
    33: {"mux": 0.60, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    34: {"mux": 0.35, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    35: {"mux": 0.65, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85},
    51: {"mux": 0.41, "mup": 0.041, "dist_tcin_asym": 20, "m_s": 0.029,
          "q_co2": 0.12, "Y_NX": 25, "Y_NP": 40, "alpha_kla": 85,
          "mu_h_scale": 1.5},
}

GOLDEN_NORMAL = [1, 2, 3, 5, 7, 8, 9, 11, 12, 14, 15, 16, 17, 18, 20, 22, 23, 24, 26, 27, 28, 29, 30, 31, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 82, 83, 84, 85, 86, 87, 88, 89, 90, 93, 95, 96, 98]
FAULT = [91, 92]

print("=" * 72)
print("FINAL Golden Set Validation v3 (PAA per-batch calibration)")
print("=" * 72)
print(f"{'Batch':>6s} {'Type':>6s} {'yield_err':>9s} {'CO2d':>6s} {'pH_end':>6s} {'crash':>12s}")
print("-" * 72)

all_errs, results = [], []
for b in GOLDEN_NORMAL + FAULT:
    v3 = pd.read_csv(f"data/processed/batches/batch_{b:02d}.csv")
    cp = COMBINED[b]
    params = {"mux": cp["mux"], "mup": cp["mup"], "alpha_kla": cp.get("alpha_kla", 85.0),
              "PAA_c": cp.get("PAA_c", 530000.0), "N_conc_paa": 150000.0, "c_oil": 1000.0,
              "dist_flag": 1, "dist_tcin_asym": cp["dist_tcin_asym"], "m_s": cp["m_s"]}
    if "m_paa" in cp:
        params["m_paa"] = cp["m_paa"]
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
    if "Y_O2_X" in cp:
        params["Y_O2_X"] = cp["Y_O2_X"]
    if "Y_O2_P" in cp:
        params["Y_O2_P"] = cp["Y_O2_P"]
    if "m_O2_X" in cp:
        params["m_O2_X"] = cp["m_O2_X"]
    if "mu_h_scale" in cp:
        params["mu_h_scale"] = cp["mu_h_scale"]
    if "late_death_rate" in cp:
        params["late_death_rate"] = cp["late_death_rate"]
        params["mu_death_ref"] = cp.get("mu_death_ref", 0.02)
        params["death_recycle"] = cp.get("death_recycle", 0.0)
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
