# -*- coding: utf-8 -*-
"""R162 治理层更新：登记 D-83/D-84、关闭 oq#36/37/38、纪律 22–24、契约 v1.92。

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
MEMLOG = os.path.join(ROOT, ".workbuddy", "memory", "2026-11-05.md")


def read(path):
    with open(path, "rb") as f:
        raw = f.read()
    nl = "\r\n" if b"\r\n" in raw else "\n"
    return raw.decode("utf-8"), nl


def write(path, text, nl):
    """写入前先归一化行尾，避免重复 CR。

    R161 及更早的治理脚本直接 `text.replace("\\n", nl)`，当文件本身已是 CRLF 时
    会把 `\\r\\n` 变成 `\\r\\r\\n`（**每个行尾多一个 CR**）——
    本函数先把所有行尾归一为 `\\n`，再统一转成目标风格 ⇒ 幂等且可修复历史污染。

    ⚠ 顺序要紧：必须**先**处理 `\\r\\r\\n`，再处理 `\\r\\n`，最后处理裸 `\\r`；
    否则 `\\r\\r\\n` 会先被 `\\r\\n` 规则切成 `\\r\\n`、再被裸 `\\r` 规则切成 `\\n\\n`
    ⇒ **一行被拆成两行**（内容损坏）。
    """
    text = text.replace("\r\r\n", "\n").replace("\r\n", "\n").replace("\r", "\n")
    with open(path, "wb") as f:
        f.write(text.replace("\n", nl).encode("utf-8"))


def normalize_eol(path):
    """把文件行尾归一化为与其原风格一致（修复历史 \\r\\r\\n 污染）。"""
    with open(path, "rb") as f:
        raw = f.read()
    nl = "\r\n" if b"\r\n" in raw else "\n"
    fixed = raw.replace(b"\r\r\n", b"\n").replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    fixed = fixed.replace(b"\n", nl.encode("ascii"))
    if fixed != raw:
        with open(path, "wb") as f:
            f.write(fixed)
        return True
    return False


def insert_after_line(path, line_prefix, block, nl):
    """在某行（按前缀匹配）的**行尾**之后插入 block —— 避免插到行中间。"""
    text, _ = read(path)
    lines = text.split("\n")
    for i, l in enumerate(lines):
        if l.startswith(line_prefix):
            lines.insert(i + 1, block)
            write(path, "\n".join(lines), nl)
            return True
    return False


def ensure_once(path, marker, block, nl=None, after=None):
    """若 marker 不在文件中，则插入 block。返回是否发生了写入。`nl=None` ⇒ 自动沿用原风格。"""
    text, cur_nl = read(path)
    if nl is None:
        nl = cur_nl
    if marker in text:
        return False
    if after is not None and after in text:
        idx = text.index(after) + len(after)
        text = text[:idx] + block + text[idx:]
    else:
        text = text + block
    write(path, text, nl)
    return True


def append_once(path, marker, block, nl=None):
    """若 marker 不在文件中，则追加到文件末尾。`nl=None` ⇒ 自动沿用原风格。"""
    text, cur_nl = read(path)
    if nl is None:
        nl = cur_nl
    if marker in text:
        return False
    if not text.endswith("\n"):
        text += "\n"
    text += block
    write(path, text, nl)
    return True


def insert_after_line(path, line_prefix, block, nl=None):
    """在某行（按前缀匹配）的**行尾**之后插入 block —— 避免插到行中间。"""
    text, cur_nl = read(path)
    if nl is None:
        nl = cur_nl
    lines = text.split("\n")
    for i, l in enumerate(lines):
        if l.startswith(line_prefix):
            lines.insert(i + 1, block)
            write(path, "\n".join(lines), nl)
            return True
    return False


def replace_once(path, old, new, nl=None):
    """精确替换一次；命中返回 True，未命中返回 False。`nl=None` ⇒ 自动沿用文件原风格。"""
    text, cur_nl = read(path)
    if nl is None:
        nl = cur_nl
    if old not in text:
        return False
    text = text.replace(old, new, 1)
    write(path, text, nl)
    return True


# ---------------------------------------------------------------------------
# 1. 债务台账：新增 D-83 / D-84
# ---------------------------------------------------------------------------
NEW_DEBTS_BLOCK = """
### D-83　MATLAB 端 **8 路时变扰动的随机成分未移植**　🟡 **R162 新增，L2（模型保真度）**

| 项 | 内容 |
|---|---|
| 发现 | MATLAB `indpensim_run.m:148-181` 用**随机低通滤波**生成 8 路时变扰动：`v = randn(T/h+1,1); distXXX = filter(b1,a1,scale·v)`（`b1 = 1−0.995`、`a1 = [1 −0.995]`），通道为 `distMuP` / `distMuX` / `distcs` / `distcoil` / `distabc` / `distPAA` / `distTcin` / `distO_2in`，注释给出各自 SD（产素 ±0.0009 h⁻¹、菌体 ±0.011 h⁻¹、进料底物 ±15 g/L、PAA ±120 g/L、冷却液温度 ±3 K 等） |
| 移植现状 | Python 侧 `simulate.py:492-500` 把这 8 个通道**全部**替换为**确定性渐近式** `dist(t) = asym·(1 − exp(−t/τ))`（τ = 40 h）⇒ **随机成分（方差）完全丢失**，只保留了从 V3 反解出的渐近值（均值） |
| 后果 | 模型的时变扰动**没有方差** ⇒ 任何「预测不确定度」都**低估**真实扰动幅度；且该缺失**从未被量化** |
| 本轮处置 | **只登记，不改引擎** —— 把随机成分加回引擎会改变全部批的数值 ⇒ 属 **GOAL §5 边界变更**，需裁决 |
| 建议 | 下一轮做「扰动方差贡献量化」：用 oq#37 同款扫描（只改 `dist_*_asym` 的幅度），量出产量/轨迹误差对扰动幅度的敏感性，**先出数字再决定是否改引擎** |
| 证据 | `IndPenSim_V2.01/IndPenSim_V2.02/indpensim_run.m:148-181`；`candidate/indpensim/v0.1/simulate.py:492-500` |

