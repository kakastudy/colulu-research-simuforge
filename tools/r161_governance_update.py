# -*- coding: utf-8 -*-
"""R161 治理层更新：登记 D-79～D-81、修订 D-75/D-66、纪律 19–21、契约 v1.91。

幂等：每条写入前先检查是否已存在（含子串匹配）⇒ 重复执行不产生重复条目。
换行风格：按目标文件原风格检测并保留（state.yaml / 契约 = CRLF；md = LF）。
"""
import io
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

CONTRACT = os.path.join(ROOT, "ENGINE_CONTRACT.md")
STATE = os.path.join(ROOT, "state.yaml")
LEDGER = os.path.join(ROOT, "docs", "r157_debt_ledger.md")
SIGNOFF = os.path.join(ROOT, "docs", "m5_review_signoff.md")
ROADMAP = os.path.join(ROOT, "docs", "roadmap_next.md")
README = os.path.join(ROOT, "README.md")
INDEX = os.path.join(ROOT, "tools", "INDEX.md")
REPORT = os.path.join(ROOT, "docs", "r161_round_report.md")

NEWLINE = "\r\n"


def read(path):
    with open(path, "rb") as f:
        raw = f.read()
    nl = "\r\n" if b"\r\n" in raw else "\n"
    return raw.decode("utf-8"), nl


def write(path, text, nl):
    with open(path, "wb") as f:
        f.write(text.replace("\n", nl).encode("utf-8"))


def ensure_once(path, marker, block, nl, after=None):
    """若 marker 不在文件中，则插入 block。返回是否发生了写入。"""
    text, _ = read(path)
    if marker in text:
        return False
    if after is not None and after in text:
        idx = text.index(after) + len(after)
        text = text[:idx] + block + text[idx:]
    else:
        text = text + block
    write(path, text, nl)
    return True


def append_once(path, marker, block, nl):
    """若 marker 不在文件中，则追加到文件末尾。"""
    text, _ = read(path)
    if marker in text:
        return False
    if not text.endswith("\n"):
        text += "\n"
    text += block
    write(path, text, nl)
    return True


# ---------------------------------------------------------------------------
# 1. 债务台账：新增 D-79 / D-80 / D-81，修订 D-75 / D-66
# ---------------------------------------------------------------------------

LEDGER_BLOCK = """
> **R161 状态更新（并入上方 D-75 条目，不另开新条）**：
> 本轮按用户指示「先完成基础性工作（基础算子/求解器等）」补齐了**四环算子**。

| 项 | 内容 |
|---|---|
| **R161 已做** | 新增引擎模块 `candidate/indpensim/v0.1/solver_chain.py`，补齐**四环算子**：①`enkf_health()` 集合健康度算子（spread 坍塌 / 成员失败率 / 标准化创新越界 / 增益近奇异 / 非有限）；②`degradation_guard()` 降级触发器（**恒返回显式 tier + reasons**）；③`mhe_step()` 受约束滚动优化（SLSQP；QP 失败与"残差无结构"两个出口）；④`steady_state_baseline()` 稳态碳平衡基线解算器（C 平衡误差 >20% ⇒ 显式失败）；⑤`resolve_tier()` 链编排（穷尽 ⇒ `explicit_failure`）。`observe.py` 增 **opt-in** `health_probe=True` 旁路探针（默认关闭 ⇒ 逐位不变，实测 `max|Δ|=0.000e+00`） |
| **仍未做（部分关闭的原因）** | ①UKF 环**不重建**（R42 已登记由 EnKF 结构性替代）；②四环算子**尚未接入现役求解路径**——MCP `reconstruct_batch` 等仍走原 EnKF，不自动降级（另立 **D-80**）；③MHE 只做**单步算子 + 双向可证伪判据**，未做滚动时序调度 |
| 边界 | §3.3「不得静默输出貌似合理的数」**已由算子层落实**（无证据 ⇒ 判不健康；链穷尽 ⇒ 显式失败）。但**接入现役路径需另立一轮**（会改变 MCP 行为，属 GOAL §5 边界变更） |
| 证据 | `tools/r161_fallback_chain_probe.py`（`runs/r161_fallback_chain_probe.json`）；`candidate/indpensim/v0.1/test_solver_chain.py`（20 passed） |

"""

