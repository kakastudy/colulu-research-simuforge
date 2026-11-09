# tools/INDEX.md — 工具索引

> 目的：`tools/` 下有 **460 个 `.py`**，绝大多数是一次性探针。没有索引时，无法判断哪个是"活的"。
> 判定规则：**被 `ENGINE_CONTRACT.md` 或 r13x 轮次报告引用的 → 活跃**；其余按轮次归档，仅留档可查。
> 新增工具的约定：文件名带轮次前缀（`rNNN_<主题>.py`），并在当轮报告里引用一次，否则三个月后即失联。

---

## 1. 交付闸门（每次改引擎必跑）

| 工具 | 用途 | 期望输出 |
|---|---|---|
| `r134_zero_regression.py` | **零回归闸门**：86 批逐批对比基准 `runs/final_validation_v2.json` | `--tol 0` 时 `max\|Δ\| = 0.00e+00`、RMSE 2.345%、86/86 |
| `golden_params.py` | 86 批黄金集清单（`GOLDEN_ALL`）与名义参数，被引擎/平台/验收共用 | — |
| `diag_final_validation_v2.py` / `diag_final_validation_v3.py` | 86 批验收的诊断视图（逐批产量、崩溃检测、分位数） | — |

引擎侧入口在 `candidate/indpensim/v0.1/`：`validate.py --all86`（产量验收）、`simulate.py --batch N`（单批）。

## 2. 当前活跃分析工具

### R140（N 平衡 / 闭环同化判决）

| 工具 | 用途 | 备注 |
|---|---|---|
| `r140_n_balance.py` | N 元素平衡六口径对比 + **完整账**（含 N 池变化与随罐移除，需 `--with-pool` 跑仿真拿内部 NH3） | `--all86 --with-pool` 约 10 min；结论见 `docs/r140_round_report.md` §1 |
| `r140_closed_loop.py` | 闭环数据同化对比（开环 vs 闭环的 X/P nRMSE 与产量） | **路线已否决**（产量 6/86），保留作反例与回归；`--k-lo/--k-hi` 限幅必设 |

### R152（D-42 旋钮判定，**引擎 +3 个默认关闭的覆盖口**）

| 工具 | 用途 | 备注 |
|---|---|---|
| `r152_gate_probe.py` | 产素门控诊断：用同一组 `mean_P/sd` 分别代入**模型 S** 与**实测 S**，比较 `P_inhib` 的分相位值与占空比 | 只读，单批约 55 s。**结论：60–120 h 模型门控 0.862 > 实测糖对应 0.848 ⇒ 门控不是缺口** |
| `r152_gate_scan.py` | 单臂扫描（9 臂）：`meanP×{1.25,1.5,2}`、`sd×{2,5,10}`、`pcritPAA×{0.5,2}`、`mu_h×{0.95,0.9,0.8}`；报分相位/选择性/产量/valid，**含 base 臂与 R151 基线的 `max\|Δ\|=0` 口径闸门** | 6 批约 7 min。选择性 = `d(60-120)/\|d(120-180)\|` |
| `r152_combo_scan.py` | 组合扫描：`sd`（二阶）× `mu_p`（一阶，走 `dist_mup`）× `mean_P`；`--all86` + `--base-from` 可从基线借 base 臂（省 1/3 时间） | 86 批 × 2 臂约 21 min。**结论：中位全改善、产量逐批崩**（D-42 转已知边界） |

> 引擎覆盖口（默认不传 ⇒ 逐位不变）：`mean_P`→par[4]、`P_std_dev`→**par[3]**、`P_crit_PAA`→par[79]。
> **`P_std_dev` 是 par[3]（1.5e−3），par[5] 是 `mu_v`（1.71e−4）** —— 首版取错，把整轮结论作废过一次。

### R151（形状口径立尺，**引擎纯新增** —— `shape_metrics()` 不被任何既有路径调用）

