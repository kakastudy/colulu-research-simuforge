# -*- coding: utf-8 -*-
"""P3-m0b：Batch_Records 通用结构探查。"""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="gbk", errors="replace")

import scipy.io as sio

P = r"C:\Users\admin\Desktop\AI4S研究\青霉素反应罐\IndPenSim_V2.01\IndPenSim_V2.02\IndPenSim_V2_export_V6.mat"
m = sio.loadmat(P, struct_as_record=False, squeeze_me=True)
print("top keys:", [k for k in m.keys() if not k.startswith("__")])
br = m["Batch_Records"]
print("Batch_Records type:", type(br))
fn = getattr(br, "_fieldnames", None)
print("fieldnames[:6]:", fn[:6] if fn else None)
if not fn:
    print("shape:", br.shape, "dtype:", getattr(getattr(br, "dtype", None), "names", None))
else:
    b = getattr(br, fn[0])
    print("fields of", fn[0], ":", getattr(b, "_fieldnames", None))
    if hasattr(b, "Raman_Spec"):
        rs = b.Raman_Spec
        print("Raman fields:", getattr(rs, "_fieldnames", None))
        inten = getattr(rs, "Intensity", None)
        import numpy as np
        if inten is not None:
            a = np.asarray(inten)
            print("Intensity shape:", a.shape, "nonzero frac:",
                  round(float((a != 0).mean()), 4), "max:", float(np.nanmax(a)))
        wl = getattr(rs, "Wavelength", None)
        if wl is not None:
            w = np.asarray(wl).ravel()
            print("Wavelength:", w[:3], "...", w[-3:], "n=", w.size)