### D-84　引擎**统一用名义 alpha_kla** ⇒ DO2 口径系统性失配，且双稳态批上是产量崖旋钮　🟡 **R162 新增，L2（参数化 + 判据）**

| 项 | 内容 |
|---|---|
| 发现 | 引擎 `golden_params.py` 86 批里 **81 批 alpha_kla = 85**（从未参与标定），而 MATLAB 端每批独立抽 `85 + 10*randn`（`indpensim_run.m:135`）⇒ 引擎对所有批假设传质系数相同 |
| 实测（oq#37） | 12 批 × 12 档 = **144 组**扫描（`runs/r162_kla_sensitivity.json`，747.9 s）：DO2 通道反解 `k*` 的跨批散布 **σ = 8.94**（名义 10，相对偏差 **10.6%**）⇒ **MATLAB 的批次级随机化在数据中确实生效**；**6/12 批** \\|k*−现役\\| > 20；DO2 口径 σ=10 影响中位 **1.95% relRMSE**（最大 5.26%） |
| 更严重的部分 | 在**双稳态 / 分岔批**（b55 / b60 / b91）上，alpha_kla 是**产量崖旋钮**：现役邻域内产量跳变 **73.9 / 57.4 / 33.8 pp**（b55：kla 80→90 使产量从 −39.5% 跳到 +34.4%）⇒ MATLAB 的批次级随机性足以决定这些批的产量成败 |
| 约束 | **不能用 DO2 通道单独标定 alpha_kla**（4 批两者最优 kla 相差 > 30；b55 最极端：DO2 偏好 140，产量最优 90） |
| 本轮处置 | **只登记，不改引擎** —— alpha_kla 逐批标定会改变全部批的数值 ⇒ 属 **GOAL §5 边界变更**，需裁决 |
| 建议 | ① 把 alpha_kla 列入**逐批标定候选**（在 DO2 + 产量**双约束**下解，且必须报告是否落在双稳态崖上）；② 短期可用 `validity()` / 形态指标把「双稳态批」标出来，避免用统一参数承诺 ±5% |
| 证据 | `runs/r162_kla_sensitivity.json`（144 组，12/12 判据 PASS） |

"""

# ---------------------------------------------------------------------------
# 2. 纪律 22–24
# ---------------------------------------------------------------------------
DISCIPLINES = """
22. **口径必须先核对符号再谈同构** —— MATLAB `Fremoved` 存**负值**出流 ⇒
    `harvested_during = sum(Fremoved·P)·h` 是**负数** ⇒ `yield_total = V_end·P_end − harvested_during`
    实为**加绝对值**。若不核符号就抄公式，会把「同构」判成「差一个负号」（R162 oq#38）。
23. **「复现随机源」类命题要先问「前提是否存在」** —— R162 oq#36 追查发现四层全部不可达
    （PCG64≠MT19937 / 播种方式不同 / Ziggurat≠polar / **种子基准来自 `rng('shuffle')` 且未被记录**），
    且**命题前提本身不成立**（Python 侧的扰动是确定性代理，**没有「种子」这个对象**）。
    **不可达的前提应当被证明并关闭，而不是反复投入。**
24. **「某参数无影响」的结论必须按口径分别给出，且必须检查悬崖** —— R162 oq#37 实测：
    alpha_kla 的 σ=10 对**产量口径**在 9/12 批上影响 < 0.4 pp（可忽略），
    但在**双稳态批**（b55/b60/b91）上达 **18.7–33.9 pp**、邻域内产量跳变 **33.8–73.9 pp**；
    同一参数在 **DO2 口径**上的影响中位 **1.95% relRMSE**。
    **一条「无影响」的结论若不区分口径、不检查悬崖，就是漏报。**
    附带：**灵敏度必须用局部窗口**——全局线性拟合会被端点崩溃档（低传质 ⇒ DO2 抑制 ⇒ 产量崩塌）污染；
    **跳变也必须限定在现役标定邻域内**，否则「悬崖」会被「崩溃区」冒充。
