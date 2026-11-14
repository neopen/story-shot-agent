"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: test_env_resolver.py
@Description: 配置安全工具模块 penshot.config.security.env_resolver 独立单元测试
"""

import os
import pytest
from pydantic import SecretStr

from penshot.config.config import Settings
from penshot.config.config_models import (
    EmbeddingBaseConfig,
    ImageBaseConfig,
    LLMBaseConfig,
)
from penshot.config.security import (
    is_trusted_env_expansion_active,
    parse_env_reference,
    resolve_api_key_value,
    trusted_env_expansion,
    validate_env_var_name,
)


def test_trusted_context_lifecycle_and_nesting():
    """trusted_env_expansion 应正确维护嵌套上下文并在异常退出时恢复默认关闭状态"""
    assert is_trusted_env_expansion_active() is False

    with trusted_env_expansion():
        assert is_trusted_env_expansion_active() is True
        with trusted_env_expansion():
            assert is_trusted_env_expansion_active() is True
        assert is_trusted_env_expansion_active() is True

    assert is_trusted_env_expansion_active() is False

    with pytest.raises(RuntimeError):
        with trusted_env_expansion():
            assert is_trusted_env_expansion_active() is True
            raise RuntimeError("boom")

    assert is_trusted_env_expansion_active() is False


@pytest.mark.parametrize(
    "valid_name",
    [
        "OPENAI_API_KEY",
        "_INTERNAL_KEY",
        "QWEN_KEY_2",
        "a",
    ],
)
def test_validate_env_var_name_accepts_posix_identifiers(valid_name):
    assert validate_env_var_name(valid_name) == valid_name


@pytest.mark.parametrize(
    "invalid_name",
    [
        "",
        "   ",
        " OPENAI_API_KEY",
        "OPENAI_API_KEY ",
        "123_INVALID",
        "OPENAI-API-KEY",
        "KEY;INJECT_CMD",
        "KEY$OTHER",
        "KEY.SUB",
        "KEY WITH SPACE",
    ],
)
def test_validate_env_var_name_rejects_illegal_names(invalid_name):
    with pytest.raises(ValueError, match="Invalid environment variable name"):
        validate_env_var_name(invalid_name)


def test_parse_env_reference_supported_syntaxes():
    assert parse_env_reference("${OPENAI_API_KEY}") == ("OPENAI_API_KEY", "")
    assert parse_env_reference("${OPENAI_API_KEY:sk-fallback:123}") == ("OPENAI_API_KEY", "sk-fallback:123")
    assert parse_env_reference("$DEEPSEEK_API_KEY") == ("DEEPSEEK_API_KEY", "")


@pytest.mark.parametrize(
    "malformed_ref",
    [
        "$",
        "${}",
        "${:default}",
        "${UNCLOSED",
        "$BAD{BRACE}",
        "${123BAD}",
        "${BAD-NAME:fallback}",
        "$BAD-NAME",
        "plain_text",
    ],
)
def test_parse_env_reference_rejects_malformed_or_illegal_references(malformed_ref):
    with pytest.raises(ValueError):
        parse_env_reference(malformed_ref)


def test_resolve_api_key_value_handles_secretstr_and_untrusted_rejection(monkeypatch):
    """即使传入 SecretStr('${VAR}')，在非受信上下文中也必须被拦截"""
    monkeypatch.setenv("PENSHOT_ENV_RESOLVER_KEY", "secret-val-99")

    with pytest.raises(ValueError, match="trusted local configuration"):
        resolve_api_key_value("${PENSHOT_ENV_RESOLVER_KEY}")

    with pytest.raises(ValueError, match="trusted local configuration"):
        resolve_api_key_value(SecretStr("${PENSHOT_ENV_RESOLVER_KEY}"))

    with trusted_env_expansion():
        assert resolve_api_key_value(SecretStr("${PENSHOT_ENV_RESOLVER_KEY}")) == "secret-val-99"
        with pytest.raises(ValueError, match="Invalid environment variable name"):
            resolve_api_key_value("${123_ILLEGAL}")
        with pytest.raises(ValueError, match="Malformed environment variable reference"):
            resolve_api_key_value("${UNCLOSED_VAR")


@pytest.mark.parametrize("model_cls", [LLMBaseConfig, EmbeddingBaseConfig, ImageBaseConfig])
def test_all_provider_models_share_unified_security_policy(monkeypatch, model_cls):
    """LLMBaseConfig、EmbeddingBaseConfig、ImageBaseConfig 应统一遵循 env_resolver 安全策略"""
    monkeypatch.setenv("PENSHOT_SHARED_MODEL_KEY", "shared-secret")

    # 1. 非受信上下文拒绝展开
    with pytest.raises(ValueError, match="trusted local configuration"):
        model_cls(api_key="${PENSHOT_SHARED_MODEL_KEY}")

    # 2. 受信上下文允许合法展开，但拒绝非法变量名/语法
    with trusted_env_expansion():
        cfg = model_cls(api_key="${PENSHOT_SHARED_MODEL_KEY}")
        assert cfg.api_key.get_secret_value() == "shared-secret"

        with pytest.raises(ValueError):
            model_cls(api_key="${BAD-ENV-NAME}")

    # 3. 普通字面量密钥保持兼容
    literal_cfg = model_cls(api_key="0" * 16)
    assert literal_cfg.api_key.get_secret_value() == "0" * 16


def test_settings_preserves_yaml_and_env_override_priority(monkeypatch):
    """重构为独立安全模块后，Settings 的系统环境变量覆盖 YAML 及 ${VAR} 展开兼容行为保持不变"""
    monkeypatch.delenv("PENSHOT_LLM__DEFAULT__MODEL_NAME", raising=False)
    monkeypatch.delenv("PENSHOT_LLM__DEFAULT__API_KEY", raising=False)
    base_settings = Settings()
    yaml_model_name = base_settings.llm.default.model_name
    assert yaml_model_name in {"gpt-4o", "gpt-4o-mini"}

    monkeypatch.setenv("PENSHOT_RESOLVER_TEST_KEY", "env-expanded-secret")
    monkeypatch.setenv("PENSHOT_LLM__DEFAULT__MODEL_NAME", "gpt-4.1-mini-from-env")
    monkeypatch.setenv("PENSHOT_LLM__DEFAULT__API_KEY", "${PENSHOT_RESOLVER_TEST_KEY}")

    loaded_from_env = Settings()
    assert loaded_from_env.llm.default.model_name == "gpt-4.1-mini-from-env"
    assert loaded_from_env.llm.default.api_key.get_secret_value() == "env-expanded-secret"
    assert os.getenv("PENSHOT_RESOLVER_TEST_KEY") == "env-expanded-secret"
