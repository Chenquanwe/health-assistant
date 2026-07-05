"""
数据库迁移脚本：为 medical_knowledge_vectors 表添加 chunk_index 字段
运行：python -m scripts.migrate_knowledge_vectors
"""
import asyncio
import logging
logger = logging.getLogger(__name__)
from database import AsyncSessionLocal
from sqlalchemy import text


async def migrate():
    async with AsyncSessionLocal() as session:
        await session.execute(text(
            "ALTER TABLE medical_knowledge_vectors ADD COLUMN IF NOT EXISTS chunk_index INTEGER DEFAULT 0"
        ))
        await session.commit()
        logger.info("[迁移] medical_knowledge_vectors 表 chunk_index 字段已添加")


if __name__ == "__main__":
    asyncio.run(migrate())