"""

# ---------------------------------------------------------------------------
# 3. 签核单 R-12
# ---------------------------------------------------------------------------
SIGNOFF_ROW = (
    "| **R-12** | **R162：M1 尾账收口 —— oq#36 / oq#37 / oq#38 三条全闭** —— "
    "① **oq#38 关闭（终末收获口径定案）**：MATLAB `indpensim_run.m:194-196` 原式 "
    "`harvested_during = sum(Fremoved·P)·h`（**负值**）/`harvested_end = V(end)·P(end)`/"
    "`yield_total = V(end)·P(end) − harvested_during` ⇒ 与 Python `yield_metrics` **逐位同构**"
    "（`max|Δ| = 0.000000e+00 g`，100/100 批）；**「终末收获」是后处理口径，不是需仿真的动态过程**，"
    "90 批 CSV 不含收获段**不构成缺口**（末行放罐非零的恰为 10 批 07/09/27/43/49/65/75/89/95/99，"
    "与 PROBLEM.md §9 一致）；反向验证：漏掉 `end_in_vessel` 偏差中位 −65.37%、最大 82.98%。"
    "② **oq#36 关闭为「命题证伪」**：四条候选路径逐位对齐全部不可达（PCG64≠MT19937 / 播种方式不同 / "
    "Ziggurat≠polar / **种子基准 `Random_seed_ref = ceil(rand*1000)` 来自 `rng('shuffle')` 且未被记录** ⇒ "
    "端到端复现原理上不可能）；且**前提不成立**（Python 侧扰动是确定性渐近式，**不存在「扰动种子」**）。"
    "③ **oq#37 关闭（量化完成）**：12 批 × 12 档 = 144 组扫描 ⇒ DO2 通道反解 `k*` 散布 **σ = 8.94**"
    "（名义 10，偏差 10.6%）⇒ **MATLAB 批次级随机化在数据中生效**；**产量口径** σ=10 影响在 9/12 批 < 0.4 pp，"
    "但**双稳态批** b55/b60/b91 达 **18.7–33.9 pp**（邻域内产量跳变 33.8–73.9 pp）；"
    "**DO2 口径** 中位 **1.95% relRMSE**（最大 5.26%）；**6/12 批** 统一用名义 85 失配 > 20；"
    "**DO2 拟合最优 ≠ 产量口径最优**（不能用 DO2 单独标定 alpha_kla）。"
    "④ **新增 D-83 / D-84**（MATLAB 扰动随机成分未移植 / alpha_kla 统一用名义值），"
    "**均属 GOAL §5 边界变更，本轮只出数字不改引擎**。**`cap` 口径不变**"
    "（仍 L2 prototype conditional，D-65 仍未闭合） | `docs/r162_round_report.md`；"
    "`docs/r157_debt_ledger.md` D-83/D-84；`runs/r162_m1_legacy_probe.json`（11/11 PASS）；"
    "`runs/r162_kla_sensitivity.json`（144 组，12/12 PASS）；`tools/r162_m1_legacy_probe.py`；"
    "`tools/r162_kla_sensitivity.py` |\n"
)

# ---------------------------------------------------------------------------
# 4. 路线图 §8.4
# ---------------------------------------------------------------------------
ROADMAP_BLOCK = """
### 8.4 R162 新增任务项（M1 尾账收口）

| # | 事项 | 优先级 | 成本 | 判据 |
|---|---|---|---|---|
| **R162-1** | **MCP 接入回退链**（D-80，沿用 R161-1）：`reconstruct_batch` 等现役路径接入 `solver_chain.resolve_tier` | 🔴 高 | 半天 | 降级标记出现在**返回体**（不许只在日志）；须重跑 MCP 路径回归 |
| **R162-2** | **alpha_kla 逐批标定**（D-84）：在 **DO2 + 产量双约束**下解 | 🔴 高 | 1 天 | 须报告每批是否落在双稳态崖上；**不得**只用 DO2 通道（b55 证伪） |
| **R162-3** | **扰动方差贡献量化**（D-83）：只改 `dist_*_asym` 幅度，量出敏感性 | 🟡 中 | 半天 | **先出数字再决定是否改引擎**；不改引擎 |
| **R162-4** | **回退链的真实退化批验证**（D-80，沿用 R161-3） | 🟡 中 | 半天 | 三层各有 ≥1 个批级触发样本（当前只有合成样本） |
| **R162-5** | **MHE 滚动时序调度**（D-80，沿用 R161-2） | 🟡 中 | 1 天 | 真实批上给出「比 EnKF 更好 / 不更好」的量化对照 |

