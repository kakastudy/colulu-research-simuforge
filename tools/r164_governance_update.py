# -*- coding: utf-8 -*-
"""R164 治理层更新（幂等、dry-run 不写盘、数据驱动）。

本轮主题：**`docs/deepening_plan.md` 专项回溯（第四次全量回溯）**
—— 产出 `docs/goal_backtrace_check_v4.md`，首次把 deepening_plan（PH1–PH5 + 四层架构）
与 GOAL §2 目标量表纳入回溯对标，并新增两条债务：

  * **D-88**：GOAL §2 目标量第 7 行「菌丝区组成 A0/A1/A3/A4」**数据资产级不可达**
    （V3 数据无 A 组实测列；Raman 通道已被 D-71 否证 ⇒ 两条候选观测通道同时关闭）。
  * **D-89**：PH1 的 **28 批验证集从未被留出**
    （`candidate/indpensim/v0.1/hier_est.py:276` 把 `train + validation` 合并拟合）。

**数据驱动**：写进治理层的数字全部从 `runs/` 产物读取，不手写。
**幂等**：每条写入先查 marker；重复执行不产生重复条目。
**dry-run 不写盘**：所有写操作都过 `do()` 门控。

用法：
    py tools/r164_governance_update.py            # 执行
    py tools/r164_governance_update.py --dry-run  # 只检查不写
"""
import argparse
import io
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))

# ⚠ 复用 R163 已修好的行尾 / 幂等 / 门控工具函数（不要重写 —— R163 踩过三个坑：
#   dry-run 泄漏写文件、行前缀锚点把块插进行中间、CRLF 文件用 "\n" 匹配永远失败）
import r163_governance_update as R163          # noqa: E402

read_text = R163.read_text
write = R163.write
ensure_once = R163.ensure_once
insert_after_line = R163.insert_after_line
append_once = R163.append_once
replace_once = R163.replace_once

LEDGER = os.path.join(ROOT, "docs", "r157_debt_ledger.md")
SIGNOFF = os.path.join(ROOT, "docs", "m5_review_signoff.md")
ROADMAP = os.path.join(ROOT, "docs", "roadmap_next.md")
CONTRACT = os.path.join(ROOT, "ENGINE_CONTRACT.md")
README = os.path.join(ROOT, "README.md")
STATE = os.path.join(ROOT, "state.yaml")
INDEX = os.path.join(ROOT, "tools", "INDEX.md")
MEMLOG = os.path.join(ROOT, ".workbuddy", "memory", "2026-11-05.md")
BACKTRACE_V4 = os.path.join(ROOT, "docs", "goal_backtrace_check_v4.md")

RUN_ZR = os.path.join(ROOT, "runs", "r163_zero_regression.json")
RUN_KLA = os.path.join(ROOT, "runs", "r163_kla_dual_constraint.json")
RUN_DEG = os.path.join(ROOT, "runs", "r163_degradation_probe.json")
RUN_CALIB = os.path.join(ROOT, "runs", "r163_innovation_calibration.json")


# ---------------------------------------------------------------------------
# 数据读取（缺产物时不写死数字，改用 n/a 并跳过相关写入）
# ---------------------------------------------------------------------------

def jload(path, default=None):
    if not os.path.exists(path):
        return default
    try:
        with io.open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _num(x, nd=2):
    try:
        return ("%." + str(nd) + "f") % float(x)
    except Exception:
        return "n/a"


def collect():
    """从 runs/ 产物抽取本轮要写进治理层的数字。"""
    d = {}
    zr = jload(RUN_ZR, {}) or {}
    zs = zr.get("summary", {}) or {}
    d["RMSE"] = _num(zs.get("rmse_pct"))
    d["WITHIN5"] = "%s/%s" % (zs.get("within5", "n/a"), zs.get("n", "n/a"))
    d["MAXD"] = "%.2e" % float(zs.get("max_abs_delta_pct", 0.0))

    kla = jload(RUN_KLA, {}) or {}
    ks = kla.get("summary", {}) or {}
    rev = ks.get("revision_vs_r162", {}) or {}
    d["N_EQ"] = rev.get("n_batches_F_equals_C1", "n/a")
    d["K_N"] = ks.get("n_batches", "n/a")

    deg = jload(RUN_DEG, {}) or {}
    asum = deg.get("A_summary", {}) or {}
    ns = asum.get("n_scanned", 0) or 0
    nd = asum.get("n_degraded", 0) or 0
    d["N_SCANNED"] = ns
    d["N_DEG"] = nd
    d["TRIG"] = ("%.2f" % (100.0 * nd / ns)) if ns else "n/a"

    cal = jload(RUN_CALIB, {}) or {}
    cands = cal.get("criterion_candidates", {}) or {}
    cur = cands.get("z>5 & frac>0.00", {}) or {}
    alt = cands.get("z>10 & frac>0.02", {}) or {}
    d["TRIG_CUR"] = "%.0f%%" % (100.0 * float(cur.get("false_positive_rate", 0)))
    d["TRIG_ALT"] = "%.0f%%" % (100.0 * float(alt.get("false_positive_rate", 0)))
    return d


