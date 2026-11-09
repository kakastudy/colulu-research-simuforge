# -*- coding: utf-8 -*-
"""R160：把「第三次回溯 + D-75/D-76/D-77/D-78」写进台账 / 签核单 / 路线图 / 契约 / state.yaml。

口径
----
- 换行风格**按文件实际**：`docs/*.md` 是 LF，`state.yaml` / `ENGINE_CONTRACT.md` 是 CRLF。
  ⇒ 读时按实际风格切分，写时**原样保持**（R159 踩过的坑：不能硬套同一个读写器）。
- **行级定位**（不靠字符串偏移）；**幂等**：锚点已存在则 `[skip]`。
- `state.yaml` 的 `open_questions` 元素是 plain scalar ⇒ 不得以 `*` 开头，
  不得含 `: ` / `,` / `[` / `]` / `{` / `}` / `#`。
- `artifacts` 是 **key: value 映射** ⇒ 其值里的 `: ` 合法，不走 plain 检查；
  但值不得以 `*` 开头、不得含 `#`。
- markdown 表格行内**不得含裸竖线**（除首尾分隔竖线外 ⇒ 竖线数必须恰好 3）。
- 契约版本表是 **3 列** ⇒ 行内竖线数必须恰好 3。

用法
----
    py tools/r160_governance_update.py
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
LEDGER = os.path.join(ROOT, "docs", "r157_debt_ledger.md")
SIGNOFF = os.path.join(ROOT, "docs", "m5_review_signoff.md")
ROADMAP = os.path.join(ROOT, "docs", "roadmap_next.md")
STATE = os.path.join(ROOT, "state.yaml")
CONTRACT = os.path.join(ROOT, "ENGINE_CONTRACT.md")
README = os.path.join(ROOT, "README.md")

FORBIDDEN_STATE = ["*", "[", "]", "{", "}", ",", ": ", "#"]


# ---------------------------------------------------------------- 工具
def _read(path):
    """按文件实际换行风格切分；返回 (lines, raw, nl)。"""
    raw = open(path, "rb").read()
    if b"\r\n" in raw:
        assert b"\n" not in raw.replace(b"\r\n", b""), "%s 混有 lone LF" % path
        return raw.decode("utf-8").split("\r\n"), raw, "\r\n"
    assert b"\r" not in raw, "%s 混有 lone CR" % path
    return raw.decode("utf-8").split("\n"), raw, "\n"


def _write(path, lines, raw_before, nl="\r\n"):
    data = nl.join(lines).encode("utf-8")
    if nl == "\r\n":
        assert b"\n" not in data.replace(b"\r\n", b""), "出现 lone LF"
    else:
        assert b"\r" not in data, "出现 lone CR"
    with open(path, "wb") as f:
        f.write(data)
    raw2 = open(path, "rb").read()
    if nl == "\r\n":
        assert b"\n" not in raw2.replace(b"\r\n", b""), "%s 写后出现 lone LF" % path
    else:
        assert b"\r" not in raw2, "%s 写后出现 lone CR" % path
    return raw_before.count(nl.encode()), raw2.count(nl.encode())


def _check_plain(text):
    """plain scalar 安全字符检查（**仅用于 open_questions 元素**）。"""
    for ch in FORBIDDEN_STATE:
        if ch in text:
            raise SystemExit("[fail] state.yaml 元素含危险字符 %r: %s" % (ch, text[:90]))


def _check_artifacts_value(text):
    body = text.split(":", 1)[1] if ":" in text else text
    if body.lstrip().startswith("*"):
        raise SystemExit("[fail] artifacts 值以 * 开头: %s" % text[:90])
    if "#" in body:
        raise SystemExit("[fail] artifacts 值含 #: %s" % text[:90])


def _check_no_pipe(text, where, ncol=3):
    """markdown 表格行内不得含裸竖线（除首尾的分隔竖线外）。

    `ncol` = 列数 ⇒ 竖线数必须 = ncol + 1。
    转义竖线 `\\|` 不计（markdown 里它不是分隔符）。
    """
    body = text.strip()
    assert body.startswith("|") and body.endswith("|"), "%s 表格行未以 | 包裹" % where
    n = body.replace("\\|", "").count("|")
    if n != ncol + 1:
        raise SystemExit("[fail] %s 表格行竖线数 = %d（应为 %d）" % (where, n, ncol + 1))


def _find(lines, prefix, start=0):
    for i in range(start, len(lines)):
        if lines[i].startswith(prefix):
            return i
    return -1


# ---------------------------------------------------------------- 台账内容
D75 = """### D-75　B 档回退链**实为单环**（MHE / 稳态基线解算器 / 降级触发器均未实现）　🔴 **R160 新增，L2（能力）**

