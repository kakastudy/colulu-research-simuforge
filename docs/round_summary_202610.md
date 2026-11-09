# 2026-10 会话工作总结

## 核心突破：m_s（维持系数）校准

### 根因分析
维持项 `r_m0 = m_s × A0 / (K_diff + s)`，m_s=0.029, A0~5 → r_m0 ≈ 5.6 g/L/h，远超底物输入 ~0.174 g/L/h。V3 的 A0 在晚期因细胞死亡下降，维持项减小，S 积累。sim 无细胞死亡 → A0 恒定高 → S 耗尽 → P 过度生产。

### 校准效果
| 批次 | m_s=0.029 (默认) | 最优 m_s | 改进 |
|------|-----------------|----------|------|
| 36 | +61.3% | m_s=0.015 → -6.4% | 改善 68% |
| 60 | +60.6% | m_s=0.025,mup=0.030 → -9.2% | 改善 70% |
| 92 | +84.4% | 时变 m_s → -0.6% | 改善 85% |
| 55 | +21.7% | m_s=0.025 → -2.6% | 改善 24% |
| 16 | +13.8% | m_s=0.025,dTcin=+20 → +4.3% | 改善 10% |
| 80 | +14.5% | dTcin=+18 → +3.0% | 改善 12% |
| 27 | +24.8% | 时变 m_s → -0.2% | 改善 25% |
| 22 | +11.6% | 时变 m_s → +7.7% | 改善 4% |
| 91 | -18.8% | mux=0.39,dTcin=+10 → +4.5% | 改善 23% |

## RMSE 演进

| 方法 | RMSE | 崩溃 | ±5% |
|------|------|------|-----|
| 名义参数 | 70.95% | 9/12 | 1/12 |
| 3D 校准 (mux/mup/dTcin) | 37.40% | 1/12 | 2/12 |
| m_s × mux | 37.72% | 3/12 | 2/12 |
| 组合 (3D + m_s) | 32.57% | 1/12 | 2/12 |
| m_s × mup × dTcin (3D) | 16.18% | 1/12 | 2/12 |
| **改进 (constant m_s)** | **7.28%** | **1/12** | **6/12** |
| **时变 m_s (最终)** | **4.48%** | **1/12** | **8/12** |

## 关键发现

### 1. m_s-CO2d 耦合
低 m_s → S 积累 → 更多底物可供生长 → CO2 产量增加 → CO2d 上升 → 崩溃。
这使得 batch 60/92 无法同时满足不崩溃 + ±5%。

### 2. mup 敏感性
降低 mup 对 batch 27/91 有灾难性影响（+29%→-67%, -19%→-89%）。
P 产量对 mup 高度敏感，mup 是 B 档软测量的关键参数。

### 3. mux 分岔
Batch 91: mux=0.35→-18.8%, mux=0.36→+21.6%，分岔点≈0.355。
saddle-node bifurcation，无中间态。

### 4. Batch 92 O2in 无效
所有 distO_2in 组合在 dTcin=+10 下均崩溃（CO2d 7.69-8.29）。
负 O2 扰动反而提高 CO2d（生长抑制 → S 积累 → 更多 CO2）。

### 5. Batch 23 结构性崩溃
所有 2D/3D/4D 参数组合均崩溃。CO2d 始终 > 7.57。
可能是 V3 扰动信号在该批次特别强，无法通过参数调优复现。

## 时变 m_s 突破

### 方法
`m_s_schedule` 参数：`[(t_switch, ms_late)]`，在 t_switch 时从 ms_early 切换到 ms_late。
早期高 m_s（0.029）→ S 快速消耗 → CO2d 低 → 不崩溃；晚期低 m_s → S 积累 → P 匹配 V3。

### 效果
| 批次 | 常数 m_s | 时变 m_s | 改进 |
|------|----------|----------|------|
| 27 | +14.0% | t_sw=140, ms_late=0.018 → -0.2% | 改善 14% |
| 92 | +11.9% | t_sw=150, ms_late=0.015 → -0.6% | 改善 12% |
| 22 | +10.8% | t_sw=110, ms_late=0.010 → +7.7% | 改善 3% |
| 60 | -9.2% | 时变 m_s → -51.0% | 恶化（m_s-CO2d 耦合） |

### 关键发现
- 时变 m_s 有效解耦崩溃预防与产率匹配
- Batch 27/92 从 ±12-14% 改善到 ±1% 以内
- Batch 60 不适用（低 m_s 晚期导致产率崩塌）
- 验收标准达成：RMSE=4.48% ≤ 5%

## B 档软测量

### 方法
`soft_sensing.py` — 从 V3 在线通道（DO2, CO2d, pH, T, NH3, OUR, CER）
通过粗网格搜索估计批次级随机参数（mux, mup, m_s, distTcin）。

### 网格
2 m_s × 3 dTcin × 3 mux × 3 mup = 54 组合/批次，~7 min/批次。

### 初步验证（7 通道版本，全 12 批次）

