"""
redis_db.py — Redis 缓存连接管理
"""
import json
from typing import Any, Optional
import redis.asyncio as aioredis
from config import cfg

_pool: aioredis.ConnectionPool | None = None


def get_pool() -> aioredis.ConnectionPool:
    """返回全局 Redis 连接池（单例）。"""
    global _pool
    if _pool is None:
        _pool = aioredis.ConnectionPool.from_url(
            cfg.redis_url,
            max_connections=20,
            decode_responses=True,
        )
    return _pool


def get_redis() -> aioredis.Redis:
    """返回 Redis 客户端（共享连接池）。"""
    return aioredis.Redis(connection_pool=get_pool())


async def close_pool():
    """应用关闭时调用。"""
    global _pool
    if _pool:
        await _pool.aclose()
        _pool = None


# ── 便捷缓存操作 ──────────────────────────────────────────────────────────────

async def cache_get(key: str) -> Optional[Any]:
    """从缓存读取 JSON 数据，未命中返回 None。"""
    try:
        r = get_redis()
        raw = await r.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception:
        return None


async def cache_set(key: str, value: Any, ttl: int) -> None:
    """将数据序列化为 JSON 写入缓存，并设置 TTL（秒）。"""
    try:
        r = get_redis()
        await r.setex(key, ttl, json.dumps(value, ensure_ascii=False))
    except Exception:
        return None


async def cache_delete(key: str) -> None:
    r = get_redis()
    await r.delete(key)


async def cache_exists(key: str) -> bool:
    r = get_redis()
    return bool(await r.exists(key))
