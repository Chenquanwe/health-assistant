"""
知识向量存储 — pgvector 操作封装
"""

import json
import logging
logger = logging.getLogger(__name__)
from typing import List, Optional
from sqlalchemy import text
from database import async_engine, AsyncSessionLocal


VECTOR_TABLE = "medical_knowledge_vectors"


async def create_vector_table():
    """创建向量表（如果不存在）"""
    async with async_engine.connect() as conn:
        await conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS {VECTOR_TABLE} (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                content TEXT NOT NULL,
                embedding vector(1024),
                source VARCHAR(50) DEFAULT 'official',
                document_id VARCHAR(255),
                extra_metadata JSONB,
                created_at TIMESTAMP DEFAULT now()
            )
        """))
        await conn.commit()
    logger.info(f"   ✅ 向量表 {VECTOR_TABLE} 就绪")


async def insert_vector(
    content: str,
    embedding: List[float],
    source: str = "official",
    document_id: Optional[str] = None,
    metadata: Optional[dict] = None
):
    """插入一条向量"""
    embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
    metadata_str = json.dumps(metadata) if metadata else None

    async with async_engine.connect() as conn:
        await conn.execute(
            text(f"""
                INSERT INTO {VECTOR_TABLE} (content, embedding, source, document_id, extra_metadata)
                VALUES (
                    :content,
                    CAST(:embedding AS vector),
                    :source,
                    :document_id,
                    CAST(:extra_metadata AS jsonb)
                )
            """),
            {
                "content": content,
                "embedding": embedding_str,
                "source": source,
                "document_id": document_id,
                "extra_metadata": metadata_str,
            }
        )
        await conn.commit()


async def search_similar(
    query_embedding: List[float],
    top_k: int = 5,
    source_filter: Optional[List[str]] = None
) -> List[dict]:
    """向量相似检索（参数化查询，避免 SQL 注入）"""
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
    top_k = int(top_k) if top_k else 5

    logger.info(f"[VectorStore] search_similar: embedding_dim={len(query_embedding)}, top_k={top_k}, source_filter={source_filter}")

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

    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(query, params)
            rows = result.fetchall()
        logger.info(f"[VectorStore] SQL 执行成功: rows={len(rows)}")
    except Exception as e:
        logger.error(f"[VectorStore] SQL 执行失败: {e}")
        raise

    results = []
    for row in rows:
        content = row[1] or ""
        summary = content[:80].replace("\n", " ")
        try:
            score = float(row[4]) if row[4] is not None else 0.0
        except Exception:
            score = 0.0
        logger.info(
            f"[VectorStore] 命中: similarity={score:.3f}, "
            f"source={row[2]}, preview={summary}"
        )
        results.append({
            "id": row[0],
            "content": content,
            "source": row[2],
            "metadata": row[3],
            "similarity": score,
        })
    return results


async def get_vector_count() -> int:
    """获取向量总数"""
    async with async_engine.connect() as conn:
        result = await conn.execute(text(f"SELECT COUNT(*) FROM {VECTOR_TABLE}"))
        return result.scalar()