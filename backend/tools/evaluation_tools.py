"""
评估工具 — 问诊完整度、PDF解析
"""

from langchain.tools import tool


# SOCRATES 框架必须项
REQUIRED_DIMENSIONS = [
    "site",        # 部位
    "onset",       # 起病时间
    "character",   # 性质
    "severity",    # 严重程度
    "allergy",     # 过敏史
]

# 建议项
SUGGESTED_DIMENSIONS = [
    "associated",     # 伴随症状
    "past_history",   # 既往史
    "medication",     # 用药史
    "radiation",      # 放射
    "timing",         # 时间规律
    "exacerbating",   # 加重缓解因素
]


@tool
def completeness_evaluator_tool(consultation_record_json: str) -> str:
    """
    评估问诊记录的信息完整度。
    输入：JSON格式的问诊记录，如 {"site":"头痛","onset":"3天前","character":"跳痛",...}
    输出：完整度分数(0~1) + 缺失维度列表 + 建议追问的问题
    """
    import json

    try:
        record = json.loads(consultation_record_json)
    except json.JSONDecodeError:
        record = {}

    # 计算必须项完整度
    required_filled = [d for d in REQUIRED_DIMENSIONS if record.get(d)]
    required_score = len(required_filled) / len(REQUIRED_DIMENSIONS) if REQUIRED_DIMENSIONS else 1

    # 计算建议项完整度
    suggested_filled = [d for d in SUGGESTED_DIMENSIONS if record.get(d)]
    suggested_score = len(suggested_filled) / len(SUGGESTED_DIMENSIONS) if SUGGESTED_DIMENSIONS else 1

    # 综合分数（必须项权重 70%，建议项权重 30%）
    total_score = required_score * 0.7 + suggested_score * 0.3

    # 缺失维度
    missing_required = [d for d in REQUIRED_DIMENSIONS if not record.get(d)]
    missing_suggested = [d for d in SUGGESTED_DIMENSIONS if not record.get(d)]

    # 维度中文映射
    dim_cn = {
        "site": "部位",
        "onset": "起病时间",
        "character": "性质",
        "severity": "严重程度(1-10分)",
        "allergy": "过敏史",
        "associated": "伴随症状",
        "past_history": "既往史",
        "medication": "用药史",
        "radiation": "放射",
        "timing": "时间规律",
        "exacerbating": "加重/缓解因素",
    }

    result = f"问诊完整度: {total_score:.0%}\n"

    if missing_required:
        result += f"\n【必须追问】以下信息缺失:\n"
        for d in missing_required:
            result += f"  - {dim_cn.get(d, d)}\n"

    if missing_suggested and total_score < 0.8:
        result += f"\n【建议追问】以下信息可补充:\n"
        for d in missing_suggested[:3]:  # 最多提示3个
            result += f"  - {dim_cn.get(d, d)}\n"

    result += f"\n完整度阈值: 80%，当前{'已达' if total_score >= 0.8 else '未达'}标"

    return result


@tool
def pdf_parser_tool(file_path: str) -> str:
    """
    解析PDF检查报告，提取文本内容。
    输入：PDF文件路径
    输出：提取的文本内容
    """
    try:
        import pdfplumber
        with pdfplumber.open(file_path) as pdf:
            text_parts = []
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)
            result = "\n".join(text_parts)
            return result if result.strip() else "PDF 中未提取到文本内容，可能需要 OCR。"
    except ImportError:
        return "pdfplumber 未安装，无法解析 PDF。请安装: pip install pdfplumber"
    except Exception as e:
        return f"PDF 解析失败: {e}"
