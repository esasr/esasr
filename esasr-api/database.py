"""
database.py — PostgreSQL 异步连接（SQLAlchemy 2.x async）
"""
import os
import socket
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from config import cfg

def _postgres_reachable() -> bool:
    """Keep local development usable when Docker/PostgreSQL is not running."""
    if os.getenv("SCHOLARSEEKER_DB", "").lower() == "sqlite":
        return False
    try:
        with socket.create_connection((cfg.db.host, int(cfg.db.port)), timeout=0.3):
            return True
    except OSError:
        return False


_using_sqlite = not _postgres_reachable()
if _using_sqlite:
    sqlite_path = Path(__file__).parent / "scholarseeker-dev.db"
    database_url = f"sqlite+aiosqlite:///{sqlite_path}"
    engine = create_async_engine(database_url, echo=cfg.app.debug)
    print(f"[Database] PostgreSQL unavailable; using local SQLite development database: {sqlite_path}")
else:
    engine = create_async_engine(
        cfg.postgres_url,
        pool_size=cfg.db.pool_size,
        max_overflow=cfg.db.max_overflow,
        pool_pre_ping=cfg.db.pool_pre_ping,
        echo=cfg.app.debug,
    )

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

class Base(DeclarativeBase):
    pass


async def get_db():
    """FastAPI 异步 DB 依赖注入。"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db():
    """应用启动时创建所有表（开发用；生产环境用 Alembic）。"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
