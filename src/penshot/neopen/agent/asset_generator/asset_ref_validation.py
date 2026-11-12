"""
Copyright (c) 2025 neopen
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: asset_ref_validation.py
@Description: 资产引用校验（file:// / http(s) / 本地路径 + sha256 校验和，0.4.5 任务 1）
@Author: neopen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/11/12
"""

import hashlib
import re
from pathlib import Path
from typing import List, Optional
from urllib.parse import unquote, urlparse

HTTP_PREFIXES = ("http://", "https://")
CHECKSUM_PREFIX = "sha256:"

_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")


def normalize_ref(asset_ref: str) -> str:
    """去除首尾空白，避免回填时把换行带进引用"""
    return str(asset_ref or "").strip()


def is_http_ref(asset_ref: str) -> bool:
    """是否为 http(s) 远程引用"""
    return normalize_ref(asset_ref).lower().startswith(HTTP_PREFIXES)


def is_file_uri(asset_ref: str) -> bool:
    """是否为显式 file:// 引用"""
    return normalize_ref(asset_ref).lower().startswith("file://")


def resolve_local_path(asset_ref: str) -> Optional[Path]:
    """把引用解析为本地路径；远程引用或空引用返回 None

    显式 ``file://`` 与裸路径都按本地文件处理，后者兼容 0.4.4 之前直接写
    绝对路径的回填清单。
    """
    text = normalize_ref(asset_ref)
    if not text or is_http_ref(text):
        return None
    if is_file_uri(text):
        parsed = urlparse(text)
        # Windows 下 file:///E:/a.png 解析出的 path 形如 /E:/a.png，需去掉前导斜杠
        raw = unquote(parsed.path or "")
        if parsed.netloc and parsed.netloc not in ("", "localhost"):
            raw = f"//{parsed.netloc}{raw}"
        if re.match(r"^/[A-Za-z]:", raw):
            raw = raw[1:]
        return Path(raw) if raw else None
    return Path(text)


def compute_sha256(path: Path) -> str:
    """计算文件 sha256 十六进制摘要"""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _checksum_hex(checksum: str) -> str:
    """提取校验和的十六进制部分；不支持的前缀返回空串"""
    text = normalize_ref(checksum).lower()
    if text.startswith(CHECKSUM_PREFIX):
        text = text[len(CHECKSUM_PREFIX) :].strip()
    return text if _SHA256_HEX_RE.match(text) else ""


def validate_asset_ref(
    asset_ref: str,
    checksum: str = "",
    require_local_file: bool = False,
) -> List[str]:
    """校验单个资产引用，返回错误列表（空列表表示通过）

    Args:
        asset_ref: 回填的资产引用
        checksum: 可选校验和，支持 ``sha256:<hex>`` 或裸 hex
        require_local_file: 是否要求裸路径必须是已存在的本地文件；
            工作流默认关闭以兼容历史产物中的不透明引用，离线工具默认开启。

    Returns:
        阻断性错误列表；无错误即视为可用
    """
    text = normalize_ref(asset_ref)
    if not text:
        return ["asset_ref 为空"]
    if is_http_ref(text):
        return []

    path = resolve_local_path(text)
    if path is None:
        return [f"asset_ref 无法解析为本地路径: {text}"]

    if not path.is_file():
        # 裸路径可能是下游自定义标识（如 /cdn/xxx.png），仅在显式 file:// 或
        # 要求本地文件时判为错误，避免历史产物整批失效
        if is_file_uri(text) or require_local_file:
            return [f"asset_ref 不可用（文件不存在）: {text}"]
        return []

    expected = _checksum_hex(checksum)
    if expected and compute_sha256(path) != expected:
        return [f"asset_ref 不可用（校验和不匹配）: {text}"]
    return []


def split_ref_warnings(asset_ref: str, checksum: str = "") -> List[str]:
    """返回不影响回填的提示（如远程引用无法校验、校验和格式未知）"""
    text = normalize_ref(asset_ref)
    warnings: List[str] = []
    checksum_text = normalize_ref(checksum)
    if checksum_text and not _checksum_hex(checksum_text):
        warnings.append(f"校验和格式无法识别，已跳过校验: {checksum_text}")
    if is_http_ref(text) and checksum_text:
        warnings.append("远程引用不下载校验，checksum 仅记录不验证")
    return warnings
