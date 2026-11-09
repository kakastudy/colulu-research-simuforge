# -*- coding: utf-8 -*-
"""R160 收尾修复：去重台账里被重复插入的 D-75..D-78 段（保留第一份）。

起因：`r160_governance_update.py` 的幂等判断只看 `D-75` 一行，
而首次运行在写入前就抛了异常（签核单列数检查）⇒ 实际写入了一部分，
但**写文件发生在检查之后**，导致三次运行各插入了一份 ⇒ 台账出现 3 份重复。

本脚本：按「首次出现保留」去重，并校验每份都完整（4 条都在）。
幂等：已去重则 `[skip]`。

用法： py tools/_r160_ledger_dedup.py
"""
from __future__ import annotations

import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
LEDGER = os.path.join(ROOT, "docs", "r157_debt_ledger.md")

HEADS = ["### D-75", "### D-76", "### D-77", "### D-78"]


def read(path):
    raw = open(path, "rb").read()
    if b"\r\n" in raw:
        assert b"\n" not in raw.replace(b"\r\n", b""), "混有 lone LF"
        return raw.decode("utf-8").split("\r\n"), raw, "\r\n"
    assert b"\r" not in raw, "混有 lone CR"
    return raw.decode("utf-8").split("\n"), raw, "\n"


def write(path, lines, raw_before, nl):
    data = nl.join(lines).encode("utf-8")
    with open(path, "wb") as f:
        f.write(data)
    return raw_before.count(nl.encode()), open(path, "rb").read().count(nl.encode())


def main():
    lines, raw, nl = read(LEDGER)

    # 找出所有 D-75..D-78 的段起点
    starts = []
    for i, l in enumerate(lines):
        for h in HEADS:
            if l.startswith(h):
                starts.append((i, h))
                break
    counts = {h: sum(1 for _, x in starts if x == h) for h in HEADS}
    print("插入次数：", counts)
    if all(c == 1 for c in counts.values()):
        print("[skip] 台账无重复")
        return 0
    if any(c == 0 for c in counts.values()):
        raise SystemExit("[fail] 有条目缺失（%s），不能盲目去重" % counts)

    # 保留第一组（4 条连续），删掉其余组
    keep = []
    drop = []
    first = True
    for k, (i, h) in enumerate(starts):
        nxt = len(lines)
        for j in range(i + 1, len(lines)):
            if lines[j].startswith("### ") or lines[j].startswith("## "):
                nxt = j
                break
        if first and h == "### D-75":
            keep.append((i, nxt))
            first = False
        else:
            drop.append((i, nxt))

    # 从后往前删，避免索引错位
    removed = 0
    for (i, nxt) in sorted(drop, key=lambda x: -x[0]):
        # 连同其后的空行一起删
        end = nxt
        while end < len(lines) and lines[end].strip() == "":
            end += 1
        del lines[i:end]
        removed += (end - i)
    print("删除行数：", removed)

    out, _ = write(LEDGER, lines, raw, nl)
    print("[ok] 已去重（%d -> %d 行）" % (out, len(lines)))

    # 复核
    lines2, _, _ = read(LEDGER)
    for h in HEADS:
        c = sum(1 for l in lines2 if l.startswith(h))
        print("  %-10s 出现 %d 次" % (h, c))
        assert c == 1, "去重失败"
    print("[ok] 复核通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
