# -*- coding: utf-8 -*-
"""统一错误语义 —— 失败必须显式，绝不静默输出「看起来正常」的默认值。

对齐 ENGINE_CONTRACT §1（I2 失败可见）与 §3.3（不得静默输出貌似合理的数）。
所有对外调用抛出的异常都是 `OperatorError`，带稳定 `code` 供 Agent / 脚本分支处理。
"""
from __future__ import annotations

from typing import Any


class ErrorCode:
    UNKNOWN_OPERATOR = "unknown_operator"
    NOT_LOADED = "operator_not_loaded"
    PARAM_INVALID = "param_invalid"
    PARAM_FORBIDDEN = "param_forbidden_l3"
    OPT_IN_REQUIRED = "opt_in_required"
    CONFIRM_REQUIRED = "confirm_required"
    BATCH_OUT_OF_RANGE = "batch_out_of_range"
    PYTHON_OBJECT_REQUIRED = "python_object_required"
    ENGINE_IMPORT_FAILED = "engine_import_failed"
    CALL_FAILED = "call_failed"
    SERIALIZATION = "serialization_error"


class OperatorError(Exception):
    """带原因码的算子错误。

    `detail` 只放结构化证据（traceback 摘要、被拒参数、判据值等），
    不放含糊的「出错了」。
    """

    def __init__(self, code: str, message: str, detail: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail

    def to_dict(self) -> dict:
        return {"ok": False, "code": self.code, "error": self.message,
                "detail": self.detail}

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


def wrap_exception(exc: BaseException, where: str) -> OperatorError:
    """把引擎抛出的任意异常转成显式错误码，同时保留类型与消息。"""
    import traceback

    return OperatorError(
        ErrorCode.CALL_FAILED,
        f"{where} 执行失败：{type(exc).__name__}: {exc}",
        {"traceback": traceback.format_exc(limit=6)},
    )
