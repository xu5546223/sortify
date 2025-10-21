"""
QA問答統計分析 API

提供問答系統的性能統計和分析數據
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.dependencies import get_db
from app.models.user_models import User
from app.core.security import get_current_active_user
from app.core.logging_utils import AppLogger
from app.services.qa_workflow.qa_analytics_service import qa_analytics_service

router = APIRouter()
logger = AppLogger(__name__, level=logging.DEBUG).get_logger()


@router.get("/statistics")
async def get_qa_statistics(
    time_range: str = Query("24h", description="時間範圍: 24h, 7d, 30d, all"),
    intent_filter: Optional[str] = Query(None, description="意圖類型過濾"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    獲取QA問答統計數據
    
    - **time_range**: 時間範圍 (24h, 7d, 30d, all)
    - **intent_filter**: 可選的意圖類型過濾
    """
    try:
        logger.info(f"用戶 {current_user.username} 請求QA統計數據, 時間範圍: {time_range}")
        
        # 獲取統計數據
        statistics = await qa_analytics_service.get_statistics(
            db=db,
            user_id=str(current_user.id),
            time_range=time_range,
            intent_filter=intent_filter
        )
        
        logger.info(f"統計數據獲取成功: {statistics.get('total_questions', 0)} 個問題")
        
        return {
            "success": True,
            **statistics
        }
        
    except Exception as e:
        logger.error(f"獲取QA統計失敗: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"獲取統計數據失敗: {str(e)}"
        )


@router.get("/trends")
async def get_performance_trends(
    days: int = Query(7, ge=1, le=90, description="天數"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    獲取性能趨勢數據
    
    - **days**: 天數 (1-90)
    """
    try:
        logger.info(f"用戶 {current_user.username} 請求性能趨勢, 天數: {days}")
        
        trends = await qa_analytics_service.get_performance_trends(
            db=db,
            user_id=str(current_user.id),
            days=days
        )
        
        return {
            "success": True,
            **trends
        }
        
    except Exception as e:
        logger.error(f"獲取性能趨勢失敗: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"獲取趨勢數據失敗: {str(e)}"
        )


@router.get("/summary")
async def get_analytics_summary(
    current_user: User = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    獲取統計摘要(包含多個時間範圍的對比)
    """
    try:
        # 獲取不同時間範圍的統計
        stats_24h = await qa_analytics_service.get_statistics(db, str(current_user.id), "24h")
        stats_7d = await qa_analytics_service.get_statistics(db, str(current_user.id), "7d")
        stats_30d = await qa_analytics_service.get_statistics(db, str(current_user.id), "30d")
        
        return {
            "success": True,
            "summary": {
                "past_24h": {
                    "total": stats_24h.get("total_questions", 0),
                    "avg_api_calls": stats_24h.get("avg_api_calls", 0),
                    "cost_saved": stats_24h.get("cost_metrics", {}).get("cost_saved_percentage", 0)
                },
                "past_7d": {
                    "total": stats_7d.get("total_questions", 0),
                    "avg_api_calls": stats_7d.get("avg_api_calls", 0),
                    "cost_saved": stats_7d.get("cost_metrics", {}).get("cost_saved_percentage", 0)
                },
                "past_30d": {
                    "total": stats_30d.get("total_questions", 0),
                    "avg_api_calls": stats_30d.get("avg_api_calls", 0),
                    "cost_saved": stats_30d.get("cost_metrics", {}).get("cost_saved_percentage", 0)
                }
            }
        }
        
    except Exception as e:
        logger.error(f"獲取統計摘要失敗: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"獲取摘要失敗: {str(e)}"
        )

