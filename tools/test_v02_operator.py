# -*- coding: utf-8 -*-
"""v0.2 算子一致性测试：calibration.death_correct_X == observe._death_corr。"""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="gbk", errors="replace")
sys.path.insert(0, r"C:\Users\admin\Desktop\AI4S研究\青霉素反应罐\candidate\indpensim\v0.1")

from simulate import simulate_open_loop
from calibration import calib_params, load_death_beta, death_correct_X
from observe import load_death_coef, _death_corr
import numpy as np

beta_t = load_death_beta()
coef_d = load_death_coef()
assert beta_t is not None, "death_term.json 未解析到"
print("beta tuple =", tuple(round(x, 2) for x in beta_t), "| r2 =", coef_d["r2"])

sim, v3 = simulate_open_loop(60, calib_params(60))
x_new = death_correct_X(sim).to_numpy(float)
x_ref = _death_corr(sim, coef_d)
d = np.max(np.abs(x_new - x_ref))
print("X end: raw=%.2f death_corr=%.2f | max |diff vs observe._death_corr| = %.2e" % (
    sim["X"].iloc[-1], x_new[-1], d))
assert d < 1e-9, "两实现不一致"
assert np.isfinite(x_new).all()
print("V0.2 OPERATOR EQUIVALENCE PASS")