| 项 | 内容 |
|---|---|
| 原文要求 | `docs/M2_method_selection.md` §3 冻结四环回退链：**UKF → EnKF → MHE+稳态碳平衡约束 → 显式失败**；§3.2 三条量化降级触发（UKF trace>10xP0 / EnKF spread→0 / MHE QP 失败）；§4 实现计划 **Phase 1（UKF 骨架）/ Phase 2（EnKF + 稳态基线）/ Phase 3（MHE 约束优化）** |
| 实测盘点 | ① **UKF**：源码无 `UKF`/`unscented`/`sigma_point` ⇒ 未实现（R42 记「由 EnKF 结构性替代」）；② **EnKF**：`observe.py` 的 `enkf_observe`/`enkf_update`/`_initial_ensemble`/`localized_K`/`phys_clamp` ⇒ **已实现且为现役主力**；③ **MHE**：源码无 `MHE`/`moving_horizon`/QP ⇒ **未实现**；④ **稳态碳平衡基线解算器**：`mechanism_cclosure.py` 只是**归认核算**（呼吸归认账 resp_share +56%~66%），**不是**可作为降级目标输出的解算器 ⇒ 未实现；⑤ **降级触发器**：`observe.py`/`soft_sensing.py`/`mcp_server.py` grep `fallback`/`degrade`/`降级` **全空** ⇒ 未实现 |
| 后果 | EnKF 收敛时可用；**EnKF 发散时没有自动降级路径**，只能由调用方手工改走别的工具 ⇒ GOAL §4 标准 5 的「失败可见」只做到「失败被标出」，没做到「失败后还有降级」 |
| 与既有结论的关系 | `docs/goal_backtrace_check.md`（v2，2026-10-27）已记「D1 的 UKF 由 EnKF 结构性替代」，但**未系统盘点过 MHE 环、稳态基线解算器与降级触发器** ⇒ 本条为 v2 未登记的新发现 |
| 处置建议 | ① **MHE + 稳态基线解算器**：建议直接**记为 V1+ 显式边界**（不实现）—— 闭环数据同化已被 R140 判不可行（产量 86/86→6/86）；EnKF 已结构性替代 UKF；MHE 的原始用途是「带约束的滚动优化」，而本项目控制路线已被 **D-54 判死**（连续调控封死）⇒ **该用途已随 D-54 消亡**。② **降级触发器**：建议**本轮就做**（低成本高价值）—— EnKF spread→0 或 RMSE 越阈时**显式**输出 `degraded_to_*` 标记而非静默继续；这是 I2「失败可见」的同族延伸（**不许静默降级**） |
| 纪律延伸 | **冻结的实现计划不等于实现了的链路** —— M2 的「回退链冻结」只冻结了**设计**；回溯时必须**逐环核对源码**，不能凭「文档已冻结」推断「链路已闭合」 |

"""

D76 = """### D-76　README **传播了 R158 已被 D-74 撤回的 A2 结论**　🔴 **R160 新增，L2（对外文档）**

| 项 | 内容 |
|---|---|
| 现象 | `README.md` 第 165–166 行仍写：「被**两点校准**（A2：只做留一锚点仿射校准、**完全不用 PAT**）中位 **0.49%** **严格支配** ⇒ **处理失真批应优先做两点校准，而非引入 Raman 资产**」 |
| 为何是问题 | 这正是 **D-74 已撤回**的结论：R159 五道证伪门**四门触发**（化验退化 / 常数基线同量级 / 斜率退化为 0 / 前推式优势消失）；**剔除 29 批退化批后 A2 20.47% 劣于 C0 10.29%**（50/57，p=4.24e−09）⇒ 「优先做两点校准」**不成立** |
| 为何此前未被发现 | R159 的治理脚本更新了台账（D-73/D-74）、签核单（B-13/B-14/R-9）、路线图、契约、state.yaml —— 但 **README 不在这五处** ⇒ 治理层更新清单**漏了 README** |
| 为何优先级高 | README 是**交接第一入口**（§5 文档阅读顺序里排在 GOAL/PROBLEM 之后靠前），比台账/签核单更早被读 ⇒ **撤回的结论仍在对外流传** |
| 修法 | README §4 的 Raman/PAA-PLS 行改写为 R159 修订后的表述：「不引入 Raman 资产」成立；「优先做两点校准」**已撤回**（D-74）；失真批 PAA 估值目前**没有已验证的简单解**，C0（锚在引擎 PAA 上的逐点比例锚定，有信息批中位 10.29%）是当前最好候选，但需化验锚点且**无在线可得判别器** ⇒ V1+ 候选 |
| 纪律延伸 | **治理层更新必须有一份「受影响文件清单」**，且该清单须**逐文件核对**（不能凭「改了台账和签核单」推断「全改了」）—— 尤其 README / 交接文档这类**面向人**的入口 |

