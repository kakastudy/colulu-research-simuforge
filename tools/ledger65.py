# -*- coding: utf-8 -*-
"""追加发现：A_t1 双约定澄清 + 批27 改善差异的机理闭合（R63-65）到双账本。"""
import json
from datetime import datetime

ts = datetime.now().isoformat()
runs_entry = {
    "ts": ts,
    "run_id": "at1-convention-clarify",
    "stage": "P4",
    "result": [
        "A_t1 双约定澄清（逐化验点透明追踪 tools/trace_death_corr11.py）:",
        "死亡项修正实际使用的公式口径 A_t1=a0/(a1+a3+a4) 在批 11 的 16 个化验对齐点",
        "上是 0.22~0.51 健康有界值（随培养成熟缓慢衰减 0.51→0.22, X_corr 紧贴化验）",
        "→ 数值稳定性疑云解除（kd2/kd3 无爆炸域）。sim 记录表内同名呈现列（60→4500,",
        "另一约定, 量级不同）与修正口径不可互换 — 已在 observe._death_corr 与",
        "calibration.death_correct_X 的 docstring 就地标注防后患。",
        "机理闭合（tools/probe_death_vs_at1.py 批27 疑点）: 全 10 黄金批 corr(delta,",
        "A_t1_late_med) = −0.589 — 批 27 改善最小(−3.3pt)正与其 late A_t1 最低(2994)",
        "一致; 批 80 最大(−23.9)配 late A_t1 3347 反向离群提示绝对 X 标度效应并存,",
        "已记录为后续多因素分析线索。",
    ],
    "evidence": {"artifacts": [
        "tools/trace_death_corr11.py", "tools/probe_death_vs_at1.py",
        "runs/hier_est/p4_death_vs_at1.json"]}
}
knowledge_entry = {
    "ts": ts,
    "event": "discovery",
    "level": "T7",
    "type": "model_knowledge",
    "content": (
        "建模符号约定陷阱: 同名变量可在『记录层』与『修正/公式层』承载相反约定"
        "(本案 A_t1 记录列≈分母/分子 vs 公式层=分子/分母, 差 4 个数量级) — 混合"
        "复用会静默把数十倍量纲误差注入滤波/修正。工程对策: 修正层显式重算并以",
        "就地 docstring 声明口径, 禁止直接读记录列。"
    ),
    "ref": "tools/trace_death_corr11.py + observe._death_corr docstring"
}
for path, entry in [(r"runs\ledger.jsonl", runs_entry), (r"knowledge\ledger.jsonl", knowledge_entry)]:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
print("ledgered:", ts)