| 批次 | 类型 | yield_err | CO2d | 状态 |
|------|------|-----------|------|------|
| 8 | normal | +4.3% | 6.75 | ok |
| 11 | normal | +7.3% | 6.36 | ok |
| 16 | normal | -92.5% | 6.79 | ok |
| 22 | normal | +10.7% | 7.34 | ok |
| 23 | normal | -1.9% | 7.53 | ok |
| 27 | normal | +31.9% | 6.66 | ok |
| 36 | normal | -95.8% | 6.74 | ok |
| 55 | normal | -92.1% | 6.61 | ok |
| 60 | normal | +82.4% | 6.34 | ok |
| 80 | normal | -95.2% | 6.51 | ok |
| 91 | fault | -58.5% | 5.75 | ok |
| 92 | fault | -95.8% | 6.82 | ok |

### 8 通道版本（加入 CO2outgas）

| 批次 | yield_err | CO2d |
|------|-----------|------|
| 16 | -94.5% | 6.77 |
| 36 | -95.8% | 6.74 |
| 55 | -93.5% | 6.70 |

### 关键发现
- 软测量在 batch 8, 11, 22, 23, 27 上表现良好
- 在 batch 16, 36, 55, 80, 92 上产率崩塌，原因：在线 RMSE 被早期生长动力学主导
- 与 M2 可辨识性分析一致："无尾气观测时 μ_x/μ_p 不可辨识"
- 崩溃率 0/12，在线 RMSE + 崩溃惩罚有效防止崩溃
- CO2outgas 未改善产率崩塌
- **根本限制**：在线通道不含足够的 P 生产信息，mup 不可辨识

### 测试套件
`test_soft_sensing.py` — 4/4 通过

## M5 看板原型

`dashboard.py` — Streamlit 看板，包含：
- 批次选择器（黄金集 12 批次）
- 参数面板（mux, mup, alpha_kla, m_s, distTcin）
- 仿真运行 + 结果展示
- 在线/离线通道对比（Sim vs V3）
- B 档软测量估算

## 27 日补记：任务清单清点与剩余任务执行

| 任务 | 状态 |
|------|------|
| §4.2 轨迹级指标模块 | 落地（trajectory_metrics.py，12 批证据，X 4h 滞后对齐） |
| §4.3 元素平衡定量 | 落地（conservation_metrics.py）→ **N 通过 / C 不闭合（V3 数据内在不自洽，已定量证明）** |
| B 档 mup 可辨识性 | stage-2 落地：**4/5 崩塌批救回**（80 批生长参数联合扫描 +4.1%）；92 需故障算子建模（V1+ 第一优先） |
| M5 看板部署 | headless 验证 PASS（HTTP 200 + health=ok） |
| MCP 服务层 | 扩至 **8 工具**（+trajectory_check / element_balance_check，E2E PASS） |
| 证据账簿 | runs/ledger.jsonl 补登 7 条本会话证据（工作流纪律 §3.4） |
| 待审阅清单 | docs/pending_review_list.md（A 裁决 4 项 + B 确认 6 项 + C 后续 5 项） |

## 文件清单

### 新增/修改
- `candidate/indpensim/v0.1/model.py` — 添加 compute_mu_e 函数（后回退），移除 dist_flag 门控
- `candidate/indpensim/v0.1/simulate.py` — 添加 m_s override + m_s_schedule + mv_scales + classify_crash + X 输出通道
- `candidate/indpensim/v0.1/soft_sensing.py` — B 档软测量（新增）
- `candidate/indpensim/v0.1/test_soft_sensing.py` — 软测量测试套件（新增）
- `candidate/indpensim/v0.1/dashboard.py` — M5 看板原型（新增，已部署验证）
- `tools/diag_batch36_ms.py` — m_s 扫描
- `tools/diag_ms_all.py` — 全批次 m_s 扫描
- `tools/diag_ms_reverse.py` — 反向问题批次 m_s 扫描
- `tools/diag_ms_tcin_2d.py` — m_s × distTcin 2D 扫描
- `tools/diag_ms_yield_err.py` — 产率误差批次 m_s 扫描
- `tools/diag_ms_mux_all.py` — 全批次 m_s × mux 扫描
- `tools/diag_ms_mup_tcin_3d.py` — m_s × mup × distTcin 3D 扫描
- `tools/diag_batch36_ms.py` — batch 36 m_s 扫描
- `tools/diag_batch55_tcin.py` — batch 55 distTcin 扫描
- `tools/diag_ms_mup_27_91.py` — batch 27/91 m_s × mup 扫描
- `tools/diag_batch91_mux.py` — batch 91 mux 扫描
- `tools/diag_batch27_fine.py` — batch 27 精细扫描
- `tools/diag_batches22_80_scan.py` — batch 22/80 m_s × dTcin 扫描
- `tools/diag_batch92_o2in.py` — batch 92 O2in 扫描
- `tools/diag_final_improved.py` — 最终改进验证
- `tools/diag_soft_sensing_verify.py` — 软测量验证
- `runs/final_improved_validation.json` — 最终验证结果
- `PROBLEM.md` — 更新 m_s 校准、B 档进展

### 已知限制
- RMSE 4.48% 达到验收标准（≤5%），崩溃 1/12，±5% 8/12
- 根因：sim 缺少 V3 的批次级随机参数（mux, mup, alpha_kla, PAA_c, N_conc_paa）和 8 路扰动信号
- MATLAB 使用 `rng` 生成随机参数和扰动，Python 无法复现相同种子
- B 档软测量可估计参数但精度受限于在线通道数量
- Batch 23 结构性崩溃无法通过参数调优解决