"""

D77 = """### D-77　README / 契约头部 / `state.yaml` 三处**版本与表述滞后**　🟢 **R160 新增，L1（文档）**

| 项 | 内容 |
|---|---|
| README §4 标题 | 写「当前状态（契约 **v1.87**）」，而契约实际已到 **v1.89** ⇒ 落后 2 版 |
| README §5 | 指向 `docs/r156_round_report.md` / `docs/r156_debt_ledger.md`（「最近一轮」「未闭项清单，接手先读这个」），而最新应为 **`r159_round_report.md`** / **`r157_debt_ledger.md`** ⇒ 接手者会从**三轮前**的台账开始读 |
| 契约头部 | `ENGINE_CONTRACT.md` 第 3 行 `> 状态：**v1.82**`，而版本表已到 **v1.89** ⇒ **v1.83–v1.89 共 7 版未反映在头部**（头部是「读最新一条」的入口之一） |
| state oq#6 | 仍写「I3 覆盖率**只覆盖 X 通道**」，但 R157/T3-1 已扩展为 **X + 粘度**（`runs/r157_i3_channels.json` 有 vis 通道且 verdict=DELIVERABLE）⇒ 与签核单 R-4 口径不一致 |
| state oq#30 | 仍写「I3 覆盖率仅 3/12 批实测：X 合并 0.630」，而 R138/R139 已给 0.8992、R157 已扩到 X+vis ⇒ **过时** |
| state oq#35 | 「终末收获后处理步骤的复现方式（90 批 CSV 不含）待 M1 定案」—— 但口径**已在 PROBLEM.md §7.2 定案**（`simulate.py:945`：`harvested = −Σ(Fremoved·P)·h`；`end = V_last·P_last`）⇒ **表述过时，可关闭** |
| 修法 | 逐处改写；README §5 的「最近一轮」改为 r159；契约头部同步到 v1.90；state oq#6/#30 改写、oq#35 关闭 |

"""

D78 = """### D-78　I3「置信区间覆盖率」是**构造性恒真指标** ⇒ 不可作为达标证据　🔴 **R160 新增，L2（判据）**

| 项 | 内容 |
|---|---|
| 现象 | `runs/r157_i3_channels.json` 的 **X / P / PAA / vis 四个通道 `coverage` 浮点数逐位相同**（`0.899548532731377`），而四者的 verdict 分别是 DELIVERABLE / NOT_IDENTIFIABLE / NOT_IDENTIFIABLE / DELIVERABLE ⇒ **同一个数字不可能同时证明「X 合格」和「P 不可辨识」** |
| 根因 | 三处代码是**同一构造**：置信区间 = **残差分布自身的 5%/95% 分位数**，再统计「有多少残差落在这个区间内」。`tools/r157_i3_channels.py:212`、`tools/r138_our_observer.py:162-168`、`tools/r139_observer_v2.py:173-179` ⇒ **由构造，对任意残差分布都必然约 0.90** |
| 决定性检验 | `tools/r160_i3_coverage_tautology.py`（直接 import R157 脚本复用 `load/_fit/_predict/_nrmse`，口径逐位可比）：**零信息预测器**（预测该批化验的常数）与正常预测器的覆盖率**逐位相同**，4 个通道**全部 Δ=0.000000**（均 0.899549）；**逐批口径**（`coverage_batchwise_mean`）同样无判别力（Δ≤0.0078） |
| 对照：区间**半宽有判别力** | 垃圾预测器半宽 60.1% / 92.6% / 77.8% / 68.3% vs 正常 5.96% / 41.6% / 56.4% / 11.2% ⇒ **T3-1 三道硬门里的第 2、3 道（半宽上限 / 半宽<A档）真正在起作用** |
| 影响面（精确界定） | ① **判决层不受影响**：T3-1 的 X/vis=DELIVERABLE 与 P/PAA=NOT_IDENTIFIABLE **均不依赖 coverage**（三道硬门为「改善>1pp / 半宽≤上限 / 半宽<A档误差」）⇒ **结论保留**；② **论证层须撤回**：「coverage 0.8995 ⇒ I3 达标」这一步无效；③ **跨三轮**：R138/R139 的 **0.8992** 同源于同一构造（`runs/p3/r138_our_observer.json` 的 `ci.coverage_pointwise = 0.8992`）⇒ 签核单 B-3/R-4、README 的「X 逐点覆盖 0.8992」**同受覆盖**（该数字曾支撑 **M4 阻断项 6 的销号**）；④ 标准 5 的总体判定（有界 PARTIAL）不变，且本条**收紧**了它缺什么 |
| 处置方案（已实测确定可行） | 改用 `candidate/indpensim/v0.1/observe.py::coverage_check` 的 **μ ± 1.96σ** 口径 —— 区间来自**预测的 σ** 而非残差分位数 ⇒ 垃圾预测器 σ→0 时覆盖率趋 **0.0000**，正常预测器给出名义覆盖率（X **0.1072** / P **0.3160**）⇒ **有判别力**。该函数**已存在**，只是多通道评估脚本没有采用它 |
| 纪律延伸 | **由分位数构造的区间，其覆盖率必然等于名义值 —— 这不是「达标」，是同义反复。** 凡引用覆盖率，必须同时引用**区间半宽**与**相对更简单基线的改善**；且必须做一次**零信息预测器对照**（把预测换成常数，看指标是否还「达标」）。另：**跨通道逐位相同是恒真的强信号** —— 本轮正是靠它发现本条 |

