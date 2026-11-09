# 投稿策略与交付说明 · 方法学版（中文导读）

> 日期：2026-11-07　|　对应稿件：`paper/manuscript_methods.md` / `.html` / `.pdf`
> 本文件是**给作者的工作说明**，不是论文正文，投稿前请删除或留在本地。
> **与旧版的关系**：`submission_strategy_zh.md` 对应「数字孪生认证审计」定位的 `manuscript.md` 与 `manuscript_journal.md`；本文件对应「过程仿真模型可信度方法学」重定位后的版本。**投稿请以本文件为准**，旧版仅作为历史版本保留。

---

## 1. 定位变更：从「审计报告」到「验证方法学」

重定位依据：用户提供的「论文模块重设计 + 试验补充方案」。核心原则是**不更改研究本身**——不改冻结基线、不改模型、不改校准参数、不改既有数值结论、不新增湿实验、不新增外部数据；只做两件事：重新组织叙事，以及对既有冻结资产做真实重算与补充诊断。

| 维度 | 旧定位（数字孪生认证审计） | 新定位（过程仿真验证方法学） |
|---|---|---|
| 研究对象 | 一个青霉素数字孪生的认证与治理审计报告 | 一套可移植的**反事实验证协议** |
| IndPenSim 角色 | 核心案例与贡献载体 | 工业级**演示基准**（demonstration substrate） |
| 阴性结果 | 审计发现 / 待整改项 | **方法学证据**（判据区分效度、可辨识性边界） |
| 主术语 | digital twin / certificate / quarantine / promotion | process simulation model / validation criterion / discriminative validity / reject or flag / model update adoption |
| 四层架构 L0–L3 | 主文核心图与创新点 | 压缩为 §2.7「证据门控流程」，细节入补充材料 S1 |
| 运行时加载、V1/V2/V3、软传感器通道矩阵 | 主文 | 全部降级至补充材料 S2–S5 |
| 核心贡献 | 可证伪性定义 + 治理框架 + 完整负结果 | 判据区分效度诊断 + 数值/秩/迁移/不连续性四条前置约束 + 最小准入清单 |
| 目标读者 | 工业数字孪生、可信 AI | 过程仿真、V&V、可辨识性、仿真优化 |

**研究本身未改动的六项事实**（主稿 §1 已显式声明）：33 态机理模型未改；86 批逐批校准参数表未改；冻结基线 2.3448% RMSE / 86 of 86 within ±5% 未改；健康分级、软传感器 5 折 CV、候选评估及所有既有数值结果未改；未采用任何 opt-in 候选；补充试验全部为对同一冻结资产的重算、真实仿真或纯计算诊断。

## 2. 五条可辩护的核心贡献

与 Abstract、§1 末段完全对齐，投稿信与答辩时按此口径展开：

1. 提出**可执行的反事实验证协议**：零信息对照、常数检测器检验、触发率审计、观测算子秩检验；判据按控制分离 / 输出熵 / 检出功效三轴分别记分。
2. 证明**四个常用验证工具在结构上无法区分模型与无模型基线**：残差分位覆盖率、legacy crash 分类器、全局创新判据、文件存在式加载测试。
3. 把**结构可辨识性零空间**与**不连续参数响应**重新表述为仿真状态估计、灵敏度分析与优化的前置约束，而非「控制不可用」的工程备注。
4. 用**留批次参数迁移实验**区分「重建一致性」与「有条件可迁移性」，直接回应「逐批校准使 RMSE 无意义」的审稿质疑。
5. 给出面向过程仿真实践的**最小验证清单**（Box 1）与准入过滤器：退化判据先剔除，再进入多准则合成。

## 3. 补充试验 E1–E8：真实结果与落点

全部为脚本从冻结资产真实计算，机器可读证据见 `methods_experiments.json`；39 个主稿数值由 `fill_methods_numbers.py` 回填，无手填。

