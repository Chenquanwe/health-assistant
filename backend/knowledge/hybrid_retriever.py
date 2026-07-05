"""
混合检索服务 - 完整版（保留，等添加大量文献后使用）
功能：全文检索 + 向量检索 + RRF融合 + 查询重写 + LLM重排序
"""
import json
import logging
logger = logging.getLogger(__name__)
from typing import List, Dict, Optional, Tuple
from sqlalchemy import text
from database import async_engine, AsyncSessionLocal

# 尝试导入 dashscope，如果失败则标记为不可用
try:
    import dashscope
    DASHSCOPE_AVAILABLE = True
except ImportError:
    dashscope = None
    DASHSCOPE_AVAILABLE = False

from langchain_openai import ChatOpenAI
from config import get_settings

settings = get_settings()

VECTOR_TABLE = "medical_knowledge_vectors"
FULLTEXT_TABLE = "medical_knowledge_fulltext"


def embed_text(text: str) -> List[float]:
    """生成文本向量嵌入"""
    if not DASHSCOPE_AVAILABLE:
        raise Exception("dashscope 模块未安装，请先安装：pip install dashscope")
    
    resp = dashscope.TextEmbedding.call(
        model=settings.embedding_model,
        api_key=settings.openai_api_key,
        input=text,
    )
    if resp.status_code == 200:
        return resp.output["embeddings"][0]["embedding"]
    else:
        raise Exception(f"Embedding 失败: {resp.code} - {resp.message}")


