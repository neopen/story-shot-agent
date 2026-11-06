"""
Copyright (c) 2025 HiPeng (NeoPen)
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: flux_client.py
@Description: Flux 文生图客户端（走 OpenAI 兼容的 /images/generations 接口）
@Author: NeoPen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/11/05
"""

import httpx

from penshot.neopen.client.image_generation.base_image_client import (
    BaseImageGenerationClient,
    ImagePayload,
    get_image_api_key,
)
from penshot.neopen.client.image_generation.image_models import ImageGenerationRequest


class FluxImageClient(BaseImageGenerationClient):
    """Flux 客户端

    以 OpenAI 兼容的图片生成接口为准（Flux 常通过兼容网关暴露该接口），
    只依赖 ``base_url`` + ``api_key`` + ``model_name``，便于切换托管服务。
    """

    def _request_image(self, request: ImageGenerationRequest) -> ImagePayload:
        """调用图片生成接口并解析首张图片"""
        url = f"{self.config.base_url.rstrip('/')}/images/generations"
        prompt = request.prompt
        if request.negative_prompt:
            # 部分兼容网关不支持独立负向字段，统一并入正向提示词
            prompt = f"{prompt}. Avoid: {request.negative_prompt}"

        body = {
            "model": self.config.model_name,
            "prompt": prompt,
            "n": 1,
            "size": request.size or self.config.size,
            "response_format": "b64_json",
        }
        if request.seed is not None:
            body["seed"] = request.seed

        headers = {
            "Authorization": f"Bearer {get_image_api_key(self.config)}",
            "Content-Type": "application/json",
        }

        response = httpx.post(
            url,
            json=body,
            headers=headers,
            timeout=self.config.timeout,
        )
        response.raise_for_status()
        data = response.json().get("data") or []
        if not data:
            raise ValueError("图片生成接口返回空 data")

        first = data[0]
        return ImagePayload(b64_data=first.get("b64_json"), url=first.get("url"))