| 工具 | 用途 | 备注 |
|---|---|---|
| `r153_age_probe.py` | **产素缺口反解**：从实测 P 与 `dy[3]=r_p−dil·P` 解出每批每相位"所需 `mu_p` 倍率"，逐点 `mu_h`（不是常数）、按 `time_h` 对齐、只统计 `P_inhib>0.2` 的病态过滤 | 88 批约 11 min（7 workers）。**结论：60 h 后三相位中位 0.93–1.01（常数 `mu_p` 已对），0–60 中位 1.631、51/81 批 >1.1，7/88 批门控全关** |
| `r153_lambda_scan.py` | λ（`mu_p_growth`）扫描，复用 `r151_shape_accept` 的 `one()` 口径；`--lams` / `--all86` / `--base-from`（借基线省 1/3 时间） | 12 批 × 2 λ 约 3 min。**结论：λ=0.30 修 48% 形状但产量 8/11；λ=0.60 产量均值 +5.4pp** |
| `r154_s_resid.py` | **S 通道双误差分解**：把 S 的误差拆成「初始峰」（`s_peak_ratio` / `s_r2_hi`，只在 `S>5%·峰` 的点算 R²）与「残糖水平」（30–120 h 中位）+ **门控占空**（0–60 h 内 `gate>0.5` 的时间比）。按 `time_h` 对齐 | 88 批约 11 min（7 workers）。**结论：峰比 1.196、峰时 8.7 vs 7.0 h、`s_r2_hi` 中位 −1.554；残糖 2.02 vs 1.72 mg/L；门控占空实测恒 0.6007 vs 模型中位 0.129、69/86 批门关** |
| `r154_shape_cal.py` | **批级形状标定装置**：任意旋钮组合（`sd18`/`sd20`/`lam045`/`lam060`/`sd18_lam030`）+ **逐批反解 `mup`**（`mup* = mup0·(1+e0)/(1+e1)`，两遍仿真）+ 三段报告（产量保持 / relRMSE 改善 / 峰比不恶化） | 12 批约 5 min。**结论：`sd18` + 逐批 `mup` 只能把 relRMSE 中位 0.1820→0.1560，产量保持 0/12、valid 11→8 ⇒ 不可用** |
| `r154_bistable.py` | **稳定性裕度 / 双稳态**：扫 `mup`（0.60–1.20）看产量是连续还是跳变；另反解「产素耗糖 / 进料糖」占比 | 4 批 × 10 档约 7 min。**结论：b59 ×1.00→×0.95 掉 32pp；斜率 b3 +0.3 / b55 +71 / b59 +411 / b60 +252 pp 每单位 `mup`，逐批差 3 个量级；产素耗糖占进料 27–50%** |
| `r155_closed_loop.py` | **葡萄糖补料闭环 pilot**（`params.fs_ctl`）：全域 PI / 门控邻域 / 时间窗 / 小增益四类配置；报产量、P 分相位、门控占空、进料总量比 | 5 批 × 4 配置约 3.5 min（5 workers）。**结论：8 个配置全部 −98%~−100%，门控占空一次都没变好 ⇒ D-54 否定** |
| `r155_fs_envelope.py` | **进料可行域厚度（动手前的前置检查）**：`kp=ki=0, u_lo=u_hi=u` ⇒ 纯静态缩放无反馈，扫 u 看多少批破 ±5%、pH 是否越 7 | 12 批 × 6 档约 12 min（6 workers）。**R155 结论：只有 u=1.00 时 12 批全过；±1% 各 5 批破线（最差 −30.1% / −100%）⇒ 域宽 < ±1% 且逐批单侧**；**R156 加 `--ph-fix 1` 与 `--mup-map`（逐批重标倍率）**：修 pH 后钳位全消但域宽未变宽，重标后减料侧扩约 4 倍（4/5 批可承受 ±2%），加料侧仍被 b22 双稳态卡死 |
| `r155_fb_limit.py` | **D-41 L1 装置**（`params.fb_limit`）：pH ≥ ph_stop 停碱（step）或按 (ph_stop−pH)/width 线性回撤；带 `off`（ph_stop=15）零效应控制臂 | 12 批 × 3 臂约 6 min。**结论：`off` 臂 max|Δ|=0；step690 钳位 5→5、越 7 9→8，但 b43 −44.42%、b54 −34.62%、b37 +67.99% ⇒ 与 D-36 同型，只缓解不解决** |
| `r155_pcollapse.py` | **崩塌性质判别**：模型 P 末/峰 vs **实测** P 末/峰，判「模型病」还是「过程真实」（避免绝对阈值误判） | 16 批约 12 min。**结论：实测末/峰本身 0.375–0.826；绝对阈值 0.5 会判 12 批；相对口径 `sim/meas<0.6` 判出 4 批 b37/b50/b51/b91，4/4 全是 pH 钳位批** |
| `r156_ph_probe.py` | **D-55 病灶定位（公式层）**：包一层 `simulate.rhs` 记录器，逐点抓 `dy[6]`，按 pH 分箱统计 `dy6/H⁺`、`dy6<0` 占比、`|dy6|/OH⁻` | 2 批约 3 min。**结论：pH>7.6 时 `|dy6|/OH⁻ = 0.994`**（状态是 H⁺、驱动项却是 OH⁻ 口径）；pH 6.99–7.05 已有 95% 的 `dy6<0`；pH 7.00→9.57 用时 1.07 h （理论 t* = 0.497 h） |
| `r156_recal.py` | **逐批 `mup` 重标**：扫倍率求「把产量打到 0」所需倍率 + 弹性（pp per unit mult） | 5 批 × 6 档约 12 min。**结论：所需倍率中位 0.868、范围 0.834–0.946；弹性跨批差 3.4 倍**（R154 在钳位世界里差 3 个量级）⇒ D-52 大幅缓解；b37 在 0.84→0.85 之间跃迁（P 峰 12.65→30.20） |
| `r156_regress86.py` | **86 批回归**：与冻结基线 `runs/r151_shape_baseline.json` 逐批比 `max|Δ|`，支持 `--ph-fix` 与 `--mup-map`（逐批倍率） | 86 批约 13 min（8 workers）。**结论：`ph_fix=1` 下 **77/86 批 `max|Δ| = 0`**，变的正好是 9 批越 7 批；重标后产量 86/86、catastrophic 4→0、P relRMSE max 0.8482→0.4303** |
| `r156_pdecay.py` | **产量崩塌的轨迹级归因**：P 是「峰没起来」还是「峰后掉光」，并对照实测 P 剖面 | 单批约 1 min。用于区分水解型崩塌与产素型崩塌 |
| `r151_shape_accept.py` | 86 批**形状基线** + **判据单一来源**（模块级 `GATE`）：P/S 的时间对齐 relRMSE、R²、峰比/末比/峰时差、四相位相对残差、`validity()`、crash 分级 | 86 批约 9–12 min（7 workers），`--limit N` 冒烟。**按 `time_h` 对齐**，与 `r150_p_shape.py` 逐批 **`max\|Δ\|=0.000e+00`**（86 批 × 5 类指标含 344 个相位值） |
| `acceptance.py` | **验收单入口**：HARD G1 产量 86/86 / G2 新发 catastrophic=0 / G2b degraded≤9 / G3 确定性 `max\|Δ\|=0`；SOFT 6 条形状判据 | `--reuse runs/r156_acceptance.json` 跳过 86 批仿真（判据本地重算，仍跑 G3），**<5 s**；正式回合须跑全量；**R157：`--reuse` 到无 health 字段的 json 时 G2/G2b 判跳过**（显式 WARN + `exit 2`，不许报 PASS）；**R156 加 `--candidate-v2`**（候选基线 v2：pH 链式法则修正 + 5 批 `mup` 重标，opt-in） |

### R157（验收层收口：把「恒真判据」与「约定」变成机器可验）

