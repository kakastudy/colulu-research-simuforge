# -*- coding: utf-8 -*-
"""R157 收口：ENGINE_CONTRACT.md 追加 **v1.87** 行（D-57 定案事实登记）。

约束：
  * 契约文件为**纯 CRLF** ⇒ 全程按 CRLF 处理，lone LF 必须为 0；
  * **幂等**：锚点 `| v1.87 |` 已存在则 [skip]；
  * **不改写 v1.85 / v1.86 的历史行**（只在其后追加）；
  * markdown 表格行内**禁止裸竖线**（会破坏表格结构）。
"""
import os
import sys

P = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "ENGINE_CONTRACT.md")

ROW = (
    "| v1.87 | R157 续：**D-57 定案 —— 连续旋钮搜索四版判据 + 崩塌态逃逸判决实验**"
    "（v1.86 之后的**事实变更**；不改写 v1.85 / v1.86 的历史记录；**引擎零改动**）。"
    "①**判据四版演进**（D-69）：v1 的二分更新用「到端点距离比较 + `<=`」在近 100 pp 跳变时把高端中点"
    "**错记到低端** ⇒ 区间塌陷 ⇒ **假阳性 CONTINUOUS**；v2 改「以响应区间中点为界」但对**单调光滑**响应会"
    "收敛到「响应取中值处」⇒ **假收缩**；**v3 锚点夹逼**（锚点 = 粗扫两端响应且固定不移动，中点按"
    "**最近锚点**分类 ⇒ 不变量「区间始终含跳变两侧」⇒ 收敛到**跳变位置本身**）；"
    "**v4** 新增 **粗区间直接密扫**（单调光滑响应不能用二分）与 **`ERRATIC` 第三分支**"
    "（密采样相邻差分**变号 ≥3 次** ⇒ 混沌窗，既非阶跃也非可走的连续段）。"
    "②**基线态判定**：`sd`（`P_std_dev`）**DISCONTINUOUS**（区间跨度恒 99.83 pp）、"
    "`mean_P` **DISCONTINUOUS**（恒 99.92 pp）、`Y_sP`（环路增益直旋钮）**DISCONTINUOUS**"
    "（恒 99.99 pp，跳变位置 **Y_sP ≈ 0.894344**）、`mu_h_scale` **ERRATIC**"
    "（4.2→4.3 间 44 pp 断崖后非单调震荡）、**`p_deg_rate` CONTINUOUS**（密扫最大相邻 4.633 pp）"
    "但**只单调降解**（0 → −73.47%）**拉不回崩塌态** ⇒ "
    "**进料可行域的硬约束是阈值型而非参数型**。"
    "③**判决性逃逸实验**（`--base-override \"Y_sP=0.85\"`）**否证了本轮自己的预判**："
    "崩塌态**不是吸引子** —— `sd` 跨过 `0.0015217285` ~ `0.0015219727`、"
    "`mean_P` 跨过 `0.002040625` ~ `0.0020406494` 即可让产量由 **−100.00%** 跃回 "
    "**+1.33% / +0.51%**（`valid=True`）；但两个能逃逸的旋钮响应是**阶跃**，"
    "两个连续旋钮在崩塌态下**全程产量恒 −100%、`valid=False`** ⇒ "
    "**没有任何旋钮能连续走回生产态**。"
    "④**D-54 分层封死**：**运行期连续调控（梯度型闭环）不可行**"
    "（响应是阶跃、跳变两侧无可用梯度区分度）；**开环设定点重整定可行**但落点相对精度要求 "
    "**1e−04（`sd`）… 1e−05（`mean_P`）** ⇒ 属**标定级**而非**控制级**；"
    "若要运行期调控须走**结构改动**路线（L3，需另行授权）。"
    "⑤**D-42（60–120 h 产素缺口）按预案转「已知边界」结案**"
    "（−0.0625 验收均值口径 / −0.0923 中位数口径）。"
    "⑥**纪律**：预判式结论必须留**专门的证伪位**且被触发时**必须改写结论**；"
    "形式判据达成 ≠ 实质可用（连续性判据只回答「能不能小步走完」，不回答「走完能不能到目标」）。"
    "⑦**治理层同步**：签核单新增边界 **B-9** 与决策 **R-7**、修订 **B-1 / B-2**、"
    "§4.3 新增三条禁止表述；`state.yaml` 的 `open_questions`（D-57 定案 / D-56 关闭）与 "
    "`artifacts`（`r157_bistab_escape.json` + v1/v2 缺陷留证）已回填 ⇒ **三处一致**。 |"
)


def main():
    # markdown 表格行：`| v1.87 | 内容 |` —— 内容体内不得有裸竖线（会破坏表格结构）
    body = ROW.strip()
    head = "| v1.87 |"
    if not (body.startswith(head) and body.endswith(" |")):
        raise SystemExit("[fail] 表格行首尾格式不符")
    inner = body[len(head):-2]
    if "|" in inner:
        raise SystemExit("[fail] 表格行内容体内含裸竖线")
    with open(P, "rb") as f:
        raw = f.read()
    text = raw.decode("utf-8")
    lines = text.split("\r\n")
    n_crlf_before = raw.count(b"\r\n")

    if any(ln.startswith("| v1.87 |") for ln in lines):
        print("[skip   ] 契约 v1.87 已存在（幂等）")
        return 0

    idx = None
    for i, ln in enumerate(lines):
        if ln.startswith("| v1.86 |"):
            idx = i + 1
    if idx is None:
        raise SystemExit("[fail] 找不到 v1.86 行")
    lines.insert(idx, ROW)
    print("[ok     ] 契约 v1.87 已追加（插在 v1.86 之后）")

    out = "\r\n".join(lines).encode("utf-8")
    with open(P, "wb") as f:
        f.write(out)

    with open(P, "rb") as f:
        raw2 = f.read()
    if b"\n" in raw2.replace(b"\r\n", b""):
        raise SystemExit("[fail] 出现 lone LF")
    ls2 = raw2.decode("utf-8").split("\r\n")
    i86 = [i for i, ln in enumerate(ls2) if ln.startswith("| v1.86 |")]
    i87 = [i for i, ln in enumerate(ls2) if ln.startswith("| v1.87 |")]
    assert len(i87) == 1, "v1.87 行数异常"
    assert i86 and i87[0] == i86[0] + 1, "v1.87 未紧跟 v1.86"
    print("[ok] CRLF 保持：%d → %d；v1.86 @line %d、v1.87 @line %d"
          % (n_crlf_before, raw2.count(b"\r\n"), i86[0], i87[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
