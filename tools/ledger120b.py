# -*- coding: utf-8 -*-
"""R120 激活账本：PH2/P4 v0.2 五闸 PASS + D9(a) 方案激活。"""
import json
from datetime import datetime

ts = datetime.now().isoformat()
runs_entry = {
    "ts": ts,
    "run_id": "ph2-p4-activation",
    "stage": "PH2/P4 v0.2",
    "result": [
        "P4 验收链 verdict=PASS（p4_upgrade_verdict.json）：",
        "  G1 池 88/88 零 tombstone；G2 hier_prior_v2.json（88 批, mux μ̂=0.4084,",
        "  mup μ̂=0.0414, m_s μ̂=0.0254）；G3 β 拟合 R²=0.666/n=621/β 三系数；",
        "  G4 覆盖率 0.625/0.789/0.474 均值 0.629≥0.60；G5 探针 10/10 改善。",
        "激活执行（d9_activation_checklist.md §2）：",
        "  [x] observe.ensemble_smooth death_term=True 默认（已确认）",
        "  [x] calibration.load_death_beta 运行时读 death_term.json（已确认）",
        "  [x] v0.1 calib_params 路径零改动（已确认）",
        "  [x] 黄金回归守护重跑（diag_final_validation_v2.py）：RMSE 4.48%/灾难 0/12/",
        "      within5% 9/12——与基线逐字一致，激活零回归确认（批 8 +1.5%/11 +0.3%/",
        "      16 +4.3%/22 +7.7%/23 -0.4% benign/27 -0.2%/36 -6.4%/55 -2.6%/60 -9.2%/",
        "      80 +3.0%/91 +4.5%/92 -0.6%，故障批 pH_end=3.00 复现）",
        "  [x] G4 重跑（三批 ensemble_smooth 30 成员, 产物 esmooth_*_p4gate.json）",
        "  [x] ENGINE_CONTRACT.md v1.2 增补（头部 + 条目 + 版本表）",
        "  [x] 验收草稿 + 用户可见报告重生成",
        "  [x] 双账本激活条目（本条）",
        "链上修复: ph1e_fit.py dst 路径 dirname 层级 bug（R120 修）; p4_upgrade_driver",
        "  hard 裁决补 G2 闸 + G3 docstring 对齐 R76 语义。",
        "时序记录: 首轮链 ph1e_fit 崩溃 → G2 时序误判 HOLD → 手动补跑 + 重跑驱动 → PASS。",
        "遗留: DL σ̂=0（网格后验波兰, PH3+ 非网格后验债务）; D9(b) ODE 级积分未实施",
        "  （产量级 RMSE ≤3.5% 需机理增强项挂 V1+）; PAT 消融对照（spec §3.5, 脚本就绪）",
        "  待验收链后执行; 黄金集扩展（D7 待用户）; PAA 批间异质（批 22/23 反相）。",
    ],
    "decision": "PH2/P4 v0.2 死亡项修正层激活（D9 方案 a: 后验算子, 引擎 ODE 零改动）。",
    "evidence": {"artifacts": [
        "runs/hier_est/p4_upgrade_verdict.json (verdict=PASS)",
        "runs/hier_est/hier_prior_v2.json",
        "runs/hier_est/residual_discovery_full.json (88 批, diverged=0)",
        "runs/hier_est/death_term.json",
        "runs/hier_est/p4_death_probe.json (10/10)",
        "ENGINE_CONTRACT.md (v1.2)",
        "docs/ph2_acceptance_report.md",
        "tools/diag_final_validation_v2.py (黄金守护)"]},
}
knowledge_entry = {
    "ts": ts,
    "event": "note", "type": "process", "level": "T3",
    "content": (
        "D9 裁决落地: 方案 a（后验算子）激活——死亡项修正层在观测/校准层生效,",
        "引擎 ODE 零改动, 黄金回归 4.48%/0/12/9 守护。G4 覆盖率 0.629 达标。",
        "产量级 RMSE ≤3.5% 目标明确挂 V1+ 机理增强（D9-b 不实施）。"
        "DL σ̂=0 债务（网格后验波兰）挂 PH3+。"
    ),
    "ref": "docs/d9_activation_checklist.md + ENGINE_CONTRACT.md v1.2"
}
for path, entry in [(r"runs\ledger.jsonl", runs_entry), (r"knowledge\ledger.jsonl", knowledge_entry)]:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
print("ledgered activation:", ts)