| 编号 | 真实结果（不得改写） | 章节 | 图表 |
|---|---|---|---|
| **E1** 求解器敏感性 | 6 代表批 × 4 配置 = 24 次重积分，22 次成功；中位端产品偏差 0.014%，最大 32.567%（近双稳盆地边界）；Radau 2 次显式步长失败；结论是**结构化、批次依赖的数值敏感性**，不是「与求解器无关」 | §2.2 / §3.1 | Fig. 4, Table 3 |
| **E2** 留批次迁移 | 5 个 disjoint folds；median prior RMSE 97.47% / bias -94.87% / 1 of 20 within ±5%；drawn prior RMSE 73.53% / bias -21.84% / 3 of 24；P5/P95 覆盖率 0.22，中位区间宽度 24.9% of yield；迁移误差约为重建误差的 41.6 倍 | §2.5 / §3.5 | Fig. 15, Table 10 |
| **E3** 不连续响应与梯度失效 | 二分 bracket 2.44e-7 / 2.44e-8，跃变 101.33 / 100.51 pp；步长 1e-2→1e-8 下视在梯度按 1/h 发散；12×12 响应面 132 个相邻区间中 34 个 >1 pp/unit、25 次符号翻转；SLSQP 与 trust-constr 各 5 初值，3/10 停在初值 | §2.6 / §3.4 | Fig. 14, Table 9 |
| **E4** 可辨识性诊断协议 | H_assim 50×4 rank 0 / nullity 4；H_report 60×4 rank 1 / nullity 3；追加 0–4 个独立隔室分辨观测行使 rank 0→4、nullity 4→0；追加 50 行已有聚合观测后 rank 仍为 1 | §2.4 / §3.3 | Fig. 12, Table 8 |
| **E5** 判据区分效度矩阵 | 10 个判据，6 剔除 / 4 准入（M4 五通道分类器、M5 通道级留一创新、M6 均值 ±1.96σ、M8 运行时 import+callable）；结构性失败 4 个，另有 M9 退化离散度、M10 完全共线 phi=1.0000 | §2.3 / §3.2 | Fig. 9–11, Table 2, Table 7 |
| **E6** 参数不确定性传播 | 6 replicates × 5 batches = 30 次全新积分；pooled RMSE 35.95%，P5 -53.13%，P95 27.42%，最大 105.69%；相关系数 alpha_kLa 0.21 > mup 0.17 > mux 0.01 | §3.1 | Fig. 8 |
| **E7** 物理一致性 | 碳平衡中位 -1.63%，12/13 within ±20%；氮按模型约定 +9.9% 达标、按真实计量约定 -58.1% 越界；RQ 由记录输入精确给出；模拟 OUR/CER 约 +12% 偏置，**声明而不修正** | §3.6 | Fig. 16, Table 11 |
| **E8** 准入过滤器 | 输入 10 判据 / 129 门检 / 5 门族，输出 4 个准入判据；保留 4 项门失败记录；剔除项**归档而非删除**；退化判据不进入任意权重 composite score | §3.6 | Fig. 17, Table 12 |

**E9** 软传感器 5 折 CV 已保留于补充材料 S5 及 Fig. S1/S2（biomass / viscosity / DO2 改进，product / PAA / substrate 标注边界）。**E10** 代理模型/降阶模型验证为 P2 可选项，本轮未执行；若目标期刊追问「跨模型可移植性」，这是最省力的补强点。

## 4. 目标期刊（重定位后需重新排序）

| 优先级 | 期刊 | 契合点 | 主要风险 |
|---|---|---|---|
| **主推** | *Computers & Chemical Engineering* (Elsevier) | 过程仿真 + 方法学；IndPenSim 相关扩展论文发表于此，审稿人熟悉基准；对 V&V、可辨识性、仿真优化约束有共同语言 | 会追问「与既有 V&V 框架的区别」；需在 cover letter 强调**可执行判据诊断**而非概念框架 |
| **并列主推** | *Simulation Modelling Practice and Theory* (Elsevier) | 仿真验证方法学是最直接的落点；对负结果与诊断性论文更友好 | 可能要求第二个仿真案例以证可移植性；E10 或第二公开基准可补 |
| 备选 1 | *Journal of Process Control* | §3.4 不连续响应与梯度失效、优化/灵敏度约束契合度高 | 需要更强的控制/估计应用场景，主稿偏方法学 |
| 备选 2 | *Chemical Engineering Research and Design* | 过程系统工程读者群，工业基准接受度高 | 方法学贡献可能被要求压缩为应用案例 |
| **不建议** | 数字孪生 / 工业 AI 专刊 | 会把论文重新推回「一个孪生的审计报告」的定位错位 | 审稿人会用数字孪生的成功叙事框架评判阴性结果，命中率显著下降 |

**重要口径变化**：旧策略以 IF > 10（CEJ / Nature Communications）为硬筛选条件。重定位后的 C&CE 与 SIMPAT 影响因子通常低于 10，但**定位匹配度与录用概率显著提高**。若仍坚持 IF > 10，应保留旧版 `manuscript_journal.*` 路线并接受其定位风险；两套稿件的标题、术语、贡献陈述与 cover letter **不可混用**。目标期刊的最新 JCR 与 Aims & Scope 请在投稿当年重新核验，本文件不固化影响因子数字。

## 5. 四条审稿应对（按重定位方案预置）

