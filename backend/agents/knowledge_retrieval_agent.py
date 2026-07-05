"""
医学知识检索Agent
职责：查询重写(口语→医学术语) → 向量检索 → LLM总结循证参考
（混合检索功能已保留，use_hybrid设为False，等添加大量文献后可启用）
"""

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from config import get_settings
from knowledge.hybrid_retriever import hybrid_search

settings = get_settings()

from middleware.health_callback import HealthAgentCallback

callback = HealthAgentCallback(verbose=False)
llm = ChatOpenAI(
    model=settings.llm_model,
    api_key=settings.openai_api_key,
    base_url=settings.openai_base_url,
    temperature=0.2,
    callbacks=[callback],
)


def build_knowledge_retrieval_agent():
    """构建知识检索Agent"""

    llm = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        temperature=0.2,
    )

    system_prompt = """你是一位医学知识助理，负责根据检索到的医学知识，为医生提供循证参考。

# 你的职责
1. 整理检索到的医学知识
2. 提取与当前病例最相关的内容
3. 给出鉴别诊断思路
4. 标注知识来源

# 输出格式
## 相关医学知识
（列出检索到的关键知识点）

## 鉴别诊断参考
（根据知识库给出可能的鉴别诊断方向）

## 建议检查项目
（为明确诊断建议的检查）

注意：只基于给定的检索结果来回答，不要编造知识。
"""

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "问诊记录：\n{consultation_record}\n\n检索到的医学知识：\n{retrieved_knowledge}\n\n请给出循证参考。"),
    ])

    chain = prompt | llm | StrOutputParser()
    return chain


async def retrieve_and_analyze(consultation_record: str, report_analysis: str = "") -> str:
    """检索医学知识并给出循证参考"""

    query_text = consultation_record
    if report_analysis:
        query_text += f"\n检查结果摘要：{report_analysis[:500]}"

    results = await hybrid_search(
        query=query_text,
        top_k=8,
        enable_rewrite=True,
        enable_rerank=False,
        use_hybrid=False
    )

    retrieved_docs = results.get("final_results", [])

    if not retrieved_docs:
        return "未检索到相关医学知识"

    retrieved = "\n\n".join([
        f"【相似度: {doc['similarity']:.4f}】\n{doc['content']}"
        for doc in retrieved_docs
    ])

    chain = build_knowledge_retrieval_agent()
    result = await chain.ainvoke({
        "consultation_record": consultation_record,
        "retrieved_knowledge": retrieved,
    })
    return result
