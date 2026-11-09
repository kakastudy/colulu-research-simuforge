# -*- coding: utf-8 -*-
"""R158 / T3-3：登记 Raman-PLS 消融的事实变更到 state.yaml 与 ENGINE_CONTRACT.md。

口径
----
- state.yaml 与 ENGINE_CONTRACT.md 均为**纯 CRLF** ⇒ 全部读写按 CRLF 处理。
- **行级定位**（不靠字符串偏移）⇒ 区块在文件中间或末尾都能处理。
- **幂等**：锚点已替换过则 `[skip]`；锚点已消失（被后续轮次改写）则 `[notfound]`，
  两者都**不视为错误**（避免把"已更新"误报成"条目丢失"）。
- `state.yaml` 的 `cap.reasons` 是 YAML flow sequence ⇒ plain scalar 里
  **不得含半角逗号 / 方括号 / 花括号 / 半角冒号+空格 / 半角 #**（老坑）。
- 契约的表格行内**不得含裸竖线**（会破坏列结构）。

用法
----
    python tools/r158_state_contract_update.py
"""
from __future__ import annotations

import io
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
STATE = os.path.join(ROOT, "state.yaml")
CONTRACT = os.path.join(ROOT, "ENGINE_CONTRACT.md")


# ---------------------------------------------------------------- 工具
def _read_crlf(path):
    """**必须二进制读取**：文本模式的 universal newlines 会把 \\r\\n 转成 \\n，
    导致 split('\\r\\n') 退化成「整文件一行」，定位全部失效（这是本轮实际踩到的坑）。"""
    raw = open(path, "rb").read()
    assert b"\n" not in raw.replace(b"\r\n", b""), "%s 存在 lone LF" % path
    return raw.decode("utf-8").split("\r\n"), raw


def _write_crlf(path, lines, raw_before):
    data = "\r\n".join(lines).encode("utf-8")
    assert b"\n" not in data.replace(b"\r\n", b""), "出现 lone LF"
    open(path, "wb").write(data)


def _block_end(lines, start):
    """返回 blocks 内某区块的结束行号（不含）。"""
    i = start + 1
    while i < len(lines):
        ln = lines[i]
        if ln.strip() == "":
            break
        if not ln.startswith((" ", "\t")):
            break
        i += 1
    return i


def _check_plain(text):
    """plain scalar 安全字符校验（state.yaml 的 flow sequence 老坑）。

    注意适用范围：**只对 `cap.reasons`（flow sequence）的元素生效**。
    `open_questions` 的元素是 block scalar 起点（`- **D-xx**：`），冒号是其结构分隔符；
    `artifacts` 是 mapping（`key: value`），冒号同样是分隔符 ⇒ 两者都**不能**用这条校验。
    本函数仅在 flow sequence 场景下调用。
    """
    for ch in (",", "[", "]", "{", "}"):
        if ch in text:
            raise SystemExit("[fail] plain scalar 含非法字符 %r: %s" % (ch, text[:80]))
    if ": " in text:
        raise SystemExit("[fail] plain scalar 含半角冒号+空格: %s" % text[:80])
    if "#" in text:
        raise SystemExit("[fail] plain scalar 含半角 # : %s" % text[:80])


def _replace_line(lines, anchor, new_text, label, check=True):
    """把含 anchor 的整行替换为 new_text；已替换过 ⇒ skip；锚点消失 ⇒ notfound。"""
    if check:
        _check_flow_element(new_text)
    hits = [i for i, l in enumerate(lines) if anchor in l]
    if not hits:
        print("[notfound] %s（锚点已不在，视为已由后续更新覆盖）" % label)
        return lines, 0, "notfound"
    i = hits[0]
    if lines[i] == new_text:
        print("[skip] %s（已是目标文本）" % label)
        return lines, 0, "skip"
    lines[i] = new_text
    print("[ok] %s" % label)
    return lines, 1, "ok"


def _check_flow_element(text):
    """flow sequence 元素的安全字符校验（`cap.reasons` 老坑）。

    仅禁**会破坏 YAML 结构**的字符：半角逗号 / 方括号 / 花括号 / 半角 #。
    **半角冒号+空格在 block scalar（`- key: ...`）与 mapping（`key: value`）里都是合法分隔符**，
    只有在 flow sequence 的裸标量里才致命 ⇒ 故此处不检查冒号。
    """
    for ch in (",", "[", "]", "{", "}", "#"):
        if ch in text:
            raise SystemExit("[fail] 含会破坏 YAML 结构的字符 %r: %s" % (ch, text[:90]))