| 审稿质疑 | 主稿中的应答位置 | 应答要点 |
|---|---|---|
| 「逐批校准使 2.3448% RMSE 无意义」 | §3.5、Fig. 15、Table 10、Abstract | E2 直接给出迁移误差 97.47% / 73.53% 与覆盖率 0.22，主动承认逐批校准不构成前瞻预测；把「重建一致性」与「有条件可迁移性」分开报告 |
| 「阴性结果过多」 | §3.2、§3.3、§4 | 区分**审计性阴性结果**（判据失效、结构不可辨识、共线）与**候选失败**（V2 种子迁移，已降入补充材料 S4）；前者是方法学证据，后者是应用示例 |
| 「与既有 V&V 有何区别」 | §1、§2.3、Box 1 | V&V 停留在概念框架（模型能否被证伪）；本文给出**对判据本身**的可执行诊断、三轴记分、实际失效清单与准入过滤器 |
| 「工程意义在哪里」 | §3.4、§3.1、§3.6 | E3 梯度失效约束仿真优化与局部灵敏度；E6 给出 35.95% 的不确定性尺度（远大于重建误差）；E8 把诊断接到 MCDA 前端 |

## 6. 三条仍需主动声明的风险

1. **单一仿真基准。** 主稿 §4 Limitations 已写明协议可移植但只在 IndPenSim 上演示；§5 把「第二过程 + 前瞻数据」列为 future work。投 SIMPAT 或综合刊前，E10 或第二个公开基准（哪怕只跑零信息对照与秩检验两项）几乎必需。
2. **全部 in silico 且逐批校准。** 这是诚信底线，Abstract / §1 / §3.5 / §4 四处显式声明，**不要删**。E2 已把该限制量化，比单纯声明更有分量。
3. **文献与书目信息。** 主稿 49 条字母序作者-年份引用，自检 M10 / M10b / M11 已验证全部可解析、全部被正文引用、按字母序排列。投稿前仍需用文献管理器统一核对卷页与 DOI，并按目标期刊样式重排（部分期刊要求数字编号）。

## 7. 主稿结构与交付规格

| 项 | 规格 |
|---|---|
| 模块 | Title / Running title / Highlights / Keywords / 单段无加粗 Abstract / 1 Introduction / 2 Materials and methods (2.1–2.7) / 3 Results (3.1–3.6) / 4 Discussion / 5 Conclusions / CRediT / Declaration of competing interest / Data availability / Acknowledgements / References |
| 版式 | 单栏（明确不用双栏）；A4 PDF 32 页；交互式 Canvas 2D 工艺流程图在 HTML 与 PDF 横版页中各一份 |
| 图表 | 24 图（含 Fig. S1–S7 补充图）、12 表；新绘 10 张 `figM*.png/pdf`（300 dpi PNG + 矢量 PDF） |
| 文献 | 49 条，字母序，作者-年份 |
| 自检 | `methods_check.json`：**PASS 15/15**（占位符、内部过程痕迹、术语、投稿模块、章节、图、表、头条数值、回填数值、引用解析、全文献被引用、字母序、HTML/PDF 交付、补充材料、独立 Markdown） |
| 数值链 | `methods_experiments.json`（69 KB 证据）→ `fill_methods_numbers.py` → `methods_numbers.json`（39 值）→ 主稿；无手填数值 |

## 8. 交付文件清单

