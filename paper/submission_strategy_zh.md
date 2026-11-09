# 投稿策略与交付说明（中文导读）· 历史版本

> **重要：本文件已被取代。** 2026-11-07 完成的论文重定位把稿件从「数字孪生认证审计」改写为「过程仿真模型可信度方法学」，目标期刊、贡献陈述、术语与投稿信全部随之变更。新方法学版请以 **`submission_strategy_methods_zh.md`** 为准，配套主稿 `manuscript_methods.md` / `.html` / `.pdf` 与投稿信 `cover_letter_methods.md`。本文件仅作为历史版本保留，勿与新稿件混用。
>
> 日期：2026-11-06　|　对应稿件：`paper/manuscript.md`（旧定位）
> 本文件是**给作者的工作说明**，不是论文正文，投稿前请删除或留在本地。

---

## 1. 一句话结论

已完成一份约 1 万词的**英文原创研究论文**，定位不是「我们复现了青霉素仿真、误差 2.345%」，而是：

> **把「可证伪性」变成数字孪生的一等工程要求**：用 86 批工业规模青霉素补料分批仿真做完整案例，系统性地证伪三类「看似达标、实则恒真」的验收指标，给出四层证据闸门架构、结构不可辨识性图谱、以及一个以 NO_GO 收场且拒绝放宽阈值的预注册负结果。

这个定位是能否够到 IF > 10 的关键。只报精度，最多是领域内方法改进；报「验收仪器本身不可信 + 一套可迁移的治理框架 + 完整负结果」，才具备跨学科方法学价值。

## 2. 四条可辩护的创新点

| # | 创新点 | 论文中的证据 |
|---|---|---|
| 1 | 四层架构 L0–L3，把「评估」与「授权」分离，候选永不静默晋级 | Fig. 1、Table 2、§3.10；L3 明确未执行 |
| 2 | 用零信息对照 / 恒定检测器 / 触发率审计，证伪三个验收指标 | Fig. 4、Table 4、§4.3；coverage 0.899548532731377 逐位相同、crash_level 86/86 恒真、创新判据 84.38% |
| 3 | 结构不可辨识性与控制不可达被登记为「已知边界」而非待办 | Fig. 6、§4.2/§4.5；H_assim rank 0/nullity 4、阶跃 99.8–101.5 pp |
| 4 | 预注册负结果：扰动方差注入 NO_GO，单种子标定在样本外崩塌 | Fig. 5、Table 5、§4.6；96.06 pp / 3 of 6 崩塌 / seed 11 → 99.85 pp / 18/20 NO_GO / 阈值未放宽 |

配套的治理链（契约 v1.97、债务台账 D-2…D-92、签核 R-1…R-17、闸门 25/25 + 20/20、幂等同步）让**负结果成为可复核的一等证据**，这是与「可重复性危机」文献对话的落点。

## 3. 目标期刊候选（IF 数据于 2026-11-06 核验，投稿当年请以最新 JCR 为准）

| 优先级 | 期刊 | 已核验 IF | 契合点 | 主要风险 |
|---|---|---|---|---|
| **主推** | *Chemical Engineering Journal* (Elsevier) | **12.5**（JCR 2025；2024 为 13.2），Q1 / 中科院 1 区 Top | 过程系统工程、工业数字孪生、基准仿真是其核心读者群；IF 明确 > 10 | 编辑可能要求「真实工厂数据」或更明确的工程增益；需在 cover letter 强调方法学普适性 |
| **进阶** | *Nature Communications* | **18.1**（JCR 2025，2024 约 15.7） | 多学科方法学 + 可重复性/可信度议题高度契合；对负结果友好 | 单一案例（仅 IndPenSim）容易被判「普适性不足」；**建议补第二个独立过程案例后再投** |
| 备选 | *Engineering* / *Science Advances* 等综合工程刊 | 投稿前核对最新 JCR | 若 CEJ 认为过于方法学，可转向综合工程刊 | 需要重新对齐篇幅与图表规格 |

> 提醒：IF > 10 只是筛选条件，不等于录用概率。审稿人最可能攻击的是「只有一个仿真基准」与「没有真实工厂验证」——这两点已在 Abstract / Limitations 主动写明，不能靠删掉来回避。

