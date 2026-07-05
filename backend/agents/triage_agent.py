"""
分诊导诊Agent
接收用户主诉 → 判断紧急程度 → 推荐科室 → 生成预问诊问题
使用 LangChain: PromptTemplate + ChatModel + PydanticOutputParser + Tool
"""

"""
分诊导诊Agent
"""

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
from typing import List
from config import get_settings


settings = get_settings()
from middleware.health_callback import HealthAgentCallback

def build_triage_agent():
    callback = HealthAgentCallback(verbose=True)
    llm = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        temperature=0.1,
        callbacks=[callback],
    )


# ============ 结构化输出定义 ============

class TriageResult(BaseModel):
    urgency: str = Field(
        description="紧急等级: emergency(红色-立即就医) / urgent(黄色-尽快就诊) / normal(绿色-可常规就诊)")
    department: str = Field(description="推荐就诊科室")
    department_reason: str = Field(description="推荐该科室的理由")
    pre_questions: List[str] = Field(description="建议患者在就诊前准备好的信息，2-3个问题")
    red_flags: List[str] = Field(description="需要警惕的危险信号，如有则必须标注")
    summary: str = Field(description="对患者主诉的简要总结，一句话")


# ============ 构建 Agent ============

def build_triage_agent():
    """构建分诊Agent"""

    # LLM
    llm = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        temperature=0.1,  # 低温度，保证稳定输出
    )

    # 结构化输出解析器
    parser = PydanticOutputParser(pydantic_object=TriageResult)

    # 提示词模板
    prompt = ChatPromptTemplate.from_messages([
        ("system", """你是一位经验丰富的急诊分诊护士，擅长根据患者的简短主诉快速判断病情紧急程度并推荐合适的科室。

# 分诊原则
1. **紧急(emergency)**：可能危及生命的状况，需要立即就医。包括但不限于：
   - 胸痛、胸闷伴呼吸困难
   - 突发剧烈头痛（"一生中最严重的头痛"）
   - 严重外伤、大出血
   - 意识障碍、抽搐
   - 呼吸困难、窒息感
   - 中毒、过敏反应(喉头水肿)

2. **尽快就诊(urgent)**：需要尽快就医但暂无生命危险。包括但不限于：
   - 持续高热(>39°C)不退
   - 中度疼痛影响日常生活
   - 持续呕吐/腹泻导致脱水风险
   - 不明原因的明显体重下降

3. **常规就诊(normal)**：可以预约门诊。包括但不限于：
   - 轻度症状、慢性病复诊
   - 健康咨询、体检异常复查
   - 轻微不适、自限性疾病可能

# 科室推荐参考
- 头痛：神经内科；伴发热→发热门诊；突发剧痛→急诊科
- 胸痛：心内科；伴反酸烧心→消化内科；外伤后→胸外科
- 腹痛：消化内科/普外科；女性下腹痛→妇科；右上腹痛→肝胆外科
- 发热：发热门诊/感染科；伴呼吸道症状→呼吸内科
- 咳嗽：呼吸内科；过敏→变态反应科
- 关节痛：风湿免疫科/骨科
- 皮疹：皮肤科；伴发热→感染科
- 头晕：神经内科/耳鼻喉科
- 心悸：心内科
- 视力问题：眼科

# 输出要求
- 用中文输出
- 红旗征象务必标注清楚
- pre_questions 是给患者看的，帮助患者提前准备信息

{format_instructions}"""),
        ("human", "{chief_complaint}")
    ])

    # 组装 Chain
    chain = prompt | llm | parser

    return chain


# ============ 调用接口 ============

async def triage(chief_complaint: str) -> TriageResult:
    """
    执行分诊

    参数:
        chief_complaint: 患者主诉，如 "我头痛三天了"

    返回:
        TriageResult 结构化分诊结果
    """
    chain = build_triage_agent()
    result = await chain.ainvoke({
        "chief_complaint": chief_complaint,
        "format_instructions": PydanticOutputParser(pydantic_object=TriageResult).get_format_instructions(),
    })
    return result