"""

# ---------------------------------------------------------------- 签核单内容
B15 = "| **B-15** | **B 档回退链实为单环** | M2 冻结四环（UKF → EnKF → MHE+稳态碳平衡 → 显式失败）中，**仅 EnKF 一环已实现**；MHE、稳态基线解算器、三条降级触发器**均未实现** ⇒ EnKF 发散时**无自动降级路径** | R160 源码盘点（`observe.py`/`soft_sensing.py`/`mcp_server.py`）；M2 §3/§4 原文 | **MHE + 稳态基线建议记为 V1+ 边界**（原始用途随 D-54 消亡）；**降级触发器建议本轮做**（I2 延伸：不许静默降级） |"

B16 = "| **B-16** | **I3 覆盖率是构造性恒真数字** | 置信区间由**残差自身 5%/95% 分位数**构造 ⇒ 对任意预测器（含**零信息**常数预测）恒报 ≈0.90；X/P/PAA/vis 四通道**逐位相同**（Δ=0.000000） | R160 探针 `runs/r160_i3_coverage_tautology.json`；三处同源代码行已定位 | **判决保留**（T3-1 三道硬门不依赖 coverage）；**「coverage 0.8995/0.8992 ⇒ 达标」这步论证须撤回**，改引**区间半宽** + **nRMSE 改善**；处置口径改用 `observe.py::coverage_check` 的 **μ ± 1.96σ**（已实测有判别力：垃圾 0.0000 vs 正常 0.1072/0.3160） |"

B17 = "| **B-17** | **README 传播了已撤回结论** | `README.md:165-166` 仍写「A2 严格支配 ⇒ 优先做两点校准」—— 已被 **D-74 撤回**（剔除退化批后 A2 20.47% 劣于 C0 10.29%） | R159 证伪 + R160 实测 | **必须改写**：保留「不引入 Raman 资产」，撤回「优先做两点校准」；失真批 PAA 估值目前**无已验证简单解**，C0 是当前最好候选但**无在线可得判别器** ⇒ V1+ |"

R10 = "| **R-10** | **第三次回溯的结论（2026-11-05）**：初始方案（A+B+C 全量）中 **A 档完成并超额、C 档已批准并完成**；**B 档参数估计器侧完成但回退链只 1/3 环**（D-75）；**唯一阻塞 `cap` 升级的仍是被暂缓的平台看板口径（D-65）**。另新证伪 **D-78**（I3 覆盖率构造性恒真，判决层不受影响但论证层须撤回） | `docs/goal_backtrace_check_v3.md`、`docs/r160_round_report.md`；GOAL §4 五条标准、M0-M5 里程碑、B 档方法族实现盘点 |"


def main():
    # ================================================================ 台账
    lines, raw, nl = _read(LEDGER)
    # 插入到「## 三、本轮新增」之后（紧接 D-74 段）
    anchor = "### D-74"
    i = _find(lines, anchor)
    assert i > 0, "未找到 D-74"
    # 找到 D-74 段的结束（下一个以 ### 开头的行）
    j = i + 1
    while j < len(lines) and not lines[j].startswith("### ") and not lines[j].startswith("## "):
        j += 1
    block = (D75 + "\n" + D76 + "\n" + D77 + "\n" + D78).rstrip("\n").split("\n")
    # 幂等：**逐条**检查（一段失败可能只写入了一部分）
    missing = [b for b in block if b.startswith("### D-")
               and not any(l.startswith(b[:9]) for l in lines)]
    if not missing:
        print("[skip] 台账已有 D-75/D-76/D-77/D-78")
    else:
        print("[fix] 台账缺：%s" % [b[:8] for b in missing])
        # 把缺失的条目**插到 D-74 段之后**（保持 R160 四条相邻）
        lines = lines[:j] + missing + [""] + lines[j:]
        n0, n1 = _write(LEDGER, lines, raw, nl)
        print("[ok] 台账补入缺失条目（%d -> %d 行）" % (n0, n1))

    # 台账总表补 4 行
    lines, raw, nl = _read(LEDGER)
    added = 0
    for row in [
        "| D-75 | B 档回退链**实为单环**（MHE/稳态基线解算器/降级触发器均未实现） | L2 | 🔴 **R160 新增**（源码盘点；MHE 建议记 V1+ 边界，降级触发器建议做） |",
        "| D-76 | README **传播了 R158 已被 D-74 撤回的 A2 结论** | L2 | 🔴 **R160 新增**（README:165-166） |",
        "| D-77 | README / 契约头部 / state.yaml 三处**版本与表述滞后** | L1 | 🟢 **R160 新增** |",
        "| D-78 | I3「置信区间覆盖率」**构造性恒真** ⇒ 不可作达标证据 | L2 | 🔴 **R160 新增**（零信息预测器对照 Δ=0.000000；判决层不受影响） |",
    ]:
        key = row.split("|")[1].strip()
        if any(l.startswith("| %s |" % key) for l in lines):
            continue
        # 插到 D-74 那行之后
        i = _find(lines, "| D-74 |")
        assert i > 0, "总表未找到 D-74 行"
        lines = lines[:i + 1] + [row] + lines[i + 1:]
        added += 1
    if added:
        n0, n1 = _write(LEDGER, lines, raw, nl)
        print("[ok] 台账总表补 %d 行" % added)
    else:
        print("[skip] 台账总表已齐")

    # 纪律追加第 15/16 条（锚点用**纪律条目的编号行**，避免命中 D-78 正文）
    lines, raw, nl = _read(LEDGER)
    if any(l.startswith("15. **由分位数构造的区间") for l in lines):
        print("[skip] 台账纪律已含第 15 条")
    else:
        tail = """15. **由分位数构造的区间，其覆盖率必然等于名义值** —— 这不是「达标」，是同义反复。
    凡引用覆盖率，必须同时引用**区间半宽**与**相对更简单基线的改善**；且必须做一次
    **零信息预测器对照**（把预测换成常数，看指标是否还"达标"）。本轮即用这个对照
    把一个跨三轮、支撑过 M4 阻断项 6 销号的数字证伪（D-78）。
