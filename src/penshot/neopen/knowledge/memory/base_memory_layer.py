"""
Copyright (c) 2025 neopen
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: base_memory_layer.py
@Description: 三层记忆公共基类 - 统一按 key 存取、持久化与统计骨架
@Author: neopen
@Github: https://github.com/neopen/story-shot-agent
@Time: 2026/11/20
"""

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, ClassVar, Dict, Optional

from penshot.logger import warning


class BaseMemoryLayer(ABC):
    """记忆层公共基类（Template Method）

    统一提供按 key 的 KV 存取、清理与统计骨架；各层只需实现：
    - ``_persist``：把 KV（或与其他数据一起）写入存储
    - ``_clear_backend``：清理该层专有后端（消息缓冲 / 摘要 / 向量库）
    - ``_delete_kv_file``：删除 KV 持久化文件
    - ``_extra_stats``：补充该层专有统计字段

    各层的 ``add/search`` 等专有语义仍保留在子类，不强行上提到基类。
    """

    backend_type: ClassVar[str] = "base"

    def __init__(self, config: Any, script_id: str):
        self.config = config
        self.script_id = script_id
        self._key_values: Dict[str, Any] = {}

    # ===================== KV 接口 =====================

    def set_value(self, key: str, value: Any) -> None:
        """按 key 保存记忆值（覆盖写入并触发持久化）"""
        self._key_values[key] = value
        self._persist()

    def get_value(self, key: str, default: Any = None) -> Any:
        """按 key 读取记忆值"""
        return self._key_values.get(key, default)

    def has_value(self, key: str) -> bool:
        """判断 key 是否存在"""
        return key in self._key_values

    def clear(self) -> None:
        """清空该层记忆：后端 + KV + 持久化文件"""
        self._clear_backend()
        self._key_values.clear()
        self._delete_kv_file()

    # ===================== 统计接口 =====================

    def get_stats(self) -> Dict[str, Any]:
        """统计骨架：公共字段 + 各层专有字段"""
        return {
            "type": self.backend_type,
            "script_id": self.script_id,
            "key_value_count": len(self._key_values),
            **self._extra_stats(),
        }

    def _extra_stats(self) -> Dict[str, Any]:
        """各层专有统计字段"""
        return {}

    # ===================== 子类钩子 =====================

    def _persist(self) -> None:
        """持久化 KV；默认仅保留在内存"""
        return None

    def _delete_kv_file(self) -> None:
        """删除 KV 持久化文件；默认无文件"""
        return None

    @abstractmethod
    def _clear_backend(self) -> None:
        """清理该层专有后端，由子类实现"""
        raise NotImplementedError

    # ===================== 持久化辅助 =====================

    @staticmethod
    def _load_json_dict(path: Optional[Path]) -> Dict[str, Any]:
        """从 JSON 文件加载字典，缺失或损坏时返回空字典"""
        if not path or not path.exists():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception as e:
            warning(f"加载记忆文件失败: {path}, {e}")
            return {}

    @staticmethod
    def _save_json_dict(path: Optional[Path], data: Dict[str, Any]) -> None:
        """写入 JSON 字典，路径为空时跳过"""
        if not path:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            warning(f"保存记忆文件失败: {path}, {e}")

    @staticmethod
    def _delete_file(path: Optional[Path]) -> None:
        """删除文件，忽略不存在的场景"""
        if path and path.exists():
            try:
                path.unlink()
            except Exception as e:
                warning(f"删除记忆文件失败: {path}, {e}")
