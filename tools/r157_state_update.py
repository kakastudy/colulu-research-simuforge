# -*- coding: utf-8 -*-
"""R157 / T1-5：state.yaml 状态更新（去矛盾 + cap 升 L2 conditional + 新债项登记）。

一次性迁移脚本（幂等性由 assert 保证：重复执行会因锚点已改而失败）。
换行符：state.yaml 为纯 CRLF ⇒ 全部锚点与插入块都按 CRLF 处理。
"""
import io
import sys

P = "state.yaml"
CR = "\r\n"


def crlf(t):
    return t.replace("\r\n", "\n").replace("\n", CR)


def main():
    s = io.open(P, encoding="utf-8", newline="").read()
    if CR not in s:
        print("!! 预期 CRLF 文件，未找到 CR —— 中止")
        return 2

    def sub1(old, new, label):
        nonlocal s
        n = s.count(old)
        if n < 1:
            print(f"  [FAIL] {label}: 锚点未找到（count={n}）")
            print(f"         old = {old[:80]!r}")
            return False
        s = s.replace(old, new, 1)
        print(f"  [ok] {label}")
        return True

    ok = True

    # 1. status_ladder
    ok &= sub1(
        "status_ladder: L1 prototype   # 2026-11-03 M4 有条件通过（docs/m4_review_signoff.md）；R138 补入 B 档观测器后 L2 阻断项降至 3 个；R156 关闭 D-55 机制侧、新增 D-56/D-57 后仍为 4 个",
        "status_ladder: L2 prototype (conditional)   # 2026-11-05 R157 **M4 签核单重评审**（docs/m5_review_signoff.md）：M4 单的 4 个 L2 阻断项（3/5/6/7）已**实质全部关闭**（R143 撤命题 / R136+R137+R139 / R138+R139 / R142）⇒ cap 升 L2；**条件未闭合 1 项**：平台口径同步与 T8 逐屏复验（用户 2026-11-05 显式暂缓）⇒ M5 保持 in_progress；授权范围限定为**引擎侧 + 验收层 + X 通道 B 档**，不含看板对外口径",
        "status_ladder")

    # 2. stage.current（去矛盾：平台并未逐屏复验）
    ok &= sub1(
        "  current: M5 引擎+看板（L1 prototype；平台五视图已逐屏复验，A 档评估集 86 批）",
        "  current: M5 引擎+看板（cap = **L2 prototype (conditional)**；A 档评估集 86 批；⚠️ **平台五视图逐屏复验【待做】**——2026-11-05 用户显式暂缓平台可视化（T1-3/T1-4），此前记的「已逐屏复验」不成立）",
        "stage.current")

    # 3/4. gates
    ok &= sub1(
        "    M4: PASS   # 2026-11-03 有条件通过：docs/m4_review_signoff.md（2 PASS/3 PARTIAL/0 FAIL）；证据 docs/m4_acceptance_package.md",
        "    M4: PASS   # 2026-11-03 有条件通过：docs/m4_review_signoff.md（2 PASS/3 PARTIAL/0 FAIL）；证据 docs/m4_acceptance_package.md；**2026-11-05 重评审**：docs/m5_review_signoff.md（4 个 L2 阻断项实质关闭 → cap 升 L2 conditional；三项裁决 T0-1(b) 保持默认基线 / T0-2(a) 接受 B 档交付 X / T0-3(a) 标准 4 改判 PASS）",
        "gates.M4")
    ok &= sub1(
        "    M5: in_progress   # platform/serve.py 五视图 + MCP A/B/C 档；待 T8 逐屏复验",
        "    M5: in_progress   # platform/serve.py 五视图 + MCP A/B/C 档；**待 T8 逐屏复验**（2026-11-05 用户显式暂缓平台可视化 ⇒ T1-3 换口径 / T1-4 重跑复验 均挂起）⇒ cap 的 L2 条件**尚差这一项**",
        "gates.M5")

    # 5. cap.level
    ok &= sub1("  level: L1 prototype", "  level: L2 prototype (conditional)", "cap.level")

    # 6. cap.reasons 前置 R157
    r157 = (
        "R157 **M4 签核单重评审 —— cap 升 L2 prototype (conditional)**（docs/m5_review_signoff.md）。"
        "①**回溯发现**：M4 单（2026-11-03）列出的 4 个 L2 阻断项**实质上已全部关闭** —— "
        "3 由 R143 **撤销命题**（b92 故障载体是回放输入里的 Fb 撞下限而非注入算子；b98 独立复现）；"
        "5 由 R136/R137 证伪 A 档 X 幅度不可修复（72 配置全部破线、兑换率 1:1）→ R139 **B 档观测器交付**（nRMSE 3.17%、86/86 <15%、I3 0.8992）且 R154 证明 S 残糖型状态**结构性不可辨识**；"
        "6 由 R138/R139 给出逐点覆盖 **0.8992**；7 由 R142 改以 **MAP 口径保守上界** σ_pop(mux)≤0.0328 / mup≤0.0056 / m_s≤0.0019（不含群体先验）关闭 ⇒ "
        "**卡 L1 的不是技术债没清，而是签核单从未重评审**。"
        "②**三项裁决**（用户 2026-11-05 指示「按建议推进、平台可视化先不做」）："
        "**T0-1(b) 保持默认基线**（候选 v2 保持 opt-in；切换属 GOAL §5 边界变更）；"
        "**T0-2(a) 标准 2 接受 B 档交付 X**（A 档已证伪不可修复）；"
        "**T0-3(a) 标准 4 改判 PASS**（故障特征由回放解释、幅值不可定量属输入饱和）。"
        "③**判定口径新增「有界 PARTIAL」**：标准 2 = X 达标(B 档) + S 封边界 + P 60–120 h 缺口 −0.0625（验收均值口径）/ −0.0923（中位数口径）仍 PARTIAL；"
        "标准 5 = I2 五通道全覆盖 + I3 仅覆盖 X 通道（0.8992；0.95 名义值未采用）仍 PARTIAL ⇒ **二者均未被判为达标**。"
        "④**已知边界清单 B-1~B-7** 落签核单 §4.4（对外必须一并引用）。"
        "⑤**验收层两处工程缺陷已修**：`acceptance.py --reuse` 的 **health 恒真**（旧 json 无 health 字段 ⇒ G2/G2b 恒真 PASS）→ 改为显式 **SKIP + WARN + exit 2**（退出码 0=全 PASS / 1=有 FAIL / 2=判据被跳过）；"
        "`conservation.py` / `mechanism_cclosure.py` 的 **np.trapezoid**（numpy 2.0 才引入而本项目锁 1.26.4 ⇒ 必崩）→ 改 `getattr(np,\"trapezoid\",None) or np.trapz`。"
        "⑥**黄金集 hash 快照**已落 `data/processed/golden_set.sha256`（100 批 CSV 逐文件 sha256 + 名单）⇒「只增不减」从约定变机器可验。"
        "⑦**M5 仍 in_progress**：平台口径同步（T1-3）与 T8 逐屏复验（T1-4）被用户显式暂缓 ⇒ L2 条件尚差这一项；**授权范围不含看板对外口径**。")
    assert "[" not in r157 and "]" not in r157
    assert ", " not in r157
    ok &= sub1("  reasons: [", "  reasons: [" + r157 + ", ", "cap.reasons 前置 R157")

    # 7. open_questions 新条目
    oq_lines = [
        "  - ✅ R157 **验收层恒真判据已修**：`acceptance.py --reuse` 复用**无 health 字段**的旧 json（D-38 之前生成，如 runs/r151_shape_baseline.json）时，G2（catastrophic）与 G2b（degraded）两条 HARD 判据**恒真通过** ⇒ 现改为显式 **SKIP + WARN**，结论标注「PASS(hard, 2 判据跳过——不可视为完整验收)」，**退出码 2**（0=全 PASS / 1=有 FAIL / 2=判据被跳过）；`shp.summarise()` 增 `n_health_rows` / `health_available` 两字段。**主推验收命令已改为 `--reuse runs/r156_acceptance.json`**（该文件带 health：normal 77 / degraded 5 / catastrophic 4）。纪律同 D-38：「恒真的判据等于没有判据」。",
        "  - ✅ R157 **numpy 版本兼容缺陷已修**：`conservation.py` 与 `mechanism_cclosure.py` 直接写 `np.trapezoid`（**numpy 2.0 才引入**的新名；本项目 requirements.txt 锁 numpy **1.26.4 <2.0**，1.x 只有 `np.trapz`）⇒ 在 pinned 环境**必崩**（AttributeError），与 README §1 旧陈述恰好相反；已改为 `getattr(np, \"trapezoid\", None) or np.trapz`。**这两个模块目前无现役路径 import**（全仓 grep 无结果）⇒ 原属**潜伏**缺陷，但它们是「守恒」与「C 平衡自洽」的名义载体。",
        "  - ✅ R157 **黄金集完整性已机器可验**：`data/processed/golden_set.sha256` 记录 `data/processed/batches/` 下 100 个 `batch_XX.csv` 的逐文件 sha256 + 字节数，外加 `golden_set.json` 名单（normal 10 / fault 2）；`python tools/r157_golden_hash.py --check` 报「修改 / 删除 / 新增 / 名单变化」四类差异（新增 CSV 允许；只增不减 ⇒ 修改/删除/改名单则 exit 1）。**交付前必跑**。",
        "  - ⏳ **D-57（最高优先，T2-1）**：b22 类**双稳态**，找**连续**旋钮。在 b22 上扫 `sd`（门控宽度）/ `mean_P`（门控中心）/ `k_deg`，判据：**响应不连续度 < 5 pp**。`mup` 已证不连续（0.3→0.9 产量恒 −99.9%、1.0 跳到 32.7）不可用。⇒ 找到则 D-54 闭环可重开、D-42 有空间；找不到则闭环控制器在这套方程里**永久关闭**，产能模型边界就此确定。",
        "  - ⏳ **D-56（T2-2，便宜低风险）**：`validity()` 的 pH 越域判据（≥7.0 即 invalid）**误杀 9 批** —— pH_max 7.001–7.126、末值 6.46–7.03、**产量全部达标、0 钳位**。改判据为「是否落在守门员钳位 / 是否远离实测区间」而非「是否 ≥ 7.0」；**必须报分布不能只报计数**（R151 的 D-44 教训）。预期 valid 77/86 → 86/86。",
        "  - ⏳ **T3-1（能力扩展）**：I3 覆盖率**只覆盖 X 通道**（0.8992；0.95 名义值未采用），S/P/DO2/PAA 的 CI **从未做过**（观测器目前只估 X）。GOAL §4 标准 5 要求的是「置信区间覆盖率经验证」⇒ 要么扩观测器到 S/P，要么把标准 5 口径明确写成「仅 X 通道」。",
        "  - ⏸ **平台可视化暂缓**（2026-11-05 用户指示「平台可视化部分先不做」）：T1-3（`platform/data.js` 换数据源到 runs/r156_acceptance.json、catastrophic KPI 改用 classify_health 五通道）与 T1-4（T8 逐屏复验重跑）**均挂起**。⇒ 看板仍停在 **v1.69 口径**，其「0 catastrophic」来自 D-38 已判恒真的 `crash_level`；**M5 保持 in_progress、cap 的 L2 条件尚差这一项**。",
    ]
    ok &= sub1("open_questions:" + CR, "open_questions:" + CR + CR.join(oq_lines) + CR,
               "open_questions 新条目（7 条）")

    # 8. artifacts
    ok &= sub1(
        "  golden_set: data/processed/golden_set.json",
        "  golden_set: data/processed/golden_set.json" + CR
        + "  golden_set_hash: data/processed/golden_set.sha256   # R157 新增：100 批 CSV 逐文件 sha256 + 名单（只增不减的机器可验凭证）" + CR
        + "  m5_signoff: docs/m5_review_signoff.md   # R157 新增：M4 签核单重评审（cap → L2 conditional）" + CR
        + "  roadmap: docs/roadmap_next.md   # R157 新增：回溯 + 下一步工作清单（T0/T1/T2/T3）",
        "artifacts")

    if not ok:
        print("\n!! 有锚点未命中，未写入（保持原文件不变）")
        return 1

    io.open(P, "w", encoding="utf-8", newline="").write(s)
    print("\n写入完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