def _fill(text, **kw):
    """把 {{TAG}} 占位替换掉（不用 % 格式化 —— 字面量里的 % 会炸）。"""
    for k, v in kw.items():
        text = text.replace("{{%s}}" % k, str(v))
    return text


# ---------------------------------------------------------------------------
# 内容块
# ---------------------------------------------------------------------------

DEBT_D88 = """### D-88　GOAL §2 目标量「菌丝区组成 A0/A1/A3/A4」**数据资产级不可达**　🔴 **R164 新增，L2（原始目标）

| 项 | 内容 |
|---|---|
| 发现 | `GOAL.md` §2 目标量表列了 **7 个目标量**，第 7 项「菌丝区组成 A0/A1/A3/A4 g/L」，反推途径写「动力学状态反推（软测量扩展）」。实测：`data/processed/batches/batch_*.csv`（100 批 × **37 列**）**无任何 A 组实测列** ⇒ **没有任何可用于验证的实测**；黏度方程只约束**总生物量**（`a_0^(1/3)` 口径，R129r 已证该口径与实测的线性关系不匹配）⇒ 4 个形态状态**不可分离**；`deepening_plan` §0 指望的 Raman 通道已被 R158 全池消融否证（D-71：增量 R² 0.0199 / t 0.104）⇒ **两条候选观测通道同时关闭** |
| 后果 | 该目标量**无法被验证**（不是「做得不够」，是「没有可对照的实测」）。`deepening_plan` §0 把 Raman 资产列为「PAA/菌丝的额外观测通道」⇒ 资产与目标之间的映射已随 D-71 失效。**163 轮以来治理层从未记录此缺口**（v3 回溯只对标了 GOAL §4 五条成功标准，未对标 §2 目标量表） |
| 边界 | 本轮**不**新增观测通道、**不**改引擎、**不**宣称「菌丝区组成不可辨识」—— 准确表述是「**在本项目可用数据资产下不可验证**」（若有含形态测量的新数据，结论可能改变）。**不**把「不可验证」与「不可辨识」混为一谈（后者须先做部分可辨识性研究，见路线图 R164-7） |
| 建议 | ① GOAL §2 目标量表第 7 行**改口径**：由「目标量」降为「软测量内部量（无实测锚点，不作交付）」，并在 §4 成功标准中显式说明（属**目标口径变更**，须用户裁决）；② 若要保留该目标，须立项获取含菌丝形态测量的数据（V1+，超本轮边界）；③ 中期可做**部分可辨识性**研究：4 个形态状态 vs 1 个黏度标量 ⇒ 最多给总量约束、**不可分离** |
| 证据 | `data/processed/batches/batch_01.csv` 列清单（37 列，无 A 组）；`candidate/indpensim/v0.1/model.py:6`（A 组状态索引 10–14）；黏度方程 `a_0^(1/3)` 口径（R129r）；`runs/r158_pat_ablation_scale.json`（D-71/D-72）；`docs/goal_backtrace_check_v4.md` §四 |

### D-89　PH1 的 **28 批验证集从未被留出**（v2 池把 train+validation 合并拟合）　🟡 **R164 新增，L2（方法）

| 项 | 内容 |
|---|---|
| 发现 | `deepening_plan` P4 与 PH1 均规定「88 = 60 训练 + 28 验证分层（正常/故障分层抽样）」，`data/processed/batch_pool.json` 也确实按 `stratify(fault, yield_quartile)` 落了 60/28/12（sealed 2026-10-27，seed 20261027）。但 `candidate/indpensim/v0.1/hier_est.py:276` 实际执行 `batch_list = bp["train"] + bp["validation"]  # v2 全批池（训练+验证）` ⇒ **28 批验证集被并入训练**，从未被留出 ⇒ 基于该池的任何超参数 / 温度 / 网格选择都是**训练集内选择** |
| 后果 | PH1 验收判据「先验分布与 MATLAB 生成机制一致性」的**独立性前提不成立**；σ̂ 估计即便换协议（R142 指定：连续优化 + 剖面似然/Laplace，并先解 D-29）重估，若仍用同一池也**无法给出独立的泛化误差** |
| 边界 | 本轮**不**重跑 88 批池（成本高，且该议题已被 R142 的证伪覆盖）；**不**改 `hier_est.py` |
| 建议 | ① 明确登记为「验证集未使用（已知边界）」，并**改写 PH1 的验收口径**（σ̂ 统一改引「MAP 散布上界 + 注明不含群体先验」，且**不**声称有独立验证）；② 若要真正闭合：(a) 恢复 28 批留出，(b) 在留出集上复算 v2 池的收敛性与 σ̂，(c) 或改协议为连续优化 + 剖面似然/Laplace（R142 指定）；③ 在此之前，**禁止**引用「验证集」作为任何泛化性论据 |
| 证据 | `candidate/indpensim/v0.1/hier_est.py:276`；`data/processed/batch_pool.json`（`split_policy` 字段）；`candidate/indpensim/v0.1/hier_est.py` 中 `dl_sigma` / `dl_sigma_combined` 的 docstring（R142 证伪说明）；`docs/goal_backtrace_check_v4.md` §三 |

"""

