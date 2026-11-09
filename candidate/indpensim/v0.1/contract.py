# -*- coding: utf-8 -*-
"""插件契约（Plugin Contract）— M3

定义求解器的输入/输出接口，供 B 档软测量和 C 档优化调用。
契约版本：v0.1.0-draft
"""
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple
import numpy as np
import pandas as pd


@dataclass
class SimRequest:
    """仿真请求。

    Attributes:
        batch_no: 批次编号（对应 data/processed/batches/batch_XX.csv）
        params: 参数覆盖字典（keys: mux, mup, alpha_kla, PAA_c, N_conc_paa, c_oil, Tcin, x0_biomass, x0_force, dist_flag, dist_*_asym）
        inhib: 抑制开关链档位（0/1/2，默认 2 = 全部启用）
        mode: 'open_loop'（默认，V3 MV 回放）或 'closed_loop'（合成闭环）
    """
    batch_no: int
    params: Optional[Dict] = None
    inhib: int = 2
    mode: str = "open_loop"


@dataclass
class SimResult:
    """仿真结果。

    Attributes:
        time_h: 时间轴 (h)
        state: 33 维状态矩阵 (N × 33)，列顺序对齐 state_names()
        online: 在线通道 DataFrame（S, DO2, P, V, pH, T, CO2outgas, O2, OUR, CER, ...）
        yield_g: 总产率 (g)
        co2d_max: CO2d 最大值 (g/L)
        crashed: 是否崩溃（CO2d > X_crit_CO2）
        conservation: 守恒诊断字典（C_err, N_err, our_rmse, cer_rmse）
        diagnostics: 诊断字段（负值截断次数、BDF 失败次数等）
    """
    time_h: np.ndarray
    state: np.ndarray
    online: pd.DataFrame
    yield_g: float
    co2d_max: float
    crashed: bool
    conservation: Dict
    diagnostics: Dict


# ── 契约函数 ──────────────────────────────────────────────

def simulate(req: SimRequest) -> SimResult:
    """执行仿真。

    入口函数：B 档软测量和 C 档优化通过此函数调用机理引擎。
    内部委托给 simulate_open_loop（开环回放）。
    """
    from simulate import simulate_open_loop, yield_metrics, trajectory_metrics

    sim, v3 = simulate_open_loop(req.batch_no, req.params or {}, inhib=req.inhib)
    ym = yield_metrics(sim, v3)
    co2d_max = float(sim["CO2d"].max())
    crashed = co2d_max > 7.57

    # 守恒诊断（简化版，完整版见 conservation.py）
    conservation = {"C_err_pct": None, "N_err_pct": None, "our_rmse": None, "cer_rmse": None}

    diagnostics = {
        "n_steps": len(sim),
        "co2d_max": co2d_max,
        "crashed": crashed,
        "yield_err": ym["rel_err_total"],
    }

    return SimResult(
        time_h=sim["time_h"].to_numpy(float),
        state=None,  # 需从 simulate_open_loop 内部获取完整状态
        online=sim,
        yield_g=ym["total_sim_g"],
        co2d_max=co2d_max,
        crashed=crashed,
        conservation=conservation,
        diagnostics=diagnostics,
    )


def validate(req: SimRequest, v3_df: pd.DataFrame) -> Dict:
    """验证仿真结果与 V3 基准的偏差。"""
    from simulate import yield_metrics, trajectory_metrics

    sim, _ = simulate_open_loop(req.batch_no, req.params or {}, inhib=req.inhib)
    ym = yield_metrics(sim, v3_df)
    tm = trajectory_metrics(sim, v3_df)

    return {
        "yield": ym,
        "trajectory": tm,
        "co2d_max": float(sim["CO2d"].max()),
        "crashed": float(sim["CO2d"].max()) > 7.57,
    }
