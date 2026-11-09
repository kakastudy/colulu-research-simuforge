# -*- coding: utf-8 -*-
"""修正条目：批 22 PAA 相关数从截断子样本校正至全样本（R54）。"""
import json
from datetime import datetime

ts = datetime.now().isoformat()
runs_entry = {
    "ts": ts,
    "run_id": "PAA-channel-facts-CORRECTION",
    "stage": "P3",
    "result": [
        "修正 R53 批 22 引擎 PAA vs 化验相关数: −0.50 → **−0.34（n=19 全样本, lag0, 标度",
        "median 0.9x）**。原因: diag_paa_align80.py 当时 pts 切了 [:12] 截断子样本",
        "（结论方向不变 — 反相关/通道保真缺口,但幅值降低）。正式指标已入 trajectory_metrics",
        "（nRMSE 64.7%@|corr|最优 lag; 批80 退化守卫生效 — sigma_over_mu=0.0028 正确标为",
        "degenerate 并从 nRMSE 打印缺席）*验证 runs/trajectory_metrics_paa_check.json*。",
    ],
    "evidence": {"artifacts": [
        "candidate/indpensim/v0.1/trajectory_metrics.py (PAA_offline 段)",
        "runs/trajectory_metrics_paa_check.json"]}
}
for path in (r"runs\ledger.jsonl", r"knowledge\ledger.jsonl"):
    entry = dict(runs_entry) if "runs" in path else {
        "ts": ts, "event": "note", "type": "asset", "level": "T2",
        "content": ("指标化纪律: 子样本截断的临时诊断数不进正式结论 — R53 登记的 r=−0.50 为",
                    "12 点截断口径, R54 全样本 r=−0.34 为准; 两者都保留可追溯。"),
        "ref": "runs/ledger.jsonl PAA-channel-facts"}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
print("ledgered:", ts)
