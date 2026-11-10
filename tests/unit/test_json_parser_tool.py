"""
Copyright (c) 2025 neopen
Licensed under the MIT License.
See LICENSE File For Details.

@FileName: test_json_parser_tool.py
@Description: JSON 解析工具回归测试：截断响应识别与 Markdown 代码块提取
@Author: neopen
"""
import json

import pytest

from penshot.neopen.tools.json_parser_tool import JsonResponseParser

TRUNCATED_RESPONSE = """{
  "title": "记忆墙",
  "characters": [
    {
      "name": "李明",
      "gender": "男",
      "type": "adult",
      "role": "主角"
    }
  ],
  "scenes": [
    {
      "id": "scene_001",
      "location": "教室",
      "audio_context": {
        "scene_type": "indoor",
        "has_dialogue": true,
        "reverb": 0.4
      }
"""


def test_extract_direct_json():
    """完整 JSON 应直接解析成功"""
    text = '{"title": "测试", "scenes": []}'
    assert JsonResponseParser.extract_json(text) == {"title": "测试", "scenes": []}


def test_extract_from_markdown_codeblock():
    """应支持 ```json 代码块中的 JSON"""
    text = '说明如下：\n```json\n{"title": "测试"}\n```\n以上。'
    assert JsonResponseParser.extract_json(text) == {"title": "测试"}


def test_complete_json_with_trailing_text():
    """完整 JSON 后带说明文字时应能提取"""
    text = '{"title": "测试"} 以上是完整结果。'
    assert JsonResponseParser.extract_json(text) == {"title": "测试"}


def test_truncated_response_raises_informative_error():
    """被截断的 JSON 应抛出带诊断信息的错误"""
    with pytest.raises(json.JSONDecodeError) as exc_info:
        JsonResponseParser.extract_json(TRUNCATED_RESPONSE)

    message = str(exc_info.value)
    assert "JSON 响应不完整" in message
    assert "截断" in message


def test_is_incomplete_json():
    """括号/引号未闭合应判定为不完整"""
    assert JsonResponseParser._is_incomplete_json('{"a": [1, 2') is True
    assert JsonResponseParser._is_incomplete_json('{"a": "未闭合') is True
    assert JsonResponseParser._is_incomplete_json('{"a": [1, 2]}') is False
    # 转义引号不应误判
    assert JsonResponseParser._is_incomplete_json('{"a": "\\"已闭合\\""}') is False


def test_parse_with_fallback_returns_fallback_for_truncated():
    """截断响应在宽松模式下应返回 fallback，不向调用方抛出异常"""
    assert JsonResponseParser.parse_with_fallback(TRUNCATED_RESPONSE, fallback_value={"ok": False}) == {"ok": False}
