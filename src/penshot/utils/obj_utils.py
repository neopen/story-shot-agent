"""
@FileName: dict_utils.py
@Description: 
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2026/1/11 23:39
"""
from copy import deepcopy
from dataclasses import fields
from typing import Optional
from typing import get_type_hints, get_origin, get_args
from enum import Enum
from dataclasses import is_dataclass, asdict
from typing import Any, Dict, List, Union
from collections import deque


class JSONObject:
    def __init__(self, data):
        for key, value in data.items():
            if isinstance(value, dict):
                setattr(self, key, JSONObject(value))
            elif isinstance(value, list):
                setattr(self, key, [JSONObject(item) if isinstance(item, dict) else item for item in value])
            else:
                setattr(self, key, value)

    def __repr__(self):
        return str(self.__dict__)


# ================================== obj 转 dict ==================================

def obj_to_dict(
        obj: Any,
        enum_mode: str = 'value',  # 'value' | 'name' | 'str'
        max_depth: int = 10,  # 防止无限递归
        current_depth: int = 0
) -> Union[Dict, List, str, int, float, bool, None]:
    """
        安全地将任意对象转换为原生 Python 数据结构（dict/list/str/int...），
        适用于序列化、日志记录、JSON 输出等场景。
            支持任意嵌套层级的 Enum 转换
            处理字典的 Key 和 Value
            支持多种容器类型

    支持：
      - dataclass
      - Pydantic v1 (BaseModel.dict())
      - Pydantic v2 (BaseModel.model_dump())
      - 普通对象（通过 __dict__）
      - 嵌套结构（递归）
      - 基本类型（直接返回）

    Args:
        obj: 任意 Python 对象

    Returns:
        可 JSON 序列化的原生数据结构
    """
    # 防止无限递归
    if current_depth > max_depth:
        return str(obj)

    # None 或基本类型
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj

    # Enum 类型处理（优先级高）
    if isinstance(obj, Enum):
        if enum_mode == 'value':
            return obj.value
        elif enum_mode == 'name':
            return obj.name
        elif enum_mode == 'str':
            return str(obj)
        return obj.value

    # 字典：同时处理 key 和 value
    if isinstance(obj, dict):
        return {
            obj_to_dict(k, enum_mode, max_depth, current_depth + 1):
                obj_to_dict(v, enum_mode, max_depth, current_depth + 1)
            for k, v in obj.items()
        }

    # 列表/元组/集合/队列：递归处理元素
    if isinstance(obj, (list, tuple, set, frozenset, deque)):
        return [
            obj_to_dict(item, enum_mode, max_depth, current_depth + 1)
            for item in obj
        ]

    # Pydantic v2
    if hasattr(obj, "model_dump") and callable(getattr(obj, "model_dump")):
        try:
            dumped = obj.model_dump(mode='python')  # mode='python' 确保不序列化 Enum
            return obj_to_dict(dumped, enum_mode, max_depth, current_depth + 1)
        except Exception as e:
            pass

    # Pydantic v1
    if hasattr(obj, "dict") and callable(getattr(obj, "dict")):
        try:
            dumped = obj.dict()
            return obj_to_dict(dumped, enum_mode, max_depth, current_depth + 1)
        except Exception as e:
            pass

    # dataclass
    if is_dataclass(obj) and not isinstance(obj, type):
        try:
            return obj_to_dict(asdict(obj), enum_mode, max_depth, current_depth + 1)
        except Exception as e:
            pass

    # 普通对象（有 __dict__）
    if hasattr(obj, "__dict__"):
        try:
            return obj_to_dict(vars(obj), enum_mode, max_depth, current_depth + 1)
        except Exception as e:
            pass

    # 处理 __slots__ 对象
    if hasattr(obj, "__slots__"):
        try:
            slot_dict = {slot: getattr(obj, slot) for slot in obj.__slots__ if hasattr(obj, slot)}
            return obj_to_dict(slot_dict, enum_mode, max_depth, current_depth + 1)
        except Exception as e:
            pass

    # 最后手段：转为字符串
    return str(obj)


def convert_data_dict(data: Dict[str, Any], enum_mode: str = 'value') -> Dict[str, Any]:
    """
    专门处理字典结构，遍历所有 key 对应的模型并转换

    Args:
        data: 字典，value 可能是模型对象
        enum_mode: 枚举转换模式 ('value' | 'name' | 'str')

    Returns:
        转换后的完整字典
    """
    if not isinstance(data, dict):
        raise TypeError("data 必须是字典类型")

    return obj_to_dict(data, enum_mode=enum_mode)


# =========================== obj 转 dict（安全版本） ===========================
def _is_enum_subclass(obj: Any) -> bool:
    """
    检查是否是 Enum 子类（包括自定义 Enum 基类）
    """
    try:
        # 检查类型继承链
        for base in type(obj).__mro__:
            if base.__name__ == 'Enum' and 'enum' in str(base.__module__):
                return True
        return False
    except Exception:
        return False

