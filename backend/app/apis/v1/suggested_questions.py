"""
建議問題 API 端點
"""

import logging
import asyncio
from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import List, Dict, Any

from app.dependencies import get_db
from app.core.security import get_current_user
from app.models.suggested_question_models import (
    GenerateQuestionsRequest,
    GenerateQuestionsResponse,
    GetSuggestedQuestionsResponse,
    SuggestedQuestion
)
from app.models.background_task_models import TaskType, TaskStatus
from app.services.ai.suggested_questions_generator import suggested_questions_generator
from app.services.background_task_manager import background_task_manager
from app.crud import crud_suggested_questions
from app.core.logging_utils import AppLogger

logger = AppLogger(__name__, level=logging.INFO).get_logger()

router = APIRouter()


@router.get(
    "/suggested-questions",
    response_model=GetSuggestedQuestionsResponse,
    summary="獲取建議問題",
    description="獲取隨機的建議問題（不重複）"
)
async def get_suggested_questions(
    count: int = 4,
    user_id: str = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    獲取建議問題
    
    - **count**: 需要的問題數量（默認 4）
    
    返回：
    - 隨機選擇的問題列表
    - 自動排除最近 7 天內使用過的問題
    """
    try:
        
        logger.info(f"用戶 {user_id} 請求 {count} 個建議問題")
        
        # 獲取隨機問題
        questions = await crud_suggested_questions.get_random_questions(
            db=db,
            user_id=user_id,
            count=count,
            exclude_recently_used=True,
            recent_use_days=7
        )
        
        return GetSuggestedQuestionsResponse(
            questions=questions,
            total=len(questions)
        )
        
    except Exception as e:
        logger.error(f"獲取建議問題失敗: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"獲取建議問題失敗: {str(e)}"
        )


@router.post(
    "/suggested-questions/generate",
    summary="生成建議問題（後台任務）",
    description="為當前用戶生成建議問題，返回任務ID用於查詢進度"
)
async def generate_suggested_questions(
    request: GenerateQuestionsRequest,
    user_id: str = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    生成建議問題（後台任務）
    
    - **force_regenerate**: 是否強制重新生成（即使已有問題）
    - **questions_per_category**: 每個分類生成的問題數量
    - **include_cross_category**: 是否包含跨分類問題
    
    返回：
    - task_id: 任務ID，用於查詢進度
    """
    try:
        logger.info(f"開始為用戶 {user_id} 創建問題生成任務")
        
        # 預先檢查前置條件
        from uuid import UUID
        owner_uuid = UUID(user_id)
        from app.crud import crud_documents
        documents = await crud_documents.get_documents(db, owner_id=owner_uuid, limit=10000)
        
        if len(documents) < 20:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"文檔數量不足（目前 {len(documents)} 個，需要至少 20 個），請先上傳更多文檔"
            )
        
        # 檢查聚類
        from app.services.ai.suggested_questions_generator import suggested_questions_generator as gen
        clusters = await gen._get_user_clusters(db, user_id)
        if not clusters:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="尚未執行智能分類，請先執行「智能分類」功能後再生成問題"
            )
        
        # 創建後台任務
        task_id = await background_task_manager.create_task(
            db=db,
            task_type=TaskType.QUESTION_GENERATION,
            user_id=user_id,
            total_items=len(clusters) + 2  # clusters + cross-category + time-based
        )
        
        # 定義進度回調
        async def progress_callback(progress: int, step: str, completed: int):
            await background_task_manager.update_task_progress(
                db=db,
                task_id=task_id,
                progress=progress,
                current_step=step,
                completed_items=completed
            )
        
        # 定義後台任務執行函數
        async def run_generation_task():
            try:
                await background_task_manager.update_task_status(
                    db=db,
                    task_id=task_id,
                    status=TaskStatus.RUNNING
                )
                
                questions = await suggested_questions_generator.generate_questions_for_user(
                    db=db,
                    user_id=user_id,
                    questions_per_category=request.questions_per_category,
                    include_cross_category=request.include_cross_category,
                    force_regenerate=request.force_regenerate,
                    progress_callback=progress_callback
                )
                
                await background_task_manager.set_task_result(
                    db=db,
                    task_id=task_id,
                    result={
                        "total_questions": len(questions),
                        "questions": [q.model_dump() for q in questions[:10]]  # 只返回前10個作為預覽
                    }
                )
                
                await background_task_manager.update_task_status(
                    db=db,
                    task_id=task_id,
                    status=TaskStatus.COMPLETED
                )
                
                logger.info(f"任務 {task_id} 完成，生成了 {len(questions)} 個問題")
                
            except Exception as e:
                logger.error(f"任務 {task_id} 失敗: {e}", exc_info=True)
                await background_task_manager.update_task_status(
                    db=db,
                    task_id=task_id,
                    status=TaskStatus.FAILED,
                    error_message=str(e)
                )
        
        # 啟動後台任務
        background_task_manager.start_background_task(task_id, run_generation_task())
        
        return {
            "success": True,
            "message": "問題生成任務已啟動",
            "task_id": task_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"創建生成任務失敗: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"創建生成任務失敗: {str(e)}"
        )


