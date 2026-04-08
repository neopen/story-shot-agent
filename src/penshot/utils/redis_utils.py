"""
@FileName: redis_utils.py
@Description: 从 env中加载配置创建redis 客户端
@Author: HiPeng
@Time: 2026/3/17 15:39
"""
import json
import os
from functools import lru_cache
from typing import Optional, Any

import redis

from penshot.logger import info, error, debug


class RedisClient:
    """Redis客户端类，从环境变量加载配置"""

    def __init__(self, connection_url: Optional[str] = None):
        """
        初始化Redis客户端

        Args:
            connection_url: Redis连接URL，如果为None则从环境变量加载
        """
        self.connection_url = connection_url or self._get_redis_url_from_env()
        self.client: Optional[redis.Redis] = None
        self._connect()

    def _get_redis_url_from_env(self) -> str:
        """
        从环境变量获取Redis连接URL

        支持的环境变量：
        - REDIS_URL: 完整的Redis连接URL（优先级最高）
        - REDIS_HOST: Redis主机地址
        - REDIS_PORT: Redis端口
        - REDIS_DB: Redis数据库编号
        - REDIS_PASSWORD: Redis密码
        - REDIS_SSL: 是否使用SSL连接

        Returns:
            Redis连接URL
        """
        # 如果设置了完整的REDIS_URL，直接使用
        redis_url = os.getenv('PENSHOT_REDIS_URL')
        if redis_url:
            return redis_url

        # 从环境变量获取各个配置项
        host = os.getenv('REDIS_HOST', 'localhost')
        port = os.getenv('REDIS_PORT', '6379')
        db = os.getenv('REDIS_DB', '0')
        password = os.getenv('REDIS_PASSWORD', '')
        ssl = os.getenv('REDIS_SSL', 'false').lower() == 'true'

        # 构建连接URL
        if password:
            auth_part = f":{password}@"
        else:
            auth_part = ""

        # 根据SSL设置选择协议
        protocol = "rediss" if ssl else "redis"

        return f"{protocol}://{auth_part}{host}:{port}/{db}"

    def _get_connection_params(self) -> dict:
        """
        从环境变量获取连接参数

        Returns:
            连接参数字典
        """
        params = {
            'host': os.getenv('REDIS_HOST', 'localhost'),
            'port': int(os.getenv('REDIS_PORT', '6379')),
            'db': int(os.getenv('REDIS_DB', '0')),
            'password': os.getenv('REDIS_PASSWORD', None) or None,
            'socket_timeout': float(os.getenv('REDIS_SOCKET_TIMEOUT', '5.0')),
            'socket_connect_timeout': float(os.getenv('REDIS_CONNECT_TIMEOUT', '5.0')),
            'retry_on_timeout': os.getenv('REDIS_RETRY_ON_TIMEOUT', 'true').lower() == 'true',
            'max_connections': int(os.getenv('REDIS_MAX_CONNECTIONS', '10')),
            'decode_responses': os.getenv('REDIS_DECODE_RESPONSES', 'true').lower() == 'true',
        }

        # SSL配置
        if os.getenv('REDIS_SSL', 'false').lower() == 'true':
            params['ssl'] = True
            params['ssl_cert_reqs'] = os.getenv('REDIS_SSL_CERT_REQS', 'required')

        # 集群配置
        if os.getenv('REDIS_CLUSTER', 'false').lower() == 'true':
            params['redis_cluster'] = True
            params['startup_nodes'] = os.getenv('REDIS_STARTUP_NODES', '').split(',')

        return params

    def _connect(self):
        """建立Redis连接"""
        try:
            if os.getenv('REDIS_CLUSTER', 'false').lower() == 'true':
                # 集群模式连接
                from redis.cluster import RedisCluster
                params = self._get_connection_params()
                startup_nodes = params.pop('startup_nodes', [])
                params.pop('redis_cluster', None)

                if startup_nodes:
                    self.client = RedisCluster(
                        startup_nodes=startup_nodes,
                        **params
                    )
                else:
                    # 如果未指定启动节点，使用普通连接
                    self.client = redis.Redis.from_url(
                        self.connection_url,
                        **params
                    )
            else:
                # 单节点模式连接
                self.client = redis.Redis.from_url(
                    self.connection_url,
                    **self._get_connection_params()
                )

            # 测试连接
            self.client.ping()
            debug(f"Redis连接成功: {self.connection_url}")

        except redis.ConnectionError as e:
            error(f"Redis连接失败: {e}")
            raise
        except Exception as e:
            error(f"Redis初始化异常: {e}")
            raise

    def get_client(self) -> redis.Redis:
        """获取Redis客户端实例"""
        if not self.client:
            self._connect()
        return self.client

    def close(self):
        """关闭Redis连接"""
        if self.client:
            self.client.close()
            info("Redis连接已关闭")

    def __enter__(self):
        """上下文管理器入口"""
        return self.get_client()

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.close()

    # 常用操作方法
    def set(self, key: str, value: Any, expire: Optional[int] = None) -> bool:
        """
        设置键值对

        Args:
            key: 键名
            value: 值（会自动序列化）
            expire: 过期时间（秒）

        Returns:
            是否设置成功
        """
        try:
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)

            result = self.client.set(key, value)

            if expire and result:
                self.client.expire(key, expire)

            return result
        except Exception as e:
            error(f"设置键 {key} 失败: {e}")
            return False

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取键值

        Args:
            key: 键名
            default: 默认值

        Returns:
            键值
        """
        try:
            value = self.client.get(key)
            if value is None:
                return default

            # 尝试解析JSON
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value

        except Exception as e:
            error(f"获取键 {key} 失败: {e}")
            return default

    def delete(self, *keys: str) -> int:
        """删除键"""
        try:
            return self.client.delete(*keys)
        except Exception as e:
            error(f"删除键失败: {e}")
            return 0

    def exists(self, key: str) -> bool:
        """检查键是否存在"""
        try:
            return bool(self.client.exists(key))
        except Exception as e:
            error(f"检查键 {key} 失败: {e}")
            return False

    def expire(self, key: str, time: int) -> bool:
        """设置过期时间"""
        try:
            return self.client.expire(key, time)
        except Exception as e:
            error(f"设置过期时间失败: {e}")
            return False

    def ttl(self, key: str) -> int:
        """获取键的剩余生存时间"""
        try:
            return self.client.ttl(key)
        except Exception as e:
            error(f"获取TTL失败: {e}")
            return -2

    def incr(self, key: str, amount: int = 1) -> Optional[int]:
        """自增操作"""
        try:
            return self.client.incr(key, amount)
        except Exception as e:
            error(f"自增操作失败: {e}")
            return None

    def hset(self, name: str, key: str, value: Any) -> bool:
        """哈希表设置"""
        try:
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            return self.client.hset(name, key, value)
        except Exception as e:
            error(f"哈希表设置失败: {e}")
            return False

    def hget(self, name: str, key: str, default: Any = None) -> Any:
        """哈希表获取"""
        try:
            value = self.client.hget(name, key)
            if value is None:
                return default

            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value

        except Exception as e:
            error(f"哈希表获取失败: {e}")
            return default


@lru_cache(maxsize=1)
def get_redis_url() -> str:
    redis_client = RedisClient()
    return redis_client.connection_url

# 使用示例
if __name__ == "__main__":
    # 创建Redis客户端实例
    redis_client = RedisClient()

    # 使用示例
    try:
        # 设置字符串值
        redis_client.set("name", "张三", expire=3600)

        # 设置JSON值
        user = {"id": 1, "name": "李四", "age": 25}
        redis_client.set("user:1", user)

        # 获取值
        name = redis_client.get("name")
        print(f"name: {name}")

        user_data = redis_client.get("user:1")
        print(f"user: {user_data}")

        # 使用哈希表
        redis_client.hset("users", "1001", {"name": "王五", "age": 30})
        user_hash = redis_client.hget("users", "1001")
        print(f"hash user: {user_hash}")

        # 自增操作
        count = redis_client.incr("counter")
        print(f"counter: {count}")

    except Exception as e:
        print(f"操作失败: {e}")
    finally:
        redis_client.close()
