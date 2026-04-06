"""
@FileName: hash_utils.py
@Description: 
@Author: HiPeng
@Time: 2026/4/2 18:04
"""
import hashlib



def text_to_id(text: str, n: int = 2) -> str:
    """文本转短数字ID（默认6字节 → 最大15位正整数）"""
    # return str(int.from_bytes(hashlib.sha256(text.encode('utf-8')).digest()[:byte_len], 'big'))
    h = hashlib.sha256(text.encode()).digest()  # 固定32字节
    # if n * 3 > len(h): raise ValueError("n 过大，3n 需 ≤ 32")
    if n < 1: raise ValueError("n 必须 > 0")
    if n > 10: raise ValueError("n 不能大于10")
    mid = (len(h) - n) // 2
    return str(int.from_bytes(h[:n] + h[mid:mid+n] + h[-n:], 'big'))


def text_to_hash_str(text: str) -> str:
    hash_bytes = text_to_hash(text)
    # 3. 字节转为正整数（大端序保证跨平台一致）
    hash_int = int.from_bytes(hash_bytes, byteorder='big')
    # 4. 转为字符串返回
    return str(hash_int)

def text_to_256hash_str(text: str) -> str:
    hash_bytes = text_to_256hash(text)
    # 3. 字节转为正整数（大端序保证跨平台一致）
    hash_int = int.from_bytes(hash_bytes, byteorder='big')
    # 4. 转为字符串返回
    return str(hash_int)

def text_to_256hash(text: str) -> bytes:
    # 1. 编码为字节（UTF-8 兼容所有文本）
    text_bytes = text.encode('utf-8')
    # 2. 计算 SHA-256 哈希值
    hash_bytes = hashlib.sha256(text_bytes).digest()
    return hash_bytes

def text_to_hash(text: str) -> bytes:
    # 1. 编码为字节（UTF-8 兼容所有文本）
    text_bytes = text.encode('utf-8')
    # 2. 计算 SHA-256 哈希值
    hash_bytes = hashlib.md5(text_bytes).digest()
    return hash_bytes


def hash_large_text_file(filepath: str) -> str:
    sha256 = hashlib.sha256()
    with open(filepath, 'r', encoding='utf-8') as f:
        while chunk := f.read(8192):  # 每次读 8KB
            sha256.update(chunk.encode('utf-8'))
    return str(int.from_bytes(sha256.digest(), 'big'))
