"""
数据库迁移脚本：为 conversations 表添加中断恢复相关字段
运行：python -m scripts.migrate_add_workflow_fields
"""
import asyncio
import logging
logger = logging.getLogger(__name__)
from database import async_engine, AsyncSessionLocal
from sqlalchemy import text


async def migrate():
    """执行数据库迁移"""
    logger.info("🔄 开始数据库迁移...")

    async with async_engine.connect() as conn:
        # 检查字段是否存在
        result = await conn.execute(
            text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'conversations'
                AND column_name IN ('workflow_state', 'uploaded_files', 'current_node', 'last_activity')
            """)
        )
        existing = {row[0] for row in result.fetchall()}

        # 添加 workflow_state 字段
        if 'workflow_state' not in existing:
            await conn.execute(
                text("ALTER TABLE conversations ADD COLUMN workflow_state JSONB")
            )
            logger.info("   ✅ 添加字段: workflow_state")

        # 添加 uploaded_files 字段
        if 'uploaded_files' not in existing:
            await conn.execute(
                text("ALTER TABLE conversations ADD COLUMN uploaded_files JSONB")
            )
            logger.info("   ✅ 添加字段: uploaded_files")

        # 添加 current_node 字段
        if 'current_node' not in existing:
            await conn.execute(
                text("ALTER TABLE conversations ADD COLUMN current_node VARCHAR(50)")
            )
            logger.info("   ✅ 添加字段: current_node")

        # 添加 last_activity 字段
        if 'last_activity' not in existing:
            await conn.execute(
                text("ALTER TABLE conversations ADD COLUMN last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
            )
            logger.info("   ✅ 添加字段: last_activity")

        await conn.commit()

    logger.info("✅ 数据库迁移完成！")
    logger.info("\n新增字段说明：")
    logger.info("   - workflow_state: 保存 LangGraph 工作流完整状态（JSON）")
    logger.info("   - uploaded_files: 保存已上传的文件信息列表（JSON）")
    logger.info("   - current_node: 当前工作流节点名称")
    logger.info("   - last_activity: 最后活动时间，用于判断会话是否中断")


if __name__ == "__main__":
    asyncio.run(migrate())
