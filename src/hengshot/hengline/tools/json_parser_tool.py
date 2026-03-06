"""
@FileName: json_parser_tool.py
@Description: JSON响应解析工具模块，提供从LLM响应中提取和解析JSON数据的功能，支持处理Markdown代码块中的JSON
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2025/12/18
"""
import json
import re
from typing import Dict, Any, Optional, Union

from hengshot.logger import debug, info, warning, error
from hengshot.utils.log_utils import print_log_exception


class JsonResponseParser:
    """
    JSON响应解析器
    负责从LLM响应中提取和解析JSON数据，处理各种格式的响应
    """

    @staticmethod
    def extract_json(response: Union[str, Any]) -> dict[str, Any] | None:
        """
        从LLM响应中提取JSON数据
        支持直接JSON响应和Markdown代码块中的JSON
        
        Args:
            response: LLM响应，可以是字符串或带有content属性的对象
            
        Returns:
            解析后的JSON字典
            
        Raises:
            json.JSONDecodeError: 当无法解析JSON时抛出
        """
        # 处理可能的响应对象
        if hasattr(response, 'content'):
            response_text = response.content
        else:
            response_text = str(response)

        # 确保response_text是字符串
        response_text = str(response_text).strip()

        # 检查响应是否为空
        if not response_text:
            raise json.JSONDecodeError("LLM响应为空", "", 0)

        # 尝试直接解析JSON
        try:
            result = json.loads(response_text)
            return result
        except json.JSONDecodeError:
            info("直接解析失败，尝试从Markdown代码块中提取JSON")
            # 尝试从Markdown代码块中提取JSON
            try:
                result = JsonResponseParser._extract_from_markdown_codeblock(response_text)
                debug("成功从Markdown代码块中提取JSON")
                return result
            except json.JSONDecodeError:
                warning("从代码块提取失败，尝试清理和修复响应文本")
                # 尝试清理和修复响应文本
                cleaned_text = JsonResponseParser._clean_response_text(response_text)
                try:
                    result = json.loads(cleaned_text)
                    debug("成功清理后解析JSON响应")
                    return result
                except json.JSONDecodeError:
                    error(f"所有Json解析尝试都失败: {cleaned_text}")
                    # 尝试从文本中提取JSON
                    json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                    if json_match:
                        try:
                            return json.loads(json_match.group())
                        except:
                            raise

    @staticmethod
    def _extract_from_markdown_codeblock(text: str) -> Dict[str, Any]:
        """
        从Markdown代码块中提取JSON数据
        
        Args:
            text: 包含Markdown代码块的文本
            
        Returns:
            解析后的JSON字典
            
        Raises:
            json.JSONDecodeError: 当无法解析提取的内容为JSON时抛出
        """
        # 匹配可能的Markdown代码块，支持json标记和无标记
        json_match = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
        if json_match:
            json_content = json_match.group(1)
            # 尝试清理和解析提取的内容
            json_content = json_content.strip()
            return json.loads(json_content)
        else:
            # 如果没有找到代码块，尝试提取第一个{到最后一个}之间的内容
            if '{' in text and '}' in text:
                start_idx = text.find('{')
                end_idx = text.rfind('}') + 1
                potential_json = text[start_idx:end_idx]
                return json.loads(potential_json)
            raise json.JSONDecodeError("未找到Markdown代码块或JSON内容", text, 0)

    @staticmethod
    def _clean_response_text(text: str) -> str:
        """
        清理响应文本，移除可能干扰JSON解析的内容
        
        Args:
            text: 需要清理的文本
            
        Returns:
            清理后的文本
        """
        # 移除可能的前缀
        if text.startswith(("response:", "输出:", "result:", "答案:", "回复:")):
            text = ':'.join(text.split(':', 1)[1]).strip()

        # 移除可能的注释前缀
        lines = text.split('\n')
        cleaned_lines = []
        for line in lines:
            # 跳过空行
            if not line.strip():
                continue
            # 跳过以注释符号开头的行（除非在JSON字符串内部）
            stripped = line.strip()
            if not (stripped.startswith("//") or stripped.startswith("#") or stripped.startswith("/*")):
                cleaned_lines.append(line)

        cleaned_text = '\n'.join(cleaned_lines)

        # 尝试提取第一个{到最后一个}之间的内容
        if '{' in cleaned_text and '}' in cleaned_text:
            start_idx = cleaned_text.find('{')
            end_idx = cleaned_text.rfind('}') + 1
            cleaned_text = cleaned_text[start_idx:end_idx]

        return cleaned_text

    @classmethod
    def parse_with_fallback(cls, response: Union[str, Any], fallback_value: Any = None) -> Dict[str, Any]:
        """
        解析JSON响应，失败时返回fallback值而不是抛出异常
        
        Args:
            response: LLM响应
            fallback_value: 解析失败时返回的值，默认为空字典
            
        Returns:
            解析后的JSON字典或fallback值
        """
        try:
            return cls.extract_json(response)
        except Exception as e:
            warning(f"JSON解析失败: {str(e)}")
            print_log_exception()
            # debug(f"原始响应文本: {str(response)[:200]}...")  # 记录部分原始响应用于调试
            debug(f"原始响应文本: {str(response)}")  # 记录部分原始响应用于调试
            return fallback_value if fallback_value is not None else {}

    @classmethod
    def validate_json_structure(cls, json_data: Dict[str, Any], required_fields: list = None) -> bool:
        """
        验证解析后的JSON数据是否包含必要的字段
        
        Args:
            json_data: 解析后的JSON数据
            required_fields: 需要验证的字段列表
            
        Returns:
            如果包含所有必要字段则返回True，否则返回False
        """
        if required_fields is None:
            required_fields = []

        for field in required_fields:
            if field not in json_data:
                warning(f"JSON验证失败：缺少必要字段 '{field}'")
                return False

        return True


# 全局实例，方便直接导入使用
json_parser = JsonResponseParser()


# 便捷函数，便于直接调用
def parse_json_response(response: Union[str, Any], fallback_value: Any = None) -> Dict[str, Any]:
    """
    便捷函数：从LLM响应中解析JSON
    
    Args:
        response: LLM响应
        fallback_value: 解析失败时返回的值
        
    Returns:
        解析后的JSON字典或fallback值
    """
    return json_parser.parse_with_fallback(response, fallback_value)


def extract_json_from_markdown(text: str) -> Optional[Dict[str, Any]]:
    """
    便捷函数：从Markdown文本中提取JSON
    
    Args:
        text: 包含可能JSON的Markdown文本
        
    Returns:
        解析后的JSON字典或None
    """
    try:
        return json_parser._extract_from_markdown_codeblock(text)
    except Exception:
        return None
