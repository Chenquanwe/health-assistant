"""
多轮问诊Agent (ReAct模式)
强化错误处理，抛出明确异常
"""

import asyncio
import logging
logger = logging.getLogger(__name__)
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langgraph.prebuilt import create_react_agent
from config import get_settings

settings = get_settings()
from middleware.health_callback import HealthAgentCallback

callback = HealthAgentCallback(verbose=False)
llm = ChatOpenAI(
    model=settings.llm_model,
    api_key=settings.openai_api_key,
    base_url=settings.openai_base_url,
    temperature=0.3,
    callbacks=[callback],
)

_cached_streaming_agent = None
_cached_fallback_agent = None


class ConsultationFailedError(Exception):
    """问诊失败异常"""
    pass


CONSULTATION_SYSTEM_PROMPT = """你是一位经验丰富的全科医生，正在通过网络问诊采集患者信息。

# 你的职责
1. 多轮提问，系统性采集患者信息
2. 每轮只问一个问题，像真正的医生一样自然对话
3. 根据患者回答动态调整后续提问方向
4. 当信息足够时，总结问诊结果

# 问诊框架 (SOCRATES + 基础信息)
你必须逐项采集以下信息：

【必须采集】：
- Site（部位）：哪里不舒服？
- Onset（起病时间）：什么时候开始的？
- Character（性质）：什么样的不舒服？
- Severity（严重程度）：1-10分打几分？
- Allergy（过敏史）：有没有药物或食物过敏？

【建议采集】：
- Associated（伴随症状）：有没有其他不舒服？
- Past_history（既往史）：以前有过类似情况吗？
- Medication（用药史）：最近在吃什么药？

# 追问节奏
- 每次只问一个问题
- 用 symptom_search_tool 检索相关追问要点
- 用 knowledge_search 工具检索知识库中的相关医学文档，作为回答参考
- 用 completeness_evaluator_tool 检查完整度
- 完整度≥80%：输出【问诊完成】
- 用 red_flag_check_tool 检查危险信号
- 当用户咨询具体的医学知识、疾病原理、饮食建议、药物说明等知识性问题时，必须优先使用 knowledge_search 工具检索知识库
- 如果检索到相关文档，必须在回复开头引用文档中的关键内容（如具体的饮食建议、用药指导），然后再询问是否需要进一步了解
- 绝对不要在检索到相关知识后仍然只追问症状而忽略用户的实际问题

# 对话风格
- 温暖、专业、简洁
- 每次回复：先简短共情，再问一个问题
- 当用户询问知识性问题时，优先作为健康顾问给予知识性解答，而不是机械追问症状

# 结束规则（极其重要）
- 当你判断信息采集足够时，立即输出【问诊完成】
- 然后**必须**使用 Markdown 表格输出问诊记录，严格按照下面示例格式：
- **必须包含表头分隔行 `|------|------|`，否则表格无法正常渲染**
【问诊完成】

问诊记录

| 维度 | 内容 |
|------|------|
| Site（部位）| [具体部位] |
| Onset（起病时间）| [具体时间] |
| Character（性质）| [具体性质] |
| Severity（严重程度）| [具体评分] |
| Allergy（过敏史）| [具体过敏情况] |
| Associated（伴随症状）| [具体症状] |
| Past_history（既往史）| [具体病史] |
| Medication（用药史）| [具体用药] |

text
- 绝对不要在【问诊完成】之后问任何问题
- 绝对不要问"需要我帮您做什么吗"、"需要进一步帮助吗"之类的话
- 【问诊完成】之后不要再有任何反问句
"""


def _build_consultation_agent_impl():
    """实际构建问诊Agent（ReAct模式）——仅在缓存为空时调用一次"""

    llm = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        temperature=0.3,
    )

    from tools.symptom_tools import symptom_search_tool, red_flag_check_tool
    from tools.evaluation_tools import completeness_evaluator_tool
    from tools.knowledge_tools import knowledge_search_tool

    tools = [
        symptom_search_tool,
        red_flag_check_tool,
        completeness_evaluator_tool,
        knowledge_search_tool,
    ]

    prompt = ChatPromptTemplate.from_messages([
        ("system", CONSULTATION_SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="messages"),
    ])

    agent = create_react_agent(
        model=llm,
        tools=tools,
        prompt=prompt,
    )

    return agent


def build_consultation_agent():
    """构建问诊Agent（ReAct模式）——带缓存，避免每次请求重建"""
    global _cached_fallback_agent
    if _cached_fallback_agent is not None:
        return _cached_fallback_agent
    _cached_fallback_agent = _build_consultation_agent_impl()
    return _cached_fallback_agent


def _get_streaming_agent():
    """获取流式Agent——带缓存，仅首次构建"""
    global _cached_streaming_agent
    if _cached_streaming_agent is not None:
        return _cached_streaming_agent

    streaming_llm = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        temperature=0.3,
        streaming=True,
    )

    from tools.symptom_tools import symptom_search_tool, red_flag_check_tool
    from tools.evaluation_tools import completeness_evaluator_tool
    from tools.knowledge_tools import knowledge_search_tool

    tools = [
        symptom_search_tool,
        red_flag_check_tool,
        completeness_evaluator_tool,
        knowledge_search_tool,
    ]

    _cached_streaming_agent = create_react_agent(
        model=streaming_llm,
        tools=tools,
        prompt=CONSULTATION_SYSTEM_PROMPT,
    )
    return _cached_streaming_agent


