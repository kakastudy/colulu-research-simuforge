# -*- coding: utf-8 -*-
"""追加里程碑：advise_control 服务层工具落地（11 工具）到双账本。"""
import json
from datetime import datetime

ts = datetime.now().isoformat()

runs_entry = {
    "ts": ts,
    "run_id": "PH4-advise-control",
    "stage": "PH4",
    "result": [
        "advise_control MCP 工具落地（第 11 个工具，VERSION v0.1.0-c4）：时间窗 [t0,t1) MV 倍率",
        "反事实重放（复用引擎 mv_window_scales）→ 逐候选 yield_g/err_vs_v3/crash 分级 +",
        "|yield−target| 选 best + validate_t1 物理操作窗校验。E2E PASS：批 8 窗 60-120h、",
        "3 候选全成功仿真（Fs×1.0/1.03/0.97，err +1.5%/+1.9%/+1.1%，全 normal）、best",
        "Fs×0.97（gap +1.1%）；T1 校验如预期触发边界告警（T=303.5K 上沿、DO2=6.9",
        "< X_crit_DO2=15，批 8 末态贴边 = 真实约束活性证据）。",
        "trajectory_check def 行在插入时被误覆盖 → 已恢复并经 fastmcp.list_tools 复验 11 工具齐。",
    ],
    "decision": "契约升级 ENGINE_CONTRACT.md v1.0→v1.1（10→11 工具）；MCP 服务 8931 重启加载新版本。",
    "evidence": {
        "artifacts": [
            "candidate/indpensim/v0.1/mcp_server.py (advise_control)",
            "ENGINE_CONTRACT.md v1.1",
            "tools/test_advise_control.py",
            "tools/list_mcp_tools.py",
        ]
    },
}
knowledge_entry = {
    "ts": ts,
    "event": "note",
    "type": "asset",
    "level": "T3",
    "content": (
        "控制求解器服务面闭环：PH4 的『反事实重放 + T1 约束校验』从离线演示"
        "（tools/advise_control_demo.py）升级为 Agent 可调用 MCP 工具 advise_control；"
        "微生物动力学（A_t1 培养龄比）/化学反应平衡（pH_H）/物理（T、DO2 传氧）三层知识"
        "作为约束层内嵌于建议评分末级（validate_t1）。"
    ),
    "ref": "ENGINE_CONTRACT.md §2 advise_control + knowledge_constraints.validate_t1",
}
for path, entry in [
    (r"runs\ledger.jsonl", runs_entry),
    (r"knowledge\ledger.jsonl", knowledge_entry),
]:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
print("ledgeredruns:", ts)
