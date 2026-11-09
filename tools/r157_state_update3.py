# -*- coding: utf-8 -*-
"""R157 收口：state.yaml 回填 —— D-57 定案 / D-56 关闭 / D-57 工件登记。

约束：
  * state.yaml 为**纯 CRLF** ⇒ 全程按 CRLF 处理；
  * **幂等**：锚点已替换则 [skip]，复跑不产生重复条目；
  * **行级定位**（不靠字符串偏移）⇒ 区块在文件中间或末尾都能处理；
  * YAML 解析校验 + plain scalar 安全字符检查
    （plain scalar 内禁止半角逗号 / 方括号 / 花括号 / 半角冒号+空格 / 半角 #）。
"""
import os
import sys

P = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "state.yaml")

# ---------------------------------------------------------------- 新文本
D57_NEW = (
    "  - ✅ R157 **D-57 已定案（T2-1）**：b22 类**双稳态**的连续旋钮搜索。"
    "**判据四版演进**（见 D-69）：v1 平局 bug（假阳性 CONTINUOUS）→ v2 响应中点界（假收缩）→ "
    "v3 锚点夹逼 → v4 粗区间密扫 + **`ERRATIC` 第三分支**。"
    "**基线态结论**：`sd` / `mean_P` / `Y_sP` 全为 **DISCONTINUOUS**（跳变位置 `Y_sP ≈ 0.894344`）、"
    "`mu_h_scale` 为 **ERRATIC**（混沌窗）、**`p_deg_rate` 为 CONTINUOUS**（密扫最大相邻 4.633 pp）"
    "但**只单调降解、拉不回崩塌态** ⇒ **进料可行域的硬约束是阈值型而非参数型**。"
    "**判决性逃逸实验**（`Y_sP=0.85`；`runs/r157_bistab_escape.json`）⇒ "
    "`sd` 跳变落在 `0.0015217285` ~ `0.0015219727`、"
    "`mean_P` 跳变落在 `0.002040625` ~ `0.0020406494`，"
    "跨过去产量由 **−100.00%** 跃至 **+1.33% / +0.51%** "
    "⇒ **崩塌态不是吸引子**（**否证了本轮预判**），但**没有任何旋钮能连续走回生产态**。"
    "⇒ **D-54 分层封死**：**运行期连续调控（梯度型闭环）不可行**"
    "（响应是阶跃、跳变两侧无可用梯度区分度）；"
    "**开环设定点重整定可行**但落点相对精度要求 **1e−04…1e−05**（属**标定级**而非**控制级**）。"
    "⇒ **D-42（60–120 h 产素缺口）按预案转「已知边界」**"
    "（−0.0625 验收均值口径 / −0.0923 中位数口径）。"
)

D56_NEW = (
    "  - ✅ R157 **D-56 已关闭（T2-2）**：`validity()` 的 pH 越域判据改为「**感知 basic 分支是否已修正**」"
    "而非拍阈值 7.0。**默认基线 `valid_old = valid_new = 77`（逐位一致）**、"
    "`valid_if_basic_fixed = 81`（残余 5 批是**真钳位** —— 原路线图「0 钳位」描述已勘误）；"
    "**候选基线 v2 实测 `valid_new = 86/86`、钳位 0、invalid 名单为空**"
    "（`runs/r157_validity_v2.json`；21m31s）。"
    "⚠ **反直觉证据**：候选 v2 下**越 7 占比反而更高**（b50 11.66% vs 默认基线 1.04%），"
    "但 basic 分支已修 ⇒ **越 7 不再意味着数值病态** ⇒ 实证「判据要感知状态、不能拍阈值」。"
)

ART_OLD = ("  r157_bistab_knob: runs/r157_bistab_knob.json"
           "   # R157/D-57 连续旋钮扫描（v2 判据）")
ART_NEW = ("  r157_bistab_knob: runs/r157_bistab_knob.json + runs/r157_bistab_escape.json"
           "   # R157/D-57 连续旋钮扫描（v4 判据）+ 崩塌态逃逸判决实验")
ART_ADD = ("  r157_bistab_defects: runs/r157_bistab_knob_v1_bisectbug.json"
           " + runs/r157_bistab_knob_v2_midpoint_bisect.json"
           "   # D-57 判据 v1/v2 缺陷留证（不删）")

