# -*- coding: utf-8 -*-
"""路径装配 —— 本库与引擎之间唯一的路径入口。

搬走这个目录也能用
------------------
默认假设 `operator_kit/` 位于项目根下：

    <PROJECT_ROOT>/
        operator_kit/          <- 本目录（可整体搬走）
        candidate/indpensim/v0.1/   <- 引擎（算子实现本体）
        platform_v2/                <- 仿真/扫描封装
        data/processed/batches/     <- V3 批次数据

若把 `operator_kit/` 搬到别处，设置环境变量即可：

    PENOPS_ENGINE_ROOT = <PROJECT_ROOT 的绝对路径>

设计纪律
--------
1. **不复制实现**：所有算子都从引擎目录 import，本库只做装配与包装。
2. **不污染调用方**：`mcp_server.py` 顶层会 `os.chdir(_ROOT)`；本库用
   `preserved_cwd()` 在加载后恢复调用者的工作目录。
3. sys.path 只在需要时追加，且做去重；不修改 `data/`、不写引擎目录。
"""
from __future__ import annotations

import contextlib
import importlib
import os
import sys
from typing import Iterator

KIT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PROJECT_ROOT = os.path.dirname(KIT_DIR)
ENV_ROOT = "PENOPS_ENGINE_ROOT"


def project_root() -> str:
    """引擎所在项目根（可由环境变量覆盖）。"""
    return os.path.abspath(os.environ.get(ENV_ROOT, DEFAULT_PROJECT_ROOT))


def engine_dir() -> str:
    return os.path.join(project_root(), "candidate", "indpensim", "v0.1")


def platform_v2_dir() -> str:
    return os.path.join(project_root(), "platform_v2")


def kit_dir() -> str:
    return KIT_DIR


def bootstrap_paths() -> dict[str, str]:
    """把引擎目录与 platform_v2 目录挂到 sys.path（幂等）。

    返回实际使用的路径字典，供 `runtime_status()` 展示。
    """
    wanted = [engine_dir(), platform_v2_dir(), KIT_DIR]
    for p in wanted:
        if p not in sys.path:
            sys.path.insert(0, p)
    return {
        "project_root": project_root(),
        "engine_dir": engine_dir(),
        "platform_v2_dir": platform_v2_dir(),
        "kit_dir": KIT_DIR,
    }


def import_engine(name: str):
    """按名字 import 引擎模块（自动装配路径）。"""
    bootstrap_paths()
    return importlib.import_module(name)


@contextlib.contextmanager
def preserved_cwd() -> Iterator[None]:
    """保护调用方 cwd：引擎模块 import 时会自行 chdir。"""
    before = os.getcwd()
    try:
        yield
    finally:
        if os.getcwd() != before:
            os.chdir(before)


def check_layout() -> dict:
    """布局体检：缺哪一块就显式报出来，不静默降级。"""
    p = {
        "project_root": project_root(),
        "engine_dir": engine_dir(),
        "platform_v2_dir": platform_v2_dir(),
        "data_dir": os.path.join(project_root(), "data", "processed", "batches"),
        "mcp_server": os.path.join(engine_dir(), "mcp_server.py"),
        "engine_api": os.path.join(platform_v2_dir(), "engine_api.py"),
    }
    p["exists"] = {k: os.path.exists(v) for k, v in p.items() if isinstance(v, str)}
    p["ok"] = all(p["exists"].values())
    return p
