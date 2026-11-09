"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: task_lifecycle_service.py
@Description: 任务生命周期服务 - 负责任务状态机管理和生命周期控制
@Author: NeoPen
@Time: 2026/4/29
"""

from __future__ import annotations

import asyncio
import functools
import ipaddress
import json
import random
import socket
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, is_dataclass
from datetime import datetime, timezone, timedelta
from enum import Enum
from threading import BoundedSemaphore, RLock
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse, urlunparse

from penshot.logger import info, error, warning, debug
from penshot.neopen.agent.base_models import VideoStyle
from penshot.neopen.agent.workflow.workflow_pipeline import MultiAgentPipeline
from penshot.neopen.shot_config import ShotConfig
from penshot.neopen.task.task_models import TaskStatus, TaskStage
from penshot.utils.hash_utils import text_to_id
from penshot.utils.obj_utils import obj_to_dict
from .task_repository import TaskRepository
from .workflow_registry import WorkflowRegistry

_FORBIDDEN_HOSTNAMES = {"localhost", "localhost.localdomain"}
_FORBIDDEN_HOST_SUFFIXES = (".localhost", ".local", ".internal")
_NAT64_WELL_KNOWN_NETWORK = ipaddress.ip_network("64:ff9b::/96")
_NAT64_LOCAL_USE_NETWORK = ipaddress.ip_network("64:ff9b:1::/48")
_DNS_RESOLVE_TIMEOUT_SECONDS: float = 5.0
_DNS_MAX_CONCURRENT_LOOKUPS: int = 8
_DNS_CONCURRENCY_SEMAPHORE = BoundedSemaphore(_DNS_MAX_CONCURRENT_LOOKUPS)
_DNS_EXECUTOR = ThreadPoolExecutor(max_workers=_DNS_MAX_CONCURRENT_LOOKUPS, thread_name_prefix="penshot-dns")


@dataclass(frozen=True)
class PinnedCallbackTarget:
    """经过 SSRF 与 DNS 校验并固定目标公网 IP 的回调请求参数。"""

    original_url: str
    pinned_url: str
    pinned_ip: str
    hostname: str
    headers: Dict[str, str]
    extensions: Dict[str, Any]


def _extract_embedded_ipv4(ip_obj: ipaddress.IPv6Address) -> Optional[ipaddress.IPv4Address]:
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


def _is_non_public_ip_object(ip_obj: ipaddress._BaseAddress) -> bool:
    """判断单个 IP 对象是否属于非公网可达地址（含 RFC 8215 本地 NAT64 前缀 64:ff9b:1::/48）。"""
    if isinstance(ip_obj, ipaddress.IPv6Address) and ip_obj in _NAT64_LOCAL_USE_NETWORK:
        return True
    return (
        ip_obj.is_private
        or ip_obj.is_loopback
        or ip_obj.is_link_local
        or ip_obj.is_multicast
        or ip_obj.is_reserved
        or ip_obj.is_unspecified
        or not ip_obj.is_global
    )


def _assert_public_ip(ip_str: str) -> None:
    """校验 IP 地址为全局公网可达地址，拒绝回环、私网、链路本地、多播、保留及过渡内嵌私网地址。"""
    if "%" in ip_str:
        raise ValueError(f"Callback URL target IP must not include zone identifier: {ip_str}")
    ip_obj = ipaddress.ip_address(ip_str)
    if isinstance(ip_obj, ipaddress.IPv6Address):
        embedded_v4 = _extract_embedded_ipv4(ip_obj)
        if embedded_v4 is not None and _is_non_public_ip_object(embedded_v4):
            raise ValueError(f"Callback URL target IP is not a public routable address: {ip_str}")
    if _is_non_public_ip_object(ip_obj):
        raise ValueError(f"Callback URL target IP is not a public routable address: {ip_str}")


def _validate_url_scheme_and_auth(parsed: Any) -> Tuple[str, Optional[int]]:
    """校验回调 URL 的协议、认证凭据及端口合法性。"""
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        raise ValueError("callback_url scheme must be http or https")
    if parsed.username is not None or parsed.password is not None or "@" in (parsed.netloc or ""):
        raise ValueError("callback_url must not contain embedded credentials")
    try:
        explicit_port = parsed.port
    except ValueError as e:
        raise ValueError(f"callback_url contains an invalid port: {e}") from e
    if explicit_port is not None and not (1 <= explicit_port <= 65535):
        raise ValueError(f"callback_url port out of valid range: {explicit_port}")
    return scheme, explicit_port


def _parse_and_validate_callback_parts(
    callback_url: str,
    *,
    ip_validator: Callable[[str], None] = _assert_public_ip,
) -> Tuple[str, Any, str, Optional[int], str, bool]:
    """解析回调 URL 并执行静态协议、端口、凭据及字面量 IP 校验。"""
    if not isinstance(callback_url, str) or not callback_url.strip():
        raise ValueError("callback_url must be a non-empty URL string")

    cleaned = callback_url.strip()
    parsed = urlparse(cleaned)
    scheme, explicit_port = _validate_url_scheme_and_auth(parsed)

    hostname = (parsed.hostname or "").strip().lower().rstrip(".")
    if not hostname:
        raise ValueError("callback_url must include a valid hostname")
    if hostname in _FORBIDDEN_HOSTNAMES or hostname.endswith(_FORBIDDEN_HOST_SUFFIXES):
        raise ValueError(f"callback_url hostname is not permitted: {hostname}")

    try:
        ipaddress.ip_address(hostname.split("%", 1)[0])
        is_literal_ip = True
    except ValueError:
        is_literal_ip = False

    if is_literal_ip:
        ip_validator(hostname)

    return cleaned, parsed, scheme, explicit_port, hostname, is_literal_ip


def _resolve_public_ips_with_guard(
    hostname: str,
    port: int,
    *,
    timeout: float = _DNS_RESOLVE_TIMEOUT_SECONDS,
    semaphore: BoundedSemaphore = _DNS_CONCURRENCY_SEMAPHORE,
    ip_validator: Callable[[str], None] = _assert_public_ip,
) -> List[str]:
    """在并发信号量与超时限制下执行 DNS 解析，并校验全部记录均为公网 IP。"""
    if timeout <= 0:
        raise ValueError("dns_timeout must be positive")
    if not semaphore.acquire(timeout=timeout):
        raise ValueError(f"DNS resolution concurrency limit exceeded for callback_url hostname '{hostname}'")

    try:
        future = _DNS_EXECUTOR.submit(lambda: socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM))
    except Exception:
        semaphore.release()
        raise

    # 仅在底层 DNS 查询真正结束（或未启动即取消）后释放并发信号量，
    # 防止慢速/阻塞的 getaddrinfo 超时后提前释放配额导致在途查询数突破上限。
    future.add_done_callback(lambda _f: semaphore.release())

    try:
        addr_infos = future.result(timeout=timeout)
    except FuturesTimeoutError as e:
        future.cancel()
        raise ValueError(f"DNS resolution timed out for callback_url hostname '{hostname}'") from e
    except socket.gaierror as e:
        raise ValueError(f"Failed to resolve callback_url hostname '{hostname}': {e}") from e

    if not addr_infos:
        raise ValueError(f"No DNS records resolved for callback_url hostname '{hostname}'")

    validated_ips: List[str] = []
    for info_item in addr_infos:
        resolved_ip = info_item[4][0]
        ip_validator(resolved_ip)
        normalized_ip = str(ipaddress.ip_address(resolved_ip))
        if normalized_ip not in validated_ips:
            validated_ips.append(normalized_ip)

    return validated_ips


def _format_netloc_host(host_str: str) -> str:
    """为 IPv6 字面量添加方括号以构造合法的 URL netloc 或 Host 头。"""
    return f"[{host_str}]" if ":" in host_str else host_str


def _format_host_with_port(host_base: str, explicit_port: Optional[int]) -> str:
    """按需拼接显式端口。"""
    return f"{host_base}:{explicit_port}" if explicit_port is not None else host_base


def resolve_and_pin_callback_target(
    callback_url: str,
    *,
    dns_timeout: float = _DNS_RESOLVE_TIMEOUT_SECONDS,
    semaphore: BoundedSemaphore = _DNS_CONCURRENCY_SEMAPHORE,
    ip_validator: Callable[[str], None] = _assert_public_ip,
) -> PinnedCallbackTarget:
    """
    解析并固定回调 URL 的实际 TCP 目标 IP，防范 DNS Rebinding：
    - 将请求 URL 的连接主机固定为已验证的公网 IP 字面量；
    - 保留原始域名用于 HTTP Host 请求头；
    - 在 HTTPS 域名场景通过 extensions['sni_hostname'] 保留 TLS SNI 与证书主机名校验。
    """
    cleaned, parsed, scheme, explicit_port, hostname, is_literal_ip = _parse_and_validate_callback_parts(
        callback_url, ip_validator=ip_validator
    )
    port = explicit_port or (443 if scheme == "https" else 80)

    if is_literal_ip:
        pinned_ip = str(ipaddress.ip_address(hostname))
        ascii_host = pinned_ip
        header_host_base = _format_netloc_host(ascii_host)
    else:
        try:
            ascii_host = hostname.encode("idna").decode("ascii")
        except UnicodeError as e:
            raise ValueError(f"Invalid IDNA hostname in callback_url: {hostname!r}") from e
        validated_ips = _resolve_public_ips_with_guard(
            ascii_host,
            port,
            timeout=dns_timeout,
            semaphore=semaphore,
            ip_validator=ip_validator,
        )
        pinned_ip = validated_ips[0]
        header_host_base = ascii_host

    pinned_netloc = _format_host_with_port(_format_netloc_host(pinned_ip), explicit_port)
    pinned_url = urlunparse((scheme, pinned_netloc, parsed.path or "", parsed.params or "", parsed.query or "", ""))
    host_header = _format_host_with_port(header_host_base, explicit_port)
    extensions: Dict[str, Any] = {"sni_hostname": ascii_host} if (scheme == "https" and not is_literal_ip) else {}

    return PinnedCallbackTarget(
        original_url=cleaned,
        pinned_url=pinned_url,
        pinned_ip=pinned_ip,
        hostname=ascii_host,
        headers={"Host": host_header},
        extensions=extensions,
    )


def validate_callback_url(
    callback_url: str,
    *,
    resolve_dns: bool = False,
    dns_timeout: float = _DNS_RESOLVE_TIMEOUT_SECONDS,
) -> str:
    """
    校验 Webhook 回调 URL 的安全性以防范 SSRF：
    1. 仅允许 http / https 协议，且不得包含内嵌认证凭据；
    2. 拒绝 localhost / .local / .internal 等内部主机名及私网、回环、链路本地字面量 IP；
    3. 当 resolve_dns=True 时，在超时与并发控制下解析全部 DNS 记录并验证所有目标 IP 均为公网地址。
    """
    if resolve_dns:
        return resolve_and_pin_callback_target(callback_url, dns_timeout=dns_timeout).original_url
    cleaned, *_ = _parse_and_validate_callback_parts(callback_url)
    return cleaned


class TaskLifecycleService:
    """负责任务状态机管理和生命周期控制。"""

    def __init__(self, repository: TaskRepository,
                 workflow_registry: WorkflowRegistry,
                 task_ttl_seconds: int = 86400):
        self.repository = repository
        self.workflow_registry = workflow_registry
        self.task_ttl_seconds = task_ttl_seconds
        self._metrics = {"created": 0, "completed": 0, "failed": 0}
        self._lock = RLock()
        # 保存后台回调任务引用，防止任务被垃圾回收提前中断
        self._callback_tasks: set = set()
        self.pipeline_factory = None

    # ==================== ID生成方法 ====================
    def _generate_script_code(self, script: str) -> str:
        return text_to_id(script, 3)

    def _generate_script_id(self, script_code: str) -> str:
        # return "NP" + datetime.now().strftime("%y%m") + script_code
        return "SN" + script_code

    def _generate_task_id(self, script_code: str) -> str:
        """生成任务ID"""
        return "TSK" + script_code[:6] + datetime.now().strftime("%y%m%d%H%M") + str(random.randint(1000, 9999))

    # ==================== 序列化方法 ====================
    def _safe_serialize(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, datetime):
            try:
                return value.isoformat()
            except Exception as e:
                warning(f"日期序列化失败: {e}")
                return str(value)
        if is_dataclass(value):
            try:
                return {k: self._safe_serialize(v) for k, v in vars(value).items()}
            except Exception as e:
                error(f"数据类序列化失败: {e}")
                return str(value)
        if isinstance(value, dict):
            res = {}
            for k, v in value.items():
                try:
                    key = str(k)
                except Exception as e:
                    warning(f"字典键序列化失败: {e}")
                    key = json.dumps(k, default=str)
                res[key] = self._safe_serialize(v)
            return res
        if isinstance(value, (list, tuple, set)):
            return [self._safe_serialize(v) for v in value]
        if isinstance(value, Enum):
            return getattr(value, "value", getattr(value, "name", str(value)))
        try:
            return json.loads(json.dumps(value))
        except Exception as e:
            debug(f"JSON序列化失败: {e}")
            return str(value)

    def _serialize_config(self, config: Any) -> Dict[str, Any]:
        try:
            if config is None:
                return {}
            # 统一用 obj_to_dict 归一化：同一份配置无论是原始的 ShotConfig 对象，
            # 还是任务记录里 JSON 反序列化后的 dict，都会得到一致的序列化结果，
            # 从而保证工作流缓存键在“创建”和“清理”两侧始终一致。
            return self._safe_serialize(obj_to_dict(config)) or {}
        except Exception as e:
            error(f"配置序列化失败: {e}")
            return {"raw": str(config)}

    def _workflow_key(self, config: Any) -> str:
        """生成工作流缓存键（与 get_workflow 使用同一套算法，供缓存清理复用）"""
        try:
            payload = json.dumps(self._serialize_config(config), sort_keys=True, ensure_ascii=False)
        except Exception as e:
            warning(f"生成工作流键失败: {e}")
            payload = str(config)
        import uuid
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, payload))

    # ==================== 核心业务方法 ====================
    def create_task(self, script: str, script_id: Optional[str] = None,
                    style: Optional[VideoStyle] = None,
                    config: Optional[ShotConfig] = None,
                    asset_manifest: Optional[Dict[str, Any]] = None) -> Tuple[str, str]:
        """
        创建任务

        Args:
            script: 剧本内容
            script_id: 剧本ID（可选）
            style: 视频风格（可选）
            config: 配置（可选）
            asset_manifest: 下游回填的资产清单（可选，JSON 可序列化）

        Returns:
            (script_id, task_id)
        """
        if not isinstance(script, str) or not script.strip():
            raise ValueError("script must be a non-empty string")

        script_code = self._generate_script_code(script)
        script_id = script_id or self._generate_script_id(script_code)
        task_id = self._generate_task_id(script_code)
        shot_config = config or ShotConfig()
        if style:
            shot_config.default_style = style.value

        record = {
            "task_id": task_id,
            "script_id": script_id,
            "script": script,
            "config": shot_config,
            # 下游回填的资产清单（asset_id -> asset_ref），随任务持久化
            "asset_manifest": asset_manifest,
            "status": TaskStatus.PENDING,
            "stage": TaskStage.INIT.code,
            "progress": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "result": None,
            "error": None,
            "callbacks": [],
        }

        self.repository.create_task(task_id, record, raw_config=shot_config)

        with self._lock:
            self._metrics["created"] += 1

        info(f"创建任务: {task_id}")
        return script_id, task_id

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务信息"""
        return self.repository.read_task(task_id)

    def update_progress(self, task_id: str, stage: TaskStage,
                        progress: Optional[float] = None,
                        details: Optional[Dict[str, Any]] = None) -> bool:
        """
        更新任务详细进度

        Args:
            task_id: 任务ID
            stage: 当前阶段
            progress: 该阶段进度百分比
            details: 阶段详细信息

        Returns:
            是否成功
        """
        stage_code = stage.code

        def updater(rec: Dict[str, Any]) -> None:
            current_status = rec.get("status")
            if current_status not in [TaskStatus.SUCCESS.value, TaskStatus.FAILED.value, TaskStatus.CANCELLED.value]:
                rec["status"] = TaskStatus.PROCESSING.value

            rec["current_stage"] = stage_code
            rec["stage"] = stage_code
            rec["updated_at"] = datetime.now(timezone.utc).isoformat()
            rec.setdefault("progress_details", {})

            if stage_code not in rec["progress_details"]:
                rec["progress_details"][stage_code] = {
                    "name": stage.name,
                    "progress": 0,
                    "status": "processing",
                    "started_at": datetime.now(timezone.utc).isoformat()
                }

            stage_detail = rec["progress_details"][stage_code]
            if progress is not None:
                stage_detail["progress"] = progress
            if details:
                stage_detail["details"] = details

            try:
                rec["progress"] = self._calculate_overall_progress(rec["progress_details"])
            except Exception as e:
                error(f"计算整体进度失败: {e}")
                rec["progress"] = 0

        updated = self.repository.update_task(task_id, updater)
        if not updated:
            warning(f"更新进度详情时未找到任务: {task_id}")
        return updated

    def complete_stage(self, task_id: str, stage: TaskStage,
                       result: Optional[Dict[str, Any]] = None) -> bool:
        """
        完成一个阶段

        Args:
            task_id: 任务ID
            stage: 完成的阶段
            result: 阶段结果

        Returns:
            是否成功
        """

        def updater(rec: Dict[str, Any]) -> None:
            rec.setdefault("progress_details", {})

            if stage.code in rec["progress_details"]:
                rec["progress_details"][stage.code]["progress"] = 100
                rec["progress_details"][stage.code]["status"] = "completed"
                rec["progress_details"][stage.code]["completed_at"] = datetime.now(timezone.utc).isoformat()
            else:
                debug(f"阶段 {stage.code} 不在进度详情中")

            if result:
                rec.setdefault("stage_results", {})
                rec["stage_results"][stage.code] = result

            try:
                rec["progress"] = self._calculate_overall_progress(rec["progress_details"])
            except Exception as e:
                error(f"计算整体进度失败: {e}")
                rec["progress"] = rec.get("progress", 0)

            rec["updated_at"] = datetime.now(timezone.utc).isoformat()

        updated = self.repository.update_task(task_id, updater)
        if not updated:
            warning(f"完成阶段时未找到任务: {task_id}")
        return updated

    def _calculate_overall_progress(self, progress_details: Dict) -> float:
        """计算整体进度"""
        max_progress = 0
        for stage_code, detail in progress_details.items():
            stage = TaskStage.from_code(stage_code)
            if stage:
                weight = stage.weight
                if detail.get("status") == "completed":
                    if weight > max_progress:
                        max_progress = weight
                elif detail.get("status") == "processing":
                    stage_progress = weight + (detail.get("progress", 0) / 100) * 10
                    if stage_progress > max_progress:
                        max_progress = stage_progress
        return min(100, max_progress)

    def update_task_result(self, task_id: str, partial_result: Dict[str, Any]) -> bool:
        """更新任务部分结果"""

        def updater(rec: Dict[str, Any]) -> None:
            cur = rec.get("result") or {}
            if not isinstance(cur, dict):
                cur = {}
            try:
                cur.update(partial_result)
            except Exception as e:
                error(f"结果合并失败: {e}")
                cur = partial_result
            rec["result"] = cur
            rec["updated_at"] = datetime.now(timezone.utc).isoformat()

        return self.repository.update_task(task_id, updater)

    def complete_task(self, task_id: str, result: Dict[str, Any]) -> None:
        """
        完成任务

        Args:
            task_id: 任务ID
            result: 任务结果
        """
        success = result.get("success", False)

        def updater(rec: Dict[str, Any]) -> None:
            rec.update({
                "status": TaskStatus.SUCCESS if success else TaskStatus.FAILED,
                "result": result,
                "error": result.get("error"),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "completed_at": datetime.now(timezone.utc).isoformat(),
            })

        updated = self.repository.update_task(task_id, updater)
        if not updated:
            warning(f"完成任务时未找到任务: {task_id}")
            return

        with self._lock:
            if success:
                self._metrics["completed"] += 1
                info(f"任务完成: {task_id}")
            else:
                self._metrics["failed"] += 1
                warning(f"任务失败: {task_id}, error={result.get('error')}")

        self._try_trigger_callback(task_id, result)
        self._cleanup_workflow_cache(task_id)

    def fail_task(self, task_id: str, error_message: str) -> None:
        """
        标记任务失败

        Args:
            task_id: 任务ID
            error_message: 错误信息
        """

        def updater(rec: Dict[str, Any]) -> None:
            rec.update({
                "status": TaskStatus.FAILED,
                "error": error_message,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })

        updated = self.repository.update_task(task_id, updater)
        if not updated:
            warning(f"失败任务时未找到任务: {task_id}")
            return

        with self._lock:
            self._metrics["failed"] += 1
            warning(f"任务失败: {task_id}, error={error_message}")

        self._try_trigger_callback(task_id, {"success": False, "error": error_message})

    def _try_trigger_callback(self, task_id: str, result: Dict[str, Any]) -> None:
        """尝试触发回调（HTTP 回调用唯一出口，避免同一任务重复通知）"""
        task = self.repository.read_task(task_id)
        if not task:
            return

        callback_url = task.get("callback_url")
        if not callback_url:
            return

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # 同步上下文（无运行中的事件循环）下退化为后台线程发送，
            # 避免 RuntimeError 冒泡到 complete_task / fail_task 调用方
            import threading

            def _run_in_thread() -> None:
                try:
                    asyncio.run(self._trigger_callback_async(task_id, callback_url, result))
                except Exception as e:
                    error(f"回调触发失败: {task_id}, error={e}")

            threading.Thread(target=_run_in_thread, daemon=True).start()
            return

        task_ref = asyncio.create_task(self._trigger_callback_async(task_id, callback_url, result))
        # 保留引用，避免任务被垃圾回收提前中断
        self._callback_tasks.add(task_ref)
        task_ref.add_done_callback(self._callback_tasks.discard)

    async def _trigger_callback_async(
        self,
        task_id: str,
        callback_url: str,
        result: Dict[str, Any],
        *,
        ssl_verify: Any = True,
        ip_validator: Callable[[str], None] = _assert_public_ip,
    ) -> None:
        """异步触发HTTP回调（将实际TCP连接固定到已验证IP，保留原始Host请求头与HTTPS SNI）"""
        try:
            pinned_target = await asyncio.to_thread(
                functools.partial(
                    resolve_and_pin_callback_target,
                    callback_url,
                    ip_validator=ip_validator,
                )
            )
            import httpx
            client_kwargs: Dict[str, Any] = {"follow_redirects": False, "trust_env": False}
            if ssl_verify is not True:
                client_kwargs["verify"] = ssl_verify
            async with httpx.AsyncClient(**client_kwargs) as client:
                post_kwargs: Dict[str, Any] = {
                    "json": {"task_id": task_id, **result},
                    "headers": pinned_target.headers,
                    "timeout": 30,
                }
                if pinned_target.extensions:
                    post_kwargs["extensions"] = pinned_target.extensions
                await client.post(pinned_target.pinned_url, **post_kwargs)
                debug(
                    f"回调触发成功: {task_id} -> {pinned_target.original_url} "
                    f"(pinned_ip={pinned_target.pinned_ip})"
                )
        except Exception as e:
            error(f"回调触发失败: {task_id}, error={e}")

    def _cleanup_workflow_cache(self, task_id: str, config: Any = None) -> None:
        """清理任务相关的工作流缓存"""
        try:
            cfg = config
            if cfg is None:
                cfg = self.repository.get_raw_config(task_id)
            if cfg is None:
                # 兼容 Redis / 进程重启场景：回退到任务记录中的 config
                task = self.repository.read_task(task_id)
                if task:
                    cfg = task.get("config")
            if cfg is None:
                return

            key = self._workflow_key(cfg)
            if key and self.workflow_registry.get(key):
                still_used = False
                for other_id, other_cfg in self.repository.iter_raw_configs():
                    if other_id == task_id or other_cfg is None:
                        continue
                    if self._workflow_key(other_cfg) == key:
                        still_used = True
                        break
                if not still_used:
                    self.workflow_registry.pop(key)
                    debug(f"清理工作流缓存: {key}")
        except Exception as e:
            error(f"清理工作流缓存失败: {e}")

    def update_task_status(self, task_id: str, status: TaskStatus) -> bool:
        """
        更新任务状态

        Args:
            task_id: 任务ID
            status: 新状态

        Returns:
            是否成功
        """

        def updater(rec: Dict[str, Any]) -> None:
            rec.update({
                "status": status.value if hasattr(status, 'value') else status,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })

        updated = self.repository.update_task(task_id, updater)
        if not updated:
            warning(f"更新状态时未找到任务: {task_id}")
        return updated

    # ==================== 任务恢复方法 ====================
    def get_pending_tasks(self, max_age_hours: int = 2) -> List[Dict[str, Any]]:
        """获取所有未完成的任务"""
        pending_tasks = []
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)

        task_ids = self.repository.list_task_ids()
        for task_id in task_ids:
            task = self.repository.read_task(task_id)
            if task:
                status = task.get("status")
                if status in [TaskStatus.PENDING.value, TaskStatus.PROCESSING.value]:
                    created_at = task.get("created_at")
                    if created_at:
                        try:
                            if isinstance(created_at, str):
                                created_at_dt = datetime.fromisoformat(created_at)
                            else:
                                created_at_dt = created_at
                            if created_at_dt >= cutoff_time:
                                pending_tasks.append(task)
                        except Exception as e:
                            error(f"解析任务创建时间失败: {e}")
                            pending_tasks.append(task)

        info(f"获取到 {len(pending_tasks)} 个未完成任务")
        return pending_tasks

    def recover_task(self, task_id: str) -> bool:
        """恢复单个任务（将状态重置为 PENDING）"""
        task = self.repository.read_task(task_id)
        if not task:
            warning(f"恢复任务失败: 任务不存在 {task_id}")
            return False

        current_status = task.get("status")
        if current_status not in [TaskStatus.PENDING.value, TaskStatus.PROCESSING.value]:
            return False

        def updater(rec: Dict[str, Any]) -> None:
            rec["status"] = TaskStatus.PENDING.value
            rec["stage"] = "recovered"
            rec["progress"] = 0
            rec["updated_at"] = datetime.now(timezone.utc).isoformat()
            rec.pop("completed_at", None)

        updated = self.repository.update_task(task_id, updater)
        if updated:
            debug(f"任务恢复成功: {task_id}")
        return updated

    def recover_all_pending_tasks(self, max_age_hours: int = 2) -> List[str]:
        """恢复所有未完成的任务"""
        pending_tasks = self.get_pending_tasks(max_age_hours=max_age_hours)
        recovered_ids = []

        for task in pending_tasks:
            task_id = task.get("task_id")
            if self.recover_task(task_id):
                recovered_ids.append(task_id)
                info(f"恢复任务: {task_id}")

        info(f"成功恢复 {len(recovered_ids)}/{len(pending_tasks)} 个任务")
        return recovered_ids

    # ==================== 工作流管理 ====================
    def get_workflow(self, script_id: str, task_id: str, config: Optional[Any] = None) -> Any:
        """获取或创建工作流"""
        if task_id is not None and (config is None or isinstance(config, dict)):
            raw = self.repository.get_raw_config(task_id)
            if raw is None:
                # 兼容 Redis / 进程重启场景：回退到任务记录中的 config
                task = self.repository.read_task(task_id)
                if task:
                    raw = task.get("config")
            if raw is not None:
                config = raw

        # 与缓存清理共用同一套键算法，避免两处算法不一致导致清理失效
        key = self._workflow_key(config)

        pipeline = self.workflow_registry.get(key)
        if pipeline is not None:
            debug(f"从缓存获取工作流: {key}")
            return pipeline

        try:
            if self.pipeline_factory is not None:
                pipeline = self.pipeline_factory(task_id, config)
            else:
                pipeline = MultiAgentPipeline(script_id, task_id, config, self)
            info(f"创建新工作流: {key}")
        except Exception as e:
            error(f"创建工作流失败: {e}")
            raise

        self.workflow_registry.put(key, pipeline)
        return pipeline

    # ==================== 工具方法 ====================
    def list_tasks(self) -> List[str]:
        """获取所有任务ID"""
        return self.repository.list_task_ids()

    def delete_task(self, task_id: str, cleanup_workflow: bool = True) -> bool:
        """删除任务"""
        # 删除后无法再从仓库读取配置，需先取出用于工作流缓存清理
        cfg = None
        if cleanup_workflow:
            cfg = self.repository.get_raw_config(task_id)
            if cfg is None:
                task = self.repository.read_task(task_id)
                if task:
                    cfg = task.get("config")

        if not self.repository.delete_task(task_id):
            return False

        if cleanup_workflow:
            self._cleanup_workflow_cache(task_id, cfg)

        return True

    def get_metrics(self) -> Dict[str, int]:
        """获取任务统计指标"""
        with self._lock:
            return dict(self._metrics)

    def set_callback(self, task_id: str, callback_url: str) -> bool:
        """设置任务回调URL"""
        callback_url = validate_callback_url(callback_url)

        def updater(rec: Dict[str, Any]) -> None:
            rec.setdefault("callbacks", [])
            rec["callbacks"] = [callback_url]
            rec["callback_url"] = callback_url
            rec["updated_at"] = datetime.now(timezone.utc).isoformat()

        updated = self.repository.update_task(task_id, updater)
        if updated:
            info(f"设置任务回调: {task_id} -> {callback_url}")
        return updated

    def export_task_snapshot(self, task_id: str) -> Optional[Dict[str, Any]]:
        """导出任务快照"""
        return self.repository.read_task(task_id)

    def import_task_snapshot(self, snapshot: Dict[str, Any]) -> str:
        """导入任务快照"""
        return self.repository.import_snapshot(snapshot)

    def shutdown(self, close_pipelines: bool = True) -> None:
        """关闭服务"""
        cache_size = self.workflow_registry.shutdown(close_workflows=close_pipelines)
        info(f"关闭 TaskLifecycleService，清理 {cache_size} 个工作流缓存")
