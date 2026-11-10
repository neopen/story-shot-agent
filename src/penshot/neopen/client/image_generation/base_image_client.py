"""
Copyright (c) 2025 neopen
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: base_image_client.py
@Description: 文生图客户端抽象基类（generate / generate_batch + 资产落盘）
@Author: neopen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/11/05
"""

import base64
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional

import httpx

from penshot.config.config import settings
from penshot.config.config_models import ImageBaseConfig
from penshot.logger import debug, warning
from penshot.neopen.client.image_generation.image_models import (
    ImageGenerationRequest,
    ImageGenerationResult,
)


@dataclass
class ImagePayload:
    """供应商返回的原始图片载荷（二选一）"""

    b64_data: Optional[str] = None
    url: Optional[str] = None


def get_image_api_key(config: ImageBaseConfig) -> str:
    """安全提取 API Key（兼容 SecretStr）"""
    api_key = getattr(config, "api_key", "") or ""
    if hasattr(api_key, "get_secret_value"):
        api_key = api_key.get_secret_value()
    return str(api_key or "")


def resolve_asset_dir(config: ImageBaseConfig) -> str:
    """解析资产落盘目录：显式配置优先，否则落在 data_output/assets"""
    if config.output_dir:
        return config.output_dir
    data_output = settings.get_data_paths().get("data_output", "./data/output")
    return os.path.join(data_output, "assets")


def _safe_filename(asset_id: str) -> str:
    """把资产ID转换为安全的文件名（保留字母数字与下划线连字符）"""
    safe = "".join(
        ch if (ch.isalnum() or ch in {"_", "-"}) else "_" for ch in asset_id.strip()
    )
    return safe or "asset"


class BaseImageGenerationClient(ABC):
    """文生图客户端基类：负责重试、下载与落盘；子类只需实现接口调用"""

    def __init__(self, config: ImageBaseConfig):
        self.config = config

    @property
    def provider(self) -> str:
        """返回供应商标识"""
        return self.config.provider

    @property
    def model_name(self) -> str:
        """返回模型名"""
        return self.config.model_name

    def is_configured(self) -> bool:
        """是否具备真实调用条件（开关开启 + 端点 + 模型 + 密钥）"""
        return bool(
            self.config.enabled
            and self.config.base_url
            and self.config.model_name
            and get_image_api_key(self.config)
        )

    def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        """生成单张图片并在成功后落盘"""
        if not self.is_configured():
            return ImageGenerationResult(
                asset_id=request.asset_id,
                success=False,
                provider=self.provider,
                model_name=self.model_name,
                error="image_client_not_configured",
            )

        start = time.time()
        last_error = ""
        attempts = self.config.max_retries + 1
        for attempt in range(attempts):
            try:
                payload = self._request_image(request)
                image_path = self._persist_payload(payload, request.asset_id)
                return ImageGenerationResult(
                    asset_id=request.asset_id,
                    success=True,
                    image_path=image_path,
                    image_url=payload.url or "",
                    provider=self.provider,
                    model_name=self.model_name,
                    latency_ms=int((time.time() - start) * 1000),
                )
            except Exception as e:  # 外部接口异常需重试，最终失败交由上层降级
                last_error = str(e)
                warning(
                    f"文生图调用失败（第{attempt + 1}/{attempts}次）: "
                    f"asset={request.asset_id}, error={last_error}"
                )
                if attempt < attempts - 1:
                    time.sleep(min(2 ** attempt, 8))

        return ImageGenerationResult(
            asset_id=request.asset_id,
            success=False,
            provider=self.provider,
            model_name=self.model_name,
            latency_ms=int((time.time() - start) * 1000),
            error=last_error or "image_generation_failed",
        )

    def generate_batch(
        self, requests: List[ImageGenerationRequest]
    ) -> List[ImageGenerationResult]:
        """批量生成；逐个执行，单个失败不影响其余资产"""
        return [self.generate(request) for request in requests]

    def _persist_payload(self, payload: ImagePayload, asset_id: str) -> str:
        """把图片载荷写入本地文件，返回本地路径"""
        asset_dir = resolve_asset_dir(self.config)
        os.makedirs(asset_dir, exist_ok=True)

        image_bytes = self._load_payload_bytes(payload)
        image_path = os.path.join(asset_dir, f"{_safe_filename(asset_id)}.png")
        with open(image_path, "wb") as f:
            f.write(image_bytes)

        debug(f"资产已落盘: {image_path}")
        return image_path

    def _load_payload_bytes(self, payload: ImagePayload) -> bytes:
        """解码 base64 或下载远端图片"""
        if payload.b64_data:
            return base64.b64decode(payload.b64_data)
        if payload.url:
            response = httpx.get(payload.url, timeout=self.config.timeout)
            response.raise_for_status()
            return response.content
        raise ValueError("图片载荷为空（既无 base64 也无 url）")

    @abstractmethod
    def _request_image(self, request: ImageGenerationRequest) -> ImagePayload:
        """调用供应商接口，返回原始图片载荷"""