> **R162 已做**：oq#36（命题证伪）/ oq#37（量化完成）/ oq#38（口径定案）三条全闭；
> 新增 D-83（MATLAB 扰动随机成分未移植）与 D-84（alpha_kla 统一用名义值）。
> **R161-4 / R161-5 已由本轮完成**（原写「PROBLEM.md §7.2」实为 **§7 验收标准第 2 条**，已勘误）。
> **cap 口径不变**（L2 prototype conditional）；**D-65 仍未闭合**（平台暂缓）。
"""

# ---------------------------------------------------------------------------
# 7. 台账总表：补 D-79 ~ D-84（总表是「未闭项清单，接手先读这个」的入口，
#    R161 未更新总表 ⇒ D-79~D-82 一直不可见；本轮一次补齐）
# ---------------------------------------------------------------------------
LEDGER_TABLE_ROWS = (
    "| D-79 | 集合 spread 判据在**地板饱和步**上假阳性 | L2 | ✅ **R161 关闭**（地板屏蔽 + 持续性 + 回归用例） |\n"
    "| D-80 | 回退链算子层**未接入现役路径** ⇒ 降级「有算子无触发」 | L2 | 🟡 **R161 新增**（接入属 GOAL §5 边界变更，需裁决） |\n"
    "| D-81 | 缺 `pytest.ini` / `conftest.py` | L1 | ✅ **R161 关闭**（新增配置，13+20 全绿） |\n"
    "| D-82 | 模型的 **T / Q 通道系统性偏差** ⇒ 创新判据在这两通道**恒真越限** | L2 | 🔴 **R161 新增**（模型层未修；判据改通道白名单） |\n"
    "| D-83 | MATLAB 端 **8 路时变扰动的随机成分未移植**（方差丢失，从未量化） | L2 | 🟡 **R162 新增**（只出数字不改引擎） |\n"
    "| D-84 | 引擎**统一用名义 alpha_kla** ⇒ DO2 口径失配，且双稳态批上是**产量崖旋钮** | L2 | 🟡 **R162 新增**（只出数字不改引擎） |\n"
)
LEDGER_TABLE_ANCHOR = "| D-75 | B 档回退链**实为单环**"

# ---------------------------------------------------------------------------
# 5. 契约 v1.92
# ---------------------------------------------------------------------------
CONTRACT_ROW = (
    "| v1.92 | R162：**M1 尾账收口 —— oq#36 / oq#37 / oq#38 三条全闭（D-83 / D-84 新增）** —— "
    "① **oq#38 终末收获口径定案**：MATLAB `indpensim_run.m:194-196` 原式 "
    "`harvested_during = sum(Fremoved·P)·h`（**Fremoved 存负值 ⇒ 该量为负**）/ "
    "`harvested_end = V(end)·P(end)` / `yield_total = V(end)·P(end) − harvested_during` ⇒ "
    "与 Python `simulate.py::yield_metrics` **逐位同构**（实测 100/100 批 `max|Δ| = 0.000000e+00 g`）；"
    "**「终末收获」是产出的后处理口径，不是需要仿真的动态过程** —— 终末收获量 = 末状态函数 `V_end·P_end`，"
    "与 CSV 是否出现收获记录无关 ⇒ **90 批 CSV 不含终末收获段不构成缺口**"
    "（末行 `Fremoved≠0` 的恰为 10 批：07/09/27/43/49/65/75/89/95/99，与 PROBLEM.md §9 一致）；"
    "反向验证：若漏掉 `end_in_vessel`（只算批内放罐）产量口径偏差 **中位 −65.37%、最大 82.98%**。"
    "② **oq#36 关闭为「命题证伪 + 替代口径确认」**：MATLAB rng → numpy 的四条候选路径"
    "（`default_rng` uniform / `RandomState` uniform / `RandomState` normal / 端到端）**逐位对齐全部不可达** —— "
    "根因依次为 **PCG64 ≠ MT19937**（max|Δ| 0.896872）、**播种方式不同**（`RandomState` 仍差 0.475763）、"
    "**normal transform Ziggurat ≠ polar**（seed 1/2/3 逐点全不等，max|Δ| 1.90–2.49）、"
    "以及**根本障碍**：MATLAB 种子基准 `Random_seed_ref = ceil(rand*1000)`（`indpensim_run.m:68`）来自 "
    "`rng('shuffle')`（`fctrl_indpensim.m:195,293`）**未被记录** ⇒ **端到端复现 V3 的批次级随机化原理上不可能**；"
    "且**命题前提不成立** —— Python 侧时变扰动是确定性渐近式 `dist(t)=asym·(1−exp(−t/τ))`（`simulate.py:492-500`），"
    "**不存在「扰动种子」**；`observe.py` 的 `default_rng` 属**估计器侧**（EnKF 集合初始化），与 MATLAB **数据侧**不同用途。"
    "③ **oq#37 alpha_kla 批次级随机性量化完成**（12 批 × 12 档 = 144 组，747.9 s）："
    "DO2 通道反解 `k*` 跨批散布 **σ = 8.94**（名义 10，偏差 **10.6%**）⇒ **MATLAB 的 `85 + 10·randn` 在数据中确实生效**；"
    "**产量口径** σ=10 影响在 9/12 批 < 0.4 pp（可忽略），但**双稳态批** b55/b60/b91 达 **18.7–33.9 pp**"
    "（现役邻域内产量跳变 **73.9 / 57.4 / 33.8 pp**）⇒ **alpha_kla 在这些批上是产量崖旋钮**；"
    "**DO2 口径** σ=10 影响中位 **1.95% relRMSE**（最大 5.26%）；**6/12 批** 统一用名义 85 失配 > 20；"
    "**DO2 拟合最优 ≠ 产量口径最优**（4 批相差 > 30）⇒ **不能用 DO2 单独标定 alpha_kla**。"
    "④ **新增 D-83**（MATLAB 8 路时变扰动的随机成分在移植时被丢弃）与 **D-84**（alpha_kla 统一用名义值）"
    "—— **两者均属 GOAL §5 边界变更，本轮只出数字不改引擎**。"
    "**引擎数值零改动**（零回归 86 批 `max|Δ| = 0.00e+00`、RMSE 2.345%、86/86） |"
)

# ---------------------------------------------------------------------------
# 6. tools/INDEX.md
# ---------------------------------------------------------------------------
INDEX_BLOCK = """
### R162（M1 尾账收口，oq#36/37/38）