| 工具 | 用途 | 备注 |
|---|---|---|
| `r157_golden_hash.py` | **黄金集 hash 快照**：对 `data/processed/batches/` 的 100 个 `batch_XX.csv` + `golden_set.json` 取 sha256，落 `data/processed/golden_set.sha256`；`--check` 报「修改 / 删除 / 新增 / 名单变化」四类差异 | 秒级。**用途：把 GOAL「黄金集只增不减」从约定变成机器可验凭证**。新增 CSV 允许（只增不减），修改/删除/改名单 ⇒ `exit 1` |
| `r157_validity.py` | **D-56 验证**：`validity()` 越域判据的**分布报告**（`n_steps`/`n_ph_over7`/`over7_frac`/`ph_max_pre` 的分位数与逐批表）+ 新旧判据前后对照；给出「默认基线 valid 77→81（残余 5 批全是**真钳位**）/ 候选 v2 77→**86**」 | 86 批 × 2 基线。**D-44 教训：必须报分布不能只报计数** |
| `r157_bistab_knob.py` | **D-57 连续旋钮搜索**：在 b22 上扫 `sd`/`meanP`/`kdeg`/`muhs`/`Ysp`；**两阶段判据**（粗扫 9 档 → 二分 12 次逼窄跳变区间 → 区间内 16 点密采样）⇒ 能区分「陡但连续」与「真阶跃」 | **v4（D-69 修正版，现行）**：二分更新为「**锚点夹逼**」（锚点 = 粗扫两端响应，固定不移动；中点按**最近锚点**分类 ⇒ 不变量「区间始终含跳变两侧」⇒ 收敛到**跳变位置本身**）；新增 **`--dense-coarse`** 在粗区间**直接密扫**（单调光滑响应不能用二分，二分会收敛到「响应取中值处」）；新增 **`ERRATIC`** 第三判定分支（密采样相邻差分**变号 ≥3 次** ⇒ 非单调震荡 ⇒ 混沌窗，既非阶跃也非可走连续段）；新增 **`--base-override "k=v"`**（把系统推进到崩塌态后扫旋钮，用于判决「崩塌态是否吸引子」）。**v2 弃用**（响应中点界：对单调光滑函数收敛到响应中值处 ⇒ 假收缩）。**v1/v2 结果留证** `runs/r157_bistab_knob_v1_bisectbug.json` / `_v2_midpoint_bisect.json`。旋钮：`Ysp`=环路增益直旋钮；`muhs` 用 par[18]（par[19] 在 inhib_flag=2 分支被 `k4·par[18]` 覆盖 ⇒ 无效） |
| `r157_i3_channels.py` | **T3-1 I3 多通道**：X / P / PAA / vis / S / DO2 统一用 R139 已验证的结构化观测器 + 批级 5 折 CV，报 A 档 nRMSE、CV nRMSE、I3 90% 区间与覆盖率 | **三道硬门**：① 优于 A 档 ② CI 半宽 ≤25% ③ CI 半宽 < A 档误差（覆盖率单独看是**可平凡满足**的 ⇒ D-38 同型陷阱）。X 通道为回归检查（须复现 nRMSE 3.17% / 覆盖 0.8992） |
| `r157_fault_modes.py` | **T3-2 模式级故障注入**（须用 `--ph-fix 1`，见 D-68）：模式库（`kla_step`/`kla_ramp`/`kla_fade`/`ph_drift`/`feed_hold` + 传感器侧 `sensor_bias`/`probe_freeze`）；每模式带**预期特征签名**，工具自动校验方向是否符物理预期 | 引擎侧用新增 opt-in `fault_profile` 时间包络（默认 None ⇒ 与 R127 逐位一致）；传感器侧只污染观测通道副本，不动动力学，并额外校验「**动力学逐位不变**」+「偏置/冻结确实生效」（OUR 末值比 =1.25、冻结后 DO2 标准差 =0）。R143 纪律：算子只用于**没录进输入**的故障 |
| `r157_state_update.py` / `r157_contract_update.py` / `r157_contract_update2.py` / `r157_state_update2.py` / `r157_state_update3.py` / `r157_contract_update3.py` | 一次性迁移脚本（state.yaml 六区块 + 契约 v1.85 行 + 契约 **v1.86 行** + 契约 **v1.87 行** + state.yaml 的 `artifacts`/`open_questions` 补充登记 + **D-57 定案 / D-56 关闭回填**）；锚点断言保证幂等 | state.yaml 与契约均为纯 CRLF ⇒ 全部锚点按 CRLF 处理。**v1.86** 记录签核单之后的三项事实变更（D-56 关闭 / T3-1 I3 多通道 / T3-2 `fault_profile` 引擎接线），**v1.87** 记录 **D-57 定案**（判据四版演进 + 崩塌态逃逸判决实验 + D-54 分层封死 + D-42 转已知边界），**均不改写 v1.85 的历史记录**。**行级定位**（不靠字符串偏移）⇒ 区块在文件中间或末尾都能处理；`artifacts` 恰在文件末尾。**update3** 额外做 **plain scalar 安全字符校验**（禁半角逗号 / 方括号 / 花括号 / 半角冒号+空格 / 半角 #）—— 这正是 `state.yaml` 用 YAML flow sequence 存 `cap.reasons` 时的老坑；幂等指示区分 `[skip]`（已是目标文本）与 `[notfound]`（锚点已消失）。**contract_update3** 另加 **markdown 表格行裸竖线校验**（`\|` 会破坏表格列结构） |
| `r157_bistab_escape_patch.py` | 一次性补丁脚本：给 `r157_bistab_knob.py` 打 `--base-override` 锚点（`_bisect` 签名 / `_dense_scan` / jobs 构造 / refine 密采样等 8 处 REPL 列表，**全部命中才写盘**）+ AST 校验 | **存在的理由**：bash `-c` 内联 Python 改源码时**反引号会被 shell 展开**（内容被吞、中文变乱码）⇒ 一律「Write 落 .py 脚本 → 再执行」。后续 `--base-override` 路径还需补 `_bisect` 的 `extra` 形参与调用点透传（该补丁脚本只打锚点，不做签名改造） |
| `r157_escape_json_meta.py` | 给已产出的 `runs/r157_bistab_escape.json` 补写 `base_override` 元数据（值从该次运行日志首行 `[base-override]` 回读，可审计） | **元数据缺失是可复核性缺陷**：崩塌态逃逸实验的 json 若不记 `base_override`，复核者无法从文件本身判断它是基线态还是崩塌态跑的（两条判读结论完全不同）⇒ **工具已修**（json dump 增加该字段），本脚本只补历史产物；幂等 |

### R158（T3-3：Raman / PAA-PLS 大规模接线 + 消融 —— 结论为否定式）

| 工具 | 用途 | 备注 |
|---|---|---|
| `r158_raman_unit_probe.py` | **量纲与保真度口径核证**：用 V6 `.mat` 的 **Batch_01 真实存储谱**（非合成谱，不含合成层偏差）做 OLS ⇒ 定出 `predict_paa()` 的真实单位；再在全池统计引擎 PAA vs 化验 PAA 的量纲比；并把「**缩放不变性演示**」（pat × 1000 后 r 逐位不变）内建为常驻回归 | **本轮挖出的核心缺陷**：PLS 资产输出 **0–2.11** vs 化验 **430–2023 mg/L** ⇒ **差 ~1000 倍**；OLS `lab(mg/L) = 721.263 × pred + 404.644`（r=0.8463）⇒ **D-70**。**相关系数对缩放不变 ⇒ R120 的三重验证（0.9995/0.9997/0.8463）全都看不出量纲错**。同时修两处：① `platform/.cache` 的 `off[ch]` 是 **`[[t,v],...]` 点对列表**（误读为标量数组会让量纲统计失真）；② V6 `.mat` 的 `mat_struct` 取值路径不一致需双路 fallback |
| `r158_pat_ablation_scale.py` | **T3-3 主体**：全池 **86 批**接线 + **5 口径消融 + 3 控制组 + 1 平凡上界 + 增量信息检验 + 分层符号检验**。口径：A 引擎直报 / **A2** 引擎+两点校准（LOOA 仿射，**完全不用 PAT**）/ B PAT 转发 / C PAT+锚定（**LOOA**）/ **C0** 引擎+锚定（LOOA）/ **C1** 直接插值化验值（平凡上界） | **四道硬门**（前三条沿用 D-63，**门④新增**）：① 优于 A 档 ② CI 半宽 ≤25% ③ CI 半宽 < A 档误差 ④ **独立信息**：控制引擎 PAA 后 PAT 的增量 R² 与 **t 检验**（\|t\|≥2 批次占比 ≥5%）。**三个关键防陷阱**：① **LOOA** 替代「锚点处覆盖率」（锚定层按构造贴化验 ⇒ 覆盖率**恒真**，D-38 形态）；② **C0 对照**（判定 C 的收益是否只来自「用了化验锚点」）；③ **A2 对照**（判定 B 的收益是否只来自两点校准）。**结论**：PAT **无独立信息**（增量 R² 0.0199 / t 0.104）⇒ 不引入交付（D-71）；锚定层**方向错误**（锚 PAT 劣于锚引擎 PAA，失真批 41/41、p=9.1e−13）⇒ D-72。**分层**是核心发现：失真批上 PAT 优于引擎直报 **38/41（p=1.05e−08）**，但被 A2（中位 0.49%）**严格支配**。全池 6.5 s |
| `r158_state_contract_update.py` | 一次性迁移脚本：登记 R158 事实到 `state.yaml`（`open_questions` +3 条 D-70/71/72、`artifacts` +2 条）与契约 **v1.88** 行；锚点断言保证幂等 | **本轮踩到的三个坑都在这里**：① **必须二进制读文件** —— 文本模式的 universal newlines 会把 `\r\n` 转成 `\n`，`split('\r\n')` 退化成「整文件一行」⇒ 定位全部失效；② **`- **D-70...` 不能以 `*` 开头** —— YAML 会当**别名锚点**解析并报错 ⇒ open_questions 元素必须是纯文本开头；③ **契约版本表是 3 列** ⇒ 行内竖线数必须**恰好 3**（表头/列分隔/表尾），多于 3 个会劈出额外列。**写盘后立即 `yaml.safe_load` 验证**（这是发现②的唯一手段） |