def obj_to_dict_safe(
        obj: Any,
        enum_mode: str = 'value',
        max_depth: int = 10,
        current_depth: int = 0,
        _seen: Optional[set] = None
) -> Union[Dict, List, str, int, float, bool, None]:
    """
    安全版本：完全深拷贝，无引用问题
    防止循环引用
    所有可变对象都创建新副本
    """
    if current_depth > max_depth:
        return str(obj)

        # 防止循环引用
    if _seen is None:
        _seen = set()
    obj_id = id(obj)
    if obj_id in _seen:
        return str(obj)

    # None
    if obj is None:
        return None

    # Enum 检查（最高优先级，在所有容器之前）
    # 使用 type(obj).__bases__ 检查是否是 Enum 子类
    if isinstance(obj, Enum) or _is_enum_subclass(obj):
        if enum_mode == 'value':
            return obj.value
        elif enum_mode == 'name':
            return obj.name
        elif enum_mode == 'str':
            return str(obj)
        return obj.value

    # 基本类型（不可变，安全）
    if isinstance(obj, (str, int, float, bool)):
        return obj

    # 字典（创建新字典）
    if isinstance(obj, dict):
        _seen.add(obj_id)
        result = {
            obj_to_dict_safe(k, enum_mode, max_depth, current_depth + 1, _seen):
                obj_to_dict_safe(v, enum_mode, max_depth, current_depth + 1, _seen)
            for k, v in obj.items()
        }
        _seen.discard(obj_id)
        return result

    # 列表/元组/集合（创建新列表）
    if isinstance(obj, (list, tuple, set, frozenset)):
        _seen.add(obj_id)
        result = [
            obj_to_dict_safe(item, enum_mode, max_depth, current_depth + 1, _seen)
            for item in obj
        ]
        _seen.discard(obj_id)
        return result

    # Pydantic v2（关键：使用 mode='python' 并递归处理结果）
    if hasattr(obj, "model_dump") and callable(getattr(obj, "model_dump")):
        try:
            _seen.add(obj_id)
            # mode='python' 返回 Python 对象，mode='json' 会直接序列化
            dumped = obj.model_dump(mode='python', exclude_none=False)
            result = obj_to_dict_safe(dumped, enum_mode, max_depth, current_depth + 1, _seen)
            _seen.discard(obj_id)
            return result
        except Exception as e:
            print(f"Pydantic v2 model_dump 失败：{e}")
            pass

    # Pydantic v1
    if hasattr(obj, "dict") and callable(getattr(obj, "dict")):
        try:
            _seen.add(obj_id)
            dumped = obj.dict()
            result = obj_to_dict_safe(dumped, enum_mode, max_depth, current_depth + 1, _seen)
            _seen.discard(obj_id)
            return result
        except Exception as e:
            print(f"Pydantic v1 dict 失败：{e}")
            pass

    # dataclass
    if is_dataclass(obj) and not isinstance(obj, type):
        try:
            _seen.add(obj_id)
            result = obj_to_dict_safe(asdict(obj), enum_mode, max_depth, current_depth + 1, _seen)
            _seen.discard(obj_id)
            return result
        except Exception as e:
            print(f"dataclass asdict 失败：{e}")
            pass

    # 普通对象（deepcopy 避免引用）
    if hasattr(obj, "__dict__"):
        try:
            _seen.add(obj_id)
            obj_dict = deepcopy(vars(obj))
            result = obj_to_dict_safe(obj_dict, enum_mode, max_depth, current_depth + 1, _seen)
            _seen.discard(obj_id)
            return result
        except Exception as e:
            print(f"__dict__ 处理失败：{e}")
            pass

    # __slots__ 对象
    if hasattr(obj, "__slots__"):
        try:
            _seen.add(obj_id)
            slot_dict = deepcopy({
                slot: getattr(obj, slot)
                for slot in obj.__slots__
                if hasattr(obj, slot)
            })
            result = obj_to_dict_safe(slot_dict, enum_mode, max_depth, current_depth + 1, _seen)
            _seen.discard(obj_id)
            return result
        except Exception as e:
            print(f"__slots__ 处理失败：{e}")
            pass

    # 最后手段
    return str(obj)


def convert_data_dict_safe(data: Dict[str, Any], enum_mode: str = 'value') -> Dict[str, Any]:
    """安全转换字典中的所有模型"""
    if not isinstance(data, dict):
        raise TypeError("data 必须是字典类型")
    return obj_to_dict_safe(data, enum_mode=enum_mode)


# ============================ dict 转 dataclass ============================

