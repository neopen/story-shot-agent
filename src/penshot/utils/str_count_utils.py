"""
@FileName: str_count_utils.py
@Description: 统计单词数的工具函数
@Author: HiPeng
@Time: 2026/3/29 16:41
"""
import re
from typing import Literal


def count_words_advanced(text: str, include_numbers: bool = True) -> int:
    """
    高级单词计数

    Args:
        text: 输入文本
        include_numbers: 是否将纯数字计入单词
    """
    if include_numbers:
        # 匹配：单词、带连字符的单词、数字
        pattern = r"\b[a-zA-Z]+(?:[-'][a-zA-Z]+)*\b|\b\d+(?:\.\d+)?\b"
    else:
        # 只匹配字母单词
        pattern = r"\b[a-zA-Z]+(?:[-'][a-zA-Z]+)*\b"

    words = re.findall(pattern, text)
    return len(words)



def count_words_mixed(text: str, include_numbers=False) -> dict:
    """
    统计中英文混合文本的单词/字符数

    Returns:
        dict: {
            'english_words': 英文单词数,
            'chinese_chars': 中文字符数,
            'numbers': 数字个数,
            'total_tokens': 总词元数
        }
    """
    # 英文单词（包括带连字符、撇号）
    english_words = re.findall(r"\b[a-zA-Z]+(?:[-'][a-zA-Z]+)*\b", text)

    # 中文字符（包括中文标点）
    chinese_chars = re.findall(r"[\u4e00-\u9fff]", text)

    # 数字
    numbers = []
    if include_numbers:
        numbers = re.findall(r"\b\d+(?:\.\d+)?\b", text)

    return {
        'english_words': len(english_words),
        'chinese_chars': len(chinese_chars),
        'numbers': len(numbers),
        'total_tokens': len(english_words) + len(chinese_chars) + len(numbers)
    }


# 下载分词数据（只需执行一次）
# nltk.download('punkt')
def count_words_nltk(text: str) -> int:
    from nltk.tokenize import word_tokenize
    """使用 NLTK 进行专业分词"""
    try:
        tokens = word_tokenize(text)
        # 过滤标点符号
        words = [t for t in tokens if t.isalpha() or t.replace("'", "").isalpha()]
        return len(words)
    except Exception:
        # fallback 到正则方法
        pattern = r"\b[a-zA-Z]+(?:[-'][a-zA-Z]+)*\b|[\u4e00-\u9fff]"
        return len(re.findall(pattern, text))


def count_words_full(
        text: str,
        mode: Literal['all', 'words_only', 'cn_only', 'en_only'] = 'all',
        include_numbers: bool = True,
        include_punctuation: bool = False
) -> int:
    """
    灵活的单词计数函数

    Args:
        text: 输入文本
        mode:
            - 'all': 英文 + 中文 + 数字
            - 'words_only': 仅英文单词 + 中文
            - 'cn_only': 仅中文
            - 'en_only': 仅英文
        include_numbers: 是否计入数字
        include_punctuation: 是否计入标点（一般不推荐）
    """
    patterns = {
        'en_words': r"\b[a-zA-Z]+(?:[-'][a-zA-Z]+)*\b",
        'cn_chars': r"[\u4e00-\u9fff]",  # 基本汉字
        'cn_extended': r"[\u4e00-\u9fff\u3400-\u4dbf\U00020000-\U0002a6df]",  # 扩展汉字
        'numbers': r"\b\d+(?:\.\d+)?\b",
        'punctuation': r"[，。！？；：''""、…—]",  # 中文标点
    }

    if mode == 'en_only':
        pattern = patterns['en_words']
    elif mode == 'cn_only':
        pattern = patterns['cn_chars']
    elif mode == 'words_only':
        pattern = f"{patterns['en_words']}|{patterns['cn_chars']}"
    else:  # 'all'
        parts = [patterns['en_words'], patterns['cn_chars']]
        if include_numbers:
            parts.append(patterns['numbers'])
        if include_punctuation:
            parts.append(patterns['punctuation'])
        pattern = '|'.join(parts)

    return len(re.findall(pattern, text))


def only_count_en(text: str) -> int:
    """仅统计英文字符数"""
    return count_words_full(text, mode="en_only", include_numbers=False, include_punctuation=False)


def final_count_words(text: str) -> int:
    """最终的单词计数函数，结合多种方法"""
    try:
        return count_words_nltk(text)
    except Exception:
        return count_words_full(text)


if __name__ == '__main__':

    text = "Hello 世界！I have 3 个 apples 和 2 个 oranges."
    print(f"NLTK 单词数：{final_count_words(text)}")  # 输出：8
    print("-----------------")

    print(f"完整单词数：{count_words_full(text, include_numbers=False)}")  # 输出：8
    print("-----------------")

    print(count_words_mixed(text))
    print("-----------------")

    # 测试
    print(count_words_advanced(text, include_numbers=True))  # 6
    print(count_words_advanced(text, include_numbers=False))  # 4

