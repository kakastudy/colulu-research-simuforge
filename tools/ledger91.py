# -*- coding: utf-8 -*-
"""扩展条目：PAA 保真差异的机理锚点 = μp 校准值（R91）。"""
import json
from datetime import datetime

ts = datetime.now().isoformat()
runs_entry = {
    "ts": ts,
    "run_id": "paa-fidelity-mechanism",
    "stage": "P3",
    "result": [
        "PAA 批间保真差异的**机理锚点**: corr(保真 r, 校准 μp) = **−0.891**（9 健全批）",
        "—— 高 μp 校准批（22/23 用 0.070）完全吻合反相（−0.345/−0.614），低 μp 批",
        "（36 0.041 / 60 0.030）近完美（+0.987/+0.998）。μp=PAA 消耗速率耦合 → 反相是",
        "参数-结构级因果（高 PAA 吸收批的引擎 PAA 状态动力学失真），非巧合/软测量噪声。",
        "m_s (−0.468) 与 μx (+0.476) 是次级关联; dtcin 几乎中性（−0.111）。",
        "工程含义: PAA 通道条件性修正的触发器可用校准 μp 阈值（如 μp>0.055）而非",
        "事后逐批检 r —— 预测式触发（校准阶段已知）→ 无需额外化验轮次。",
    ],
    "evidence": {"artifacts": [
        "runs/hier_est/paa_fidelity_census.json", "calibration.CAL", "R90 批普查"]}
}
knowledge_entry = dict(runs_entry)
knowledge_entry.pop("run_id", None)
knowledge_entry.update({
    "event": "discovery", "level": "T7", "type": "model_knowledge",
    "content": (
        "生物 PAA 代谢机理: 引擎 PAA 状态失真的驱动力是 μp（青霉素合成速率）校准值的"
        "大小 — μp 高 = PAA 被快速吸收。ferment 在高吸收 regime 下, PAA 前体库的"
        "供给（Fpaa 进料, 由 V3 配方固定）与消耗速率失衡放大 → 状态偏差呈反相关形状。"
        "这是『参数级结构误差表现为特征级反相关』的又一实例（与『模塑/观测假象』"
        "两类分开——前者需要机理增补, 后者只需滤波修正）。"
    ),
    "ref": "runs/hier_est/paa_fidelity_census.json + calibration.CAL"
})
for path, entry in [(r"runs\ledger.jsonl", runs_entry), (r"knowledge\ledger.jsonl", knowledge_entry)]:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
print("ledgered:", ts)
