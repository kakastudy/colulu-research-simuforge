# -*- coding: utf-8 -*-
import json
r = json.load(open('runs/trajectory_metrics.json', encoding='utf-8'))
print(f"{'batch':>6s} {'S_max%':>7s} {'P_max%':>7s} {'DO2%':>6s} {'X%':>6s} {'pH%':>6s} {'T%':>5s} {'OUR%':>6s}")
for row in r:
    m = row['metrics']
    def g(k):
        v = m.get(k, {})
        return round(v.get('nrmse_max_pct', float('nan')), 1)
    print(f"{row['batch']:>6d} {g('S'):>7} {g('P'):>7} {g('DO2'):>6} {g('X_offline'):>6} {g('pH'):>6} {g('T'):>5} {g('OUR'):>6}")
