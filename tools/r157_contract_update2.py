# -*- coding: utf-8 -*-
"""R157 续：契约追加 **v1.86** 行（签核单重评审之后的三项事实变更）。

背景
----
v1.85 写于签核单落稿时，那时 T3-1（T3-1 I3 多通道）与 D-56（有效性判据）尚未收口，
且 T3-2 的引擎侧 `fault_profile` 尚未接线。v1.85 里「引擎零改动」与「I3 仅覆盖 X 通道」
两句现已过时 ⇒ 追加 v1.86 记录**事实变更**，不改写 v1.85 的历史记录。

落点
----
`ENGINE_CONTRACT.md` §4 版本与变更表的**末行之后**（v1.85 之后）。
文件为**纯 CRLF** ⇒ 全部读写按 CRLF 处理（`newline=''` + 显式 `\r\n`）。

幂等
----
以 `| v1.86 |` 为锚点；若已存在则**跳过**（不重复追加），退出码 0。
"""
from __future__ import annotations

import io
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
TARGET = os.path.join(ROOT, "ENGINE_CONTRACT.md")
ANCHOR = "| v1.86 |"

ROW = (
    "| v1.86 | R157 续：**D-56 有效性判据关闭 + T3-1 I3 多通道 + T3-2 引擎侧 `fault_profile`**"
    "（v1.85 之后的**事实变更**；不改写 v1.85 的历史记录）。"
    "①**D-56 关闭**：`validity()` 的 pH 越域判据由「是否 ≥7.0」改为「**是否感知 basic 分支已被修正**」——"
    "新增 `sim.attrs[\"ph_basic_fixed\"]`（= `params[\"ph_fix\"]`），`ph_hard_max=\"auto\"` 时："
    "`ph_fix=0`（默认，basic 分支数值病态）⇒ `ph_hard = 7.0`（**与 R148 旧行为逐位一致**）；"
    "`ph_fix=1`（basic 分支已修）⇒ `ph_hard = None`（越 7 **只登记不判 invalid**）。"
    "**默认路径 valid 逐位不变（77/86）**；「basic 已修」口径下 **81/86**；候选 v2 下 **86/86**。"
    "新增诊断字段 `n_steps` / `over7_frac` / `ph_hard_max_used` / `basic_branch_fixed`"
    "（**`n_steps` 非常量：1049–1289 ⇒ 必须报分布，不能只报计数**，D-44 教训）。"
    "**勘误**：v1.84/v1.85 引用的「9 批 pH_max 7.001–7.126、0 钳位」只成立于**候选 v2**；"
    "**默认基线实测 9 批中有 5 批是真钳位**（b37/50/51/91/92，`[H⁺]` 曾 ≤ 0 ⇒ 数值崩溃，b37 pH_max **9.185**）"
    "⇒ 这 5 批判 invalid **完全正确、不可放宽**。"
    "②**T3-1 I3 多通道**（`tools/r157_i3_channels.py`，结构化双通道观测器 + 批级 5 折 CV，"
    "跨 4 种代理组合结论一致）：**X** A 档 24.58% → B 档 **2.28%**（覆盖 89.95%，复现 R139 的 3.17%/0.8992）、"
    "**vis（粘度）** 19.69% → **5.57%**（CI 半宽 10.6%）⇒ **标准 5 的 I3 覆盖面由「仅 X」扩展为「X + 粘度」**；"
    "**P** 14.19% → 17.70%、**PAA** 28.20% → 28.72%（均**劣于 A 档**）⇒ **有量化证据的否定结论**"
    "（与 R154「残糖型状态结构性不可辨识」同向 ⇒「没有代理」成为**可引用的边界**）；"
    "S / DO2 的软测量目标为**参考模型输出而非化验** ⇒ 循环论证，仅参考。"
    "**判定规则含三道硬门**：① 优于 A 档 ② **CI 半宽 ≤ 25%** ③ **CI 半宽 < A 档误差** —— "
    "门②③ 为本轮**自查补上**（原规则下 S 通道「覆盖 90%」是靠区间半宽 **97.9%** 平凡满足的，"
    "**D-38 同型陷阱**）⇒ 长期纪律：**覆盖率 / 通过率类指标必须同时约束分母侧**。"
    "③**T3-2 引擎侧新增 opt-in `fault_profile`**（时间包络 `[(t_h, rel_amp), ...]`，线性插值 × `fault_magnitude`）："
    "`model.rhs` → `integrate_interval` → `simulate_open_loop(params[\"fault_profile\"])` 链路打通；"
    "**默认 None ⇒ 相对幅值恒为 1 ⇒ 逐位一致**。用于**没录进回放输入**的故障"
    "（未记录的 KLa 衰减、传感器偏置、摄取停滞；R143 纪律）。"
    "④**签核单同步**：`docs/m5_review_signoff.md` 的标准 5 口径、边界清单 **B-3 / B-5** 修订、"
    "新增 **B-8**（I3 类判据的可平凡满足性）、决策 R-4 更新 ⇒ **三处一致**（契约 / 签核单 / `state.yaml`）。 |\r\n"
)


def main() -> int:
    with io.open(TARGET, "r", encoding="utf-8", newline="") as f:
        text = f.read()
    if ANCHOR in text:
        print("[skip] v1.86 已存在，未重复追加")
        return 0
    # 契约末尾是 `\r\n\r\n`（表后空行）。在**最后一个非空行之后**插入 v1.86。
    lines = text.split("\r\n")
    # 找最后一个非空行索引
    last = -1
    for i, ln in enumerate(lines):
        if ln.strip():
            last = i
    if last < 0:
        print("[fail] 契约文件为空")
        return 1
    anchor_line = lines[last]
    if not anchor_line.startswith("| v1.85"):
        print(f"[warn] 末个非空行不是 v1.85（实际前 12 字符：{anchor_line[:12]!r}）——仍按『末行之后』追加")
    lines.insert(last + 1, ROW.rstrip("\r\n"))
    new_text = "\r\n".join(lines)
    with io.open(TARGET, "w", encoding="utf-8", newline="") as f:
        f.write(new_text)
    print("[ok] 已追加 v1.86 行")
    print("[ok] CRLF 保持：", new_text.replace("\r\n", "").count("\n") == 0)
    print("[ok] 行数：", len(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
