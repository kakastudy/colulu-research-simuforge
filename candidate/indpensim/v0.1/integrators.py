# -*- coding: utf-8 -*-
"""纯 numpy 显式 RK4 积分器（小步长 + 数值稳定化）。

用途：IndPenSim 33 维 ODE 的积分（scipy 不可用时的兜底）。
方法：RK4，步长 h=0.001 h（对 kla~0.34 稳定，h*kla=0.00034<<1）。
稳定化：每步后 clamp 刚性状态（DO2, pH, O2）到合理范围。
性能：每步 4 rhs 调用。0.2h 区间 = 200 步 = 800 rhs 调用。
"""
import numpy as np


def rk4_integrate(f, t0, y0, t_end, h, clamp=None):
    """RK4 积分 [t0, t_end]。返回 (ts, ys) 其中 ys 形状 (n_states, n_steps+1)。"""
    n = len(y0)
    ts = [t0]
    ys = [y0.copy()]
    t = t0
    y = y0.copy()

    while t < t_end - 1e-9:
        hh = min(h, t_end - t)
        t_next = t + hh

        k1 = f(t, y)
        k2 = f(t + hh / 2, y + hh / 2 * k1)
        k3 = f(t + hh / 2, y + hh / 2 * k2)
        k4 = f(t_next, y + hh * k3)

        y_new = y + hh / 6 * (k1 + 2 * k2 + 2 * k3 + k4)

        # 数值稳定化
        if clamp:
            for (i, lo, hi) in clamp:
                if y_new[i] < lo:
                    y_new[i] = lo
                if y_new[i] > hi:
                    y_new[i] = hi

        y = y_new
        t = t_next
        ts.append(t)
        ys.append(y.copy())

    return np.array(ts), np.array(ys).T