16. **跨通道逐位相同是恒真的强信号** —— 本轮正是靠「X/P/PAA/vis 四通道 coverage 逐位相同」
    发现 D-78。任何在多通道/多批次上汇总的指标，若不同通道给出**逐位相同**的值
    ⇒ 必须先假设它是构造产物，再去反查它的计算路径。
17. **冻结的实现计划不等于实现了的链路** —— M2「回退链冻结」只冻结了**设计**；
    回溯时必须**逐环核对源码**，不能凭「文档已冻结」推断「链路已闭合」（D-75）。
18. **治理层更新必须有一份「受影响文件清单」**，且**逐文件核对** ——
    尤其 README / 交接文档这类**面向人**的入口（D-76：R159 更新了台账/签核单/路线图/契约/state，
    却漏了 README ⇒ 撤回的结论继续对外流传）。"""
        # 插到「## 六、纪律」节末尾（该节是文件最后一个二级标题）
        i = _find(lines, "## 六、纪律")
        assert i > 0, "台账未找到「## 六、纪律」"
        # 该节内容到下一个 "## " 之前；本节是最后一节 ⇒ 直接追加到文末
        lines = lines[:] + [""] + tail.split("\n")
        n0, n1 = _write(LEDGER, lines, raw, nl)
        print("[ok] 台账纪律追加第 15–18 条（%d -> %d 行）" % (n0, n1))

    # ================================================================ 签核单
    lines, raw, nl = _read(SIGNOFF)
    added = 0
    for row in [B15, B16, B17]:
        key = row.split("|")[1].strip().replace("**", "")
        if any(key in l for l in lines):
            continue
        _check_no_pipe(row, "签核单 %s" % key, ncol=5)
        # 插到 R-9 行之后
        i = _find(lines, "| **R-9** |")
        assert i > 0, "签核单未找到 R-9 行"
        lines = lines[:i + 1] + [row] + lines[i + 1:]
        added += 1
    # R-10
    if not any("**R-10**" in l for l in lines):
        _check_no_pipe(R10, "签核单 R-10", ncol=3)
        i = _find(lines, "| **R-9** |")
        lines = lines[:i + 1] + [R10] + lines[i + 1:]
        added += 1
    if added:
        n0, n1 = _write(SIGNOFF, lines, raw, nl)
        print("[ok] 签核单新增 %d 行（B-15/B-16/B-17/R-10）" % added)
    else:
        print("[skip] 签核单已齐")

    # 修订 B-3 的 coverage 口径（撤回 0.8992 作为达标证据）
    lines, raw, nl = _read(SIGNOFF)
    hit = False
    for i, l in enumerate(lines):
        if l.startswith("| **B-3** |"):
            if "D-78" in l:
                print("[skip] B-3 已含 D-78 修订")
            else:
                lines[i] = l.replace(
                    "X 逐点覆盖 **0.8992**（90% 区间 [−6.82%, +9.45%]）",
                    "X 90% 区间 [−6.82%, +9.45%]（**半宽 8.14%**、nRMSE **3.17%**、86/86 <15%）；"
                    "**R160 修订（D-78）**：原记「逐点覆盖 0.8992」是**构造性恒真数字**"
                    "（区间由残差分位数构造 ⇒ 对任意预测器恒 ≈0.90）⇒ **不得作为达标证据**，"
                    "达标论据改用**区间半宽 + nRMSE 改善**")
                hit = True
            break
    if hit:
        n0, n1 = _write(SIGNOFF, lines, raw, nl)
        print("[ok] 签核单 B-3 的 coverage 口径已修订")

    # ================================================================ 路线图
    lines, raw, nl = _read(ROADMAP)
    if "## 八、R160 第三次回溯" in "\n".join(lines):
        print("[skip] 路线图已有 R160 段")
    else:
        block = """## 八、R160 第三次回溯（2026-11-05）

