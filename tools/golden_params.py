# -*- coding: utf-8 -*-
"""兼容层：把引擎包内的单一事实源重新导出给 tools/ 下的脚本。

**参数表的真正位置已迁到** `candidate/indpensim/v0.1/golden_params.py`（R132）。
这个文件不再持有任何数据，只做转发——它存在的原因仅是 tools/ 下十余个脚本
（r131_*、d6_health_view、r131_mup_robust 等）历史上都写 `from golden_params import ...`。

为什么用 importlib 而不是 `sys.path.insert`：
    本文件自身就叫 golden_params.py，直接插入包路径会让 `import golden_params`
    解析到包内那份，与 tools/ 下的同名模块形成循环/歧义。用独立模块名
    `_indpen_golden_params` 显式加载，二者互不干扰。
"""

import importlib.util
import os

_PKG_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "candidate", "indpensim", "v0.1", "golden_params.py")

_spec = importlib.util.spec_from_file_location("_indpen_golden_params", _PKG_FILE)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

# 数据
COMBINED = _mod.COMBINED
GOLDEN_NORMAL = _mod.GOLDEN_NORMAL
FAULT = _mod.FAULT
GOLDEN_ALL = _mod.GOLDEN_ALL
R131_OVERRIDES = _mod.R131_OVERRIDES
R131_ROBUSTNESS = _mod.R131_ROBUSTNESS
# R156 / D-55 候选基线 v2（opt-in）：pH 链式法则修正 + 5 批 mup 重标
RECAL_V2_MUP = _mod.RECAL_V2_MUP

# 装配
build_params = _mod.build_params
params_for = _mod.params_for
apply_candidate_v2 = _mod.apply_candidate_v2