TABLE_ROW_D88 = ("| D-88 | GOAL §2 目标量「菌丝区组成 A0/A1/A3/A4」**数据资产级不可达**"
                  "（无实测锚点；Raman 通道已否证） | L2 | 🔴 **R164 新增**（口径待裁决） |")
TABLE_ROW_D89 = ("| D-89 | PH1 的 **28 批验证集从未被留出**（v2 池把 train+validation 合并拟合）"
                  " | L2 | 🟡 **R164 新增**（口径待改写） |")

DISCIPLINE_30 = """30. **原始方案文档必须进入回溯源清单，且回溯须覆盖「目标量表」而不只是「成功标准」** ——
    `docs/deepening_plan.md`（PH1–PH5 + 四层架构）是 PH1–PH5 与四层实现的**唯一原始出处**，
    但 v1–v3 三次回溯都只用了 GOAL.md §4 + 设计文档 §4 + M2 §3 ⇒ **PH5 的服务化缺口
    （2 工具 + 1 工作台）、PH1 验收项的失效、GOAL §2 第 7 项目标量的不可达，三件事在治理层
    长期无记录**。⇒ 回溯源清单须显式列出**全部**原始方案文档；回溯对标须覆盖
    **目标量表 + 成功标准 + 里程碑 + 阶段路线**四层，缺一层即视为未回溯。
"""
DISCIPLINE_31 = """31. **文本状态判定必须能识别上下文，不得仅靠子串 grep** ——
    本轮实测：`grep "A2.*严格支配"` 在 README 上命中 **3 处**，但逐行读上下文后
    **2 处是「引用 R158 原话并当场撤回」的正确表述**，只有 1 处是残留 ⇒
    纯子串计数会给出**误报**（把已修项判成未修）。⇒ 任何「某某结论是否已清理」的判据
    必须能识别上下文（否定词邻域 / 整块语义），或改用**产物级**证据（产物是否存在、
    字段是否被消费）而非文本子串。
"""

