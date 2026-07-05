"""
健康报告接口
"""

from fastapi import APIRouter

router = APIRouter()

# 模拟存储（后续可接入数据库）
_reports_store = {}


@router.get("/api/report/{session_id}")
async def get_report(session_id: str):
    report = _reports_store.get(session_id)
    if not report:
        return {"error": "报告不存在"}
    return report


@router.get("/api/reports")
async def list_reports():
    return {"reports": list(_reports_store.keys()), "total": len(_reports_store)}