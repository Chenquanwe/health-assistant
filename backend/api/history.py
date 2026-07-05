"""
历史记录 API 路由
功能：查询会话列表、会话详情（含消息和报告）
"""
from fastapi import APIRouter, Query, HTTPException, Depends
from sqlalchemy import select, desc, delete
from sqlalchemy.orm import selectinload
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from database import AsyncSessionLocal
from models.base import generate_uuid
from models.conversation import Conversation, Message
from models.report import HealthReport, CheckReport
from utils.user_utils import ensure_user_exists

router = APIRouter(prefix="/api/history", tags=["历史记录"])


class MessageResponse(BaseModel):
    """消息响应"""
    id: str
    role: str
    content: str
    message_type: str
    created_at: datetime


class HealthReportResponse(BaseModel):
    """健康报告响应"""
    id: str
    content_markdown: Optional[str]
    risk_level: Optional[str]
    created_at: datetime


class CheckReportResponse(BaseModel):
    """检查报告响应"""
    id: str
    filename: Optional[str]
    file_type: Optional[str]
    analysis_result: Optional[str]
    created_at: datetime


class ConversationListItem(BaseModel):
    """会话列表项"""
    id: str
    title: Optional[str]
    status: str
    message_count: int
    created_at: datetime
    updated_at: datetime


class ConversationDetail(BaseModel):
    """会话详情"""
    id: str
    title: Optional[str]
    status: str
    messages: List[MessageResponse]
    health_reports: List[HealthReportResponse]
    check_reports: List[CheckReportResponse]
    created_at: datetime
    updated_at: datetime


class ConversationListResponse(BaseModel):
    """会话列表响应"""
    success: bool
    message: str
    data: List[ConversationListItem]
    total: int
    page: int
    page_size: int


class ConversationDetailResponse(BaseModel):
    """会话详情响应"""
    success: bool
    message: str
    data: Optional[ConversationDetail]


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


@router.get("", response_model=ConversationListResponse)
async def get_conversation_list(
    user_id: str = Query(default="default_user", description="用户ID"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=10, ge=1, le=50, description="每页数量"),
    status: Optional[str] = Query(default=None, description="筛选状态: active/completed"),
):
    """
    获取会话列表（分页）
    """
    # 确保用户存在
    await ensure_user_exists(user_id, "默认用户")

    offset = (page - 1) * page_size

    async with AsyncSessionLocal() as session:
        try:
            # 构建查询
            query = select(Conversation).where(Conversation.user_id == user_id)

            if status:
                query = query.where(Conversation.status == status)

            # 获取总数
            count_query = select(Conversation).where(Conversation.user_id == user_id)
            if status:
                count_query = count_query.where(Conversation.status == status)
            total_result = await session.execute(count_query)
            total = len(total_result.scalars().all())

            # 分页查询
            query = query.order_by(desc(Conversation.updated_at)).offset(offset).limit(page_size)
            result = await session.execute(query)
            conversations = result.scalars().all()

            # 获取每个会话的消息数量
            items = []
            for conv in conversations:
                msg_count_result = await session.execute(
                    select(Message).where(Message.conversation_id == conv.id)
                )
                msg_count = len(msg_count_result.scalars().all())

                items.append(ConversationListItem(
                    id=conv.id,
                    title=conv.title or f"问诊记录 {conv.created_at.strftime('%Y-%m-%d %H:%M')}",
                    status=conv.status,
                    message_count=msg_count,
                    created_at=conv.created_at,
                    updated_at=conv.updated_at,
                ))

            return ConversationListResponse(
                success=True,
                message="获取成功",
                data=items,
                total=total,
                page=page,
                page_size=page_size,
            )

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation_detail(
    conversation_id: str,
    user_id: str = Query(default="default_user", description="用户ID"),
):
    """
    获取会话详情（包括消息列表、报告列表）
    """
    async with AsyncSessionLocal() as session:
        try:
            # 查询会话
            result = await session.execute(
                select(Conversation).where(
                    Conversation.id == conversation_id,
                    Conversation.user_id == user_id
                )
            )
            conversation = result.scalar_one_or_none()

            if not conversation:
                raise HTTPException(status_code=404, detail="会话不存在")

            # 查询消息
            messages_result = await session.execute(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at)
            )
            messages = messages_result.scalars().all()

            # 查询健康报告
            reports_result = await session.execute(
                select(HealthReport).where(HealthReport.conversation_id == conversation_id)
            )
            health_reports = reports_result.scalars().all()

            # 查询检查报告
            check_result = await session.execute(
                select(CheckReport).where(CheckReport.conversation_id == conversation_id)
            )
            check_reports = check_result.scalars().all()

            return ConversationDetailResponse(
                success=True,
                message="获取成功",
                data=ConversationDetail(
                    id=conversation.id,
                    title=conversation.title or f"问诊记录 {conversation.created_at.strftime('%Y-%m-%d %H:%M')}",
                    status=conversation.status,
                    messages=[
                        MessageResponse(
                            id=m.id,
                            role=m.role,
                            content=m.content,
                            message_type=m.message_type,
                            created_at=m.created_at,
                        )
                        for m in messages
                    ],
                    health_reports=[
                        HealthReportResponse(
                            id=r.id,
                            content_markdown=r.content_markdown,
                            risk_level=r.risk_level,
                            created_at=r.created_at,
                        )
                        for r in health_reports
                    ],
                    check_reports=[
                        CheckReportResponse(
                            id=r.id,
                            filename=r.filename,
                            file_type=r.file_type,
                            analysis_result=r.analysis_result,
                            created_at=r.created_at,
                        )
                        for r in check_reports
                    ],
                    created_at=conversation.created_at,
                    updated_at=conversation.updated_at,
                ),
            )

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


