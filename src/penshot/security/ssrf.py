"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: ssrf.py
@Description: SSRF / DNS / HTTPS 回调 URL 防护与安全出站：
  1. 静态校验协议、认证凭据、端口、内部主机名与私网字面量 IP；
  2. 在超时与并发控制下解析 DNS 并校验全部记录均为公网地址；
  3. 将实际 TCP 连接固定到已验证 IP（防 DNS Rebinding），保留原始 Host 与 HTTPS SNI。
本模块仅依赖标准库（httpx 在发送函数内惰性导入），可独立复用；通过 SsrfPolicy 扩展放行策略。
@Author: NeoPen
@Time: 2026/11/17
"""

from __future__ import annotations

import asyncio
import functools
import ipaddress
import socket
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from threading import BoundedSemaphore
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse, urlunparse

_IPAddress = Union[ipaddress.IPv4Address, ipaddress.IPv6Address]
IpValidator = Callable[[str], None]

_DEFAULT_FORBIDDEN_HOSTNAMES = frozenset({"localhost", "localhost.localdomain"})
_DEFAULT_FORBIDDEN_HOST_SUFFIXES = (".localhost", ".local", ".internal")
_NAT64_WELL_KNOWN_NETWORK = ipaddress.ip_network("64:ff9b::/96")
_NAT64_LOCAL_USE_NETWORK = ipaddress.ip_network("64:ff9b:1::/48")


@dataclass(frozen=True)
class SsrfPolicy:
    """可配置的 SSRF 防护策略，便于在不同部署场景间复用。

    默认策略拒绝一切非公网目标；如需放行内网回调，可显式设置
    ``allow_private_networks=True``（仅放宽 RFC1918/ULA 私网，回环、链路本地、
    元数据与保留地址仍会被拒绝），或用 ``host_allowlist`` 精确放行特定主机名。
    """

    allowed_schemes: Tuple[str, ...] = ("http", "https")
    forbidden_hostnames: frozenset[str] = _DEFAULT_FORBIDDEN_HOSTNAMES
    forbidden_host_suffixes: Tuple[str, ...] = _DEFAULT_FORBIDDEN_HOST_SUFFIXES
    allow_private_networks: bool = False
    host_allowlist: Tuple[str, ...] = ()
    dns_timeout: float = 5.0
    max_concurrent_lookups: int = 8


@dataclass(frozen=True)
class PinnedCallbackTarget:
    """经过 SSRF 与 DNS 校验并固定目标公网 IP 的回调请求参数。"""

    original_url: str
    pinned_url: str
    pinned_ip: str
    hostname: str
    headers: Dict[str, str]
    extensions: Dict[str, Any]


def _extract_embedded_ipv4(
    ip_obj: ipaddress.IPv6Address,
) -> Optional[ipaddress.IPv4Address]:
    """提取 IPv6 过渡机制（IPv4-mapped / 6to4 / Teredo / RFC 6052 NAT64 /96）内嵌的 IPv4 地址。"""
    if ip_obj.ipv4_mapped is not None:
        return ip_obj.ipv4_mapped
    if ip_obj.sixtofour is not None:
        return ip_obj.sixtofour
    if ip_obj.teredo is not None:
        return ip_obj.teredo[1]
    if ip_obj in _NAT64_WELL_KNOWN_NETWORK:
        return ipaddress.IPv4Address(int(ip_obj) & 0xFFFFFFFF)
    return None


def _is_blocked_ip_object(ip_obj: _IPAddress, *, allow_private_networks: bool) -> bool:
    """判断单个 IP 是否属于不可达/需拒绝的地址。

    含 RFC 8215 本地 NAT64 前缀 64:ff9b:1::/48。``allow_private_networks`` 为真时
    仅放宽私网段（RFC1918 / IPv6 ULA），但仍拒绝回环、链路本地、多播、保留与未指定地址。
    """
    if isinstance(ip_obj, ipaddress.IPv6Address) and ip_obj in _NAT64_LOCAL_USE_NETWORK:
        return True
    if allow_private_networks:
        return (
            ip_obj.is_loopback
            or ip_obj.is_link_local
            or ip_obj.is_multicast
            or ip_obj.is_reserved
            or ip_obj.is_unspecified
        )
    return (
        ip_obj.is_private
        or ip_obj.is_loopback
        or ip_obj.is_link_local
        or ip_obj.is_multicast
        or ip_obj.is_reserved
        or ip_obj.is_unspecified
        or not ip_obj.is_global
    )


def assert_public_ip(ip_str: str, *, allow_private_networks: bool = False) -> None:
    """校验 IP 为可达地址，拒绝回环、私网、链路本地、多播、保留及过渡内嵌私网地址。"""
    if "%" in ip_str:
        raise ValueError(
            f"Callback URL target IP must not include zone identifier: {ip_str}"
        )
    ip_obj = ipaddress.ip_address(ip_str)
    if isinstance(ip_obj, ipaddress.IPv6Address):
        embedded_v4 = _extract_embedded_ipv4(ip_obj)
        if embedded_v4 is not None and _is_blocked_ip_object(
            embedded_v4, allow_private_networks=allow_private_networks
        ):
            raise ValueError(
                f"Callback URL target IP is not a public routable address: {ip_str}"
            )
    if _is_blocked_ip_object(ip_obj, allow_private_networks=allow_private_networks):
        raise ValueError(
            f"Callback URL target IP is not a public routable address: {ip_str}"
        )


def _format_netloc_host(host_str: str) -> str:
    """为 IPv6 字面量添加方括号以构造合法的 URL netloc 或 Host 头。"""
    return f"[{host_str}]" if ":" in host_str else host_str


def _format_host_with_port(host_base: str, explicit_port: Optional[int]) -> str:
    """按需拼接显式端口。"""
    return f"{host_base}:{explicit_port}" if explicit_port is not None else host_base


class SsrfGuard:
    """可复用的 SSRF 防护器：持有策略与独立的 DNS 解析执行器/并发信号量。

    每个实例自带解析资源，便于按业务分配配额、隔离慢查询，并通过策略定制放行规则。
    """

    def __init__(self, policy: Optional[SsrfPolicy] = None) -> None:
        self.policy = policy or SsrfPolicy()
        self._allowlist = frozenset(h.lower() for h in self.policy.host_allowlist)
        self._semaphore = BoundedSemaphore(self.policy.max_concurrent_lookups)
        self._executor = ThreadPoolExecutor(
            max_workers=self.policy.max_concurrent_lookups,
            thread_name_prefix="penshot-dns",
        )

    def close(self) -> None:
        """释放底层 DNS 解析执行器资源。"""
        self._executor.shutdown(wait=False)

    def _is_allowlisted(self, hostname: str) -> bool:
        return hostname in self._allowlist

    def assert_public_ip(self, ip_str: str) -> None:
        """按当前策略校验 IP 可达性。"""
        assert_public_ip(
            ip_str, allow_private_networks=self.policy.allow_private_networks
        )

    def _validate_scheme_and_auth(self, parsed: Any) -> Tuple[str, Optional[int]]:
        """校验回调 URL 的协议、认证凭据及端口合法性。"""
        scheme = parsed.scheme.lower()
        if scheme not in self.policy.allowed_schemes:
            allowed = " or ".join(self.policy.allowed_schemes)
            raise ValueError(f"callback_url scheme must be {allowed}")
        if (
            parsed.username is not None
            or parsed.password is not None
            or "@" in (parsed.netloc or "")
        ):
            raise ValueError("callback_url must not contain embedded credentials")
        try:
            explicit_port = parsed.port
        except ValueError as e:
            raise ValueError(f"callback_url contains an invalid port: {e}") from e
        if explicit_port is not None and not (1 <= explicit_port <= 65535):
            raise ValueError(f"callback_url port out of valid range: {explicit_port}")
        return scheme, explicit_port

    def _parse_and_validate(
        self, callback_url: str, *, ip_validator: IpValidator
    ) -> Tuple[str, Any, str, Optional[int], str, bool]:
        """解析回调 URL 并执行静态协议、端口、凭据、主机名及字面量 IP 校验。"""
        if not isinstance(callback_url, str) or not callback_url.strip():
            raise ValueError("callback_url must be a non-empty URL string")

        cleaned = callback_url.strip()
        parsed = urlparse(cleaned)
        scheme, explicit_port = self._validate_scheme_and_auth(parsed)

        hostname = (parsed.hostname or "").strip().lower().rstrip(".")
        if not hostname:
            raise ValueError("callback_url must include a valid hostname")

        allowlisted = self._is_allowlisted(hostname)
        if not allowlisted and (
            hostname in self.policy.forbidden_hostnames
            or hostname.endswith(self.policy.forbidden_host_suffixes)
        ):
            raise ValueError(f"callback_url hostname is not permitted: {hostname}")

        try:
            ipaddress.ip_address(hostname.split("%", 1)[0])
            is_literal_ip = True
        except ValueError:
            is_literal_ip = False

        if is_literal_ip and not allowlisted:
            ip_validator(hostname)

        return cleaned, parsed, scheme, explicit_port, hostname, is_literal_ip

    def _extract_unique_ips(
        self,
        addr_infos: List[Any],
        hostname: str,
        ip_validator: IpValidator,
        *,
        validate_ips: bool,
    ) -> List[str]:
        """校验 DNS 记录（可选）并按顺序去重。"""
        if not addr_infos:
            raise ValueError(
                f"No DNS records resolved for callback_url hostname '{hostname}'"
            )

        validated_ips: List[str] = []
        for info_item in addr_infos:
            resolved_ip = info_item[4][0]
            if validate_ips:
                ip_validator(resolved_ip)
            normalized_ip = str(ipaddress.ip_address(resolved_ip))
            if normalized_ip not in validated_ips:
                validated_ips.append(normalized_ip)
        return validated_ips

    def _resolve_public_ips_with_guard(
        self,
        hostname: str,
        port: int,
        *,
        timeout: float,
        semaphore: Optional[BoundedSemaphore],
        ip_validator: IpValidator,
        validate_ips: bool,
    ) -> List[str]:
        """在并发信号量与超时限制下执行 DNS 解析，并按需校验记录均为公网 IP。"""
        if timeout <= 0:
            raise ValueError("dns_timeout must be positive")

        active_semaphore = semaphore or self._semaphore
        if not active_semaphore.acquire(timeout=timeout):
            raise ValueError(
                f"DNS resolution concurrency limit exceeded for callback_url hostname '{hostname}'"
            )

        try:
            future = self._executor.submit(
                lambda: socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
            )
        except Exception:
            active_semaphore.release()
            raise

        # 仅在底层 DNS 查询真正结束（或未启动即取消）后释放并发信号量，
        # 防止慢速/阻塞的 getaddrinfo 超时后提前释放配额导致在途查询数突破上限。
        future.add_done_callback(lambda _f: active_semaphore.release())

        try:
            addr_infos = future.result(timeout=timeout)
        except FuturesTimeoutError as e:
            future.cancel()
            raise ValueError(
                f"DNS resolution timed out for callback_url hostname '{hostname}'"
            ) from e
        except socket.gaierror as e:
            raise ValueError(
                f"Failed to resolve callback_url hostname '{hostname}': {e}"
            ) from e

        return self._extract_unique_ips(
            addr_infos, hostname, ip_validator, validate_ips=validate_ips
        )

    def resolve_and_pin(
        self,
        callback_url: str,
        *,
        dns_timeout: Optional[float] = None,
        semaphore: Optional[BoundedSemaphore] = None,
        ip_validator: Optional[IpValidator] = None,
    ) -> PinnedCallbackTarget:
        """
        解析并固定回调 URL 的实际 TCP 目标 IP，防范 DNS Rebinding：
        - 将请求 URL 的连接主机固定为已验证的 IP 字面量；
        - 保留原始域名用于 HTTP Host 请求头；
        - 在 HTTPS 域名场景通过 extensions['sni_hostname'] 保留 TLS SNI 与证书主机名校验。
        """
        effective_validator = ip_validator or self.assert_public_ip
        cleaned, parsed, scheme, explicit_port, hostname, is_literal_ip = (
            self._parse_and_validate(callback_url, ip_validator=effective_validator)
        )
        allowlisted = self._is_allowlisted(hostname)
        port = explicit_port or (443 if scheme == "https" else 80)

        if is_literal_ip:
            pinned_ip = str(ipaddress.ip_address(hostname))
            ascii_host = pinned_ip
            header_host_base = _format_netloc_host(ascii_host)
        else:
            try:
                ascii_host = hostname.encode("idna").decode("ascii")
            except UnicodeError as e:
                raise ValueError(
                    f"Invalid IDNA hostname in callback_url: {hostname!r}"
                ) from e
            validated_ips = self._resolve_public_ips_with_guard(
                ascii_host,
                port,
                timeout=dns_timeout or self.policy.dns_timeout,
                semaphore=semaphore,
                ip_validator=effective_validator,
                validate_ips=not allowlisted,
            )
            pinned_ip = validated_ips[0]
            header_host_base = ascii_host

        pinned_netloc = _format_host_with_port(
            _format_netloc_host(pinned_ip), explicit_port
        )
        pinned_url = urlunparse(
            (
                scheme,
                pinned_netloc,
                parsed.path or "",
                parsed.params or "",
                parsed.query or "",
                "",
            )
        )
        host_header = _format_host_with_port(header_host_base, explicit_port)
        extensions: Dict[str, Any] = (
            {"sni_hostname": ascii_host}
            if (scheme == "https" and not is_literal_ip)
            else {}
        )

        return PinnedCallbackTarget(
            original_url=cleaned,
            pinned_url=pinned_url,
            pinned_ip=pinned_ip,
            hostname=ascii_host,
            headers={"Host": host_header},
            extensions=extensions,
        )

    def validate(
        self,
        callback_url: str,
        *,
        resolve_dns: bool = False,
        dns_timeout: Optional[float] = None,
    ) -> str:
        """
        校验 Webhook 回调 URL 的安全性以防范 SSRF：
        1. 仅允许策略配置的协议，且不得包含内嵌认证凭据；
        2. 拒绝内部主机名及私网、回环、链路本地字面量 IP；
        3. 当 resolve_dns=True 时，在超时与并发控制下解析全部 DNS 记录并验证目标 IP。
        """
        if resolve_dns:
            return self.resolve_and_pin(
                callback_url, dns_timeout=dns_timeout
            ).original_url
        cleaned, *_ = self._parse_and_validate(
            callback_url, ip_validator=self.assert_public_ip
        )
        return cleaned


default_guard = SsrfGuard()


def validate_callback_url(
    callback_url: str,
    *,
    resolve_dns: bool = False,
    dns_timeout: Optional[float] = None,
    guard: Optional[SsrfGuard] = None,
) -> str:
    """使用默认（或指定）防护器校验回调 URL，返回去除首尾空白后的原始 URL。"""
    return (guard or default_guard).validate(
        callback_url, resolve_dns=resolve_dns, dns_timeout=dns_timeout
    )


def resolve_and_pin_callback_target(
    callback_url: str,
    *,
    dns_timeout: Optional[float] = None,
    semaphore: Optional[BoundedSemaphore] = None,
    ip_validator: Optional[IpValidator] = None,
    guard: Optional[SsrfGuard] = None,
) -> PinnedCallbackTarget:
    """使用默认（或指定）防护器解析并固定回调目标 IP。"""
    return (guard or default_guard).resolve_and_pin(
        callback_url,
        dns_timeout=dns_timeout,
        semaphore=semaphore,
        ip_validator=ip_validator,
    )


async def post_json_pinned(
    url: str,
    payload: Dict[str, Any],
    *,
    ssl_verify: Any = True,
    ip_validator: Optional[IpValidator] = None,
    timeout: float = 30,
    guard: Optional[SsrfGuard] = None,
) -> PinnedCallbackTarget:
    """校验并将连接固定到目标 IP 后发送 JSON POST，返回固定后的请求参数。

    安全出站要点：``follow_redirects=False``（禁止跳转到未校验地址）、
    ``trust_env=False``（忽略代理等环境变量）、HTTPS 场景透传 SNI 保留证书主机名校验。
    """
    active_guard = guard or default_guard
    pinned_target = await asyncio.to_thread(
        functools.partial(
            active_guard.resolve_and_pin,
            url,
            ip_validator=ip_validator,
        )
    )

    import httpx

    client_kwargs: Dict[str, Any] = {"follow_redirects": False, "trust_env": False}
    if ssl_verify is not True:
        client_kwargs["verify"] = ssl_verify
    async with httpx.AsyncClient(**client_kwargs) as client:
        post_kwargs: Dict[str, Any] = {
            "json": payload,
            "headers": pinned_target.headers,
            "timeout": timeout,
        }
        if pinned_target.extensions:
            post_kwargs["extensions"] = pinned_target.extensions
        await client.post(pinned_target.pinned_url, **post_kwargs)
    return pinned_target
