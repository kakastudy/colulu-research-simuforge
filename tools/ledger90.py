# -*- coding: utf-8 -*-
"""修正条目：PAA 通道保真度普查（R90 扩全 10 批 → R52 结论收窄）。"""
import json
from datetime import datetime

ts = datetime.now().isoformat()
runs_entry = {
    "ts": ts,
    "run_id": "paa-fidelity-census-CORRECTION",
    "stage": "P3",
    "result": [
        "PAA 通道保真度批量普查（tools/census_paa_fidelity.py 扩至 10 黄金批）修证 R52:",
        "『引擎 PAA 反相关』**不是系统性**——分布为批次异质:",
        "强正相关 批36 +0.987 / 批60 +0.998（lag 扫描最优, 健全批）;",
        "弱正 批8 +0.615/lag2 批16 +0.412/lag6 批27 +0.513/lag8 批55 +0.241;",
        "噪级 批11 +0.093; 反相 仅 批22 −0.345 / 批23 −0.614; 批80 退化(σ/μ=0.0028 正确排除)。",
        "|r| 中位 0.513; 反相 2/9 批。",
        "→ 保真缺口是**批间异质**（引擎参数/我校曲线带内 PAA 抑制结构随批特征变化）",
        "而非通道系统性反向; PAT 锚定修正优先级调低（本地已无必要全宽修正）。",
        "R90 普查产物 runs/hier_est/paa_fidelity_census.json。",
    ],
    "evidence": {"artifacts": [
        "runs/hier_est/paa_fidelity_census.json", "tools/census_paa_fidelity.py"]}
}
knowledge_entry = {
    "ts": ts,
    "event": "discovery",
    "level": "T7",
    "type": "model_knowledge",
    "content": (
        "通道保真度治理结论修正: 『个别反相批 ≠ 系统反相』——保留批异质性事实为原调查",
        "重点（Gaussian 维持（G_Module_L9_PAA抑制项批间差异 / m_s 调度批分布特征））。"
        "工程结论: 通道级『全宽修正』不再必要, 按批次条件启用修正（r<0 优先）即可;"
        "R53 登记的『PAT 应先锚定修正再前向』收窄为『仅在该批 r<0 时』。"
    ),
    "ref": "runs/hier_est/paa_fidelity_census.json"
}
for path, entry in [(r"runs\ledger.jsonl", runs_entry), (r"knowledge\ledger.jsonl", knowledge_entry)]:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
print("ledgered:", ts)
