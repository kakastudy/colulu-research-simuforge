# -*- coding: utf-8 -*-
"""Add Y_PAA_P and Y_PAA_X overrides to simulate.py."""
import os

p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "candidate", "indpensim", "v0.1", "simulate.py")

with open(p, "r", encoding="utf-8") as f:
    s = f.read()

old = '    if "m_paa" in params:\n        par[77] = params["m_paa"]\n'
new = '    if "m_paa" in params:\n        par[77] = params["m_paa"]\n    if "Y_PAA_P" in params:\n        par[75] = params["Y_PAA_P"]\n    if "Y_PAA_X" in params:\n        par[76] = params["Y_PAA_X"]\n'

assert old in s, "old not found"
s = s.replace(old, new)

with open(p, "w", encoding="utf-8", newline="") as f:
    f.write(s)

print("Added Y_PAA_P and Y_PAA_X overrides to simulate.py")