| 工具 | 用途 | 备注 |
|---|---|---|
| `r162_m1_legacy_probe.py` | oq#38 终末收获口径 + oq#36 MATLAB rng 映射的**证伪式**探针：P1 逐位同构 / 符号自洽 / 零信息对照 / 反向验证 + 100 批放罐段普查；P2 四层映射对照（算法 / 播种 / 变换 / 种子基准） | 秒级。结论见 `docs/r162_round_report.md` |
| `r162_kla_sensitivity.py` | oq#37 alpha_kla 批次级随机性量化：12 批 × 12 档扫描，产量/P/DO2 三口径灵敏度 + DO2 通道反解 `k*` + 产量崖检测 | 144 组约 **12 min**（8 进程）；`--analyze-only` 可只重算判据。结论见 `docs/r162_round_report.md` |
| `r162_governance_update.py` | 治理层更新（台账 / 签核单 / 路线图 / 契约 / state / README / 工具索引 / 工作记忆） | **幂等**（逐条检查后写入，重复执行不产生重复条目） |
| `r162_final_check.py` | **R162 终检**（常驻可复跑）：A 探针判据 / B 报告结构 / C 治理层同步 / D 文档卫生 四组共 **39 条** | **只读**，秒级；`--json` 追加写 `runs/r162_final_check.json` |
"""


def main():
    changed = []

    # --- 0. 行尾归一化（修复 R161 治理脚本引入的 \r\r\n 双重 CR 污染）---
    for p in (CONTRACT, STATE):
        if normalize_eol(p):
            changed.append("行尾归一化: " + os.path.basename(p))

    # --- 1. 台账：新增 D-83 / D-84（插在 D-79 之前，保持「新增债」聚在一起） ---
    anchor = "### D-79　集合 spread 判据在**地板饱和步**上产生假阳性"
    if ensure_once(LEDGER, "### D-83　MATLAB 端", NEW_DEBTS_BLOCK, None, after=anchor):
        changed.append("台账: D-83/D-84")

    # --- 2. 台账：纪律 22–24 ---
    if append_once(LEDGER, "22. **口径必须先核对符号再谈同构**", DISCIPLINES, None):
        changed.append("台账: 纪律 22-24")

    # --- 2b. 台账总表：补 D-79 ~ D-84 + 标题更新到 R162 ---
    replace_once(LEDGER, "## 五、台账总表（截至 R157）", "## 五、台账总表（截至 R162）")
    if "| D-83 | MATLAB 端 **8 路时变扰动的随机成分未移植**" not in read(LEDGER)[0]:
        if insert_after_line(LEDGER, LEDGER_TABLE_ANCHOR, LEDGER_TABLE_ROWS):
            changed.append("台账: 总表补 D-79~D-84")

    # --- 3. 签核单 R-12 ---
    text, nl = read(SIGNOFF)
    if "**R-12**" not in text:
        lines = text.split("\n")
        idx = next((i for i, l in enumerate(lines) if "**R-11**" in l and l.startswith("|")), None)
        if idx is not None:
            lines.insert(idx + 1, SIGNOFF_ROW.rstrip("\n"))
            write(SIGNOFF, "\n".join(lines), nl)
            changed.append("签核单: R-12")

    # --- 4. 路线图 §8.4 ---
    if ensure_once(ROADMAP, "### 8.4 R162 新增任务项", ROADMAP_BLOCK, None):
        changed.append("路线图: §8.4")

    # --- 5. 契约：版本表 + 头部 ---
    # 必须插在 v1.91 行的**行尾**（R162 首版用 "after=| v1.91 |" 插到了行中间，
    # 把 v1.91 行内容挤成了 v1.92 的尾巴 ⇒ 破坏历史记录）
    if "| v1.92 |" not in read(CONTRACT)[0]:
        if insert_after_line(CONTRACT, "| v1.91 |", CONTRACT_ROW):
            changed.append("契约: v1.92 版本行")
    replace_once(CONTRACT,
                 "# ENGINE_CONTRACT.md — 求解器引擎批处理契约（v1.91，2026-11-05）",
                 "# ENGINE_CONTRACT.md — 求解器引擎批处理契约（v1.92，2026-11-05）")
    text, nl = read(CONTRACT)
    if text.startswith("# ENGINE_CONTRACT.md — 求解器引擎批处理契约（v1.92"):
        new_head = ("> 状态：**v1.92**（R162 **M1 尾账收口 —— oq#36 / oq#37 / oq#38 三条全闭；"
                    "D-83 / D-84 新增**。①**oq#38 终末收获口径定案**：MATLAB `indpensim_run.m:194-196` 原式 "
                    "与 Python `simulate.py::yield_metrics` **逐位同构**（100/100 批 `max|Δ| = 0.000000e+00 g`）"
                    "⇒ **「终末收获」是后处理口径，不是需仿真的动态过程**；90 批 CSV 不含收获段**不构成缺口**。"
                    "②**oq#36 关闭为「命题证伪」**：MATLAB rng → numpy 四条候选路径逐位对齐**全部不可达**"
                    "（PCG64≠MT19937 / 播种方式不同 / Ziggurat≠polar / **种子基准来自 `rng('shuffle')` 且未被记录**）"
                    "⇒ 端到端复现原理上不可能；且**前提不成立**（Python 侧扰动是确定性代理，**无「扰动种子」**）。"
                    "③**oq#37 量化完成**：DO2 通道反解 `k*` 散布 **σ = 8.94**（名义 10，偏差 10.6%）"
                    "⇒ MATLAB 批次级随机化在数据中生效；**产量口径** σ=10 影响在 9/12 批 < 0.4 pp，"
                    "但**双稳态批** b55/b60/b91 达 **18.7–33.9 pp**（邻域内产量跳变 33.8–73.9 pp）；"
                    "**DO2 口径** 中位 **1.95% relRMSE**；**6/12 批** 统一用名义 85 失配 > 20。"
                    "④**新增 D-83 / D-84**（均属 GOAL §5 边界变更，**本轮只出数字不改引擎**）。"
                    "**引擎数值零改动**（零回归 86 批 `max|Δ| = 0.00e+00`、RMSE 2.345%、86/86）。）。")
        lines = text.split("\n")
        for i, l in enumerate(lines):
            if l.startswith("> 状态：**v1.91**"):
                # 原 v1.91 状态块**逐字保留**，只把标签从「状态」降级为「历史」
                # （R162 首版把它压缩成一行 ⇒ 丢失约 1400 字符历史摘要，破坏版本链）
                lines[i] = new_head
                lines.insert(i + 1, l.replace("> 状态：**v1.91**（", "> **历史：v1.91**（", 1))
                write(CONTRACT, "\n".join(lines), nl)
                changed.append("契约: 头部状态块 v1.92（v1.91 原文降级保留）")
                break

    # --- 6. README ---
    replace_once(README,
                 "5. `docs/r161_round_report.md` —— 最近一轮；历史报告按编号倒序",
                 "5. `docs/r162_round_report.md` —— 最近一轮；历史报告按编号倒序"
                 "\n   （上一轮：`docs/r161_round_report.md`）", "\n")
    replace_once(README, "## 4. 当前状态（契约 v1.91）", "## 4. 当前状态（契约 v1.92）", "\n")
    # §4 验收表补一行 M1 口径定案（R162）
    readme_row = ("| **M1 遗留口径定案（R162）** | **oq#38 终末收获口径**："
                  "`end_of_batch 产量 ≡ −Σ(Fremoved·P)·h + V_end·P_end`，与 MATLAB `Penicllin_yield_total` "
                  "**逐位同构**（100/100 批 `max|Δ| = 0.000000e+00 g`）⇒ **「终末收获」是后处理口径，"
                  "不是需仿真的动态过程**；90 批 CSV 不含收获段**不构成缺口**。"
                  "**oq#36**：MATLAB rng → numpy 映射**原理上不可达**（种子基准未记录）⇒ 关闭为命题证伪。"
                  "**oq#37**：DO2 反解 alpha_kla 散布 **σ = 8.94**（名义 10）⇒ MATLAB 批次级随机化在数据中生效 | "
                  "三条全闭（**口径已定，非新增验收项**）；新增 **D-83 / D-84**（只出数字不改引擎） |\n")
    if "| **M1 遗留口径定案（R162）**" not in read(README)[0]:
        if insert_after_line(README, "| 能力档位 |", readme_row):
            changed.append("README: §4 M1 口径行")
    # §5 阻断项清单补 D-83 / D-84
    replace_once(README,
                 "D-52 双稳态 / D-53 残糖不可辨识 / D-64 P 与 PAA 软测量不可辨识 / D-54 缺葡萄糖闭环（L3）",
                 "D-52 双稳态 / D-53 残糖不可辨识 / D-64 P 与 PAA 软测量不可辨识 / D-54 缺葡萄糖闭环（L3）"
                 " / **D-83 扰动随机成分未移植** / **D-84 alpha_kla 统一用名义值**（R162 新增，均只出数字不改引擎）")
    readme_extra = """
