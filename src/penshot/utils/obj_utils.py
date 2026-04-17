"""
@FileName: dict_utils.py
@Description: 
@Author: HiPeng
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/1/11 23:39
"""
import inspect
from collections import deque
from copy import deepcopy
from dataclasses import asdict, fields, is_dataclass
from enum import Enum
from typing import Any, Dict, List, Union, get_origin, get_args, Optional, get_type_hints


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


# 尝试导入 SecretStr，如果不存在则定义占位符
try:
    from pydantic import SecretStr
except ImportError:
    # 定义简单的 SecretStr 类用于类型检查
    class SecretStr:
        def __init__(self, value: str = ""):
            self._value = value

        def __str__(self):
            return "**********"

        def get_secret_value(self):
            return self._value


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


def is_special_type(clazz) -> bool:
    """检查是否为需要特殊处理的类型"""
    # SecretStr 特殊处理
    if clazz is SecretStr:
        return True

    # 可以扩展其他特殊类型
    special_types = (SecretStr,)
    return clazz in special_types


def dict_to_obj(data: Any, clazz) -> Any:
    """将字典或其他数据结构转换为指定类型的对象。

    优化点：
    1. 添加对 dataclass 的支持
    2. 修复字段类型检测逻辑
    3. 增加对枚举类型的支持
    4. 更好的错误处理和类型校验
    5. 支持嵌套对象转换
    6. 支持 SecretStr 等特殊类型
    """
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
        if not isinstance(data, dict):
            return data
        key_type = args[0] if args else str
        value_type = args[1] if len(args) > 1 else Any
        return {dict_to_obj(k, key_type): dict_to_obj(v, value_type)
                for k, v in data.items()}

    # 情况2: clazz 是 List[...] 或 list
    if origin is list or clazz is list or (origin in (List, list)):
        if not isinstance(data, list):
            return data
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

    # 情况4: clazz 是枚举类型
    if hasattr(clazz, '__members__') and inspect.isclass(clazz):
        try:
            return clazz(data)
        except (ValueError, TypeError):
            return data

    # 情况5: clazz 是 SecretStr 等特殊类型
    if is_special_type(clazz):
        try:
            # 如果已经是 SecretStr 类型，直接返回
            if isinstance(data, SecretStr):
                return data
            # 如果是字符串，创建 SecretStr 实例
            if isinstance(data, str):
                return SecretStr(data)
            # 如果是其他类型，尝试转换
            return SecretStr(str(data))
        except Exception:
            # 转换失败，返回空 SecretStr
            return SecretStr("")

    # 情况6: clazz 是普通类
    if isinstance(clazz, type) and hasattr(clazz, '__init__'):
        # 处理基本类型：如果目标是基本类型，直接返回
        if clazz in (str, int, float, bool, complex, bytes, bytearray):
            return clazz(data) if not isinstance(data, clazz) else data

        # 处理字典数据
        if isinstance(data, dict):
            try:
                # 优先使用 dataclass 的字段信息
                if is_dataclass(clazz):
                    field_types = {f.name: f.type for f in fields(clazz)}
                else:
                    # 使用类型注解
                    field_types = get_type_hints(clazz)
            except Exception:
                field_types = {}

            kwargs = {}
            for key, value in data.items():
                # 获取字段类型
                field_type = field_types.get(key)

                # 如果没有类型注解，尝试从构造函数参数推断
                if field_type is None:
                    # 检查是否是 __init__ 的参数
                    try:
                        sig = inspect.signature(clazz.__init__)
                        param = sig.parameters.get(key)
                        if param and param.annotation != inspect.Parameter.empty:
                            field_type = param.annotation
                        else:
                            field_type = Any
                    except (ValueError, TypeError):
                        field_type = Any

                # 递归转换值
                kwargs[key] = dict_to_obj(value, field_type)

            try:
                return clazz(**kwargs)
            except TypeError as e:
                # 如果参数不匹配，尝试只传递存在的参数
                if "unexpected keyword argument" in str(e):
                    # 获取可接受的参数名
                    sig = inspect.signature(clazz.__init__)
                    valid_params = set(sig.parameters.keys()) - {'self'}
                    filtered_kwargs = {k: v for k, v in kwargs.items()
                                       if k in valid_params}

                    # 特殊处理 SecretStr 字段
                    for param_name, param_value in filtered_kwargs.items():
                        # 如果参数类型是 SecretStr 但值不是，进行转换
                        param_type = field_types.get(param_name)
                        if param_type is SecretStr and not isinstance(param_value, SecretStr):
                            filtered_kwargs[param_name] = SecretStr(str(param_value))

                    return clazz(**filtered_kwargs)
                raise
        else:
            # 数据不是 dict，尝试直接实例化
            try:
                return clazz(data)
            except (TypeError, ValueError):
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
