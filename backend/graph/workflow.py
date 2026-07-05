"""
Checkpointer 初始化与管理
"""

import asyncio
import logging
logger = logging.getLogger(__name__)
import psycopg
from graph.async_saver import AsyncPostgresSaver
from config import get_settings

checkpointer = None
_checkpointer_cm = None


def _init_checkpointer_sync():
    """同步初始化 Checkpointer"""
    global checkpointer, _checkpointer_cm
    settings = get_settings()
    
    db_url = settings.database_url.replace("+asyncpg", "").replace("+psycopg2", "")
    
    if "?" in db_url:
        db_url += "&connect_timeout=10&sslmode=disable&keepalives_idle=30"
    else:
        db_url += "?connect_timeout=10&sslmode=disable&keepalives_idle=30"
    
    safe_url = db_url
    if "@" in db_url:
        before, after = db_url.split("@", 1)
        if ":" in before and "://" in before:
            proto, rest = before.split("://", 1)
            if ":" in rest:
                user, pwd = rest.split(":", 1)
                safe_url = f"{proto}://{user}:****@{after}"
    logger.info(f"📡 数据库连接字符串（脱敏）: {safe_url}")
    
    try:
        test_conn = psycopg.connect(db_url)
        with test_conn.cursor() as cur:
            cur.execute("SELECT 1")
        test_conn.close()
        logger.info("✅ 数据库连接测试成功")
    except Exception as e:
        logger.error(f"❌ 数据库连接测试失败: {e}")
        raise
    
    _checkpointer_cm = AsyncPostgresSaver.from_conn_string(db_url)
    checkpointer = _checkpointer_cm.__enter__()
    checkpointer.setup()
    logger.info("✅ PostgresSaver 初始化完成")


async def init_checkpointer():
    """在应用启动时初始化并测试连接"""
    await asyncio.to_thread(_init_checkpointer_sync)


async def close_checkpointer():
    """在应用关闭时清理连接"""
    global checkpointer, _checkpointer_cm
    if _checkpointer_cm:
        try:
            await asyncio.to_thread(_checkpointer_cm.__exit__, None, None, None)
            logger.info("✅ PostgresSaver 连接已关闭")
        except Exception as e:
            logger.info(f"⚠️ 关闭 PostgresSaver 时出错: {e}")
        checkpointer = None
        _checkpointer_cm = None


def get_checkpointer():
    """获取全局单例"""
    return checkpointer
