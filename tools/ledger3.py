# -*- coding: utf-8 -*-
import json
import datetime

e = {'ts': datetime.datetime.now().isoformat(), 'run_id': 'PH1-v2-stall-note', 'stage': 'PH1',
     'hypothesis': 'v2 全池积分耗时诊断',
     'result': ('进程满核；近崩边界组合（μp jitter 近 0.048 边缘）单组合 30+ min 病理积分；'
                '总时长不确定（估计 10-15 h），断点续跑可承受'),
     'evidence': {'log': 'runs/hier_est/train_theta_v2.jsonl',
                   'loss_list': [0.174, 0.14, 0.191, 0.097, 0.176, 0.162, 0.186],
                   'best_loss': '0.097（批4，全池最优）'}}
with open('runs/ledger.jsonl', 'a', encoding='utf-8') as f:
    f.write(json.dumps(e, ensure_ascii=False) + '\n')
print('ok')
