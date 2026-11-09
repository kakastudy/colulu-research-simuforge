import sys; sys.path.insert(0, 'candidate/indpensim/v0.1'); sys.path.insert(0, 'tools/vendor')
import numpy as np, pandas as pd
from simulate import simulate_open_loop, build_initial_state, build_inp1, load_batch, IDX, H_SAMPLE
from params import make_params
from model import rhs, N_STATES

d = load_batch(1)
par = make_params(alpha_kla=90.0, N_conc_paa=150000.0, PAA_c=530000.0, mup=0.041, mux=0.41)

# 用 inhib=2 跑仿真
sim, v3 = simulate_open_loop(1, nominal=True, inhib=2)

# 检查关键时间点的抑制因子
print('=== inhib=2: Key trajectory ===')
for t_target in [0, 2, 5, 10, 20, 40, 60, 80, 100]:
    sim_mask = abs(sim['time_h'] - t_target) < 0.15
    v3_mask = abs(v3['time_h'] - t_target) < 0.15
    if sim_mask.any() and v3_mask.any():
        sr = sim[sim_mask].iloc[-1]
        vr = v3[v3_mask].iloc[-1]
        print(f't={t_target}: S sim={sr["S"]:.4f} V3={vr["S"]:.4f} | '
              f'X sim={sr["A0"]+sr["A1"]+sr["A3"]+sr["A4"]:.3f} | '
              f'NH3 sim={sr["NH3"]:.1f} | '
              f'PAA sim={sr["PAA"]:.1f} | '
              f'CO2 sim={sr["CO2"]:.4f} | '
              f'DO2 sim={sr["DO2"]:.2f} V3={vr["DO2"]:.2f} | '
              f'pH sim={sr["pH"]:.3f} V3={vr["pH"]:.3f} | '
              f'P sim={sr["P"]:.3f} V3={vr["P"]:.3f}')

# 手动计算 t=0 时的抑制因子
y = build_initial_state(d, nominal=True)
inp1 = build_inp1(d.iloc[0], inhib=2)
s = y[0]; a0 = y[11]; a1 = y[12]
pH_H = y[6]; T = y[7]
NH3 = y[30]; PAA = y[29]; CO2d = y[28]
DO2 = y[1]

K1 = par[64]; K2 = par[65]
A_inhib = par[45]
X_crit_N = par[73]
X_crit_CO2 = par[92]
X_crit_DO2 = par[43]
P_crit_DO2 = par[44]
X_crit_PAA = par[78]
P_crit_PAA = par[79]
k_g = par[58]; k_d = par[59]
Eg = par[56]; Ed = par[57]
R = par[42]

pH_inhib = 1.0 / (1 + pH_H / K1 + K2 / pH_H)
NH3_inhib = 0.5 * (1 - np.tanh(A_inhib * (X_crit_N - NH3)))
T_inhib = k_g * np.exp(-(Eg / (R * T))) - k_d * np.exp(-(Ed / (R * T)))
CO2_inhib = 0.5 * (1 + np.tanh(A_inhib * (X_crit_CO2 - CO2d * 1000.0)))
DO_2_inhib_X = 0.5 * (1 - np.tanh(A_inhib * (X_crit_DO2 * 15.02 - DO2)))
PAA_inhib_X = 0.5 * (1 + np.tanh(X_crit_PAA - PAA))
PAA_inhib_P = 0.5 * (1 + np.tanh(-P_crit_PAA + PAA))

print(f'\n=== t=0 inhibition factors ===')
print(f'pH_inhib = {pH_inhib:.4f}')
print(f'NH3_inhib = {NH3_inhib:.4f} (NH3={NH3})')
print(f'T_inhib = {T_inhib:.4f} (T={T})')
print(f'CO2_inhib = {CO2_inhib:.4f} (CO2d={CO2d}, CO2d*1000={CO2d*1000})')
print(f'DO_2_inhib_X = {DO_2_inhib_X:.4f}')
print(f'PAA_inhib_X = {PAA_inhib_X:.4f} (PAA={PAA})')
print(f'PAA_inhib_P = {PAA_inhib_P:.4f}')
mu_e = par[1] * pH_inhib * NH3_inhib * T_inhib * DO_2_inhib_X * CO2_inhib * PAA_inhib_X
print(f'mu_e = {mu_e:.4f}')
