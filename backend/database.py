from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
import logging
logger = logging.getLogger(__name__)
from sqlalchemy import create_engine, text
from config import get_settings

settings = get_settings()

# 异步引擎
async_engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# 同步引擎（建表用）
sync_engine = create_engine(settings.database_sync_url, echo=False)


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def check_db_connection() -> bool:
    try:
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"数据库连接失败: {e}")
        return False


async def check_pgvector() -> bool:
    try:
        async with async_engine.connect() as conn:
            result = await conn.execute(
                text("SELECT extname, extversion FROM pg_extension WHERE extname = 'vector'")
            )
            row = result.fetchone()
            if row:
                logger.info(f"   pgvector 版本: {row[1]}")
                return True
            return False
    except Exception as e:
        logger.error(f"   pgvector 检查失败: {e}")
        return False


def init_db():
    from models import Base

    with sync_engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\""))
        conn.commit()

    Base.metadata.create_all(sync_engine)
    logger.info("   数据库表创建完成")