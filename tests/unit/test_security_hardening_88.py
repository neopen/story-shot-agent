"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: test_security_hardening_88.py
@Description: 针对 Issue #88 与 PR #89 Review 的安全加固单元与网络层集成测试：
  1. 阻断非受信请求负载（含 BatchProcessRequest 的 llm/embed/image default & fallback）中的环境变量展开；
  2. Webhook callback_url SSRF 防护、DNS 超时/并发控制、混合记录与 IPv6 映射拦截，以及真实 TCP/TLS IP 固定连接验证；
  3. 公开默认配置接口脱敏与请求侧宿主机路径/数据库 URI 覆盖防护。
"""

import asyncio
import datetime
import json
import socket
import ssl
import tempfile
import threading
import time
from threading import BoundedSemaphore
from typing import Dict
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
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
)
from penshot.config.security import trusted_env_expansion
from penshot.neopen.shot_config import ShotConfig
from penshot.neopen.task.task_lifecycle_service import (
    TaskLifecycleService,
    resolve_and_pin_callback_target,
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
# 2. Webhook callback_url SSRF、DNS 边界与真实网络层 IP 固定测试
# ============================================================================


_LINK_LOCAL_METADATA_HOST = ".".join(["169", "254", "169", "254"])


@pytest.mark.parametrize(
    "unsafe_url",
    [
        "http://127.0.0.1:8000/callback",
        "http://localhost/callback",
        "http://sub.localhost/callback",
        "http://[::1]/callback",
        "http://[::ffff:127.0.0.1]/callback",
        "http://[::ffff:10.0.0.1]/callback",
        f"http://[::ffff:{_LINK_LOCAL_METADATA_HOST}]/callback",
        "http://[2002:7f00:1::1]/callback",
        "http://[64:ff9b::7f00:1]/callback",
        "http://[64:ff9b:1::808:808]/callback",
        f"http://{_LINK_LOCAL_METADATA_HOST}/latest/meta-data/",
        "http://10.0.0.1/callback",
        "http://100.64.0.1/callback",
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
    """validate_callback_url 应拒绝回环、内网、IPv4-mapped IPv6、过渡隧道私网、内部域名与非法协议"""
    with pytest.raises(ValueError):
        validate_callback_url(unsafe_url)


def test_validate_callback_url_allows_public_https():
    """合法的公网 HTTPS 回调地址应通过基础校验"""
    url = "https://webhook.example.com/penshot/callback"
    assert validate_callback_url(url) == url


@pytest.mark.parametrize(
    "fake_addrinfo",
    [
        [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))],
        # 混合公网与私网 DNS 记录：只要包含任意非公网地址必须整体拒绝
        [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.8", 443)),
        ],
        # 混合公网 IPv4 与 IPv4-mapped IPv6 私网/元数据地址记录
        [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::ffff:127.0.0.1", 443, 0, 0)),
        ],
        [
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", (f"::ffff:{_LINK_LOCAL_METADATA_HOST}", 443, 0, 0)),
        ],
    ],
)
def test_validate_callback_url_dns_resolution_blocks_private_and_mixed_records(fake_addrinfo):
    """resolve_dns=True 时若 DNS 返回私网、混合公私网或 IPv4-mapped IPv6 内网记录应拒绝"""
    with patch("socket.getaddrinfo", return_value=fake_addrinfo):
        with pytest.raises(ValueError, match="not a public routable address"):
            validate_callback_url("https://rebind.example.com/cb", resolve_dns=True)


def test_resolve_and_pin_callback_target_ipv4_and_ipv6_formatting():
    """resolve_and_pin_callback_target 应固定目标 IP 并保留原始 Host 与 HTTPS SNI"""
    ipv6_addrinfo = [
        (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2606:2800:220:1:248:1893:25c8:1946", 8443, 0, 0)),
    ]
    with patch("socket.getaddrinfo", return_value=ipv6_addrinfo):
        pinned = resolve_and_pin_callback_target("https://webhook.example.com:8443/v1/hook?ok=1")

    assert pinned.pinned_ip == "2606:2800:220:1:248:1893:25c8:1946"
    assert pinned.pinned_url == "https://[2606:2800:220:1:248:1893:25c8:1946]:8443/v1/hook?ok=1"
    assert pinned.headers == {"Host": "webhook.example.com:8443"}
    assert pinned.extensions == {"sni_hostname": "webhook.example.com"}


def test_dns_resolution_timeout_and_concurrency_limit():
    """DNS 解析应强制执行超时中断，且在慢查询真正结束前持续持有信号量配额"""
    release_block = threading.Event()
    entered_lookup = threading.Event()
    single_permit_sem = BoundedSemaphore(1)

    def slow_getaddrinfo(*_args, **_kwargs):
        entered_lookup.set()
        release_block.wait(timeout=2.0)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]

    try:
        with patch("socket.getaddrinfo", side_effect=slow_getaddrinfo):
            start = time.monotonic()
            with pytest.raises(ValueError, match="timed out"):
                resolve_and_pin_callback_target(
                    "https://slow.example.com/cb",
                    dns_timeout=0.05,
                    semaphore=single_permit_sem,
                )
            assert time.monotonic() - start < 0.8
            assert entered_lookup.is_set()

            # 慢查询线程尚未退出时，信号量配额仍被占用，后续并发请求必须被并发上限拦截
            with pytest.raises(ValueError, match="concurrency limit exceeded"):
                resolve_and_pin_callback_target(
                    "https://busy.example.com/cb",
                    dns_timeout=0.05,
                    semaphore=single_permit_sem,
                )
    finally:
        release_block.set()


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


def test_trigger_callback_async_disables_redirects_and_pins_resolved_ip():
    """_trigger_callback_async 发送前应固定已验证 IP，透传 Host/sni_hostname 且设置 follow_redirects=False"""
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
                "https://example.com/webhook?src=penshot",
                {"success": True},
            )
        )

    mock_async_client_cls.assert_called_once_with(follow_redirects=False, trust_env=False)
    mock_client.post.assert_awaited_once_with(
        "https://93.184.216.34/webhook?src=penshot",
        json={"task_id": "TSK_TEST_88", "success": True},
        headers={"Host": "example.com"},
        extensions={"sni_hostname": "example.com"},
        timeout=30,
    )


def _generate_self_signed_tls_pem(dns_name: str):
    """动态生成仅绑定指定 DNS SAN（不含任何 IP SAN）的内存测试证书，避免硬编码私钥文本。"""
    crypto_x509 = pytest.importorskip("cryptography.x509")
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = crypto_x509.Name([crypto_x509.NameAttribute(NameOID.COMMON_NAME, dns_name)])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        crypto_x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(crypto_x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(hours=1))
        .add_extension(crypto_x509.SubjectAlternativeName([crypto_x509.DNSName(dns_name)]), critical=False)
        .sign(key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )
    return cert_pem, key_pem


def test_real_network_https_ip_pinning_prevents_dns_rebinding_and_verifies_tls_sni():
    """
    真实网络层 TCP + TLS 集成测试（不 Mock HTTPX 客户端）：
    1. 模拟 DNS Rebinding：首次 DNS 查询返回已验证目标地址，若发生第二次 DNS 查询则立即抛错/切向陷阱地址；
    2. 真实 httpx.AsyncClient 建立 TLS 连接并发送请求，验证实际连接固定在首次解析 IP、TLS SNI 与证书主机名校验均使用原始域名、HTTP Host 头保留原始域名；
    3. 当证书 SAN 与原始域名不匹配时，TLS 握手严格拒绝连接。
    """

    async def _run_integration() -> None:
        cert_pem, key_pem = _generate_self_signed_tls_pem("webhook.example.com")
        bad_cert_pem, bad_key_pem = _generate_self_signed_tls_pem("attacker-mismatch.example.com")

        with (
            tempfile.NamedTemporaryFile(suffix=".pem") as cf,
            tempfile.NamedTemporaryFile(suffix=".pem") as kf,
            tempfile.NamedTemporaryFile(suffix=".pem") as bad_cf,
            tempfile.NamedTemporaryFile(suffix=".pem") as bad_kf,
        ):
            cf.write(cert_pem)
            cf.flush()
            kf.write(key_pem)
            kf.flush()
            bad_cf.write(bad_cert_pem)
            bad_cf.flush()
            bad_kf.write(bad_key_pem)
            bad_kf.flush()

            observed: Dict[str, object] = {"requests": 0}
            server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            server_ctx.load_cert_chain(cf.name, kf.name)

            def _sni_cb(_ssl_sock, server_name, _ctx):
                observed["sni"] = server_name

            server_ctx.sni_callback = _sni_cb

            async def _handle_tls(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
                raw_head = await reader.readuntil(b"\r\n\r\n")
                header_text = raw_head.decode("latin1")
                headers_map: Dict[str, str] = {}
                for line in header_text.split("\r\n")[1:]:
                    if ":" in line:
                        k, val = line.split(":", 1)
                        headers_map[k.strip().lower()] = val.strip()
                content_len = int(headers_map.get("content-length", "0"))
                body_bytes = await reader.readexactly(content_len) if content_len else b""
                observed["requests"] = int(observed["requests"]) + 1
                observed["host_header"] = headers_map.get("host")
                observed["local_addr"] = writer.get_extra_info("sockname")
                observed["payload"] = json.loads(body_bytes.decode("utf-8"))
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nOK")
                await writer.drain()
                writer.close()

            real_getaddrinfo = socket.getaddrinfo
            dns_lookup_count = {"domain_queries": 0}

            server = await asyncio.start_server(_handle_tls, "127.0.0.1", 0, ssl=server_ctx)
            port = server.sockets[0].getsockname()[1]

            def _rebinding_getaddrinfo(host, srv_port, *args, **kwargs):
                if host == "webhook.example.com":
                    dns_lookup_count["domain_queries"] += 1
                    if dns_lookup_count["domain_queries"] > 1:
                        raise AssertionError("DNS rebinding vulnerability: unexpected second DNS resolution!")
                    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", srv_port))]
                return real_getaddrinfo(host, srv_port, *args, **kwargs)

            client_ssl_ctx = ssl.create_default_context(cafile=cf.name)
            repository = TaskRepository(task_ttl_seconds=3600)
            registry = WorkflowRegistry(max_cache_size=4)
            service = TaskLifecycleService(repository, registry)

            async with server:
                with patch("socket.getaddrinfo", side_effect=_rebinding_getaddrinfo):
                    await service._trigger_callback_async(
                        "TSK_REAL_NET_89",
                        f"https://webhook.example.com:{port}/callback",
                        {"success": True},
                        ssl_verify=client_ssl_ctx,
                        ip_validator=lambda _ip: None,
                    )

            assert dns_lookup_count["domain_queries"] == 1
            assert observed["requests"] == 1
            assert observed["sni"] == "webhook.example.com"
            assert observed["host_header"] == f"webhook.example.com:{port}"
            assert observed["local_addr"][0] == "127.0.0.1"
            assert observed["payload"] == {"task_id": "TSK_REAL_NET_89", "success": True}

            # 验证证书主机名不匹配时真实 TLS 握手被严格阻断
            mismatch_received = {"count": 0}
            bad_server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            bad_server_ctx.load_cert_chain(bad_cf.name, bad_kf.name)

            async def _handle_bad_tls(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
                await reader.read(1024)
                mismatch_received["count"] += 1
                writer.close()

            bad_server = await asyncio.start_server(_handle_bad_tls, "127.0.0.1", 0, ssl=bad_server_ctx)
            bad_port = bad_server.sockets[0].getsockname()[1]
            bad_client_ctx = ssl.create_default_context(cafile=bad_cf.name)

            async with bad_server:
                with patch(
                    "socket.getaddrinfo",
                    return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", bad_port))],
                ):
                    pinned_bad = resolve_and_pin_callback_target(
                        f"https://webhook.example.com:{bad_port}/callback",
                        ip_validator=lambda _ip: None,
                    )
                async with httpx.AsyncClient(
                    follow_redirects=False,
                    trust_env=False,
                    verify=bad_client_ctx,
                ) as raw_client:
                    with pytest.raises(httpx.ConnectError):
                        await raw_client.post(
                            pinned_bad.pinned_url,
                            headers=pinned_bad.headers,
                            extensions=pinned_bad.extensions,
                            json={"probe": 1},
                        )

            assert mismatch_received["count"] == 0

    asyncio.run(_run_integration())


# ============================================================================
# 3. 公开配置脱敏、宿主机路径保护与 BatchProcessRequest image/llm/embed 校验
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
            checkpoint_dir="/etc/arbitrary",
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
            "image": {
                "default": {"api_key": "0" * 16},
                "fallback": {"api_key": "1" * 16},
            },
        },
    )
    assert "checkpoint_dir" not in batch_req.config
    assert "postgres_uri" not in batch_req.config
    assert batch_req.config["default_shot_duration"] == 4.0


@pytest.mark.parametrize(
    "untrusted_batch_cfg",
    [
        {"llm": {"api_key": "${OPENAI_API_KEY}"}},
        {"llm": {"default": {"api_key": "${OPENAI_API_KEY}"}}},
        {"llm": {"fallback": {"api_key": "$FALLBACK_LLM_KEY"}}},
        {"embed": {"api_key": "${EMBED_API_KEY}"}},
        {"embed": {"default": {"api_key": "${EMBED_API_KEY}"}}},
        {"embed": {"fallback": {"api_key": "$FALLBACK_EMBED_KEY"}}},
        {"image": {"api_key": "${IMAGE_API_KEY}"}},
        {"image": {"default": {"api_key": "${IMAGE_DEFAULT_KEY}"}}},
        {"image": {"fallback": {"api_key": "${IMAGE_FALLBACK_KEY:leak}"}}},
        {"image": {"default": {"api_key": "0" * 12}, "api_key": "${HIDDEN_TOP_KEY}"}},
    ],
)
def test_batch_process_request_blocks_env_expansion_across_llm_embed_and_image(untrusted_batch_cfg):
    """BatchProcessRequest 应对 llm、embed、image 的平铺及 default/fallback 配置统一阻断环境变量展开"""
    with pytest.raises(ValueError, match="trusted local configuration"):
        BatchProcessRequest(scripts=["测试剧本"], config=untrusted_batch_cfg)
