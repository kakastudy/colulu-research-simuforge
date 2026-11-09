# -*- coding: utf-8 -*-
import json
import datetime

e = {'ts': datetime.datetime.now().isoformat(), 'run_id': 'PH3-m2-enkf-fixed', 'stage': 'PH3',
     'hypothesis': '定位 EnKF NaN 假象的根因',
     'result': ('根因审计：phys_clamp 通用 g/L 下限 1e-3 误伤 pH_H 状态（[H+] 尺度 1e-7，'
                '被钳到 1e-3 = pH 3.0 不可能态：生长停摆，S 堆 88 g/L，X 死 3.9）。'
                '同时修正 Q 观测单位错配（引擎 kJ/h vs V3 列已 /1000）与集合膨胀复利'
                '（1.05/步 → 3e8 倍爆散；改 1.0005/步 ≈ 全批 1.93×）。'),
     'outcome': ('修后：X 15→34.7 健康追踪；P 覆盖率 100%；PAA 75%；X 12.5% 与已登记'
                 '死亡动力学缺口同源（量化支持 PH2 主路径）'),
     'evidence': {'artifacts': ['candidate/indpensim/v0.1/observe.py',
                                 'tools/enkf_bisect.py', 'tools/dbg_do2_trace.py'],
                  'note': '成员级 BDF 失败重采样（I2）+ 观测定位/物理钳位/集合膨胀三件套纳入 PH3 正式实现'}}
with open('runs/ledger.jsonl', 'a', encoding='utf-8') as f:
    f.write(json.dumps(e, ensure_ascii=False) + '\n')
print('ok')
