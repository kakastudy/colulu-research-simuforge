# -*- coding: utf-8 -*-
import json
import datetime

entries = [
 {'ts': datetime.datetime.now().isoformat(), 'run_id': 'PH2-death-term-fit', 'stage': 'PH2',
  'result': ('PASS（首个数值级验证）：30 批 × 621 化验点；X 残差 σ 4.616 → 2.667 '
             '（R²=0.67）；kd2·X·A_t1 = −293.7（主导负项=促衰亡方向）、kd1·X=+81.7、'
             'kd3·X·A_t1²=+158.6（高次校正）。'),
  'decision': ('P4 版本化流程启动：death-term 作为 v0.2 候选算子'
               '（calibration.py 增量；v0.1 保留回退）；88 批全量复验后正式升版'),
  'evidence': {'artifacts': ['tools/fit_death_term.py',
                              'runs/hier_est/death_term.json']}},
 {'ts': datetime.datetime.now().isoformat(), 'event': 'discovery', 'level': 'T7',
  'type': 'model_knowledge',
  'content': ('死亡动力学项的定量形式（批级 X 修正）：resid = 0.82·X − 2.94·X·A_t1 '
              '+ 1.59·X·A_t1²（Akaike-approved 形式：以「培养年龄比 A_t1=a0/(a1+a3+a4)」'
              '调制的衰亡项）——与 Pirt-maintenance 理论和 V3 批 23 X 衰减证据三重同向。'),
  'ref': 'runs/hier_est/death_term.json + knowledge_constraints.ph2_candidates'},
]
with open('runs/ledger.jsonl', 'a', encoding='utf-8') as f:
    for e in entries:
        f.write(json.dumps(e, ensure_ascii=False) + '\n')
print('2 entries ok')
