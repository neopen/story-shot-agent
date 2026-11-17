"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: env_resolver.py
@Description: 配置安全工具模块 - 统一管理受信任配置加载上下文与环境变量引用安全解析
@Author: NeoPen
@Time: 2026/11/09
"""

import os
import re
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator, Optional, Tuple

from pydantic import SecretStr

_ALLOW_ENV_EXPANSION: ContextVar[bool] = ContextVar("_ALLOW_ENV_EXPANSION", default=False)
_ENV_VAR_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def is_trusted_env_expansion_active() -> bool:
    """检查当前是否处于受信任的本地配置加载上下文。"""
    return bool(_ALLOW_ENV_EXPANSION.get())


@contextmanager
def trusted_env_expansion() -> Iterator[None]:
    """仅在加载受信任的本地配置（settings.yaml / .env）时允许展开环境变量引用。"""
    token = _ALLOW_ENV_EXPANSION.set(True)
    try:
        yield
    finally:
        _ALLOW_ENV_EXPANSION.reset(token)


def validate_env_var_name(env_var: str) -> str:
    """校验环境变量名称合法性（严格匹配标准 POSIX 标识符 ^[A-Za-z_][A-Za-z0-9_]*$，拒绝首尾空白）。"""
    if not isinstance(env_var, str) or not env_var or not _ENV_VAR_NAME_PATTERN.fullmatch(env_var):
        raise ValueError(f"Invalid environment variable name in configuration reference: {env_var!r}")
    return env_var


def parse_env_reference(raw: str) -> Tuple[str, str]:
    """
    解析环境变量引用语法并校验变量名称合法性。

    支持语法:
    - ${ENV_VAR}
    - ${ENV_VAR:default_value}
    - $ENV_VAR
    """
    if not isinstance(raw, str):
        raise ValueError("Environment variable reference must be a string")

    expr = raw.strip()
    if not expr.startswith("$"):
        raise ValueError(f"Not an environment variable reference: {raw!r}")

    if expr.startswith("${"):
        if not expr.endswith("}"):
            raise ValueError(f"Malformed environment variable reference syntax (unclosed '${{'): {raw!r}")
        inner = expr[2:-1]
        if not inner:
            raise ValueError(f"Empty environment variable reference: {raw!r}")
        env_var_part, has_sep, default_val = inner.partition(":")
        env_var = validate_env_var_name(env_var_part)
        return env_var, (default_val if has_sep else "")

    if "{" in expr or "}" in expr:
        raise ValueError(f"Malformed environment variable reference syntax: {raw!r}")

    env_var = validate_env_var_name(expr[1:])
    return env_var, ""


def _extract_raw_string(value: Any) -> Optional[str]:
    """提取字符串或 SecretStr 中的原始字符串值。"""
    if isinstance(value, SecretStr):
        return value.get_secret_value()
    if isinstance(value, str):
        return value
    return None


def resolve_api_key_value(v: Any) -> Any:
    """
    统一校验并按信任边界解析配置模型中的 API Key 字段：
    1. 非环境变量引用（不以 $ 开头）保持原样返回；
    2. 非受信请求上下文传入环境变量引用时立即拒绝；
    3. 受信上下文中校验引用语法与变量名合法性后展开宿主机环境变量。
    """
    raw_str = _extract_raw_string(v)
    if raw_str is None:
        return v

    stripped = raw_str.strip()
    if not stripped.startswith("$"):
        return v

    if not is_trusted_env_expansion_active():
        raise ValueError(
            "Environment variable expansion in api_key is only allowed in trusted local configuration"
        )

    env_var, default_val = parse_env_reference(stripped)
    return os.getenv(env_var, default_val)
