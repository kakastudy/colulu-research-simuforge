# -*- coding: utf-8 -*-
"""dashboard.py 无头探测（DASH_NO_UI=1 保证仅数据层执行）：批 8/27 全图帧构造。"""
import sys, os, json, inspect
import numpy as np

os.environ["DASH_NO_UI"] = "1"
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "candidate", "indpensim", "v0.1")))
import dashboard as db

PASS = 0

def ok(name, cond):
    global PASS
    if cond:
        PASS += 1
        print(f"[PASS] {name}")
    else:
        raise AssertionError(name)

for b in (8, 27):
    v3 = db.load_batch_data(b)
    sim = db.run_simulation(b, db.calib_params(b))
    ym, lvl, reasons = db.batch_summary(sim, v3)
    ok(f"b{b} batch_summary: lvl={lvl} err={ym['rel_err_total']:+.1%}", lvl in ("normal", "benign", "catastrophic"))
    n = 0
    for pairs in (db.ONLINE_PAIRS, db.OFFLINE_PAIRS):
        for sch, vch, lag in pairs:
            df = db.pair_frame(sim, v3, sch, vch, lag)
            if df is None:
                ok(f"b{b} pair {sch}/{vch} None（双方皆无 → 跳过声明）", vch is None)
                continue
            assert "Sim" in df.columns, (sch, vch)
            if vch is not None:
                assert "V3" in df.columns and (np.isfinite((df["Sim"] - df["V3"])).mean() > 0.9), (sch, vch)
            n += 1
    ok(f"b{b}: {n} 图帧无 KeyError/TypeError 且指数对齐", n >= 8)

assert "verbose" in inspect.signature(db.estimate_batch).parameters
ok("estimate_batch 签名含 verbose", True)

print(f"\nAll {PASS} probes passed")
