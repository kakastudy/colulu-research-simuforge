# -*- coding: utf-8 -*-
import sys, os
V01 = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "candidate", "indpensim", "v0.1")
sys.path.insert(0, V01)
import soft_sensing, optimize
print("B-tier import OK:", hasattr(soft_sensing, "estimate_batch"))
print("C-tier import OK:", hasattr(optimize, "optimize_feed"))
src = open(os.path.join(V01, "dashboard.py"), encoding="utf-8").read()
print("dashboard has B-tier section:", "B 档软测量估算" in src)
print("dashboard has C-tier section:", "C 档" in src)
ss = open(os.path.join(V01, "soft_sensing.py"), encoding="utf-8").read()
print("estimate_batch uses RELATIVE data path (fragile):", 'read_csv(f"data/processed' in ss)
print("estimate_batch has divergence guard:", "except Exception" in ss)
