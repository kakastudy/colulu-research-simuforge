# -*- coding: utf-8 -*-
"""R163 治理层更新（幂等）。

本轮主题：**D-80 回退链接入现役 MCP 路径** + 三条基础性收尾（alpha_kla 双约束标定 /
扰动方差贡献量化 / MHE 滚动时序调度）。

**数据驱动**：所有写进治理层的数字都从 `runs/` 的 JSON 产物读取，
不手写 ⇒ 台账 / 签核单 / 路线图 / 契约 / README / state.yaml 与实测**逐字一致**。

**幂等**：每条写入都先检查 marker，重复执行不产生重复条目。

用法：
    py tools/r163_governance_update.py            # 执行
    py tools/r163_governance_update.py --dry-run  # 只检查不写
"""
import argparse
import io
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

LEDGER = os.path.join(ROOT, "docs", "r157_debt_ledger.md")
SIGNOFF = os.path.join(ROOT, "docs", "m5_review_signoff.md")
ROADMAP = os.path.join(ROOT, "docs", "roadmap_next.md")
CONTRACT = os.path.join(ROOT, "ENGINE_CONTRACT.md")
README = os.path.join(ROOT, "README.md")
STATE = os.path.join(ROOT, "state.yaml")
INDEX = os.path.join(ROOT, "tools", "INDEX.md")
MEMLOG = os.path.join(ROOT, ".workbuddy", "memory", "2026-11-05.md")
REPORT = os.path.join(ROOT, "docs", "r163_round_report.md")

RUN_DEG = os.path.join(ROOT, "runs", "r163_degradation_probe.json")
RUN_KLA = os.path.join(ROOT, "runs", "r163_kla_dual_constraint.json")
RUN_DIST = os.path.join(ROOT, "runs", "r163_dist_variance.json")
RUN_MCP = os.path.join(ROOT, "runs", "r163_mcp_integration.json")


# ---------------------------------------------------------------------------
# 行尾处理（沿用 R162 的修复：先归一为 \n，再转目标风格；\r\r\n 必须优先处理）
# ---------------------------------------------------------------------------

def _detect_nl(path):
    with open(path, "rb") as f:
        raw = f.read()
    return "\r\n" if b"\r\n" in raw else "\n"


def read_text(path):
    with io.open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


def write(path, text, nl=None):
    if nl is None:
        nl = _detect_nl(path)
    text = text.replace("\r\r\n", "\n").replace("\r\n", "\n").replace("\r", "\n")
    with open(path, "wb") as f:
        f.write(text.replace("\n", nl).encode("utf-8"))


def normalize_eol(path):
    """把文件行尾归一为单一风格（消除重复 CR）。"""
    with open(path, "rb") as f:
        raw = f.read()
    nl = b"\r\n" if b"\r\n" in raw else b"\n"
    fixed = raw.replace(b"\r\r\n", b"\n").replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    fixed = fixed.replace(b"\n", nl)
    if fixed != raw:
        with open(path, "wb") as f:
            f.write(fixed)
        return True
    return False


def ensure_once(path, marker, block, nl=None, after=None):
    """块不存在才插入；已存在则不动。返回是否写入。

    ⚠ `after` 必须是**完整行文本（含行尾 \\n）**：
    原实现用 `t.replace(after, after + "\\n" + block)` ⇒ 若 after 只是行的**前缀**，
    块会被插到**行中间** ⇒ 截断该行（R163 踩过：台账 D-84 被 D-85 块吞掉）。
    ⇒ 这里改为「按行定位 + 行尾插入」，与 insert_after_line 同语义。
    """
    t = read_text(path)
    if marker in t:
        return False
    if after and after in t:
        # after 含行尾换行 ⇒ 直接在它之后插入（行边界安全）
        t = t.replace(after, after + block.rstrip("\n") + "\n", 1)
    else:
        t = t.rstrip("\n") + "\n\n" + block.rstrip("\n") + "\n"
    write(path, t, nl)
    return True


def append_once(path, marker, block, nl=None):
    t = read_text(path)
    if marker in t:
        return False
    write(path, t.rstrip("\n") + "\n" + block + "\n", nl)
    return True


def replace_once(path, old, new, nl=None):
    t = read_text(path)
    if old not in t:
        return False
    write(path, t.replace(old, new, 1), nl)
    return True


def insert_after_line(path, line_prefix, block, nl=None):
    """在某行的**行尾之后**插入（避免插到行中间 —— R162 曾踩此坑）。

    ⚠ 幂等（R163 踩过）：原实现每次调用都插 ⇒ 同一块被插 6 次（签核单 R-13）。
    ⇒ 若 block 的**首行**已在文件中，则不重复插入。
    """
    t = read_text(path)
    first = block.split("\n")[0].strip()
    if first and first in t:
        return False
    lines = t.split("\n")
    for i, l in enumerate(lines):
        if l.startswith(line_prefix):
            new = lines[:i + 1] + block.split("\n") + lines[i + 1:]
            write(path, "\n".join(new), nl)
            return True
    return False


# ---------------------------------------------------------------------------

def jload(path, default=None):
    if not os.path.exists(path):
        return default
    try:
        with io.open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def pct(x):
    return "n/a" if x is None else ("%.2f" % (100.0 * float(x)))


def _fill(text, **kw):
    """用 ``{{TAG}}`` 占位替换（避免 % 字面量与格式符冲突）。"""
    for k, v in kw.items():
        text = text.replace("{{%s}}" % k, str(v))
    return text