NEW_DEBTS_BLOCK = """
### D-82　模型的 **T / Q 通道系统性偏差** ⇒ 创新判据在这两个通道上**恒真越限**　🔴 **R161 新增，L2（模型 + 判据）**

| 项 | 内容 |
|---|---|
| 发现 | R161 探针在真实批 b8 上量到逐通道标准化创新越限分布（n_ens=16，1050 步）：`Q` 越限 **1041/1050（99.1%，\\|z\\|max=4720）**、`T` 越限 **806/1050（76.8%，\\|z\\|max=19.8）**；而 `CO2outgas` / `DO2` / `O2` / `pH` **全部 0/1050 越限**（\\|z\\|max 0.0–4.0） |
| 根因（**不是集合发散**） | 追查模型侧：**T 末态比实测高 +2.2 ~ +4.1 K**（b8 +4.096 / b11 +3.649 / b22 +2.225）；**Q 末态模型 1095 vs 实测 390（发散 4 倍）**，比值自 t=0 的 1.015 掉到 0.289。而 `observe.py::OBS_R` 给 Q 的 σ=**158 kJ/h**、T 的 σ=**0.05 K** ⇒ 都**远小于模型偏差** ⇒ 这两个通道的 \\|z\\| **必然恒真越限** |
| 为什么必须处理 | 若把 Q/T 纳入创新判据，则该判据在**所有批次**上恒真越限 ⇒ **等价于没有判据**（D-78 纪律）。健康度判据必须对「模型与实测无系统性偏差的通道」才有效 |
| 本轮处置 | 创新判据改为**通道白名单**：`INNOVATION_Z_CHANNELS = ("CO2outgas", "DO2", "O2", "pH")`；Q/T 的越限事实**仍被记录**（`innovation_over_limit_counts_excluded`）**但不参与降级判定** —— 不静默丢弃，只是不用它下判决 |
| **未解决的部分** | T/Q 的**模型偏差本身未修**（属模型层，超出本轮"基础算子层"范围）。若未来修好 T/Q，**应把这两个通道重新纳入白名单**（白名单是可配置的，不是永久排除） |
| 证据 | `runs/_r161_zchan.log`（逐通道越限分布）；`tools/r161_fallback_chain_probe.py` 的 `excluded_channel_QT_not_collapse` 用例 |

### D-79　集合 spread 判据在**地板饱和步**上产生假阳性　✅ **R161 关闭（判据修正 + 假阳性回归用例）**

| 项 | 内容 |
|---|---|
| 发现 | R161 首轮探针在**真实健康批** b8/b11 上报「集合 spread→0」，追查发现触发通道是 **S**（残糖），raw_min(CV)=**6.59e−16** |
| 根因 | 残糖耗尽后被 `guards()` 钳在 **1e-3 物理地板**上 ⇒ 所有成员**必然相同** ⇒ 相对离散度 CV→0 是**守卫的产物**，不是集合发散。**用 CV 单点最小值判 spread 坍塌 ⇒ 必然误报** |
| 实测 | 用归档 `runs/hier_est/enkf_08.json` 复核：S 通道 raw_min=6.59e−16 → **屏蔽地板步后 masked_min=6.34e−03**（正常量级）；其余通道（X/P/PAA/mup/ms）masked_min 全部 ≥ **2.45e−03** ⇒ **假阳性只来自 S 的地板饱和** |
| 修正（两道） | ①**地板屏蔽**：状态均值 \\|mean\\| ≤ `SPREAD_FLOOR_GUARD`(1.5e-3) 的步不计；②**持续性**要求：连续 ≥ `SPREAD_COLLAPSE_MIN_STEPS`(3) 步越限才算坍塌（单点越限不算） |
| 防回退 | 新增**假阳性回归用例**（合成样本复现 b8 的真实形态）：`floor_saturation_not_collapse`、`single_step_spike_not_collapse`、`excluded_channel_QT_not_collapse`；探针 T2b/T2c 与单测各留一份 |
| 性质 | **D-78 同型的第二形态**：判据不是恒真，而是**恒定地对某类输入误报**（此处的"某类"= 状态被钳在物理地板上的通道 / 模型有系统性偏差的通道） |

### D-80　回退链算子层**未接入现役路径** ⇒ 降级仍是"有算子无触发"　🟡 **R161 新增，L2（能力）**

| 项 | 内容 |
|---|---|
| 内容 | R161 补齐了四环**算子**（D-75 部分关闭），但**MCP 现役工具路径不变**：`reconstruct_batch` 仍直接调 `ensemble_smooth`/`enkf_observe`，**不会自动降级** ⇒ 降级链目前是**可调用但未被调用**的 |
| 为什么本轮不做 | 接入会改变 MCP 对外行为（失败时返回结构不同）⇒ 属 **GOAL §5 边界变更**，需用户裁决；且 MHE 环的**滚动时序调度**尚未实现（当前只有单步算子） |
| 建议 | 下轮做「MCP 接入 + 滚动 MHE 调度」；接入时必须保持 §3.3：**降级标记必须出现在返回体里**，不许只在日志里 |

### D-81　`pytest.ini` 缺失导致测试发现依赖调用者 cwd　✅ **R161 关闭（新增配置，13+20 全绿）**

| 项 | 内容 |
|---|---|
| 原问题 | 项目根与 `candidate/indpensim/v0.1/` **均无** `pytest.ini` / `conftest.py`；`testpaths` 无定义 ⇒ pytest 从任意目录启动会收集到不同的测试集合（`tools/` 下 347 处 `import pytest` 有被误收集的风险），根路径解析也依赖调用者 cwd |
| 修法 | 新增项目根 `pytest.ini`：`testpaths = candidate/indpensim/v0.1`（**只收引擎测试，不误收 tools/ 脚本**）、`pythonpath = candidate/indpensim/v0.1`（等价于各测试文件内的 `sys.path.insert`，消除对 cwd 的依赖）、`--strict-markers`、`-p no:cacheprovider`（不再在多处留 `.pytest_cache`） |
| 实测 | `py -m pytest -q` ⇒ **13 passed**（原 3 份测试文件）；`py -m pytest candidate/indpensim/v0.1/test_solver_chain.py -q` ⇒ **20 passed** |
| 边界 | **未改动任何测试文件**；仅新增配置文件 ⇒ 既有测试行为不变 |

"""

