# -*- coding: utf-8 -*-
"""追加里程碑：P4 死亡项引擎层升级前探针 + v0.2 算子注册（R44）到双账本。"""
import json
from datetime import datetime

ts = datetime.now().isoformat()
runs_entry = {
    "ts": ts,
    "run_id": "P4-death-probe-v02-operator",
    "stage": "P4",
    "result": [
        "升级前探针（tools/p4_death_probe.py）: 死亡项后验修正（X − f(kd, A_t1)）套入",
        "确定性重放（4h 滞后对齐同口径）→ **10/10 正常黄金批 X nRMSE 全部改善**:",
        "批11 -14.1pt (22.6→8.5%) 批16 -22.0 批22 -15.4 批23 -15.3 批27 -3.3 批36 -20.5",
        "批55 -11.1 批60 -18.9 (24.8→5.9%, corr 0.942→0.989) 批80 -23.9 → 支持引擎层",
        "v0.2 升级（原限『观测层专用』的前提被证据推翻）。",
        "v0.2 算子已注册 calibration.py（增量式，'只增不减'）: load_death_beta() +",
        "death_correct_X(sim_df)（默认关闭;β 运行时读 runs/hier_est/death_term.json,",
        "88 批全池重拟合后零代码改动）。等价性测试 PASS: 与 observe._death_corr",
        "max diff = 0.00（批60 X_end 27.70→19.75）。",
    ],
    "decision": "PH2 全池 A_t1 一致性验收（≥60% 负向）通过后再启用引擎层挂接（先观测层,后验证器）。",
    "evidence": {
        "artifacts": [
            "runs/hier_est/p4_death_probe.json",
            "candidate/indpensim/v0.1/calibration.py (load_death_beta/death_correct_X)",
            "tools/test_v02_operator.py",
        ]
    },
}
knowledge_entry = {
    "ts": ts,
    "event": "discovery",
    "level": "T7",
    "type": "model_knowledge",
    "content": (
        "青霉素发酵菌丝衰亡结构项的批间普适性定量证据: 形如 X·f(培养龄比 A_t1) 的"
        "衰亡算子（kd1·X + kd2·X·A_t1 + kd3·X·A_t1², β 由 30 批微分残差拟合 R²=0.67）"
        "在 10/10 独立黄金批上系统性改善 X 轨迹拟合（nRMSE 中位改善 -15.3pt）——"
        "支持 Pirt-maintenance/细胞老化理论中『年龄结构化衰亡』是 V3 缺失的主导机制"
        "（对照已登记共识: 记忆失活项 + D1 维持系数为常数）。批27 改善最小(-3.3pt)"
        "与其 m_s 调度批次特性一致（ Palestine 晚期模式差异,登记）。"
    ),
    "ref": "runs/hier_est/p4_death_probe.json + Pirt 1990 (10.1016/0922-338x(90)90224-k) + Goma 1979",
}
for path, entry in [(r"runs\ledger.jsonl", runs_entry), (r"knowledge\ledger.jsonl", knowledge_entry)]:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
print("ledgered:", ts)
