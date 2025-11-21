"""
聚類管理API端點
提供文檔動態聚類的相關功能
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, BackgroundTasks
from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import List, Optional

from app.db.mongodb_utils import get_db
from app.core.security import get_current_active_user
from app.core.logging_utils import log_event, LogLevel
from app.models.user_models import UserInDB
from app.models.clustering_models import ClusteringJobStatus, ClusterSummary
from app.models.document_models import Document
from app.models.response_models import BasicResponse
from app.services.external.clustering_service import ClusteringService

router = APIRouter()


@router.post("/trigger-hierarchical", response_model=ClusteringJobStatus, summary="手動觸發階層聚類")
async def trigger_hierarchical_clustering(
    request: Request,
    background_tasks: BackgroundTasks,
    force_recluster: bool = False,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    手動觸發當前用戶的階層聚類 (兩級結構)
    
    階層1 (Level 0 - 大類):
    - 例如: 超商、帳單、食品等
    - 使用較大的 min_cluster_size
    
    階層2 (Level 1 - 細分類):
    - 例如: 7-11、全家、水費、電費等
    - 對每個大類內部再次聚類
    
    Args:
        force_recluster: 是否強制重新聚類已聚類的文檔
    
    Returns:
        ClusteringJobStatus: 聚類任務狀態
    """
    request_id = request.state.request_id if hasattr(request.state, 'request_id') else None
    
    await log_event(
        db=db,
        level=LogLevel.INFO,
        message=f"用戶 {current_user.username} 手動觸發階層聚類",
        source="api.clustering.trigger_hierarchical",
        user_id=str(current_user.id),
        request_id=request_id,
        details={"force_recluster": force_recluster}
    )
    
    try:
        clustering_service = ClusteringService()
        
        # 在後台任務中執行階層聚類
        async def run_hierarchical_clustering():
            try:
                await clustering_service.run_hierarchical_clustering(
                    db, current_user.id, force_recluster
                )
            except Exception as e:
                await log_event(
                    db=db,
                    level=LogLevel.ERROR,
                    message=f"階層聚類任務失敗: {str(e)}",
                    source="api.clustering.background_task",
                    user_id=str(current_user.id),
                    request_id=request_id
                )
        
        # 添加到後台任務
        background_tasks.add_task(run_hierarchical_clustering)
        
        # 立即返回初始狀態
        job_status = ClusteringJobStatus(
            owner_id=current_user.id,
            status="running"
        )
        
        return job_status
        
    except Exception as e:
        await log_event(
            db=db,
            level=LogLevel.ERROR,
            message=f"觸發階層聚類失敗: {str(e)}",
            source="api.clustering.trigger_hierarchical",
            user_id=str(current_user.id),
            request_id=request_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"觸發階層聚類失敗: {str(e)}"
        )