根目录：`C:\Users\liuli\Desktop\AI4S\青霉素反应罐\paper\`

| 文件 | 内容 |
|---|---|
| `manuscript_methods.md` | 方法学主稿（78 KB），独立可编辑 Markdown |
| `manuscript_methods.html` | 自包含 HTML（8.5 MB），全部图 base64 内嵌，含交互式 Canvas 2D 工艺流程图 |
| `manuscript_methods.pdf` | A4 打印版（5.5 MB，32 页），Fig. 2 工艺流程图独占横版整页 |
| `supplementary_methods.md` | 补充材料 S1–S8（13 KB）：证据门控流程、五通道分类器、运行时加载、V1/V2/V3、软传感器通道矩阵、E1–E8 可复现协议、图表目录、数值约定 |
| `cover_letter_methods.md` | **本轮新增**：匹配方法学定位的英文投稿信 |
| `submission_strategy_methods_zh.md` | 本文件：方法学版投稿策略与交付说明 |
| `methods_experiments.py` / `.json` | E1–E8 补充试验脚本（fast / sim 两阶段）与机器可读证据 |
| `make_method_figures.py` | 生成 9 张方法学新图，数值全部取自证据 JSON |
| `fill_methods_numbers.py` / `methods_numbers.json` | 39 个主稿数值回填，含 unresolved placeholder 硬失败 |
| `check_methods.py` / `methods_check.json` | 15 项一致性自检 |
| `build_html.py` / `export_pdf.py` | 参数化三格式构建链（`export_pdf.py` 已改为动态图数校验，不写死 19） |
| `figures/figM*.png` / `.pdf` | 方法学新图；`figM10_axes.*` 为中性命名副本，避免文件名带旧术语 |

保留但未改动的历史版本：`manuscript.md` / `manuscript_journal.md` 及其 html/pdf、`cover_letter.md`、`submission_strategy_zh.md`、`references.bib`、`check_journal.py`。

## 9. 投稿前必须补齐

| 项 | 当前状态 | 需要做什么 |
|---|---|---|
| 作者 / 单位 / 通讯 / ORCID | 主稿 3 处、投稿信 1 处占位 | 填写，确认全部作者已审阅并同意 |
| CRediT 作者贡献 | 占位 | 按期刊要求补 |
| 资助 / 利益冲突 / Acknowledgements | 占位 | 填写并逐作者确认 |
| 目标期刊名、编辑姓名、推荐审稿人 | `[Journal Name]` / 占位 | 按 §4 选定期刊后填写；建议三类专家（过程仿真与 V&V、结构可辨识性与状态估计、不连续响应下的仿真优化） |
| 数据与代码永久标识 | 仅本地路径 | 打包 `runs/` 关键 JSON + `paper/` 证据与脚本上传 DOI 仓库，加许可证，替换 Data availability 中的本地表述 |
| 数据使用许可 | 未声明 | 核对 IndPenSim 原作者再分发条款，必要时只上传派生证据而非原始批次 CSV |
| 期刊格式 | 通用 Markdown / 单栏 | 按目标期刊模板重排：字数上限、Results/Discussion 是否合并、图注位置、参考文献样式（C&CE 与 SIMPAT 多为数字编号，需转换） |
| 图件规格 | 300 dpi PNG + 矢量 PDF | 按目标期刊单栏/双栏宽度缩放，确认字体嵌入与色盲友好 |
| 预印本 | 未声明 | 若先投 arXiv，需同步声明并确认期刊政策 |
| 伦理声明 | 已写「不适用」 | in-silico 研究，无需改动 |

## 10. 绝对不能宣称的清单

沿用旧策略的九条（逐位复现 MATLAB、独立验证集、coverage 0.8995 达标、0 catastrophic、S/P/PAA/菌丝区可交付、运行期闭环控制可行、V2 NO_GO 改写为 PASS、真实工厂/GMP/前瞻验证、不放宽 20/30 pp 阈值），并**新增本轮六条**：

- 不宣称切换求解器对全部批次无影响：E1 最大偏差 32.567%，且 Radau 有 2 次显式失败。
- 不宣称逐批校准参数可前瞻迁移：E2 已给出 97.47% / 73.53% 的迁移误差与 0.22 覆盖率。
- 不宣称有限差分 Jacobian、局部灵敏度或梯度优化在该响应面可直接采用：E3 的 1/h 发散、25 次符号翻转与 3/10 停滞是硬约束。
- 不宣称增加同类观测数据量能消除零空间：E4 追加 50 行已有聚合观测后 rank 仍为 1，只有**新增测量类型**才提升秩。
- 不宣称参数不确定性小于重建误差：E6 pooled RMSE 35.95% 对 2.3448%，二者不是同一量。
- 不宣称修改过模型、校准参数或冻结基线，也不宣称新增湿实验或外部数据。

## 11. 自检与复现

```
python paper/methods_experiments.py --stage fast     # E3/E4/E5/E7/E8
python paper/methods_experiments.py --stage sim      # E1/E2/E6（真实积分，耗时较长）
python paper/make_method_figures.py
python paper/fill_methods_numbers.py
python paper/build_html.py paper/manuscript_methods.md paper/manuscript_methods.html
python paper/export_pdf.py paper/manuscript_methods.html paper/manuscript_methods.pdf "Counterfactual validation of process simulation models" "Process simulation validation &middot; in silico"
python paper/check_methods.py
```

环境注意：仿真脚本必须在带 numpy / scipy 的 Python 环境下运行，并固定 `OMP_NUM_THREADS=1`、`OPENBLAS_NUM_THREADS=1`、`MKL_NUM_THREADS=1`、`NUMEXPR_NUM_THREADS=1`；默认 workbuddy Python 3.13 缺少这些依赖。逐批参数的权威来源是 `golden_params.params_for(batch)`，**不要**用 `runs/final_validation_v2.json` 里的 `results[].params`（那是部分参数记录，会导致仿真结果偏离冻结锚点）。

交互式查看平台：`python platform/serve.py --port 8771`（8770 保持不动）。