async def stream_consultation(messages: list):
    """流式问诊 - 逐 token 返回 AI 回复（带超时保护）"""

    agent = _get_streaming_agent()

    full_response = ""
    has_tokens = False
    chunk_count = 0

    logger.info(f"[stream_consultation] 输入消息数: {len(messages)}")
    for i, m in enumerate(messages):
        role = m.get('role', 'unknown') if isinstance(m, dict) else getattr(m, 'type', 'unknown')
        content_preview = str(m.get('content', '') if isinstance(m, dict) else getattr(m, 'content', ''))[:50]
        logger.info(f"[stream_consultation]   msg[{i}]: {role} -> '{content_preview}'")

    try:
        stream_agen = agent.astream(
            {"messages": messages}, stream_mode="messages"
        )
        stream_iter = stream_agen.__aiter__()

        yield "[progress]🤔 正在分析您的症状…"

        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(stream_iter.__anext__(), timeout=30)
                except asyncio.TimeoutError:
                    logger.info(f"[stream] 流式等待超时（已收 {chunk_count} 个 chunk）")
                    break
                except StopAsyncIteration:
                    logger.info(f"[stream] 流式正常结束")
                    break

                chunk_count += 1
                if not isinstance(chunk, tuple) or len(chunk) < 2:
                    continue

                msg = chunk[0]
                metadata = chunk[1]

                node_name = metadata.get("langgraph_node", "") if isinstance(metadata, dict) else ""

                KNOWN_TOOL_NODES = {"tools"}
                if node_name in KNOWN_TOOL_NODES:
                    if chunk_count <= 5:
                        logger.info(f"[stream] 跳过工具节点: {node_name}")
                    # 进入工具节点时，发送进度提示（不累积到 full_response）
                    yield "[progress]🔍 正在检索医学知识…"
                    yield "[thinking]{\"tool\": \"检索工具\", \"status\": \"开始检索相似症状\"}"
                    continue

                content = ""
                if hasattr(msg, 'content'):
                    content = msg.content or ""
                elif isinstance(msg, dict):
                    content = msg.get('content', '') or ""

                if isinstance(content, list):
                    content = "".join(str(c) for c in content if c)

                has_tool_calls = False
                tool_names = []
                if hasattr(msg, 'tool_calls'):
                    tc = msg.tool_calls or []
                    has_tool_calls = bool(tc)
                    tool_names = [getattr(t, 'name', '') or (t.get('name', '') if isinstance(t, dict) else '') for t in tc]
                elif isinstance(msg, dict):
                    tc = msg.get('tool_calls', []) or []
                    has_tool_calls = bool(tc)
                    tool_names = [t.get('name', '') if isinstance(t, dict) else '' for t in tc]

                if chunk_count <= 5:
                    msg_type = type(msg).__name__
                    tool_str = f", tool_calls={has_tool_calls}"
                    logger.info(f"[stream] chunk#{chunk_count}: type={msg_type}, "
                          f"content_len={len(str(content)) if content else 0}{tool_str}, "
                          f"node={node_name}")

                # 进入评估工具时，发送专门的进度提示（不累积到 full_response）
                if has_tool_calls:
                    joined = " ".join(tool_names)
                    if "completeness" in joined or "evaluator" in joined:
                        yield "[progress]📊 正在评估信息完整度…"
                        yield "[thinking]{\"tool\": \"信息完整度评估\", \"progress\": \"正在计算完整度百分比\"}"
                    elif "red_flag" in joined:
                        yield "[progress]🔍 正在检索医学知识…"
                        yield "[thinking]{\"tool\": \"危险信号检查\", \"status\": \"正在评估严重程度\"}"
                    elif "symptom" in joined:
                        yield "[progress]🔍 正在检索医学知识…"
                        yield "[thinking]{\"tool\": \"症状检索\", \"input\": \"根据对话内容检索\", \"output\": \"正在生成检索结果...\"}"
                    else:
                        yield "[progress]🔍 正在检索医学知识…"
                        yield "[thinking]{\"tool\": \"检索工具\", \"status\": \"调用工具中\"}"
                    continue
                if not content or not isinstance(content, str) or len(content) == 0:
                    continue

                full_response += content
                has_tokens = True
                yield content
        finally:
            try:
                await stream_agen.aclose()
            except Exception:
                pass

    except Exception as e:
        logger.error(f"[stream_consultation] 流式错误: {e}")
        import traceback
        traceback.print_exc()
        raise ConsultationFailedError(f"流式生成失败: {str(e)}")

    logger.info(f"[stream] 总共 {chunk_count} 个 chunk，收集到 {len(full_response)} 字文本")

    if not has_tokens or not full_response:
        logger.info("[stream_consultation] 流式未产生 token，回退到非流式模式")
        try:
            fallback_agent = build_consultation_agent()
            fallback_result = await fallback_agent.ainvoke({"messages": messages})
            ai_msgs = [m for m in fallback_result["messages"] if hasattr(m, 'type') and m.type == "ai"]
            if ai_msgs:
                full_response = ai_msgs[-1].content
                yield full_response
                logger.info(f"[stream_consultation] 回退完成，共 {len(full_response)} 字")
                return
        except Exception as fallback_e:
            logger.error(f"[stream_consultation] 回退也失败: {fallback_e}")
            import traceback
            traceback.print_exc()
            raise ConsultationFailedError(f"回退模式也失败: {str(fallback_e)}")

        raise ConsultationFailedError("流式和回退模式都未产生有效回复")

    logger.info(f"[stream_consultation] 流式完成，共 {len(full_response)} 字")
