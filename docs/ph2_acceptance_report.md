# PH2/P4 v0.2 升级验收报告

> 自动生成于 2026-10-30T00:58:08（tools/make_ph2_acceptance_report.py）——所有数字提取自 runs/ 产物，可追溯。

## 一、验收判决

**verdict = PASS**（来源 runs/hier_est/p4_upgrade_verdict.json）

| 闸门 | 判据 | 实测 | 结果 |
|---|---|---|---|
| G1 池规模 | v2 池 ≥88 批 | 88 | ✅ PASS |
| G2 先验产物 | hier_prior_v2.json 存在 | True | ✅ PASS |
| G3 死亡项拟合 | R²≥0.5 ∧ n≥400 ∧ β 三系数 | R²=0.666, n=621 | ✅ PASS |
| G4 X 覆盖率 | 黄金子集均值 ≥0.60 | mean=0.629 | ✅ PASS |
| G5 探针改善 | ≥半数黄金批改善 | 10/10 | ✅ PASS |

## 二、死亡项算子（v0.2）参数

- β（kd1, kd2, kd3）= (81.70, -293.71, 158.56)
- R² = 0.6663；n = 621 点（X 通道全批水平拟合，runs/hier_est/death_term.json）
- 口径：A_t1 = a0/(a1+a3+a4)（化验对齐点 0.22~0.51，随成熟衰减；记录列 sim[A_t1] 为另一约定不可互换）
- 双实现等价：observe._death_corr ≡ calibration.death_correct_X（max diff 0.00e0）

## 三、升级前探针改善（确定性重放）

| 批 | Δ X nRMSE (pt) |
|---|---|
| 8 | -5.5 |
| 11 | -14.1 |
| 16 | -22.0 |
| 22 | -15.4 |
| 23 | -15.3 |
| 27 | -3.3 |
| 36 | -20.5 |
| 55 | -11.1 |
| 60 | -18.9 |
| 80 | -23.9 |

改善 10/10 批，中位 -15.3 pt。

## 四、激活后回归（黄金回归守护）

- 黄金 RMSE = 4.48%（12 批 yield_err 的 RMSE，来源 runs/final_validation_v2.json）
- within5% = 9/12；灾难 = 0/12

## 五、诚实缺口（不静默化）

- DL σ̂ 需非网格后验（PH3+ 债务）—— **R165 勘误（R142）**：`dl_sigma` 的 σ_pop=0 是温度口径失效产物（T_EB=1.0 比损失差大 106×、ESS=46.8/48），`COMBINED` 逐批点估计亦不得作批间分布样本；现行可引用口径只有 MAP 散布上界 σ_pop ≤ 0.0328/0.0056/0.0019（不含群体先验）
- PAA 通道批间异质（R90 普查 7/9 正向、2/9 反相；μp 机理锚点 −0.891）
- D9 方案 (b) ODE 级积分未实施；~~产量级 RMSE ≤3.5% 需机理增强项（V1+）~~
  **R165 回填（`docs/goal_backtrace_check_v4.md` §D3）**：该「诚实缺口」**早已闭合** —— 默认基线 86 批产量 **RMSE 2.345%**（红线 3.5%）、**86/86 在 ±5%**、**0 catastrophic**（证据 `runs/r163_zero_regression.json`：`summary.rmse_pct=2.345` / `within5=86` / `n=86`；`runs/r156_acceptance.json` HARD 全 PASS）⇒ 「需机理增强项」的推断已不成立，本项从缺口清单移除。
- PAT 消融对照（引擎 PAA vs PAT 转发 vs fused 三口径, 健康批 60/22 先行）待执行

## 六、下一步（V1+ 队列）

1. PAT 消融对照（批 60/22, 三口径净变化）
2. 产量级机理增强项（死亡项之外的通道）
3. 黄金集扩展（待用户确认数量）

