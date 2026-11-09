# -*- coding: utf-8 -*-
"""R121 账本：PAA 批间异质机理探查——时序错位根因。"""
import json
from datetime import datetime

ts = datetime.now().isoformat()
runs_entry = {
    "ts": ts,
    "run_id": "paa-heterogeneity-mechanism",
    "stage": "V1+ 机理探查",
    "result": [
        "PAA 批间异质机理探查（tools/paa_heterogeneity_probe.py + paa_shape_probe.py）：",
        "  关键发现 1: P 通道在所有批次健康（corr 0.97-0.998）——PAA 反相",
        "    不是 P 通道误差传导, 是 PAA 方程本身的结构误差。",
        "  关键发现 2: 反相批的 PAA 时序严重错位——引擎峰值早于化验峰值 144-180h:",
        "    批 22 (μp=0.070): sim_peak@60h vs lab_peak@204h, lag=-144h, corr=-0.231",
        "    批 23 (μp=0.070): sim_peak@24h vs lab_peak@204h, lag=-180h, corr=-0.538",
        "    批 36 (μp=0.041): sim_peak@230h vs lab_peak@230h, lag=0h, corr=+0.984 ✅",
        "    批 60 (μp=0.030): sim_peak@230h vs lab_peak@230h, lag=0h, corr=+0.998 ✅",
        "  关键发现 3: 引擎在高 μp 批系统性低估 PAA 幅值（批 22: sim 1019 vs lab 1495;",
        "    批 23: sim 464 vs lab 1257; 批 60: sim 2213 vs lab 2198 几乎匹配）。",
        "  机理解读: PAA 生产项 Y_PAA_P*dP/dt + Y_PAA_X*X 正比于前体消耗速率和生物量,",
        "    在高 μp 下生物量早期快速生长时这些项过早触发 → PAA 生产相提前开启。",
        "    这是相门控（phase-gating）结构缺失——PAA 生产应被限制在生产相而非生长期。",
        "  假设 H1-H4 检验: H1（时序错位）确认——peak_lag_h 在高 μp 批达 -144/-180h,",
        "    低 μp 批为 0h。H2（幅值偏差）部分确认——高 μp 系统性低估。",
        "    H3/H4 待轨迹形状细查。",
    ],
    "decision": (
        "PAA 批间异质根因 = 时序错位（生产相过早开启）, 非幅值偏差为主。"
        "修正方向: PAA 方程增加相门控项（生产相抑制函数）, 属 D9(b) ODE 级"
        "机理增强, 挂 V1+。与 D9(a) 后验算子（已激活）互补——(a) 修观测层, "
        "(b) 修结构层。"
    ),
    "evidence": {"artifacts": [
        "runs/p3/paa_heterogeneity_probe.json",
        "runs/p3/paa_shape_probe.json",
        "tools/paa_heterogeneity_probe.py",
        "tools/paa_shape_probe.py"]},
}
knowledge_entry = {
    "ts": ts,
    "event": "note", "type": "process", "level": "T3",
    "content": (
        "PAA 批间异质根因确认: 时序错位（生产相过早开启）, 高 μp 批引擎 PAA 峰值"
        "早于化验 144-180h。P 通道健康（排除前体传导）。修正方向: PAA 方程"
        "增加相门控项（生产相抑制函数）——D9(b) ODE 级机理增强, V1+。"
        "与已激活的 D9(a) 后验算子互补。"
    ),
    "ref": "runs/p3/paa_shape_probe.json + docs/deepening_plan.md §8"
}
for path, entry in [(r"runs\ledger.jsonl", runs_entry), (r"knowledge\ledger.jsonl", knowledge_entry)]:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
print("ledgered:", ts)
