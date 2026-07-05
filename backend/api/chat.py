"""
WebSocket 聊天端点 - 重构版
使用 LangGraph Checkpointer 管理状态，废弃全局 sessions 字典
"""

import json
import logging
logger = logging.getLogger(__name__)
import asyncio
from typing import Optional, Dict
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from database import AsyncSessionLocal
from models.conversation import Conversation, Message
from models.report import HealthReport
from models.base import generate_uuid
from datetime import datetime
from utils.user_utils import ensure_user_exists

from agents.consultation_agent import ConsultationFailedError
from services.voice_service import voice_service

router = APIRouter(prefix="/api", tags=["聊天"])

# 连接管理：以 ws_id 为 key，记录连接实例和关联的 conversation_id
connections = {}
processed_request_ids = set()

HEARTBEAT_INTERVAL = 30
HEARTBEAT_TIMEOUT = 60


def _extract_ai_response(messages):
    """从消息列表中提取最后一条 AI 回复"""
    for m in reversed(messages):
        if isinstance(m, dict) and m.get("role") == "assistant":
            return m.get("content", "")
        if hasattr(m, 'role') and m.role == "assistant":
            return m.content if hasattr(m, 'content') else ""
    return ""


async def _create_conversation(user_id: str, chief_complaint: str, title: str = None) -> str:
    """创建新会话并返回 ID"""
    conv_id = generate_uuid()
    if title:
        conv_title = title
    else:
        conv_title = f"{chief_complaint[:20]}..." if len(chief_complaint) > 20 else chief_complaint

    async with AsyncSessionLocal() as session:
        conv = Conversation(
            id=conv_id,
            user_id=user_id,
            title=conv_title or "未命名问诊",
            status="active",
        )
        session.add(conv)
        await session.commit()
    return conv_id


async def _save_message(
    conversation_id: str,
    role: str,
    content: str,
    message_type: str = "text",
):
    """保存一条消息"""
    async with AsyncSessionLocal() as session:
        msg = Message(
            id=generate_uuid(),
            conversation_id=conversation_id,
            role=role,
            content=content,
            message_type=message_type,
        )
        session.add(msg)
        await session.commit()


async def _save_health_report(
    conversation_id: str,
    user_id: str,
    content_markdown: str,
    risk_level: str = "low",
):
    """保存健康报告"""
    async with AsyncSessionLocal() as session:
        report = HealthReport(
            id=generate_uuid(),
            conversation_id=conversation_id,
            user_id=user_id,
            content_markdown=content_markdown,
            risk_level=risk_level,
        )
        session.add(report)
        await session.commit()


async def _extract_risk_level(report_text: str) -> str:
    """从报告文本中提取风险等级"""
    if "风险等级" in report_text or "风险" in report_text:
        if "高" in report_text:
            return "high"
        if "中" in report_text:
            return "medium"
    return "low"