> 引擎侧新增 `simulate.shape_metrics(sim, v3, channels=("P","S"))`，与 `yield_metrics()` / `trajectory_metrics()` **并列不替换**；
> `print_report(shape=True)` 与 CLI `--shape` 均**默认关闭**。
> 结论：P relRMSE 中位 **0.1557**、峰比 **1.060**、末比 **1.021**（峰/末已对）⇒ 缺的是**中段**
> （60–120 中位 **−0.092**）；剔掉 9 批 invalid 后缺口**更深**（−0.071）⇒ 结构性、与 pH 越界无关。
> **「0 catastrophic」在 86 批上恒真**（全走 `classify_crash` 早退），已补 `invalid ≤ 9` 替代（D-38）。

### R159（A2 证伪位检验 —— **撤回 R158 的「唯一正面结论」**）

| 工具 | 用途 | 备注 |
|---|---|---|
| `r159_a2_falsification.py` | **五道证伪门 + 化验退化筛查 + 有效口径重判 + R158 交叉影响**：G1 化验信号退化度 / G2 **常数预测基线**（控制组）/ G3 A2 斜率可辨识性 / G4 **时间因果**（前推式，只用过去锚点）/ G5 在线可得性；再加**剔除退化批后的三层重判**（有信息 / 退化 / 真·失真）与 **R158 结论逐条交叉复核** | 86 批（`GOLDEN_ALL`，与 R158 同口径，复算关键量**逐位一致**），约 4 s。**判决 A2_RETRACTED**：① 失真批 41 批中 **29 批化验退化**（V6 批 61–90 的 `PAA_offline` 钉在 ~1200 mg/L）⇒ A2 **退化为常数预测**（斜率中位 **0.0010**、预测动态范围 **0.072%**），**连常数基线都打不过**（37/41 更差，p=1.03e−07）；② **剔除后 A2 20.47% 劣于 C0 10.29%**（50/57，p=4.24e−09），方向反转；③ 真·失真批（n=12）上 A2 30.48% 劣于常数基线 28.64%。**D-71 加固**（增量 R² 0.0199→**0.0092**、t 0.104→**0.036**），D-72/D-70 维持。**判据内建**：`lab_cv_pct < 2%` ⇒ 退化批 |
| `r159_governance_update.py` | 一次性迁移脚本：登记 R159 事实到台账（**D-73 / D-74** + 修订 D-71 的关键否证行）、签核单（**B-13 / B-14 / R-9** + 两条禁止表述 + 修订 B-10）、路线图 T3-3 行、`state.yaml`（oq +2 / artifacts +1）与契约 **v1.89**；锚点断言保证幂等 | **本轮踩到的两个坑**：① **换行风格按文件分** —— `docs/*.md` 是 **LF**，而 `state.yaml` / `ENGINE_CONTRACT.md` 是 **CRLF** ⇒ 不能用同一个读写器硬套；② **`artifacts` 是 `key: value` 映射**（`: ` 合法），而 `open_questions` 是 **plain scalar** ⇒ **安全字符检查必须分块**，否则合法条目被误杀 |

### R160（第三次全面回溯 + **D-78 判据恒真证伪**）

| 工具 | 用途 | 备注 |
|---|---|---|
| `r160_i3_coverage_tautology.py` | **I3 覆盖率恒真性证伪**：① **零信息预测器对照**（把 B 档预测换成该批化验的常数）② 跨通道逐位对照 ③ 逐批口径判别力 ④ **μ ± 1.96σ 替代口径**检验。**直接 import `r157_i3_channels.py` 并复用其 `load/_fit/_predict/_nrmse`** ⇒ 口径逐位可比 | 判决 **TAUTOLOGICAL**：**零信息常数预测器与正常预测器的覆盖率逐位相同**（X/P/PAA/vis 四通道均 **0.899549**，Δ=**0.000000**）⇒ 该数字**无判别力**；逐批口径同样无判别力（Δ≤0.0078）；**±1.96σ 口径有判别力**（垃圾 0.0000 vs 正常 0.1072/0.3160）⇒ 处置方案确定。**判决层不受影响**（T3-1 三道硬门不依赖 coverage），**论证层须撤回** |
| `r160_governance_update.py` | 一次性迁移脚本：登记 R160 事实到台账（**D-75 / D-76 / D-77 / D-78** + 纪律第 15–18 条）、签核单（**B-15 / B-16 / B-17 / R-10** + 修订 B-3 的 coverage 口径）、路线图 §八、契约 **v1.90**（含头部 v1.82→v1.90 同步）、`state.yaml`（oq +4 / artifacts +2）、README（修 D-76/D-77 + 补 D-78 已知边界） | **本轮踩到的三个坑**：① **幂等检查必须逐条** —— 只看 `D-75` 一行时，若后续步骤抛异常则已写入的部分无法被识别 ⇒ 台账被插入 3 份（用 `tools/_legacy/_r160_ledger_dedup.py` 去重）；② **markdown 表格的列数**按文件而异（签核单边界表 **5 列**、决策表 **3 列**、契约版本表 **2 列**）⇒ 校验函数须带 `ncol` 参数；③ **YAML plain scalar 的 `#` 检查**会误伤 `oq#6` 这类文本 ⇒ 措辞须避开 `#` |

### R150（P/产量通道可行性判定，**零引擎改动** —— `simulate.py`/`model.py` 未改一行）

| 工具 | 用途 | 备注 |
|---|---|---|
| `r150_p_shape.py` | 86 批 P 通道误差结构：峰/峰时/末值/降幅（模型与实测并列）、**分相位相对残差**（以实测峰归一）、产量误差、`validity()` | 86 批约 11 min（6 workers）；`--all-100` 跑全 100 批。**按 `time_h` 对齐**（不按行号：`sim` 0.4 h 起、`v3` 0.2 h 起，差一格），故与 `trajectory_metrics()` 有微小差异（b55 0.2673→0.2659） |
| `r150_ident.py` | `mu_p`/`mu_h`/`k_deg` 可辨识性：`--stage svd`（三列统一换算成"等价 `mu_h` 变化 5%"的 Jacobian + SVD）与 `--stage swap`（`mu_h` 降 ε vs `k_deg` 补等量的置换检验） | 6 批约 4 min。**含硬断言：任一方向轨迹差为 0 即抛异常**（防"参数没生效"被误读成"不可辨识"，R147 踩过）。`mu_p` 走 `dist_mup`（加性），`mu_h` 走 `mu_h_scale`→`par[18]` |
| `r150_phase_probe.py` | 6 通道（P/S/X/PAA/DO2/OUR）**分相位**残差，用于排除"另一个通道在同一相位也偏" | 6 批约 1 min。S 在 0–60 h 的相对残差会爆（分母趋 0），不是真实误差 |