@router.get(
    "/suggested-questions/task/{task_id}",
    summary="查詢任務狀態",
    description="查詢問題生成任務的進度和狀態"
)
async def get_task_status(
    task_id: str,
    user_id: str = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    查詢任務狀態
    
    返回任務的當前狀態、進度和結果
    """
    try:
        task = await background_task_manager.get_task_status(db, task_id)
        
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="任務不存在"
            )
        
        # 驗證任務所有權
        if task.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="無權訪問此任務"
            )
        
        return {
            "task_id": task.task_id,
            "status": task.status.value,
            "progress": task.progress,
            "current_step": task.current_step,
            "total_items": task.total_items,
            "completed_items": task.completed_items,
            "result": task.result,
            "error_message": task.error_message
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查詢任務狀態失敗: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"查詢任務狀態失敗: {str(e)}"
        )


@router.put(
    "/suggested-questions/{question_id}/use",
    summary="標記問題已使用",
    description="標記某個問題已被使用"
)
async def mark_question_used(
    question_id: str,
    user_id: str = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    標記問題已使用
    
    - **question_id**: 問題ID
    
    這會更新問題的 last_used_at 和 use_count，
    使得該問題在未來一段時間內不會再被隨機選中
    """
    try:
        
        success = await crud_suggested_questions.mark_question_used(
            db=db,
            user_id=user_id,
            question_id=question_id
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="問題不存在或更新失敗"
            )
        
        return {"success": True, "message": "已標記問題為已使用"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"標記問題使用失敗: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"標記問題使用失敗: {str(e)}"
        )


@router.get(
    "/suggested-questions/all",
    response_model=GetSuggestedQuestionsResponse,
    summary="獲取所有建議問題",
    description="獲取用戶的所有建議問題（不過濾）"
)
async def get_all_suggested_questions(
    user_id: str = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    獲取所有建議問題
    
    返回用戶的完整問題庫
    """
    try:
        
        questions_doc = await crud_suggested_questions.get_user_questions(db, user_id)
        
        if not questions_doc:
            return GetSuggestedQuestionsResponse(
                questions=[],
                total=0
            )
        
        return GetSuggestedQuestionsResponse(
            questions=questions_doc.questions,
            total=len(questions_doc.questions)
        )
        
    except Exception as e:
        logger.error(f"獲取所有建議問題失敗: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"獲取所有建議問題失敗: {str(e)}"
        )


@router.delete(
    "/suggested-questions",
    summary="刪除所有建議問題",
    description="刪除用戶的所有建議問題"
)
async def delete_all_suggested_questions(
    user_id: str = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    刪除所有建議問題
    
    清空用戶的問題庫
    """
    try:
        
        success = await crud_suggested_questions.delete_user_questions(db, user_id)
        
        if not success:
            return {"success": False, "message": "沒有問題可刪除"}
        
        return {"success": True, "message": "已刪除所有建議問題"}
        
    except Exception as e:
        logger.error(f"刪除建議問題失敗: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"刪除建議問題失敗: {str(e)}"
        )


@router.get(
    "/suggested-questions/debug/clusters",
    summary="調試：檢查用戶聚類狀態",
    description="檢查用戶是否有聚類信息（調試用）"
)
async def debug_check_clusters(
    user_id: str = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    檢查用戶的聚類狀態
    
    返回：
    - 聚類數量
    - 文檔數量
    - 聚類詳情
    """
    try:
        from uuid import UUID
        from app.crud import crud_documents
        
        # 檢查聚類
        clusters_collection = db["clusters"]
        owner_uuid = UUID(user_id)
        
        # 嘗試 UUID 查詢
        cursor_uuid = clusters_collection.find({"owner_id": owner_uuid})
        clusters_uuid = await cursor_uuid.to_list(length=100)
        
        # 嘗試字符串查詢
        cursor_str = clusters_collection.find({"owner_id": user_id})
        clusters_str = await cursor_str.to_list(length=100)
        
        # 檢查文檔
        documents = await crud_documents.get_documents(db, owner_id=owner_uuid, limit=10000)
        
        # 檢查聚類任務狀態
        clustering_jobs = db["clustering_jobs"]
        latest_job = await clustering_jobs.find_one(
            {"owner_id": owner_uuid},
            sort=[("started_at", -1)]
        )
        
        return {
            "user_id": user_id,
            "clusters_found_by_uuid": len(clusters_uuid),
            "clusters_found_by_string": len(clusters_str),
            "total_documents": len(documents),
            "clusters_detail": [
                {
                    "cluster_id": str(c.get("_id", c.get("cluster_id", ""))),
                    "cluster_name": c.get("cluster_name", ""),
                    "document_count": c.get("document_count", 0),
                    "owner_id_type": type(c.get("owner_id")).__name__,
                    "owner_id_value": str(c.get("owner_id", ""))
                }
                for c in (clusters_uuid or clusters_str)[:5]  # 只顯示前5個
            ],
            "latest_clustering_job": {
                "status": latest_job.get("status") if latest_job else None,
                "clusters_created": latest_job.get("clusters_created") if latest_job else 0,
                "completed_at": str(latest_job.get("completed_at")) if latest_job and latest_job.get("completed_at") else None
            } if latest_job else None
        }
        
    except Exception as e:
        logger.error(f"調試檢查失敗: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"調試檢查失敗: {str(e)}"
        )

