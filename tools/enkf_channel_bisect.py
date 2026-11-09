# -*- coding: utf-8 -*-
"""单通道级二分（obs_channels 白名单机制）：找 X 破坏的有毒在线观测。"""
import sys
sys.path.insert(0, 'candidate/indpensim/v0.1')
import observe as ob

CHS = ["DO2", "T", "Q", "CO2outgas", "O2", "pH"]
out = {}
for ch in CHS:
    r = ob.enkf_observe(11, n_ens=16, verbose=False, out_path=None,
                        obs_channels=[ch])
    recs = r["records"]
    xs = [(round(int(x['time_h'])), round(x["X_sum"], 2)) for x in recs
          if int(x["time_h"]) in (40, 120, 240)]
    out[ch] = xs
    print(f"[{ch}] fail={r.get('integration_failures')} :: {xs}", flush=True)