> 结论：**产量指标对 P 轨迹完全失明** —— 产量 **86/86** 在 ±5%（中位 −0.07%），同期 P relRMSE
> **中位 15.6% / max 84.8%**，相关 **+0.011**；P 误差 >0.20 的 **21 批产量全部达标**（b50 峰高 79%、末低 37%、产量 −0.26%）。
> **`k_deg` 不可辨识**：列范数只有 `mu_h` 的 1/4–1/45，置换检验 A/B 中位 **10.16×**、抵消比 **0.937**；
> 结构上 `dP/dt = 产素项 − (mu_h+k_deg+D)·P`，二者只以和出现。
> **唯一主体缺口是 60–120 h 低 22%**：同相位 S **+0.4%**、PAA **+33%**、X **+11%**、A1/X 差 4–5%
> ⇒ 排除糖/前体/生物量/形态，指向 `r_p` 产素项本身（`rho_a0` 在 `v_a1` 里完全抵消）。

### R149（pH 通道可行性判定，**只读 + 1 个 opt-in 参数覆盖 `abc`**）

| 工具 | 用途 | 备注 |
|---|---|---|
| `r149_ph_shape.py` | pH **相位/振幅归因**：对 `--knob {gamma1,gamma2,m_ph,abc}` 扫标度，逐批报峰/谷/振幅/**分相位残差**（0–60/60–120/120–180/180+）/ `validity()` / 产率 | 单批约 21 s；5 批 × 5 档约 3.5 min（6 workers）。**含口径闸门：`s=1.0` 必须与冻结基准逐批 `max\|Δyield\|=0`** |
| `r149_ph_band.py` | 统计实测 pH 的**控制带**（批内 std / 极差 / `\|pH−6.50\|≤0.05` 占比），全 100 批 | **只读数据、不跑仿真**，约 3 s |
| `r149_biomass_probe.py` | 模型 `X` 与实测 `X_offline` 在 6 个时刻点对齐，检验"中段 pH 偏低是不是生物量高估导致 `m_ph·X` 多产酸" | 6 批约 2 min。**结论：不是**——b36 在 t=140 的 X 只高 12%，而 pH 低 1.13 ⇒ 生物量假设不足，保留作反例 |

> 结论：**pH 不能作标定目标**。实测 pH 是控制设定量（批内 std 中位 **0.0247**、95.2% 样点在 6.50±0.05）；
> `γ1`/`m_ph`/`abc` 三系数**全是一阶平移**、无振幅旋钮；`γ1` 悬崖在 **0.985**（b22 `s=0.99` 产率 −0.07%、`s=0.98` **−100%**），
> 且 b22 **单批自相矛盾**（归零自身中段残差需 ×0.898，而 ×0.98 已崩）。
> 踩坑三例：①`build_params()` **不含** `gamma1/gamma2/m_ph/abc`（它们在 `make_params()` 的 62/63/64/61），
> 按批 dict 取会拿到 `None`；②`amp_ratio`（模型峰谷差 / 实测峰谷差）是**伪指标**——实测极小点在 17–25 h、
> 模型极小点在 90–174 h，且分母是控制带；③全局 `min/max` 不能替代分相位残差；
> 崩溃签名是**全部相位 ≈ −3.4~−3.5**（= 3.0 − 6.50），可直接当钳位检测器。

### R148（D-34 落地：有效性判据 + 守卫审计，**引擎 4 处旁路改动，默认逐位不变**）

| 工具 | 用途 | 备注 |
|---|---|---|
| `r148_validity_gate.py` | 全 86 批跑 `validity()`，逐批报 `valid` / `pH_pre max` / 钳位步 / 越 7 步 / pH≈3 样点 / 产率；汇总"全部 vs 仅 valid vs 仅 invalid"三组 RMSE 与 ±5% | 约 18 min（8 workers）；**含口径闸门：批集取 `final_validation_v2.json` 的 86 批，不是 `sorted(COMBINED)` 的 88 批** |

> 判据：`pH_H` 从未被守卫改写 **且** 守卫**前** pH 从未 ≥ 7.0。结果 **77 valid / 9 invalid**
> （invalid = b37/40/43/49/50/51/54/91/92，分 `clamp` 5 批 / `over7` 4 批）。
> **不要用误差筛 invalid 批**——9 批全部在 ±5% 内（max 4.12%），且 `clamp` 组 RMSE 1.978% 反而低于 valid 组 2.303%。
> 踩坑三例：①`_tgt = _guard_tally` 别名导致计数翻倍（靠 `tally["pH_H"] == ph_nonpos_steps` 恒等式抓到）；
> ②`sorted(COMBINED)` 是 88 批，验收集是 86 批（多 b99/b100）；③零初值在首步必然触发守卫，
> `A3/A4/n0..nm/phi0` 每批各 1 次，不扣除会让 `suspect` 命中 88/88 批。

### R147（D-36 算子层：`r_p` 口径三态，**改引擎 1 处 opt-in，默认不变**）

| 工具 | 用途 | 备注 |
|---|---|---|
| `r147_d36_rp_mode.py` | 15 批（5 钳位批 ∪ 12 黄金批，去重）× 3 口径（`net`/`prod_only`/`all_acid`）对比：产率、pH min/max/末、钳位样点、≥7 样点、P 末/峰 | 约 5 min；**含口径闸门：`net` 必须与冻结基准逐批 max\|Δ\|=0** |

> θ 经 `params["ph_rp_mode"]` 注入（`rhs` 内 `_adj = 0/1/2`），只改 `dy[6]` 不改 `dy[3]`。
> **三条口径全部证伪**，不要再用它做"修 pH"的尝试（黄金批 12/12 → 5/12 → 3/12）。
> 踩坑：新增贯穿三层的参数时，`grep` 命中数齐全 ≠ 参数到位；**必须跑一条已知会改变结果的臂验证**——
> 首版漏了 `integrate_interval(...)` 调用点，三口径跑出**完全相同**的数字。

### R146（D-35 可辨识性 / 可修正性判定，**只读 + 3 个 opt-in 参数覆盖**）

| 工具 | 用途 | 备注 |
|---|---|---|
| `r146_ph_ident.py` | `--stage base` 出 12 批 pH 基线诊断（偏差/漂移/钳位/≥7/包络）；`sens` 出干净批灵敏度、逐批条件数、GN 一步；`g1` 扫逐批 γ1 标度 | base 约 3 min；**含口径闸门：基线须与冻结基准逐批 max\|Δ\|=0** |
| `r146_ph_linesearch.py` | 复用已存 d1 做阻尼线搜索（λ 扫描），报 RMSE/偏差/钳位/≥7/maxpH/偏差跨度 | 10 批×7 λ 约 14 min；**λ=0.25 即崩（b22 越 7）**，不必重算灵敏度 |

> 两个工具都**不改引擎**：θ 只经 `params["gamma1"/"gamma2"/"m_ph"]` 覆盖注入（`par[62]/[63]/[64]`）。
> 踩坑：`final_validation_v2.json` 的 `params` 字段缺 `build_params` 注入的 `dist_flag=1`，
> 必须走 `golden_params.params_for(b)`，否则整条结论落在另一个工况上。

### R145（D-32 机制定位 + 两条修复证伪，**只读 + 2 条反事实臂**）

| 工具 | 用途 | 备注 |
|---|---|---|
| `r145_d32_terms.py` | pH 方程逐项预算：包裹 `integrate_interval` 取 `(t0,y0,inp1,par)`，自算 buffer/稀释项反解产酸项 | ~70 s/批；**自检必须用有限差分**（残差式自检是同义反复） |
| `r145_d32_scan.py` | 86 批扫描：产酸源符号、`P_inhib` 门控、pH 越域、钳位 | `--all --workers 8` 约 12 min；**30 批产酸转负 / 25 批门控归零 / 9 批越 7 / 5 批被钳** |
| `r145_d32_hydacid.py` | 反事实臂 1：`ph_hyd_acid=True`（水解按产酸翻正） | 约 14 min；**证伪**：pH 末 5.0–5.3、46 批破线 |
| `r145_d32_phmode.py` | 反事实臂 2：`ph_mode="measured"`（pH 按实测回放） | 约 14 min；**证伪**：5 批 +28…+125 pt、24/86 越 ±5% |

### R144（D-30 机制定位，**只读 + 每批 1 次仿真**）

| 工具 | 用途 | 备注 |
|---|---|---|
| `r144_d30_probe.py` | 包裹 `simulate.guards`，逐步记录采样末的 `y[6]` pre/post | 秒级；**一次跑出 `pH=3.000` 是 `0.001` 钳位值** |
| `r144_d30_sweep.py` | 全批扫描：哪些批、被钳哪个状态索引、首次触发时刻 | ~41 min / 88 批（并发下）；**86 批内 5 批撞 `[H+]`** |
| `r144_d30_chaos.py` | 混沌检验：输入 ×`(1+1e-6·U)`，固定种子重复，统计 yield 极差 | `--merge` 可分批跑并合并；**b37 极差 70.96 pt** |
### R143（D-9 故障幅值命题撤销，**只读 + 3 次/批仿真**）

| 工具 | 用途 | 备注 |
|---|---|---|
| `r143_d9_scale.py` | 量纲取证：从数据反解 `d[H+]/dt`，换算算子等价 mag；自动检出 pH 事件窗 | 秒级；**一次跑出"旧扫描放大 2.4e4 倍"** |
| `r143_d9_mechanism.py` | 三臂（基线 / Fb 反事实 / 旧口径 mag=100）+ mag 剂量响应 12 点 | ~4 min；反事实臂用 monkeypatch `simulate.load_batch`，不改引擎 |
| `r143_d9_tail.py` | 尾段崩落性质：跨求解器 BDF@1e-3 / BDF@1e-6 / Radau@1e-8 | ~2 min；**Radau 在 t=217.4 直接失败**，即证为数值奇异 |
| `r143_d9_b98.py` | 交叉验证：b98（NORMAL，非故障批）基线 vs Fb 反事实两臂 | ~40 s；窗内 RMSE **0.170** ⇒ 同一签名可重复 |

### R142（D-2 DL σ̂ 定标，**全部只读、不跑仿真**）

| 工具 | 用途 | 备注 |
|---|---|---|
| `r142_d2_diagnose.py` | Part A：温度诊断 —— ESS、`var_w`/网格满铺比、`var_b`、DL gap | 秒级；读出 **ESS=46.8/48** 即证后验≡无信息先验 |
| `r142_d2_snr2.py` | Part B2：可加模型 `L=μ+a+b+c+ε` 方差分解，SNR 与残差 SD | 取代 `r142_d2_snr.py`（首版把其他参数主效应算进噪声） |
| `r142_d2_quant.py` | Part C：网格量化下限 `d²/12` + **COMBINED vs 生成机制真值** | 给出 8.3×/4.0×/∞ 膨胀；真值取自 MATLAB 源码，勿凭记忆填 |
| `r142_d2_tsweep.py` | Part D：温度敏感性 `T∈[1e-3,1]`，定位 σ_pop 转正窗口与 ESS | 结论：非零区 ESS≈1–2，属伪精度 |
| `r142_d2_snr.py` | ⚠️ **反例保留**：首版"组内散布"混入了其他参数的真实主效应，系统性低估 SNR（mux 0.32 vs 修正后 0.76） | 不作为结论引用 |

### R141（D-8 形态学衰亡链）

| 工具 | 用途 | 备注 |
|---|---|---|
| `r141_death_mode.py` | 两条臂对照：`prop`（`late_death_rate += δ`）vs `morph`（`death_mode=1` 老化+溶菌），报告 ΔX/ΔP/Δyield/debris | 默认 10 批 × 7 配置 ≈ 6 min；`--all86` 约 90 min |
| `r141_analyse.py` | Part A 前沿（ΔX≥5pt 的产量代价）+ Part B 退化极限（age 固定、lysis 0.01→1.0） | 读上一步的 JSON；结论见 `docs/r141_round_report.md` §4–5 |

### R139（双通道观测器，**当前交付版本**）

| 工具 | 用途 |
|---|---|
| **`r139_observer_v2.py`** | **B 档 X 轨迹交付件**：`log(X_est/X_model)=p·mean(log r_OUR)+q·(log r_CER−mean)`，含 5 折 CV、I3 区间、门控。`--all86 --cv` |
| `r139_dual_channel.py` | 双通道裁决：`r_CER` vs `r_OUR` 的 log-log 斜率、批内去均值回归、α 扫描 |
| `r139_ratio_gate.py` | 门控判据评估 + **冻结校正反事实**（证明 J5 不可用） |

### R138（碳平衡 / OUR 观测器 v1）

| 工具 | 用途 | 状态 |
|---|---|---|
| `r138_our_observer.py` | OUR 单通道观测器 v1（α=0.60） | **已被 v2 取代**，仅留证据链 |
| `r138_carbon_observer.py` | 碳平衡反演 X | 失败（X 仅占碳通量 14%） |
| `r138_our_softsensor.py` | `qO2=OUR/X` 形状先验软测量 + LOBO | 失败（可观测性地板 15.6%） |

### R136–R137（X 通道归因）

| 工具 | 用途 |
|---|---|
| `r136_x_s_channel.py` | X 误差结构分解（分段比值）+ S 通道独立评估 + OUR/X 自洽 |
| `r136_xaxis_probe.py` | 五类杠杆反事实（72 配置），证明 X 幅度在参数域内不可修复 |
| `r136_ldr_calibrate.py` | LDR 标度校准 | **前提已证伪，勿运行**（文件头有警告） |
| `r137_morphology_probe.py` | 形态学链路探针（`key*` 乘数语义），证明 `k_vac` 未接线 |

### R130–R135（引擎与通道基础）

| 工具 | 用途 |
|---|---|
| `r131_harness.py` | 批量仿真骨架（并行、参数扫描） |
| `r131_mup_robust.py` | `mup` 窄窗稳健性 |
| `r131_xoff_mechanism.py` | X_offline 与模型偏差的机制 |
| `r132_calib_merge_check.py` | 双参数表（CAL vs COMBINED）合并核验 |
| `r132_channel_classifier.py` | 通道三类判侧（generation / scale_only / measurement） |
| `r132_vis_scale_cal.py` / `r133_vis_*.py` | 黏度输出标度解耦与形状核验 |
| `r134_bifurcation.py` | b27/b92 分岔真伪（四求解器配置扫描） |
| `r134_paa_attrib.py` | PAA_offline 幅度-波形分解判侧 |
| `r134_our_subordinate.py` | OUR 从属验证（`corr(k_OUR,k_X)=0.854`） |
| `r135_do2_attrib.py` / `r135_b55_b91_attrib.py` | DO2 归因、b55/b91 异常批归因 |
| `d6_health_view.py` | 健康度视图（平台消费） |

## 3. 测试

`test_*.py` 共 11 个（pytest），覆盖 MCP 客户端/HTTP、runstore、软测量守卫、看板操作、趋势数据。
`smoke_*.py` 3 个为 G4 闸门冒烟（gate / gate16 / gate60）。

```bash
python -m pytest tools/ -q
```

## 4. 历史归档（可查，勿作新工作起点）

| 前缀 | 数量 | 内容 | 处置建议 |
|---|---|---|---|
| `d9_*` | **127** | 早期非黄金集校准迭代（`d9_nongolden_calibration1..19` 等） | 已被 `golden_params` + R131+ 取代，可整体移入 `_legacy/` |
| `diag_*` | **109** | 各轮诊断快照（多为一次性） | 保留最近 3 轮，其余可归档 |
| `r130*` | 15 | R130 系列（`k_vac` 扫描、晚期衰亡、Y_sX 校准） | 结论已被 R137 覆盖，留档 |
| 其他 | ~112 | 杂项脚本（`audit_bc`、`append_ledger` 等） | 逐个判定，多数可归档 |

> 归档不等于删除。移入 `tools/_legacy/` 后仍可 `git log`/检索，只是不再出现在默认列表里。

## 5. `tools/_legacy/`

已归档的一次性脚本（2026-11-04 清理）：

| 类别 | 文件 |
|---|---|
| 根目录调试残留 | `check_paa.py`、`check_sim_p.py`、`check_v3_cols.py`、`check_v3_s.py`、`debug_biomass.py`、`debug_inhib2.py`、`debug_traj.py` |
| 一次性补丁 | `_add_paa_overrides.py`、`_patch_b55b91.py`、`_q_investigate.py`、`_update_d6_combined.py`、`_jscheck.js`、`_jscheck_info.js` |
| 已废弃绕行 | `download_scipy.py`、`vendor_manifest.txt`（原 `tools/vendor/` 137 MB 的清单，**目录本体已删**） |

> 注：`check_*` / `debug_*` 里有几个仍在 `sys.path` 里插了已删除的 `tools/vendor`，若需复跑要先删那一行。

**注意**：`tools/vendor/` 内是 scipy **1.14.1 的 cp312 wheel**，与当前 CPython 3.10 解释器错配，
且版本与零回归基线不符。正式环境用 `requirements.txt` 里的 **scipy 1.15.3**，不要再恢复 vendor。

### R161（B 档回退链算子层，D-75 部分关闭）

| 工具 | 用途 | 备注 |
|---|---|---|
| `r161_fallback_chain_probe.py` | 回退链四环算子的**证伪式**探针：T1/T2/T3 健康度判据真假阳性（含两条假阳性回归）、T4 显式失败语义、T5 MHE 双向可证伪、T6 稳态基线 C 平衡判据、T7 opt-in 零回归、真实批 EnKF 探针 + 稳态基线 C 平衡普查 | `--skip-real` 只跑合成判据（秒级）；全量含真实批 EnKF 约 **30 min**。结论见 `docs/r161_round_report.md` |
| `r161_governance_update.py` | 治理层更新（台账 / 签核单 / 路线图 / 契约 / state / README / 工具索引 / 工作记忆） | **幂等**（逐条检查后写入，重复执行不产生重复条目） |

### R162（M1 尾账收口，oq#36/37/38）

| 工具 | 用途 | 备注 |
|---|---|---|
| `r162_m1_legacy_probe.py` | oq#38 终末收获口径 + oq#36 MATLAB rng 映射的**证伪式**探针：P1 逐位同构 / 符号自洽 / 零信息对照 / 反向验证 + 100 批放罐段普查；P2 四层映射对照（算法 / 播种 / 变换 / 种子基准） | 秒级。结论见 `docs/r162_round_report.md` |
| `r162_kla_sensitivity.py` | oq#37 alpha_kla 批次级随机性量化：12 批 × 12 档扫描，产量/P/DO2 三口径灵敏度 + DO2 通道反解 `k*` + 产量崖检测 | 144 组约 **12 min**（8 进程）；`--analyze-only` 可只重算判据。结论见 `docs/r162_round_report.md` |
| `r162_governance_update.py` | 治理层更新（台账 / 签核单 / 路线图 / 契约 / state / README / 工具索引 / 工作记忆） | **幂等**（逐条检查后写入，重复执行不产生重复条目） |
| `r162_final_check.py` | **R162 终检**（常驻可复跑）：A 探针判据 / B 报告结构 / C 治理层同步 / D 文档卫生 四组共 **39 条** | **只读**，秒级；`--json` 追加写 `runs/r162_final_check.json` |

### R163（D-80 回退链接入 + 三条基础性收尾）

| 工具 | 用途 | 备注 |
|---|---|---|
| `r163_degradation_probe.py` | 真实退化批的**筛查 + 确认 + 注入**三段式：A 段跨批 EnKF 健康度筛查（增量落盘、可恢复）、B 段大集合确认、C 段物理可信故障注入 + 零信息对照 | A 段结论：**创新判据真实触发率 84.38%** ⇒ 触发 **D-87** |
| `r163_innovation_calibration.py` | 创新判据的**跨批标定**：逐通道 \|z\| 的 p50/p90/p99/max + 越限占比，并离线枚举 (阈值 × 持续占比) 候选判据的假阳性率 | 为 **D-87** 的修正提供数据基础 |
| `r163_kla_dual_constraint.py` | alpha_kla **DO2 + 产量双约束**逐批标定：可行集 F、唯一性、产量崖标记、**不可标定批识别** | 复用 R162 扫描数据，秒级；**D-84** |
| `r163_dist_variance_probe.py` | MATLAB 8 路扰动**随机成分**的贡献量化（进程内 patch，磁盘引擎零改动）：逐通道单独注入 + 全叠加 + 幅值扫描 | **D-83**；与 MATLAB 低通同构（τ=40 h） |
| `r163_mcp_integration_probe.py` | MCP 接入的**零回归 + 标记完备性**验证（Z1–Z6）；含 fastmcp stub 注入以绕开 **D-85** | 基线夹具：`tools/_legacy/mcp_server_pre_r163.py` |
| `r163_governance_update.py` | 治理层更新（台账 / 签核单 / 路线图 / 契约 / README / state / 工具索引 / 工作记忆） | **幂等**；数字全部从 `runs/` 产物读取 |
| `r163_merge_c.py` | C 段产物**合并 + 分层归因**：把健康批注入（因果可归因）与混合批注入（不可归因）合并为单一主产物，并输出 TP/FN/TN/FP 四格 | 幂等；**「对照已退化 ⇒ 触发不可归因」** 的口径在此固化 |
| `r163_report_fill.py` | 报告占位符**数据驱动回填**（`{{TAG}}` → 实测值）；`--reset` 可把已填值反向还原后重填 | 幂等；数字全部从 `runs/` 产物读取 |
| `r163_final_check.py` | **R163 终检**（常驻可复跑）：A 探针判据 / B 报告结构 / C 治理层同步 / D 文档卫生 四组共 **60 条** | **只读**，秒级；`--json` 追加写 `runs/r163_final_check.json` |

| `docs/goal_backtrace_check_v4.md` | 第四次全量回溯（**`deepening_plan` 专项** + 首次对标 GOAL §2 目标量表）| 产出 D-88 / D-89；PH1–PH5 逐阶段对标 |

| `r164_governance_update.py` | 治理层更新（台账 / 签核单 / 路线图 / 契约 / README / state / 工具索引 / 工作记忆）| **幂等**；dry-run 不写盘；数字全部从 `runs/` 读取 |

### R165（阶段收口：R164-1…R164-7 波次 1+2）

| 工具 | 用途 | 备注 |
|---|---|---|
| `r165_mcp_tools_probe.py` | R164-1 PH5 服务化补齐验证：AST 静态计数 12→14、既有 12 工具函数体逐字比对、`solver_info` 冻结快照、两工具双向判别力、菌丝分室标记 | stub 注入绕开 D-85；**12/12 PASS**；`runs/r165_mcp_tools_probe.json` |
| `r165_co2_stuck_detector.py` | R164-5 CO2 卡死只读检测器：exact/near_flat 双阈值、std_frac 分离度扫描、LOO 5 折、灵敏度下界、EnKF OR 四格增益 | **11/11 PASS**；`runs/r165_co2_stuck_detector.json`；只读、不进默认引擎路径 |
| `r165_mycelium_identifiability.py` | R164-7 菌丝区 A0/A1/A3/A4 可辨识性证明：从 `observe.py` 真实常量导出 H、列归一 SVD、零空间/反例/正例扰动族、`model.rhs` 动力学层 Δ | **11/11 PASS**；`runs/r165_mycelium_identifiability.json`；主文档 `docs/r165_mycelium_identifiability.md` |
| `r165_governance_text.py` | R164-2/3/4/6 治理文本四项（46 项精确替换/插入） | **幂等**（46 项、三次复跑零写入）、dry-run 零泄漏、数字数据驱动、CRLF/LF 原样；`runs/r165_governance_text.json` |
| `r165_governance_update.py` | 治理层同步（契约 v1.95 / 台账 D-90 / 签核单 R-15 / README / INDEX / state / 工作记忆） | **幂等**、dry-run 零泄漏；数字全部从 `runs/` 读取 |
| `r165_final_check.py` | **R165 终检**（常驻可复跑、只读）：A 探针判据 / B 治理文本 / C 治理层同步 / D 闸门与文档卫生 | `--json` 写 `runs/r165_final_check.json` |

| `docs/r165_round_report.md` | R165 轮次主交付（十章 + 收口补记） | 含下一阶段任务清单引用与闸门最终结果 |
| `docs/r165_mycelium_identifiability.md` | 菌丝区可辨识性证明主文档 | D-88 双重结论与口径勘误 |

### R166（五项委托裁决 · A/B 证据闸门）

| 工具 / 文档 | 用途 | 备注 |
|---|---|---|
| `r166_ab_gate.py` | **A/B 证据闸门**：V1 逐通道判据扫描（零信息对照 / 双向 / 网格 + 显式裕度 + LOO / 四格 A/B）、V2 统计等价方差注入、V3 `k_dual` 查表 | `--stage v1_collect / v1_analyze / v23 / all --json`；`runs/r166_v1_health.json`、`runs/r166_ab_gate.json` |
| `r166_v2_optim.py` | **V2 多轮寻优**（D-83）：σ=0 零信息对照 → 全幅 σ 崩塌复现 → scale 网格扫描 → 显式目标（R163 实测 pp）→ 按批 LOO + 额外种子样本外验证；**判据阈值原样不改** | `--stage scan / seeds / all --workers 6`；`runs/r166_v2_optim.json` |
| `r166_mcp_smoke.py` | **MCP 冒烟闸门**（无 stub、进程内、不监听端口）：14 工具枚举 + 与 R165 冻结快照逐位比对 + 依赖锁 + 14 工具函数体 AST 一致性 | `--json` 写 `runs/r166_mcp_smoke.json`；S1–S9 |
| `r166_governance_update.py` | 治理层同步（契约 v1.96 / 台账 D-91 / 签核单 R-16 / README / INDEX / state / §8.8 / 报告 / 工作记忆） | **幂等**、dry-run 零泄漏、数字全部从 `runs/` 读取、CRLF/LF 原样 |
| `r166_final_check.py` | **R166 终检**（只读、常驻可复跑）：A 裁决 / B 候选通道 / C A/B 证据 / D 闸门与治理同步 / E 文档卫生 | `--json` 写 `runs/r166_final_check.json` |

| `docs/r166_verdict.md` | 五项裁决单（含最优架构论证、Go/No-Go 切换条件、未越界声明） | 用户委托裁决依据 |
| `docs/r166_round_report.md` | R166 轮次主交付 | 含 §8.8 下一阶段任务清单引用 |
| `runs/r166_zero_regression.json` | 86 批逐位零回归证据 | `max|Δ| = 0.00e+00` |

### R167（平台升级 · 算子运行时装载 · T8 六视图复验）

| 工具 / 产物 | 用途 | 命令 / 证据 |
|---|---|---|
| `platform/ops_registry.py` | **能力注册表**（新增）：14 个 A/B/C/D 工具 + 12 个算子的运行时 `import+callable` 核验、`invoke()` 白名单 / 禁用 L3 参数 / `opt_in` / `confirm` 闸门、`evidence()` 只读 runs/ | 进程内复用 `mcp_server.py` 工具本体，不复制实现 |
| `platform/serve.py` | 增 `/api/ops` `/api/evidence` `/api/invoke`；`/api/simulate` L0 逐字未改 | `py platform/serve.py --port 8771` |
| `platform/export_data.py` | 契约版本头部+表体取最大 / KPI 改 classify_health / 算子运行时核验 / 新增 `workbench` + `evidence` 数据块 | `py platform/export_data.py` → `platform/data.js`（v1.97） |
| `platform/app.js` / `index.html` / `style.css` | 第 6 视图「观察·控制工作台」；算子视图改运行时装载标签；总览 catastrophic 改「4 已登记 / 0 新发」 | `#workbench` |
| `tools/r167_platform_gate.py` | **R167 闸门**：源码边界 / 运行时装载 / HTTP 冒烟 / L0 回归 / L3 行为拒绝 / T8 六视图逐屏复验 + 截图 | `py tools/r167_platform_gate.py [--no-shots]`；`runs/r167_platform_gate.json` **PASS 25/25** |
| `tools/r167_governance_update.py` | 治理层同步（契约 v1.97 / 台账 D-65+D-92 / 签核单 R-17 / README / INDEX / state / §8.9 / 记忆） | 幂等、dry-run 零泄漏、CRLF/LF 原样 |
| `docs/goal_backtrace_check_v5.md` | 第五次全量回溯：研发成果 / 基础工作完备性 / 平台装载缺口 | R167 决策依据 |
| `docs/r167_platform_screen_check.md` | T8 六视图逐屏复验记录 | 6 张截图 `docs/screenshots/platform/r167_*.png` |
| `docs/r167_round_report.md` | R167 轮次主交付 | 见报告 |