## R162 M1 尾账收口（oq#36 / oq#37 / oq#38）

三条 M1 遗留未做项本轮全闭，**引擎数值零改动**：

| oq | 结论 |
|---|---|
| **#38** 终末收获口径 | **定案**：`end_of_batch 产量 ≡ −Σ(Fremoved·P)·h + V_end·P_end`，与 MATLAB `Penicllin_yield_total` **逐位同构**（100/100 批 `max|Δ| = 0.000000e+00 g`）。**「终末收获」是后处理口径，不是需仿真的动态过程** ⇒ 90 批 CSV 不含收获段**不构成缺口** |
| **#36** MATLAB rng → numpy 映射 | **关闭为「命题证伪」**：四条候选路径逐位对齐**全部不可达**（PCG64≠MT19937 / 播种方式不同 / Ziggurat≠polar / **种子基准来自 `rng('shuffle')` 且未被记录**）⇒ 端到端复现原理上不可能；且前提不成立（Python 侧扰动是确定性代理） |
| **#37** alpha_kla 批次级随机性 | **量化完成**：DO2 通道反解 `k*` 散布 **σ = 8.94**（名义 10）⇒ MATLAB 批次级随机化在数据中生效；**产量口径** 9/12 批可忽略，但**双稳态批**达 18.7–33.9 pp；**DO2 口径** 中位 1.95% relRMSE |

新增两条债：**D-83**（MATLAB 8 路时变扰动的随机成分在移植时被丢弃）、**D-84**（alpha_kla 统一用名义值）——
两者均属 GOAL §5 边界变更，**本轮只出数字不改引擎**。

