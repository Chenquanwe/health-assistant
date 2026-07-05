import os
import logging
logger = logging.getLogger(__name__)
import re
import asyncio
import tempfile
import base64
import json
import time
import aiohttp
from typing import Optional, AsyncGenerator

try:
    import dashscope
    from dashscope import MultiModalConversation
    from dashscope.audio.tts import SpeechSynthesizer
    HAS_DASHSCOPE = True
except ImportError:
    HAS_DASHSCOPE = False

try:
    from pydub import AudioSegment
    HAS_PYDUB = True
except ImportError:
    HAS_PYDUB = False


class VoiceService:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
        if HAS_DASHSCOPE and self.api_key:
            dashscope.api_key = self.api_key
            dashscope.base_http_api_url = 'https://dashscope.aliyuncs.com/api/v1'
        self._available = HAS_DASHSCOPE and self.api_key

    @property
    def available(self) -> bool:
        return self._available

    async def speech_to_text(self, audio_bytes: bytes) -> str:
        if not self._available:
            return "语音识别服务不可用，请安装 dashscope 并配置 DASHSCOPE_API_KEY"

        logger.info(f"[ASR调试] 音频字节长度: {len(audio_bytes)}")

        tmp_webm = None
        tmp_wav = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
                f.write(audio_bytes)
                tmp_webm = f.name
            input_size = os.path.getsize(tmp_webm)
            logger.info(f"[ASR调试] 原始音频: {tmp_webm}, 大小: {input_size} 字节")

            if not HAS_PYDUB:
                logger.error("[ASR调试] 警告: 未安装 pydub，无法转码，尝试直接使用原始文件")
                tmp_wav = tmp_webm
            else:
                audio = AudioSegment.from_file(tmp_webm)
                audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    audio.export(f.name, format="wav")
                    tmp_wav = f.name
                output_size = os.path.getsize(tmp_wav)
                logger.info(f"[ASR调试] 转码后: {tmp_wav}, 大小: {output_size} 字节")

            messages = [
                {
                    "role": "user",
                    "content": [
                        {"audio": tmp_wav}
                    ]
                }
            ]
            response = MultiModalConversation.call(
                model="qwen3-asr-flash",
                messages=messages,
            )

            logger.info(f"[ASR调试] 响应: {response}")
            logger.info(f"[ASR调试] status_code: {response.status_code}")

            if response.status_code == 200:
                try:
                    text = response.output.choices[0].message.content[0].get("text", "")
                    if text.strip():
                        logger.info(f"[ASR调试] 识别成功: {text}")
                        return text
                    else:
                        logger.info(f"[ASR调试] 识别结果为空")
                        return "未识别到语音内容，请重试"
                except (AttributeError, IndexError, KeyError) as e:
                    logger.error(f"[ASR调试] 解析响应失败: {e}, 响应内容: {response}")
                    return "识别失败，响应格式异常"
            else:
                code = getattr(response, 'code', '未知')
                message = getattr(response, 'message', '未知')
                logger.error(f"[ASR调试] ASR 调用失败: status_code={response.status_code}, code={code}, message={message}")
                return f"语音识别失败: {message}"
        except Exception as e:
            logger.error(f"[ASR调试] 异常: {e}")
            return f"语音识别异常: {str(e)}"
        finally:
            for path in [tmp_webm, tmp_wav]:
                if path and os.path.exists(path):
                    os.unlink(path)

    async def text_to_speech(self, text: str) -> bytes:
        if not self._available:
            return b""

        url = "https://dashscope.aliyuncs.com/api/v1/services/audio/tts/SpeechSynthesizer"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": "cosyvoice-v3-flash",
            "input": {
                "text": text,
                "voice": "longanyang",
                "format": "mp3",
                "sample_rate": 24000
            }
        }

        try:
            logger.info(f"[TTS调试] 请求文本: {text[:100]}...")
            logger.info(f"[TTS调试] 请求URL: {url}")

            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload, timeout=30) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        logger.info(f"[TTS调试] 响应: {result}")

                        audio_info = result.get("output", {}).get("audio")
                        if not audio_info:
                            logger.info(f"[TTS调试] 响应中没有 audio 字段")
                            return b""

                        if isinstance(audio_info, dict):
                            audio_url = audio_info.get("url")
                            if not audio_url:
                                logger.info(f"[TTS调试] audio 字典中没有 url 字段")
                                return b""
                            async with session.get(audio_url) as audio_resp:
                                if audio_resp.status == 200:
                                    audio_bytes = await audio_resp.read()
                                    logger.info(f"[TTS调试] 成功下载音频，长度: {len(audio_bytes)} 字节")
                                    return audio_bytes
                                else:
                                    logger.error(f"[TTS调试] 下载音频失败: {audio_resp.status}")
                                    return b""
                        elif isinstance(audio_info, str):
                            audio_bytes = base64.b64decode(audio_info)
                            logger.info(f"[TTS调试] 成功解码 base64 音频，长度: {len(audio_bytes)} 字节")
                            return audio_bytes
                        else:
                            logger.info(f"[TTS调试] 未知的 audio 类型: {type(audio_info)}")
                            return b""
                    else:
                        error_text = await resp.text()
                        logger.error(f"[TTS调试] HTTP 错误 {resp.status}: {error_text}")
                        return b""
        except Exception as e:
            logger.error(f"[TTS调试] 请求异常: {e}")
            import traceback
            traceback.print_exc()
            return b""

    async def stream_tts(
        self,
        text: str,
        voice: str = "longxiaochun",
    ) -> AsyncGenerator[str, None]:
        """
        流式 TTS 生成器：调用 DashScope TTS (stream=true)，
        按 SSE 逐块 yield base64 编码的音频数据。

        DashScope 流式 TTS 每个 SSE 事件的 data 字段是一段 JSON，结构形如：
            {"output": {"audio": {"data": "<base64>", "duration": 0.2, "status": "playing"}}, "usage": {...}}
        结束事件为 data: [DONE]。
        """
        if not self._available:
            logger.info("[TTS流式] 语音合成服务不可用")
            return

        url = "https://dashscope.aliyuncs.com/api/v1/services/audio/tts/SpeechSynthesizer"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }

        payload = {
            "model": "cosyvoice-v3-flash",
            "input": {
                "text": text,
                "voice": voice,
                "format": "mp3",
                "sample_rate": 24000,
            },
            "parameters": {
                "stream": True,
            },
        }

        logger.info(f"[TTS流式] 请求文本: {text[:100]}..., 音色: {voice}")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, headers=headers, json=payload, timeout=120
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(f"[TTS流式] HTTP 错误 {resp.status}: {error_text}")
                        return

                    # DashScope SSE 使用 utf-8，逐行读取
                    async for raw_line in resp.content:
                        try:
                            line = raw_line.decode("utf-8").strip()
                        except UnicodeDecodeError:
                            continue
                        if not line:
                            # SSE 中空行仅为事件分隔，跳过
                            continue

                        # DashScope 可能同时出现 "data:" 与 "event:" 行，仅处理 data:
                        if not line.startswith("data:"):
                            continue

                        data_str = line[len("data:"):].strip()
                        if not data_str:
                            continue
                        if data_str == "[DONE]":
                            logger.info("[TTS流式] 收到 [DONE]，流结束")
                            break

                        try:
                            data = json.loads(data_str)
                        except json.JSONDecodeError as e:
                            logger.error(f"[TTS流式] JSON解析失败: {data_str[:100]}..., err={e}")
                            continue

                        audio_info = data.get("output", {}).get("audio")
                        if not audio_info:
                            continue

                        base64_chunk = None
                        if isinstance(audio_info, str):
                            # 某些版本直接将 base64 字符串放在 audio 字段
                            base64_chunk = audio_info
                        elif isinstance(audio_info, dict):
                            # 主流格式：audio.data 或 audio.audio 存 base64
                            candidate = audio_info.get("data") or audio_info.get("audio")
                            if isinstance(candidate, str):
                                base64_chunk = candidate

                        if base64_chunk:
                            yield base64_chunk
        except Exception as e:
            logger.error(f"[TTS流式] 请求异常: {e}")
            import traceback
            traceback.print_exc()


