# -*- coding: utf-8 -*-
"""G4 预跑（批 60）：调用形态同 p4_upgrade_driver 内部（n_ens=30, death on）。"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="gbk", errors="replace")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "candidate", "indpensim", "v0.1"))

from observe import ensemble_smooth

r = ensemble_smooth(60, n_ens=30, seed=11, verbose=False,
                    out_path=os.path.join(ROOT, "runs", "hier_est", "esmooth_60_p4gate.json"))
cov = r.get("coverage", {})
print("PAA_offline:", cov.get("PAA_offline"))
print("P_offline:", cov.get("P_offline"))
print("X_offline:", cov.get("X_offline"))