> 依据 `GOAL.md` v1.0 + `docs/01_设计讨论` §4 + `docs/M2_method_selection.md` §3/§4 三份原文，
> 对 v2（2026-10-27）之后的 R129–R159 共 31 轮变更做**全量回溯**。
> 完整对标见 `docs/goal_backtrace_check_v3.md`；本节只给**结论与新增任务项**。

### 8.1 五条标准与里程碑的当前判定

| # | 标准 | 判定 | 与 v2 的差异 |
|---|---|---|---|
| 1 | 产量 ≤±5% | ✅ PASS（RMSE 2.345%、86/86） | 不变 |
| 2 | 轨迹级 | 🟡 有界 PARTIAL | X 由 B 档交付、S 封边界、P 缺口定量化 |
| 3 | 守恒 | ✅ PASS | 不变 |
| 4 | 故障特征 | ✅ PASS（改判） | R143 撤销原命题 |
| 5 | I2 + I3 | 🟡 有界 PARTIAL | **R160 新证伪 D-78**：coverage 是构造性恒真数字（判决保留、论证撤回） |

**里程碑**：M0–M4 实质完成；**M2 的回退链只 1/3 环**（D-75）；**M5 唯一欠账 = 看板对外口径（D-65，仍暂缓）**。

### 8.2 本轮新增任务项

| # | 事项 | 优先级 | 成本 | 判据 |
|---|---|---|---|---|
| **R160-1** | **修 D-76**：README §4 的 Raman/PAA-PLS 行改写为 R159 修订表述 | 🔴 最高 | 5 min | README 不再出现「A2 严格支配 / 优先做两点校准」 |
| **R160-2** | **修 D-78 的引用口径**：签核单 B-3/R-4、README、路线图改引**区间半宽 + nRMSE 改善**，并标注 coverage 为构造性恒真 | 🔴 高 | 30 min | 三处不再以 coverage 作为达标证据 |
| **R160-3** | **补回退链降级触发器**（D-75 的一半） | 🟡 中 | 半天 | EnKF spread→0 / RMSE 越阈时**显式**输出降级标记（不许静默降级） |
| **R160-4** | **修 D-77 文档滞后**：契约头部 → v1.90、README §4/§5、state oq#6/#30 改写、oq#35 关闭 | 🟡 中 | 半天 | 三处口径一致 |
| **R160-5** | **D-66**：加 `pytest.ini` / `conftest.py` | 🟢 低 | 10 min | pytest 根路径解析稳定 |
| **R160-6** | **M1-遗留 oq#33/34**：rng 映射对照实验、alpha_kla 批次间随机性量化 | 🟢 低 | 各半天 | 补齐 M1 尾账 |
| **R160-7** | **U-1a/U-1b（MHE + 稳态基线解算器）** | — | 大 | **建议直接记为 V1+ 边界、不做**（原始用途已随 D-54 消亡） |

> **cap 口径不变**（L2 prototype conditional）；**D-65 仍未闭合**（平台暂缓）。