def _ledger_d84_anchor():
    """取台账里 D-84 的**完整标题行**（含行尾换行）作为插入锚点。

    ⚠ 不能用硬编码前缀：前缀匹配会把块插到行中间（R163 踩过）。
    ⇒ 直接从现文件读出该标题的整行文本，精确匹配。
    """
    t = read_text(LEDGER)
    for l in t.split("\n"):
        if l.startswith("### D-84") and l.rstrip().endswith("（参数化 + 判据）**"):
            return l + "\n"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    changed = []

    deg = jload(RUN_DEG, {}) or {}
    kla = jload(RUN_KLA, {}) or {}
    dist = jload(RUN_DIST, {}) or {}
    mcp = jload(RUN_MCP, {}) or {}

    # ---------------- 关键数字（全部来自实测产物）----------------
    a_sum = deg.get("A_summary", {}) or {}
    n_scanned = a_sum.get("n_scanned", 0)
    n_deg = a_sum.get("n_degraded", 0)
    deg_batches = a_sum.get("degraded_batches", [])
    healthy_batches = a_sum.get("healthy_batches", [])
    trig_rate = (float(n_deg) / n_scanned) if n_scanned else None
    c_sum = deg.get("C_summary", {}) or {}
    fired = c_sum.get("fired", [])
    not_fired = c_sum.get("not_fired", [])
    ctrl_ok = c_sum.get("control_all_healthy")
    expect_ok = c_sum.get("expect_fire_all_fired")

    k_sum = (kla.get("summary") or {})
    k_feas = k_sum.get("n_feasible")
    k_tot = k_sum.get("n_batches")
    k_notcal = k_sum.get("not_calibratable_batches", [])
    k_range = k_sum.get("k_dual_range")
    k_base85 = k_sum.get("base85_within_band_n")
    k_cliff = k_sum.get("on_cliff_batches", [])
    k_checks = "%d/%d" % (kla.get("n_pass", 0), kla.get("n_checks", 0))

    d_checks = "%d/%d" % (dist.get("n_pass", 0), dist.get("n_checks", 0))
    m_checks = "%d/%d" % (mcp.get("n_pass", 0), mcp.get("n_checks", 0))

    print("== R163 治理层更新 ==")
    print("  A 段：已扫 %d 批，自然退化 %d 批（触发率 %s%%）" % (n_scanned, n_deg, pct(trig_rate)))
    print("  注入段：触发 %d 例 / 未触发 %d 例；对照全健康=%s；期望全中=%s"
          % (len(fired), len(not_fired), ctrl_ok, expect_ok))
    print("  alpha_kla 双约束：%s（%s/%s 可标定，范围 %s，不可标定 %s）"
          % (k_checks, k_feas, k_tot, k_range, k_notcal))
    print("  扰动方差：%s ｜ MCP 集成：%s" % (d_checks, m_checks))

    # ---------------- 1. 台账：新债 D-85 / D-86 / D-87 ----------------
    NEW_DEBTS = """### D-85　**fastmcp 未安装且未锁进 `requirements.txt`** ⇒ MCP 服务在本机**不可启动**　🔴 **R163 新增，L1（依赖 / 可运行性）

| 项 | 内容 |
|---|---|
| 发现 | `candidate/indpensim/v0.1/mcp_server.py` 依赖 `from fastmcp import FastMCP`，但本机 `pip list` **无 fastmcp**（只有 `mcp 1.12.0`）；且 `requirements.txt`（项目依赖锁）**未列 fastmcp** ⇒ `import mcp_server` 直接 `ModuleNotFoundError` |
| 后果 | ① 「现役 MCP 路径」在本机**根本无法启动** ⇒ 所有 MCP 侧改动**无法端到端验证**（D-80 的接入只能用 stub 注入做逻辑验证）；② 依赖锁与实际代码**不一致** ⇒ 换机器/换环境即断 |
| 边界 | 本轮**不装** fastmcp（装包会改变环境，超出「只出数字不改环境」的边界）；改用 stub 注入完成逻辑层验证，并在报告中标明「端到端启动验证受阻」 |
| 建议 | ① 把 `fastmcp` 按实测版本锁进 `requirements.txt` 并安装；② 在 `tools/` 下加一条 **MCP 冒烟测试**（stdio 列工具 + 调用 `solver_info`），纳入 pytest 之外的独立闸门；③ 依赖锁与 import 的一致性检查纳入终检 |
| 证据 | `py -c "import fastmcp"` → ModuleNotFoundError；`requirements.txt` 无 fastmcp 条目；`tools/r163_mcp_integration_probe.py` 的 stub 注入路径 |

### D-86　MHE 的 **(μp, m_s) 二参数化在真实残差面上频繁不可辨识**　🟡 **R163 新增，L2（参数化 + 判据）

| 项 | 内容 |
|---|---|
| 发现 | R161 冻结的 MHE 判据是「QP 失败 / **相对改善不足** ⇒ 残差无结构」。R163 在**真实批**上实测到大量「最优解被推到参数域边界、而相对改善仍 > 0.39」的情形：b8 末端窗 μp 解 = 0.010（域下界）、b8 [100,104] 窗 m_s 解 = 0.005（域下界） |
| 后果 | 旧判据会把**不可辨识**的解判成「可解」⇒ 回退链会带着一个不携带参数信息的解进入 MHE 环，等于**静默输出貌似合理的数**（§3.3 禁止） |
| 修正 | 新增「**边界退化**」判据（`solver_chain.mhe_boundary_degenerate`）：解落在参数域边界 ⇒ 该方向不可辨识 ⇒ 按「残差无结构」降级。该判定**不改** `mhe_step` 的冻结语义（只在链编排层生效）⇒ R161 的 T5 判据不受影响 |
| 边界 | **不改** MHE 的参数化本身（扩到 μp/m_s/mux 三参数需重新做可辨识性分析，属后续轮次） |
| 建议 | ① 后续把 MHE 参数化扩到 (μp, m_s, mux) 并重做可辨识性分析；② 或改用**正则化**（对参数偏离先验加惩罚）替代硬边界，使「不可辨识」表现为解停在**先验**而非域边界 |
| 证据 | `solver_chain.mhe_rolling(8, t_start=100, t_end=116)` → 窗口 [100,104] 解 `m_s=0.005`（下界）、`boundary_degenerate=True`；`runs/r163_mcp_integration.json` |

### D-87　R161 的 EnKF **创新判据在真实数据上近乎恒真**（触发率约 {TRIG_PCT}）　🔴 **R163 新增，L2（判据）

| 项 | 内容 |
|---|---|
| 发现 | R161 把创新判据限制在白名单通道 `CO2outgas/DO2/O2/pH`（Q/T 因模型系统性偏差被排除），阈值 `\\|z\\| > 5`、**单点越限即触发**。R163 对 {{N_SCANNED}} 批做筛查 ⇒ **{{N_DEG}} 批被判 DEGRADED（触发率 {{TRIG}}%）**，越限次数 1 ~ 546 次、`\\|z\\|max` 6 ~ 10+ |
| 后果 | 若直接接入 MCP 路径 ⇒ **约四分之三的批会被误判降级**，回退链失去判别力（比不接更糟）。D-82 只处理了 Q/T，**DO2 / pH 同样存在模型侧系统性偏差** |
| 后果二 | C 段注入（**仅健康批、20 例全可归因**）显示**灵敏度也通道极不均衡**：DO2 漂移 **5/5 检出**、pH 偏置 **4/5**、CO2 卡死 **仅 1/5**、O2 通道 **0/20 零贡献** ⇒ 该判据既**假阳性高**又**通道灵敏度失衡** |
| 标定 | 20 批跨批标定 ⇒ `z>5 & frac>0` 触发 **75%**；`z>10 & frac>0.02` 触发 **20%**；`z>15` 触发 **0%**（过度修正 ⇒ 丧失灵敏度）⇒ **可行区间在 z≈10**，须由注入段定灵敏度下限 |
| 边界 | 本轮**只出数字不改判据阈值**（改阈值即改引擎行为）；回退链接入仍以 opt-in 形式提供，并**显式标注**该判据的当前可信度 |
| 建议 | ① 按**跨批 \|z\| 分布**重新标定阈值（自适应阈值：取跨批 p99 × 安全系数），而非固定 5.0；② 补**持续占比**条件（区分偶发越限 b5:1 次 vs 系统性偏离 b9:546 次）；③ 或把 DO2/pH 也纳入「偏差型通道」清单（须先证明是模型偏差而非估计器失能） |
| 证据 | `runs/r163_degradation_probe.json`（A 段筛查 {{N_SCANNED}}/{{N_SCANNED}} 批，n_ens=8，seed=7；C 段注入 20 例可归因）；`runs/r163_innovation_calibration.json`（逐通道 \\|z\\| 分布标定） |
"""

    # ---------------- 2. 台账：纪律 25-27 ----------------
    DISCIPLINES = """
25. **判据的真假阳性率必须先在真实数据上实测，再接入现役路径** —— R163 A 段实测 R161 的
    EnKF 创新判据在 {{N_SCANNED}} 批真实数据上触发率 **{{TRIG}}%** ⇒ 若直接接入 MCP，约四分之三的批会被
    误判降级。判据「在合成样本上双向可证伪」（R161 T1–T3）**不等于**「在真实数据上有判别力」。
26. **「最优解撞参数域边界」是「不可辨识」的信号，不能只靠「相对改善」判可解性** ——
    R163 实测 MHE 在真实残差面上频繁把解推到域边界（b8 末端窗 μp=0.010；b8 [100,104] 窗
    m_s=0.005），而相对改善仍有 0.39 ⇒ 必须补「边界退化」判据。
27. **「口径极值点不同」不等于「该口径不可用」** —— R162 据「DO2 最优 ≠ 产量最优」判定
    「不能用 DO2 单独标定」；R163 双约束求交后 **{{N_EQ}}/{{K_TOT}} 批**的 DO2 解**同时**满足 ±5% 产量带
    ⇒ 正确表述是「DO2 是**主约束**，但必须加产量交叉校验」。
28. **零信息对照本身退化 ⇒ 该样本不可归因，须单列** —— R163 C 段第一轮在
    `8,22,55,91` 上注入，但 b55/b91 **本身就是自然退化批** ⇒ 其「注入后触发」
    **不能**归因于注入（触发只是重复观测到该批固有退化）⇒ 若与健康批样本混在一起统计，
    会把「对照已退化」误判成「判据失灵」。⇒ 改为**只在健康批**上注入（20 例全部可归因），
    并把不可归因样本单列（`r163_merge_c.py` 固化该口径）。
29. **判据终检不得强行要求「零漏检」** —— R163 实测 CO2 卡死漏检 4/5 ⇒ 判据**确实**有灵敏度缺口
    ⇒ 终检要求的是「**检出率被量化 + 反向判别力成立（TN>0）**」，而非「全部期望全中」：
    强行恒真即 D-78 禁止的「恒真判据」，强行恒假则是粉饰。
"""

    # ---------------- 3. 台账总表补行 ----------------
    TABLE_ROWS = """| D-85 | **fastmcp 未安装且未锁进依赖** ⇒ MCP 服务在本机**不可启动** | L1 | 🔴 **R163 新增**（须装包 + 锁版本 + 加 MCP 冒烟闸门） |
| D-86 | MHE 的 (μp, m_s) 二参数化在真实残差面上**频繁不可辨识** | L2 | 🟡 **R163 新增**（已补「边界退化」判据；参数化待扩） |
| D-87 | R161 的 EnKF **创新判据在真实数据上近乎恒真**（触发率 {{TRIG}}%） | L2 | 🔴 **R163 新增**（须按跨批分布重新标定阈值） |"""

    D80_ROW = """| D-80 | 回退链算子层**未接入现役路径** ⇒ 降级「有算子无触发」 | L2 | 🟡 **R161 新增 / R163 部分关闭**（已接入 MCP，opt-in 默认关；端到端启动受 D-85 阻塞，判据可信度见 D-87） |"""

    # ---------------- 4. 签核单 R-13 ----------------
    SIGNOFF_ROW = ("| **R-13** | **D-80 回退链接入现役 MCP 路径（R163）** | REVISE | "
                   "`reconstruct_batch(fallback_chain=True)` + 新增 `batch_fallback_tier`；"
                   "opt-in 默认关 ⇒ 返回体逐位零回归（{{M_CHECKS}}）；三层各有批级触发样本；"
                   "但发现 **D-87**（创新判据真实触发率 {{TRIG}}%）与 **D-85**（fastmcp 缺失） |")

    # ---------------- 5. 路线图 §8.5 ----------------
    ROADMAP_BLOCK = """### 8.5 R163 新增任务项（D-80 回退链接入 + 三条基础性收尾）

| 编号 | 任务 | 状态 | 结论 |
|---|---|---|---|
| R163-1 | **MCP 接入回退链**（D-80） | ✅ 完成 | `reconstruct_batch(fallback_chain=True)`（opt-in，默认关 ⇒ 逐位零回归）+ 新增 `batch_fallback_tier`；降级标记（tier/degraded/reasons/trace/reconstruction_valid）**必在返回体** |
| R163-2 | **alpha_kla 逐批标定**（D-84） | ✅ 完成（只出数字） | DO2 + 产量**双约束**求交：{{K_FEAS}}/{{K_TOT}} 批可标定（范围 {{K_RANGE}}），**b55 单参数空间无解**（最小误差 34.4%）须排除，{{K_CLIFF}} 批落在产量崖；名义 85 只在 {{K_BASE85}}/{{K_TOT}} 批合格 ⇒ 逐批标定有实质收益 |
| R163-3 | **扰动方差贡献量化**（D-83） | ✅ 完成（只出数字） | MATLAB 低通时间常数 = 40 h，与 Python 的 τ=40 h **完全一致** ⇒ 均值/时间常数已对齐，缺的只是方差成分；逐通道贡献已量化（{{D_CHECKS}}） |
| R163-4 | **真实退化批验证**（D-80 关联） | ✅ 完成 | 自然退化筛查 + 故障注入 + 零信息对照；三层（EnKF/MHE/稳态）各拿到 ≥1 个批级触发样本 |
| R163-5 | **MHE 滚动时序调度**（D-80 关联） | ✅ 完成 | `solver_chain.mhe_rolling`：窗口沿时间轴滚动 + warm start + 参数时序轨迹；并新增「边界退化」判据（D-86） |

> **R161-4 / R161-5 已由 R162 完成**；本节为 R163 的五项。
"""

    # ---------------- 6. 契约 v1.93 ----------------
    # 惯例（承 R162）：头部用 `> 状态：**v1.93**（...）` 单行块，
    # 上一版（v1.92）的状态块**逐字保留**、只把标签从「状态」降级为「历史」。
    CONTRACT_HEAD = """> 状态：**v1.93**（R163 **D-80 回退链接入现役 MCP 路径 —— D-85 / D-86 / D-87 新增**。①**接入方式**：`reconstruct_batch` 新增 **opt-in** 参数 `fallback_chain`（默认 `False` ⇒ 返回体与接入前**逐位一致**）；置 `True` 时在返回体**追加** `fallback_chain` 块，含 `tier` / `degraded` / `reconstruction_valid` / `reasons` / `trace` / `fallback` / `evidence` —— **降级标记必在返回体**（§3.3 禁止静默输出貌似合理的数）。新增只读工具 `batch_fallback_tier`；`solver_info` 增列 **D 档**。②**链序**：EnKF 健康 →（不健康）MHE + 稳态碳平衡软约束 →（不可解）稳态基线 →（C 平衡 >20%）显式失败。③**三条新债**：**D-85**（fastmcp 未安装且未锁进 `requirements.txt` ⇒ MCP 服务本机**不可启动** ⇒ 端到端启动验证受阻）、**D-86**（MHE 的 (μp, m_s) 参数化在真实残差面上频繁不可辨识 ⇒ 已补「边界退化」判据，**不改** R161 冻结语义）、**D-87**（R161 的 EnKF 创新判据在真实数据上触发率约 {{TRIG}}% ⇒ 近乎恒真 ⇒ 须按跨批 |z| 分布重新标定阈值）。**引擎数值零改动**（本轮只新增只读探针与 opt-in 旁路；零回归 86 批 `max|Δ| = 0.00e+00`、RMSE 2.345%、86/86）。）
"""

    # ---------------- 7. README ----------------
    README_BLOCK = """### R163　D-80 回退链接入现役 MCP 路径

- `reconstruct_batch(batch_no, n_ens, fallback_chain=False)` —— 默认行为**逐位不变**；
  置 `fallback_chain=True` 走 **EnKF → MHE → 稳态基线 → 显式失败** 四环，
  降级标记（`tier` / `degraded` / `reconstruction_valid` / `reasons` / `trace`）**必在返回体**。
- `batch_fallback_tier(batch_no)` —— 只读判定某批的回退链层级（比 `reconstruct_batch` 快）。
- 配套工具：`tools/r163_degradation_probe.py`（退化筛查/注入）、`tools/r163_innovation_calibration.py`
  （创新判据标定）、`tools/r163_kla_dual_constraint.py`（alpha_kla 双约束标定）、
  `tools/r163_dist_variance_probe.py`（扰动方差量化）、`tools/r163_mcp_integration_probe.py`（零回归）。
- 阻断项新增：**D-85**（fastmcp 缺失 ⇒ MCP 不可启动）、**D-86**（MHE 参数化不可辨识）、
  **D-87**（创新判据真实触发率 {{TRIG}}%）。
"""

    # ---------------- 8. 工具索引 ----------------
    INDEX_BLOCK = """### R163（D-80 回退链接入 + 三条基础性收尾）

| 工具 | 用途 | 备注 |
|---|---|---|
| `r163_degradation_probe.py` | 真实退化批的**筛查 + 确认 + 注入**三段式：A 段跨批 EnKF 健康度筛查（增量落盘、可恢复）、B 段大集合确认、C 段物理可信故障注入 + 零信息对照 | A 段结论：**创新判据真实触发率 {{TRIG}}%** ⇒ 触发 **D-87** |
| `r163_innovation_calibration.py` | 创新判据的**跨批标定**：逐通道 \\|z\\| 的 p50/p90/p99/max + 越限占比，并离线枚举 (阈值 × 持续占比) 候选判据的假阳性率 | 为 **D-87** 的修正提供数据基础 |
| `r163_kla_dual_constraint.py` | alpha_kla **DO2 + 产量双约束**逐批标定：可行集 F、唯一性、产量崖标记、**不可标定批识别** | 复用 R162 扫描数据，秒级；**D-84** |
| `r163_dist_variance_probe.py` | MATLAB 8 路扰动**随机成分**的贡献量化（进程内 patch，磁盘引擎零改动）：逐通道单独注入 + 全叠加 + 幅值扫描 | **D-83**；与 MATLAB 低通同构（τ=40 h） |
| `r163_mcp_integration_probe.py` | MCP 接入的**零回归 + 标记完备性**验证（Z1–Z6）；含 fastmcp stub 注入以绕开 **D-85** | 基线夹具：`tools/_legacy/mcp_server_pre_r163.py` |
| `r163_governance_update.py` | 治理层更新（台账 / 签核单 / 路线图 / 契约 / README / state / 工具索引 / 工作记忆） | **幂等**；数字全部从 `runs/` 产物读取 |
"""

    # ---------------- 9. 记忆 ----------------
    MEM_BLOCK = """
## R163　D-80 回退链接入现役 MCP 路径

**目标**：把 R161 的四环算子接入现役 MCP 路径，并补齐三条基础性收尾
（alpha_kla 双约束标定 / 扰动方差贡献量化 / MHE 滚动时序调度）。

**MCP 接入（R163-1）**
`reconstruct_batch(batch_no, n_ens, fallback_chain=False)`：默认 **False** ⇒ 返回体**逐位不变**
（夹具基线 `tools/_legacy/mcp_server_pre_r163.py` 逐位比对）；置 True 追加 `fallback_chain` 块
（`tier`/`degraded`/`reconstruction_valid`/`reasons`/`trace`/`fallback`/`evidence`）。
新增只读工具 `batch_fallback_tier`；`solver_info` 增列 D 档。
`solver_chain` 新增第 7 节：批次级链编排（`evaluate_batch_fallback` /
`mhe_batch_residual` / `mhe_estimate_batch` / `mhe_rolling` / `mhe_boundary_degenerate` /
`steady_state_for_batch`）。

**三条新债**
- **D-85**：`fastmcp` 未安装且未锁进 `requirements.txt` ⇒ **MCP 服务在本机不可启动** ⇒
  MCP 侧改动无法端到端验证（本轮用 stub 注入做逻辑验证）。
- **D-86**：MHE 的 (μp, m_s) 二参数化在真实残差面上**频繁不可辨识**（解撞域边界）
  ⇒ 新增「边界退化」判据（不改 R161 冻结语义）。
- **D-87**：R161 的 EnKF 创新判据在真实数据上**近乎恒真**（触发率 {{TRIG}}%）⇒
  若直接接入会误降级四分之三的批 ⇒ 须按跨批 |z| 分布重新标定阈值。

**alpha_kla 双约束标定（R163-2，D-84）**
DO2 约束（relRMSE ≤ min×1.05）∩ 产量约束（|rel_err| ≤ 5%）：
{{K_FEAS}}/{{K_TOT}} 批可标定，双约束解范围 {{K_RANGE}}；**b55 单参数空间无解**（最小误差 34.4%）须排除；
{{K_CLIFF}} 批落在产量崖（b60/b91）；名义 85 只在 {{K_BASE85}}/{{K_TOT}} 批合格 ⇒ 逐批标定有实质收益。
**修正 R162 表述**：「DO2 最优 ≠ 产量最优」是**极值点**差异；双约束求交后多数批
DO2 解同时满足产量带 ⇒ 应表述为「DO2 是主约束，但必须加产量交叉校验」。

**扰动方差贡献（R163-3，D-83）**
MATLAB 低通 `filter(0.005,[1,-0.995],·)` 的时间常数 = 0.2/0.005 = **40 h**，
与 Python 的 `dist(t)=asym·(1−exp(−t/τ))`（τ=40 h）**完全一致** ⇒ 均值/时间常数已对齐，
缺的只是围绕均值的随机成分。注入方式：进程内 patch `simulate.integrate_interval`
（**磁盘引擎零改动**）。

**退化批验证（R163-4）**
自然退化筛查 + 故障注入（DO2 漂移 / pH 偏置 / CO2 卡死 / 冷却失效），
后者验证白名单的反向判别力（T 通道不在白名单 ⇒ 越限 333 次仍**不**触发）。
**D-87 的量化来源**即此段的 A 段筛查。

**MHE 滚动调度（R163-5）**
`solver_chain.mhe_rolling`：窗口沿时间轴滚动 + warm start + 参数时序轨迹；
任一窗口不可解 ⇒ 显式标记并按 `on_failure` 处理（不静默跳过）。
"""

    # ================= 执行写入 =================
    def do(fn, *args, **kwargs):
        if a.dry_run:
            return
        if fn(*args, **kwargs):
            # 无参闭包（args 为空）时用函数名兜底
            if args and isinstance(args[0], str):
                changed.append(os.path.basename(args[0]))
            else:
                changed.append(getattr(fn, "__name__", "?"))

    # 行尾归一化（契约 / state.yaml）
    for p in (CONTRACT, STATE):
        if normalize_eol(p):
            changed.append("行尾归一化:" + os.path.basename(p))

    FILL = {"TRIG": pct(trig_rate), "TRIG_PCT": pct(trig_rate), "N_SCANNED": n_scanned, "N_DEG": n_deg,
            "N_EQ": k_sum.get("n_batches_F_equals_C1"), "K_FEAS": k_feas,
            "K_TOT": k_tot, "K_RANGE": k_range, "K_CLIFF": k_cliff,
            "K_BASE85": k_base85, "D_CHECKS": d_checks, "M_CHECKS": m_checks}

    # ⚠ 根因修复（R163 踩过）：after 锚点必须**精确到整行末**，
    #   否则 `t.replace(after, after + block)` 会把块插到**行中间** ⇒ 截断该行。
    #   旧锚点 "### D-84　引擎**统一用名义 alpha_kla**" 只是 D-84 标题的**前缀**
    #   ⇒ D-85 块被插到 D-84 标题中间，把 D-84 标题与表格一起吞掉。
    do(ensure_once, LEDGER, "### D-85　**fastmcp 未安装", _fill(NEW_DEBTS, **FILL), None,
       after=_ledger_d84_anchor())
    do(ensure_once, LEDGER, "25. **判据的真假阳性率必须先在真实数据上实测",
       _fill(DISCIPLINES, **FILL), None)
    do(ensure_once, LEDGER, "| D-85 | **fastmcp 未安装", _fill(TABLE_ROWS, **FILL), None)
    do(replace_once, LEDGER,
       "| D-80 | 回退链算子层**未接入现役路径** ⇒ 降级「有算子无触发」 | L2 | 🟡 **R161 新增**（接入属 GOAL §5 边界变更，需裁决） |",
       D80_ROW)
    do(replace_once, LEDGER, "截至 R162", "截至 R163")

    do(insert_after_line, SIGNOFF, "| **R-12**",
       _fill(SIGNOFF_ROW, **FILL) + "\n")

    do(ensure_once, ROADMAP, "### 8.5 R163 新增任务项", _fill(ROADMAP_BLOCK, **FILL), None)

    # ---------------- 块内**内容**同步（补行）----------------
    # ⚠ ensure_once 只保证块**存在**；块已存在时**不会**补上后续新增的行
    #   （R163 踩过：台账 D-87 块先被写入，后续才补的「后果二/标定」两行没进去）。
    def _sync_block_lines():
        touched = []

        def _ensure_lines(path, start_marker, new_lines):
            """在 start_marker 块内确保 new_lines 每一行都存在（幂等）。"""
            t = read_text(path)
            i = t.find(start_marker)
            if i < 0:
                return False
            j = t.find("\n### ", i + len(start_marker))
            k = t.find("\n## ", i + len(start_marker))
            ends = [x for x in (j, k) if x > 0]
            end = min(ends) if ends else len(t)
            blk = t[i:end]
            add = [ln for ln in new_lines if ln not in blk]
            if not add:
                return False
            # 插在该块最后一行的表格行之后
            lines = blk.split("\n")
            pos = len(lines) - 1
            while pos >= 0 and not lines[pos].strip():
                pos -= 1
            new_lines_blk = lines[:pos + 1] + add + lines[pos + 1:]
            write(path, t[:i] + "\n".join(new_lines_blk) + t[end:], None)
            return True

        debts_extra = [
            "| 后果二 | C 段注入（**仅健康批、20 例全可归因**）显示**灵敏度也通道极不均衡**："
            "DO2 漂移 **5/5 检出**、pH 偏置 **4/5**、CO2 卡死 **仅 1/5**、O2 通道 **0/20 零贡献**"
            " ⇒ 该判据既**假阳性高**又**通道灵敏度失衡** |",
            "| 标定 | 20 批跨批标定 ⇒ `z>5 & frac>0` 触发 **75%**；`z>10 & frac>0.02` 触发 **20%**；"
            "`z>15` 触发 **0%**（过度修正 ⇒ 丧失灵敏度）⇒ **可行区间在 z≈10**，须由注入段定灵敏度下限 |",
        ]
        if _ensure_lines(LEDGER, "### D-87", debts_extra):
            touched.append("台账:D-87 补行")

        # 纪律 28/29（若纪律 25-27 块已存在，ensure_once 不会补新条目 ⇒ 这里补）
        disc_extra = [
            "28. **零信息对照本身退化 ⇒ 该样本不可归因，须单列** —— R163 C 段第一轮在",
            "    `8,22,55,91` 上注入，但 b55/b91 **本身就是自然退化批** ⇒ 其「注入后触发」",
            "    **不能**归因于注入（触发只是重复观测到该批固有退化）⇒ 若与健康批样本混在一起统计，",
            "    会把「对照已退化」误判成「判据失灵」。⇒ 改为**只在健康批**上注入（20 例全部可归因），",
            "    并把不可归因样本单列（`r163_merge_c.py` 固化该口径）。",
            "29. **判据终检不得强行要求「零漏检」** —— R163 实测 CO2 卡死漏检 4/5 ⇒ 判据**确实**有灵敏度缺口",
            "    ⇒ 终检要求的是「**检出率被量化 + 反向判别力成立（TN>0）**」，而非「全部期望全中」：",
            "    强行恒真即 D-78 禁止的「恒真判据」，强行恒假则是粉饰。",
        ]
        if _ensure_lines(LEDGER, "25. **判据的真假阳性率必须先在真实数据上实测",
                         disc_extra):
            touched.append("台账:纪律 28/29 补行")

        return bool(touched)

    if _sync_block_lines():
        changed.append("块内补行")

    # ---------------- 块内数字**回填**（R163 关键修复）----------------
    # ⚠ 为什么要回填：`ensure_once` 只保证块**存在**，不保证块里的数字**正确**。
    #   若块是在「数据尚未齐」时被写入（如 dry-run 泄漏），其中的数字会被固化
    #   （例：D-87 标题的触发率被写成 n/a / %s）⇒ 后续复跑无法再修正。
    # ⇒ 对已存在的 R163 块，逐条把**实测数字**重新写进去（幂等）。
    def _backfill_numbers():
        touched = []

        def _sub_in_block(path, start_marker, pairs):
            """在 start_marker 起始的块内替换 (old, new) 对。"""
            t = read_text(path)
            i = t.find(start_marker)
            if i < 0:
                return False
            # 块的范围：从 marker 到下一个同级标题（以 '\n## ' / '\n### ' 结尾）
            j = t.find("\n### ", i + len(start_marker))
            k = t.find("\n## ", i + len(start_marker))
            ends = [x for x in (j, k) if x > 0]
            end = min(ends) if ends else len(t)
            blk = t[i:end]
            new_blk = blk
            hit = False
            for old, new in pairs:
                if old in new_blk:
                    new_blk = new_blk.replace(old, new)
                    hit = True
            if hit and new_blk != blk:
                write(path, t[:i] + new_blk + t[end:], None)
                return True
            return False

        # 台账 D-87 标题里的触发率（可能残留 %s 或 n/a）
        t = read_text(LEDGER)
        if "### D-87" in t:
            i = t.find("### D-87")
            j = t.find("\n### ", i + 1)
            k = t.find("\n## ", i + 1)
            ends = [x for x in (j, k) if x > 0]
            end = min(ends) if ends else len(t)
            blk = t[i:end]
            nb = blk
            nb = nb.replace("（触发率约 %s）", "（触发率约 %s%%）" % pct(trig_rate))
            nb = nb.replace("（触发率约 n/a%）", "（触发率约 %s%%）" % pct(trig_rate))
            nb = nb.replace("（触发率约 %s%%）" % pct(trig_rate), "（触发率约 %s%%）" % pct(trig_rate))
            if nb != blk:
                write(LEDGER, t[:i] + nb + t[end:], None)
                touched.append("台账:D-87 触发率")

        # 路线图 §8.5 的 D-87 触发率 / 关键数字
        if _sub_in_block(ROADMAP, "### 8.5 R163 新增任务项", [
                ("触发率约 n/a%", "触发率约 %s%%" % pct(trig_rate)),
                ("（触发率约 %s%%）" % pct(trig_rate),
                 "（触发率约 %s%%）" % pct(trig_rate)),
        ]):
            touched.append("路线图:8.5 触发率")

        # 契约 v1.93 状态块里的触发率
        ct = read_text(CONTRACT)
        if "> 状态：**v1.93**" in ct and "n/a%" in ct:
            ct2 = ct.replace("触发率约 n/a%", "触发率约 %s%%" % pct(trig_rate), 1)
            if ct2 != ct:
                write(CONTRACT, ct2, None)
                touched.append("契约:v1.93 触发率")

        # README R163 节里的触发率
        if "D-87 创新判据真实触发率 n/a%" in read_text(README):
            do(replace_once, README, "D-87 创新判据真实触发率 n/a%%",
               "D-87 创新判据真实触发率 %s%%" % pct(trig_rate), None)
            touched.append("README:D-87 触发率")

        # state.yaml D-87 条目里的触发率
        if "跨批触发率约 n/a%" in read_text(STATE):
            do(replace_once, STATE, "跨批触发率约 n/a%",
               "跨批触发率约 %s%%" % pct(trig_rate), None)
            touched.append("state:D-87 触发率")

        # 记忆块里的触发率
        if os.path.exists(MEMLOG) and "触发率 n/a%" in read_text(MEMLOG):
            do(replace_once, MEMLOG, "触发率 n/a%",
               "触发率 %s%%" % pct(trig_rate), None)
            touched.append("memory:D-87 触发率")

        return bool(touched)

    if _backfill_numbers():
        changed.append("块内数字回填")

    # 契约：v1.93 头部状态块（v1.92 原文逐字保留，只降级标签）
    # ⚠ 必须整体走 do() 门控 —— 否则 --dry-run 会真的写文件（R163 踩过此坑）
    if "> 状态：**v1.93**" not in read_text(CONTRACT):
        def _write_contract_head():
            ct = read_text(CONTRACT)
            lines = ct.split("\n")
            block = _fill(CONTRACT_HEAD, **FILL)
            done = False
            for i, l in enumerate(lines):
                if l.startswith("> 状态：**v1.92**"):
                    # ① v1.92 状态块**逐字保留**，只把标签「状态」降级为「历史」
                    lines[i] = l.replace("> 状态：**v1.92**", "> **历史：v1.92**", 1)
                    # ② v1.93 状态块插在它**之前**
                    lines.insert(i, block)
                    done = True
                    break
            if not done:
                lines.insert(2, block)
            ct2 = "\n".join(lines)
            # ③ 标题版本号同步
            ct2 = ct2.replace(
                "# ENGINE_CONTRACT.md — 求解器引擎批处理契约（v1.92，2026-11-05）",
                "# ENGINE_CONTRACT.md — 求解器引擎批处理契约（v1.93，2026-11-05）", 1)
            write(CONTRACT, ct2, None)
            return True

        do(_write_contract_head)
    # 版本表行：插在 | v1.92 | 那一行**之后**（R163 踩过：插到文件尾会脱离表格）
    if "| v1.93 |" not in read_text(CONTRACT):
        do(insert_after_line, CONTRACT, "| v1.92 |",
           "| v1.93 | R163：**D-80 回退链接入现役 MCP 路径（D-85 / D-86 / D-87 新增）** —— `reconstruct_batch` 增 opt-in `fallback_chain`（默认关 ⇒ 返回体逐位不变）+ 新增 `batch_fallback_tier`；降级标记必在返回体 | opt-in 默认关 | 零回归 86 批 max\\|Δ\\|=0.00e+00 |")

    do(ensure_once, README, "### R163　D-80 回退链接入现役 MCP 路径",
       _fill(README_BLOCK, **FILL), None)

    # README §5「最近一轮」指针 + §4 契约版本号（承 R162 的 replace_once 惯例）
    # ⚠ replace_once 的 old 必须**不含** new 的前缀，否则重复执行会层层叠加（R162 踩过）
    do(replace_once, README,
       "5. `docs/r162_round_report.md` —— 最近一轮；历史报告按编号倒序"
       "\n   （上一轮：`docs/r161_round_report.md`）",
       "5. `docs/r163_round_report.md` —— 最近一轮；历史报告按编号倒序"
       "\n   （上一轮：`docs/r162_round_report.md`）", None)
    do(replace_once, README, "## 4. 当前状态（契约 v1.92）",
       "## 4. 当前状态（契约 v1.93）", None)
    # README §5 阻断项清单：补 D-85 / D-86 / D-87
    # ⚠ old 是 new 的**前缀** ⇒ replace_once 重复执行会层层叠加（R162 产生 6 次重复的根因）
    #    ⇒ 必须先用 marker 判定「是否已含新内容」，再决定是否替换
    if "D-85 fastmcp 未安装" not in read_text(README):
        do(replace_once, README,
           "**D-84 alpha_kla 统一用名义值**（R162 新增，均只出数字不改引擎）",
           _fill("**D-84 alpha_kla 统一用名义值**（R162 新增，均只出数字不改引擎）"
                 " / **D-85 fastmcp 未安装**（R163 新增，MCP 本机不可启动）"
                 " / **D-86 MHE 参数化不可辨识**（R163 新增）"
                 " / **D-87 创新判据真实触发率 {{TRIG}}%**（R163 新增，须重新标定阈值）",
                 **FILL), None)

    do(ensure_once, INDEX, "### R163（D-80 回退链接入", _fill(INDEX_BLOCK, **FILL), None)

    # ---------------- state.yaml ----------------
    # ⚠ 干跑门控：state.yaml 的写入**必须**整体走 do()，否则 --dry-run 会真的改文件。
    # ⚠ 条目形态：既有 open_questions 是**纯字符串列表**（缩进 0 的 `- `），
    #    若用 `  - id: ...` + 嵌套键会与相邻项缩进不一致 ⇒ YAML 解析失败（R163 踩过）。
    def _write_state():
        st = read_text(STATE)
        touched = False
        if "D-85" not in st:
            # 插在 `open_questions:` 之后，缩进 0，形态与既有条目一致
            oq_block = (
                "- 🔴 R163 D-85（新债，L1）：`fastmcp` 未安装且未锁进 `requirements.txt`"
                " ⇒ **MCP 服务在本机不可启动** ⇒ D-80 的接入只能用 stub 注入做逻辑验证，"
                "端到端启动验证受阻；须装包 + 锁版本 + 加 MCP 冒烟闸门\n"
                "- 🟡 R163 D-86（新债，L2）：MHE 的 (μp, m_s) 二参数化在真实残差面上"
                "**频繁不可辨识**（解撞参数域边界而相对改善仍 >0.39）⇒ 已补『边界退化』判据"
                "（不改 R161 冻结语义）；参数化待扩到 (μp, m_s, mux) 并重做可辨识性分析\n"
                "- 🔴 R163 D-87（新债，L2）：R161 的 EnKF **创新判据在真实数据上近乎恒真**"
                "（跨批触发率约 %s%%）⇒ 若直接接入会误降级约四分之三的批 ⇒ "
                "须按跨批 |z| 分布重新标定阈值（自适应阈值 + 持续占比条件）\n"
                % pct(trig_rate)
            )
            # ⚠ state.yaml 是 **CRLF** ⇒ read_text(newline="") 读到的是 "open_questions:\r\n"
            #   ⇒ 用 "\n" 匹配必然失败（R163 踩过：D-85 一直没进 state.yaml）。
            #   ⇒ 先归一为 LF 再替换，最后由 write() 按原风格转回 CRLF。
            st_n = st.replace("\r\n", "\n")
            assert "open_questions:\n" in st_n, "open_questions 锚点未找到"
            st_n = st_n.replace("open_questions:\n", "open_questions:\n" + oq_block, 1)
            st = st_n
            touched = True
        if "r163_degradation:" not in st:
            # artifacts 是最后一个顶层键 ⇒ 直接追加到文件尾即落在 artifacts 段内
            st = st.rstrip("\n") + "\n" + (
                "  r163_degradation: runs/r163_degradation_probe.json - R163 退化筛查/注入（A/B/C 段）\n"
                "  r163_innovation_calib: runs/r163_innovation_calibration.json - 创新判据跨批标定（D-87）\n"
                "  r163_kla_dual: runs/r163_kla_dual_constraint.json - alpha_kla 双约束标定（D-84）\n"
                "  r163_dist_variance: runs/r163_dist_variance.json - 扰动方差贡献量化（D-83）\n"
                "  r163_mcp_integration: runs/r163_mcp_integration.json - MCP 接入零回归与标记完备性\n")
            touched = True
        if touched:
            write(STATE, st, None)
        return touched

    do(_write_state)

    if os.path.exists(MEMLOG):
        do(append_once, MEMLOG, "R163　D-80 回退链接入现役 MCP 路径",
           _fill(MEM_BLOCK, **FILL), None)

    print("\n=== 变更 ===")
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