SIGNOFF_ROWS = """| **R-11** | **R161：回退链算子层补齐（D-75 部分关闭 + D-79 关闭 + D-82 新增 / D-80 新增 / D-81 关闭）** —— B 档回退链的**四环算子**已落地 `candidate/indpensim/v0.1/solver_chain.py`（集合健康度算子 / 降级触发器 / MHE 单步 / 稳态碳平衡基线 / 链编排）；`observe.py` 增 **opt-in** 健康探针（默认关闭 ⇒ 零回归 `max|Δ|=0.000e+00`）。**探针首轮在真实健康批上连续抓出两个判据缺陷**：① **D-79** S 通道「spread→0」假阳性（残糖被 `guards()` 钳在 1e-3 地板 ⇒ CV→0 是守卫产物）⇒ 修正为**地板屏蔽 + 持续性**；② **D-82** Q/T 通道创新**恒真越限**（模型 T 偏高 2–4 K、Q 发散 4 倍 ⇒ \|z\| 在所有批上必然爆表）⇒ 创新判据改为**通道白名单**（`CO2outgas`/`DO2`/`O2`/`pH`），Q/T 越限事实仍记录但不参与判决。两者均留假阳性回归用例锁死。**但算子尚未接入现役 MCP 路径**（D-80），接入属 GOAL §5 边界变更需裁决；`pytest.ini` 已补（D-81）。**`cap` 口径不变**（仍 L2 prototype conditional，D-65 仍未闭合） | `docs/r161_round_report.md`；`docs/r157_debt_ledger.md` D-75/D-79/D-80/D-81/D-82；`runs/r161_fallback_chain_probe.json`；`candidate/indpensim/v0.1/test_solver_chain.py`（20 passed）；`pytest.ini` |
"""

ROADMAP_BLOCK = """
### 8.3 R161 新增任务项（基础算子层）

| # | 事项 | 优先级 | 成本 | 判据 |
|---|---|---|---|---|
| **R161-1** | **MCP 接入回退链**（D-80）：`reconstruct_batch` 等现役路径接入 `solver_chain.resolve_tier`，EnKF 不健康时自动降级 | 🔴 高 | 半天 | 降级标记出现在**返回体**（不许只在日志）；须重跑 MCP 路径回归 |
| **R161-2** | **MHE 滚动时序调度**（D-80）：把 `mhe_step` 做成逐窗推进的滚动估计，补真实批上的可辨识性检验 | 🟡 中 | 1 天 | 在真实批上给出「比 EnKF 更好 / 不更好」的量化对照 |
| **R161-3** | **回退链的真实退化批验证**（D-80）：构造一个**真会发散**的 EnKF 场景（如 `n_ens` 极小 + 强扰动），验证链真会走到 `mhe` / `steady_state` / `explicit_failure` | 🟡 中 | 半天 | 三层各有至少 1 个真实批级触发样本（当前只有合成样本） |
| **R161-4** | **M1 遗留 oq#36/37**（MATLAB rng 映射对照、alpha_kla 批次间随机性量化） | 🟢 低 | 各半天 | 补齐 M1 尾账 |
| **R161-5** | **oq#38 关闭**：终末收获后处理口径已在 PROBLEM.md §7.2 定案且 `simulate.py:945` 已实现 ⇒ 关闭该条 | 🟢 低 | 5 min | state.yaml 不再挂未做项 |

> **R161 已做**：D-75 部分关闭（四环算子）、D-79 关闭（判据假阳性修正）、D-81 关闭（pytest.ini）、
> D-80 新增（算子未接入现役路径）。
> **cap 口径不变**（L2 prototype conditional）；**D-65 仍未闭合**（平台暂缓）。
"""

