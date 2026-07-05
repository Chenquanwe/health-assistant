"""
知识库检索工具 — 基于向量相似检索，从 medical_knowledge_vectors 中召回相关医学文档
"""

from langchain.tools import tool
import logging
logger = logging.getLogger(__name__)
import dashscope
from config import get_settings
from knowledge.vector_store import search_similar

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
async def knowledge_search_tool(query: str, top_k: int = 5) -> str:
    """
    从知识库中检索与 query 相关的医学文档内容，作为回答参考。
    输入：检索关键词或自然语言问题，如"高血压患者饮食注意事项"
    输出：最相关的若干条知识文档片段及其元信息
    """
    source_filter = ["user_upload", "种子数据"]
    logger.info(f"[Knowledge Search] 查询文本: {query}")
    logger.info(f"[Knowledge Search] 检索参数: top_k={top_k}, source_filter={source_filter}")

    try:
        embedding = _embed_query(query)
        results = await search_similar(
            embedding,
            top_k=top_k,
            source_filter=source_filter,
        )
    except Exception as e:
        logger.error(f"[Knowledge Search] 检索异常: {e}")
        return f"知识库检索异常: {e}"

    logger.info(f"[Knowledge Search] 原始结果数量: {len(results) if results else 0}")

    if not results:
        logger.info("[Knowledge Search] 未检索到相关文档")
        return "知识库中未检索到相关文档，请基于通用医学知识回答。"

    output_parts = []
    for r in results:
        meta = r.get("metadata") or {}
        source = r.get("source") or meta.get("source") or "用户上传"
        title = meta.get("title") or meta.get("document_title") or ""
        score = r.get("similarity")
        score_str = f"{score:.3f}" if isinstance(score, float) else str(score)
        content_preview = (r.get("content") or "")[:80].replace("\n", " ")
        logger.info(
            f"[Knowledge Search] 命中: similarity={score_str}, "
            f"source={source}, preview={content_preview}"
        )
        header = f"[{source}]"
        if title:
            header += f" {title}"
        header += f" (相似度={score_str})"
        output_parts.append(f"{header}\n{r['content']}")

    return "\n\n".join(output_parts)
