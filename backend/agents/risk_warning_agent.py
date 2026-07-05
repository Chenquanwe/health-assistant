"""
风险预警Agent
职责：规则引擎+LLM双重判断，输出风险等级和建议
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
    temperature=0.1,  # 各Agent温度不同
    callbacks=[callback],
)
# 硬编码红旗征象规则
EMERGENCY_RULES = [
    "突发剧烈头痛（雷击样）",
    "胸痛伴呼吸困难",
    "大出血",
    "意识障碍",
    "抽搐",
    "严重过敏(喉头水肿)",
    "中毒",
    "高热>40°C持续不退",
]


def check_emergency_rules(consultation_record: str, report_analysis: str) -> list:
    """规则引擎：硬编码红旗征象扫描"""
    triggered = []
    combined = (consultation_record + report_analysis).lower()

    if any(w in combined for w in ["雷击样", "最严重的头痛", "从未有过的头痛"]):
        triggered.append("雷击样头痛 — 需排除蛛网膜下腔出血")
    if any(w in combined for w in ["胸痛", "胸闷"]) and any(w in combined for w in ["喘不上气", "呼吸困难"]):
        triggered.append("胸痛+呼吸困难 — 需排除心梗/肺栓塞/主动脉夹层")
    if any(w in combined for w in ["意识不清", "叫不醒", "昏迷", "昏倒"]):
        triggered.append("意识障碍 — 立即急诊")
    if any(w in combined for w in ["抽搐", "抽筋"]) and "抽筋" not in combined[-10:]:
        triggered.append("抽搐 — 需排除癫痫/中枢神经系统病变")

    return triggered


def build_risk_warning_agent():
    """构建风险预警Agent"""

    llm = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        temperature=0.1,
    )

    system_prompt = """你是一位医疗安全专家，负责综合评估患者风险。

# 你的职责
1. 综合分析所有信息，评估风险等级
2. 风险等级：🔴红色(立即就医) 🟡黄色(尽快就诊) 🟢绿色(可观察)
3. 给出具体的风险原因
4. 给出明确的行动建议

# 输出格式
## 风险等级
🔴/🟡/🟢 [等级名称]

## 风险原因
1. ...
2. ...

## 行动建议
- ...
- ...

## 就医紧急度
（一句话说明是否需要立即就医）
"""

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human",
         "规则引擎触发预警：\n{rule_alerts}\n\n"
         "问诊记录：\n{consultation_record}\n\n"
         "检查报告：\n{report_analysis}\n\n"
         "诊断建议：\n{diagnosis}\n\n"
         "请给出风险预警评估。"
         ),
    ])

    chain = prompt | llm | StrOutputParser()
    return chain


async def assess_risk(consultation_record: str, report_analysis: str, diagnosis: str) -> str:
    """执行风险评估"""

    # 规则引擎先行
    rule_alerts = check_emergency_rules(consultation_record, report_analysis)
    rule_text = "\n".join(rule_alerts) if rule_alerts else "未触发硬编码红旗征象"

    # LLM 综合判断
    chain = build_risk_warning_agent()
    result = await chain.ainvoke({
        "rule_alerts": rule_text,
        "consultation_record": consultation_record,
        "report_analysis": report_analysis or "无检查报告",
        "diagnosis": diagnosis,
    })
    return result