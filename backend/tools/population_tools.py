"""
人群特征匹配工具
"""

from langchain.tools import tool


@tool
def population_match_tool(age: int = 0, gender: str = "", special_status: str = "") -> str:
    """
    根据用户年龄、性别、特殊状态匹配追问调整规则。
    输入：age=年龄, gender=性别(男/女), special_status=特殊状态(孕妇/免疫功能低下/无)
    输出：该人群的追问调整建议
    """
    rules = []

    # 老年人 (≥65)
    if age >= 65:
        rules.append("【老年人群】追问调整：")
        rules.append("- 追加问：有无跌倒史？认知功能有无变化？")
        rules.append("- 追加问：是否多重用药？(≥5种药物)")
        rules.append("- 注意：症状表现可能不典型，疼痛阈值可能升高")
        rules.append("- 建议追问：日常生活能力有无下降？")

    # 孕妇
    if special_status == "孕妇" or "孕" in special_status:
        rules.append("【孕妇人群】追问调整：")
        rules.append("- 必须追问：孕周？胎动有无异常？")
        rules.append("- 必须追问：有无阴道出血或流液？")
        rules.append("- 注意：避免使用致畸药物，检查需考虑胎儿安全")
        rules.append("- 建议追问：孕期有无并发症(高血压/糖尿病)？")

    # 儿童 (<12)
    if 0 < age < 12:
        rules.append("【儿童人群】追问调整：")
        rules.append("- 追问转向监护人：孩子精神状态如何？食欲如何？")
        rules.append("- 追加问：有无传染病接触史？疫苗接种史？")
        rules.append("- 注意：病情变化可能更快，需更密切观察")

    # 免疫功能低下
    if "免疫" in special_status or "低下" in special_status:
        rules.append("【免疫功能低下人群】追问调整：")
        rules.append("- 追加问：有无机会性感染相关症状？")
        rules.append("- 注意：感染风险升高，临床表现可能不典型")
        rules.append("- 建议追问：近期有无使用免疫抑制剂或化疗？")

    if not rules:
        rules.append("【普通成人】无特殊人群追问调整规则，按标准 SOCRATES 框架问诊。")

    return "\n\n".join(rules)