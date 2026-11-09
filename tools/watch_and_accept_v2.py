# -*- coding: utf-8 -*-
"""v2 池完成监视器：轮询 train_theta_v2.jsonl 到 88/88 后自动串行执行
ph1e_fit.py（构建 hier_prior_v2.json）→ p4_upgrade_driver.py（G1–G5 验收链，
内嵌 ph2_full_driver.py 全池残差发现），产物与判决落盘，日志逐行 flush。
"""
import io
import os
import subprocess
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="gbk", errors="replace")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
HE = os.path.join(ROOT, "runs", "hier_est")
POOL = os.path.join(HE, "train_theta_v2.jsonl")
PYC = r"C:\Python314\python.exe"


def _n():
    return sum(1 for _ in open(POOL, encoding="utf-8")) if os.path.exists(POOL) else 0


while True:
    n = _n()
    if n >= 88:
        break
    print("[watcher] pool %d/88 at %s — sleeping 120s" % (n, time.strftime("%H:%M:%S")), flush=True)
    time.sleep(120)

print("[watcher] POOL COMPLETE %d/88 -> ph1e_fit" % _n(), flush=True)
r1 = subprocess.run([PYC, os.path.join(ROOT, "tools", "ph1e_fit.py")], cwd=ROOT)
print("[watcher] ph1e_fit exit=%d" % r1.returncode, flush=True)

print("[watcher] -> p4_upgrade_driver (G1-G5, 内嵌 ph2_full_driver)", flush=True)
r2 = subprocess.run([PYC, os.path.join(ROOT, "tools", "p4_upgrade_driver.py")], cwd=ROOT)
print("[watcher] p4_upgrade_driver exit=%d" % r2.returncode, flush=True)

print("[watcher] -> make_ph2_acceptance (验收草稿自动生成)", flush=True)
r3 = subprocess.run([PYC, os.path.join(ROOT, "tools", "make_ph2_acceptance.py")], cwd=ROOT)
print("[watcher] make_ph2_acceptance exit=%d" % r3.returncode, flush=True)

print("[watcher] -> make_ph2_acceptance_report (用户可见报告)", flush=True)
r4 = subprocess.run([PYC, os.path.join(ROOT, "tools", "make_ph2_acceptance_report.py")], cwd=ROOT)
print("[watcher] make_ph2_acceptance_report exit=%d" % r4.returncode, flush=True)

vp = os.path.join(HE, "p4_upgrade_verdict.json")
print("[watcher] verdict file: %s" % vp, flush=True)
print("[watcher] DONE", flush=True)