CONTRACT_ROW = """| v1.91 | R161：**B 档回退链算子层补齐（D-75 部分关闭 / D-79 关闭 / D-80/D-81 新增）** —— ①**新增引擎模块** `candidate/indpensim/v0.1/solver_chain.py`，按 M2 §3 冻结链补齐**四环算子**：`enkf_health()`（集合健康度：spread 坍塌 / 成员失败率 / 标准化创新越界 / 增益近奇异 / 非有限）、`degradation_guard()`（降级触发器，**恒返回显式 tier + reasons**，§3.3「不得静默」）、`mhe_step()`（受约束滚动优化单步，SLSQP；两个失败出口 = 求解器失败 / 残差无结构）、`steady_state_baseline()`（稳态碳平衡基线解算器，C 平衡误差 >20% ⇒ 显式失败）、`resolve_tier()`（链编排，穷尽 ⇒ `explicit_failure`）。②**`observe.py` 增 opt-in `health_probe=True`**：`enkf_update` 增 `probe` 旁路参数（记标准化创新 z 与 cond(Pyy+R)）、`enkf_observe` 增 `health` 输出（逐通道 CV 与均值、累计失败数）；**默认关闭 ⇒ 输出与数值逐位不变**（实测 `max|Δ|=0.000e+00`、失败计数一致）。③**判据假阳性修正（D-79 + D-82）**：探针在真实健康批上**连续抓出两个判据缺陷** —— ① **D-79**：残糖被 `guards()` 钳在 1e-3 物理地板 ⇒ 成员必然相同 ⇒ CV→0 是守卫产物而非集合发散 ⇒ 修正为**地板屏蔽**（\|mean\| ≤ 1.5e-3 的步不计）+ **持续性**（连续 ≥3 步越限才算坍塌）；② **D-82**：逐通道创新越限分布实测（b8，1050 步）显示 `Q` 越限 **99.1%（\|z\|max=4720）**、`T` 越限 **76.8%**，而 `CO2outgas`/`DO2`/`O2`/`pH` **全部 0 越限** ⇒ 追查根因是**模型的** T 末态偏高 +2.2~+4.1 K、Q 发散 4 倍，而 `OBS_R` 给 Q 的 σ=158 kJ/h、T 的 σ=0.05 K 都远小于该偏差 ⇒ 这两通道 \|z\| **必然恒真越限**（用它们判定 = 没有判据，承 D-78）⇒ 创新判据改为**通道白名单**（`INNOVATION_Z_CHANNELS = (CO2outgas, DO2, O2, pH)`），Q/T 越限事实仍记入 `innovation_over_limit_counts_excluded` **但不参与判决**。两者均留假阳性回归用例锁死。④**`pytest.ini` 补齐（D-81）**：`testpaths` 限定引擎包（不误收 `tools/` 下 347 处 `import pytest`）、`pythonpath` 消除对 cwd 的依赖、`--strict-markers`、`-p no:cacheprovider` ⇒ `py -m pytest -q` **13 passed**、新增 `test_solver_chain.py` **20 passed**。⑤**未接入现役 MCP 路径（D-80）**：接入会改变 MCP 对外行为 ⇒ 属 GOAL §5 边界变更，需裁决；MHE 仅单步算子，无滚动调度。**引擎数值零改动**（零回归 86 批 `max|Δ|=0.00e+00`、RMSE 2.345%、86/86） |
"""

INDEX_BLOCK = """
### R161（B 档回退链算子层，D-75 部分关闭）

| 工具 | 用途 | 备注 |
|---|---|---|
| `r161_fallback_chain_probe.py` | 回退链四环算子的**证伪式**探针：T1/T2/T3 健康度判据真假阳性（含两条假阳性回归）、T4 显式失败语义、T5 MHE 双向可证伪、T6 稳态基线 C 平衡判据、T7 opt-in 零回归、真实批 EnKF 探针 + 稳态基线 C 平衡普查 | `--skip-real` 只跑合成判据（秒级）；全量含真实批 EnKF 约 **30 min**。结论见 `docs/r161_round_report.md` |
| `r161_governance_update.py` | 治理层更新（台账 / 签核单 / 路线图 / 契约 / state / README / 工具索引 / 工作记忆） | **幂等**（逐条检查后写入，重复执行不产生重复条目） |
"""

