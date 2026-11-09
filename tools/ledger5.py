# -*- coding: utf-8 -*-
import json
import datetime

e = {'ts': datetime.datetime.now().isoformat(), 'run_id': 'PH3-m2-batch8-verify', 'stage': 'PH3',
     'hypothesis': 'EnKF 修复跨批有效性验证（批 8 对照）',
     'result': ('X 14.5→32.4 健康追踪；I3 覆盖率 X 36.8% / P 78.9% / PAA 63.2%（19 点）；'
                '出现成员级 NaN 但被重采样吸收（fail 计数可见）——稳健性 P4 精调保留'),
     'evidence': {'artifacts': ['candidate/indpensim/v0.1/observe.py',
                                 'runs/hier_est/enkf_08.json']}}
with open('runs/ledger.jsonl', 'a', encoding='utf-8') as f:
    f.write(json.dumps(e, ensure_ascii=False) + '\n')
print('ok')
