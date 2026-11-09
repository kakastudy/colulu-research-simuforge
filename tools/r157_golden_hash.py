# -*- coding: utf-8 -*-
"""R157 / T1-8：黄金集 hash 快照 —— 把"只增不减"从约定变成机器可验的凭证。

背景
----
GOAL.md 的红线之一是"黄金集只增不减"。但 `data/processed/golden_set.json` 只是
一份**名单**（10 个 normal + 2 个 fault 批号），而 100 批的实测 CSV 在
`data/processed/batches/batch_XX.csv`。只要有人改动/替换其中任何一个 CSV，
"只增不减"在事后**无法证明**——没有任何凭证记录它们本来的字节。

本工具生成 `data/processed/golden_set.sha256`：
  - `batches/` 下 100 个 batch_XX.csv 的逐文件 sha256（+ 字节数）
  - `golden_set.json` 自身的 sha256
  - 名单快照（normal/fault 批号），使"名单被扩/被缩"也可检出

用法
----
    python tools/r157_golden_hash.py --write     # 生成/刷新快照（会覆盖，写入前报差异）
    python tools/r157_golden_hash.py --check     # 只校验；不一致则 exit 1 并列出差异
    python tools/r157_golden_hash.py --check --verbose
"""
import argparse
import hashlib
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
PROC = os.path.join(ROOT, "data", "processed")
BATCH_DIR = os.path.join(PROC, "batches")
SNAPSHOT = os.path.join(PROC, "golden_set.sha256")
MANIFEST = os.path.join(PROC, "golden_set.json")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def collect():
    """收集当前磁盘状态：{relpath: (sha256, size)}。"""
    out = {}
    names = sorted(n for n in os.listdir(BATCH_DIR) if n.endswith(".csv"))
    for n in names:
        p = os.path.join(BATCH_DIR, n)
        out[f"batches/{n}"] = (sha256_file(p), os.path.getsize(p))
    if os.path.exists(MANIFEST):
        out["golden_set.json"] = (sha256_file(MANIFEST), os.path.getsize(MANIFEST))
    return out


def load_snapshot():
    if not os.path.exists(SNAPSHOT):
        return None
    data = json.load(open(SNAPSHOT, encoding="utf-8"))
    return data


def write_snapshot(state, roster):
    blob = {
        "schema": "golden_set.sha256/1",
        "purpose": "GOAL.md『黄金集只增不减』的机器可验凭证（只增不减=不得修改/删除已有 CSV）",
        "n_batches": sum(1 for k in state if k.startswith("batches/")),
        "roster": roster,
        "files": {k: {"sha256": v[0], "bytes": v[1]} for k, v in sorted(state.items())},
    }
    with open(SNAPSHOT, "w", encoding="utf-8") as f:
        json.dump(blob, f, ensure_ascii=False, indent=1, sort_keys=False)
    return blob


def diff(old, new):
    """返回 (modified, removed, added) 三个名单。"""
    ok = set(old)
    nk = set(new)
    modified = sorted(k for k in ok & nk if old[k][0] != new[k][0])
    removed = sorted(ok - nk)
    added = sorted(nk - ok)
    return modified, removed, added


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="生成/刷新快照")
    ap.add_argument("--check", action="store_true", help="只校验（默认行为）")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    if not args.write and not args.check:
        args.check = True

    state = collect()
    roster = {}
    if os.path.exists(MANIFEST):
        roster = json.load(open(MANIFEST, encoding="utf-8"))
    n_csv = sum(1 for k in state if k.startswith("batches/"))

    print(f"=== 黄金集 hash 快照 ===")
    print(f"  目录 {os.path.relpath(BATCH_DIR, ROOT)}")
    print(f"  实测 {n_csv} 个 batch CSV + golden_set.json")
    print(f"  名单 normal={len(roster.get('normal', []))} fault={len(roster.get('fault', []))}")

    if args.write:
        old = load_snapshot()
        if old:
            o_state = {k: (v["sha256"], v["bytes"]) for k, v in old.get("files", {}).items()}
            mod, rem, add = diff(o_state, state)
            if mod or rem or add:
                print(f"\n  [DIFF] 相对旧快照：修改 {len(mod)} / 删除 {len(rem)} / 新增 {len(add)}")
                for k in mod[:20]:
                    print(f"     M {k}")
                for k in rem[:20]:
                    print(f"     - {k}  (被删除！违反『只增不减』)")
                for k in add[:20]:
                    print(f"     + {k}")
                if len(mod) + len(rem) + len(add) > 60:
                    print(f"     ... 其余略")
            else:
                print("  快照与磁盘完全一致（无差异）")
        blob = write_snapshot(state, roster)
        print(f"  [OK] 已写入 {os.path.relpath(SNAPSHOT, ROOT)}"
              f"（{blob['n_batches']} 个 CSV）")
        return 0

    # --check
    old = load_snapshot()
    if old is None:
        print(f"  [FAIL] 快照不存在：{os.path.relpath(SNAPSHOT, ROOT)}"
              f"（先跑 --write 建立基线）")
        return 1
    o_state = {k: (v["sha256"], v["bytes"]) for k, v in old.get("files", {}).items()}
    mod, rem, add = diff(o_state, state)
    o_roster = old.get("roster", {})
    roster_diff = (o_roster.get("normal") != roster.get("normal")
                    or o_roster.get("fault") != roster.get("fault"))
    ok = not (mod or rem or roster_diff)
    # 新增 CSV 是允许的（"只增不减" ⇒ 允许增）；但要显式报告
    print(f"\n  修改 {len(mod)} | 删除 {len(rem)} | 新增 {len(add)}"
          f" | 名单变化 {'有' if roster_diff else '无'}")
    for k in mod[:30]:
        print(f"     M {k}")
    for k in rem[:30]:
        print(f"     - {k}  ← 被删除，违反『只增不减』")
    if add and args.verbose:
        for k in add[:30]:
            print(f"     + {k}  （新增，允许）")
    if roster_diff:
        print(f"     ! 名单被改动：normal {o_roster.get('normal')} → {roster.get('normal')}")
        print(f"       fault {o_roster.get('fault')} → {roster.get('fault')}")
    print(f"\n  [{'PASS' if ok else 'FAIL'}] 黄金集完整性"
          + ("（含允许的新增）" if add and not mod and not rem else ""))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