证据：`docs/r162_round_report.md`、`runs/r162_m1_legacy_probe.json`（11/11 PASS）、
`runs/r162_kla_sensitivity.json`（144 组，12/12 PASS）。
"""
    if ensure_once(README, "## R162 M1 尾账收口", readme_extra, None):
        changed.append("README: R162 节")

    # --- 7. tools/INDEX.md ---
    if ensure_once(INDEX, "### R162（M1 尾账收口", INDEX_BLOCK, None):
        changed.append("INDEX: R162 段")

    # --- 8. state.yaml ---
    st, nl = read(STATE)
    if nl != "\r\n":
        print("WARN: state.yaml 不是 CRLF，保留原风格", nl.encode("unicode_escape"))
    oq_repl = [
        ("- MATLAB rng 序列 → numpy default_rng 映射（扰动/故障种子）待 M1 对照实验",
         "- ✅ R162 **oq#36 已关闭（命题证伪）**：MATLAB rng → numpy `default_rng` 的四条候选路径"
         "（`default_rng` uniform / `RandomState` uniform / `RandomState` normal / 端到端）**逐位对齐全部不可达** —— "
         "根因依次为 **PCG64≠MT19937**（max|Δ| 0.896872）、**播种方式不同**（`RandomState` 仍差 0.475763）、"
         "**normal transform Ziggurat≠polar**（seed 1/2/3 逐点全不等，max|Δ| 1.90–2.49）、"
         "以及**根本障碍**：MATLAB 种子基准 `Random_seed_ref = ceil(rand*1000)`（`indpensim_run.m:68`）来自 "
         "`rng('shuffle')`（`fctrl_indpensim.m:195,293`）**未被记录** ⇒ 端到端复现 V3 的批次级随机化**原理上不可能**；"
         "且**命题前提不成立** —— Python 侧时变扰动是确定性渐近式 `dist(t)=asym·(1−exp(−t/τ))`"
         "（`simulate.py:492-500`），**不存在「扰动种子」**；`observe.py` 的 `default_rng` 属**估计器侧**"
         "（EnKF 集合初始化），与 MATLAB **数据侧**不同用途。**替代口径早已生效**：批级参数从 V3 实测反解后逐批登记"),
        ("- alpha_kla 批次间随机性（85±10）对复现精度的影响待量化",
         "- ✅ R162 **oq#37 已关闭（量化完成）**：MATLAB `alpha_kla = 85 + 10·randn`（`indpensim_run.m:135`）的批次级随机化"
         "**在 V3 数据中确实生效** —— DO2 通道反解 `k*` 的跨批散布 **σ = 8.94**（名义 10，相对偏差 **10.6%**，"
         "12 批 × 12 档 = 144 组扫描，747.9 s）。**结论必须分口径给**：① **产量口径** σ=10 的影响在 **9/12 批 < 0.4 pp**"
         "（可忽略），但在**双稳态/分岔批**（b55/b60/b91）达 **18.7–33.9 pp**，现役邻域内产量跳变 **73.9 / 57.4 / 33.8 pp** ⇒ "
         "**alpha_kla 在这些批上是产量崖旋钮**；② **DO2 口径** σ=10 影响中位 **1.95% relRMSE**（最大 5.26%）⇒ 不可忽略；"
         "③ **6/12 批** 统一用名义 85 失配 > 20；④ **DO2 拟合最优 ≠ 产量口径最优**（4 批相差 > 30）⇒ "
         "**不能用 DO2 通道单独标定 alpha_kla**"),
        ("- 终末收获后处理步骤的复现方式（90 批 CSV 不含）待 M1 定案",
         "- ✅ R162 **oq#38 已关闭（口径定案）**：**end_of_batch 产量 ≡ `−Σ(Fremoved·P)·h`（批内放罐段累计）+ `V_end·P_end`"
         "（批末罐内剩余，全部收走）**，与 MATLAB `indpensim_run.m:194-196` 的 `Penicllin_yield_total` **逐位同构**"
         "（100/100 批 `max|Δ| = 0.000000e+00 g`；注意 `Fremoved` 存**负值** ⇒ `harvested_during` 为负，"
         "第三行的「减」实为加绝对值）。**「终末收获」是产出的后处理口径，不是需要仿真的动态过程** —— "
         "终末收获量 = **末状态的函数**，与 CSV 是否出现收获记录无关 ⇒ **90 批 CSV 不含收获段不构成缺口**"
         "（末行 `Fremoved≠0` 的恰为 10 批 07/09/27/43/49/65/75/89/95/99，与 PROBLEM.md §9 一致；"
         "全部 100 批放罐段恒自 t=100.2 h 起、流量恒 −4000 L/h）。反向验证：若漏掉 `end_in_vessel`"
         "（只算批内放罐）产量口径偏差 **中位 −65.37%、最大 82.98%**"),
    ]
    for old, new in oq_repl:
        if old in st:
            st = st.replace(old, new, 1)
            changed.append("state: oq 关闭")
    # 新增 D-83 / D-84 两条 oq
    new_oq = ("- 🟡 R162 D-83（新增，L2）：MATLAB 端 **8 路时变扰动的随机成分未移植** —— "
              "`indpensim_run.m:148-181` 用 `filter(b1,a1,scale·randn)` 生成 8 路随机低通扰动，"
              "而 `simulate.py:492-500` 全部替换为**确定性渐近式** `dist(t)=asym·(1−exp(−t/τ))` ⇒ "
              "**方差成分完全丢失**且从未量化 ⇒ 任何「预测不确定度」都低估真实扰动幅度；"
              "本轮**只登记不改引擎**（属 GOAL §5 边界变更）\n"
              "- 🟡 R162 D-84（新增，L2）：引擎**统一用名义 alpha_kla**（86 批中 81 批 = 85，从未参与标定）⇒ "
              "DO2 口径系统性失配（6/12 批 \\|k*−base\\| > 20），且在**双稳态批**（b55/b60/b91）上 "
              "alpha_kla 是**产量崖旋钮**（邻域内跳变 33.8–73.9 pp）⇒ **不能用 DO2 通道单独标定**；"
              "逐批标定属 GOAL §5 边界变更，本轮**只出数字不改引擎**\n")
    if "R162 D-83（新增，L2）" not in st:
        anchor = "- ✅ R161 D-82（新债，L2）"
        idx = st.find(anchor)
        if idx >= 0:
            # 找到该条目所在行的结尾（下一个 "- " 行首）
            nxt = st.find("\n- ", idx + 1)
            if nxt < 0:
                nxt = len(st)
            st = st[:nxt + 1] + new_oq + st[nxt + 1:]
            changed.append("state: D-83/D-84 oq")
    # artifacts
    if "r162_m1_legacy:" not in st:
        st = st.rstrip("\n") + "\n" + (
            "  r162_m1_legacy: runs/r162_m1_legacy_probe.json - R162 oq#36/oq#38 证伪式探针（11/11 PASS）\n"
            "  r162_kla_sensitivity: runs/r162_kla_sensitivity.json - R162 oq#37 alpha_kla 灵敏度与 DO2 反解"
            "（12 批 × 12 档 = 144 组，747.9 s，12/12 PASS）\n"
            "  r162_report: docs/r162_round_report.md\n")
        changed.append("state: artifacts")
    # 终检工具（后加的常驻件，单独守卫以免被上面的 if 吞掉）
    if "r162_final_check:" not in st:
        st = st.rstrip("\n") + "\n" + (
            "  r162_final_check: tools/r162_final_check.py - R162 终检（39 条，只读常驻可复跑）\n")
        changed.append("state: artifacts(final_check)")
    # recent_route
    if "R162 **M1 尾账收口" not in st:
        route = ("- ts: 2026-11-05T20:30\n  from: M5\n  to: M5\n  decision: REVISE\n"
                 "  reason: R162 **M1 尾账收口 —— oq#36 / oq#37 / oq#38 三条全闭**"
                 "（`tools/r162_m1_legacy_probe.py` 11/11 PASS + `tools/r162_kla_sensitivity.py` 144 组 12/12 PASS；"
                 "D-83 扰动随机成分未移植 / D-84 alpha_kla 统一用名义值，均属 GOAL §5 边界变更本轮只出数字不改引擎；"
                 "引擎数值零改动，零回归 86 批 max|Δ|=0.00e+00、RMSE 2.345%、86/86）\n")
        idx = st.find("recent_route:")
        if idx >= 0:
            idx = st.index("\n", idx) + 1
            st = st[:idx] + route + st[idx:]
            changed.append("state: recent_route")
    write(STATE, st, nl)

    # --- 9. 工作记忆 ---
    if os.path.exists(MEMLOG):
        mem = """
