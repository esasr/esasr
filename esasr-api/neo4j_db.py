"""
neo4j_db.py — Neo4j 图数据库连接管理
"""
from neo4j import AsyncGraphDatabase, AsyncDriver
from config import cfg

_driver: AsyncDriver | None = None


def get_driver() -> AsyncDriver:
    """返回全局 Neo4j 驱动（单例）。"""
    global _driver
    if _driver is None:
        _driver = AsyncGraphDatabase.driver(
            cfg.neo4j_bolt_url,
            auth=(cfg.neo4j.user, cfg.neo4j_password),
            database=cfg.neo4j.database,
        )
    return _driver


async def close_driver():
    """应用关闭时调用。"""
    global _driver
    if _driver:
        await _driver.close()
        _driver = None


async def get_neo4j_session():
    """FastAPI 依赖注入：提供 Neo4j 异步 session。"""
    driver = get_driver()
    async with driver.session(database=cfg.neo4j.database) as session:
        yield session


async def run_query(cypher: str, parameters: dict = None) -> list:
    """便捷函数：执行 Cypher 查询并返回结果列表。"""
    driver = get_driver()
    async with driver.session(database=cfg.neo4j.database) as session:
        result = await session.run(cypher, parameters or {})
        return [record.data() async for record in result]