## 4. 三条主要审稿风险与补强建议

1. **全部证据 in silico，且 86 批各自带标定参数。**
   已在 Abstract、§3.1、§4.1、§6 四处显式声明「2.3448% 是重建一致性，不是前瞻预测」。**这是本稿的诚信底线，不要删。**
   补强建议：若能补一组「留出批次、不使用该批标定参数」的前瞻评估，哪怕结果更差，也会显著增强可信度——且与论文主旨一致。

2. **方法普适性只有一个案例。**
   已在 §5.5 给出可迁移的九项清单（Box 1），§7 把「第二个独立过程 + 前瞻工厂数据」列为 future work。
   补强建议（投 Nature Communications 前几乎必需）：把同一套审计协议跑在第二个公开基准上，哪怕只验证「零信息对照」和「秩检验」两项，也能把「单一案例」变成「跨案例方法」。

3. **参考文献与书目信息。**
   39 条文献中，Birol 2002、Goldrick 2015/2019、Kapoor & Narayanan 2023、Raue 2009、Brunton 2016、Henderson 2018、Wilkinson 2016、Bland & Altman 1986、Shapiro & Wilk 1965 已联网核对卷页与 DOI；其余为标准经典文献。
   补强建议：投稿前用 Zotero/EndNote 统一导入 `references.bib` 并核对无 DOI 条目的卷页，再按目标期刊格式重排编号引用。

## 5. 投稿前必须补齐的清单

| 项 | 当前状态 | 需要做什么 |
|---|---|---|
| 作者 / 单位 / 通讯 / ORCID | 4 处 `[to be completed]` 占位 | 填写，确认全部作者已审阅并同意 |
| 作者贡献 CRediT | 未写 | 按期刊要求补 |
| 资助 / 利益冲突 | 占位 | 填写并逐作者确认 |
| 数据与代码永久标识 | 仅本地路径 | 打包 `runs/` 关键 JSON + `platform/` + `paper/` 上传 Zenodo 等 DOI 仓库，加许可证，替换 §7 本地路径为永久链接 |
| 数据使用许可 | 未声明 | 核对 IndPenSim 原作者的再分发条款 [2,3]，必要时只上传派生证据而非原始批次 CSV |
| Cover letter | 草稿 | 填期刊名、通讯作者、推荐审稿人（建议 3 类专家，见文件内提示）、签名 |
| 期刊格式 | 通用 Markdown | 按目标期刊模板重排：字数上限、结构（是否合并 Results/Discussion）、图注位置、参考文献样式 |
| 图件规格 | 300 dpi PNG + 矢量 PDF，7.2 in 宽 | 按目标期刊单栏/双栏宽度缩放；确认字体嵌入、色盲友好 |
| 伦理声明 | 已写「不适用」 | 符合 in-silico 研究，无需改动 |
| 预印本 | 未声明 | 若先投 bioRxiv / arXiv，需同步声明并确认期刊政策 |

## 6. 绝对不能宣称的清单（写作时已主动规避）

- 不宣称 MATLAB 逐位复现（`rng('shuffle')` 种子未记录，oq#36）；只宣称「与我方冻结基线逐位一致」。
- 不宣称有独立验证集或分层估计的泛化误差（D-89：28 批验证集从未留出）。
- 不把 coverage 0.8995 / 0.8992 当达标证据（D-78 已判构造性恒真）。
- 不宣称「0 catastrophic」（来自 D-38 恒真判据）；只说「4 已登记 / 0 新发」。
- 不宣称 S / P / PAA / 菌丝区可交付（结构不可辨识）。
- 不宣称运行期闭环控制可行（阶跃响应）。
- 不把 V2 的 NO_GO 改写成 PASS，不放宽 20/30 pp 阈值，不删除首过 16/18 FAIL 证据。
- 不宣称任何真实工厂 / GMP / 前瞻试验验证。

## 7. 交付文件清单

