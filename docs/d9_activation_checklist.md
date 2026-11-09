# D9 裁决材料 + v0.2 激活执行清单（R115 预写，待 p4_upgrade_verdict.json PASS 后执行）

## 1. D9 裁决：后验算子 vs ODE 级积分

| 方案 | 内容 | 状态 |
|---|---|---|
| **(a) 后验算子（推荐）** | 死亡项修正层 X_corr = X − (kd1·X + kd2·X·A_t1 + kd3·X·A_t1²)/100，A_t1=a0/(a1+a3+a4)，作用于观测/校准层（observe._death_corr / calibration.death_correct_X 双实现等价，max diff 0.00e0） | 已定性完成（R44-46）；β=(81.70, −293.71, 158.56)，R²=0.6663，n=621 |
| (b) ODE 级积分 | 把死亡项作为 ODE 状态方程直接积分 | 未实施；需重做黄金回归（代价高，且 X 通道化验 RMSE 改善与产量级 RMSE 收益差异未经检验） |

**推荐 (a) 的理由**（已在 ledger/docs 记录）：
- 算子在观测/校准层，不动引擎 ODE → 黄金回归（4.48%/0/12/9）逐字守护通过，零回归风险
- 10/10 黄金批 X 通道 nRMSE 改善中位 −15.3pt（p4_death_probe.json，确定性重放）
- 全池 G4 覆盖率提升（批 11/16/60 = 0.625/0.789/0.474，均值 0.629 ≥ 0.60 通过线）
- 与「只增不减」原则一致：v0.1 基线不动，v0.2 仅在观测层追加

**已裁决的开放问题**：产量级 RMSE ≤3.5% 的目标——死亡项算子不改变产量输出
（X 通道是状态观测修正，非产量方程），产量级收益需另设机理项（挂 V1+ 机理增强）。

## 2. 激活执行清单（verdict=PASS 后按序执行）

1. ☑ `candidate/indpensim/v0.1/observe.py` + `calibration.py`：确认 death_term.json
   作为默认 β 来源（load_death_beta() 已实现），确认 v0.1 calib_params 路径零改动
2. ☑ 重跑黄金回归守护 `tools/diag_final_validation_v2.py` → **4.48%/0/12/9 逐字保持**（R120）
3. ☑ 重跑 G4 覆盖率（三批 11/16/60，death on）→ **均值 0.629 ≥0.60**（0.625/0.789/0.474）
4. ☑ 更新 `runs/final_validation_v2.json` + 双账本（activation 条目，ledger120b）
5. ☑ 重生成 `docs/ph2_acceptance_draft.md`（make_ph2_acceptance.py 自动）
6. ☑ 生成用户可见验收报告 `docs/ph2_acceptance_report.md`（verdict=PASS，五闸全过）
7. ☑ ENGINE_CONTRACT.md 增补 v0.2 算子条目（默认启用声明 + 口径注释，v1.2）
8. ☑ pending_review_list.md 标记 D9 已裁决 + 更新状态（顶部 + 索引表）

> 链后四环核对（post_chain_verify.py）：ph1e_fit / ph2_full / p4_driver / acceptance **全 PASS**。
> 时序修复记录：首轮链 ph1e_fit 路径 bug 崩溃 → G2 时序误判 HOLD → 手动补跑 + 重跑驱动 → PASS。

## 3. 用户可见验收报告模板（激活后生成）

```
# PH2/P4 v0.2 升级验收报告
- 日期 / verdict 来源（p4_upgrade_verdict.json）
- 五闸明细（G1 池规模、G2 先验产物、G3 β 拟合 R²/n、G4 覆盖率均值、G5 探针改善率）
- 死亡项算子参数（β、口径声明 A_t1=a0/(a1+a3+a4)、双实现等价性）
- 激活后回归数字（黄金 4.48%/0/12/9、覆盖率三元组）
- 诚实缺口（DL σ̂ 需非网格后验；PAA 批间异质；D9-b 未实施）
- 下一步（V1+ 队列：PAA 消融对照、机理增强项、黄金集扩展）
```

## 4. 若 verdict=HOLD 的处置

- 读 verdict.json 各 gate 明细定位首个 FAIL
- G1/G2 失败 → 池未满或先验缺失 → 重跑对应环节（watcher 链或手工）
- G3 失败 → β 拟合口径漂移 → 重跑 fit_death_term.py
- G4 失败 → 覆盖率低于 0.60 → 查 ensemble_smooth 参数（n_ens/seed）后重跑
- G5 失败 → 探针改善率不足 → 复查 p4_death_probe 实现

## 5. 附录：ENGINE_CONTRACT.md v0.2 条目（就绪文本，激活时填入 §2 工具契约后 + §4 版本表）

```markdown
### death_term_operator() → dict（观测层，无新增 MCP 工具——经 reconstruct_batch/trajectory_check 生效）
**PH2/P4 v0.2 死亡项修正层**（默认启用）：X_corr = X − (kd1·X + kd2·X·A_t1 + kd3·X·A_t1²)/100，
A_t1 = a0/(a1+a3+a4)（公式层口径，化验对齐点 0.22~0.51）。β=(kd1,kd2,kd3) 运行时读
runs/hier_est/death_term.json（R²=0.6663, n=621）。生效路径：observe.ensemble_smooth
（death_term=True 默认）与 calibration.death_correct_X；引擎 ODE 零改动，黄金回归
4.48%/0/12/9 逐字守护。
```

版本表追加行：

```markdown
| v1.2 | +死亡项修正层（PH2/P4 v0.2）：观测层 X 通道校正，默认启用；引擎 ODE 零改动 |
```
