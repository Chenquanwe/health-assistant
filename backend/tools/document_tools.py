"""
文档处理工具 — 分块、重复检测、质量评分
"""

from langchain.tools import tool
from langchain_text_splitters import RecursiveCharacterTextSplitter
# from langchain.text_splitter import RecursiveCharacterTextSplitter


@tool
def text_splitter_tool(text: str, chunk_size: int = 500, overlap: int = 100) -> str:
    """
    将长文本按语义分块。
    输入：text=待分块的文本, chunk_size=每块字符数(默认500), overlap=重叠字符数(默认100)
    输出：分块结果的摘要信息
    """
    if not text or len(text) < chunk_size:
        return f"文本较短({len(text)}字符)，无需分块"

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        separators=["\n\n", "\n", "。", "！", "？", "；", ".", "!", "?", ";", " "]
    )
    chunks = splitter.split_text(text)
    return f"分块完成：共 {len(chunks)} 块，每块约 {chunk_size} 字符，重叠 {overlap} 字符"


@tool
async def duplicate_check_tool(query_text: str) -> str:
    """
    检查知识文档是否与已有知识库重复。
    输入：待检查的文本
    输出：重复检测结果
    """
    import dashscope
    from config import get_settings
    from knowledge.vector_store import search_similar

    settings = get_settings()

    try:
        resp = dashscope.TextEmbedding.call(
            model=settings.embedding_model,
            api_key=settings.openai_api_key,
            input=query_text,
        )
        if resp.status_code != 200:
            return f"Embedding 失败: {resp.code}"

        embedding = resp.output["embeddings"][0]["embedding"]
        results = await search_similar(embedding, top_k=3)

        if results and results[0]["similarity"] > 0.95:
            return f"⚠️ 发现高度重复内容(相似度 {results[0]['similarity']:.2%})，建议检查是否已存在。"
        elif results and results[0]["similarity"] > 0.85:
            return f"⚡ 存在较相似内容(相似度 {results[0]['similarity']:.2%})，请确认是否仍需添加。"
        else:
            return f"✅ 未发现重复内容，最高相似度 {results[0]['similarity']:.2%}" if results else "✅ 知识库为空，无重复风险"

    except Exception as e:
        return f"重复检测失败: {e}"


@tool
def quality_scorer_tool(content: str) -> str:
    """
    评估知识文档的医学相关性质量。
    输入：文档文本内容
    输出：质量评分(0~1)及理由
    """
    from langchain_openai import ChatOpenAI
    from config import get_settings

    settings = get_settings()

    try:
        llm = ChatOpenAI(
            model=settings.llm_model,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            temperature=0,
        )

        prompt = f"""请评估以下文本的医学知识相关性和质量，给出0~1之间的分数。

评分标准：
- 1.0: 专业医学内容(疾病、诊断、治疗、药物)
- 0.7-0.9: 健康科普、养生保健
- 0.4-0.6: 一般健康话题、生活方式
- 0.1-0.3: 与医学关联较弱
- 0.0: 完全无关

文本内容：
{content[:2000]}

请输出格式：分数|理由
示例：0.85|内容涉及高血压的诊断标准和药物治疗方案，适合作为医学知识库补充"""

        result = llm.invoke(prompt)
        return result.content.strip()

    except Exception as e:
        return f"质量评分失败: {e}"