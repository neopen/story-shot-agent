"""
@FileName: testddd.py
@Description: 
@Author: HiPeng
@Time: 2026/3/29 15:24
"""
import json
from dataclasses import dataclass
from enum import Enum
from typing import List, Dict

from pydantic import BaseModel

from penshot.utils.obj_utils import obj_to_dict, convert_data_dict, convert_data_dict_safe


# 多层枚举定义
class ModelType(Enum):
    RUNWAY = "runway"
    SORA = "sora"
    MIDJOURNEY = "midjourney"


class Status(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"


class Priority(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3


# 多层嵌套数据结构
@dataclass
class Task:
    name: str
    model: ModelType
    status: Status


@dataclass
class Project:
    title: str
    tasks: List[Task]
    metadata: Dict[str, Status]
    priority: Priority


@dataclass
class Organization:
    name: str
    projects: List[Project]
    config: Dict[str, Dict[str, ModelType]]


def test_dict_util():
    # 创建测试数据
    org = Organization(
        name="AI Studio",
        projects=[
            Project(
                title="视频生成",
                tasks=[
                    Task("任务 1", ModelType.RUNWAY, Status.PENDING),
                    Task("任务 2", ModelType.SORA, Status.PROCESSING),
                ],
                metadata={"stage1": Status.PENDING, "stage2": Status.COMPLETED},
                priority=Priority.HIGH
            ),
            Project(
                title="图像生成",
                tasks=[
                    Task("任务 3", ModelType.MIDJOURNEY, Status.COMPLETED),
                ],
                metadata={"stage1": Status.PROCESSING},
                priority=Priority.MEDIUM
            )
        ],
        config={
            "group1": {"model_a": ModelType.RUNWAY, "model_b": ModelType.SORA},
            "group2": {"model_c": ModelType.MIDJOURNEY}
        }
    )

    # 转换测试
    result = obj_to_dict(org, enum_mode='value')
    print(json.dumps(result, ensure_ascii=False, indent=2))


def test_batch_obj_to_dict():
    # 定义枚举
    class ModelType(Enum):
        RUNWAY = "runway"
        SORA = "sora"

    # 定义模型类
    class DD(BaseModel):
        name: str = "dd_model"
        type: ModelType = ModelType.RUNWAY
        version: int = 1

    class EE(BaseModel):
        title: str = "ee_model"
        type: ModelType = ModelType.SORA
        enabled: bool = True

    class SS(BaseModel):
        config: str = "ss_config"
        priority: int = 5

    # 创建你的 data 结构
    data = {
        'instructions': DD(),
        'eee': EE(),
        'ssss': SS()
    }

    # 转换整个 data
    result = convert_data_dict(data, enum_mode='value')
    print(json.dumps(result, ensure_ascii=False, indent=2))


def test_deepcopy_util():
    from pydantic import BaseModel
    from enum import Enum

    class ModelType(Enum):
        RUNWAY = "runway"
        SORA = "sora"

    class DD(BaseModel):
        name: str = "dd_model"
        type: ModelType = ModelType.RUNWAY
        tags: list = ["default"]

    class EE(BaseModel):
        title: str = "ee_model"
        enabled: bool = True

    # 原对象
    data = {
        'instructions': DD(),
        'eee': EE()
    }

    # 安全转换
    converted = convert_data_dict_safe(data)

    # 修改转换结果
    converted['instructions']['tags'].append("modified")
    converted['instructions']['name'] = "changed"
    converted['eee']['enabled'] = False

    # 验证原对象未受影响
    print("原对象 tags:", data['instructions'].tags)  # ['default']
    print("原对象 name:", data['instructions'].name)  # 'dd_model'
    print("原对象 enabled:", data['eee'].enabled)  # True

    print("\n转换结果 tags:", converted['instructions']['tags'])  # ['default', 'modified']
    print("转换结果 name:", converted['instructions']['name'])  # 'changed'
    print("转换结果 enabled:", converted['eee']['enabled'])  # False

    # JSON 序列化测试
    json_str = json.dumps(converted, ensure_ascii=False)
    print("\nJSON 序列化成功！" + json_str)