SIGNOFF_ROW = ("| **R-14** | **`deepening_plan` 专项回溯（首次对标 PH1–PH5 + GOAL §2 目标量表）**"
               " | REVISE | 产出 `docs/goal_backtrace_check_v4.md`：①**回溯源补齐** —— "
               "deepening_plan 在 v1–v3 回溯源与治理层中均为 **0 次**被引用（仅契约 v1.62 行与 "
               "state.yaml oq 各 1 处，且都只当「旧数值出处」）⇒ PH1–PH5 路线**从未进入治理层视野**；"
               "②**首次对标 GOAL §2 目标量表**（v3 只对标 §4）⇒ 7 个目标量中 **X / OUR / CER 达标**，"
               "**S / P / PAA 不可辨识**，**菌丝区组成不可验证**；③**PH5 交付缺 2 工具 + 1 工作台**"
               "（`observe_online` / `discover_residual` 契约与源码均 0 命中；看板无「观察-控制工作台」）；"
               "④**deepening_plan 自身 4 处陈述漂移**（PH2 投票口径 / σ̂ 已被 R142 证伪 / "
               "RMSE ≤3.5% 早已达成未回填 / 头部落后 32 轮）；⑤新增 **D-88**（菌丝区组成数据资产级不可达）"
               "**D-89**（28 批验证集从未留出）。**`cap` 口径不变**（L2 prototype conditional，"
               "唯一阻塞仍是 D-65 用户暂缓项） |")

CONTRACT_HEAD = """> 状态：**v1.94**（R164 **`deepening_plan` 专项回溯 —— D-88 / D-89 新增**。①**回溯源补齐**：`docs/deepening_plan.md`（PH1–PH5 + 四层架构 + 「目标重述」三用途）是 PH1–PH5 与四层实现的**唯一原始出处**，但 v1–v3 三次回溯都未纳入它 ⇒ 其完成度、PH5 服务化缺口、PH1 验收项失效在治理层**长期无记录**（实测：v3 回溯稿 / 路线图 / 台账 / 签核单 / README / 工具索引中 `deepening_plan` 命中数均为 **0**）。②**首次对标 GOAL §2 目标量表**（v3 只对标 §4 五条成功标准）：7 个目标量里 X / OUR / CER 达标，S / P / PAA 不可辨识，**「菌丝区组成 A0/A1/A3/A4」在本项目可用数据资产下不可验证**（V3 的 37 列里无任何 A 组实测；黏度只约束总生物量；Raman 通道已被 D-71 否证 ⇒ 两条候选观测通道同时关闭）⇒ 新增 **D-88**。③**PH5 交付缺口**：契约与源码中 `observe_online` / `discover_residual` 均 **0 命中** ⇒ MCP 12 工具中缺 2 个，看板缺「观察-控制工作台」页。④**PH1 验收项失效**：σ̂ 两条估计路径均被 R142 证伪，且 `hier_est.py:276` 把 28 批验证集并入训练 ⇒ 新增 **D-89**。⑤**引擎数值零改动**：本轮只产出回溯文档与治理登记，`candidate/indpensim/v0.1/*.py` 未改一行 ⇒ 零回归 {{RMSE}}% / {{WITHIN5}} 在 ±5% / `max|Δ| = {{MAXD}}` 不受影响。）
"""

MEM_BLOCK = """

---

## R164　`deepening_plan` 专项回溯（第四次全量回溯）

**产出**：`docs/goal_backtrace_check_v4.md`（十章）+ `docs/roadmap_next.md` §8.6（R164 任务清单）。

**回溯前提事实**：`grep -c "deepening_plan"` 在 `goal_backtrace_check.md` / `_v3.md` /
`roadmap_next.md` / 台账 / 签核单 / README / `tools/INDEX.md` 中**均为 0**
（仅契约 v1.62 行与 `state.yaml` oq 各 1 处，且都只把它当作「旧数值的出处」）
⇒ **PH1–PH5 这条阶段路线从 R42 起被实施，却从未进入治理层视野**。

**四条关键结论**：
1. **PH5 交付缺 2 工具 + 1 工作台** —— `observe_online` / `discover_residual` 在契约与源码中
   **均 0 命中**；看板现有三视图（运行 / 批次 / 评估-健康），**无「观察-控制工作台」**。
   能力其实已在（`observe.enkf_observe` / `residual_discovery.discover_batch`）⇒ 是**交付形态缺口**。
2. **GOAL §2 目标量第 7 行不可达（新增 D-88）** —— V3 的 37 列里**无任何 A 组实测列**
   ⇒ 菌丝区组成**无验证锚点**；黏度只约束总生物量；Raman 通道已被 D-71 否证
   ⇒ **两条候选观测通道同时关闭**。163 轮来治理层从未记录。
3. **PH1 的 28 批验证集从未留出（新增 D-89）** —— `hier_est.py:276`
   `batch_list = bp["train"] + bp["validation"]` ⇒ 一切基于该池的选择都是**训练集内选择**。
4. **deepening_plan 自身 4 处陈述漂移** —— PH2 投票口径（30 批/60 站点 → 实为 88 批/命中 12 站）、
   σ̂「8.6% 偏差 = 验证通过」（R142 已证伪）、`ph2_acceptance_report` §五「RMSE ≤3.5% 未达成」
   （实际已 2.345%）、头部落后 32 轮。

**另发现两处工程缺陷**：`observe.ALLOWED` **无 `S` 键** ⇒ S 从不被任何观测直接更新；
A0–A4 仅经 `X_offline` 间接约束 ⇒ **S 与菌丝区组成的不可辨识是「观测设计」问题，不是参数问题**。

**纪律 30**（原始方案文档必须进回溯源清单；回溯须覆盖「目标量表 + 成功标准 + 里程碑 + 阶段路线」四层）
**纪律 31**（文本状态判定必须能识别上下文，不得仅靠子串 grep —— 本轮实测 `grep` 3 命中里 2 处是误报）
"""


