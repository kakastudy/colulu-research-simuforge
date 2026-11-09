# -*- coding: utf-8 -*-
import json
import datetime

e = {'ts': datetime.datetime.now().isoformat(), 'run_id': 'PH2-death-term-verify', 'stage': 'PH2',
     'result': ('PASS（实施验证）：death-term 层并入集合平滑器（批 11，50 成员，全成功）；'
                'I3 X 覆盖率 43.8% → **62.5%**（+43% 相对提升）；P 93.8% / PAA 87.5% 不受影响（层只作用于 X 通道）；'
                'death-layer on (R²=0.6663, 621 点)。',
     ),
     'decision': ('v0.2 候选算子的双重证据链完成：(1) 拟合 R²=0.67（30 批）；'
                  '(2) 实施覆盖率提升（批 11）——待 v2 池 88 批全量复验后升版'),
     'evidence': {'artifacts': ['candidate/indpensim/v0.1/observe.py death-layer',
                                 'runs/hier_est/esmooth_11_v02.json',
                                 'runs/hier_est/death_term.json']}}
with open('runs/ledger.jsonl', 'a', encoding='utf-8') as f:
    f.write(json.dumps(e, ensure_ascii=False) + '\n')
print('ok')