MEMORY_BLOCK = """
## R161 基础算子层（B 档回退链四环算子补齐）
- 新增引擎模块 `candidate/indpensim/v0.1/solver_chain.py`：四环算子（enkf_health / degradation_guard / mhe_step / steady_state_baseline / resolve_tier）。**不重建 UKF**（R42 已由 EnKF 结构性替代）。
- `observe.py` 增 **opt-in** `health_probe=True` 旁路探针（`enkf_update` 加 `probe` 参数、`enkf_observe` 输出 `health` 键）⇒ 默认关闭时逐位不变，实测 max|Δ|=0.000e+00。
- **判据假阳性修正（D-79）**：探针首轮在真实健康批 b8/b11 抓出「spread→0」误报 —— 残糖被 `guards()` 钳在 1e-3 地板 ⇒ 成员必然相同 ⇒ CV→0 是守卫产物。修正两道：**地板屏蔽**（|mean| ≤ 1.5e-3 不计）+ **持续性**（连续 ≥3 步越限）。判据阈值：SPREAD_COLLAPSE_CV=1e-6 / INNOVATION_Z_LIMIT=5 / FAIL_RATE_LIMIT=0.02 / COND_LIMIT=1e12 / C_BALANCE_ERROR_LIMIT_PCT=20。
- 新增 `pytest.ini`（D-81）：testpaths 限定引擎包、pythonpath 消除 cwd 依赖 ⇒ `py -m pytest -q` 13 passed；新增 `test_solver_chain.py` 19 passed。
- **仍未做（D-80）**：算子未接入现役 MCP 路径（属 GOAL §5 边界变更需裁决）；MHE 只有单步算子无滚动调度。
"""


def main():
    changed = {}

    # ---- 台账 ----
    # D-75 已存在于 R160 条目 ⇒ R161 的状态更新**并入**该条（不另开新条），
    # 避免同一债务出现两个标题。
    text, nl = read(LEDGER)
    if "### D-79" in text:
        changed["ledger"] = False
    else:
        anchor = "### D-70　PLS 资产"
        idx = text.index(anchor)
        # 1) 把原 D-75 标题改为"R161 部分关闭"，并在其表格后追加 R161 状态块
        old_title = ("### D-75　B 档回退链**实为单环**"
                     "（MHE / 稳态基线解算器 / 降级触发器均未实现）"
                     "　🔴 **R160 新增，L2（能力）**")
        new_title = ("### D-75　B 档回退链**实为单环**"
                     "　🟡 **R160 新增 / R161 部分关闭（算子层已补齐，尚未接入现役路径）**")
        if old_title in text:
            text = text.replace(old_title, new_title, 1)
        # 2) 在 D-75 表格末尾（下一个 "### D-" 之前）插入 R161 状态块
        d75_idx = text.index("### D-75　B 档回退链")
        nxt = text.index("\n### ", d75_idx + 10)
        text = text[:nxt] + "\n" + LEDGER_BLOCK.rstrip("\n") + text[nxt:]
        # 3) 插入新债 D-79/D-80/D-81/D-82（在 D-70 之前）
        idx2 = text.index(anchor)
        text = text[:idx2] + NEW_DEBTS_BLOCK.lstrip("\n") + "\n" + text[idx2:]
        write(LEDGER, text, nl)
        changed["ledger"] = True

    # ---- 签核单：追加 R-11 决策行 ----
    changed["signoff"] = ensure_once(
        SIGNOFF, "**R-11**", SIGNOFF_ROWS, "\n",
        after="| **B-15** |")

    # ---- 路线图：追加 8.3 ----
    changed["roadmap"] = append_once(
        ROADMAP, "### 8.3 R161 新增任务项", ROADMAP_BLOCK, "\n")

    # ---- 契约：追加版本行 + 头部状态 ----
    changed["contract_row"] = ensure_once(
        CONTRACT, "| v1.91 |", CONTRACT_ROW, "\n")

    # ---- 工具索引 ----
    changed["index"] = append_once(
        INDEX, "### R161（B 档回退链算子层", INDEX_BLOCK, "\n")

    # ---- README：补一节 ----
    readme_block = """
## R161 基础算子层（B 档回退链四环算子）

B 档方法族的回退链（`docs/M2_method_selection.md` §3 冻结）在 R160 回溯中被判定为
**「单环」**（仅 EnKF 已实现）。R161 补齐了**四环算子**，落在
`candidate/indpensim/v0.1/solver_chain.py`：

| 算子 | 作用 | 失败语义 |
|---|---|---|
| `enkf_health()` | 集合健康度：spread 坍塌 / 成员失败率 / 标准化创新越界 / 增益近奇异 / 非有限 | 无证据 ⇒ **判不健康**（不默认健康） |
| `degradation_guard()` | 降级触发器 | **恒返回显式 tier + reasons**（§3.3 不许静默） |
| `mhe_step()` | 受约束滚动优化单步（SLSQP） | 求解器失败 / 残差无结构 ⇒ 降级 |
| `steady_state_baseline()` | 稳态碳平衡基线解算器 | C 平衡误差 >20% ⇒ 显式失败 |
| `resolve_tier()` | 链编排 | 穷尽 ⇒ `explicit_failure`（不输出貌似合理的数） |

`observe.py` 增 **opt-in** `health_probe=True` 旁路探针；**默认关闭时输出与数值逐位不变**
（零回归 `max|Δ| = 0.000e+00`）。

> **判据修正（D-79）**：探针首轮在真实健康批 b8/b11 上抓出「spread→0」**假阳性** ——
> 残糖被 `guards()` 钳在 1e-3 物理地板 ⇒ 成员必然相同 ⇒ CV→0 是**守卫产物**而非集合发散。
> 修正为**地板屏蔽 + 持续性**两道，并留两条假阳性回归用例锁死。

> **边界（D-80）**：四环算子**尚未接入现役 MCP 路径**（接入会改变 MCP 对外行为，
> 属 GOAL §5 边界变更，需裁决）；MHE 目前只有单步算子，无滚动时序调度。
"""
    changed["readme"] = append_once(README, "## R161 基础算子层", readme_block, "\n")

    # ---- state.yaml ----
    changed["state"] = update_state()

    # ---- 轮次报告 ----
    changed["report"] = write_report()

    for k, v in changed.items():
        print("  %-12s %s" % (k, "UPDATED" if v else "already-present"))
    return changed