def batch_dict_to_dataclass(datas: List[Any], cls) -> [Any]:
    """ 将字典列表转换为指定的 dataclass 对象列表。"""
    if datas is None or datas == []:
        return datas

    if isinstance(datas, dict):
        return [dict_to_dataclass(datas, cls)]

    if isinstance(datas, list):
        try:
            return [dict_to_dataclass(item, cls) for item in datas]
        except Exception as e:
            print(f"Error in batch_dict_to_dataclass: {e}")
            return [cls(**d) for d in datas]


def dict_to_dataclass(data, cls) -> Any:
    """ 将字典转换为指定的 dataclass 对象。"""
    #  or not is_dataclass(cls):
    if data is None or data == {} or not isinstance(data, dict):
        return data

    try:
        # pip install dacite
        from dacite import from_dict, Config
        return from_dict(data_class=cls, data=data, config=Config(strict=False))
    except Exception as e:
        print(f"Error in dict_to_dataclass from dacite: {e}")

        try:
            return cls(**data)
        except Exception as e:
            print(f"Error in dict_to_dataclass manual: {e}")
            hints = get_type_hints(cls)
            kwargs = {}

            for field in fields(cls):
                key = field.name
                field_type = hints[key]

                if key not in data:
                    if field.default is not field.default_factory.__class__ or field.default is not None:
                        kwargs[key] = field.default
                    elif hasattr(field, 'default_factory') and field.default_factory is not None:
                        kwargs[key] = field.default_factory()
                    continue

                value = data[key]
                origin = get_origin(field_type)
                args = get_args(field_type)

                # 处理 Optional[T] == Union[T, None]
                if origin is Union:
                    non_none_types = [t for t in args if t is not type(None)]
                    if len(non_none_types) == 1:
                        field_type = non_none_types[0]
                        origin = get_origin(field_type)
                        args = get_args(field_type)

                # 递归处理嵌套 dataclass
                if is_dataclass(field_type):
                    kwargs[key] = dict_to_dataclass(value, field_type)
                # 处理 List[SomeDataclass]
                elif origin is list and args and is_dataclass(args[0]):
                    kwargs[key] = [dict_to_dataclass(item, args[0]) for item in value]
                # 处理 Dict[str, SomeDataclass]
                elif origin is dict and len(args) == 2 and is_dataclass(args[1]):
                    kwargs[key] = {k: dict_to_dataclass(v, args[1]) for k, v in value.items()}
                else:
                    kwargs[key] = value

            return cls(**kwargs)


def dict_to_obj(data: Any, clazz) -> Any:
    """ 将字典或其他数据结构转换为指定类型的对象。"""
    if data is None:
        return None

    # 处理基本类型：直接返回
    if not isinstance(data, (dict, list)):
        return data

    # 获取原始类型（剥离泛型）
    origin = get_origin(clazz)
    args = get_args(clazz)

    # 情况1: clazz 是 Dict[...] 或 dict
    if origin is dict or clazz is dict or (origin in (Dict, dict)):
        # Dict[K, V] → 我们只关心 value 类型（args[1]）
        key_type = args[0] if args else str
        value_type = args[1] if len(args) > 1 else Any
        return {k: dict_to_obj(v, value_type) for k, v in data.items()}

    # 情况2: clazz 是 List[...] 或 list
    if origin is list or clazz is list or (origin in (List, list)):
        item_type = args[0] if args else Any
        return [dict_to_obj(item, item_type) for item in data]

    # 情况3: clazz 是 Union（包括 Optional）
    if origin is Union:
        # Optional[T] == Union[T, None]
        # 尝试用第一个非-None 的类型解析
        non_none_types = [t for t in args if t is not type(None)]
        if non_none_types:
            return dict_to_obj(data, non_none_types[0])
        return data

    # 情况4: clazz 是一个普通类（如 Person, Address）
    if isinstance(clazz, type) and hasattr(clazz, '__init__'):
        if isinstance(data, dict):
            try:
                annotations = get_type_hints(clazz)
            except Exception:
                annotations = {}

            kwargs = {}
            for key, value in data.items():
                field_type = annotations.get(key, Any)
                kwargs[key] = dict_to_obj(value, field_type)
            return clazz(**kwargs)
        else:
            # 数据不是 dict，但目标是类？可能出错，回退
            return data

    # 默认：无法识别类型，原样返回
    return data


if __name__ == '__main__':
    from dataclasses import dataclass


    @dataclass
    class Person:
        name: str
        age: int


    # 示例 2: dataclass
    p = Person("Alice", 30)
    print(obj_to_dict(p))
    # → {'name': 'Alice', 'age': 30}

    # 示例 3: 嵌套结构
    data = {
        "user": p,
        "response": {'name': 'Alice', 'age': 30},
        "meta": ["a", {"b": Person("Bob", 25)}]
    }
    print(obj_to_dict(data))
