"""
种子数据加载器 — 读取 JSON → 文本化 → Embedding → pgvector
"""
import sys
import logging
logger = logging.getLogger(__name__)
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json
# import os
import asyncio
from typing import List
import dashscope
from config import get_settings
from knowledge.vector_store import (
    create_vector_table,
    insert_vector,
    get_vector_count
)

settings = get_settings()


def embed_text(text: str) -> list:
    """用阿里云 dashscope 原生方式生成 Embedding"""
    resp = dashscope.TextEmbedding.call(
        model=settings.embedding_model,
        api_key=settings.openai_api_key,
        input=text,
    )
    if resp.status_code == 200:
        return resp.output["embeddings"][0]["embedding"]
    else:
        raise Exception(f"Embedding 失败: {resp.code} - {resp.message}")


def load_seed_data(seed_dir: str) -> List[dict]:
    """加载所有种子 JSON 文件"""
    data = []
    for filename in sorted(os.listdir(seed_dir)):
        if filename.endswith(".json"):
            filepath = os.path.join(seed_dir, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                data.append(json.load(f))
    return data


def symptom_to_text(symptom_data: dict) -> List[dict]:
    """
    将一个症状 JSON 拆分为多个可检索的文本块
    每个块包含不同维度的信息
    """
    chunks = []

    symptom = symptom_data["symptom"]
    department = symptom_data.get("department", "")

    # 块1：症状概述 + 科室
    chunks.append({
        "content": f"症状：{symptom}。推荐就诊科室：{department}。",
        "metadata": {"symptom": symptom, "type": "overview", "department": department}
    })

    # 块2：必须追问的问题
    must_ask_text = "必须追问的问题：\n" + "\n".join(
        [f"- {q['dimension']}：{q['question']}" for q in symptom_data.get("must_ask", [])]
    )
    chunks.append({
        "content": f"症状：{symptom}\n{must_ask_text}",
        "metadata": {"symptom": symptom, "type": "must_ask"}
    })

    # 块3：建议追问
    suggest = symptom_data.get("suggest_ask", [])
    if suggest:
        suggest_text = "建议追问的问题：\n" + "\n".join(
            [f"- {q['dimension']}：{q['question']}" for q in suggest]
        )
        chunks.append({
            "content": f"症状：{symptom}\n{suggest_text}",
            "metadata": {"symptom": symptom, "type": "suggest_ask"}
        })

    # 块4：红旗征象（安全底线）
    red_flags = symptom_data.get("red_flags", [])
    if red_flags:
        red_text = "危险信号（红旗征象）：\n" + "\n".join([f"- {r}" for r in red_flags])
        chunks.append({
            "content": f"症状：{symptom}\n{red_text}",
            "metadata": {"symptom": symptom, "type": "red_flags"}
        })

    # 块5：鉴别疾病
    diseases = symptom_data.get("related_diseases", [])
    for disease in diseases:
        features = "、".join(disease.get("key_features", []))
        chunks.append({
            "content": f"症状：{symptom}。可能疾病：{disease['disease']}。关键特征：{features}。",
            "metadata": {"symptom": symptom, "type": "disease", "disease": disease["disease"]}
        })

    # 块6：触发追问
    triggers = symptom_data.get("trigger_questions", {})
    if triggers:
        trigger_text = "条件触发追问：\n" + "\n".join(
            [f"- {k}：{v}" for k, v in triggers.items()]
        )
        chunks.append({
            "content": f"症状：{symptom}\n{trigger_text}",
            "metadata": {"symptom": symptom, "type": "triggers"}
        })

    return chunks


async def seed_all():
    """主函数：加载种子数据并向量化入库"""
    seed_dir = os.path.join(os.path.dirname(__file__), "seed_data")

    logger.info(f"\n📂 加载种子数据: {seed_dir}")
    all_data = load_seed_data(seed_dir)
    logger.info(f"   找到 {len(all_data)} 个症状 JSON 文件")

    if len(all_data) == 0:
        logger.info("   ⚠️ 没有找到种子数据文件，请先添加 JSON 文件")
        return

    # 确保向量表存在
    logger.info(f"\n🗄️  创建向量表...")
    await create_vector_table()

    # 处理每个症状
    total_chunks = 0
    for symptom_data in all_data:
        symptom_name = symptom_data["symptom"]
        chunks = symptom_to_text(symptom_data)
        logger.info(f"\n📝 {symptom_name}: 拆分为 {len(chunks)} 个文本块")

        for i, chunk in enumerate(chunks):
            try:
                embedding = embed_text(chunk["content"])
                await insert_vector(
                    content=chunk["content"],
                    embedding=embedding,
                    source="official",
                    document_id=None,
                    metadata=chunk["metadata"]
                )
                total_chunks += 1
                logger.info(f"   ✅ 块 {i+1}/{len(chunks)} 入库成功 ({chunk['metadata']['type']})")
            except Exception as e:
                logger.info(f"   ❌ 块 {i+1}/{len(chunks)} 失败: {e}")

    # 验证
    count = await get_vector_count()
    logger.info(f"\n{'=' * 40}")
    logger.info(f"✅ 向量化完成: 共 {total_chunks} 个文本块入库")
    logger.info(f"   向量表总计: {count} 条记录")
    logger.info(f"{'=' * 40}")


if __name__ == "__main__":
    asyncio.run(seed_all())