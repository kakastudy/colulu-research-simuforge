# -*- coding: utf-8 -*-
"""R157：把 v1.85 变更行追加到 ENGINE_CONTRACT.md §4 版本表。

一次性迁移脚本（锚点断言保证幂等：重复执行会因 v1.85 已存在而中止）。
文件为纯 CRLF ⇒ 插入内容按 CRLF 拼接。
"""
import io
import sys

P = "ENGINE_CONTRACT.md"
CR = "\r\n"

ROW = (
    "| v1.85 | R157：**M4 签核单重评审 —— cap 升 L2 prototype (conditional)**（验收层两处恒真/兼容性缺陷修复 + 黄金集 hash 凭证 + 治理层收口；**引擎零改动**）。"
    "①**回溯发现**：M4 单（2026-11-03）列出的 4 个 L2 阻断项**实质上已全部关闭** —— "
    "**3** 由 R143 撤销命题（b92 故障载体是回放输入里的 `Fb` 撞下限，140–160 h 恒 10.00 mL/h，不是注入算子；标称窗内 pH RMSE 0.254、最低 5.434 vs 化验 5.482；b98 独立复现 0.170）；"
    "**5** 由 R136/R137 证伪 A 档 X 幅度不可修复（五类杠杆 72 配置全部把产量推出 ±5%、兑换率 1:1）→ R139 B 档观测器交付（nRMSE 3.17%、86/86 <15%、I3 逐点覆盖 0.8992），且 R154 证明 S 残糖型状态**结构性不可辨识**（0.002 g/L 残差需 0.01% 通量精度）；"
    "**6** 由 R138/R139 给出 90% 区间 [−6.82%,+9.45%]、逐点覆盖 0.8992；"
    "**7** 由 R142 归因于温度口径失效（`T_EB=1.0` 比损失差 106×、ESS=46.8/48）后改以 **MAP 口径保守上界** σ_pop(mux)≤0.0328 / mup≤0.0056 / m_s≤0.0019（不含群体先验）关闭 ⇒ "
    "**卡 L1 的不是技术债没清，而是签核单从未重评审**。"
    "②**三项裁决**（用户 2026-11-05 指示「按建议推进、平台可视化先不做」）：**T0-1(b) 保持默认基线**（候选基线 v2 保持 opt-in；切换属 GOAL §5 边界变更）、"
    "**T0-2(a) 标准 2 接受「B 档交付 X」作为达标口径**（A 档已证伪不可修复）、**T0-3(a) 标准 4 改判 PASS**（故障特征由回放解释、幅值不可定量属输入饱和）。"
    "③**判定口径新增「有界 PARTIAL」**：标准 2 = X 达标(B 档) + S 封边界 + P 60–120 h 缺口 **−0.0625**（验收均值口径）/ **−0.0923**（跨批中位数口径）仍 PARTIAL；"
    "标准 5 = I2 五通道全覆盖 + **I3 仅覆盖 X 通道**（0.8992；0.95 名义值未采用）仍 PARTIAL ⇒ **二者均未被判为达标**，只把「未定口径」变为「已定口径的已知边界」。"
    "**已知边界清单 B-1~B-7** 落 `docs/m5_review_signoff.md` §4.4（对外必须一并引用）。"
    "④**`acceptance.py --reuse` 的 health 恒真已修**：`runs/r151_shape_baseline.json`（D-38 之前生成）86 行**无 `health` 字段** ⇒ `shp.summarise()` 静默返回 0 计数 ⇒ "
    "**G2（catastrophic）与 G2b（degraded）两条 HARD 判据恒真通过**（与 D-38 同一类错误的复发，发生在 `--reuse` 通路）。"
    "现改为：读到无 health 的 rows ⇒ 两条判据显式 **SKIP + WARN**，结论标注「PASS(hard, N 判据跳过——不可视为完整验收)」，**退出码 2**（0=全 PASS / 1=有 FAIL / 2=判据被跳过）；"
    "`shp.summarise()` 增 `n_health_rows` / `health_available` 两字段。主推验收命令改为 `--reuse runs/r156_acceptance.json`（带 health：normal 77 / degraded 5 / catastrophic 4）。"
    "⑤**numpy 版本兼容缺陷已修**：`conservation.py` 与 `mechanism_cclosure.py` 直接写 `np.trapezoid`（**numpy 2.0 才引入**的新名；requirements.txt 锁 numpy **1.26.4 <2.0**，1.x 只有 `np.trapz`）⇒ "
    "在 pinned 环境**必崩**（AttributeError），与 README §1 旧陈述恰好相反；已改为 `getattr(np, \"trapezoid\", None) or np.trapz`（与 `conservation_metrics.py` / `r138_carbon_observer.py` 一致）。"
    "**这两个模块目前无现役路径 import**（全仓 grep 无结果）⇒ 原属**潜伏**缺陷，但它们是「守恒」与「C 平衡自洽」的名义载体。"
    "⑥**黄金集 hash 快照**已落 `data/processed/golden_set.sha256`（`data/processed/batches/` 下 100 个 `batch_XX.csv` 逐文件 sha256 + 字节数，外加 `golden_set.json` 名单 normal 10 / fault 2）⇒ "
    "GOAL「黄金集只增不减」从**约定**变为**机器可验凭证**；`tools/r157_golden_hash.py --check` 报「修改 / 删除 / 新增 / 名单变化」四类差异（新增允许；修改/删除/改名单 ⇒ exit 1），**交付前必跑**。"
    "⑦**M5 仍 `in_progress`**：平台口径同步（T1-3）与 T8 逐屏复验（T1-4）被用户显式暂缓 ⇒ **cap 的 L2 条件尚差这一项**；**授权范围限定为引擎侧 + 验收层 + X 通道 B 档，不含看板对外口径**。"
    "⑧**默认路径零漂移**：`ph_fix` 与候选基线 v2 的 `mup` 重标**均默认关闭**，未经 GOAL §5 边界变更授权不得提为默认。 |"
)


def main():
    s = io.open(P, encoding="utf-8", newline="").read()
    if "| v1.85 |" in s:
        print("!! v1.85 已存在，未改动（幂等保护）")
        return 1
    if CR not in s:
        print("!! 预期 CRLF 文件")
        return 2
    # 锚点：v1.84 行之后插入
    anchor = "| v1.84 |"
    i = s.find(anchor)
    if i < 0:
        print("!! 未找到 v1.84 行")
        return 2
    j = s.find(CR, i) + len(CR)          # v1.84 行末
    s = s[:j] + ROW + CR + s[j:]
    io.open(P, "w", encoding="utf-8", newline="").write(s)
    print("OK: v1.85 已追加")
    return 0


if __name__ == "__main__":
    sys.exit(main())
