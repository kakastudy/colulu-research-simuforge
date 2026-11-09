# -*- coding: utf-8 -*-
"""runstore + 记录模块 无头探测：真实 A 档存/取回环 + B 指标纪录 + 列表过滤。"""
import os, sys
V01 = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "candidate", "indpensim", "v0.1")
sys.path.insert(0, V01)
os.environ["DASH_NO_UI"] = "1"
import pandas as pd
import dashboard as db
import runstore

ok = 0
def ck(name, cond):
    global ok
    assert cond, name
    ok += 1
    print("[PASS]", name)

v3 = db.load_batch_data(8)
sim = db.run_simulation(8, db.calib_params(8))
ym, lvl, _ = db.batch_summary(sim, v3)
journal = {"mux": 0.47, "mup": 0.041, "m_s": 0.029, "dist_tcin_asym": 10, "alpha_kla": 85.0,
           "dist_flag": 1, "PAA_c": 530000.0, "N_conc_paa": 150000.0, "c_oil": 1000.0}
k1 = runstore.save_run("A", 8, journal, sim_df=sim,
                       metrics={"yield_err": float(ym["rel_err_total"]),
                                "co2d_max": float(sim["CO2d"].max()), "crash_level": lvl})
meta, df1 = runstore.load_run(k1)
ck("A跟踪回环: 行列一致", df1 is not None and df1.shape == sim.shape)
# 与重新 sim 等价性：直接对比缓存值
hit = runstore.has_run("A", 8, journal)
ck("A命中检测", hit == k1)

k2 = runstore.save_run("B", 8, {"grid": "v1_online54", "batch": 8},
                       metrics={"yield_err": 0.0152, "online_rmse": 0.109},
                       extra={"result": {"params": journal, "top5": [1, 2]}})
meta2, df2 = runstore.load_run(k2)
ck("B指标纪录无轨迹", df2 is None and meta2["metrics"]["yield_err"] == 0.0152)

runs = runstore.list_runs(tier="A", batch_no=8)
ck("列表过滤 A/批8", any(r["run_key"] == k1 for r in runs) and all(r["batch"] == 8 for r in runs))
runstore.delete_run(k2)
ck("删除 B 纪录", runstore.has_run("B", 8, {"grid": "v1_online54", "batch": 8}) is None)

# pair_frame 与记录轨迹继续可用
ck("pair_frame 支持缓存 df", db.pair_frame(df1, v3, "DO2", "DO2") is not None)
print(f"\nAll {ok} store probes passed")