async def create_fulltext_table():
    """创建全文索引表（如果不存在）"""
    async with async_engine.connect() as conn:
        await conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS {FULLTEXT_TABLE} (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                content TEXT NOT NULL,
                content_tsv tsvector,
                source VARCHAR(50) DEFAULT 'official',
                document_id VARCHAR(255),
                metadata JSONB,
                created_at TIMESTAMP DEFAULT now()
            )
        """))
        await conn.execute(text(f"""
            CREATE INDEX IF NOT EXISTS idx_fulltext_content
            ON {FULLTEXT_TABLE}
            USING gin (content_tsv)
        """))
        await conn.commit()
    logger.info(f"✅ 全文索引表 {FULLTEXT_TABLE} 就绪")


async def insert_fulltext(
    content: str,
    source: str = "official",
    document_id: Optional[str] = None,
    metadata: Optional[dict] = None
):
    """插入全文索引记录"""
    metadata_str = json.dumps(metadata) if metadata else None

    async with async_engine.connect() as conn:
        await conn.execute(
            text(f"""
                INSERT INTO {FULLTEXT_TABLE} (content, content_tsv, source, document_id, metadata)
                VALUES (
                    :content,
                    to_tsvector('chinese', :content),
                    :source,
                    :document_id,
                    CAST(:metadata AS jsonb)
                )
            """),
            {
                "content": content,
                "source": source,
                "document_id": document_id,
                "metadata": metadata_str,
            }
        )
        await conn.commit()


async def fulltext_search(
    query: str,
    top_k: int = 10
) -> List[dict]:
    """全文检索 - 使用 PostgreSQL tsvector"""
    async with async_engine.connect() as conn:
        result = await conn.execute(
            text(f"""
                SELECT id, content, source, metadata,
                       ts_rank(content_tsv, to_tsquery('chinese', :query)) AS rank
                FROM {FULLTEXT_TABLE}
                WHERE content_tsv @@ to_tsquery('chinese', :query)
                ORDER BY rank DESC
                LIMIT :top_k
            """),
            {"query": query, "top_k": top_k}
        )
        rows = result.fetchall()
        return [
            {
                "id": str(row[0]),
                "content": row[1],
                "source": row[2],
                "metadata": row[3],
                "rank": float(row[4]),
                "retrieval_type": "fulltext"
            }
            for row in rows
        ]


async def vector_search(
    query_embedding: List[float],
    top_k: int = 10,
    source_filter: Optional[List[str]] = None
) -> List[dict]:
    """向量相似检索（参数化查询，避免 SQL 注入）"""
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
    top_k = int(top_k) if top_k else 10

    base_select = (
        f"SELECT id, content, source, extra_metadata, "
        f"1 - (embedding <=> CAST(:embedding AS vector)) AS similarity "
        f"FROM {VECTOR_TABLE}"
    )
    order_clause = "ORDER BY embedding <=> CAST(:embedding AS vector)"

    params: dict = {"embedding": embedding_str, "top_k": top_k}

    if source_filter:
        if len(source_filter) == 1:
            query = text(
                f"{base_select} "
                f"WHERE source = :filter "
                f"{order_clause} "
                f"LIMIT :top_k"
            )
            params["filter"] = str(source_filter[0])
        else:
            placeholders = ", ".join([f":filter_{i}" for i in range(len(source_filter))])
            query = text(
                f"{base_select} "
                f"WHERE source IN ({placeholders}) "
                f"{order_clause} "
                f"LIMIT :top_k"
            )
            for i, val in enumerate(source_filter):
                params[f"filter_{i}"] = str(val)
    else:
        query = text(
            f"{base_select} "
            f"{order_clause} "
            f"LIMIT :top_k"
        )

    async with AsyncSessionLocal() as session:
        result = await session.execute(query, params)
        rows = result.fetchall()
        return [
            {
                "id": str(row[0]),
                "content": row[1],
                "source": row[2],
                "metadata": row[3],
                "similarity": float(row[4]) if row[4] is not None else 0.0,
                "retrieval_type": "vector"
            }
            for row in rows
        ]


def rrf_fusion(
    vector_results: List[dict],
    fulltext_results: List[dict],
    k: int = 60
) -> List[dict]:
    """
    Reciprocal Rank Fusion (RRF) 融合排序
    k: 融合参数，默认60
    """
    vector_rank = {doc["id"]: i + 1 for i, doc in enumerate(vector_results)}
    fulltext_rank = {doc["id"]: i + 1 for i, doc in enumerate(fulltext_results)}

    all_docs = {}
    for doc in vector_results:
        all_docs[doc["id"]] = doc
    for doc in fulltext_results:
        if doc["id"] not in all_docs:
            all_docs[doc["id"]] = doc

    fused_scores = {}
    for doc_id in all_docs:
        r1 = vector_rank.get(doc_id, float('inf'))
        r2 = fulltext_rank.get(doc_id, float('inf'))

        score = 0.0
        if r1 != float('inf'):
            score += 1 / (k + r1)
        if r2 != float('inf'):
            score += 1 / (k + r2)

        fused_scores[doc_id] = score

    sorted_ids = sorted(fused_scores.keys(), key=lambda x: fused_scores[x], reverse=True)

    return [
        {**all_docs[doc_id], "rrf_score": fused_scores[doc_id]}
        for doc_id in sorted_ids
    ]


async def query_rewrite(query: str) -> Tuple[str, str]:
    """
    查询重写：将用户口语转为医学术语
    """
    llm = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        temperature=0,
    )

    prompt = f"""
    你是一个医学术语标准化专家。请将用户的口语化症状描述转换为专业的医学术语，并生成标准化的查询语句。

    用户输入：{query}

    请按照以下格式输出：
    医学术语：[转换后的医学术语，用逗号分隔]
    标准化查询：[适合用于检索的标准化查询语句]

    示例：
    用户输入："我最近总是头痛，特别是早上起床的时候"
    医学术语：头痛,晨起头痛
    标准化查询：头痛 晨起发作

    用户输入："有点咳嗽，感觉喉咙不舒服"
    医学术语：咳嗽,咽喉不适
    标准化查询：咳嗽 咽喉不适
    """

    result = llm.invoke(prompt)
    content = result.content.strip()

    medical_terms = ""
    normalized_query = query

    lines = content.split("\n")
    for line in lines:
        if line.startswith("医学术语："):
            medical_terms = line.replace("医学术语：", "").strip()
        elif line.startswith("标准化查询："):
            normalized_query = line.replace("标准化查询：", "").strip()

    return medical_terms, normalized_query


async def llm_rerank(
    query: str,
    documents: List[dict],
    top_k: int = 5
) -> List[dict]:
    """
    使用 LLM 对检索结果进行重排序
    """
    llm = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        temperature=0,
    )

    docs_text = "\n".join([
        f"{i+1}. {doc['content'][:300]}"
        for i, doc in enumerate(documents)
    ])

    prompt = f"""
    你是一个医学知识检索专家。请根据以下用户查询，对提供的文档进行相关性打分（0-100分）。

    用户查询：{query}

    文档列表：
    {docs_text}

    请按照以下格式输出，每行一个文档编号和分数：
    1: 85
    2: 70
    3: 90
    4: 45
    5: 60

    评分标准：
    - 100分：文档内容与查询高度相关，能直接回答问题
    - 80-99分：文档内容与查询相关，能提供有用信息
    - 60-79分：文档内容与查询有一定相关性
    - 40-59分：文档内容与查询相关性较低
    - 0-39分：文档内容与查询基本无关
    """

    result = llm.invoke(prompt)
    content = result.content.strip()

    scores = {}
    for line in content.split("\n"):
        line = line.strip()
        if ":" in line:
            parts = line.split(":")
            try:
                idx = int(parts[0].strip()) - 1
                score = int(parts[1].strip())
                scores[idx] = score
            except:
                pass

    for i, doc in enumerate(documents):
        doc["llm_score"] = scores.get(i, 0)

    sorted_docs = sorted(documents, key=lambda x: x.get("llm_score", 0), reverse=True)
    return sorted_docs[:top_k]


async def hybrid_search(
    query: str,
    top_k: int = 10,
    enable_rewrite: bool = True,
    enable_rerank: bool = True,
    use_hybrid: bool = False
) -> Dict[str, List[dict]]:
    """
    智能检索主入口
    :param query: 用户查询
    :param top_k: 返回数量
    :param enable_rewrite: 是否启用查询重写
    :param enable_rerank: 是否启用LLM重排序
    :param use_hybrid: 是否启用混合检索（当前默认不启用，等添加大量文献后改为True）
    """
    results = {
        "original_query": query,
        "rewritten_query": query,
        "medical_terms": "",
        "vector_results": [],
        "fulltext_results": [],
        "fused_results": [],
        "reranked_results": [],
        "final_results": []
    }

    if enable_rewrite:
        try:
            medical_terms, normalized_query = await query_rewrite(query)
            results["medical_terms"] = medical_terms
            results["rewritten_query"] = normalized_query
            search_query = normalized_query
        except Exception as e:
            logger.error(f"查询重写失败: {e}")
            search_query = query
    else:
        search_query = query

    query_embedding = embed_text(search_query)
    vector_results = await vector_search(query_embedding, top_k=top_k * 2)
    results["vector_results"] = vector_results

    if use_hybrid:
        fulltext_results = await fulltext_search(search_query, top_k=top_k * 2)
        results["fulltext_results"] = fulltext_results
        fused_results = rrf_fusion(vector_results, fulltext_results)
        results["fused_results"] = fused_results[:top_k * 2]
        candidates = fused_results
    else:
        candidates = vector_results

    if enable_rerank and candidates:
        try:
            reranked_results = await llm_rerank(search_query, candidates[:top_k * 2], top_k=top_k)
            results["reranked_results"] = reranked_results
            results["final_results"] = reranked_results
        except Exception as e:
            logger.error(f"LLM重排序失败: {e}")
            results["final_results"] = candidates[:top_k]
    else:
        results["final_results"] = candidates[:top_k]

    return results


async def sync_knowledge_to_fulltext():
    """将向量表数据同步到全文索引表"""
    async with async_engine.connect() as conn:
        result = await conn.execute(text(f"SELECT id, content, source, document_id, extra_metadata FROM {VECTOR_TABLE}"))
        rows = result.fetchall()

        count = 0
        for row in rows:
            doc_id = str(row[0])
            content = row[1]
            source = row[2]
            document_id = row[3]
            extra_metadata = row[4]

            exists = await conn.execute(
                text(f"SELECT 1 FROM {FULLTEXT_TABLE} WHERE id = :id"),
                {"id": doc_id}
            )
            if not exists.scalar():
                await insert_fulltext(
                    content=content,
                    source=source,
                    document_id=document_id,
                    metadata=extra_metadata
                )
                count += 1

        await conn.commit()
    logger.info(f"✅ 已同步 {count} 条记录到全文索引")
