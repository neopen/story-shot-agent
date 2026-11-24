"""
Copyright 2025 neopen
SPDX-License-Identifier: Apache-2.0
Licensed under the Apache License, Version 2.0.
See the LICENSE and NOTICE files for details.

@FileName: __init__.py
@Description: 统一安全工具包 - 汇总 SSRF/回调防护、环境变量引用解析与请求配置脱敏。
``request_config`` 依赖配置模型，故通过 PEP 562 惰性导出，避免 config 与 security 循环导入。
@Author: neopen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/11/17
"""

from typing import Any

from penshot.security.env_refs import (
    is_trusted_env_expansion_active,
    parse_env_reference,
    resolve_api_key_value,
    trusted_env_expansion,
    validate_env_var_name,
)
from penshot.security.ssrf import (
    PinnedCallbackTarget,
    SsrfGuard,
    SsrfPolicy,
    assert_public_ip,
    post_json_pinned,
    resolve_and_pin_callback_target,
    validate_callback_url,
)

__all__ = [
    # env_refs
    "is_trusted_env_expansion_active",
    "parse_env_reference",
    "resolve_api_key_value",
    "trusted_env_expansion",
    "validate_env_var_name",
    # ssrf
    "PinnedCallbackTarget",
    "SsrfGuard",
    "SsrfPolicy",
    "assert_public_ip",
    "post_json_pinned",
    "resolve_and_pin_callback_target",
    "validate_callback_url",
    # request_config（惰性导出）
    "sanitize_batch_config",
    "sanitize_shot_config",
]

_REQUEST_CONFIG_EXPORTS = frozenset({"sanitize_batch_config", "sanitize_shot_config"})


def __getattr__(name: str) -> Any:
    if name in _REQUEST_CONFIG_EXPORTS:
        from penshot.security import request_config

        return getattr(request_config, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
