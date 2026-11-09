# -*- coding: utf-8 -*-
"""R120 账本：PAT 消融对照完成 + stdout 双包装修复。"""
import json
from datetime import datetime

ts = datetime.now().isoformat()
runs_entry = {
    "ts": ts,
    "run_id": "pat-ablation-r120",
    "stage": "PAT ablation (spec §3.5)",
    "result": [
        "PAT 消融对照完成（tools/pat_ablation.py, 批 60+22, n_ens=50）：",
        "  批 60: 引擎 PAA corr=0.97 → PAT 转发 corr=0.966 (Δ=-0.004);",
        "        I3 PAA 覆盖率 0.895; 触发器不触发 (μp=0.030<0.055)",
        "  批 22: 引擎 PAA corr=0.353 → PAT 转发 corr=0.345 (Δ=-0.008);",
        "        触发器触发 (μp=0.070>0.055), fused corr=0.808 (+0.455)",
        "  fidelity r≈0.9995 双批一致（与 R51 合成层验证口径一致）",
        "结论: PAT 转发通道对引擎 PAA 动态几乎无损; 触发批上 fused 锚定层",
        "  把反相关批的 corr 从 0.35 拉回 0.81——锚定修正层价值得到定量确认。",
        "附带修复: raman_pipeline.py / raman_pat_channel.py 双 stdout 包装 bug",
        "  （模块级 TextIOWrapper 二次包装 → GC 关闭底层缓冲区 → I/O closed）",
        "  → raman_pipeline 条件包装 + detach; raman_pat_channel 移除模块级包装。",
    ],
    "decision": "PAT 消融对照（spec §3.5）完成——转发口径近无损、fused 触发批改善显著。",
    "evidence": {"artifacts": [
        "runs/p3/pat_ablation.json",
        "tools/pat_ablation.py",
        "tools/raman_pipeline.py (stdout fix)",
        "tools/raman_pat_channel.py (stdout fix)"]},
}
knowledge_entry = {
    "ts": ts,
    "event": "note", "type": "process", "level": "T3",
    "content": (
        "PAT 消融定量结论: 转发通道近无损（Δcorr≤0.008, fidelity r≈0.9995）;",
        "触发批 fused 锚定把反相关批 corr 0.35→0.81。PAT 定位维持"
        "「忠实转发 + 条件锚定」。stdout 双包装教训: 库模块不得模块级包装 stdout。"
    ),
    "ref": "docs/raman_pat_integration_spec.md §3.5 + runs/p3/pat_ablation.json"
}
for path, entry in [(r"runs\ledger.jsonl", runs_entry), (r"knowledge\ledger.jsonl", knowledge_entry)]:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
print("ledgered ablation:", ts)
