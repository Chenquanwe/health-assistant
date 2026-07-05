"""
流式 TTS 端点
- POST /api/tts/stream  （SSE 形式的流式 TTS）
- 原有 /api/tts 端点保持不变，新旧并存
"""
import json
import logging
logger = logging.getLogger(__name__)

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from services.voice_service import voice_service, generate_tts_segments

router = APIRouter()


class StreamTTSRequest(BaseModel):
    text: str
    voice: str = "longxiaochun"


@router.post("/api/tts/stream")
async def stream_tts_endpoint(request: StreamTTSRequest):
    """流式语音合成 SSE 端点。

    响应格式（SSE）:
        data: <base64 音频块>

        data: <base64 音频块>
        ...
    """
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="文本不能为空")

    voice = request.voice or "longxiaochun"

    async def event_generator():
        try:
            async for item in generate_tts_segments(text, voice=voice):
                if item == "[DONE]":
                    yield f"data: [DONE]\n\n".encode("utf-8")
                elif isinstance(item, dict) and item.get("audio"):
                    yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n".encode("utf-8")
        except Exception as e:
            logger.error(f"[TTS流式端点] 异常: {e}")
            import traceback
            traceback.print_exc()
            yield b"data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