# ---------------------------------------------------------------- state.yaml
# open_questions 的元素是 **plain scalar**（不是 block scalar）⇒ 必须能安全解析。
# ⚠️ **不能以 `*` 开头** —— YAML 会把 `*xxx` 当作**别名锚点**（alias）解析并报
#    "expected alphabetic or numeric character, but found '*'"。
#    现有条目（如 R157/D-68）都是纯文本开头，本轮同样用纯文本开头。
D70 = ("  - R158/T3-3 D-70（PLS 资产量纲）：PLS 资产 `PAA_PLS_model.mat` 的输出单位**不是 mg/L**"
       "（实测 0–2.11 vs 化验 430–2023 mg/L；Batch_01 真实存储谱 OLS ⇒ lab = 721.263 × pred + 404.644）"
       "⇒ **所有绝对量使用点必须先标定**；R120 的三重验证全用相关系数 ⇒ 量纲错被完全掩盖（D-38 第四形态）")

D71 = ("  - R158/T3-3 D-71（PAT 通道无独立信息）：全池 86 批消融 ⇒ PAT 与引擎 PAA 相关中位 0.9796、"
       "控制引擎后增量 R2 0.0199 / t 0.104 ⇒ **PAT 是引擎 PAA 的重命名，不作为交付组件**；"
       "失真批上 PAT 优于引擎直报 38/41（p=1.05e-08）但被两点校准 A2（中位 0.49%）严格支配")

D72 = ("  - R158/T3-3 D-72（锚定层方向错误）：PAA 锚定修正层把化验锚点锚在 PAT 上，"
       "实测系统性劣于锚在引擎 PAA 上（失真批 41/41 劣化，p=9.1e-13）⇒ 现有 fused 口径不交付；"
       "修正方向为锚在引擎 PAA 上（属 L3，需另行授权）")

ART_PAT = ("  r158_pat_ablation_scale: "
           "runs/r158_pat_ablation_scale.json - T3-3 全池 86 批 Raman/PAA-PLS 消融"
           "（5 口径 + 3 控制组 + 平凡上界 + 增量信息检验 + 分层符号检验）；结论为否定式")

ART_UNIT = ("  r158_raman_unit_probe: "
            "runs/r158_raman_unit_probe.json - T3-3 量纲核证"
            "（Batch_01 真实存储谱 OLS 标定 + 缩放不变性演示）")


def update_state():
    lines, raw = _read_crlf(STATE)
    n_crlf_before = raw.count(b"\r\n")

    # 1) open_questions 追加三条
    try:
        i = lines.index("open_questions:")
    except ValueError:
        print("[skip] state.yaml 未找到 open_questions 区块")
        return
    end = _block_end(lines, i)
    existing = "\n".join(lines[i + 1:end])
    for tag, txt in (("D-70", D70), ("D-71", D71), ("D-72", D72)):
        if ("R158/T3-3 %s" % tag) in existing:
            print("[skip] open_questions 已有 %s" % tag)
            continue
        _check_flow_element(txt)
        lines.insert(end, txt)
        end += 1
        print("[ok] open_questions 追加 %s" % tag)

    # 2) artifacts 追加两条
    try:
        j = lines.index("artifacts:")
    except ValueError:
        print("[skip] state.yaml 未找到 artifacts 区块")
        return
    jend = _block_end(lines, j)
    block = "\n".join(lines[j + 1:jend])
    for key, txt in (("r158_pat_ablation_scale", ART_PAT),
                     ("r158_raman_unit_probe", ART_UNIT)):
        if ("%s:" % key) in block:
            print("[skip] artifacts 已有 %s" % key)
            continue
        _check_flow_element(txt)
        lines.insert(jend, txt)
        jend += 1
        print("[ok] artifacts 追加 %s" % key)

    _write_crlf(STATE, lines, raw)
    raw2 = open(STATE, "rb").read()
    assert b"\n" not in raw2.replace(b"\r\n", b""), "state.yaml 出现 lone LF"
    # **写盘后立即验证 YAML 可解析** —— 本轮实际踩到：`- **D-70...` 以 `*` 开头会被
    # YAML 当作别名锚点解析并报错，而 `yaml.safe_load` 是唯一的发现手段。
    import yaml
    try:
        doc = yaml.safe_load(raw2.decode("utf-8"))
    except Exception as e:
        raise SystemExit("[fail] state.yaml 写入后 YAML 解析失败：%s: %s"
                         % (type(e).__name__, str(e)[:200]))
    print("[ok] state.yaml 写入完成（CRLF %d → %d，YAML 解析通过，oq=%d art=%d）"
          % (n_crlf_before, raw2.count(b"\r\n"), len(doc.get("open_questions", [])),
             len(doc.get("artifacts", {}))))


