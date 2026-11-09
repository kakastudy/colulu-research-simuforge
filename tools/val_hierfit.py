# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, 'candidate/indpensim/v0.1')
import hier_est as he
import numpy as np

tl = he.load_theta_log()
by_batch = {r['batch']: r for r in tl}
val_set = [1, 6, 9, 14, 15, 21, 24, 25, 28, 38, 40, 41, 44, 50, 52, 53,
           61, 64, 65, 66, 67, 70, 76, 81, 82, 84, 95, 96]
val_theta = [by_batch[b] for b in val_set if b in by_batch]
print('验证池可用:', len(val_theta), '/28')
fit = he.hier_fit(val_theta)
for k, v in fit.items():
    print(f"{k:>4}: mu_hat={v['mu_hat']:.4f}  sigma_hat={v['sigma_hat']:.4f}  MATLAB_ref={v['matlab_ref']}")
mup_vals = [t['theta_post']['mup'] for t in val_theta]
print('μp 批间 min/max:', round(min(mup_vals), 4), round(max(mup_vals), 4),
      'std:', round(float(np.std(mup_vals)), 4))
