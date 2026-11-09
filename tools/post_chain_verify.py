# -*- coding: utf-8 -*-
"""P4 验收链后核对（池满 → watcher 自动链跑完后执行）。
核对: ph1e_fit → ph2_full_driver → p4_upgrade_driver → acceptance 草稿 四环产物完整性。
用法: python tools/post_chain_verify.py [--wait 轮询直到链完成]
"""
import io
import json
import os
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="gbk", errors="replace")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
HE = os.path.join(ROOT, "runs", "hier_est")


def load(name):
    p = os.path.join(HE, name)
    if os.path.exists(p):
        return json.load(open(p, encoding="utf-8"))
    return None


def fmt(v):
    return json.dumps(v, ensure_ascii=False)[:200]


def main():
    wait = "--wait" in sys.argv
    if wait:
        print("轮询等待验收链完成（watcher 串行: ph1e_fit → p4_driver → acceptance）...", flush=True)
        deadline = time.time() + 3600
        while time.time() < deadline:
            v = load("p4_upgrade_verdict.json")
            if v and v.get("verdict") in ("PASS", "HOLD") and "gates" in v:
                g = v.get("gates", {})
                if all(k in g for k in ("G1_pool", "G2_prior", "G3_A_t1", "G4_X_coverage", "G5_probe")):
                    break
            time.sleep(30)
        else:
            print("超时：验收链未在 1h 内完成", flush=True)
            sys.exit(2)

    checks = []
    ok_all = True

    # 环 1: ph1e_fit 产物
    prior = load("hier_prior_v2.json")
    if prior:
        n = prior.get("n_batches", "?")
        ok = n == 88
        checks.append(("ph1e_fit", f"hier_prior_v2.json n_batches={n}", ok))
    else:
        checks.append(("ph1e_fit", "hier_prior_v2.json 缺失", False))
        ok_all = False

    # 环 2: ph2_full_driver 产物
    full = load("residual_discovery_full.json")
    if full:
        div = full.get("diverged") or []
        at = full.get("A_t1") or {}
        ok = len(div) == 0 and full.get("n_effective") == 88
        checks.append(("ph2_full", f"n_effective={full.get('n_effective')} diverged={len(div)} "
                      f"A_t1(appears={at.get('appears')}, neg={at.get('neg')})", ok))
        if not ok:
            ok_all = False
    else:
        checks.append(("ph2_full", "residual_discovery_full.json 缺失", False))
        ok_all = False

    # 环 3: p4_upgrade_driver verdict
    verdict = load("p4_upgrade_verdict.json")
    if verdict:
        g = verdict.get("gates", {})
        g1 = g.get("G1_pool", {}).get("pass")
        g2 = g.get("G2_prior", {}).get("pass")
        g3 = g.get("G3_A_t1", {}).get("pass")
        g4 = g.get("G4_X_coverage", {}).get("pass")
        g5 = g.get("G5_probe", {}).get("pass")
        ok = verdict.get("verdict") == "PASS"
        checks.append(("p4_driver", f"verdict={verdict.get('verdict')} G1={g1} G2={g2} G3={g3} "
                      f"G4={g4} G5={g5}", ok))
        if not ok:
            ok_all = False
    else:
        checks.append(("p4_driver", "p4_upgrade_verdict.json 缺失", False))
        ok_all = False

    # 环 4: acceptance 草稿
    draft = os.path.join(ROOT, "docs", "ph2_acceptance_draft.md")
    if os.path.exists(draft):
        txt = open(draft, encoding="utf-8").read()
        ok = "PASS" in txt and "G4" in txt
        checks.append(("acceptance", f"ph2_acceptance_draft.md {len(txt)} chars, 含 PASS 段落", ok))
        if not ok:
            ok_all = False
    else:
        checks.append(("acceptance", "ph2_acceptance_draft.md 缺失（make_ph2_acceptance 未跑或失败）", False))
        ok_all = False

    print("=" * 70)
    print("P4 验收链后核对报告")
    print("=" * 70)
    for name, desc, ok in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {name:12s} {desc}")
    print("=" * 70)
    print("总体:", "全部 PASS ✅" if ok_all else "存在 FAIL ❌ —— 见上方明细")
    if ok_all and verdict and verdict.get("verdict") == "PASS":
        print("\n→ 下一步: D9 裁决（后验算子已定性完成）→ v0.2 激活执行化 → 用户可见验收报告")
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    main()
