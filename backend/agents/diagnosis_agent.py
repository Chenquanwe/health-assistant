"""
诊断建议Agent
职责：综合问诊+报告+RAG → 鉴别诊断排序
"""

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from config import get_settings

settings = get_settings()

from middleware.health_callback import HealthAgentCallback

callback = HealthAgentCallback(verbose=False)
llm = ChatOpenAI(
    model=settings.llm_model,
    api_key=settings.openai_api_key,
    base_url=settings.openai_base_url,
    temperature=0.2,  # 各Agent温度不同
    callbacks=[callback],
)
def build_diagnosis_agent():
    """构建诊断建议Agent"""

    llm = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        temperature=0.2,
    )

    system_prompt = """你是一位资深全科医生，负责综合所有信息给出鉴别诊断建议。

# 你的职责
1. 综合分析问诊记录、检查报告和循证医学知识
2. 给出Top-3鉴别诊断，按可能性排序
3. 每个诊断附置信度(高/中/低)和依据
4. 列出排除某些疾病的理由

# 输出格式
## 鉴别诊断（按可能性排序）

### 1. [疾病名称] — 置信度：[高/中/低]
- 支持证据：
- 不符合点：
- 建议确认检查：

### 2. [疾病名称] — 置信度：[高/中/低]
...

## 排除考虑
以下疾病已考虑但可能性较低：
- [疾病]：排除理由

## 下一步建议
（进一步检查或治疗建议）
"""

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human",
         "问诊记录：\n{consultation_record}\n\n"
         "检查报告分析：\n{report_analysis}\n\n"
         "循证医学参考：\n{rag_reference}\n\n"
         "请给出鉴别诊断建议。"
         ),
    ])

    chain = prompt | llm | StrOutputParser()
    return chain


async def diagnose(consultation_record: str, report_analysis: str, rag_reference: str) -> str:
    """执行诊断"""
    chain = build_diagnosis_agent()
    result = await chain.ainvoke({
        "consultation_record": consultation_record,
        "report_analysis": report_analysis or "无检查报告",
        "rag_reference": rag_reference,
    })
    return result