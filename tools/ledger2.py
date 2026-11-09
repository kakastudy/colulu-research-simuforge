# -*- coding: utf-8 -*-
import json
import datetime

entries = [
 {'ts': datetime.datetime.now().isoformat(), 'run_id': 'T2-maintenance-lit', 'level': 'T2',
  'event': 'note', 'type': 'asset',
  'content': ('领域文献补充（维持系数时变性领域锚点）：Goma/Moletta/Novak, '
              'Comments on the maintenance coefficient changes during alcohol fermentation, '
              'Biotechnology Letters, 1979, 10.1007/bf01388078（支持"维持系数随时间变化"的'
              '领域证据 → PH2 候选库 m_s(t) 项文献级来源）'),
  'ref': 'Crossref'},
 {'ts': datetime.datetime.now().isoformat(), 'run_id': 'PH1-runstore-dedup-fix', 'stage': 'PH1',
  'event': 'fix',
  'content': ('潜伏 bug 修复：run_pool 的断点去重原从 v1 日志固定路径读（续跑 v2 池会'
              '误判已完成后全程跳过）；改为按 out_log 去重 + observe.ensemble_smooth '
              '优先 v2 池（细 μp 分辨）'),
  'evidence': {'artifacts': ['candidate/indpensim/v0.1/hier_est.py',
                              'candidate/indpensim/v0.1/observe.py']}},
]
with open('runs/ledger.jsonl', 'a', encoding='utf-8') as f:
    for e in entries:
        f.write(json.dumps(e, ensure_ascii=False) + '\n')
print('ok 2 entries')
