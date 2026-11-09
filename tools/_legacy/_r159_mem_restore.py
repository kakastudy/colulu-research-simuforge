# -*- coding: utf-8 -*-
"""R159 恢复：把 §十一 插回 2026-11-05 记忆日志的 §十 与 §十二 之间。

背景
----
本轮一次写文件时 `cur` 为空（`bytes.encode` 用错）⇒ 今日日志被清空（30580 → 460 字节）。
恢复材料来自会话 jsonl（`.workbuddy/projects/.../<session>.jsonl`）：
  - R156 段：写入脚本 `tools/_r156_memory.py` 的 `TEXT`
  - R157 前半：Edit 操作的 `new_string`
  - §十一：Edit 操作的 `new_string`
  - R157 后半 + R158：`tail -120` 的 stdout

用法
----
    py tools/_r159_mem_restore.py
"""
from __future__ import annotations

import os
import pickle

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
MEM = os.path.join(ROOT, ".workbuddy", "memory", "2026-11-05.md")
PICKLE = os.path.join(ROOT, "runs", "_mem_parts3.pkl")

# R159 段（本轮新增；与报告 docs/r159_round_report.md 的结论一致）
R159 = """
---

## R159：A2 证伪位检验 —— **撤回 R158 的「唯一正面结论」**

**触发**：用户 2026-11-05「ok，继续」⇒ 承接 R158 唯一正面结论做证伪位检验。
**性质**：结论证伪 / 口径纠错；**引擎零改动**。

### 判决：A2_RETRACTED（R158 的「唯一正面结论」**撤回**）

R158 曾报「失真批上 A2 两点校准 nRMSE 中位 **0.49%**，严格支配 PAT 转发 31.90%
⇒ 处理失真批应优先做两点校准」。**本轮证伪，该结论不成立**。

**五道证伪门**（`tools/r159_a2_falsification.py`，86 批 `GOLDEN_ALL`，与 R158 同口径，
复算关键量**逐位一致**：失真批 n=41、`A_engine_r` 0.0518、A2 0.49203788267713794）：

| 门 | FIRED | 关键数字 |
|---|---|---|
| G1 化验信号退化 | 是 | 失真批化验 CV 中位 **0.4568%** vs 可信批 **56.6742%**（比值 0.0081） |
| G2 **常数基线对照** | 是 | 失真批 A2 **0.4920%** vs 常数基线 **0.4854%**；符号检验 **37/41 批 A2 更差**，p=1.03e-07 |
| G3 斜率退化 | 是 | A2 拟合斜率中位 **0.0010** 约等于 0；预测动态范围 **0.0720%** vs 化验 **24.50 mg/L** |
| G4 时间泄漏（前推式） | 是 | 前推式 A2 **0.6461%** vs 前推常数 **0.6147%** |
| G5 在线可得性 | 是 | 分组标签 `A_engine_r` 需化验值 |

**剔除退化批后（n=57 有信息批）方向反转**：
A2 **20.47%** **劣于** C0 **10.29%**（50/57，p=4.24e-09）；
**真·失真批**（有信息且 r<=0.5，n=12）A2 **30.48%** 劣于常数基线 **28.64%**。

**根因（D-73）**：**V6 数据集批 61-90 的 `PAA_offline` 是占位值**（钉在 ~1200 mg/L，
CV 0.13-1.85%、动态范围 6.7-102.4 mg/L；批 1-60 正常，CV 中位 43.8%）。
全 100 CSV 普查 => 退化 **30 批**（池内 29 批）。
**失真批 41 批里 29 批是退化批** => 该分层实为「化验恒定」与「引擎失真」的混合体。

**R158 结论交叉影响**：
- **D-71 加固**（PAT 无独立信息）：增量 R2 0.0199 -> **0.0092**、t 0.104 -> **0.036**、
  `pat_vs_engine_r` 0.9796 -> **0.9843** => **主判决更硬**。
- **D-72 / D-70 维持**（与化验退化正交）。
- 「失真批 B>A 38/41（p=1.05e-08）」=> 剔除后仅 **2/12、p=0.0386** => 显著削弱。

**修正后的表述**：「而非引入 Raman 资产」**成立**；「优先做两点校准」**不成立**。
失真批 PAA 估值**目前没有已验证的简单解**；C0（锚在引擎 PAA 上的逐点比例锚定，
有信息批中位 10.29%）是当前最好候选，但**需化验锚点 + 无在线可得判别器** => V1+ 候选。

### 本轮沉淀的两条纪律（新增）

1. **统计口径必须先做「信号退化筛查」** —— 任何以化验/真值为分母或对照的统计，
   必须先验证**真值本身有动态信息**（CV / 动态范围）。
   否则结论会落在「真值恒定」的子集上 => **任何**预测器（含「输出一个常数」）误差都趋 0
   => 结论**必然**平凡满足，且**模型排名被真值退化翻转**
   （本轮：常数基线 0.30% 打败最好的模型）。
2. **正面结论与否定结论享有同等的被证伪义务** —— 不得因正面结论「更可用」而给更宽松的复核标准。
   （R158 给正面结论、R159 推翻它，**这不是 R158 的错误，而是流程奏效**。）

### 工程坑（本轮实际踩到）

- **Windows 下 `python` != `py`**：`python` = WorkBuddy 自带 3.13.12（**无 numpy/pandas/scipy**）；
  `py` = Python 3.10.4（numpy 1.26.4 / pandas 2.3.3 / scipy 1.15.3）
  => **本项目所有脚本必须用 `py`**（用 `python` 会直接 `ModuleNotFoundError`）。
- **换行风格按文件分**：`docs/*.md` 是 **LF**；`state.yaml` / `ENGINE_CONTRACT.md` 是 **CRLF**
  => 迁移脚本必须**按文件各自的风格读写**，不能用同一个读写器硬套。
- **YAML 安全字符检查必须分块**：`open_questions` 是 **plain scalar**（禁 `: ` / `,` / `[` / `]` / `#`）；
  `artifacts` 是 **`key: value` 映射**（`: ` **合法**）=> 用同一套规则会误杀合法条目。
- **字典字面量里不能混写条件表达式作为值**：`{"k": X if c else Y}` 在 `X` 含逗号时被解析成 tuple。
- **`--batches all` 与逗号列表分支的判断顺序**：先判 `== "all"`，否则 `"all"` 进 `int()` 抛 ValueError。
- **幂等指示要区分 `[skip]` 与「未命中」**：replace 未命中时**不得**报 `[ok]`。
- **写文件前务必校验 `cur` 非空** —— 本轮一次 `cur.rstrip(b"\n").encode()` 误用导致
  今日日志被清空（30580 -> 460 字节），后经会话 jsonl 恢复
  （从 Edit 操作的 `old_string` / `new_string` 与 `tail` 输出重建）。

### 工件

`tools/r159_a2_falsification.py` / `tools/r159_governance_update.py`（工具 456 -> **458**）、
`tools/_r159_mem_restore.py`（本轮记忆恢复脚本）、
`runs/r159_a2_falsification.json` 、`docs/r159_round_report.md` 、
`docs/r157_debt_ledger.md` D-73/D-74 + 修订 D-71 、
`docs/m5_review_signoff.md` B-13/B-14/R-9 + 修订 B-10 、
`docs/roadmap_next.md` T3-3 补 R159 修订 、`ENGINE_CONTRACT.md` **v1.89** 、
`state.yaml`（oq 41 -> **43**、art 18 -> **19**）

### R159 闸门证据

- 零回归 `tools/r134_zero_regression.py --tol 0` => RMSE **2.345%**（红线 3.5%）、**86/86** 在 +-5%、
  **max|d| = 0.00e+00%**、全 86 批逐批一致（1044 s，exit 0）
- pytest `py -m pytest candidate/indpensim/v0.1 -q` => **13 passed in 1040.41s**（exit 0）
- 复跑一致性：R159 产物 vs 复跑副本 => **7 个关键量逐位一致**
- 迁移脚本幂等复跑 => 全部 `[skip]` / exit 0
- `state.yaml` oq **43** / art **19**、YAML 解析通过、纯 CRLF；契约 **v1.89**、竖线数 = 3

**cap 口径不变**（仍 L2 prototype conditional），D-65 平台看板仍未闭合。
"""

HEADER = "# 2026-11-05 工作日志\n"


def main():
    with open(PICKLE, "rb") as f:
        parts = pickle.load(f)
    text156 = parts["text156"]
    r157 = parts["r157"]
    e0new = parts["e0new"]

    # §十一 已插入（parts3 里 r157 已含）
    full = (HEADER + text156.rstrip("\n") + "\n\n"
            + e0new.rstrip("\n") + "\n\n"
            + r157.rstrip("\n") + "\n" + R159)

    assert len(full) > 20000, "重建内容过短，中止写入"
    assert "### 十一、R157 后半段实测回填" in full, "缺少 §十一"
    assert "### 十二、" in full and "### 十三、" in full and "## R158" in full, "缺章节"

    data = full.encode("utf-8")
    with open(MEM, "wb") as f:
        f.write(data)
    print("[ok] 记忆日志已重建：%d bytes" % len(data))
    heads = [l for l in full.split("\n") if l.startswith("#")]
    for h in heads:
        print("   ", h[:80])


if __name__ == "__main__":
    main()
