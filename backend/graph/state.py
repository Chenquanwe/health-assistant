"""
LangGraph 全局状态定义
"""
from typing import TypedDict, List, Optional, Any


class Message(TypedDict):
    role: str
    content: str


class ConsultationState(TypedDict):
    # 会话基础
    user_id: str
    session_id: str
    messages: List[Message]
    chief_complaint: str

    # 分诊结果
    triage_urgency: str
    triage_department: str
    triage_summary: str

    # 问诊状态
    consultation_phase: str  # "asking" | "analyzing_report" | "completed"
    consultation_record: str
    completeness_score: float

    # 检查报告
    pending_reports: List[dict]
    analyzed_reports: List[dict]
    report_analysis: str

    # 下游结果
    rag_result: str
    diagnosis: str
    risk_warning: str
    final_report: str

    # 流程控制
    next_step: str
    error: Optional[str]