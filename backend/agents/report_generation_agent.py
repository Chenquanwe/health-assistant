"""
报告生成Agent
职责：汇总全流程结果 → 生成结构化健康报告
"""

from langchain_openai import ChatOpenAI
import logging
logger = logging.getLogger(__name__)
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

def build_report_generation_agent():
    """构建报告生成Agent"""

    llm = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        temperature=0.2,
    )

    system_prompt = """你是一位医疗报告撰写专家，负责将智能健康助手的所有分析结果整理为一份专业、易懂的健康报告。

# 报告结构（严格按以下7段）
1. **基本信息与主诉** — 患者主诉概述
2. **问诊摘要** — SOCRATES框架整理
3. **检查结果解读** — 如果有检查报告
4. **鉴别诊断与依据** — Top-3可能性
5. **风险提示** — 风险等级+红旗征象
6. **就诊建议** — 科室+紧急程度
7. **免责声明** — 固定文案

# 免责声明（必须包含）
> ⚠️ 本报告由AI智能健康助手生成，仅供参考，不构成医疗诊断或治疗建议。如有不适，请及时就医，以医生面诊意见为准。

# 风格要求
- 专业但通俗易懂
- 重要信息用粗体标注
- 风险等级用颜色标记（🔴🟡🟢）
- 整体字数控制在800字以内
"""

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human",
         "请根据以下信息生成健康报告：\n\n"
         "【主诉】{chief_complaint}\n\n"
         "【分诊结果】{triage_result}\n\n"
         "【问诊记录】{consultation_record}\n\n"
         "【检查报告分析】{report_analysis}\n\n"
         "【循证参考】{rag_reference}\n\n"
         "【诊断建议】{diagnosis}\n\n"
         "【风险预警】{risk_warning}"
         ),
    ])

    chain = prompt | llm | StrOutputParser()
    return chain


async def generate_report(
        chief_complaint: str,
        triage_result: str,
        consultation_record: str,
        report_analysis: str,
        rag_reference: str,
        diagnosis: str,
        risk_warning: str,
) -> str:
    """生成健康报告"""
    logger.info(f"[报告生成] chief_complaint: {chief_complaint[:50]}")
    logger.info(f"[报告生成] consultation_record长度: {len(consultation_record)}")
    logger.info(f"[报告生成] diagnosis: {diagnosis[:50] if diagnosis else '空'}")
    logger.error(f"[报告生成] risk_warning: {risk_warning[:50] if risk_warning else '空'}")

    chain = build_report_generation_agent()
    result = await chain.ainvoke({
        "chief_complaint": chief_complaint,
        "triage_result": triage_result,
        "consultation_record": consultation_record,
        "report_analysis": report_analysis or "无检查报告",
        "rag_reference": rag_reference,
        "diagnosis": diagnosis,
        "risk_warning": risk_warning,
    })
    logger.info(f"[报告生成] 结果长度: {len(result)}")
    return result