# -*- coding: utf-8 -*-
"""R159：把「A2 结论撤回 + 化验退化区登记」写进台账 / 签核单 / 契约 / state.yaml。

口径
----
- `state.yaml` 与 `ENGINE_CONTRACT.md` 均为**纯 CRLF** ⇒ 全部读写按 CRLF 处理。
- **行级定位**（不靠字符串偏移）。
- **幂等**：锚点已存在则 `[skip]`。
- `state.yaml` 的 `open_questions` 元素是 plain scalar ⇒ **不得以 `*` 开头**
  （YAML 会当别名锚点），且不得含会破坏结构的字符。
- 契约版本表是 **3 列** ⇒ 行内竖线数必须**恰好 3**。
- markdown 表格行内**不得含裸竖线**。

用法
----
    py tools/r159_governance_update.py
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

FORBIDDEN_STATE = ["*", "[", "]", "{", "}", ",", ": ", "#"]


# ---------------------------------------------------------------- 工具
def _read_crlf(path):
    """**必须二进制读取**：文本模式的 universal newlines 会把 \\r\\n 转成 \\n。

    换行风格按文件实际：docs/*.md 是 **LF**，state.yaml / ENGINE_CONTRACT.md 是 **CRLF**。
    ⇒ 读时按实际风格切分，写时**原样保持**，不跨风格改写整个文件。
    """
    raw = open(path, "rb").read()
    if b"\r\n" in raw:
        assert b"\n" not in raw.replace(b"\r\n", b""), "%s 混有 lone LF" % path
        return raw.decode("utf-8").split("\r\n"), raw, "\r\n"
    assert b"\r" not in raw, "%s 混有 lone CR" % path
    return raw.decode("utf-8").split("\n"), raw, "\n"


def _write_crlf(path, lines, raw_before, nl="\r\n"):
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
    """plain scalar 安全字符检查（**仅用于 open_questions 元素**）。

    `artifacts` 是 **key: value 映射**（如 `golden_set: data/...`），
    其值里出现 `: ` 是合法的（YAML 只在 flow 上下文才有歧义）⇒ 不走本检查。
    """
    for ch in FORBIDDEN_STATE:
        if ch in text:
            raise SystemExit("[fail] state.yaml 元素含危险字符 %r: %s" % (ch, text[:90]))


def _check_artifacts_value(text):
    """artifacts 的 value 检查：不得含 `#` 注释分隔符后的歧义、不得以 `*` 开头。

    允许 `key: value` 形态（`: ` 是映射语法，不是 plain scalar 风险）。
    """
    body = text.split(":", 1)[1] if ":" in text else text
    if body.lstrip().startswith("*"):
        raise SystemExit("[fail] artifacts 值以 * 开头（YAML 别名锚点）: %s" % text[:90])
    if "#" in body:
        raise SystemExit("[fail] artifacts 值含 # （会被当作注释截断）: %s" % text[:90])


def _check_no_pipe(text, where):
    """markdown 表格行内不得含裸竖线（除首尾的分隔竖线外）。"""
    body = text.strip()
    assert body.startswith("|") and body.endswith("|"), "%s 表格行未以 | 包裹" % where
    if body.count("|") != 3:
        raise SystemExit("[fail] %s 表格行竖线数 = %d（应为 3）" % (where, body.count("|")))


# ---------------------------------------------------------------- 台账
D73 = """### D-73　V6 数据集批 61–90 的 `PAA_offline` 是**占位值**（化验信号退化）　🔴 **R159 新增，L2（数据）**

| 项 | 内容 |
|---|---|
| 现象 | `data/processed/batches/batch_61..90.csv` 的 `PAA_offline` 列（`time_h > 20`）被**钉在 ~1200 mg/L**：均值 **1198.6–1205.0 mg/L**、CV **0.13%–1.85%**、动态范围仅 **6.7–102.4 mg/L**。而批 1–60 的同一列是正常动态（CV 中位 **43.8%**、动态范围 **3166.6 mg/L**） |
| 全量普查 | 对 `data/processed/batches/` **全部 100 个 CSV** 扫 `PAA_offline` ⇒ 退化批共 **30 批**（61–90，b81 无 `GOLDEN_ALL` 缓存 ⇒ 池内 **29 批**） |
| 为何此前未被发现 | R158 §4.3 写过「**不在批 80 退化化验上做单点合格**」——**单批退化当时已被察觉**，但**未推广到全池**，也**未在统计口径上排除** ⇒ 退化批混在全池统计里，把「化验恒定」的子集当成了「引擎失真」的样本 |
| 后果 | 任何以化验 PAA 为真值/分母的统计，在退化批上会让**任何**预测器（含「输出一个常数」）的误差趋近 0 ⇒ ① R158 的「A2 两点校准中位 0.49%、严格支配 PAT」结论**被这 29 批污染**（详见 D-74）；② 失真批（`A_engine_r ≤ 0.5`）分层里 **29/41 是退化批** ⇒ 该分层实际是「化验恒定」与「引擎失真」的混合体 |
| 修法 | ① 任何以化验/真值为对照的统计，**先做信号退化筛查**（CV / 动态范围）再分层；② 本项目已落地判据：`lab_cv_pct < 2%` ⇒ 判为退化批（`tools/r159_a2_falsification.py` 内建）；③ **不改数据文件**（占位值是 V6 数据集的事实，属外部数据问题）⇒ 长期登记项 |
| 纪律延伸 | **统计口径必须先验证真值本身有动态信息** —— 否则结论会落在「真值恒定」的子集上，而这类子集让**任何**预测器的误差都趋近 0 ⇒ 结论**必然**平凡满足，且**模型排名被真值退化翻转**（本轮：一个「预测常数」的基线拿到 0.30%，比最好的模型还好） |

### D-74　R158 的「A2 两点校准**严格支配**」结论**撤回**　🔴 **R159 新增，L2（结论）**

| 项 | 内容 |
|---|---|
| 被撤回的结论 | R158 §3.2 / §4.2：「失真批上 A2（引擎 PAA + 两点仿射校准）nRMSE 中位仅 **0.49%**，远优于 PAT 转发 31.90% 与 PAT+锚定 11.23% ⇒ 失真批的『引擎 PAA 失真』本质是**两点可校准的偏置/斜率差** ⇒ **处理失真批应优先做两点校准，而非引入 Raman 资产**」 |
| 五道证伪门 | `tools/r159_a2_falsification.py`，86 批（`GOLDEN_ALL`，与 R158 同口径，复算关键量**逐位一致**）⇒ **四门触发 + 一门结构性触发**：**G1** 化验退化（失真批化验 CV 中位 **0.4568%** vs 可信批 **56.6742%**，比值 0.0081）、**G2** 常数基线（失真批 A2 **0.4920%** vs 常数基线 **0.4854%**，符号检验 **37/41 批 A2 更差**，p=1.03e−07）、**G3** 斜率退化（A2 拟合斜率中位 **0.0010** ≈ 0、预测动态范围 **0.0720%**）、**G4** 时间泄漏（前推式下 A2 **0.6461%** vs 前推常数 **0.6147%**）、**G5** 分组标签在线不可得 |
| 有效口径重判 | 剔除 29 批退化批（CV < 2%）后：**有信息批 n=57** 上 A2 中位 **20.47%** **劣于** C0（逐点比例锚定）中位 **10.29%**（符号检验 **50/57 更差**，p=4.24e−09）⇒ **方向反转**；**真·失真批**（有信息且 `A_engine_r ≤ 0.5`，n=12）上 A2 **30.48%** 甚至**劣于常数基线 28.64%** |
| 判决 | **A2_RETRACTED** —— R158 的「A2 严格支配」**不成立**；「处理失真批应优先做两点校准」这条**操作建议撤回** |
| **主判决不受影响（反而加固）** | D-71（PAT 无独立信息）维持并**加固**：剔除退化批后增量 R² 中位 **0.0199 → 0.0092**、t 值中位 **0.104 → 0.036**、`pat_vs_engine_r` **0.9796 → 0.9843**；D-72（锚定方向错误）与 D-70（PLS 量纲）与化验退化正交，**维持** |
| 修正后的表述 | 「**而非引入 Raman 资产**」成立（PAT 仍无独立信息，不引入的决定不变）；「**优先做两点校准**」不成立 —— 失真批 PAA 估值问题**目前没有已验证的简单解**；C0（锚在引擎 PAA 上的逐点比例锚定）在有信息批上中位 **10.29%** 是当前最好候选，但**仍需化验锚点**（只适用于有离线化验的批次）且**尚无在线可得的失真判别器** ⇒ 属 **V1+ 候选**，不是可交付组件 |
| 纪律延伸 | **正面结论与否定结论享有同等的被证伪义务** —— 不得因为正面结论「更可用」而给予更宽松的复核标准（R158 给出正面结论、R159 推翻它，**这本身不是 R158 的错误，而是流程奏效**） |

"""

LEDGER_ANCHOR = "### D-70　PLS 资产"


def update_ledger():
    lines, raw, nl = _read_crlf(LEDGER)
    n0, n1 = raw.count(b"\r\n"), None
    if "### D-73" in "\n".join(lines) and "### D-74" in "\n".join(lines):
        print("[skip] 台账已有 D-73 / D-74")
        return
    idx = None
    for i, l in enumerate(lines):
        if l.startswith(LEDGER_ANCHOR):
            idx = i
    if idx is None:
        raise SystemExit("[fail] 台账未找到 D-70 锚点")
    block = D73.rstrip("\n").split("\n")
    # 插入到 D-70 之前（保持编号升序）
    lines[idx:idx] = block
    # 修订 D-71 的「关键否证」行（撤回 A2 支配的表述；幂等：命中才改）
    _d71_done = False
    for i, l in enumerate(lines):
        if l.startswith("| **关键否证（已被 D-74 撤回）** |"):
            print("[skip] D-71 关键否证行已修订")
            _d71_done = True
            break
        if l.startswith("| **关键否证** |"):
            lines[i] = ("| **关键否证（已被 D-74 撤回）** | "
                        "R158 曾记「失真批上两点校准的引擎 PAA（A2）nRMSE 中位仅 0.49% ⇒ "
                        "失真批本质是两点可校准的偏置差 ⇒ PAT 不是最优解」—— "
                        "**R159 证伪**：该分层 41 批中 **29 批化验值退化**（D-73），"
                        "A2 在其上退化为常数预测（斜率中位 0.0010）且**连常数基线都打不过**；"
                        "剔除后 A2 劣于 C0 ⇒ **本行结论撤回** |")
            print("[ok] 修订 D-71 的关键否证行")
            _d71_done = True
            break
    if not _d71_done:
        print("[skip] 未找到 D-71 的关键否证行")
    # 汇总表追加两行
    for i, l in enumerate(lines):
        if l.startswith("| D-72 |"):
            lines.insert(i + 1,
                         "| D-73 | V6 批 61–90 的 `PAA_offline` 是占位值（化验信号退化） | L2 | 🔴 **R159 新增**（数据；统计前须做退化筛查） |")
            lines.insert(i + 2,
                         "| D-74 | R158 的「A2 两点校准严格支配」结论**撤回** | L2 | 🔴 **R159 新增**（五道证伪门 4 门触发 + 剔除退化批后方向反转） |")
            print("[ok] 台账汇总表追加 D-73 / D-74")
            break
    n0, n1 = _write_crlf(LEDGER, lines, raw, nl)
    print("[ok] 台账更新（CRLF %d → %d）" % (n0, n1))


# ---------------------------------------------------------------- 签核单
SIGNOFF_ROWS = """| **B-13** | **V6 批 61–90 的 `PAA_offline` 是占位值（化验信号退化）** | 该区间化验 PAA 被钉在 ~1200 mg/L：均值 **1198.6–1205.0 mg/L**、CV **0.13%–1.85%**、动态范围仅 **6.7–102.4 mg/L**；批 1–60 则为正常动态（CV 中位 **43.8%**、动态范围 **3166.6 mg/L**）。全 100 CSV 普查 ⇒ 退化 **30 批**（池内 29 批） | **R159 退化筛查（R159，`runs/r159_a2_falsification.json`）**；D-73 | **任何以化验/真值为对照的统计必须先做信号退化筛查**（本项目判据：`lab_cv_pct < 2%`）。**不得**在未筛查的批次上汇报 PAA 相关指标 |
| **B-14** | **R158 的「A2 两点校准严格支配」结论已撤回** | 五道证伪门**四门触发**：化验退化（CV 比值 0.0081）、常数基线同量级（37/41 更差，p=1.03e−07）、斜率退化为 0（0.0010）、前推式下优势消失。剔除 29 批退化批后 A2 **20.47%** **劣于** C0 **10.29%**（50/57，p=4.24e−09）；真·失真批（n=12）上 A2 **30.48%** 劣于常数基线 **28.64%** | **R159 证伪位检验（R159）**；D-74 | **「处理失真批应优先做两点校准」撤回**。失真批 PAA 估值**目前没有已验证的简单解**；C0（锚在引擎 PAA 上的逐点比例锚定，有信息批中位 **10.29%**）是当前最好候选，但**需化验锚点 + 无在线可得判别器** ⇒ V1+ 候选，非可交付组件。**D-71 / D-72 / D-70 维持**（且 D-71 被加固：增量 R² 0.0199→**0.0092**、t 0.104→**0.036**） |
"""

SIGNOFF_BANNED = """| "处理失真批应优先做两点校准" | 那是 **R158 的结论，已被 R159 证伪撤回**：A2 的 0.49% 来自 **29 批化验退化**（真值恒定 ⇒ 任何预测器误差趋 0），**连常数基线都打不过**（37/41，p=1.03e−07）；剔除后 A2 **20.47%** 劣于 C0 **10.29%** ⇒ 失真批 PAA 估值**目前没有已验证的简单解**（**B-14**） |
| "失真批上 PAT 转发优于引擎直报 38/41、p=1.05e-08" | 那是 R158 的**原口径**结论，其分层（n=41）里 **29 批化验退化**；剔除后真·失真批（n=12）上仅 **2/12、p=0.0386** ⇒ **显著削弱**，不得单独引用（**B-13 / B-14**） |
"""

SIGNOFF_DECISION = """| **R-9** | **R158 的「唯一正面结论」撤回（R159 证伪位触发）**：R158 的「A2 两点校准在失真批上中位 0.49%、严格支配 PAT 转发 31.90% ⇒ 处理失真批应优先做两点校准」**不成立** —— 该分层 41 批中 **29 批的化验 PAA 是占位值**（CV < 2%、动态范围 17.8 mg/L）⇒ ① A2 在其上**退化为常数预测**（拟合斜率中位 0.0010、预测动态范围 0.072%），**连常数基线都打不过**（37/41 批更差，p=1.03e−07）；② **剔除退化批后 A2（20.47%）劣于 C0（10.29%）**，方向反转（50/57，p=4.24e−09）；③ 真·失真批（n=12）上 A2（30.48%）**劣于常数基线**（28.64%）。**D-71 / D-72 / D-70 维持且 D-71 被加固**（增量 R² 0.0199→0.0092、t 0.104→0.036）。**新增边界 B-13 / B-14** | `docs/r159_round_report.md`；`docs/r157_debt_ledger.md` D-73/D-74（并修订 D-71）；**B-13 / B-14**（新增边界）；§4.3 新增两条禁止表述。**`cap` 口径不变**（仍 L2 prototype conditional，D-65 仍未闭合） |
"""

BANNED_ANCHOR = "| \"PAT 可作为处理引擎 PAA 失真批的方案\""
DECISION_ANCHOR = "| **R-8** |"
BOUNDARY_ANCHOR = "| **B-12** |"


def update_signoff():
    lines, raw, nl = _read_crlf(SIGNOFF)
    body = "\n".join(lines)
    n0 = raw.count(b"\r\n")

    # 1) 禁止表述：追加两条
    if "处理失真批应优先做两点校准" not in body:
        idx = None
        for i, l in enumerate(lines):
            if l.startswith(BANNED_ANCHOR):
                idx = i
        if idx is None:
            raise SystemExit("[fail] 签核单未找到禁止表述锚点")
        lines[idx + 1:idx + 1] = SIGNOFF_BANNED.rstrip("\n").split("\n")
        print("[ok] 签核单追加 2 条禁止表述")

    # 2) 边界清单：追加 B-13 / B-14
    body = "\n".join(lines)
    if "| **B-13** |" not in body:
        idx = None
        for i, l in enumerate(lines):
            if l.startswith(BOUNDARY_ANCHOR):
                idx = i
        if idx is None:
            raise SystemExit("[fail] 签核单未找到 B-12 锚点")
        lines[idx + 1:idx + 1] = SIGNOFF_ROWS.rstrip("\n").split("\n")
        print("[ok] 签核单追加 B-13 / B-14")

    # 3) 决策清单：追加 R-9（放在 R-8 之后）
    body = "\n".join(lines)
    if "| **R-9** |" not in body:
        idx = None
        for i, l in enumerate(lines):
            if l.startswith(DECISION_ANCHOR):
                idx = i
        if idx is None:
            raise SystemExit("[fail] 签核单未找到 R-8 锚点")
        lines.insert(idx + 1, SIGNOFF_DECISION.rstrip("\n"))
        print("[ok] 签核单追加 R-9")

    # 4) 修订 B-10 里的「正面结论」表述（幂等：命中才改）
    _b10_done = False
    for i, l in enumerate(lines):
        if l.startswith("| **B-10** |"):
            if "R159 修订" in l:
                print("[skip] B-10 已是 R159 修订版")
            else:
                new_l = l.replace(
                    "正面结论仅限「失真批上 PAT 优于引擎直报」，但被**两点校准**"
                    "（A2 口径：只做留一锚点仿射校准、**完全不用 PAT**）中位 **0.49%** 严格支配"
                    "（PAT 为 31.90%）⇒ **处理失真批应优先做两点校准，而非引入 Raman 资产**。",
                    "**R159 修订**：R158 原称「正面结论仅限『失真批上 PAT 优于引擎直报』，但被两点校准"
                    "（A2）中位 0.49% 严格支配 ⇒ 处理失真批应优先做两点校准」——"
                    "**该 A2 支配结论已撤回（见 B-14 / D-74）**；且该分层的 29 批化验退化（见 B-13），"
                    "剔除后真·失真批（n=12）上 PAT 优于引擎直报仅 **2/12、p=0.0386** ⇒ "
                    "**「失真批上 PAT 优于引擎直报」也不得单独引用**。"
                    "**保留结论**：PAT 无独立信息（增量 R² 0.0199→0.0092、t 0.104→0.036，加固）⇒ **不引入交付**不变。")
                if new_l != l:
                    lines[i] = new_l
                    print("[ok] 修订 B-10 的正面结论表述")
                else:
                    print("[skip] B-10 未匹配到待替换文本（可能已改写）")
            _b10_done = True
            break
    if not _b10_done:
        print("[skip] 未找到 B-10 行")

    n0, n1 = _write_crlf(SIGNOFF, lines, raw, nl)
    print("[ok] 签核单更新（CRLF %d → %d）" % (n0, n1))


# ---------------------------------------------------------------- 路线图
def update_roadmap():
    lines, raw, nl = _read_crlf(ROADMAP)
    body = "\n".join(lines)
    if "R159 修订" in body:
        print("[skip] 路线图已有 R159 修订")
        return
    for i, l in enumerate(lines):
        if "T3-3" in l and "R158 已完成" in l:
            lines[i] = l.rstrip() + (
                "。**R159 修订（证伪位触发）**：该结论的「唯一正面结论」"
                "（A2 中位 0.49% 严格支配 PAT ⇒ 优先做两点校准）**已撤回** —— "
                "失真批 41 批中 **29 批化验值退化**（V6 批 61–90 的 `PAA_offline` 是占位值），"
                "A2 在其上退化为常数预测且连常数基线都打不过；"
                "**剔除后 A2 20.47% 劣于 C0 10.29%** ⇒ 方向反转。"
                "**D-71 / D-72 / D-70 维持**（D-71 加固）。详见 `docs/r159_round_report.md`")
            print("[ok] 路线图 T3-3 行补 R159 修订")
            break
    n0, n1 = _write_crlf(ROADMAP, lines, raw, nl)
    print("[ok] 路线图更新（CRLF %d → %d）" % (n0, n1))


# ---------------------------------------------------------------- state.yaml
D73_S = ("  - R159 D-73（化验信号退化区）：V6 批 61–90 的 `PAA_offline` 是占位值"
        "（均值 1198.6–1205.0 mg/L，CV 0.13–1.85%，动态范围 6.7–102.4 mg/L）"
        "⇒ 该区间无 PAA 化验信息；全 100 CSV 普查确认退化 30 批"
        "⇒ 任何以化验为真值/分母的统计必须先做信号退化筛查")

D74_S = ("  - R159 D-74（A2 结论撤回）：R158 的「A2 两点校准中位 0.49% 严格支配 PAT」"
        "不成立 —— 五道证伪门四门触发（化验退化/常数基线同量级/斜率退化为 0/前推式优势消失）"
        "⇒ 剔除 29 批退化批后 A2 20.47% 劣于 C0 10.29%"
        "⇒ 「处理失真批应优先做两点校准」撤回；D-71/D-72/D-70 维持且 D-71 加固")

ART_R159 = ("  r159_a2_falsification: "
            "runs/r159_a2_falsification.json - R159 A2 证伪位检验"
            "（五道证伪门 + 化验退化筛查 + 有效口径重判 + R158 交叉影响）")


def update_state():
    lines, raw, nl = _read_crlf(STATE)
    n0 = raw.count(b"\r\n")

    try:
        i = lines.index("open_questions:")
    except ValueError:
        raise SystemExit("[fail] state.yaml 未找到 open_questions")
    end = _block_end(lines, i)
    existing = "\n".join(lines[i + 1:end])
    for tag, txt in (("D-73", D73_S), ("D-74", D74_S)):
        if ("R159 %s" % tag) in existing:
            print("[skip] open_questions 已有 %s" % tag)
            continue
        _check_plain(txt)
        lines.insert(end, txt)
        end += 1
        print("[ok] open_questions 追加 %s" % tag)

    try:
        j = lines.index("artifacts:")
    except ValueError:
        raise SystemExit("[fail] state.yaml 未找到 artifacts")
    jend = _block_end(lines, j)
    block = "\n".join(lines[j + 1:jend])
    if "r159_a2_falsification:" not in block:
        _check_artifacts_value(ART_R159)
        lines.insert(jend, ART_R159)
        jend += 1
        print("[ok] artifacts 追加 r159_a2_falsification")
    else:
        print("[skip] artifacts 已有 r159_a2_falsification")

    n0, n1 = _write_crlf(STATE, lines, raw, nl)
    import yaml
    raw2 = open(STATE, "rb").read()
    try:
        doc = yaml.safe_load(raw2.decode("utf-8"))
    except Exception as e:
        raise SystemExit("[fail] state.yaml 写入后 YAML 解析失败：%s: %s"
                         % (type(e).__name__, str(e)[:200]))
    print("[ok] state.yaml 更新（CRLF %d → %d，YAML 解析通过，oq=%d art=%d）"
          % (n0, n1, len(doc.get("open_questions", [])), len(doc.get("artifacts", {}))))


def _block_end(lines, start):
    """block sequence 的结束行下标（下一个非缩进且非空行）。"""
    j = start + 1
    while j < len(lines):
        l = lines[j]
        if l.strip() == "":
            j += 1
            continue
        if not l.startswith(" ") and not l.startswith("-"):
            break
        j += 1
    return j


# ---------------------------------------------------------------- 契约
ROW = ("| v1.89 | R159：**A2 结论撤回 + 化验退化区登记**"
       "（v1.88 之后的**事实变更**；不改写历史记录；**引擎零改动**）。"
       "①**R158 的「唯一正面结论」撤回**：失真批（`A_engine_r ≤ 0.5`，n=41）里 **29 批的化验 "
       "`PAA_offline` 是占位值**（V6 批 61–90，钉在 ~1200 mg/L，CV 0.13–1.85%）"
       "⇒ A2 在其上**退化为常数预测**（拟合斜率中位 **0.0010**、预测动态范围 **0.072%**），"
       "**连常数基线都打不过**（37/41 批更差，p=1.03e−07）⇒ "
       "**剔除退化批后 A2 中位 20.47% 劣于 C0 中位 10.29%**（50/57，p=4.24e−09），"
       "**方向反转**；真·失真批（n=12）上 A2 30.48% 劣于常数基线 28.64% ⇒ **D-74**。"
       "②**新增数据债 D-73**：化验信号退化区 ⇒ 统计前须做退化筛查。"
       "③**D-71 / D-72 / D-70 维持，且 D-71 加固**（增量 R² 0.0199→0.0092、t 0.104→0.036、"
       "`pat_vs_engine_r` 0.9796→0.9843）⇒ **PAT 仍不引入交付**。"
       "④**签核单同步**：新增边界 **B-13 / B-14**、决策 **R-9**、§4.3 两条禁止表述；"
       "`state.yaml` 的 `open_questions`（D-73/D-74）与 `artifacts` 已回填 ⇒ **三处一致**；"
       "**`cap` 口径不变**（仍 L2 prototype conditional，D-65 未闭合）。 |")


def update_contract():
    lines, raw, nl = _read_crlf(CONTRACT)
    n0 = raw.count(b"\r\n")
    if any(l.startswith("| v1.89 |") for l in lines):
        print("[skip] 契约已有 v1.89 行")
        return
    body = ROW.strip()
    _check_no_pipe(body, "契约 v1.89 行")
    idx = None
    for i, l in enumerate(lines):
        if l.startswith("| v1."):
            idx = i
    if idx is None:
        raise SystemExit("[fail] 未找到契约版本表")
    lines.insert(idx + 1, ROW)
    n0, n1 = _write_crlf(CONTRACT, lines, raw, nl)
    print("[ok] 契约追加 v1.89（CRLF %d → %d）" % (n0, n1))


def main():
    update_ledger()
    update_signoff()
    update_roadmap()
    update_state()
    update_contract()


if __name__ == "__main__":
    main()