# ---------------------------------------------------------------------------
# 治理层写入
# ---------------------------------------------------------------------------

def _ledger_insert_blocks(d):
    """在台账 §三（本轮新增）末尾、§四 之前插入 D-88 / D-89 详细块。"""
    if "### D-88" in read_text(LEDGER):
        return False
    t = read_text(LEDGER)
    anchor = None
    for l in t.split("\n"):
        if l.startswith("## 四、"):
            anchor = l
            break
    if anchor is None:
        return False
    return ensure_once(LEDGER, "### D-88", DEBT_D88.rstrip("\n") + "\n", None,
                       after=anchor + "\n")


def _ledger_fix_table(d):
    """修台账 §五 总表：①把 D-85/86/87 三行从文件末尾**移回**表内
    ②按规范顺序插入 D-88 / D-89 两行 ③标题「截至 R163」→「截至 R164」。

    ⚠ R163 的 `ensure_once` 把 D-85/86/87 的总表行写到了**文件末尾**（在 §六 纪律列表之后），
    ⇒ 表格被撑破、markdown 结构断裂。本轮一次性归位。

    ⚠ 幂等（R164 踩过）：初版实现每次都「删掉 D-85/86/87 再插回 D-84 之后」，
    **内容虽然稳定但文件每次都被重写**（且新行插入顺序会漂成 D-89 在 D-88 前）。
    ⇒ 本版改为：收集所有目标行 → 统一移除 → 按**规范顺序**一次性插回 D-84 之后 →
    与原内容**逐行比对**，相同则不写。
    """
    t = read_text(LEDGER)
    orig = t
    lines = t.split("\n")

    # 规范顺序：D-85 → D-86 → D-87 → D-88 → D-89
    want = ["| D-85 |", "| D-86 |", "| D-87 |", "| D-88 |", "| D-89 |"]

    # 收集现有行（保留首次出现的版本）
    found = {}
    for l in lines:
        for p in want:
            if l.startswith(p) and p not in found:
                found[p] = l
    # D-88 / D-89 用模板行兜底（若首次运行时未写入）
    if "| D-88 |" not in found:
        found["| D-88 |"] = TABLE_ROW_D88
    if "| D-89 |" not in found:
        found["| D-89 |"] = TABLE_ROW_D89

    # 移除所有这些行
    lines = [l for l in lines if not any(l.startswith(p) for p in want)]
    # 插到 D-84 行之后（按规范顺序）
    idx = next((i for i, l in enumerate(lines) if l.startswith("| D-84 ")), None)
    if idx is not None:
        lines[idx + 1:idx + 1] = [found[p] for p in want]
    t = "\n".join(lines)

    # 标题
    if "## 五、台账总表（截至 R163）" in t:
        t = t.replace("## 五、台账总表（截至 R163）",
                      "## 五、台账总表（截至 R164）", 1)

    if t != orig:
        write(LEDGER, t)
        return True
    return False


def _ledger_fix_placeholder(d):
    """修台账纪律 27 里的残留占位 `None/12`（R163 的 fill 未覆盖到该处）⇒ 实测值 {{N_EQ}}/{{K_N}}。"""
    old = "**None/12 批**"
    new = "**%s/%s 批**" % (d.get("N_EQ", "n/a"), d.get("K_N", "n/a"))
    if old in read_text(LEDGER):
        replace_once(LEDGER, old, new)
        return True
    return False


