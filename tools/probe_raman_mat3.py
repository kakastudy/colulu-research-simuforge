# -*- coding: utf-8 -*-
"""P3-m0c：Raw_Batch_data 全批 Raman 可用性普查。"""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="gbk", errors="replace")

import numpy as np
import scipy.io as sio

P = r"C:\Users\admin\Desktop\AI4S研究\青霉素反应罐\IndPenSim_V2.01\IndPenSim_V2.02\IndPenSim_V2_export_V6.mat"
m = sio.loadmat(P, struct_as_record=False, squeeze_me=True, variable_names=["Raw_Batch_data", "Batch_no"])
rb = m["Raw_Batch_data"]
fn = getattr(rb, "_fieldnames", None)
print("Raw_Batch_data n_fields:", len(fn) if fn else 0)
print("first fields:", fn[:8] if fn else None)

# 批号 61-90（Raman 记录批次候选）与黄金批 80
targets = ["Batch_61", "Batch_80", "Batch_90", "Batch_01"]
n_raman = 0
for t in targets[:1] + (fn[60:66] if fn and len(fn) >= 66 else []):
    b = getattr(rb, t, None)
    if b is None:
        continue
    rs = getattr(b, "Raman_Spec", None)
    if rs is None:
        print(t, ": NO Raman_Spec")
        continue
    inten = np.asarray(getattr(rs, "Intensity"))
    flag = getattr(b, "PAT_ref", None)
    nz = float((inten != 0).mean())
    print(f"{t}: Intensity{inten.shape} nonzero={nz:.3f} PAT_ref~{np.asarray(flag).ravel()[0] if not np.isscalar(flag) else flag}")
    if nz > 0.5:
        n_raman += 1
# 全体普查（轻量：只看是否有 Raman_Spec 键 + 非零率抽检每10批）
count = 0
for t in (fn or []):
    b = getattr(rb, t, None)
    rs = getattr(b, "Raman_Spec", None) if b is not None else None
    if rs is not None:
        inten = np.asarray(getattr(rs, "Intensity"))
        if inten.shape[0] > 0 and (inten != 0).mean() > 0.5:
            count += 1
print("batches with real Raman intensity:", count, "/", len(fn or []))
