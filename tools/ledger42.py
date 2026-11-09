# -*- coding: utf-8 -*-
"""追加里程碑：PH3 EnKF NaN 重采样债务清偿（R42-43）到双账本。"""
import json
from datetime import datetime

ts = datetime.now().isoformat()
runs_entry = {
    "ts": ts,
    "run_id": "PH3-nan-resample",
    "stage": "PH3-m2",
    "result": [
        "EnKF 成员级 NaN 自动重采样守卫落地（已登记的 PH3 债务）: integrate_interval 返回",
        "后加 np.isfinite 全向量门——NaN 走异常路径（FloatingPointError）→ 回均值邻域重采样,",
        "fail_count 计数升级为含 NaN 事件;isfinite 门保证 NaN 成员不过夜 → z_ens.mean(0)",
        "永不投毒（旧版 1.05/步 内爆 3e8 倍 + NaN 级联的真凶之一被封死在源头）。",
        "回归验证 PASS: 批 11 n_ens=20 轨迹健康（X 15.1→34.7@200h ±1.61→3.57、mup ",
        "0.0405→0.0388 收敛）;I3 P 93.75% / PAA 87.5% 与 n_ens=40 修复版一致;X 6.25%",
        "（n_ens 敏感性,已登记现象）。附带清理 enkf_observe 内重复的同化过滤死代码块。",
    ],
    "decision": "PH3-m2 EnKF 健壮性债务清偿完成;UKF 替代（原 D1 核心遗留）按拍板选项 (a) V1+ 维持登记。",
    "evidence": {
        "artifacts": [
            "candidate/indpensim/v0.1/observe.py (enkf_observe isfinite 门)",
            "runs/hier_est/enkf_11_resample.json",
        ]
    },
}
knowledge_entry = {
    "ts": ts,
    "event": "note",
    "type": "asset",
    "level": "T3",
    "content": (
        "数值反直觉经验（工程知识）: solve_ivp/BDF 出 NaN 时通常不抛异常而是静默返回,",
        "滤波器必须显式 isfinite 门控,异常捕获不足以防止集合均值投毒——对应 V3 工程中"
        "CRITICAL 仪表静默漂移的『数据不报错但已失真』同构现象。"
    ),
}
for path, entry in [(r"runs\ledger.jsonl", runs_entry), (r"knowledge\ledger.jsonl", knowledge_entry)]:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
print("ledgered:", ts)
