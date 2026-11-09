# -*- coding: utf-8 -*-
"""R159 恢复辅助：把 §十一 插回 r157 段，产出 parts3 pickle。"""
import pickle
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

parts = pickle.load(open(os.path.join(ROOT, "runs", "_mem_parts2.pkl"), "rb"))
sec11 = pickle.load(open(os.path.join(ROOT, "runs", "_mem_sec11.pkl"), "rb"))
r157 = parts["r157"]

MARK = "### " + chr(0x5341) + chr(0x4E8C) + chr(0x3001)   # "### 十二、"
i12 = r157.find(MARK)
assert i12 >= 0, "未找到 §十二 标记"
r157_full = r157[:i12] + sec11.rstrip("\n") + "\n\n" + r157[i12:]
print("插入后长度", len(r157_full))
assert chr(0x5341) + chr(0x4E00) in r157_full, "缺少 §十一"
assert r157_full.count("### " + chr(0x5341) + chr(0x4E09) + chr(0x3001)) == 1, "§十三 重复"
assert r157_full.count("### " + chr(0x5341) + chr(0x56DB) + chr(0x3001)) == 1, "§十四 重复"
assert r157_full.count("## R158") == 1

parts["r157"] = r157_full
with open(os.path.join(ROOT, "runs", "_mem_parts3.pkl"), "wb") as f:
    pickle.dump(parts, f)
print("[ok] parts3 已生成")
for l in r157_full.split("\n"):
    if l.startswith("### ") and ("R157" in l or "坑" in l):
        print("   ", l[:70])
