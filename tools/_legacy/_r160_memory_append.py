# -*- coding: utf-8 -*-
"""R160：把本轮（第三次全面回溯 + D-75..D-78）追加到工作区记忆日志。

口径：`.workbuddy/memory/2026-11-05.md` 是 **LF**（`state.yaml` / `ENGINE_CONTRACT.md` 才是 CRLF）
⇒ 追加时按 LF 写，且**必须先校验目标非空**（R159 曾因 `bytes.encode` 用错把日志清空过一次）。
幂等：已含 `## R160：` 则 `[skip]`。

用法： py tools/_r160_memory_append.py
"""
from __future__ import annotations

import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
MEM = os.path.join(ROOT, ".workbuddy", "memory", "2026-11-05.md")

TEXT = """
---

## R160：第三次全面回溯 + **D-78 判据恒真证伪**

**触发**：用户「回溯初始研发方案以及目标，先看下哪些任务未完成」。
**性质**：回溯盘点 + 一处判据恒真的证伪；**引擎零改动**。

### 回溯结论（初始方案 = GOAL.md v1.0 + 设计文档 §4 + M2 §3/§4）

| 档 | 初始承诺 | 实测完成度 |
|---|---|---|
| A 仿真引擎 | 全状态轨迹 + 批次统计 + 诊断 | **完成并超额**（RMSE 2.345%、86/86、有效域、崩溃判据） |
| B 软测量 | 估值 ± CI + 状态诊断 | 参数估计器侧完成并超额；状态估计器侧 **EnKF 已交付 X + 粘度**；**回退链只 1/3 环**（D-75） |
| C 寻优 | 反设计 | **已批准并完成**（12/12 ±5%） |
| 看板（M5） | 三视图 | 三视图齐备，**对外口径停在 v1.69**（D-65，唯一 cap 约束项，用户暂缓） |

**GOAL §4 五条标准**：1 PASS / 2 有界 PARTIAL / 3 PASS / 4 PASS（改判） / 5 有界 PARTIAL。
**里程碑**：M0–M4 实质完成；M2 回退链不完整；M5 唯一欠账 = 看板口径。

### 🔴 D-78：I3「置信区间覆盖率」是**构造性恒真指标**

**发现**：读 `runs/r157_i3_channels.json` 时注意到 **X / P / PAA / vis 四通道的 `coverage` 浮点数逐位相同**
（`0.899548532731377`），而 verdict 分属 DELIVERABLE / NOT_IDENTIFIABLE / NOT_IDENTIFIABLE / DELIVERABLE
⇒ 同一个数字不可能同时证明「X 合格」和「P 不可辨识」。

**根因**：三处同构造 —— 区间 = **残差自身 5%/95% 分位数**，再数有多少残差落在区间内：
`r157_i3_channels.py:212` / `r138_our_observer.py:162-168` / `r139_observer_v2.py:173-179`
⇒ **由构造，对任意残差分布都必然 ≈0.90**。

**决定性检验**（`tools/r160_i3_coverage_tautology.py`，直接 import R157 脚本复用 `load/_fit/_predict/_nrmse`）：

| 预测器 | 逐点 coverage | 区间半宽 |
|---|---|---|
| **垃圾常数预测器（零信息）** | **0.899549（4 通道全同）** | 60.1 / 92.6 / 77.8 / 68.3% |
| 正常 B 档预测器 | **0.899549（4 通道全同）** | 5.96 / 41.6 / 56.4 / 11.2% |
| **差** | **Δ = 0.000000（全部）** | **≥31 pp（半宽有判别力）** |

- 逐批口径（`coverage_batchwise_mean`）同样无判别力（Δ≤0.0078）⇒ 不能作替代口径。
- **μ ± 1.96σ 口径有判别力**：垃圾（σ→0）覆盖 **0.0000** vs 正常 **0.1072(X) / 0.3160(P)** ⇒ 处置方案确定
  （`observe.py::coverage_check` 已存在，只是多通道脚本没采用）。

**影响面（精确）**：
- **判决层保留** —— T3-1 三道硬门（改善 >1pp / 半宽 ≤ 上限 / 半宽 < A 档误差）**均不依赖 coverage**
  ⇒ X/vis=DELIVERABLE、P/PAA=NOT_IDENTIFIABLE **不变**。
- **论证层须撤回** —— 「coverage 0.8995 ⇒ I3 达标」无效；0.8992 同源（R138/R139）⇒ 签核单 B-3/R-4、README 同受覆盖
  （该数字曾支撑 **M4 阻断项 6 的销号**）。
- 标准 5 总体判定（有界 PARTIAL）不变，且被**收紧**。

### 本轮新增四条债

| 编号 | 内容 | 层级 |
|---|---|---|
| **D-75** | **B 档回退链实为单环**：MHE / 稳态基线解算器 / 三条降级触发器**均未实现** ⇒ EnKF 发散时无自动降级路径 | L2 |
| **D-76** | **README 传播了 R158 已被 D-74 撤回的 A2 结论**（R159 治理层更新清单**漏了 README**） | L2 |
| **D-77** | README §4/§5、契约头部（v1.82 vs v1.89）、`state.yaml` oq#6/#30/#35 三处滞后 | L1 |
| **D-78** | I3 覆盖率构造性恒真 | L2 |

### 处置建议（本轮结论）

- **MHE + 稳态基线解算器** ⇒ **建议直接记为 V1+ 边界、不做**：闭环同化已判不可行（R140：产量 86/86→6/86）；
  EnKF 已替代 UKF；MHE 原始用途（带约束滚动优化）对应的控制路线已被 **D-54 判死** ⇒ 用途已随 D-54 消亡。
- **降级触发器** ⇒ **建议做**（半天）：EnKF spread→0 / RMSE 越阈时**显式**输出降级标记 ⇒ I2「失败可见」的同族延伸（不许静默降级）。
- **D-65 平台口径** 仍是唯一 cap 约束项（需用户解除暂缓）。

### 新增纪律（第 15–18 条）

15. **由分位数构造的区间，其覆盖率必然等于名义值** —— 这不是「达标」，是同义反复。
    凡引用覆盖率必须同时引用**区间半宽**与**相对更简单基线的改善**；必须做一次**零信息预测器对照**。
16. **跨通道逐位相同是恒真的强信号** —— 本轮正是靠它发现 D-78。
17. **冻结的实现计划不等于实现了的链路** —— M2「回退链冻结」只冻结设计，回溯必须**逐环核对源码**。
18. **治理层更新必须有一份「受影响文件清单」且逐文件核对** —— 尤其 README 这类面向人的入口。

### 工程坑（本轮实际踩到）

- **幂等检查必须逐条**：只看 `D-75` 一行时，后续步骤抛异常 ⇒ 已写入的部分无法被识别 ⇒ 台账被插入 **3 份**
  （用 `tools/_legacy/_r160_ledger_dedup.py` 去重）。
- **markdown 表格列数按文件而异**：签核单边界表 **5 列**、决策表 **3 列**、契约版本表 **2 列**
  ⇒ 校验函数须带 `ncol` 参数，不能硬编码 3。
- **YAML plain scalar 的 `#` 检查会误伤** `oq#6` 这类文本 ⇒ 措辞须避开 `#`。
- **回退链盘点要 grep 源码而非 grep 文档**：`observe.py`/`soft_sensing.py`/`mcp_server.py` 里
  `fallback`/`degrade` 全空，才证实 D-75。
- **README 是交接第一入口** ⇒ 治理层更新漏掉它 = 撤回的结论继续对外流传（D-76 的根因）。

### 工件

`docs/goal_backtrace_check_v3.md`（第三次全面回溯对标）· `docs/r160_round_report.md` ·
`tools/r160_i3_coverage_tautology.py` · `tools/r160_governance_update.py`（工具 458→**460**）·
`runs/r160_i3_coverage_tautology.json` · 台账 D-75/D-76/D-77/D-78 + 纪律 15–18 ·
签核单 B-15/B-16/B-17/R-10 + 修订 B-3 · 路线图 §八 · 契约 **v1.90**（头部 v1.82→v1.90 同步）·
`state.yaml`（oq 43→**47**、art 19→**21**）· README（修 D-76/D-77 + 补 D-78 已知边界）

### R160 闸门证据

- 零回归 `tools/r134_zero_regression.py --tol 0` ⇒ RMSE **2.345%**（红线 3.5%）、**86/86** 在 ±5%、
  **max|Δ| = 0.00e+00%**、全 86 批逐批一致（572 s，exit 0）
- pytest `py -m pytest candidate/indpensim/v0.1 -q` ⇒ **13 passed in 510.31s**（exit 0）
- 复跑一致性：R160 产物 vs 复跑副本 ⇒ **11 个关键量逐位一致**
- 迁移脚本幂等复跑 ⇒ 全部 `[skip]`
- `state.yaml` oq **47** / art **21**、YAML 解析通过、纯 CRLF；契约 **v1.90**

**cap 口径不变**（仍 L2 prototype conditional），**D-65 平台看板仍未闭合**。
"""


def main():
    raw = open(MEM, "rb").read()
    assert len(raw) > 1000, "记忆文件异常小（%d 字节），拒绝写入" % len(raw)
    assert b"\r\n" not in raw, "记忆文件不是 LF"
    cur = raw.decode("utf-8")
    if "## R160：第三次全面回溯" in cur:
        print("[skip] 今日日志已含 R160 段")
        return 0
    out = cur.rstrip("\n") + "\n" + TEXT
    with open(MEM, "wb") as f:
        f.write(out.encode("utf-8"))
    print("[ok] 已追加 R160 段（%d -> %d bytes）" % (len(raw), len(out.encode("utf-8"))))
    # 复核
    chk = open(MEM, "rb").read()
    assert len(chk) > len(raw), "追加后长度未增加"
    s = chk.decode("utf-8")
    for mark in ["## R160：第三次全面回溯", "D-78", "D-75", "零信息预测器对照", "## R159"]:
        print("  %-24s %s" % (mark, "OK" if mark in s else "MISS"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
