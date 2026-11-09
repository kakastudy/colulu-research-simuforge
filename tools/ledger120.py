# -*- coding: utf-8 -*-
"""R120 账本：v2 池 88/88 满池 + 验收链触发 + ph1e_fit 路径 bug 修复。"""
import json
from datetime import datetime

ts = datetime.now().isoformat()
runs_entry = {
    "ts": ts,
    "run_id": "pool-complete-chain",
    "stage": "PH2/P4",
    "result": [
        "v2 池 88/88 全齐、零 tombstone（pwsh-524 池 worker exit=0）——PH1 全量完成。",
        "watcher（pwsh-874 新链）自动触发验收链: ph1e_fit → p4_upgrade_driver",
        "（内嵌 ph2_full_driver → G4 → G5）→ make_ph2_acceptance → make_ph2_acceptance_report。",
        "ph1e_fit 首次运行因 dst 路径 dirname 多一层崩溃（写到 AI4S研究\\runs\\...）——",
        "修复为项目根两级 dirname；手动补跑成功：hier_prior_v2.json 落盘（88 批,",
        "mux μ̂=0.4084/σ̂=0.0032, mup μ̂=0.0414/σ̂=0.0014, m_s μ̂=0.0254/σ̂=0.0011;",
        "EB T*=4 (mux)/1 (mup); DL σ̂=0（var_mean 主导——网格后验波兰, 已登记 PH3+ 债务）——",
        "与 MATLAB 生成机制参考（0.41±0.025 / 0.041±0.0025）吻合。",
        "时序注意: p4_upgrade_driver 启动时 G2 检查先于手动补跑 → 本轮 verdict 将判",
        "HOLD（G2=False）；ph2_full_driver + G4 跑完后需重跑驱动（G2/G3 产物已就位,",
        "仅 G4 ensemble_smooth ~15 min 重跑）→ 预期 PASS。",
        "另修: 驱动 hard 裁决列表补入 G2（原仅 G1/G3/G4——ph1e_fit 崩溃会被漏判）；",
        "驱动 docstring G3 描述与 R76 实际实现对齐。",
    ],
    "decision": "池满 → 验收链在跑; 终判需驱动重跑一次（G2 时序修复后）。",
    "evidence": {"artifacts": [
        "runs/hier_est/train_theta_v2.jsonl (88 rows)",
        "runs/hier_est/hier_prior_v2.json",
        "tools/ph1e_fit.py (path fix)",
        "tools/p4_upgrade_driver.py (G2 hard-gate + docstring)"]},
}
knowledge_entry = {
    "ts": ts,
    "event": "note", "type": "process", "level": "T3",
    "content": (
        "链上时序教训: 验收链各环节的产物存在性检查必须在该环节完成之后——ph1e_fit 崩溃",
        "时 G2 检查不能「先查后补」；补跑后需重跑下游驱动才能让 verdict 反映真实状态。"
        "另: 驱动的裁决闸门列表必须包含所有硬闸（G1-G4），G5 为报告性不入裁决。"
    ),
    "ref": "tools/p4_upgrade_driver.py + watch_and_accept_v2.py"
}
for path, entry in [(r"runs\ledger.jsonl", runs_entry), (r"knowledge\ledger.jsonl", knowledge_entry)]:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
print("ledgered:", ts)
