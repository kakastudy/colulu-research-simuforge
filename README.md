# SimuForge · 青霉素反应罐 AI 原生仿真计算系统

一个可复核、可复现的化工过程仿真技术栈：**58 个底层算子 → 33 维机理求解器 → 两代仿真计算平台**，全部由一个受约束的 AI Agent 研发闭环产出，数值结果由固定判据验收。

本仓库回答一个问题：**AI Agent 能不能把仿真算子推到「可验收」，而不只是「能跑」？**

---

## 1. 三层结构

```
            ┌──────────────────────────────────────────────┐
            │  平台层   platform/ (v1) · platform_v2/ (v2)  │
            │  参数覆盖 · 工况扫描 · 批次回放 · 异步队列      │
            └───────────────────┬──────────────────────────┘
                                │  调用
            ┌───────────────────▼──────────────────────────┐
            │  求解器层 candidate/indpensim/v0.1/           │
            │  33 状态 · 105 参数 · 26 输入 · BDF 刚性积分   │
            └───────────────────┬──────────────────────────┘
                                │  调用
            ┌───────────────────▼──────────────────────────┐
            │  算子层   operator_kit/ (penops)              │
            │  58 底层算子 · 18 高层能力 · 21 MCP 工具       │
            └───────────────────┬──────────────────────────┘
                                │  读取
                        data/processed/  100 个生产批次的加工数据
```

三层之间只通过显式契约通信：算子不复制求解器实现（全部现场 import），平台不写回引擎参数，任何新能力默认关闭。

## 2. 指标

| 层 | 指标 | 数值 |
|---|---|---|
| 算子 | 底层算子 / 高层能力 / MCP 工具 | 58 / 18 / 21 |
| 算子 | 自检（真实调用而非静态扫描） | 29 / 29 通过 |
| 求解器 | 状态量 / 参数 / 外源输入 | 33 / 105 / 26 |
| 求解器 | 86 批产量相对误差 RMSE | **2.3448%** |
| 求解器 | 落在 ±5% 验收带的批次 | **86 / 86** |
| 求解器 | 最大单批误差 | 4.83% |
| 平台 v1 | 六视图闸门 | 25 / 25 |
| 平台 v2 | 快速闸门（真实起服务 + 真实仿真） | 18 / 18 |
| 平台 v2 | 可调参数 / 输出通道 / 原生时间分辨率 | 97 / 40 / 0.2 h |

## 3. 目录

```
candidate/indpensim/v0.1/     机理求解器
  model.py                    33 维 ODE 右端项（逐项对照 MATLAB 参考实现）
  params.py                   105 参数、批次级随机参数注入
  integrators.py              BDF / Radau 封装（rtol=1e-3, atol=1e-6, max_step=0.01 h）
  simulate.py                 单批仿真 CLI
  golden_params.py            冻结的黄金参数集（只读）
  validate.py                 验收判据：±5% 产量带 + 五通道健康分级
  observe.py / soft_sensing.py    B 档观测器（软测量）
  optimize.py                 C 档反设计
  identifiability.py          结构可辨识性分析
  conservation.py             守恒量校验（C/H/O/N 元素平衡）

operator_kit/                 penops：算子封装层
  penops/                     L1 可调用 SDK（import penops 即可用）
  penops_mcp/                 L2 MCP 协议适配（stdio JSON-RPC）
  manifest.json               算子清单（自动生成 + 真实调用验证）
  QUICKSTART.py               可运行的使用说明
  tools/verify_kit.py         全量自检

platform/                     仿真计算平台 v1（冻结基线，端口 8770）
platform_v2/                  仿真计算平台 v2（端口 8772）
  engine_api.py               引擎适配与通道映射
  param_catalog.py            97 参数目录
  scan.py                     二维参数扫描
  job_queue.py                异步作业队列
  index.html / app_v2.js      前端

tools/                        研发与验收脚本（回归、闸门、出图、截图）
data/processed/               100 批加工数据 + 清单 + 黄金集
docs/blog/assets/             公开文章所用插图
paper/figures/                方法学插图
```

## 4. 快速开始

环境：CPython 3.10（`numpy<2` 是硬约束，`np.trapz` 在 numpy 2.x 已移除）。

```bash
pip install -r requirements.txt
```

**跑一次单批仿真**（约 20–60 s）：

```bash
python candidate/indpensim/v0.1/simulate.py --batch 11 --out out.json
```

**算子包自检**：

```bash
python operator_kit/QUICKSTART.py             # L1 轻调用 + L2 自检
python operator_kit/QUICKSTART.py --simulate  # 额外跑一次真实仿真
```

**起平台**：

```bash
python platform_v2/serve_v2.py     # http://127.0.0.1:8772
python platform/serve.py           # http://127.0.0.1:8770（v1 冻结基线）
```

**跑测试**：

```bash
python -m pytest -q
```

## 5. 数据与基准

- **来源**：IndPenSim 青霉素补料分批发酵仿真数据集，100 个生产批次（Goldrick et al., 2015）。本仓库只包含加工后的 CSV，原始 MATLAB 源码与导出文件不入库。
- **规模**：单批 167–290 h，在线通道 0.2 h 采样，离线化验 12 h 采样并滞后 4 h，37 个通道。
- **为什么要加工**：原始导出存在表头错位 2 列、离线通道 98.2% 为空、批次间参数随机等问题。加工口径写在 `data/processed/batches_manifest.csv` 与 `golden_set.json` 中。
- **扰动与故障**：8 路低通滤波随机扰动作用于生长、产物、底物、油、酸碱、前体、冷却水温与进气氧；另含 8 类故障注入。
- **基准选择理由**：参考实现是**可执行代码**而不是论文方程——论文给方程形态，代码给口径（单位、时序、控制回路、随机数位置）。代价是 MATLAB 随机数不可逐位复现，因此本项目以「参数分布 + 轨迹对齐」而非逐位复现作为对齐目标。

## 6. 复现边界（重要）

这些是实测结论，不是免责声明：

1. **2.3448% 是重建一致性，不是前瞻预测能力。** 每个批次使用各自的标定参数；留出批次的前瞻迁移中位误差是 97.47%，20 批里只有 1 批进入 ±5%。
2. **参数可行域很窄。** C 档反设计的 12 批口径可以 12/12 落进 ±5%，但进料速率可行域只有 ±1% 量级；要补齐 60–120 h 的产量缺口需要 ±30%~±80% 的调整，差约 30 倍。
3. **闭环数据同化不成立。** 在 86 批上表现为可用，换到留出批次只剩 6/86。
4. **部分结构不可辨识。** 菌丝区相关参数与 P/PAA 通道在现有观测下判定为 `NOT_IDENTIFIABLE`，不是精度不足而是结构上无法确定。
5. **单案例、有界条件。** 全部结论限于本案例与本数据集，不主张跨工艺泛化。

## 7. 许可

- 代码：暂未声明开源许可证（默认保留所有权利）。若需复用请先联系作者。
- 数据：加工数据派生自 IndPenSim，原始数据集版权归原作者，使用请遵循其许可并引用：

> Goldrick, S., Ştefan, A., Lovett, D., Montague, G., Lennox, B. (2015). The development of an industrial-scale fed-batch fermentation simulation. *Journal of Biotechnology*, 193, 70–82.

## 8. 相关文章

- 《AI Agent 原生仿真计算系统之路：以青霉素反应罐算子/求解器/仿真计算平台研发为例》— 见 `blog_ai_agent_sim_stack_public_20261109.md`
