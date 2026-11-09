"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: test_security_hardening_88.py
@Description: 针对 Issue #88 的三项安全加固单元测试：
  1. 阻断非受信请求负载中的 ${ENV_VAR} / $ENV_VAR 环境变量展开；
  2. Webhook callback_url SSRF 校验（协议、内网/回环/元数据地址、DNS 解析与禁用重定向）；
  3. 公开默认配置接口脱敏与请求侧宿主机路径/数据库 URI 覆盖防护。
"""

import asyncio
import socket
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from penshot.api.rest_api import (
    BatchProcessRequest,
    ProcessRequest,
    PublicConfigResponse,
    SyncProcessRequest,
    get_default_config,
)
from penshot.config.config import settings
from penshot.config.config_models import (
    EmbeddingBaseConfig,
    ImageBaseConfig,
    LLMBaseConfig,
    trusted_env_expansion,
)
from penshot.neopen.shot_config import ShotConfig
from penshot.neopen.task.task_lifecycle_service import (
    TaskLifecycleService,
    validate_callback_url,
)
from penshot.neopen.task.task_repository import TaskRepository
from penshot.neopen.task.workflow_registry import WorkflowRegistry


# ============================================================================
# 1. API Key 环境变量展开信任边界测试
# ============================================================================


def test_untrusted_api_key_rejects_env_expansion(monkeypatch):
    """非受信上下文（如外部 HTTP 请求反序列化）传入 ${VAR} 或 $VAR 应直接拒绝"""
    monkeypatch.setenv("PENSHOT_TEST_SECRET_88", "super-secret-token")

    with pytest.raises(ValueError, match="trusted local configuration"):
        LLMBaseConfig(api_key="${PENSHOT_TEST_SECRET_88}")

    with pytest.raises(ValueError, match="trusted local configuration"):
        EmbeddingBaseConfig(api_key="$PENSHOT_TEST_SECRET_88")

    with pytest.raises(ValueError, match="trusted local configuration"):
        ImageBaseConfig(api_key="${PENSHOT_TEST_SECRET_88:fallback}")


def test_trusted_env_expansion_resolves_env_var_and_default(monkeypatch):
    """在 trusted_env_expansion() 上下文内（本地配置加载）应正常展开环境变量与默认值"""
    monkeypatch.setenv("PENSHOT_TEST_SECRET_88", "resolved-local-secret")
    monkeypatch.delenv("PENSHOT_MISSING_SECRET_88", raising=False)

    with trusted_env_expansion():
        llm_cfg = LLMBaseConfig(api_key="${PENSHOT_TEST_SECRET_88}")
        embed_cfg = EmbeddingBaseConfig(api_key="$PENSHOT_TEST_SECRET_88")
        image_cfg = ImageBaseConfig(api_key="${PENSHOT_MISSING_SECRET_88:default-img-key}")

    assert llm_cfg.api_key.get_secret_value() == "resolved-local-secret"
    assert embed_cfg.api_key.get_secret_value() == "resolved-local-secret"
    assert image_cfg.api_key.get_secret_value() == "default-img-key"

    # 退出上下文后应恢复拒绝状态
    with pytest.raises(ValueError, match="trusted local configuration"):
        LLMBaseConfig(api_key="${PENSHOT_TEST_SECRET_88}")


def test_literal_api_key_still_accepted_outside_trusted_context():
    """普通字面量 API Key 在请求配置中仍可正常传入"""
    cfg = LLMBaseConfig(api_key="sk-literal-user-key-12345")
    assert cfg.api_key.get_secret_value() == "sk-literal-user-key-12345"


# ============================================================================
# 2. Webhook callback_url SSRF 防护测试
# ============================================================================


_LINK_LOCAL_METADATA_HOST = ".".join(["169", "254", "169", "254"])


@pytest.mark.parametrize(
    "unsafe_url",
    [
        "http://127.0.0.1:8000/callback",
        "http://localhost/callback",
        "http://sub.localhost/callback",
        "http://[::1]/callback",
        f"http://{_LINK_LOCAL_METADATA_HOST}/latest/meta-data/",
        "http://10.0.0.1/callback",
        "http://172.16.0.10/callback",
        "http://192.168.1.1/callback",
        "http://0.0.0.0/callback",
        "http://internal-service.local/callback",
        "http://metadata.internal/callback",
        "ftp://example.com/callback",
        "file" + ":///etc/passwd",
        "https://user:pass@example.com/callback",
        "https://@example.com/callback",
        "https://example.com:0/callback",
        "",
    ],
)
def test_validate_callback_url_rejects_unsafe_targets(unsafe_url):
    """validate_callback_url 应拒绝回环、内网、链路本地、内部域名、非 HTTP 协议与内嵌凭据"""
    with pytest.raises(ValueError):
        validate_callback_url(unsafe_url)


def test_validate_callback_url_allows_public_https():
    """合法的公网 HTTPS 回调地址应通过基础校验"""
    url = "https://webhook.example.com/penshot/callback"
    assert validate_callback_url(url) == url


def test_validate_callback_url_dns_resolution_blocks_private_ip():
    """resolve_dns=True 时若域名解析到私网或回环 IP 应拒绝"""
    fake_addrinfo = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
    ]
    with patch("socket.getaddrinfo", return_value=fake_addrinfo):
        with pytest.raises(ValueError, match="not a public routable address"):
            validate_callback_url("https://rebind.example.com/cb", resolve_dns=True)


def test_process_request_and_set_callback_reject_ssrf_url():
    """ProcessRequest 与 TaskLifecycleService.set_callback 均应拦截 SSRF 回调地址"""
    with pytest.raises(ValueError):
        ProcessRequest(script="测试剧本", callback_url=f"http://{_LINK_LOCAL_METADATA_HOST}/latest/meta-data/")

    repository = TaskRepository(task_ttl_seconds=3600)
    registry = WorkflowRegistry(max_cache_size=4)
    service = TaskLifecycleService(repository, registry)
    _, task_id = service.create_task("测试剧本")
    try:
        with pytest.raises(ValueError):
            service.set_callback(task_id, "http://127.0.0.1:9000/internal")
    finally:
        service.delete_task(task_id)


def test_trigger_callback_async_disables_redirects_and_validates_dns():
    """_trigger_callback_async 发送前应执行 DNS 校验并显式设置 follow_redirects=False"""
    repository = TaskRepository(task_ttl_seconds=3600)
    registry = WorkflowRegistry(max_cache_size=4)
    service = TaskLifecycleService(repository, registry)

    public_addrinfo = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
    ]
    mock_client = AsyncMock()
    mock_client_cm = MagicMock()
    mock_client_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_cm.__aexit__ = AsyncMock(return_value=None)

    with patch("socket.getaddrinfo", return_value=public_addrinfo), patch(
        "httpx.AsyncClient", return_value=mock_client_cm
    ) as mock_async_client_cls:
        asyncio.run(
            service._trigger_callback_async(
                "TSK_TEST_88",
                "https://example.com/webhook",
                {"success": True},
            )
        )

    mock_async_client_cls.assert_called_once_with(follow_redirects=False, trust_env=False)
    mock_client.post.assert_awaited_once()


# ============================================================================
# 3. 公开配置脱敏与宿主机路径/数据库 URI 覆盖防护测试
# ============================================================================


def test_get_default_config_redacts_internal_paths_and_credentials():
    """GET /api/v1/config 返回的 PublicConfigResponse 不得暴露宿主机路径、数据库连接串与密钥对象"""
    resp = get_default_config()
    assert isinstance(resp, PublicConfigResponse)

    dumped = resp.model_dump()
    assert "checkpoint_dir" not in dumped
    assert "postgres_uri" not in dumped
    assert "llm" not in dumped
    assert "embed" not in dumped
    assert "api_key" not in str(dumped)
    assert dumped["enable_llm"] is True
    assert dumped["max_shot_duration"] == 60.0


def test_request_config_sanitizes_checkpoint_dir_and_postgres_uri():
    """外部请求传入的 checkpoint_dir 和 postgres_uri 应被强制重置为服务端安全值"""
    expected_checkpoint_dir = settings.get_data_paths().get("data_checkpoint")

    req = ProcessRequest(
        script="测试剧本",
        config=ShotConfig(
            checkpoint_dir="/tmp/attacker-controlled-path",
            postgres_uri="postgresql://attacker:pass@10.0.0.99:5432/db",
        ),
    )
    assert req.config.checkpoint_dir == expected_checkpoint_dir
    assert req.config.postgres_uri is None

    sync_req = SyncProcessRequest(
        script="测试剧本",
        config=ShotConfig(
            checkpoint_dir="/etc/ arbitrary",
            postgres_uri="postgresql://attacker:pass@127.0.0.1:5432/db",
        ),
    )
    assert sync_req.config.checkpoint_dir == expected_checkpoint_dir
    assert sync_req.config.postgres_uri is None

    batch_req = BatchProcessRequest(
        scripts=["测试剧本"],
        config={
            "checkpoint_dir": "/tmp/evil",
            "postgres_uri": "postgresql://evil/db",
            "default_shot_duration": 4.0,
        },
    )
    assert "checkpoint_dir" not in batch_req.config
    assert "postgres_uri" not in batch_req.config
    assert batch_req.config["default_shot_duration"] == 4.0

    with pytest.raises(ValueError, match="trusted local configuration"):
        BatchProcessRequest(
            scripts=["测试剧本"],
            config={"llm": {"api_key": "${OPENAI_API_KEY}"}},
        )