class RenameRequest(BaseModel):
    """重命名请求"""
    title: str


@router.patch("/{conversation_id}")
async def update_conversation_title(
    conversation_id: str,
    data: RenameRequest,
    user_id: str = Query(default="default_user", description="用户ID"),
):
    """
    更新会话标题
    """
    title = data.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="标题不能为空")

    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(
                select(Conversation).where(
                    Conversation.id == conversation_id,
                    Conversation.user_id == user_id
                )
            )
            conversation = result.scalar_one_or_none()

            if not conversation:
                raise HTTPException(status_code=404, detail="会话不存在")

            conversation.title = title.strip()
            await session.commit()

            return {"success": True, "message": "更新成功"}

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"更新失败: {str(e)}")


@router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    user_id: str = Query(default="default_user", description="用户ID"),
):
    """
    删除会话（级联删除关联数据）
    """
    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(
                select(Conversation).where(
                    Conversation.id == conversation_id,
                    Conversation.user_id == user_id
                )
            )
            conversation = result.scalar_one_or_none()

            if not conversation:
                raise HTTPException(status_code=404, detail="会话不存在")

            await session.execute(
                delete(Message).where(Message.conversation_id == conversation_id)
            )
            await session.execute(
                delete(HealthReport).where(HealthReport.conversation_id == conversation_id)
            )
            await session.execute(
                delete(CheckReport).where(CheckReport.conversation_id == conversation_id)
            )

            await session.delete(conversation)
            await session.commit()

            return {"success": True, "message": "删除成功"}

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")


@router.get("/stats/summary")
async def get_conversation_stats(
    user_id: str = Query(default="default_user", description="用户ID"),
):
    """
    获取会话统计信息
    """
    async with AsyncSessionLocal() as session:
        try:
            # 总会话数
            total_result = await session.execute(
                select(Conversation).where(Conversation.user_id == user_id)
            )
            total = len(total_result.scalars().all())

            # 已完成数
            completed_result = await session.execute(
                select(Conversation).where(
                    Conversation.user_id == user_id,
                    Conversation.status == "completed"
                )
            )
            completed = len(completed_result.scalars().all())

            # 本月会话数
            from datetime import datetime
            first_day = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            monthly_result = await session.execute(
                select(Conversation).where(
                    Conversation.user_id == user_id,
                    Conversation.created_at >= first_day
                )
            )
            monthly = len(monthly_result.scalars().all())

            return {
                "success": True,
                "message": "获取成功",
                "data": {
                    "total": total,
                    "completed": completed,
                    "active": total - completed,
                    "monthly": monthly,
                },
            }

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


class CreateConversationRequest(BaseModel):
    """创建会话请求"""
    title: str = "新对话"


@router.post("/create")
async def create_conversation(
    req: CreateConversationRequest,
    user_id: str = Query(default="default_user", description="用户ID"),
):
    """创建新会话，返回会话ID"""
    await ensure_user_exists(user_id, "默认用户")

    conv_id = generate_uuid()

    async with AsyncSessionLocal() as session:
        conv = Conversation(
            id=conv_id,
            user_id=user_id,
            title=req.title or "新对话",
            status="active",
        )
        session.add(conv)
        await session.commit()

    return {
        "success": True,
        "message": "创建成功",
        "data": {"id": conv_id}
    }


@router.get("/{conversation_id}/download")
async def download_report(
    conversation_id: str,
    format: str = Query(default="md", description="导出格式: md, pdf, docx"),
    preview: str = Query(default="false", description="是否预览模式: true/false"),
    user_id: str = Query(default="default_user", description="用户ID"),
):
    """
    下载或预览健康报告
    """
    from utils.report_export import markdown_to_pdf, markdown_to_docx
    from fastapi.responses import Response
    import urllib.parse

    async with AsyncSessionLocal() as session:
        try:
            reports_result = await session.execute(
                select(HealthReport).where(HealthReport.conversation_id == conversation_id)
            )
            health_reports = reports_result.scalars().all()

            if not health_reports:
                raise HTTPException(status_code=404, detail="未找到健康报告")

            md_text = health_reports[-1].content_markdown

            if format == "pdf":
                content = markdown_to_pdf(md_text)
                content_type = "application/pdf"
                filename = f"健康报告_{conversation_id[:8]}.pdf"
            elif format == "docx":
                content = markdown_to_docx(md_text)
                content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                filename = f"健康报告_{conversation_id[:8]}.docx"
            else:
                content = md_text.encode("utf-8")
                content_type = "text/markdown; charset=utf-8"
                filename = f"健康报告_{conversation_id[:8]}.md"

            encoded_filename = urllib.parse.quote(filename)
            disposition = "inline" if preview == "true" else "attachment"
            headers = {
                "Content-Disposition": f"{disposition}; filename={encoded_filename}; filename*=UTF-8''{encoded_filename}",
            }

            return Response(content=content, media_type=content_type, headers=headers)

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"下载失败: {str(e)}")
