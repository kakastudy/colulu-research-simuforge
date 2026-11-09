# -*- coding: utf-8 -*-
"""追加里程碑：T1 窗口包络采样（R49）到双账本。"""
import json
from datetime import datetime

ts = datetime.now().isoformat()
runs_entry = {
    "ts": ts,
    "run_id": "PH4-t1-window-envelope",
    "stage": "PH4",
    "result": [
        "advise_control 的 T1 校验采样升级: 末态瞬时(全批尾,含未来 ~240h) → **咨询窗口包络**",
        "(best 候选自身轨迹, 窗内 [t0,t1) 裁剪: T=max pH=最违反端 CO2d=max DO2=min; t1_sample",
        "随输出回传作证据)。因此正确 scoped: 批 8 窗 60-120h 判定现在只看窗内证据",
        "(DO2 min=10.9 → 仅 DO2 告警, 而非旧版把 ~240h 末态 DO2=6.9/T=303.5 混入 advisory)。",
        "进程内 + HTTP 双双回归 PASS (11 工具); 服务 8931 已重启加载。",
    ],
    "decision": "T1 判定域=咨询域(滚动控制一致性原则); 全批末态判定保留在 classify_crash 侧。",
    "evidence": {"artifacts": [
        "candidate/indpensim/v0.1/mcp_server.py (advise_control envelope-sampler)",
        "tools/test_advise_control.py", "tools/test_mcp_http_11.py", "job pwsh-665"]}
}
knowledge_entry = {
    "ts": ts,
    "event": "note",
    "type": "asset",
    "level": "T3",
    "content": (
        "控制知识原则: 操作窗约束判定的时间域必须与控制建议的时间域一致(滚动窗内),",
        "否则把批末惯性态混进当窗建议会造成误警/漏警双向偏差 — 物理上对应 HAZOP "
        "envelope 评估(取窗内最违反包络) 而非 end-point 抽查。"
    ),
}
for path, entry in [(r"runs\ledger.jsonl", runs_entry), (r"knowledge\ledger.jsonl", knowledge_entry)]:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
print("ledgered:", ts)
