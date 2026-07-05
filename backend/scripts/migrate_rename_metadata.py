"""
数据库迁移脚本：将 medical_knowledge_vectors 表的 metadata 列重命名为 extra_metadata
运行：python -m scripts.migrate_rename_metadata
"""
import asyncio
import logging
logger = logging.getLogger(__name__)
from database import async_engine
from sqlalchemy import text


async def migrate():
    logger.info("🔄 开始 metadata -> extra_metadata 迁移...")

    async with async_engine.connect() as conn:
        result = await conn.execute(
            text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'medical_knowledge_vectors'
            """)
        )
        columns = {row[0] for row in result.fetchall()}
        logger.info(f"   当前列: {columns}")

        if 'metadata' in columns and 'extra_metadata' not in columns:
            try:
                await conn.execute(
                    text("ALTER TABLE medical_knowledge_vectors RENAME COLUMN metadata TO extra_metadata")
                )
                await conn.commit()
                logger.info("✅ 已将 metadata 列重命名为 extra_metadata")
            except Exception as e:
                logger.error(f"⚠️ RENAME 失败，尝试 ADD/DROP 方式: {e}")
                await conn.execute(
                    text("ALTER TABLE medical_knowledge_vectors ADD COLUMN extra_metadata JSONB")
                )
                await conn.execute(
                    text("UPDATE medical_knowledge_vectors SET extra_metadata = metadata")
                )
                await conn.execute(
                    text("ALTER TABLE medical_knowledge_vectors DROP COLUMN metadata")
                )
                await conn.commit()
                logger.info("✅ 使用 ADD/UPDATE/DROP 方式迁移成功")
        elif 'extra_metadata' in columns:
            logger.info("✅ 列 extra_metadata 已存在，跳过迁移")
        else:
            logger.info("⚠️  未找到 metadata 列，跳过")

    logger.info("✅ 迁移完成")


if __name__ == "__main__":
    asyncio.run(migrate())
