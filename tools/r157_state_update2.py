# -*- coding: utf-8 -*-
"""R157 续：state.yaml 的 `artifacts` 追加 R157 新产物 + `open_questions` 追加收口条目。

背景
----
v1 的 `tools/r157_state_update.py` 只登记了 3 个 R157 产物（golden_set_hash / m5_signoff / roadmap）。
本轮后半段又产出了：轮次报告、债务台账、I3 多通道结果、有效性判据两臂结果、故障模式仿真四臂结果、
D-57 扫描结果 ⇒ 补登记，避免「结论落在一处、状态记在另一处」。

另外补 3 条 `open_questions`：把本轮新出现、但**尚未有结论**的问题登记在案
（D-57 的最终判定待 v2 扫描；D-68 的 `ph_fix=1` 是否提为默认待裁决；平台口径同步仍暂缓）。

落点与格式
----------
`state.yaml` 为**纯 CRLF** ⇒ 全部读写按 CRLF 处理（`newline=''` + 显式 `\r\n`）。
`artifacts` 是 **mapping**（`  key: value`），`open_questions` 是 **sequence**（`  - item`）。
`cap.reasons` 是 flow sequence ⇒ **不得**在 plain scalar 里出现方括号或 ASCII 逗号（本脚本不碰它）。

实现
----
**行级定位**（不靠字符串偏移）⇒ 区块可能在文件中间也可能在**末尾**（`artifacts` 就在末尾）都能处理。

幂等
----
以各条目的**键名/首词**为锚点；已存在则跳过。
"""
from __future__ import annotations

import io
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
TARGET = os.path.join(ROOT, "state.yaml")

ARTIFACTS = [
    ("r157_report", "docs/r157_round_report.md   # R157 轮次报告（十节）"),
    ("r157_debt_ledger", "docs/r157_debt_ledger.md   # R157 债务台账（关闭 6 条 / 新增 8 条）"),
    ("r157_i3_channels", "runs/r157_i3_channels.json   # R157/T3-1 I3 多通道（X + 粘度可交付；P/PAA 不可辨识）"),
    ("r157_validity", "runs/r157_validity_base.json + runs/r157_validity_v2.json   # R157/D-56 有效性判据两臂"),
    ("r157_fault_modes", "runs/r157_fault_modes_phfix1.json + runs/r157_fault_modes_b3_phfix1.json   # R157/T3-2 故障模式（ph_fix=1 口径）"),
    ("r157_bistab_knob", "runs/r157_bistab_knob.json   # R157/D-57 连续旋钮扫描（v2 判据）"),
]

OPEN_QUESTIONS = [
    "R157/D-57：b22 类双稳态的连续旋钮搜索 —— v1 判据有平局缺陷（D-69）已作废并重跑；"
    "v2 结论待回填。若五个旋钮全部 DISCONTINUOUS，则 D-54（葡萄糖闭环）在这套方程里永久关闭，进料可行域边界就此确定",
    "R157/D-68：故障特征级仿真必须在 ph_fix=1 口径下做（默认基线会把故障影响放大约 2 倍）；"
    "是否把 ph_fix 提为默认，属 GOAL §5 边界变更，待裁决",
    "R157/T1-3 与 T1-4：平台数据与口径同步、T8 逐屏复验 —— 用户 2026-11-05 显式暂缓；"
    "在此之前看板仍停在 v1.69 口径（catastrophic=0 来自 D-38 已判恒真的旧判据），cap 保持 conditional",
]


def _block_end(lines, start):
    """返回从 start+1 开始的**块内**行数（块 = 随后的所有缩进行）。"""
    i = start + 1
    while i < len(lines):
        ln = lines[i]
        if ln.strip() == "":
            break
        if not ln.startswith((" ", "\t")):
            break
        i += 1
    return i


def main() -> int:
    with io.open(TARGET, "r", encoding="utf-8", newline="") as f:
        text = f.read()
    assert "\r\n" in text, "state.yaml 预期为 CRLF"
    lines = text.split("\r\n")

    def find_key(name):
        for i, ln in enumerate(lines):
            if ln.rstrip() == name + ":":
                return i
        return -1

    # ---- 1) artifacts：追加 mapping 条目 ----
    added_a = 0
    ai = find_key("artifacts")
    assert ai >= 0, "未找到 artifacts 区块"
    end = _block_end(lines, ai)
    for key, val in ARTIFACTS:
        if any(ln.startswith("  %s:" % key) for ln in lines):
            print("[skip] artifact 已存在：%s" % key)
            continue
        lines.insert(end, "  %s: %s" % (key, val))
        end += 1
        added_a += 1
        print("[ok] artifact 新增：%s" % key)

    # ---- 2) open_questions：追加 sequence 条目 ----
    added_q = 0
    qi = find_key("open_questions")
    assert qi >= 0, "未找到 open_questions 区块"
    end = _block_end(lines, qi)
    for q in OPEN_QUESTIONS:
        key = q.split("：")[0]
        if any(key in ln for ln in lines):
            print("[skip] open_question 已存在：%s" % key)
            continue
        lines.insert(end, "  - %s" % q)
        end += 1
        added_q += 1
        print("[ok] open_question 新增：%s" % key)

    new_text = "\r\n".join(lines)
    with io.open(TARGET, "w", encoding="utf-8", newline="") as f:
        f.write(new_text)

    # ---- 3) 校验 ----
    import yaml
    d = yaml.safe_load(io.open(TARGET, encoding="utf-8", newline=""))
    raw = open(TARGET, "rb").read()
    print("[ok] YAML 解析通过；CRLF 保持：%s"
          % (raw.replace(b"\r\n", b"").count(b"\n") == 0))
    print("[ok] artifacts n = %d；open_questions n = %d" %
          (len(d["artifacts"]), len(d["open_questions"])))
    print("[ok] cap.level = %s" % d["cap"]["level"])
    print("[ok] 本次新增：artifacts %d 条、open_questions %d 条" % (added_a, added_q))
    return 0


if __name__ == "__main__":
    sys.exit(main())