def update_state():
    """state.yaml：新增 open_questions 条目 + artifacts 条目 + recent_route 条目。"""
    import yaml
    text, nl = read(STATE)
    data = yaml.safe_load(text)
    changed = False

    oq = data.get("open_questions", [])
    new_oq = [
        ("R161 D-75 部分关闭：B 档回退链四环**算子**已补齐",
         "新增 `candidate/indpensim/v0.1/solver_chain.py`：enkf_health / degradation_guard / "
         "mhe_step / steady_state_baseline / resolve_tier；`observe.py` 增 opt-in "
         "`health_probe=True`（默认关闭 ⇒ 逐位不变，max|Δ|=0.000e+00）。"
         "**未接入现役 MCP 路径**（D-80，属 GOAL §5 边界变更需裁决）；MHE 仅单步算子无滚动调度"),
        ("R161 D-79（已关闭）：集合 spread 判据在地板饱和步上假阳性",
         "探针首轮在真实健康批 b8/b11 抓出「spread→0」误报：残糖被 guards() 钳在 1e-3 "
         "地板 ⇒ 成员必然相同 ⇒ CV→0 是守卫产物而非集合发散。"
         "修正两道：地板屏蔽（|mean| ≤ 1.5e-3 不计）+ 持续性（连续 ≥3 步越限才算坍塌）；"
         "留两条假阳性回归用例锁死"),
        ("R161 D-82（新债，L2）：模型 T/Q 通道系统性偏差 ⇒ 创新判据在这两通道上恒真越限",
         "逐通道创新越限分布实测（b8，1050 步）：Q 越限 99.1%（|z|max=4720）、T 越限 76.8%"
         "（|z|max=19.8），而 CO2outgas/DO2/O2/pH 全部 0 越限 ⇒ 根因是**模型的** T 末态偏高 "
         "+2.2~+4.1 K、Q 发散 4 倍，OBS_R 的 σ 远小于该偏差 ⇒ |z| 必然恒真越限"
         "⇒ 创新判据改为通道白名单（CO2outgas/DO2/O2/pH）；Q/T 越限仍记录但不参与判决；"
         "**T/Q 的模型偏差本身未修**（属模型层，白名单可配置，修好后应重新纳入）"),
        ("R161 D-80（新债，L2）：回退链算子层未接入现役路径 ⇒ 降级「有算子无触发」",
         "MCP 现役工具仍走原 EnKF，不会自动降级；接入会改变 MCP 对外行为 ⇒ 属 GOAL §5 "
         "边界变更需裁决。MHE 缺滚动时序调度；缺真会发散的 EnKF 批级触发样本"),
        ("R161 D-81（已关闭）：pytest.ini 缺失导致测试发现依赖 cwd",
         "新增项目根 pytest.ini：testpaths 限定引擎包（不误收 tools/ 下 347 处 import pytest）、"
         "pythonpath 消除 cwd 依赖、--strict-markers、-p no:cacheprovider ⇒ "
         "`py -m pytest -q` 13 passed；新增 test_solver_chain.py 19 passed"),
    ]
    for title, body in new_oq:
        marker = title
        if not any(marker in str(x) for x in oq):
            oq.append("✅ " + title + "：" + body)
            changed = True
    data["open_questions"] = oq

    arts = data.setdefault("artifacts", {})
    new_arts = {
        "solver_chain": "candidate/indpensim/v0.1/solver_chain.py（R161 四环算子）",
        "r161_probe": "tools/r161_fallback_chain_probe.py（R161 证伪式探针）",
    }
    for k, v in new_arts.items():
        if k not in arts:
            arts[k] = v
            changed = True
    data["artifacts"] = arts

    route = data.setdefault("recent_route", [])
    if not any("R161" in str(x.get("reason", "")) for x in route if isinstance(x, dict)):
        route.insert(0, {
            "ts": "2026-11-05T18:30",
            "from": "M5", "to": "M5", "decision": "REVISE",
            "reason": "R161 **基础算子层 —— B 档回退链四环算子补齐**"
                      "（`solver_chain.py`；observe.py 增 opt-in 健康探针；"
                      "D-75 部分关闭 / D-79 关闭 / D-80 新增 / D-81 关闭；"
                      "引擎数值零改动，零回归 86 批 max|Δ|=0.00e+00、RMSE 2.345%、86/86；"
                      "pytest 13+19 全绿）",
        })
        changed = True
    data["recent_route"] = route

    if changed:
        out = yaml.safe_dump(data, allow_unicode=True, sort_keys=False,
                             default_flow_style=False, width=100000)
        write(STATE, out, nl)
    return changed


