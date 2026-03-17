"""
@FileName: result_storage_tool.py
@Description: 结果存储工具模块，提供智能体结果的保存、加载和管理功能
@Author: HiPeng
@Github: https://github.com/neopen/video-shot-agent
@Time: 2025/12/18
"""

import os
import json
from typing import Any, Dict, Optional
from datetime import datetime

from penshot.config.config import settings
from penshot.logger import debug, info, warning, error
from penshot.utils.obj_utils import obj_to_dict


class ResultStorage:
    """
    结果存储管理类
    负责智能体结果的保存、加载和管理
    """

    def __init__(self, base_output_dir: Optional[str] = None):
        """
        初始化结果存储管理器
        
        Args:
            base_output_dir: 基础输出目录路径，默认为配置文件中的data_output路径
        """
        # 延迟导入以避免循环导入
        self.base_output_dir = base_output_dir or settings.get_data_paths()['data_output']
        debug(f"结果存储初始化完成，基础目录: {self.base_output_dir}")

    def get_result_path(self, uuid: str, result_filename: str = "script_parser_result.json") -> str:
        """
        获取特定结果文件的完整路径
        
        Args:
            uuid: 请求的唯一标识符
            result_filename: 结果文件名
            
        Returns:
            结果文件的完整路径
        """
        # 创建以uuid命名的子目录
        uuid_dir = os.path.join(self.base_output_dir, uuid)
        os.makedirs(uuid_dir, exist_ok=True)

        # 返回完整的结果文件路径
        return os.path.join(uuid_dir, result_filename)

    def save_obj_result(self, uuid: str, result_data: Any,
                        result_filename: str):
        """保存json"""
        try:
            # 转换为字典
            data_dict = obj_to_dict(result_data)

            # 递归检查并处理可能被截断的字符串
            self._ensure_string_integrity(data_dict)

            save_result = self.save_result(uuid, data_dict, result_filename)
            info(f"成功保存: data/output/{uuid}/{result_filename}")
            return save_result
        except Exception as save_error:
            error(f"保存{result_filename}失败: {str(save_error)}")
            # 抛出异常以便上层处理
            raise

    def save_result(self, uuid: str, result_data: Dict[str, Any],
                    result_filename: str = "script_parser_result.json",
                    add_timestamp: bool = True) -> str:
        """
        保存智能体结果到指定文件

        Args:
            uuid: 请求的唯一标识符
            result_data: 要保存的结果数据
            result_filename: 结果文件名
            add_timestamp: 是否添加时间戳

        Returns:
            保存的文件路径

        Raises:
            IOError: 保存文件失败时抛出
        """
        try:
            # 获取保存路径
            result_path = self.get_result_path(uuid, result_filename)

            # 创建要保存的数据副本
            save_data = result_data.copy()

            # 添加时间戳信息
            if add_timestamp:
                save_data["metadata"] = save_data.get("metadata", {})
                save_data["metadata"]["saved_at"] = datetime.now().isoformat()
                save_data["metadata"]["uuid"] = uuid

            # === 保存数据到JSON文件（增强版）===
            with open(result_path, 'w', encoding='utf-8') as f:
                # 使用更安全的JSON序列化设置
                json.dump(
                    save_data,
                    f,
                    ensure_ascii=False,  # 确保中文正常显示
                    indent=2,             # 保持缩进以便阅读
                    separators=(',', ': '),  # 使用标准分隔符，不压缩
                    default=str           # 处理不可序列化的对象
                )
                # 确保所有数据都被写入
                f.flush()
                os.fsync(f.fileno())  # 强制写入磁盘

            # 验证文件是否成功写入
            if os.path.exists(result_path) and os.path.getsize(result_path) > 0:
                debug(f"结果保存成功: {result_path} (大小: {os.path.getsize(result_path)} 字节)")
            else:
                warning(f"结果文件可能未正确写入: {result_path}")

            return result_path

        except Exception as e:
            error(f"保存结果失败 (UUID: {uuid}): {str(e)}")
            raise IOError(f"无法保存结果: {str(e)}")

    def _ensure_string_integrity(self, data: Any) -> None:
        """
        递归检查并确保字符串完整性
        主要检查是否有截断标记（如...）并发出警告

        Args:
            data: 要检查的数据
        """
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, str):
                    # 检查是否包含可能的截断标记
                    if value.endswith('...') or '...' in value[-10:]:
                        warning(f"检测到可能的字符串截断: {key} 以 '...' 结尾")
                else:
                    self._ensure_string_integrity(value)
        elif isinstance(data, list):
            for item in data:
                self._ensure_string_integrity(item)

    def _safe_json_dumps(self, data: Any) -> str:
        """
        安全地将数据转换为JSON字符串，处理长字符串

        Args:
            data: 要转换的数据

        Returns:
            JSON字符串
        """
        try:
            # 尝试标准序列化
            return json.dumps(data, ensure_ascii=False, default=str)
        except Exception as e:
            warning(f"JSON序列化失败，尝试分段处理: {str(e)}")

            # 如果失败，可能是由于字符串过长，尝试手动处理
            if isinstance(data, dict):
                result = {}
                for k, v in data.items():
                    if isinstance(v, str) and len(v) > 10000:
                        # 对于超长字符串，确保不被截断
                        result[k] = v
                    else:
                        result[k] = v
                return json.dumps(result, ensure_ascii=False, default=str)
            return json.dumps({"error": "序列化失败", "original": str(data)}, ensure_ascii=False)

    def load_result(self, uuid: str, result_filename: str = "script_parser_result.json") -> Optional[Dict[str, Any]]:
        """
        从文件加载智能体结果

        Args:
            uuid: 请求的唯一标识符
            result_filename: 结果文件名

        Returns:
            加载的结果数据，如果文件不存在则返回None

        Raises:
            IOError: 加载文件失败时抛出
        """
        try:
            # 获取文件路径
            result_path = self.get_result_path(uuid, result_filename)

            # 检查文件是否存在
            if not os.path.exists(result_path):
                warning(f"结果文件不存在: {result_path}")
                return None

            # 检查文件大小
            file_size = os.path.getsize(result_path)
            debug(f"加载结果文件: {result_path} (大小: {file_size} 字节)")

            # 加载JSON文件
            with open(result_path, 'r', encoding='utf-8') as f:
                result_data = json.load(f)

            debug(f"结果加载成功: {result_path}")
            return result_data

        except json.JSONDecodeError as e:
            error(f"解析结果文件失败 (UUID: {uuid}): {str(e)}")
            raise IOError(f"无法解析结果文件: {str(e)}")
        except Exception as e:
            error(f"加载结果失败 (UUID: {uuid}): {str(e)}")
            raise IOError(f"无法加载结果: {str(e)}")

    def result_exists(self, uuid: str, result_filename: str = "script_parser_result.json") -> bool:
        """
        检查特定UUID的结果文件是否存在

        Args:
            uuid: 请求的唯一标识符
            result_filename: 结果文件名

        Returns:
            文件是否存在
        """
        result_path = self.get_result_path(uuid, result_filename)
        return os.path.exists(result_path)

    def delete_result(self, uuid: str, result_filename: str = "script_parser_result.json") -> bool:
        """
        删除特定UUID的结果文件

        Args:
            uuid: 请求的唯一标识符
            result_filename: 结果文件名

        Returns:
            删除是否成功
        """
        try:
            result_path = self.get_result_path(uuid, result_filename)

            if os.path.exists(result_path):
                os.remove(result_path)
                debug(f"结果文件已删除: {result_path}")
                return True
            else:
                warning(f"要删除的结果文件不存在: {result_path}")
                return False

        except Exception as e:
            error(f"删除结果失败 (UUID: {uuid}): {str(e)}")
            return False

    def list_available_results(self) -> Dict[str, Dict[str, str]]:
        """
        列出所有可用的结果文件

        Returns:
            包含UUID和相关信息的字典
        """
        results = {}

        try:
            # 遍历所有UUID子目录
            if not os.path.exists(self.base_output_dir):
                return results

            for uuid_dir in os.listdir(self.base_output_dir):
                uuid_path = os.path.join(self.base_output_dir, uuid_dir)

                # 确保是目录
                if not os.path.isdir(uuid_path):
                    continue

                # 查找结果文件
                parser_result_path = os.path.join(uuid_path, "script_parser_result.json")

                if os.path.exists(parser_result_path):
                    try:
                        # 加载元数据信息
                        with open(parser_result_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)

                        metadata = data.get("metadata", {})
                        results[uuid_dir] = {
                            "result_path": parser_result_path,
                            "saved_at": metadata.get("saved_at", "未知"),
                            "last_modified": datetime.fromtimestamp(
                                os.path.getmtime(parser_result_path)
                            ).isoformat()
                        }

                    except Exception as e:
                        warning(f"无法读取结果元数据 (UUID: {uuid_dir}): {str(e)}")
                        results[uuid_dir] = {
                            "result_path": parser_result_path,
                            "saved_at": "未知",
                            "last_modified": datetime.fromtimestamp(
                                os.path.getmtime(parser_result_path)
                            ).isoformat()
                        }

            debug(f"找到{len(results)}个可用结果")
            return results

        except Exception as e:
            error(f"列出可用结果失败: {str(e)}")
            return results


def create_result_storage(base_output_dir: Optional[str] = None) -> ResultStorage:
    """
    创建结果存储实例的工厂函数

    Args:
        base_output_dir: 基础输出目录路径，默认为配置文件中的data_output路径

    Returns:
        ResultStorage实例
    """
    return ResultStorage(base_output_dir)


def save_script_parser_result(uuid: str, result_data: Dict[str, Any],
                              base_output_dir: str = "data/output") -> str:
    """
    保存剧本解析器结果的便捷函数

    Args:
        uuid: 请求的唯一标识符
        result_data: 剧本解析结果数据
        base_output_dir: 基础输出目录路径

    Returns:
        保存的文件路径
    """
    storage = create_result_storage(base_output_dir)
    return storage.save_result(uuid, result_data, "script_parser_result.json")


def load_script_parser_result(uuid: str,
                              base_output_dir: str = "data/output") -> Optional[Dict[str, Any]]:
    """
    加载剧本解析器结果的便捷函数

    Args:
        uuid: 请求的唯一标识符
        base_output_dir: 基础输出目录路径

    Returns:
        剧本解析结果数据，如果不存在则返回None
    """
    storage = create_result_storage(base_output_dir)
    return storage.load_result(uuid, "script_parser_result.json")