# -*- coding: utf-8 -*-
"""mcp_server.advise_control 实调用验证：批 8（golden）60–120h 窗 Fs×1.03 反事实。"""
import io
import sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="gbk", errors="replace")
sys.path.insert(0, r"C:\Users\admin\Desktop\AI4S研究\青霉素反应罐\candidate\indpensim\v0.1")

import mcp_server

r = mcp_server.advise_control(8, 60, 120, candidates=[{"Fs": 1.0}, {"Fs": 1.03}, {"Fs": 0.97}])
print("target_g =", round(r["target_g"], 1))
for c in r["cands"]:
    print(" cand:", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in c.items() if k != "scales"},
          c["scales"])
print("best =", r["best"])
print("t1_validation =", r["t1_validation"])
assert r["target_g"] > 0
assert len(r["cands"]) == 3
assert all("err_vs_v3" in c for c in r["cands"]), "全部候选都应完成仿真"
assert r["best"] is not None
print("PASS")
