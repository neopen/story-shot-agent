"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: test_ssrf_policy.py
@Description: SsrfPolicy/SsrfGuard 扩展点测试：验证可配置放行内网与精确主机白名单，
且默认策略仍保持严格拒绝（证明可扩展但默认不弱化）。
"""

import socket
from unittest.mock import patch

import pytest

from penshot.security.ssrf import SsrfGuard, SsrfPolicy


def _guard(**kwargs) -> SsrfGuard:
    return SsrfGuard(SsrfPolicy(**kwargs))


def test_default_policy_blocks_private_and_loopback_literals():
    """默认策略应拒绝私网、回环与云元数据地址。"""
    guard = _guard()
    try:
        for url in (
            "http://10.0.0.5/hook",
            "http://192.168.1.10/hook",
            "http://127.0.0.1/hook",
            "http://169.254.169.254/latest/meta-data",
        ):
            with pytest.raises(ValueError):
                guard.validate(url)
    finally:
        guard.close()


def test_allow_private_networks_permits_rfc1918_but_not_loopback():
    """allow_private_networks=True 仅放宽私网段，回环/链路本地仍拒绝。"""
    guard = _guard(allow_private_networks=True)
    try:
        assert guard.validate("http://10.0.0.5:8080/hook") == (
            "http://10.0.0.5:8080/hook"
        )
        assert guard.validate("http://192.168.1.10/hook") == (
            "http://192.168.1.10/hook"
        )
        with pytest.raises(ValueError):
            guard.validate("http://127.0.0.1/hook")
        with pytest.raises(ValueError):
            guard.validate("http://169.254.169.254/hook")
    finally:
        guard.close()


def test_host_allowlist_permits_specific_internal_hostname():
    """host_allowlist 精确放行默认被禁止的内部主机名，其余内部域名仍拒绝。"""
    guard = _guard(host_allowlist=("localhost",))
    try:
        assert guard.validate("http://localhost:9000/hook") == (
            "http://localhost:9000/hook"
        )
        with pytest.raises(ValueError):
            guard.validate("http://app.internal/hook")
    finally:
        guard.close()


def test_allowlisted_literal_ip_pins_without_dns_lookup():
    """白名单中的私网字面量 IP 无需 DNS 解析即可固定目标。"""
    guard = _guard(host_allowlist=("10.0.0.5",))
    try:
        with patch("socket.getaddrinfo") as mock_lookup:
            target = guard.resolve_and_pin("http://10.0.0.5:8080/hook")
        mock_lookup.assert_not_called()
        assert target.pinned_ip == "10.0.0.5"
        assert target.pinned_url == "http://10.0.0.5:8080/hook"
    finally:
        guard.close()


def test_allowlisted_hostname_skips_ip_validation_on_dns():
    """白名单主机名解析出的内网 IP 不再被拒绝（精确放行，而非全局放宽）。"""
    guard = _guard(host_allowlist=("internal.corp",))
    addrinfo = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.20.30.40", 8080)),
    ]
    try:
        with patch("socket.getaddrinfo", return_value=addrinfo):
            target = guard.resolve_and_pin("http://internal.corp:8080/hook")
        assert target.pinned_ip == "10.20.30.40"
        assert target.headers["Host"] == "internal.corp:8080"
    finally:
        guard.close()


def test_default_policy_rejects_private_record_from_dns():
    """默认策略下，解析到私网记录的主机名仍被拒绝。"""
    guard = _guard()
    addrinfo = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.7", 80))]
    try:
        with patch("socket.getaddrinfo", return_value=addrinfo):
            with pytest.raises(ValueError):
                guard.resolve_and_pin("http://webhook.example.com/hook")
    finally:
        guard.close()


def test_custom_allowed_schemes_restricts_transport():
    """allowed_schemes 可收窄允许的协议集合。"""
    guard = _guard(allowed_schemes=("https",))
    try:
        assert guard.validate("https://example.com/hook") == (
            "https://example.com/hook"
        )
        with pytest.raises(ValueError):
            guard.validate("http://example.com/hook")
    finally:
        guard.close()
