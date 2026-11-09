# -*- coding: utf-8 -*-
"""追加里程碑：Raman P3 数据可用性普查（R50）到双账本。"""
import json
from datetime import datetime

ts = datetime.now().isoformat()
runs_entry = {
    "ts": ts,
    "run_id": "P3-raman-availability",
    "stage": "P3",
    "result": [
        "Raman 数据可用性普查（P3 第二期启用前置核查）: V6/V7 export .mat 含**真实模拟光谱**",
        "（Batch_01: Intensity 2200×1215 [201..2400 cm⁻¹], 99.2% 非零, max≈2.6e6, 与",
        "Raman_Sim.m 引擎内合成一致）但仅 Batch_01/02 两个示范批; V3 大 CSV 波长列全零;",
        "批池 61-90 实测光谱不在工作区（Mendeley 文件 API 400 / S3 直链 403 / web_search",
        "缺 key）。→ P3 外部数据缺口如实登记（I2 可见性）。",
        "两路径: (a) 引擎侧合成层 — Raman_Sim.m 从引擎状态（PAA 浓度等）前向合成光谱,",
        "与 PLS 资产自洽（PLS 本就对 Raman_Sim 合成谱标定）→ 推荐, V1+; (b) 人工获取",
        "Mendeley Raman 原始文件。",
    ],
    "evidence": {"artifacts": [
        "tools/probe_raman_mat.py", "tools/probe_raman_mat2.py", "tools/probe_raman_mat3.py",
        "docs/pending_review_list.md 条目5 更新"]}
}
knowledge_entry = {
    "ts": ts,
    "event": "discovery",
    "level": "T5",
    "type": "data_provenance",
    "content": (
        "数据考古发现: IndPenSim_V2.02 公开导出 .mat 的 Raman_Spec 是**引擎内 Raman_Sim.m "
        "前向合成**的光谱（非实验室实测）→ 与 PAA_PLS_model 自洽闭环（PLS 系数即对合成谱"
        "标定）。 industrially: PAT 软测量资产的『ground truth』本身是模型层生成 — 消融"
        "设计必须区分『光路/噪声真实性』与『浓度预测精度』两类误差。V3 数据集的 CSV 展平"
        "把光谱列置零（仅记录波长标签），实测光谱存于单独发布文件（未随工作区归档）。"
    ),
    "ref": "IndPenSim_V2.01/IndPenSim_V2.02/Raman_Sim.m + probe_raman_mat*.py"
}
for path, entry in [(r"runs\ledger.jsonl", runs_entry), (r"knowledge\ledger.jsonl", knowledge_entry)]:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
print("ledgered:", ts)
