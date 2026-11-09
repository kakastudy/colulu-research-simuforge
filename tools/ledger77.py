# -*- coding: utf-8 -*-
"""追加里程碑：model.py a_0^(1/3) NaN 健壮性修复 + 批 73 根因（R77）到双账本。"""
import json
from datetime import datetime

ts = datetime.now().isoformat()
runs_entry = {
    "ts": ts,
    "run_id": "model-cbrt-robustness",
    "stage": "PH2-engine",
    "result": [
        "根因修复：model.py dy[9]（viscosity）= 3·a_0**(1/3)·… 在 BDF 试探子步 a_0<0 时",
        "产生 NaN → scipy LU asarray_chkfinite ValueError 炸掉整链（批 73 全池投票唯一",
        "diverged 的根因; rd 单点 debug 链: 参数四舍五入版成功 vs 实际细化值 0.40638/",
        "0.041478/0.026835 失败 → 参数敏感性边界）。修复: a_0 负体力试算钳 0（物理：菌丝",
        "量非负; 与 guards() 后验钳一致）。批 73 rd aligned 路径实测通过（simulate OK/",
        "aligned OK）。",
        "**引擎守护验证 PASS**: 黄金回归在补丁后精确保持 RMSE 4.48% / 灾难性 0/12 /",
        "within5% 9/12（逐字 A-tier 基线）→ 对健康轨迹零行为变化。",
    ],
    "evidence": {"artifacts": [
        "candidate/indpensim/v0.1/model.py (a_0_pos 钳)",
        "runs/final_validation_v2.json（重生成）",
        "tools/probe_batch73.py / debug_batch73_rd.py（根因链）"]}
}
knowledge_entry = {
    "ts": ts,
    "event": "discovery",
    "level": "T5",
    "type": "model_knowledge",
    "content": (
        "ODE 健壮性工程要点: MATLAB 移植模型的『亚表层标定余量』假设（a_0≥0）在参数"
        "细化（θ_b 网格 48 组合、Δμx~1e-4）下可被推到边界外 → 底数可为负的分数幂在"
        "scipy 积分器的试探步上直接废掉 LU（不只是产生坏轨迹）。修复形式=物理域钳制",
        "（非 NaN 吞噬/非符号翻转），并必须跑黄金回归验证『对健康轨迹零行为变化』"
        "——这是任何 rp模型数值补丁的最低守护标准。"
    ),
    "ref": "runs/final_validation_v2.json + tools/debug_batch73_rd.py"
}
for path, entry in [(r"runs\ledger.jsonl", runs_entry), (r"knowledge\ledger.jsonl", knowledge_entry)]:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
print("ledgered:", ts)
