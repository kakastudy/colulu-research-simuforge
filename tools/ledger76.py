# -*- coding: utf-8 -*-
"""追加发现：A_t1 判据三重口径揭示 + G3 语义修正（R73-76）到双账本。"""
import json
from datetime import datetime

ts = datetime.now().isoformat()
runs_entry = {
    "ts": ts,
    "run_id": "at1-gate-semantics",
    "stage": "P4",
    "result": [
        "A_t1 一致性判据的**三重口径揭示**（R73-76）:",
        "① 记录列口径（伪特征）: _features 原用 sim[A_t1] 记录列（60→4500 陡峭上行, 与",
        "晚期 dres 斜率机械相关）→ 85 有效批命中 85 站, neg 56.5% — 命中是形状 artifact;",
        "② 公式层口径（物理）: 修复 _features 重算 a0/(a1+a3+a4) 后全池重投票 → A_t1",
        "best-subset 仅命中 **12 站 / 42% 负向**（87 有效批）— 导数空间信号弱;",
        "③ 公式层水平空间（权威）: death_term.json β 拟合（R²=0.67, 621 点全 X 通道）",
        "已被 10/10 黄金批探针 + 覆盖层收益双重验证。",
        "**G3 语义修正落地**: p4_upgrade_driver G3 判据改为→death_term.json（R²≥0.5 且",
        "n≥400 且 beta 三系数）; 残差投票降为辅助披露。修正原理: 判据应与启用依据",
        "（β 拟合）同口径, 而非与形状 artifact（记录列）同口径。",
        "附带: midvote55.py 两轮聚合器 bug（coefs→beta 字段名、截断样本）修正史完整保留。",
    ],
    "decision": "G3 修正后: PASS 依据 = death_term.json 现值（R²=.67, 621 点, β=(81.7,-293.7,158.6)）。",
    "evidence": {"artifacts": [
        "runs/hier_est/residual_discovery_mid55.json（公式层终版）",
        "candidate/indpensim/v0.1/residual_discovery.py (_features 公式化修复)",
        "tools/p4_upgrade_driver.py (G3 语义修正, syntax OK)"]}
}
knowledge_entry = {
    "ts": ts,
    "event": "discovery",
    "level": "T7",
    "type": "model_knowledge",
    "content": (
        "结构发现方法论（第三重口径）: 同一『缺失项一致性』问题在三个空间有不同答案"
        "— (1)导数空间 SINDy 子集命中: 携带特征形状 artifact 且依赖子集搜索;",
        "(2)水平空间线性 β 拟合: 对『该机制的水平层贡献』最直接的量度;",
        "(3)下游覆盖率收益: 机制的实用层验证。判据设计应放在『启用依据所在的空间』;"
        "跨空间阈值直接移植是把口径 artifact 合法化的经典错误（本案记录列口径 63%→"
        "56.5% 的高速摇摆即为揭示信号）。"
    ),
    "ref": "runs/hier_est/residual_discovery_mid55.json + death_term.json"
}
for path, entry in [(r"runs\ledger.jsonl", runs_entry), (r"knowledge\ledger.jsonl", knowledge_entry)]:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
print("ledgered:", ts)
