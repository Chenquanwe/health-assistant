"""
检查报告分析Agent
职责：解析PDF/图片报告 → 提取指标 → 对照正常值 → 输出异常列表
使用 LangChain: ChatPromptTemplate + LLMChain + Tool
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
def build_report_analysis_agent():
    """构建报告分析Agent"""

    llm = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        temperature=0.1,
    )

    system_prompt = """你是一位临床检验科医生，擅长解读各类检查报告。

# 你的职责
1. 解析检查报告文本，提取所有检测项目及其数值
2. 对照正常值范围，标记异常指标
3. 按异常程度分级：偏高/偏低/危急值
4. 给出每个异常指标的临床意义简述
5. 如果报告正常，告知用户无需担心

# 重要：表格数据解析规则
由于 OCR 识别可能导致表格数据错位，请按以下规则解析：
1. 表格通常有多列：代号 | 项目名称 | 检测值 | 参考范围
2. 代号列包含英文缩写如 WBC、NEU%、LYM% 等
3. 参考范围格式通常是 "X.X-X.X" 或 "X.X~X.X"
4. 如果数据排列混乱，尝试根据上下文推断正确的对应关系
5. 同一个指标的行，其数值和参考范围应该在同一行或相邻行

# 输出格式
请按以下格式输出分析结果：

## 报告概要
- 检测项目总数：X 项
- 异常项目数：X 项
- 危急值：X 项

## 异常指标详情
| 指标名称 | 检测值 | 正常范围 | 偏离程度 | 临床意义 |
|---------|--------|---------|---------|---------|
| xxx     | xxx    | xxx     | 偏高/偏低 | xxx     |

## 综合建议
（基于异常指标的综合分析建议，2-3句话）

# 常用正常值参考
- 白细胞(WBC)：4.0-10.0×10⁹/L
- 中性粒细胞：1.8-6.3×10⁹/L
- 淋巴细胞：1.1-3.2×10⁹/L
- 血红蛋白(Hb)：男120-160g/L，女110-150g/L
- 血小板(PLT)：100-300×10⁹/L
- C反应蛋白(CRP)：<5mg/L
- 血糖(GLU)：空腹3.9-6.1mmol/L
- 谷丙转氨酶(ALT)：5-40U/L
- 谷草转氨酶(AST)：8-40U/L
- 肌酐(Cr)：44-133μmol/L
- 尿素(BUN)：2.9-8.2mmol/L
- 总胆固醇(TC)：<5.2mmol/L
- 甘油三酯(TG)：<1.7mmol/L

# 注意
- 如果报告文本无法识别，请说明原因
- 危急值必须用 ⚠️ 标注
- 不要编造报告中没有的数据
- 对于 OCR 识别的模糊数据，基于常识推断最可能的结果
"""

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "请分析以下检查报告：\n\n{report_text}"),
    ])

    chain = prompt | llm | StrOutputParser()

    return chain


async def analyze_report(report_text: str) -> str:
    """分析检查报告"""
    chain = build_report_analysis_agent()
    result = await chain.ainvoke({"report_text": report_text})
    return result


# 兼容别名
analyze_report_agent = analyze_report