## R162　M1 尾账收口（oq#36 / oq#37 / oq#38 三条全闭）

**目标**：收 M1 遗留尾账（`state.yaml` open_questions 三条）。

**新增工件（只读探针，引擎零改动）**
- `tools/r162_m1_legacy_probe.py` → `runs/r162_m1_legacy_probe.json`（P1 oq#38 + P2 oq#36，**11/11 PASS**）
- `tools/r162_kla_sensitivity.py` → `runs/r162_kla_sensitivity.json`（P3 oq#37，144 组，**12/12 PASS**，747.9 s）
- `docs/r162_round_report.md`（十章）
- `tools/r162_final_check.py` → **R162 终检**（39 条：A 探针判据 / B 报告结构 / C 治理层同步 / D 文档卫生）
  —— **只读**、秒级、常驻可复跑；`--json` 追加写 `runs/r162_final_check.json`

**oq#38 终末收获口径（关闭）**
MATLAB `indpensim_run.m:194-196`：`harvested_during = sum(Fremoved·P)·h`（**Fremoved 负值 ⇒ 为负**）/
`harvested_end = V(end)·P(end)`/`yield_total = V(end)·P(end) − harvested_during`
⇒ 与 Python `yield_metrics` **逐位同构**（100/100 批 `max|Δ| = 0.000000e+00 g`）。
**「终末收获」是后处理口径，不是需仿真的动态过程** ⇒ 90 批 CSV 不含收获段**不构成缺口**
（末行放罐非零的恰为 10 批 07/09/27/43/49/65/75/89/95/99，与 PROBLEM.md §9 一致）。
反向验证：漏掉 `end_in_vessel` ⇒ 偏差中位 −65.37%、最大 82.98%。

**oq#36 MATLAB rng → numpy（关闭为命题证伪）**
四层全部不可达：PCG64≠MT19937（0.896872）/ 播种方式不同（`RandomState` 仍差 0.475763）/
Ziggurat≠polar（seed 1/2/3 逐点全不等，1.90–2.49）/ **种子基准 `Random_seed_ref = ceil(rand*1000)`
来自 `rng('shuffle')` 且未记录 ⇒ 端到端复现原理上不可能**。
且**前提不成立**：Python 侧扰动是确定性渐近式 `asym·(1−exp(−t/τ))`（τ=40 h）⇒ **无「扰动种子」**；
`observe.py` 的 `default_rng` 属估计器侧（EnKF 集合初始化）。

**oq#37 alpha_kla 批次级随机性（量化完成）**
MATLAB `85 + 10·randn`；引擎 86 批中 81 批恒为 85。
12 批 × 12 档（30…140）= 144 组：DO2 反解 `k*` 散布 **σ = 8.94**（名义 10，偏差 10.6%）⇒ **随机化在数据中生效**。
**分口径**：产量口径 9/12 批 σ=10 影响 < 0.4 pp，但**双稳态批** b55/b60/b91 达 **18.7–33.9 pp**
（邻域内跳变 73.9/57.4/33.8 pp）⇒ alpha_kla 是**产量崖旋钮**；DO2 口径中位 **1.95% relRMSE**（最大 5.26%）。
6/12 批统一用名义 85 失配 > 20；**DO2 最优 ≠ 产量最优**（不能用 DO2 单独标定）。
**方法论**：灵敏度必须用**局部窗口**（全局拟合被端点崩溃档污染）；跳变也必须限定在现役邻域内
（否则「悬崖」被「崩溃区」冒充）—— 判据 C9 因此重写。

**新增债**：**D-83**（MATLAB 8 路时变扰动随机成分未移植）、**D-84**（alpha_kla 统一用名义值）。
两者均属 GOAL §5 边界变更 ⇒ 本轮**只出数字不改引擎**。

**闸门**：零回归 86 批 `max|Δ| = 0.00e+00`、RMSE 2.345%、86/86；`py -m pytest -q` 33 passed。
**`cap` 口径不变**（L2 prototype conditional，D-65 仍未闭合）。
"""
        # 直接交给 append_once 判定（不要用 `marker not in mem` ——
        # 待写内容本身就含 marker ⇒ 该判断恒假 ⇒ 章节永远写不进去）
        if append_once(MEMLOG, "R162　M1 尾账收口", mem, None):
            changed.append("记忆: R162 章节")

    print("=== R162 治理层更新 ===")
    if changed:
        for c in changed:
            print("  +", c)
    else:
        print("  （全部已存在，无需写入 —— 幂等）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
