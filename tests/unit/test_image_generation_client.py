"""M0.4.2 文生图客户端测试。

覆盖配置门禁、成功落盘、批量失败隔离，确保文生图能力未启用时
不会发起网络请求，启用时可产出本地 asset_ref。
"""

import base64

from penshot.config.config_models import ImageBaseConfig
from penshot.neopen.client.image_generation import (
    BaseImageGenerationClient,
    ImageGenerationRequest,
    ImagePayload,
)


class _FakeImageClient(BaseImageGenerationClient):
    """以 base64 回包模拟供应商，避免真实网络调用"""

    def __init__(self, config: ImageBaseConfig, fail_asset_ids=()):
        super().__init__(config)
        self._fail_asset_ids = set(fail_asset_ids)

    def _request_image(self, request: ImageGenerationRequest) -> ImagePayload:
        if request.asset_id in self._fail_asset_ids:
            raise RuntimeError("mock provider failed")
        return ImagePayload(b64_data=base64.b64encode(b"fake-png").decode())


def _config(tmp_path, enabled=True, max_retries=0) -> ImageBaseConfig:
    return ImageBaseConfig(
        provider="flux",
        base_url="https://example.com/v1",
        api_key="test-key",
        model_name="flux-1.1-pro",
        size="1024x1024",
        timeout=10,
        max_retries=max_retries,
        output_dir=str(tmp_path),
        enabled=enabled,
    )


def test_disabled_client_skips_generation(tmp_path):
    """未启用时不发起调用，直接返回未配置错误"""
    client = _FakeImageClient(_config(tmp_path, enabled=False))
    result = client.generate(ImageGenerationRequest(asset_id="char_001", prompt="a hero"))
    assert result.success is False
    assert result.error == "image_client_not_configured"
    assert result.image_path == ""


def test_generate_saves_asset_to_output_dir(tmp_path):
    """成功生成时把图片落盘并返回本地引用"""
    client = _FakeImageClient(_config(tmp_path))
    result = client.generate(ImageGenerationRequest(asset_id="char_001", prompt="a hero"))
    assert result.success is True
    assert result.image_path.endswith("char_001.png")
    assert (tmp_path / "char_001.png").read_bytes() == b"fake-png"


def test_batch_isolates_failures(tmp_path):
    """批量生成时单个资产失败不影响其余资产"""
    client = _FakeImageClient(_config(tmp_path), fail_asset_ids={"prop_001"})
    results = client.generate_batch(
        [
            ImageGenerationRequest(asset_id="char_001", prompt="hero"),
            ImageGenerationRequest(asset_id="prop_001", prompt="watch"),
        ]
    )
    assert [r.success for r in results] == [True, False]
    assert results[1].error == "mock provider failed"


def test_api_key_fallback_accepts_plain_string():
    """SecretStr 与普通字符串配置都能识别为已配置"""
    config = ImageBaseConfig(
        provider="flux",
        base_url="https://example.com/v1",
        api_key="plain-key",
        model_name="flux-1.1-pro",
        enabled=True,
    )
    assert config.api_key is not None
    assert config.api_key.get_secret_value() == "plain-key"
