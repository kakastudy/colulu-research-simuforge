# -*- coding: utf-8 -*-
"""追加发现：PAA 通道两级数据/机制事实（R52-53）到双账本。"""
import json
from datetime import datetime

ts = datetime.now().isoformat()
runs_entry = {
    "ts": ts,
    "run_id": "PAA-channel-facts",
    "stage": "P3",
    "result": [
        "PAT 前向通道演示（批80, tools/demo_raman_channel.py → runs/p3/raman_pat_batch80.json）",
        "暴露 PAA 通道两级事实:",
        "(1) 数据面: 批 80 V3 PAA_offline **退化饱和** — 19 点全钉 1185.3~1203.1",
        "(σ/μ=0.003; 普查 tools/diag_paa_assay_degeneracy.py 显示其余 11 黄金批 σ/μ",
        "0.21~0.76 健康) → 孤例, 对它做相关无意义。",
        "(2) 机制面: 健康批(22) 引擎 PAA 状态 vs 化验 **r=−0.50（lag0, 标度 median 0.9x",
        "正确**; 化验缓升 1300→1520 while 引擎 PAA 大幅振荡 200↔2127）→ PAA 前体通道是",
        "引擎最弱保真通道（P 产物通道 nRMSE 9-15% 良好, PAA 未早前指标化）。",
        "含义: P3 (a) 路径会忠实转播引擎 PAA 的反相关 → PAT 接入的优先形态应先做",
        "『PAA 化验锚定修正』（cross-check/偏差修正）而非直接前向; I3 PAA 覆盖率口径",
        "（宽带包住≠局部保真）在 PH2 全池验收时应与相关系数并列披露。",
    ],
    "evidence": {"artifacts": [
        "runs/p3/raman_pat_batch80.json", "tools/diag_paa_align80.py (已参数化)",
        "tools/diag_paa_assay_degeneracy.py", "tools/demo_raman_channel.py"]}
}
knowledge_entry = {
    "ts": ts,
    "event": "discovery",
    "level": "T7",
    "type": "model_knowledge",
    "content": (
        "评估方法论两条: (1) I3 覆盖率（±1.96σ 包住真值）在化验退化为常量时无信息量、"
        "在引擎振荡（与真值反相关）而带宽足够时仍可满分 → 覆盖率必须与局部相关/偏差"
        "并列才构成保真证据; (2) 软测量通道接入策略分层 — 若源模型对 analyte 反相关,"
        "说 PAS嘴 PAT 通道应先做锚定修正再前向（PAT 作为校正源而非转发器）。"
    ),
    "ref": "runs/p3/raman_pat_batch80.json"
}
for path, entry in [(r"runs\ledger.jsonl", runs_entry), (r"knowledge\ledger.jsonl", knowledge_entry)]:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
print("ledgered:", ts)