# ---------------------------------------------------------------- 契约
ROW = ("| v1.88 | R158：**T3-3 Raman/PAA-PLS 消融 —— 结论为否定式**"
       "（v1.87 之后的**事实变更**；不改写 v1.85 / v1.86 / v1.87 的历史记录；**引擎零改动**，仅观测层）。"
       "①**PAT 通道不作为交付组件**：全池 86 批消融 ⇒ PAT 与引擎 PAA 相关中位 **0.9796**、"
       "控制引擎 PAA 后**增量 R² 0.0199 / t 0.104** ⇒ **PAT 是引擎 PAA 的重命名，不含独立信息**（**D-71**）。"
       "②**PAA 锚定修正层的锚定方向错误**：把化验锚点锚在 PAT 上**系统性劣于**锚在引擎 PAA 上"
       "（失真批 **41/41** 劣化，符号检验 p=9.1e−13）⇒ 现有 fused 口径**不交付**（**D-72**）。"
       "③**PLS 资产输出单位不是 mg/L**：实测输出 0–2.11 vs 化验 430–2023 mg/L（差约 1000 倍），"
       "OLS 标定 `lab(mg/L) = 721.263 × pred + 404.644` ⇒ **所有绝对量使用点必须先标定**（**D-70**）；"
       "R120 的三重验证全用相关系数 ⇒ 量纲错被完全掩盖。④**唯一正面结论**（且被更简单方法支配）："
       "引擎 PAA 失真批上 PAT 优于引擎直报 **38/41**（p=1.05e−08），但被**两点校准**"
       "（A2 口径，中位 **0.49%** vs PAT 的 31.90%）**严格支配** ⇒ 处理失真批应优先做两点校准。"
       "⑤**签核单同步**：`docs/m5_review_signoff.md` 新增边界 **B-10 / B-11 / B-12**、决策 **R-8**、"
       "§4.3 新增三条禁止表述；`state.yaml` 的 `open_questions`（D-70/D-71/D-72）与 `artifacts` 已回填 "
       "⇒ **三处一致**；`cap` 口径**不变**（仍 L2 prototype conditional，D-65 未闭合）。 |")


def update_contract():
    lines, raw = _read_crlf(CONTRACT)
    n_crlf_before = raw.count(b"\r\n")
    if any(l.startswith("| v1.88 |") for l in lines):
        print("[skip] 契约已有 v1.88 行")
        return
    # 契约版本表是 **3 列**（`| 版本 | 内容 |`）⇒ 行内必须**恰好 3 个**竖线
    # （1 个表头 + 1 个列分隔 + 1 个表尾）。多于 3 个 ⇒ 有裸竖线会把内容劈成额外列。
    body = ROW.strip()
    assert body.startswith("|") and body.endswith("|"), "表格行必须以 | 包裹"
    n_pipe = body.count("|")
    if n_pipe != 3:
        raise SystemExit("[fail] 表格行竖线数 = %d（应为 3：表头/列分隔/表尾）" % n_pipe)
    # 插到表格末尾：找最后一个以 '| v1.' 开头的行
    idx = None
    for i, l in enumerate(lines):
        if l.startswith("| v1."):
            idx = i
    if idx is None:
        raise SystemExit("[fail] 未找到契约版本表")
    lines.insert(idx + 1, ROW)
    _write_crlf(CONTRACT, lines, raw)
    raw2 = open(CONTRACT, "rb").read()
    assert b"\n" not in raw2.replace(b"\r\n", b""), "契约出现 lone LF"
    print("[ok] 契约追加 v1.88（CRLF %d → %d）" % (n_crlf_before, raw2.count(b"\r\n")))


def main():
    update_state()
    update_contract()


if __name__ == "__main__":
    main()
