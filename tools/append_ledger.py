# -*- coding: utf-8 -*-
import json, datetime
entries = [
  {'run_id': 'SEC43-A1-mechanism-closure', 'stage': 'M4', 'hypothesis': '碳账以呼吸归认口径可批级闭合',
   'result': 'PASS（归认披露）', 'decision': 'A1 选项1 采纳',
   'evidence': {'artifacts': ['candidate/indpensim/v0.1/mechanism_cclosure.py', 'runs/mechanism_c_closure.json'],
   'metrics': 'resp_share +56%~+66%（12批一致）；V3/引擎气体C份额 ~0.15t/批，比液相账低~30倍→气体单位不可调和，溯源待原文'}},
  {'run_id': 'B-stage2-final', 'stage': 'M2/L2', 'result': 'PASS（5/5 救回）', 'decision': 'mup 可辨识性已解决',
   'evidence': {'artifacts': ['runs/b80_92_rescue_scan.json', 'runs/b92_pinpoint.json'],
   'metrics': '80 +4.1%；92 mup=0.0322 → +0.17%（p_fit 2.41）；批92 每0.001 mup ≈ 60% 产率摆动'}},
  {'run_id': 'MV-validity-guard', 'stage': 'C档', 'result': '已落地', 'decision': 'A3 采纳',
   'evidence': {'artifacts': ['candidate/indpensim/v0.1/simulate.py'],
   'detail': 'mv_scales 越域告警 sim.attrs mv_warnings，验证域 [0.90, 1.25]'}},
  {'run_id': 'user-signoff', 'stage': 'S0/S8', 'result': '2026-10-27 用户裁决',
   'decision': 'A1 选项1 / A2 正式采纳 / A3 C档批准 / A4 网格精细路线',
   'evidence': {'instruction': '根据你的建议来，继续'}},
]
with open('runs/ledger.jsonl', 'a', encoding='utf-8') as f:
    for e in entries:
        e.setdefault('ts', datetime.datetime.now().isoformat())
        f.write(json.dumps(e, ensure_ascii=False) + '\n')
print('appended', len(entries))