"""
        lines = lines[:] + block.rstrip("\n").split("\n") + [""]
        n0, n1 = _write(ROADMAP, lines, raw, nl)
        print("[ok] 路线图追加 R160 段（%d -> %d 行）" % (n0, n1))

    # ================================================================ 契约
    lines, raw, nl = _read(CONTRACT)
    if "| v1.90 |" in "\n".join(lines):
        print("[skip] 契约已有 v1.90")
    else:
        row = ("| v1.90 | R160：**第三次全面回溯 + D-75/D-76/D-77/D-78**（v1.89 之后的**事实变更**；"
               "不改写历史记录）—— ①**回溯盘点**：依据 GOAL.md v1.0 + 设计文档 §4 + M2 §3/§4 三份原文，"
               "对 R129–R159 共 31 轮变更做全量回溯 ⇒ **A 档完成并超额、C 档已批准并完成、"
               "B 档回退链只 1/3 环**（D-75）；**唯一阻塞 cap 升级的仍是被暂缓的平台看板口径（D-65）**。"
               "②**D-75**：B 档回退链实为单环 —— MHE、稳态基线解算器、三条降级触发器**均未实现**"
               "（源码 grep `mhe`/`moving_horizon`/`fallback`/`degrade` 全空）⇒ EnKF 发散时无自动降级路径。"
               "③**D-78**：I3「置信区间覆盖率」是**构造性恒真指标** —— 区间由残差自身 5%/95% 分位数构造"
               "（`r157_i3_channels.py:212` / `r138_our_observer.py:162` / `r139_observer_v2.py:173` 三处同构造）"
               "⇒ 零信息常数预测器与正常预测器的覆盖率**逐位相同**（4 通道 Δ=0.000000，均 0.899549）；"
               "**判决层保留**（T3-1 三道硬门不依赖 coverage）但**论证层须撤回**"
               "（「coverage 0.8995/0.8992 ⇒ 达标」无效）⇒ 处置改用 `observe.py::coverage_check` 的"
               "**μ ± 1.96σ** 口径（已实测有判别力：垃圾 0.0000 vs 正常 0.1072/0.3160）。"
               "④**D-76**：README 传播了 R158 已被 D-74 撤回的 A2 结论。⑤**D-77**：README/契约头部/state 三处滞后。"
               "**引擎零改动**；对标文档 `docs/goal_backtrace_check_v3.md`、报告 `docs/r160_round_report.md` |")
        _check_no_pipe(row, "契约 v1.90", ncol=2)
        # 插到版本表最后一行之后
        idx = -1
        for i, l in enumerate(lines):
            if l.startswith("| v1."):
                idx = i
        assert idx > 0, "契约版本表未找到"
        lines = lines[:idx + 1] + [row] + lines[idx + 1:]
        # 头部状态同步 v1.82 -> v1.90
        for i, l in enumerate(lines):
            if l.startswith("> 状态：**v1.82**"):
                lines[i] = l.replace("> 状态：**v1.82**", "> 状态：**v1.90**")
                break
        n0, n1 = _write(CONTRACT, lines, raw, nl)
        print("[ok] 契约追加 v1.90 并同步头部（%d -> %d 行）" % (n0, n1))

    # ================================================================ state.yaml
    lines, raw, nl = _read(STATE)
    new_oq = [
        "R160/D-75 B 档回退链实为单环：M2 冻结四环 UKF→EnKF→MHE+稳态碳平衡→显式失败中仅 EnKF 已实现；MHE、稳态基线解算器、三条降级触发器均未实现（源码 grep 全空）⇒ EnKF 发散时无自动降级路径 ⇒ MHE 与稳态基线建议记为 V1+ 边界，降级触发器建议本轮做",
        "R160/D-76 README 传播了 R158 已被 D-74 撤回的 A2 结论（README 第 165 至 166 行仍写 A2 严格支配与优先做两点校准）⇒ R159 治理层更新清单漏了 README ⇒ 须改写",
        "R160/D-77 文档滞后三处：README 第 4 节标题写契约 v1.87 而实为 v1.89；README 第 5 节指向 r156 报告与台账而应为 r159 与 r157；ENGINE_CONTRACT 头部状态停在 v1.82 而版本表已到 v1.89；state 的 open_questions 第 6 与第 30 条表述过时",
        "R160/D-78 I3 置信区间覆盖率是构造性恒真指标：区间由残差自身 5 至 95 百分位构造 ⇒ 对任意预测器含零信息常数预测恒报约 0.90；X P PAA vis 四通道逐位相同且零信息对照差为 0.000000 ⇒ 判决层保留但 coverage 作为达标证据的论证须撤回；处置改用 observe.py 的 mu 加减 1.96 sigma 口径",
    ]
    added = 0
    for q in new_oq:
        if any(q[:40] in l for l in lines):
            continue
        _check_plain(q)
        i = _find(lines, "open_questions:")
        assert i > 0, "state.yaml 未找到 open_questions"
        # 找到该块的元素列表（缩进 2 空格的 "- " 行）
        j = i + 1
        while j < len(lines) and (lines[j].startswith("  - ") or lines[j].strip() == ""):
            j += 1
        lines = lines[:j - 1] + ["  - " + q] + lines[j - 1:]
        added += 1
    if added:
        n0, n1 = _write(STATE, lines, raw, nl)
        print("[ok] state.yaml open_questions +%d" % added)
    else:
        print("[skip] state.yaml open_questions 已含")

    # artifacts
    lines, raw, nl = _read(STATE)
    art_added = 0
    for key, val in [
        ("r160_i3_coverage_tautology", "runs/r160_i3_coverage_tautology.json"),
        ("goal_backtrace_check_v3", "docs/goal_backtrace_check_v3.md"),
    ]:
        if any(l.strip().startswith(key + ":") for l in lines):
            continue
        _check_artifacts_value("%s: %s" % (key, val))
        i = _find(lines, "artifacts:")
        assert i > 0, "state.yaml 未找到 artifacts"
        j = i + 1
        while j < len(lines) and (lines[j].startswith("  ") and lines[j].strip()):
            j += 1
        lines = lines[:j] + ["  %s: %s" % (key, val)] + lines[j:]
        art_added += 1
    if art_added:
        n0, n1 = _write(STATE, lines, raw, nl)
        print("[ok] state.yaml artifacts +%d" % art_added)
    else:
        print("[skip] state.yaml artifacts 已含")

    # 验证 YAML 可解析
    import yaml
    d = yaml.safe_load(open(STATE, encoding="utf-8"))
    print("[ok] state.yaml 解析通过：oq=%d art=%d cap=%s"
          % (len(d["open_questions"]), len(d["artifacts"]), d["cap"]["level"]))

    # ================================================================ README
    lines, raw, nl = _read(README)
    changed = False
    # ① 修 D-76：撤回表述
    for i, l in enumerate(lines):
        if "严格支配" in l and "两点校准" in l:
            lines[i] = ("  **R159 修订（D-74）**：原称「A2 两点校准中位 0.49% 严格支配 PAT ⇒ 应优先做两点校准」"
                        "—— **该支配结论已撤回**：失真批 41 批中 **29 批化验值退化**（V6 批 61–90 的 `PAA_offline` "
                        "是占位值），A2 在其上退化为常数预测且连常数基线都打不过；**剔除退化批后 A2 20.47% 劣于 "
                        "C0 10.29%** ⇒ 「优先做两点校准」**不成立**。**保留结论**：「而非引入 Raman 资产」成立。"
                        "失真批 PAA 估值**目前没有已验证的简单解**；C0（锚在引擎 PAA 上的逐点比例锚定，有信息批中位 "
                        "10.29%）是当前最好候选，但需化验锚点且**无在线可得判别器** ⇒ V1+ 候选。")
            changed = True
            break
    # ② 修 D-77：§4 标题版本 + §5 文档指向
    for i, l in enumerate(lines):
        if l.startswith("## 4. 当前状态（契约 v1.87）"):
            lines[i] = "## 4. 当前状态（契约 v1.90）"
            changed = True
        if l.startswith("5. `docs/r156_round_report.md`"):
            lines[i] = "5. `docs/r160_round_report.md` —— 最近一轮；历史报告按编号倒序"
            changed = True
        if l.startswith("6. `docs/r156_debt_ledger.md`"):
            lines[i] = ("6. `docs/r157_debt_ledger.md` —— **未闭项清单，接手先读这个**"
                        "（L2 阻断项：**D-65 平台看板口径**（唯一治理条件未闭合，用户暂缓）/ **D-75 B 档回退链单环** / "
                        "**D-78 I3 覆盖率构造性恒真** / D-52 双稳态 / D-53 残糖不可辨识 / D-64 P 与 PAA 软测量不可辨识 / "
                        "D-54 缺葡萄糖闭环（L3）；**R160 已完成第三次全面回溯**，见 `docs/goal_backtrace_check_v3.md`）")
            changed = True
    if changed:
        n0, n1 = _write(README, lines, raw, nl)
        print("[ok] README 已修 D-76/D-77（%d -> %d 行）" % (n0, n1))
    else:
        print("[skip] README 已是修订后状态")

    print("\n[R160] 治理层登记完成")


if __name__ == "__main__":
    main()
