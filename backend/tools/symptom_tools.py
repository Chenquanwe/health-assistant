"""
症状相关工具
"""

from langchain.tools import tool
from knowledge.vector_store import search_similar
import dashscope
from config import get_settings

settings = get_settings()


def _embed_query(text: str) -> list:
    """文本转向量"""
    resp = dashscope.TextEmbedding.call(
        model=settings.embedding_model,
        api_key=settings.openai_api_key,
        input=text,
    )
    if resp.status_code == 200:
        return resp.output["embeddings"][0]["embedding"]
    raise Exception(f"Embedding 失败: {resp.code}")


@tool
async def symptom_search_tool(query: str) -> str:
    """
    根据症状描述检索医学知识库，返回相关的追问要点、鉴别疾病和红旗征象。
    输入：症状描述文本，如"头痛太阳穴跳着疼"
    输出：相关的医学知识内容
    """
    embedding = _embed_query(query)
    results = await search_similar(embedding, top_k=5)

    if not results:
        return "未找到相关医学知识，请基于通用医学知识进行追问。"

    output_parts = []
    for r in results:
        output_parts.append(f"[{r['metadata'].get('type', 'N/A')}] {r['content']}")

    return "\n\n".join(output_parts)


@tool
async def red_flag_check_tool(symptom: str) -> str:
    """
    检查某个症状是否存在危险信号（红旗征象），用于判断是否需要紧急就医。
    输入：症状名称
    输出：该症状的红旗征象列表
    """
    embedding = _embed_query(f"症状：{symptom} 危险信号 红旗征象")
    results = await search_similar(embedding, top_k=3)

    for r in results:
        if r['metadata'].get('type') == 'red_flags':
            return r['content']

    return f"未找到 {symptom} 的特定红旗征象记录，请按通用急危重症标准判断。"


@tool
async def disease_info_tool(symptom: str) -> str:
    """
    根据症状检索可能的疾病及其关键特征。
    输入：症状名称
    输出：相关疾病及特征描述
    """
    embedding = _embed_query(f"症状：{symptom} 可能疾病 关键特征")
    results = await search_similar(embedding, top_k=5)

    diseases = [r for r in results if r['metadata'].get('type') == 'disease']
    if not diseases:
        return f"未找到与 {symptom} 直接关联的疾病信息。"

    return "\n\n".join([d['content'] for d in diseases])