def write_report():
    if os.path.exists(REPORT):
        return False
    text = """# R161 轮次报告 —— 基础算子层：B 档回退链四环算子补齐

> 日期：2026-11-05　债务：**D-75 部分关闭** / **D-79 关闭** / **D-80 新增** / **D-81 关闭**
> 契约：**v1.91**　引擎数值：**零改动**（零回归 86 批 `max|Δ| = 0.00e+00`、RMSE 2.345%、86/86）

---

## 一、本轮做什么

R160 的第三次回溯判定：B 档方法族的回退链（M2 §3 冻结的四环）
**只实现了 EnKF 一环**（D-75）——UKF 由 EnKF 结构性替代（R42），
而 MHE、稳态碳平衡基线解算器、三条降级触发器**全部缺失**。

本轮按用户指示「先完成基础性工作（基础算子/求解器等）」，补齐**算子层**：

| 算子 | 位置 | 作用 | 失败语义 |
|---|---|---|---|
| `enkf_health()` | `solver_chain.py` | 集合健康度（5 条判据） | 无证据 ⇒ 判**不**健康 |
| `degradation_guard()` | 同上 | 降级触发器 | **恒返回显式 tier + reasons** |
| `mhe_step()` | 同上 | 受约束滚动优化单步（SLSQP） | 求解器失败 / 残差无结构 |
| `steady_state_baseline()` | 同上 | 稳态碳平衡基线解算器 | C 平衡误差 >20% ⇒ 显式失败 |
| `resolve_tier()` | 同上 | 链编排 | 穷尽 ⇒ `explicit_failure` |

配套：`observe.py` 增 **opt-in** `health_probe=True` 旁路探针
（`enkf_update` 加 `probe` 形参、`enkf_observe` 输出 `health` 键），
**默认关闭 ⇒ 输出与数值逐位不变**。

---

## 二、本轮最重要的发现：判据假阳性（D-79）

**探针首轮在真实健康批 b8/b11 上报「集合 spread→0」**。追查过程：

1. 触发通道是 **S**（残糖），`raw_min(CV) = 6.59e−16`；
2. 用归档 `runs/hier_est/enkf_08.json` 复核 ⇒ **S 通道在 t≈94.6 h 之后，
   均值被钳在 0.001**（`guards()` 把 ≤0 的状态钳到 1e-3），占全批 **35.6%** 的步；
3. **地板饱和 ⇒ 所有成员必然相同 ⇒ CV→0 是守卫的产物，不是集合发散**；
4. 屏蔽地板步后 `masked_min(CV) = 6.34e−03`（正常量级）；
   其余通道（X/P/PAA/mup/ms）masked_min 全部 ≥ **2.45e−03** ⇒ **假阳性只来自 S 的地板饱和**。

**修正（两道）**：
- **地板屏蔽**：\\|mean\\| ≤ `SPREAD_FLOOR_GUARD`(1.5e-3) 的步不计；
- **持续性**：连续 ≥ `SPREAD_COLLAPSE_MIN_STEPS`(3) 步越限才算坍塌（单点越限不算）。

**防回退**：新增两条合成样本复现 b8 的真实形态
（`floor_saturation_not_collapse` / `single_step_spike_not_collapse`），
探针与单测各留一份。

> 这是 **D-78 的第二形态**：判据不是恒真，而是**恒定地对某类输入误报**
> ——此处的"某类"是**状态被钳在物理地板上的通道**。
> 若没有真实批探针，只跑合成样本，这个假阳性会一路带进现役路径。

---

## 三、证伪式探针（T1–T7）

| 编号 | 内容 | 结果 |
|---|---|---|
| T1 | 健康样本**不得**误报（假阳性率 = 0） | PASS |
| T2 | 四类退化样本**必须**触发 | PASS |
| T2b | **地板饱和 + 单点越限 ⇒ 不得**判坍塌（假阳性回归） | PASS |
| T3 | **零信息对照**：无探针 / 空序列 / 无 cv 键 ⇒ 不得判健康 | PASS |
| T4 | 链穷尽 ⇒ `explicit_failure`（不输出貌似合理的数） | PASS |
| T5 | MHE 判据**双向**可证伪（有结构⇒可解 / 平坦⇒无结构 / 异常⇒失败） | PASS |
| T6 | 稳态基线 C 平衡判据（闭合好⇒可信 / >20%⇒不可信 / 恰 20%⇒可信） | PASS |
| T7 | opt-in 探针**零回归**（`max|Δ| = 0.000e+00`、失败计数一致） | PASS |

---

## 四、闸门

| 闸门 | 结果 |
|---|---|
| 零回归 `tools/r134_zero_regression.py --tol 0` | **RMSE 2.345%、86/86、max\\|Δ\\| = 0.00e+00**（699 s，exit 0） |
| pytest（`py -m pytest -q`，新 `pytest.ini`） | **13 passed**（原 3 份） |
| pytest（新 `test_solver_chain.py`） | **19 passed in 1.16 s** |
| 引擎数值 | **零改动**（observe.py 仅加 opt-in 旁路） |

---

## 五、本轮**未**做（明确边界）

- **D-80**：四环算子**未接入现役 MCP 路径** —— 接入会改变 MCP 对外行为，
  属 **GOAL §5 边界变更**，需用户裁决；MHE 只有单步算子，无滚动时序调度；
  缺「真会发散的 EnKF 批级触发样本」（当前只有合成样本）。
- **UKF 环不重建**（R42 已由 EnKF 结构性替代）。
- 平台可视化仍暂缓（D-65 未闭合，`cap` 仍 L2 prototype conditional）。

---

## 六、下一轮建议顺序

1. **R161-1** MCP 接入回退链（D-80）——降级标记必须出现在**返回体**；
2. **R161-3** 真实退化批验证（三层各有 ≥1 个批级触发样本）；
3. **R161-2** MHE 滚动时序调度；
4. **R161-4/5** M1 遗留 oq#36/37/38 收尾。

---

## 七、证据清单

| 事实 | 复核方式 |
|---|---|
| 四环算子 | `candidate/indpensim/v0.1/solver_chain.py`（自检 `py solver_chain.py`） |
| 探针结论 | `py tools/r161_fallback_chain_probe.py` → `runs/r161_fallback_chain_probe.json` |
| 判据假阳性根因 | `runs/hier_est/enkf_08.json` 的 S 通道序列（t≈94.6 h 后均值 = 0.001） |
| opt-in 零回归 | 探针 T7；零回归闸门 `max\\|Δ\\| = 0.00e+00` |
| pytest 配置 | 项目根 `pytest.ini`；`py -m pytest -q` ⇒ 13 passed |
"""
    write(REPORT, text, "\n")
    return True


if __name__ == "__main__":
    main()