@router.post("/trigger", response_model=ClusteringJobStatus, summary="手動觸發聚類")
async def trigger_clustering_manual(
    request: Request,
    background_tasks: BackgroundTasks,
    force_recluster: bool = False,
    include_all_vectorized: bool = True,  # 默認包含所有已向量化的文檔
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    手動觸發當前用戶的文檔聚類
    
    Args:
        force_recluster: 是否強制重新聚類已聚類的文檔
        include_all_vectorized: 是否包含所有已向量化的文檔(默認True,推薦用於初次聚類)
    
    Returns:
        ClusteringJobStatus: 聚類任務狀態
    """
    request_id = request.state.request_id if hasattr(request.state, 'request_id') else None
    
    await log_event(
        db=db,
        level=LogLevel.INFO,
        message=f"用戶 {current_user.username} 手動觸發聚類",
        source="api.clustering.trigger",
        user_id=str(current_user.id),
        request_id=request_id,
        details={"force_recluster": force_recluster, "include_all_vectorized": include_all_vectorized}
    )
    
    try:
        clustering_service = ClusteringService()
        
        # 在後台任務中執行聚類
        async def run_clustering():
            try:
                await clustering_service.run_clustering_for_user(
                    db, current_user.id, force_recluster, include_all_vectorized
                )
            except Exception as e:
                await log_event(
                    db=db,
                    level=LogLevel.ERROR,
                    message=f"後台聚類任務失敗: {str(e)}",
                    source="api.clustering.background_task.error",
                    user_id=str(current_user.id),
                    details={"error": str(e)}
                )
        
        background_tasks.add_task(run_clustering)
        
        # 返回初始任務狀態
        job_status = ClusteringJobStatus(
            owner_id=current_user.id,
            status="running",
            total_documents=0,
            processed_documents=0
        )
        
        return job_status
        
    except Exception as e:
        await log_event(
            db=db,
            level=LogLevel.ERROR,
            message=f"觸發聚類失敗: {str(e)}",
            source="api.clustering.trigger.error",
            user_id=str(current_user.id),
            request_id=request_id,
            details={"error": str(e)}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"觸發聚類失敗: {str(e)}"
        )


@router.get("/status", response_model=Optional[ClusteringJobStatus], summary="獲取聚類狀態")
async def get_clustering_status(
    request: Request,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    獲取當前用戶的最新聚類任務狀態
    
    Returns:
        ClusteringJobStatus: 最新的聚類任務狀態,如果不存在則返回None
    """
    request_id = request.state.request_id if hasattr(request.state, 'request_id') else None
    
    try:
        clustering_service = ClusteringService()
        job_status = await clustering_service.get_latest_job_status(db, current_user.id)
        
        await log_event(
            db=db,
            level=LogLevel.DEBUG,
            message=f"用戶 {current_user.username} 查詢聚類狀態",
            source="api.clustering.status",
            user_id=str(current_user.id),
            request_id=request_id
        )
        
        return job_status
        
    except Exception as e:
        await log_event(
            db=db,
            level=LogLevel.ERROR,
            message=f"獲取聚類狀態失敗: {str(e)}",
            source="api.clustering.status.error",
            user_id=str(current_user.id),
            request_id=request_id,
            details={"error": str(e)}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"獲取聚類狀態失敗: {str(e)}"
        )


@router.get("/clusters", response_model=List[ClusterSummary], summary="獲取聚類列表")
async def list_user_clusters(
    request: Request,
    level: Optional[int] = None,  # None=全部, 0=僅大類, 1=僅子類
    include_subclusters: bool = True,  # 是否包含子聚類的詳細信息
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    獲取當前用戶的所有聚類
    
    Args:
        level: 過濾層級 (None=全部, 0=僅大類, 1=僅子類)
        include_subclusters: 是否在結果中包含子聚類的完整信息
    
    Returns:
        List[ClusterSummary]: 聚類摘要列表
    """
    request_id = request.state.request_id if hasattr(request.state, 'request_id') else None
    
    try:
        clustering_service = ClusteringService()
        clusters = await clustering_service.get_user_clusters(db, current_user.id)
        
        # 按層級過濾
        if level is not None:
            clusters = [c for c in clusters if c.level == level]
        
        # 如果需要包含子聚類的完整信息
        if include_subclusters:
            # 為每個大類聚類填充子聚類信息
            cluster_dict = {c.cluster_id: c for c in clusters}
            
            for cluster in clusters:
                if cluster.level == 0 and cluster.subclusters:
                    # 填充子聚類摘要
                    subcluster_summaries = []
                    for subcluster_id in cluster.subclusters:
                        if subcluster_id in cluster_dict:
                            subcluster_summaries.append(cluster_dict[subcluster_id])
                    
                    if subcluster_summaries:
                        cluster.subcluster_summaries = subcluster_summaries
        
        # 如果只要大類,過濾掉孤立的子類
        if level == 0:
            clusters = [c for c in clusters if c.level == 0]
        
        await log_event(
            db=db,
            level=LogLevel.INFO,
            message=f"用戶 {current_user.username} 獲取聚類列表",
            source="api.clustering.list",
            user_id=str(current_user.id),
            request_id=request_id,
            details={"cluster_count": len(clusters), "level_filter": level}
        )
        
        return clusters
        
    except Exception as e:
        await log_event(
            db=db,
            level=LogLevel.ERROR,
            message=f"獲取聚類列表失敗: {str(e)}",
            source="api.clustering.list.error",
            user_id=str(current_user.id),
            request_id=request_id,
            details={"error": str(e)}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"獲取聚類列表失敗: {str(e)}"
        )


@router.get("/clusters/{cluster_id}/documents", response_model=List[Document], summary="獲取聚類中的文檔")
async def get_cluster_documents(
    cluster_id: str,
    request: Request,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    獲取特定聚類中的所有文檔
    
    Args:
        cluster_id: 聚類ID
    
    Returns:
        List[Document]: 文檔列表
    """
    request_id = request.state.request_id if hasattr(request.state, 'request_id') else None
    
    try:
        clustering_service = ClusteringService()
        documents = await clustering_service.get_cluster_documents(
            db, cluster_id, current_user.id
        )
        
        await log_event(
            db=db,
            level=LogLevel.INFO,
            message=f"用戶 {current_user.username} 獲取聚類 {cluster_id} 的文檔",
            source="api.clustering.get_documents",
            user_id=str(current_user.id),
            request_id=request_id,
            details={"cluster_id": cluster_id, "document_count": len(documents)}
        )
        
        return documents
        
    except Exception as e:
        await log_event(
            db=db,
            level=LogLevel.ERROR,
            message=f"獲取聚類文檔失敗: {str(e)}",
            source="api.clustering.get_documents.error",
            user_id=str(current_user.id),
            request_id=request_id,
            details={"cluster_id": cluster_id, "error": str(e)}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"獲取聚類文檔失敗: {str(e)}"
        )


@router.delete("/clusters/{cluster_id}", response_model=BasicResponse, summary="刪除聚類")
async def delete_cluster(
    cluster_id: str,
    request: Request,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    刪除特定聚類
    
    注意: 這只會刪除聚類本身,不會刪除文檔。
    文檔的 clustering_status 會被設為 "pending"。
    
    Args:
        cluster_id: 聚類ID
    
    Returns:
        BasicResponse: 操作結果
    """
    request_id = request.state.request_id if hasattr(request.state, 'request_id') else None
    
    try:
        # 驗證聚類是否屬於當前用戶
        cluster = await db["clusters"].find_one({
            "cluster_id": cluster_id,
            "owner_id": current_user.id
        })
        
        if not cluster:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="聚類不存在或無權訪問"
            )
        
        # 刪除聚類
        delete_result = await db["clusters"].delete_one({
            "cluster_id": cluster_id,
            "owner_id": current_user.id
        })
        
        if delete_result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="刪除聚類失敗"
            )
        
        # 將屬於該聚類的文檔狀態重置為 pending
        update_result = await db["documents"].update_many(
            {
                "owner_id": current_user.id,
                "cluster_info.cluster_id": cluster_id
            },
            {
                "$set": {
                    "clustering_status": "pending",
                    "cluster_info": None
                }
            }
        )
        
        await log_event(
            db=db,
            level=LogLevel.INFO,
            message=f"用戶 {current_user.username} 刪除聚類 {cluster_id}",
            source="api.clustering.delete",
            user_id=str(current_user.id),
            request_id=request_id,
            details={
                "cluster_id": cluster_id,
                "cluster_name": cluster.get("cluster_name"),
                "documents_affected": update_result.modified_count
            }
        )
        
        return BasicResponse(
            success=True,
            message=f"聚類已刪除,{update_result.modified_count} 個文檔已重置為待分類狀態"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        await log_event(
            db=db,
            level=LogLevel.ERROR,
            message=f"刪除聚類失敗: {str(e)}",
            source="api.clustering.delete.error",
            user_id=str(current_user.id),
            request_id=request_id,
            details={"cluster_id": cluster_id, "error": str(e)}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"刪除聚類失敗: {str(e)}"
        )


@router.delete("/clusters", response_model=BasicResponse, summary="刪除所有聚類")
async def delete_all_clusters(
    request: Request,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    刪除當前用戶的所有聚類，並將所有文檔重置為待分類狀態
    
    注意: 這是破壞性操作，會刪除所有聚類數據，但不會刪除文檔本身
    
    Returns:
        BasicResponse: 操作結果
    """
    request_id = request.state.request_id if hasattr(request.state, 'request_id') else None
    
    try:
        # 獲取當前用戶的所有聚類數量
        clusters_count = await db["clusters"].count_documents({
            "owner_id": current_user.id
        })
        
        if clusters_count == 0:
            return BasicResponse(
                success=True,
                message="沒有聚類需要刪除"
            )
        
        # 刪除所有聚類
        delete_result = await db["clusters"].delete_many({
            "owner_id": current_user.id
        })
        
        # 將所有文檔重置為 pending（待分類）
        # 用戶手動刪除所有聚類，表示要完全重置分類狀態
        # 所有文檔歸到"待分類"，包括之前因為數量不足而被標記為 excluded 的文檔
        # 這樣用戶可以完全重新開始分類流程
        update_result = await db["documents"].update_many(
            {
                "owner_id": current_user.id,
                "clustering_status": {"$in": ["clustered", "excluded"]}
            },
            {
                "$set": {
                    "clustering_status": "pending",
                    "cluster_info": None
                }
            }
        )
        
        await log_event(
            db=db,
            level=LogLevel.INFO,
            message=f"用戶 {current_user.username} 刪除所有聚類",
            source="api.clustering.delete_all",
            user_id=str(current_user.id),
            request_id=request_id,
            details={
                "clusters_deleted": delete_result.deleted_count,
                "documents_reset": update_result.modified_count
            }
        )
        
        return BasicResponse(
            success=True,
            message=f"已刪除 {delete_result.deleted_count} 個聚類，{update_result.modified_count} 個文檔已重置為待分類狀態"
        )
        
    except Exception as e:
        await log_event(
            db=db,
            level=LogLevel.ERROR,
            message=f"刪除所有聚類失敗: {str(e)}",
            source="api.clustering.delete_all.error",
            user_id=str(current_user.id),
            request_id=request_id,
            details={"error": str(e)}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"刪除所有聚類失敗: {str(e)}"
        )


@router.get("/tree", response_model=dict, summary="獲取結構化聚類樹")
async def get_clusters_tree(
    request: Request,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    獲取結構化的聚類樹（三層結構）
    
    Returns:
        dict: {
            "main_clusters": [...],  # 主要聚類
            "small_clusters": [...],  # 小型聚類（其他：XXX）
            "unclustered_count": int,  # 未分類文檔數量
            "total_clusters": int
        }
    """
    request_id = request.state.request_id if hasattr(request.state, 'request_id') else None
    
    try:
        clustering_service = ClusteringService()
        tree = await clustering_service.get_structured_clusters_tree(db, current_user.id)
        
        await log_event(
            db=db,
            level=LogLevel.INFO,
            message=f"用戶 {current_user.username} 獲取結構化聚類樹",
            source="api.clustering.tree",
            user_id=str(current_user.id),
            request_id=request_id,
            details={
                "main_clusters": len(tree["main_clusters"]),
                "small_clusters": len(tree["small_clusters"]),
                "unclustered": tree["unclustered_count"]
            }
        )
        
        return tree
        
    except Exception as e:
        await log_event(
            db=db,
            level=LogLevel.ERROR,
            message=f"獲取聚類樹失敗: {str(e)}",
            source="api.clustering.tree.error",
            user_id=str(current_user.id),
            request_id=request_id,
            details={"error": str(e)}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"獲取聚類樹失敗: {str(e)}"
        )


@router.get("/statistics", response_model=dict, summary="獲取聚類統計信息")
async def get_clustering_statistics(
    request: Request,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    獲取當前用戶的聚類統計信息
    
    Returns:
        dict: 統計信息,包括總聚類數、總文檔數、待分類文檔數等
    """
    request_id = request.state.request_id if hasattr(request.state, 'request_id') else None
    
    try:
        # 獲取總聚類數
        total_clusters = await db["clusters"].count_documents({"owner_id": current_user.id})
        
        # 獲取各狀態的文檔數
        pending_docs = await db["documents"].count_documents({
            "owner_id": current_user.id,
            "clustering_status": "pending"
        })
        
        clustered_docs = await db["documents"].count_documents({
            "owner_id": current_user.id,
            "clustering_status": "clustered"
        })
        
        excluded_docs = await db["documents"].count_documents({
            "owner_id": current_user.id,
            "clustering_status": "excluded"
        })
        
        statistics = {
            "total_clusters": total_clusters,
            "pending_documents": pending_docs,
            "clustered_documents": clustered_docs,
            "excluded_documents": excluded_docs,
            "total_documents": pending_docs + clustered_docs + excluded_docs,
            "clustering_coverage": round(
                (clustered_docs / (pending_docs + clustered_docs + excluded_docs) * 100)
                if (pending_docs + clustered_docs + excluded_docs) > 0 else 0,
                2
            )
        }
        
        await log_event(
            db=db,
            level=LogLevel.DEBUG,
            message=f"用戶 {current_user.username} 獲取聚類統計",
            source="api.clustering.statistics",
            user_id=str(current_user.id),
            request_id=request_id
        )
        
        return statistics
        
    except Exception as e:
        await log_event(
            db=db,
            level=LogLevel.ERROR,
            message=f"獲取聚類統計失敗: {str(e)}",
            source="api.clustering.statistics.error",
            user_id=str(current_user.id),
            request_id=request_id,
            details={"error": str(e)}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"獲取聚類統計失敗: {str(e)}"
        )


@router.get("/folder-order", response_model=List[str], summary="獲取資料夾顯示順序")
async def get_folder_display_order(
    request: Request,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    獲取當前用戶自定義的資料夾顯示順序
    
    Returns:
        List[str]: 資料夾ID陣列（按顯示順序排列）
    """
    request_id = request.state.request_id if hasattr(request.state, 'request_id') else None
    
    try:
        # 從資料庫讀取用戶的資料夾排序設置
        folder_order_doc = await db.user_preferences.find_one({
            "_id": f"folder_order_{current_user.id}"
        })
        
        if folder_order_doc and "folder_order" in folder_order_doc:
            folder_order = folder_order_doc["folder_order"]
            
            await log_event(
                db=db,
                level=LogLevel.DEBUG,
                message=f"用戶 {current_user.username} 獲取資料夾排序",
                source="api.clustering.get_folder_order",
                user_id=str(current_user.id),
                request_id=request_id,
                details={"folder_count": len(folder_order)}
            )
            
            return folder_order
        else:
            # 如果沒有自定義排序，返回空陣列
            await log_event(
                db=db,
                level=LogLevel.DEBUG,
                message=f"用戶 {current_user.username} 沒有自定義資料夾排序",
                source="api.clustering.get_folder_order",
                user_id=str(current_user.id),
                request_id=request_id
            )
            return []
            
    except Exception as e:
        await log_event(
            db=db,
            level=LogLevel.ERROR,
            message=f"獲取資料夾排序失敗: {str(e)}",
            source="api.clustering.get_folder_order.error",
            user_id=str(current_user.id),
            request_id=request_id,
            details={"error": str(e)}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"獲取資料夾排序失敗: {str(e)}"
        )


@router.post("/folder-order", response_model=BasicResponse, summary="保存資料夾顯示順序")
async def save_folder_display_order(
    folder_order: List[str],
    request: Request,
    current_user: UserInDB = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    保存當前用戶自定義的資料夾顯示順序
    
    Args:
        folder_order: 資料夾ID陣列（按顯示順序排列）
    
    Returns:
        BasicResponse: 保存結果
    """
    request_id = request.state.request_id if hasattr(request.state, 'request_id') else None
    
    try:
        from datetime import datetime, UTC
        
        # 保存到資料庫
        result = await db.user_preferences.update_one(
            {"_id": f"folder_order_{current_user.id}"},
            {
                "$set": {
                    "owner_id": current_user.id,
                    "folder_order": folder_order,
                    "updated_at": datetime.now(UTC)
                },
                "$setOnInsert": {
                    "created_at": datetime.now(UTC)
                }
            },
            upsert=True
        )
        
        await log_event(
            db=db,
            level=LogLevel.INFO,
            message=f"用戶 {current_user.username} 保存資料夾排序",
            source="api.clustering.save_folder_order",
            user_id=str(current_user.id),
            request_id=request_id,
            details={
                "folder_count": len(folder_order),
                "folder_ids": folder_order[:5]  # 只記錄前5個
            }
        )
        
        return BasicResponse(
            success=True,
            message=f"資料夾排序已保存（共{len(folder_order)}個資料夾）"
        )
        
    except Exception as e:
        await log_event(
            db=db,
            level=LogLevel.ERROR,
            message=f"保存資料夾排序失敗: {str(e)}",
            source="api.clustering.save_folder_order.error",
            user_id=str(current_user.id),
            request_id=request_id,
            details={"error": str(e)}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"保存資料夾排序失敗: {str(e)}"
        )
