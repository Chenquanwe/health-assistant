"""
检索 API 路由
功能：查询重写 + 向量检索 + (可选混合检索)
"""
from fastapi import APIRouter, Query, HTTPException
from typing import Optional, Dict
from knowledge.hybrid_retriever import hybrid_search, query_rewrite

router = APIRouter(prefix="/api/retrieval", tags=["检索"])


@router.get("/search", response_model=Dict)
async def search(
    q: str = Query(..., description="用户查询"),
    top_k: int = Query(10, description="返回数量"),
    enable_rewrite: bool = Query(True, description="是否启用查询重写"),
    use_hybrid: bool = Query(False, description="是否启用混合检索（等添加大量文献后再启用）"),
):
    """检索接口"""
    if not q or len(q.strip()) == 0:
        raise HTTPException(status_code=400, detail="查询不能为空")

    try:
        results = await hybrid_search(
            query=q,
            top_k=top_k,
            enable_rewrite=enable_rewrite,
            use_hybrid=use_hybrid
        )
        return {
            "success": True,
            "message": "检索成功",
            "data": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"检索失败: {str(e)}")


@router.get("/query-rewrite", response_model=Dict)
async def query_rewrite_endpoint(
    q: str = Query(..., description="用户查询")
):
    """查询重写接口"""
    if not q or len(q.strip()) == 0:
        raise HTTPException(status_code=400, detail="查询不能为空")

    try:
        medical_terms, normalized_query = await query_rewrite(q)
        return {
            "success": True,
            "message": "重写成功",
            "data": {
                "original_query": q,
                "medical_terms": medical_terms,
                "normalized_query": normalized_query
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重写失败: {str(e)}")


@router.get("/health", response_model=Dict)
async def health():
    """健康检查"""
    return {"status": "healthy", "service": "retrieval"}