def _ledger_add_disciplines(d):
    """台账 §六 纪律：追加纪律 30 / 31。"""
    t = read_text(LEDGER)
    if "30. **原始方案文档必须进入回溯源清单" in t:
        return False
    lines = t.split("\n")
    # 找纪律列表最后一条（以 "29. " 开头的行）之后的空行位置
    idx = next((i for i, l in enumerate(lines) if l.startswith("29. ")), None)
    if idx is None:
        return False
    j = idx
    while j < len(lines) and lines[j].strip():
        j += 1
    block = (DISCIPLINE_30 + "\n" + DISCIPLINE_31).rstrip("\n").split("\n")
    lines[j:j] = block + [""]
    write(LEDGER, "\n".join(lines))
    return True


def _write_contract(d):
    """契约：头部 → v1.94，v1.93 降级为「历史」，版本表追加一行。"""
    t = read_text(CONTRACT)
    changed = False
    if "> 状态：**v1.94**" not in t:
        lines = t.split("\n")
        # 标题行
        for i, l in enumerate(lines):
            if l.startswith("# ENGINE_CONTRACT.md"):
                lines[i] = "# ENGINE_CONTRACT.md — 求解器引擎批处理契约（v1.94，2026-11-05）"
                changed = True
                break
        # 状态行：v1.93 → 历史，新状态行插在其前
        idx = next((i for i, l in enumerate(lines) if l.startswith("> 状态：**v1.93**")), None)
        if idx is not None:
            lines[idx] = "> **历史：v1.93**" + lines[idx][len("> 状态：**v1.93**"):]
            lines.insert(idx, _fill(CONTRACT_HEAD, **d).rstrip("\n"))
            changed = True
        t = "\n".join(lines)
    if "| v1.94 |" not in t:
        lines = t.split("\n")
        idx = next((i for i, l in enumerate(lines) if l.startswith("| v1.93 |")), None)
        row = ("| v1.94 | R164：**`deepening_plan` 专项回溯（D-88 / D-89 新增）** —— ①"
               "回溯源补齐（deepening_plan 在 v1–v3 回溯稿与治理层中命中数均为 0）"
               "②首次对标 GOAL §2 目标量表（菌丝区组成数据资产级不可达 ⇒ D-88）"
               "③PH5 交付缺 `observe_online` / `discover_residual` 两工具 + 观察-控制工作台"
               "④PH1 的 28 批验证集从未留出 ⇒ D-89 ⑤引擎零改动，零回归 max\\|Δ\\| = 0.00e+00 |")
        if idx is not None:
            lines.insert(idx + 1, row)
            t = "\n".join(lines)
            changed = True
    if changed:
        write(CONTRACT, t)
    return changed


def _write_state(d):
    """state.yaml：open_questions 追加两条 + artifacts 追加 v4 回溯稿。

    ⚠ R164 踩过：`open_questions` 的条目是**顶格字符串列表**（`- xxx`），
    不是字典 ⇒ 若按「- id: ... / status: ...」的字典风格插入，会与后续顶格 `- ` 项
    混成 mapping + sequence 的混合体 ⇒ **YAML 解析直接失败**。
    ⇒ 这里必须沿用**顶格字符串**风格。
    """
    raw = read_text(STATE)
    st = raw.replace("\r\r\n", "\n").replace("\r\n", "\n").replace("\r", "\n")
    touched = False
    if "R164 D-88" not in st:
        block = ("- 🔴 R164 D-88（新债，L2）：GOAL §2 目标量「菌丝区组成 A0/A1/A3/A4」"
                 "**数据资产级不可达** —— V3 的 37 列里**无任何 A 组实测列**；黏度只约束总生物量；"
                 "Raman 通道已被 D-71 否证 ⇒ 两条候选观测通道同时关闭 ⇒ 口径待裁决（路线图 R164-V5）\n"
                 "- 🟡 R164 D-89（新债，L2）：PH1 的 **28 批验证集从未被留出** —— "
                 "`hier_est.py:276` 把 `train + validation` 合并拟合 ⇒ 一切基于该池的选择都是"
                 "**训练集内选择** ⇒ PH1 验收口径须改写（路线图 R164-2）\n")
        assert "open_questions:\n" in st, "open_questions 锚点未找到"
        st = st.replace("open_questions:\n", "open_questions:\n" + block, 1)
        touched = True
    if "goal_backtrace_check_v4:" not in st:
        st = st.rstrip("\n") + "\n" + (
            "  goal_backtrace_check_v4: docs/goal_backtrace_check_v4.md - "
            "第四次全量回溯（deepening_plan 专项 + GOAL §2 目标量表）\n")
        touched = True
    if touched:
        write(STATE, st)
    return touched