# ---------------------------------------------------------------- 工具
FORBIDDEN = [",", "[", "]", "{", "}", " #"]


def _check_plain(s):
    """plain scalar 安全字符检查（YAML 1.2 ns-plain-char）。"""
    for bad in FORBIDDEN:
        if bad in s:
            raise AssertionError("plain scalar 含危险字符 %r：%s" % (bad, s[:80]))
    if ": " in s:
        raise AssertionError("plain scalar 含半角冒号+空格：%s" % s[:80])


def _replace_line(lines, anchor, new_text, label, check=True):
    """把含 anchor 的整行替换为 new_text；已替换过则跳过（幂等）。

    check=True 用于 **block sequence 的 plain scalar**（open_questions 条目）：
    禁止半角逗号 / 方括号 / 花括号 / 半角冒号+空格 / 半角 #。
    check=False 用于 **mapping 行**（artifacts：`key: value   # 注释`）——
    其注释部分天然合法，不适用 plain scalar 规则。
    """
    if check:
        _check_plain(new_text)
    hits = [i for i, ln in enumerate(lines) if anchor in ln]
    if not hits:
        return lines, 0, "notfound"
    if len(hits) > 1:
        raise AssertionError("锚点 %r 命中 %d 行" % (anchor, len(hits)))
    i = hits[0]
    if lines[i] == new_text:
        return lines, 0, "skip"
    lines[i] = new_text
    return lines, 1, "ok"


def main():
    with open(P, "rb") as f:
        raw = f.read()
    if b"\r\n" not in raw:
        raise SystemExit("[fail] state.yaml 不是 CRLF")
    text = raw.decode("utf-8")
    lines = text.split("\r\n")
    n_crlf_before = raw.count(b"\r\n")

    changed = 0
    for anchor, new_text, label in [
        ("**D-57（最高优先，T2-1）**", D57_NEW, "D-57 open_question"),
        ("**D-56（T2-2，便宜低风险）**", D56_NEW, "D-56 open_question"),
        ("r157_bistab_knob:", ART_NEW, "artifacts r157_bistab_knob"),
    ]:
        # 幂等判定：新文本已在 ⇒ 已处理过（skip），而不是"锚点消失"（notfound）
        if any(ln == new_text for ln in lines):
            print("[skip   ] %s（已是目标文本）" % label)
            continue
        lines, n, st = _replace_line(lines, anchor, new_text, label,
                                    check=not anchor.startswith("r157_bistab_knob"))
        changed += n
        print("[%-7s] %s" % (st, label))

    # 追加缺陷留证行（幂等：已存在则跳过）
    if any(ln.startswith("  r157_bistab_defects:") for ln in lines):
        print("[skip   ] artifacts r157_bistab_defects")
    else:
        idx = None
        for i, ln in enumerate(lines):
            if ln.startswith("  r157_bistab_knob:"):
                idx = i + 1
        if idx is None:
            raise SystemExit("[fail] 找不到 artifacts r157_bistab_knob 行")
        lines.insert(idx, ART_ADD)
        changed += 1
        print("[ok     ] artifacts r157_bistab_defects（新增）")

    if changed == 0:
        print("[skip   ] 无变更（幂等）")
        return 0

    out = "\r\n".join(lines).encode("utf-8")
    with open(P, "wb") as f:
        f.write(out)

    # ---- 校验 ----
    with open(P, "rb") as f:
        raw2 = f.read()
    if b"\n" in raw2.replace(b"\r\n", b""):
        raise SystemExit("[fail] 出现 lone LF")
    try:
        import yaml
        d = yaml.safe_load(raw2.decode("utf-8"))
        oq = d.get("open_questions") or []
        art = d.get("artifacts") or {}
        print("[ok] YAML 解析通过；open_questions n = %d；artifacts n = %d"
              % (len(oq), len(art)))
        assert not any("D-57（最高优先" in str(x) for x in oq), "D-57 旧条目仍在"
        assert not any("D-56（T2-2，便宜低风险" in str(x) for x in oq), "D-56 旧条目仍在"
        assert "r157_bistab_escape.json" in str(art.get("r157_bistab_knob")), "escape json 未登记"
    except ImportError:
        print("[warn] 无 yaml 模块，跳过解析校验")
    print("[ok] state.yaml 回填完成（CRLF 保持：%d → %d）"
          % (n_crlf_before, raw2.count(b"\r\n")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
