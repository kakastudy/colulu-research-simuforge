# -*- coding: utf-8 -*-
"""P3-m0 Raman 数据可用性探针：V6/V7 .mat 内是否有 Raman_Spec 强度数据。"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="gbk", errors="replace")

import scipy.io as sio

P = r"C:\Users\admin\Desktop\AI4S研究\青霉素反应罐\IndPenSim_V2.01\IndPenSim_V2.02\IndPenSim_V2_export_V6.mat"
print("loading (98MB)...", flush=True)
try:
    m = sio.loadmat(P, struct_as_record=False, squeeze_me=True, variable_names=["Batch_Records"])
except Exception as e:
    print("scipy loadmat failed:", type(e).__name__, e, flush=True)
    m = None

if m:
    br = m.get("Batch_Records")
    print("type:", type(br), "shape:", getattr(br, "shape", None))
    names = getattr(br, "_fieldnames", None)
    if not names:
        names = list(br.dtype.names) if hasattr(br, "dtype") else []
    print("n_batches:", len(names) if names else 0)
    if names:
        key = [n for n in names if "3" in n or "61" in n or "80" in n][:3]
        for k in key[:1]:
            b = getattr(br, k)
            print("fields of", k, ":", getattr(b, "_fieldnames", None) or b.dtype.names)