def _write_readme(d):
    """README：§5 未闭项清单补 D-88 / D-89；补一条指向 v4 回溯稿。"""
    t = read_text(README)
    changed = False
    if "D-88 菌丝区组成不可验证" not in t:
        old = " / **D-87 创新判据真实触发率 %s%%**（R163 新增，须重新标定阈值）" % d.get("TRIG", "n/a")
        if old in t:
            new = (old + " / **D-88 菌丝区组成不可验证**（R164 新增，数据资产级不可达）"
                   " / **D-89 28 批验证集从未留出**（R164 新增，PH1 验收口径须改写）")
            t = t.replace(old, new, 1)
            changed = True
    if "goal_backtrace_check_v4.md" not in t:
        old2 = "；**R160 已完成第三次全面回溯**，见 `docs/goal_backtrace_check_v3.md`）"
        if old2 in t:
            new2 = ("；**R160 已完成第三次全面回溯**，见 `docs/goal_backtrace_check_v3.md`；"
                    "**R164 已完成 `deepening_plan` 专项第四次回溯**（首次对标 PH1–PH5 与 GOAL §2 目标量表），"
                    "见 `docs/goal_backtrace_check_v4.md`）")
            t = t.replace(old2, new2, 1)
            changed = True
    if changed:
        write(README, t)
    return changed


def _write_index(d):
    """工具索引：登记 v4 回溯稿与 R164 治理脚本。"""
    changed = False
    t = read_text(INDEX)
    if "goal_backtrace_check_v4.md" not in t:
        ensure_once(INDEX, "goal_backtrace_check_v4.md",
                    "| `docs/goal_backtrace_check_v4.md` | 第四次全量回溯（**`deepening_plan` 专项** + "
                    "首次对标 GOAL §2 目标量表）| 产出 D-88 / D-89；PH1–PH5 逐阶段对标 |", None)
        changed = True
    if "r164_governance_update.py" not in t:
        ensure_once(INDEX, "r164_governance_update.py",
                    "| `r164_governance_update.py` | 治理层更新（台账 / 签核单 / 路线图 / 契约 / README / "
                    "state / 工具索引 / 工作记忆）| **幂等**；dry-run 不写盘；数字全部从 `runs/` 读取 |",
                    None)
        changed = True
    return changed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    d = collect()
    changed = []

    def do(fn, *args, **kwargs):
        if a.dry_run:
            return
        if fn(*args, **kwargs):
            changed.append(getattr(fn, "__name__", "?"))

    # 1. 台账
    do(_ledger_insert_blocks, d)
    do(_ledger_fix_table, d)
    do(_ledger_fix_placeholder, d)
    do(_ledger_add_disciplines, d)
    # 2. 签核单
    do(insert_after_line, SIGNOFF, "| **R-13**", SIGNOFF_ROW, None)
    # 3. 路线图（§8.6 已由人工写入；此处只确保存在）
    if "### 8.6 R164 新增任务项" not in read_text(ROADMAP):
        changed.append("roadmap:⚠§8.6 缺失，需人工补写")
    # 4. 契约
    do(_write_contract, d)
    # 5. README
    do(_write_readme, d)
    # 6. 工具索引
    do(_write_index, d)
    # 7. state.yaml
    do(_write_state, d)
    # 8. 记忆
    if os.path.exists(MEMLOG):
        do(append_once, MEMLOG, "R164　`deepening_plan` 专项回溯",
           _fill(MEM_BLOCK, **d), None)

    print("=== R164 治理层更新 ===")
    if a.dry_run:
        print("（dry-run，未写入）")
    elif changed:
        for c in changed:
            print("  + %s" % c)
    else:
        print("  （全部已存在，无需写入 —— 幂等）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