def split_text_for_tts(text: str, max_len: int = 60):
    """按中英文标点分句，长句在字边界截断。"""
    if not text:
        return []

    # 先按强标点切分
    parts = re.split(r"([。！？!?\.\!?])", text)
    sentences = []
    i = 0
    while i < len(parts):
        seg = parts[i]
        if i + 1 < len(parts) and re.match(r"[。！？!?\.\!?]", parts[i + 1]):
            seg = seg + parts[i + 1]
            i += 2
        else:
            i += 1
        seg = seg.strip()
        if not seg:
            continue
        # 长句再按弱标点/长度切分
        if len(seg) <= max_len:
            sentences.append(seg)
        else:
            sub_parts = re.split(r"([,，;；:：])", seg)
            buf = ""
            j = 0
            while j < len(sub_parts):
                piece = sub_parts[j]
                if j + 1 < len(sub_parts) and re.match(r"[,，;；:：]", sub_parts[j + 1]):
                    piece = piece + sub_parts[j + 1]
                    j += 2
                else:
                    j += 1
                if len(buf) + len(piece) <= max_len:
                    buf += piece
                else:
                    if buf:
                        sentences.append(buf.strip())
                    # 若 piece 自身仍超长，按字硬切
                    while len(piece) > max_len:
                        sentences.append(piece[:max_len])
                        piece = piece[max_len:]
                    buf = piece
            if buf:
                sentences.append(buf.strip())
    return [s for s in sentences if s]


async def generate_tts_segments(
    text: str,
    voice: str = "longxiaochun",
) -> AsyncGenerator:
    """
    分句合成生成器：将文本按句切分后并发调用 text_to_speech，
    按原始 index 顺序依次 yield 每个句子的 JSON 片段。
    """
    logger.info(f"[generate_tts_segments] 原始文本: {text[:50]}...")
    sentences = split_text_for_tts(text)
    logger.info(f"[generate_tts_segments] 分句数量: {len(sentences)}")

    if not sentences:
        yield "[DONE]"
        return

    logger.info("[generate_tts_segments] 开始并发调用 TTS...")
    semaphore = asyncio.Semaphore(5)

    async def _synthesize_one(idx: int, sent: str):
        async with semaphore:
            try:
                audio_bytes = await voice_service.text_to_speech(sent)
                audio_b64 = base64.b64encode(audio_bytes).decode("utf-8") if audio_bytes else ""
                if audio_bytes:
                    logger.info(f"[generate_tts_segments] 句子 {idx} 生成成功: {len(audio_bytes)} 字节")
                else:
                    logger.error(f"[generate_tts_segments] 句子 {idx} 生成失败: 无")
                return {
                    "index": idx,
                    "audio": audio_b64,
                    "text": sent,
                }
            except Exception as e:
                logger.error(f"[generate_tts_segments] 句子 {idx} 生成失败: {e}")
                return {
                    "index": idx,
                    "audio": "",
                    "text": sent,
                }

    tasks = [_synthesize_one(i, s) for i, s in enumerate(sentences)]
    results = await asyncio.gather(*tasks)

    for item in results:
        yield item

    logger.info("[generate_tts_segments] 所有句子处理完毕")
    yield "[DONE]"


voice_service = VoiceService()