async def _update_conversation_status(conversation_id: str, status: str = "active"):
    """更新会话状态"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        conv = result.scalar_one_or_none()
        if conv:
            conv.status = status
            conv.updated_at = datetime.now()
            await session.commit()


@router.websocket("/ws/chat")
async def chat_endpoint(websocket: WebSocket):
    await websocket.accept()
    ws_id = str(id(websocket))
    user_id = "default_user"

    await ensure_user_exists(user_id, "默认用户")

    connections[ws_id] = {
        "websocket": websocket,
        "conversation_id": None,
        "last_heartbeat": datetime.now(),
    }

    try:
        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=HEARTBEAT_TIMEOUT
                )

                msg = json.loads(data)

                request_id = msg.get("request_id")
                if request_id and request_id in processed_request_ids:
                    logger.info(f"🔄 [幂等检查] 请求已处理: {request_id}")
                    continue
                if request_id:
                    processed_request_ids.add(request_id)
                    asyncio.create_task(_cleanup_request_id(request_id))

                if msg.get("type") == "heartbeat":
                    connections[ws_id]["last_heartbeat"] = datetime.now()
                    await websocket.send_text(json.dumps({"type": "heartbeat_ack"}, ensure_ascii=False))
                    continue

                conversation_id = msg.get("conversation_id")
                if not conversation_id:
                    logger.error(f"❌ [错误] 缺少 conversation_id")
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": "缺少会话ID",
                        "request_id": request_id
                    }, ensure_ascii=False))
                    continue

                connections[ws_id]["conversation_id"] = conversation_id

                msg_type = msg.get("type", "")

                if msg_type == "message":
                    user_input = msg.get("message", "")
                    title = msg.get("title", None)
                    if not user_input.strip():
                        continue
                    await _handle_chat_message(
                        websocket, user_id, conversation_id, user_input, request_id, title
                    )
                elif msg_type == "generate_report":
                    await _handle_generate_report(
                        websocket, user_id, conversation_id, request_id
                    )
                elif msg_type == "voice_input":
                    audio_base64 = msg.get("audio", "")
                    if not audio_base64:
                        await websocket.send_text(json.dumps({
                            "type": "voice_input_result",
                            "text": "",
                            "error": "音频数据为空",
                            "conversation_id": conversation_id,
                            "request_id": request_id
                        }, ensure_ascii=False))
                        continue

                    import base64
                    try:
                        audio_bytes = base64.b64decode(audio_base64)
                    except Exception as e:
                        await websocket.send_text(json.dumps({
                            "type": "voice_input_result",
                            "text": "",
                            "error": f"音频解码失败: {str(e)}",
                            "conversation_id": conversation_id,
                            "request_id": request_id
                        }, ensure_ascii=False))
                        continue

                    text = await voice_service.speech_to_text(audio_bytes)
                    await websocket.send_text(json.dumps({
                        "type": "voice_input_result",
                        "text": text,
                        "conversation_id": conversation_id,
                        "request_id": request_id
                    }, ensure_ascii=False))

                    if text and not text.startswith("语音识别"):
                        await _handle_chat_message(
                            websocket, user_id, conversation_id, text, request_id
                        )

            except asyncio.TimeoutError:
                logger.info(f"⏰ 心跳超时: ws_id={ws_id}")
                break

    except WebSocketDisconnect:
        logger.info(f"🔌 WebSocket 断开: ws_id={ws_id}")

    except Exception as e:
        logger.error(f"❌ 错误: {e}")
        try:
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": str(e),
                "conversation_id": conversation_id if 'conversation_id' in locals() else None,
                "request_id": request_id if 'request_id' in locals() else None
            }, ensure_ascii=False))
        except:
            pass

    finally:
        if ws_id in connections:
            del connections[ws_id]


async def _cleanup_request_id(request_id: str):
    """清理已处理的请求ID（10秒后）"""
    await asyncio.sleep(10)
    if request_id in processed_request_ids:
        processed_request_ids.remove(request_id)


async def _handle_chat_message(
    websocket: WebSocket,
    user_id: str,
    conversation_id: str,
    user_input: str,
    request_id: str,
    title: str = None
):
    """处理普通聊天消息 - 直接调用 consultation_agent 流式回复"""
    logger.info(f"💬 [聊天] conversation_id={conversation_id}, user_input={user_input[:50]}...")
    logger.info(f"[调试] 收到消息类型: message, 内容: {user_input[:50]}")
    if title:
        logger.info(f"[调试] 自定义标题: {title}")

    async with AsyncSessionLocal() as db_session:
        result = await db_session.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        existing_conv = result.scalar_one_or_none()

        if not existing_conv:
            conversation_id = await _create_conversation(user_id, user_input, title)
            logger.info(f"📝 创建新会话: {conversation_id}")

    await _save_message(conversation_id, "user", user_input)
    logger.info(f"[调试] 用户消息已保存")

    async with AsyncSessionLocal() as db_session:
        result = await db_session.execute(
            select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at)
        )
        messages = result.scalars().all()
        logger.info(f"[调试] 加载了 {len(messages)} 条历史消息")

    history = []
    for msg in messages:
        history.append({"role": msg.role, "content": msg.content})

    try:
        from agents.consultation_agent import stream_consultation

        logger.info(f"[调试] 开始流式生成...")
        full_response = ""
        progress_sent = False
        async for token in stream_consultation(history):
            # 识别进度提示 token：不累积到 full_response，也不发送 stream_token
            if isinstance(token, str) and token.startswith("[progress]"):
                progress_content = token[len("[progress]"):]
                await websocket.send_text(json.dumps({
                    "type": "progress",
                    "content": progress_content,
                    "conversation_id": conversation_id,
                    "request_id": request_id
                }, ensure_ascii=False))
                logger.info(f"[调试] 发送进度提示: {progress_content}")
                continue

            # 识别思考详情 token：不累积到 full_response，也不发送 stream_token
            if isinstance(token, str) and token.startswith("[thinking]"):
                thinking_data = token[len("[thinking]"):]
                await websocket.send_text(json.dumps({
                    "type": "thinking",
                    "content": thinking_data,
                    "conversation_id": conversation_id,
                    "request_id": request_id
                }, ensure_ascii=False))
                logger.info(f"[调试] 发送思考详情: {thinking_data}")
                continue

            full_response += token
            await websocket.send_text(json.dumps({
                "type": "stream_token",
                "content": token,
                "conversation_id": conversation_id,
                "request_id": request_id
            }, ensure_ascii=False))

            if "【问诊完成】" in full_response and not progress_sent:
                await websocket.send_text(json.dumps({
                    "type": "progress",
                    "content": "📝 正在生成问诊记录...",
                    "message": "正在生成问诊记录...",
                    "conversation_id": conversation_id,
                    "request_id": request_id
                }, ensure_ascii=False))
                progress_sent = True
                logger.info(f"[调试] 发送进度提示: 正在生成问诊记录")

        await websocket.send_text(json.dumps({
            "type": "stream_end",
            "content": full_response,
            "has_stream_tokens": True,
            "conversation_id": conversation_id,
            "request_id": request_id
        }, ensure_ascii=False))

        await _save_message(conversation_id, "assistant", full_response)

    except ConsultationFailedError as e:
        logger.error(f"❌ 问诊失败: {e}")
        logger.error(f"[异常] ConsultationFailedError: {e}")
        await websocket.send_text(json.dumps({
            "type": "error",
            "message": "AI 服务暂时不可用，请稍后重试",
            "conversation_id": conversation_id,
            "request_id": request_id
        }, ensure_ascii=False))
        await websocket.send_text(json.dumps({
            "type": "stream_end",
            "content": "",
            "has_stream_tokens": False,
            "conversation_id": conversation_id,
            "request_id": request_id
        }, ensure_ascii=False))
    except Exception as e:
        logger.error(f"❌ 聊天异常: {e}")
        import traceback
        traceback.print_exc()
        await websocket.send_text(json.dumps({
            "type": "error",
            "message": str(e),
            "conversation_id": conversation_id,
            "request_id": request_id
        }, ensure_ascii=False))
        await websocket.send_text(json.dumps({
            "type": "stream_end",
            "content": "",
            "has_stream_tokens": False,
            "conversation_id": conversation_id,
            "request_id": request_id
        }, ensure_ascii=False))


async def _handle_generate_report(
    websocket: WebSocket,
    user_id: str,
    conversation_id: str,
    request_id: str
):
    """处理生成报告请求 - 加载历史消息，直接调用报告生成Agent"""
    from agents.report_generation_agent import generate_report

    logger.info(f"📄 [生成报告] conversation_id={conversation_id}")

    async with AsyncSessionLocal() as db_session:
        result = await db_session.execute(
            select(Message).where(
                Message.conversation_id == conversation_id,
                Message.message_type != "report"
            ).order_by(Message.created_at)
        )
        messages = result.scalars().all()

    if not messages:
        await websocket.send_text(json.dumps({
            "type": "error",
            "message": "没有历史消息，无法生成报告",
            "conversation_id": conversation_id,
            "request_id": request_id
        }, ensure_ascii=False))
        return

    history = []
    chief_complaint = ""
    consultation_record = ""
    for msg in messages:
        history.append({"role": msg.role, "content": msg.content})
        if msg.role == "user" and not chief_complaint:
            chief_complaint = msg.content[:100]
        role = "用户" if msg.role == "user" else "AI"
        consultation_record += f"{role}: {msg.content}\n"

    logger.info(f"[调试] chief_complaint: '{chief_complaint}'")
    logger.info(f"[调试] consultation_record 长度: {len(consultation_record)}")

    await websocket.send_text(json.dumps({
        "type": "progress",
        "content": "📊 正在生成健康报告...",
        "message": "正在生成健康报告...",
        "conversation_id": conversation_id,
        "request_id": request_id
    }, ensure_ascii=False))

    try:
        final_report = await generate_report(
            chief_complaint=chief_complaint,
            triage_result="",
            consultation_record=consultation_record,
            report_analysis="",
            rag_reference="",
            diagnosis="",
            risk_warning="",
        )

        logger.info(f"[调试] final_report 长度: {len(final_report) if final_report else 0}")
        logger.info(f"[调试] final_report 内容: {final_report[:100] if final_report else '空'}")

        if final_report:
            risk_level = await _extract_risk_level(final_report)
            await _save_health_report(conversation_id, user_id, final_report, risk_level)
            await _update_conversation_status(conversation_id, "completed")

            await websocket.send_text(json.dumps({
                "type": "report",
                "report": final_report,
                "conversation_id": conversation_id,
                "request_id": request_id
            }, ensure_ascii=False))
        else:
            await websocket.send_text(json.dumps({
                "type": "error",
                "message": "报告生成失败，请重试",
                "conversation_id": conversation_id,
                "request_id": request_id
            }, ensure_ascii=False))

        await websocket.send_text(json.dumps({
            "type": "stream_end",
            "content": "",
            "has_stream_tokens": False,
            "conversation_id": conversation_id,
            "request_id": request_id
        }, ensure_ascii=False))

    except Exception as e:
        logger.error(f"❌ [生成报告异常] conversation_id={conversation_id}, error={e}")
        import traceback
        traceback.print_exc()
        await websocket.send_text(json.dumps({
            "type": "error",
            "message": f"生成报告失败: {str(e)}",
            "conversation_id": conversation_id,
            "request_id": request_id
        }, ensure_ascii=False))


async def _handle_workflow_event(
    websocket: WebSocket,
    conversation_id: str,
    request_id: str,
    node_name: str,
    state_update: dict
):
    """处理工作流中间事件"""
    logger.info(f"📨 [工作流事件] node={node_name}")

    node_progress = {
        "triage": "🏥 正在分诊...",
        "consultation": "💬 正在问诊...",
        "report_analysis": "📊 正在分析报告...",
        "knowledge_retrieval": "📚 正在检索医学知识...",
        "diagnosis": "🩺 正在生成诊断建议...",
        "risk_warning": "⚠️ 正在评估风险...",
        "report_generation": "📝 正在生成报告...",
    }

    await websocket.send_text(json.dumps({
        "type": "progress",
        "content": node_progress.get(node_name, f"⏳ 正在处理: {node_name}"),
        "message": node_progress.get(node_name, f"正在处理: {node_name}"),
        "conversation_id": conversation_id,
        "request_id": request_id
    }, ensure_ascii=False))


from pydantic import BaseModel
from fastapi import HTTPException
import base64


class TTSRequest(BaseModel):
    text: str


@router.post("/tts")
async def tts_endpoint(request: TTSRequest):
    """语音合成接口，返回 base64 编码的音频"""
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="文本不能为空")
    audio_bytes = await voice_service.text_to_speech(request.text)
    if not audio_bytes:
        raise HTTPException(status_code=500, detail="TTS 合成失败")
    return {"audio": base64.b64encode(audio_bytes).decode("utf-8")}



