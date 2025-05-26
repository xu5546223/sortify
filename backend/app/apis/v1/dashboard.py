from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from ...dependencies import get_db
from ...models.dashboard_models import SystemStats, RecentActivities, ActivityItem
from ...crud import crud_dashboard

router = APIRouter()

@router.get(
    "/stats",
    response_model=SystemStats,
    summary="獲取系統統計數據",
    description="提供關於系統整體狀態的統計信息，如文件數量、用戶連接數等。"
)
async def get_dashboard_stats(db: AsyncIOMotorDatabase = Depends(get_db)):
    stats = await crud_dashboard.get_system_stats(db=db)
    return stats

@router.get(
    "/activities",
    response_model=RecentActivities,
    summary="獲取最近活動列表",
    description="提供系統中最近發生的活動或重要日誌條目。"
)
async def get_dashboard_activities(
    db: AsyncIOMotorDatabase = Depends(get_db),
    skip: int = Query(0, ge=0, description="跳過的活動數量"),
    limit: int = Query(20, ge=1, le=100, description="返回的活動數量上限"),
    user_id: Optional[str] = Query(None, description="篩選特定用戶的活動"),
    # activity_types: Optional[List[str]] = Query(None, description="篩選特定類型的活動 (例如: document_uploaded, user_login)") # 暫時不實現複雜篩選
):
    activities_list = await crud_dashboard.get_recent_activities(
        db=db, 
        skip=skip, 
        limit=limit, 
        user_id=user_id
        # activity_types_filter=activity_types # 傳遞給CRUD層
    )
    total_count = await crud_dashboard.count_recent_activities(
        db=db,
        user_id=user_id
        # activity_types_filter=activity_types
    )
    return RecentActivities(activities=activities_list, total_count=total_count, limit=limit, skip=skip) 