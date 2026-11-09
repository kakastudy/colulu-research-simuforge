# Raman PAT 通道接入规格（(a) 引擎合成层路线 — V1+ 设计稿）

> R51/R53/R81 证据链的工程化收口。状态：**设计草案**（工程未启动）；启动条件 = PH2
> 正式验收 PASS 后的下一个 V1+ 工作周期（与 D9 裁决、批池扩展并行评审）。

## 0. 已就绪资产（不重做）

| 资产 | 状态 |
|---|---|
| 合成层 `tools/raman_pipeline.py::synth_batch()` | ✅ 翻译忠实度 r=0.9995（对 Batch_01 存储谱） |
| PLS 层 `predict_paa()`（b 第 4 行 + savgol/diff/212 bins/3 点平滑） | ✅ 循环自洽 r=0.9997 |
| 独立预测力上界 | r=0.8463（V2 示范批真实噪声+真实化验，n=22） |
| 三重口径方法论 | ✅ 已入 T7 台账（还原忠实度/循环自洽/独立预测力） |

## 1. 接入架构（在观测层 Achieve — 不进引擎 ODE）

```
引擎状态（sim DataFrame: P/X/vis/S/PAA）
   └─ synth_batch → spec (2200 × n_t)
        └─ predict_paa → PAA_pat（PAT "读数"）
             └─ 【锚定修正层】PAA_paT_corr
                  输入: 化验锚点 (t_lab, PAA_offline) + PAT 读数
                  机制: 二级低频校正（PAT 高频形状 × 化验低频基准）
                  输出: 融合观测通道 → 见证 I3 覆盖率三元组
```

**为什么 (a) 是校正源而非转发器（R53 发现引化）**：引擎 PAA 局部保真不足
（批 22 r=−0.34@lag0），PAT 转发引擎值会继承该反相关。锚定修正层把 PAT 的高频
结构与化验真值水平耦合，是数据上唯一可辩护的接入形态。

## 2. 验收判据（三元组，扩展到 PAT 通道）

| 口径 | 定义 | 通过线（建议） |
|---|---|---|
| 还原忠实度 | PAT_corr 合成回放 vs V3/引擎 chem 混合参照 | r ≥0.9 |
| 循环自洽 | 合成驱动 PAA → PLS → PAA_pat vs 化验插值 | r ≥0.95 |
| 独立预测力 | （V1+ 若获得 61–90 实测谱）PAT vs 化验裸点 | r ≥0.8（对照 V2 demo 0.8463） |

**通道对账范式（R111 实证后追加）**：合成读数通道（PAT）的独立预测力必须与其所转发的
状态通道（引擎 PAA）逐批对账——一致则通道忠实（无额外失真/增益），分歧则存在通道层
问题。实测 10/10 批一致（pat_triple_census vs paa_fidelity_census，偏差 ≤0.02 由插值
时点差异造成）→ PAT 是『忠实转发 + 条件锚定』，不是独立信息源。

## 3. 工作分解（V1+）—— 进度（R111 更新：4.5/5 完成）

1. ✅ `raman_pat_channel.py`：把 demo_raman_channel.py 收束为库函数（含锚定修正层）——R103
2. ✅ 评估三元组扩展进 `trajectory_metrics`（--pat flag，默认关；PAT_triple 段）——R110
3. ✅ 仪表盘观察工作台加 PAT 卡片（触发器预览 + 口径声明）——R104
4. ✅ MCP `reconstruct_batch` 附 `paa_pat_advisory`（触发器预告）——R105
5. ✅ 消融对照（R120 完成）：PAT on/off 对 I3 PAA 覆盖率与相关系数的净变化
   - **批 60**（健康正向）：引擎 PAA corr=0.97 → PAT 转发 corr=0.966（Δ=−0.004 近无损）；
     I3 PAA 覆盖率 0.895 不变；触发器不触发（μp=0.030<0.055）
   - **批 22**（μp 触发批）：引擎 PAA corr=0.353 → PAT 转发 corr=0.345（Δ=−0.008 近无损）；
     **fused corr=0.808**（+0.455——锚定层把反相关批拉回）
   - **结论**：PAT 转发通道对引擎 PAA 动态几乎无损（fidelity r≈0.9995）；触发批上
     fused 锚定层显著改善与化验的相关（0.35→0.81）；覆盖率口径维持（宽而盖二象性，R63）
   - 产物：runs/p3/pat_ablation.json；脚本：tools/pat_ablation.py
   - 附带修复：raman_pipeline/raman_pat_channel 双 stdout 包装 bug（detach + 条件包装）

## 4. 明确不做

- 不把 PAT 读数反向接入引擎 ODE（观测分离原则——除非 D9-b 级别方案获批）
- 不在批 80 退化化验上做单点合格（σ/μ=0.28% 已登记，需用健康批）
- 不用记录列 `sim[A_t1]` 作为 PAT 输入（与死亡项双约定陷阱同类——先读口径注释）
