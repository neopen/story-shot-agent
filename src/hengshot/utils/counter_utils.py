"""
@FileName: counter_utils.py
@Description: 线程安全的数据递增器
@Author: HengLine
@Github: https://github.com/HengLine/video-shot-agent
@Time: 2026/1/17 22:32
"""

import threading
import time

class ThreadSafeCounter:
    """ 线程安全的整数计数器
        所有操作均为原子操作，适用于多线程环境下的计数需求。
    """
    def __init__(self, initial_value=0):
        self._value = initial_value
        self._lock = threading.Lock()

    def increment(self, delta=1):
        with self._lock:
            self._value += delta
            return self._value

    def get(self):
        with self._lock:
            return self._value

    def set(self, value):
        with self._lock:
            self._value = value



class ExpiringStringCounter:
    """ 带过期时间的线程安全字符串计数器
        适用于不同字符串的计数，若某字符串在指定时间内未被访问，则其计数器重置为0。
     """
    def __init__(self, expire_after=300):  # 默认 5 分钟过期
        self._data = {}  # {key: (count, last_access_time)}
        self._lock = threading.Lock()
        self._expire_after = expire_after

    def _cleanup_expired(self):
        """惰性清理：在每次访问时移除过期项（可选，也可用后台线程）"""
        now = time.time()
        expired_keys = [
            key for key, (_, ts) in self._data.items()
            if now - ts > self._expire_after
        ]
        for key in expired_keys:
            del self._data[key]

    def get_next(self, key: str) -> int:
        with self._lock:
            self._cleanup_expired()  # 清理过期项

            now = time.time()
            if key in self._data:
                count, _ = self._data[key]
                count += 1
            else:
                count = 1

            self._data[key] = (count, now)
            return count


if __name__ == '__main__':
    counter = ThreadSafeCounter()
    print(counter.increment())
    print(counter.increment())
    def worker():
        for _ in range(1000):
            counter.increment()


    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    print(counter.get())  # 应该输出 10000

    #---------------------------- 测试 ExpiringStringCounter ----------------------------#
    counter = ExpiringStringCounter(expire_after=5)  # 1分钟后未访问则清零

    print(counter.get_next("userA"))  # 1
    print(counter.get_next("userA"))  # 2
    print(counter.get_next("userB"))  # 1
    print(counter.get_next("userA"))  # 3
    print(counter.get_next("userA"))  # 4
    print(counter.get_next("userB"))  # 2
    print(counter.get_next("test"))  # 1

    # 等待 61 秒后...
    time.sleep(6)
    print(counter.get_next("userA"))  # 1 （因为已过期，重新开始）
