from contextlib import asynccontextmanager
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from database import init_db
from neo4j_db import close_driver
from redis_db import close_pool
from routers import search, papers, auth, user


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── 启动 ──────────────────────────────────────────────────────────────────
    await init_db()          # PostgreSQL: 创建表
    # Neo4j 驱动懒加载，首次使用时自动连接
    yield
    # ── 关闭 ──────────────────────────────────────────────────────────────────
    await close_driver()     # Neo4j: 关闭驱动
    await close_pool()       # Redis: 关闭连接池


app = FastAPI(title="ESASR API", lifespan=lifespan)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(search.router, prefix="/api/search", tags=["Search"])
app.include_router(papers.router, prefix="/api/papers", tags=["Papers"])
app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(user.router, prefix="/api/user", tags=["User"])


@app.get("/")
def read_root():
    return {"status": "ok", "message": "ESASR API is running"}


@app.get("/health")
async def health_check(response: Response):
    """健康检查端点，可验证各数据库连接状态。"""
    from redis_db import get_redis
    from neo4j_db import get_driver
    from database import engine
    from sqlalchemy import text

    status = {"api": "ok", "postgres": "unknown", "redis": "unknown", "neo4j": "unknown"}
    
    # Postgres ping
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        status["postgres"] = "ok"
    except Exception as e:
        status["postgres"] = f"error: {e}"

    # Redis ping
    try:
        r = get_redis()
        await r.ping()
        status["redis"] = "ok"
    except Exception as e:
        status["redis"] = f"error: {e}"

    # Neo4j ping
    try:
        driver = get_driver()
        await driver.verify_connectivity()
        status["neo4j"] = "ok"
    except Exception as e:
        status["neo4j"] = f"error: {e}"

    degraded = any(value != "ok" for key, value in status.items() if key != "api")
    status["overall"] = "degraded" if degraded else "ok"
    if degraded:
        response.status_code = 503
    return status
