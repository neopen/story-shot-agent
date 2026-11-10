"""
Copyright (c) 2025 neopen
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: image_models.py
@Description: 文生图客户端数据模型（M0.4.2）
@Author: neopen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/11/05
"""

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ImageGenerationRequest(BaseModel):
    """单个文生图请求（仅生成静态资产，不做视频生成）"""

    asset_id: str = Field(..., description="资产唯一标识，用于落盘命名")
    prompt: str = Field(..., min_length=1, description="正向提示词")
    negative_prompt: str = Field(default="", description="负向提示词")
    size: str = Field(default="1024x1024", description="输出尺寸")
    seed: Optional[int] = Field(default=None, description="随机种子")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="资产类型/归属名等附加信息"
    )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典表示"""
        return self.model_dump()


class ImageGenerationResult(BaseModel):
    """单个文生图结果；asset_ref 为落盘后的本地引用"""

    asset_id: str = Field(..., description="资产唯一标识")
    success: bool = Field(default=False, description="是否生成成功")
    image_path: str = Field(default="", description="落盘后的本地图片路径")
    image_url: str = Field(default="", description="远端图片地址（如有）")
    provider: str = Field(default="", description="实际使用的供应商")
    model_name: str = Field(default="", description="实际使用的模型名")
    latency_ms: int = Field(default=0, description="耗时（毫秒）")
    error: str = Field(default="", description="失败原因")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典表示"""
        return self.model_dump()