根目录：`C:\Users\liuli\Desktop\AI4S\青霉素反应罐\paper\`

| 文件 | 内容 |
|---|---|
| `manuscript.md` | 英文全文：Title / Abstract / Keywords / §1–§7 / Declarations / 39 条 References；12 主图 + 7 补图、11 张表 |
| `manuscript.html` | 自包含 HTML（内嵌全部图与公式），含**交互式 Canvas 2D 工艺流程图**（悬停溯源、图层开关、PNG 导出） |
| `manuscript.pdf` | A4 打印版（35 页；Fig. 12 工艺流程图独占横版整页） |
| `supplementary.md` | 补充材料：8 条 Supplementary Notes + 3 张补图图注 + 表格索引 |
| `supplementary_tables.md` | 机器生成的数值附录 S-Table A–I（86 批全表、通道 nRMSE、coverage 原始值、V2 网格、seed 迁移、G1–G25 / F1–F20 清单） |
| `references.bib` | 39 条 BibTeX，可直接导入文献管理器 |
| `cover_letter.md` | 英文投稿信草稿 |
| `submission_strategy_zh.md` | 本文件 |
| `make_figures.py` / `make_figures_v2.py` | 从 `runs/` 真实 JSON 生成 19 张 300 dpi PNG + 18 张矢量 PDF 图 |
| `make_extended_stats.py` | 从 `runs/` 二次派生扩展统计（朴素基线阶梯、判别力证书、证据矩阵、校准阶梯） |
| `pfd.js` / `pfd.html` / `export_pfd.py` | Canvas 2D 工艺流程图（交互版 + 300 dpi 静态导出） |
| `build_html.py` / `export_pdf.py` | 三格式构建链：md → 自包含 HTML → A4 PDF（headless Chrome） |
| `make_supplement.py` | 从 `runs/` 生成数值附录 |
| `check_manuscript.py` | 一致性自检（22 项判据），输出 `manuscript_check.json` |
| `figures/` | `fig1…fig12`、`figS1…figS7`（PNG + PDF，fig12 为 Canvas 导出） |

## 8. 图表清单

| 编号 | 主题 | 主数据出处 |
|---|---|---|
| Fig. 1 | 四层证据闸门架构 + 治理脊 | `state.yaml`、`ENGINE_CONTRACT.md`、`r166_ab_gate.json` |
| Fig. 2 | 33 态模型 / 观测层 / 四环回退链 | `model.py`、`solver_chain.py`、`r157_i3_channels.json` |
| Fig. 3 | 86 批产量误差 + 五通道健康分级 | `final_validation_v2.json`、`r156_acceptance.json` |
| Fig. 4 | 三个恒真指标被证伪 | `r160_i3_coverage_tautology.json`、`r163_degradation_probe.json` |
| Fig. 5 | 扰动注入：scale 扫描 / seed 迁移 / 全幅崩塌 | `r166_v2_optim.json`、`r166_ab_gate.json` |
| Fig. 6 | 结构不可辨识性 + 阶跃响应 | `r165_mycelium_identifiability.json`、`r157_bistab_escape.json` |
| Fig. S1 | 六通道 nRMSE（A vs B，5 折 CV） | `r157_i3_channels.json` |
| Fig. S2 | 运行时装载与六视图平台 | `r167_platform_gate.json`、`r167_final_check.json` |
| Fig. S3 | 167 轮证据生命周期 | 各轮报告与治理文本 |

所有图均**由脚本从证据 JSON 读取数值绘制**，没有手填数据；图注中标注了对应文件。

## 9. 复现命令

```
python -m pip install -r requirements.txt
python platform/export_data.py
python tools/r167_platform_gate.py
python tools/r167_final_check.py
python paper/make_figures.py
python paper/make_supplement.py
python paper/check_manuscript.py
```

交互式查看平台：`python platform/serve.py --port 8771`（8770 保持不动）。

## 10. 若需要 Word / LaTeX 投稿版

本轮交付的是 Markdown 主稿 + BibTeX + 矢量图，便于继续编辑与版本管理。若目标期刊要求 Word 模板，可在安装 pandoc 后用：

```
pandoc paper/manuscript.md --citeproc --bibliography=paper/references.bib -o paper/manuscript.docx
```

或者按期刊 LaTeX 模板排版，`figures/*.pdf` 可直接 `\includegraphics`，`references.bib` 可直接 `\bibliography`。转换后务必人工核对表格、图注与编号引用（Vancouver 数字编号在自动转换时可能需要 `--csl` 指定样式）。
