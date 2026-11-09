# -*- coding: utf-8 -*-
"""追加里程碑：G4 三批预跑记分卡定案（R59-63）到双账本。"""
import json
from datetime import datetime

ts = datetime.now().isoformat()
runs_entry = {
    "ts": ts,
    "run_id": "P4-G4-prescore",
    "stage": "P4",
    "result": [
        "G4 闸门三批全预跑（n_ens=30, death_term=True, seed=11, 形态同 driver）:",
        "批11 X=0.625 / 批16 X=0.789 / 批60 X=0.474 → 均值 **0.629 >= 0.60 → G4 PASS(贴线)**。",
        "物证 esmooth_1{1,6}_p4gate.json / esmooth_60_p4gate.json。",
        "诚实口径注意: 覆盖率≠逐点保真 — 批60 死亡项探针逐点最强(corr .942→.989,",
        "nRMSE 24.8→5.9%) 但覆盖率最低(0.474): 其集合带『窄而偏』; 批16 逐点较弱但带",
        "『宽而覆盖』→ 高覆盖。覆盖率与 nRMSE/相关并列披露的政策（R52-53 登记）再次",
        "被数据印证。",
    ],
    "decision": "G4 无需设计干预; 自动验收链白跑风险解除。",
    "evidence": {"artifacts": [
        "runs/hier_est/esmooth_11_p4gate.json", "runs/hier_est/esmooth_16_p4gate.json",
        "runs/hier_est/esmooth_60_p4gate.json", "tools/smoke_g4_gate*.py"]}
}
knowledge_entry = {
    "ts": ts,
    "event": "discovery",
    "level": "T7",
    "type": "model_knowledge",
    "content": (
        "覆盖率的『窄而偏 vs 宽而盖』二象性: 同一 posterior 机制下, 逐点拟合最好批的",
        "覆盖率可以最低(窄带偏倚), 拟合较弱批反可满分(宽带) — 集合置信区间评价需",
        "『覆盖率×离散保真×相关性』三元组, 单元指标会同时漏报两类不同失败模式。"
        "工程含义: 校准 spread 时应对『偏倚』与『宽度』分别处理(偏倚修正/膨胀)而非仅膨胀。"
    ),
    "ref": "runs/hier_est/esmooth_*_p4gate.json 三批对照"
}
for path, entry in [(r"runs\ledger.jsonl", runs_entry), (r"knowledge\ledger.jsonl", knowledge_entry)]:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
print("ledgered:", ts)
