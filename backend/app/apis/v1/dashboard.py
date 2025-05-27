from typing import List, Optional

from fastapi import APIRouter, Depends, Query, HTTPException, status # Add HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from ...dependencies import get_db
from ...models.dashboard_models import SystemStats, RecentActivities, ActivityItem
from ...models.user_models import User # Import User
from ...core.security import get_current_active_user # Import auth dependency
from ...crud import crud_dashboard

router = APIRouter()

@router.get(
    "/stats",
    response_model=SystemStats,
    summary="獲取系統統計數據",
    description="提供關於系統整體狀態的統計信息，如文件數量、用戶連接數等。"
)
async def get_dashboard_stats(
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: User = Depends(get_current_active_user) # Add auth dependency
):
    # TODO: Add role-based access if these stats are sensitive for non-admin users
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
    current_user: User = Depends(get_current_active_user), # Add auth dependency
    skip: int = Query(0, ge=0, description="跳過的活動數量"),
    limit: int = Query(20, ge=1, le=100, description="返回的活動數量上限"),
    user_id: Optional[str] = Query(None, description="篩選特定用戶的活動 (目前僅限當前用戶)"),
    # activity_types: Optional[List[str]] = Query(None, description="篩選特定類型的活動 (例如: document_uploaded, user_login)") # 暫時不實現複雜篩選
):
    user_id_to_filter: str
    if user_id:
        if user_id != str(current_user.id):
            # TODO: Add admin role check here in the future to allow admins to see other users' activities
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="無權查看其他使用者的活動"
            )
        user_id_to_filter = user_id
    else:
        user_id_to_filter = str(current_user.id)

    activities_list = await crud_dashboard.get_recent_activities(
        db=db, 
        skip=skip, 
        limit=limit, 
        user_id=user_id_to_filter # Use the validated/derived user_id
        # activity_types_filter=activity_types # 傳遞給CRUD層
    )
    total_count = await crud_dashboard.count_recent_activities(
        db=db,
        user_id=user_id_to_filter # Use the validated/derived user_id
        # activity_types_filter=activity_types
    )
    return RecentActivities(activities=activities_list, total_count=total_count, limit=limit, skip=skip) 