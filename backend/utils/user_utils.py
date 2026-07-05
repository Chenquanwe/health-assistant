"""
用户相关的工具函数
"""
from sqlalchemy import select
from database import AsyncSessionLocal
from models.user import User
from models.base import generate_uuid


async def ensure_user_exists(user_id: str, username: str = None):
    """确保用户存在，如果不存在则创建"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()

        if user is None:
            # 用户不存在，创建
            new_user = User(
                id=user_id,
                username=username or user_id,
                password_hash="",
            )
            session.add(new_user)
            await session.commit()
            return True
        return False


async def create_default_user():
    """创建默认用户用于测试"""
    return await ensure_user_exists("default_user", "默认用户")
