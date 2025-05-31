from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import List, Optional, Dict
import uuid

from pydantic import BaseModel
from app.db.mongodb_utils import get_db
from app.core.security import get_current_active_user
from app.models.user_models import User
from app.models.vector_models import SemanticSearchRequest, SemanticSearchResult, BatchProcessRequest
from app.models.response_models import BasicResponse
from app.services.semantic_summary_service import semantic_summary_service
from app.services.embedding_service import embedding_service
from app.dependencies import get_vector_db_service
from app.core.logging_utils import AppLogger
import logging
from app.crud.crud_documents import get_document_by_id, update_document_vector_status
from app.models.document_models import VectorStatus

logger = AppLogger(__name__, level=logging.DEBUG).get_logger()

router = APIRouter()

@router.get("/stats")
async def get_vector_db_stats(
    current_user: User = Depends(get_current_active_user)
):
    """獲取向量資料庫統計信息 - 需要用戶認證"""
    try:
        logger.info(f"用戶 {current_user.username} 請求向量資料庫統計")
        vector_db_service_instance = get_vector_db_service()
        
        # 只獲取當前狀態，不觸發重量級操作
        stats = await vector_db_service_instance.get_collection_stats()
        
        # 添加Embedding模型信息（包含真實的加載狀態）
        embedding_info = embedding_service.get_model_info()
        stats["embedding_model"] = embedding_info
        
        # 添加初始化建議
        if not embedding_info["model_loaded"]:
            stats["initialization_required"] = True
            stats["initialization_message"] = "模型尚未加載，請使用初始化功能啟動向量數據庫"
        
        if 'error' in stats and '集合未初始化' in stats.get('error', ''):
            stats["collection_initialization_required"] = True
        
        return stats
        
    except Exception as e:
        logger.error(f"獲取向量資料庫統計失敗: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"獲取統計信息失敗: {str(e)}"
        )

@router.post("/initialize")
async def initialize_vector_database(
    current_user: User = Depends(get_current_active_user)
):
    """初始化向量資料庫（創建集合和索引） - 需要用戶認證"""
    try:
        logger.info(f"用戶 {current_user.username} 開始初始化向量資料庫")
        
        # 確保模型已加載
        if not embedding_service._model_loaded:
            logger.info("Embedding模型尚未加載，正在進行初始化...")
            embedding_service._load_model()
        
        # 獲取向量維度
        vector_dimension = embedding_service.vector_dimension
        
        if not vector_dimension:
            raise HTTPException(
                status_code=500,
                detail="無法獲取Embedding模型的向量維度，請確保模型已正確加載"
            )
        
        # 創建集合
        vector_db_service_instance = get_vector_db_service()
        vector_db_service_instance.create_collection(vector_dimension)
        
        logger.info(f"用戶 {current_user.username} 向量資料庫初始化成功")
        
        return JSONResponse(
            content={
                "message": "向量資料庫初始化成功",
                "vector_dimension": vector_dimension,
                "collection_name": vector_db_service_instance.collection_name,
                "status": "initialized"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"初始化向量資料庫失敗: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"初始化向量資料庫失敗: {str(e)}"
        )

@router.delete("/document/{document_id}")
async def delete_document_from_vector_db(
    document_id: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """從向量資料庫中刪除文檔 - 需要用戶認證"""
    try:
        logger.info(f"用戶 {current_user.username} 從向量資料庫刪除文檔: {document_id}")
        
        doc_id_as_uuid: Optional[uuid.UUID] = None
        try:
            doc_id_as_uuid = uuid.UUID(document_id)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"無效的文檔 ID 格式: {document_id}")
            
        document = await get_document_by_id(db, doc_id_as_uuid)
        
        if not document:
            raise HTTPException(
                status_code=404,
                detail=f"文檔不存在: {document_id}"
            )
        
        if document.owner_id != current_user.id:
            raise HTTPException(
                status_code=403,
                detail="您沒有權限刪除此文檔"
            )
        
        vector_db_service_instance = get_vector_db_service()
        # 實際從向量數據庫刪除
        delete_success_from_chroma = vector_db_service_instance.delete_by_document_id(document_id)
        
        if delete_success_from_chroma:
            # 更新 MongoDB 中的 vector_status
            updated_doc = await update_document_vector_status(
                db, doc_id_as_uuid, VectorStatus.NOT_VECTORIZED
            )
            if not updated_doc:
                # 即使 vector_status 更新失敗，也可能認為ChromaDB刪除成功了。記錄一個警告。
                logger.warning(f"已從ChromaDB刪除文檔 {document_id} 的向量，但在MongoDB中更新vector_status失敗。")
                # 根據業務需求，這裡可以選擇是否拋出錯誤或仍返回成功
                # 為了前端一致性，如果ChromaDB刪除成功，我們仍可返回成功，但日誌應記錄問題。

            return JSONResponse(
                content={
                    "message": f"已從向量資料庫刪除文檔: {document_id}，狀態已更新",
                    "document_id": document_id,
                    "status": "deleted_and_status_updated" # 或者更精確的狀態
                }
            )
        else:
            # 如果ChromaDB刪除失敗，則認為整個操作失敗
            raise HTTPException(
                status_code=500,
                detail="從向量數據庫刪除向量操作失敗"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"刪除文檔向量失敗: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"刪除文檔向量失敗: {str(e)}"
        )

@router.post("/process-document/{document_id}")
async def process_document_to_vector(
    document_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    將單個文檔處理並添加到向量資料庫 - 需要用戶認證
    
    背景任務處理：
    1. 生成語義摘要
    2. 向量化
    3. 存儲到向量資料庫
    """
    try:
        logger.info(f"用戶 {current_user.username} 開始處理文檔到向量資料庫: {document_id}")
        logger.info(f"API - process_document_to_vector: Received document_id string from path: '{document_id}', type: {type(document_id)}")
        
        # 獲取文檔並檢查所有權
        from app.crud.crud_documents import get_document_by_id
        
        doc_id_as_uuid_for_crud: Optional[uuid.UUID] = None
        try:
            doc_id_as_uuid_for_crud = uuid.UUID(document_id)
            logger.info(f"API - process_document_to_vector: Successfully converted string ID '{document_id}' to UUID: {doc_id_as_uuid_for_crud}")
        except ValueError as e_uuid:
            logger.error(f"API - process_document_to_vector: Invalid UUID string received in path: '{document_id}' - Error: {e_uuid}")
            raise HTTPException(status_code=400, detail=f"無效的文檔 ID 格式: {document_id}")

        logger.info(f"API - process_document_to_vector: Calling crud_documents.get_document_by_id with UUID: {doc_id_as_uuid_for_crud}")
        document = await get_document_by_id(db, doc_id_as_uuid_for_crud)
        
        if not document:
            logger.warning(f"API - process_document_to_vector: crud_documents.get_document_by_id returned None for original string ID '{document_id}' (UUID: {doc_id_as_uuid_for_crud})")
            raise HTTPException(
                status_code=404,
                detail=f"文檔不存在: {document_id}"
            )
        
        if document.owner_id != current_user.id:
            raise HTTPException(
                status_code=403,
                detail="您沒有權限處理此文檔"
            )
        
        # 添加背景任務
        background_tasks.add_task(
            semantic_summary_service.process_document_for_vector_db,
            db,
            document
        )
        
        return JSONResponse(
            status_code=202,
            content={
                "message": f"文檔 {document_id} 已加入向量化處理隊列",
                "document_id": document_id,
                "status": "processing"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"處理文檔到向量資料庫失敗: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"處理文檔失敗: {str(e)}"
        )

@router.post("/batch-process")
async def batch_process_documents(
    request_body: BatchProcessRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    批量處理文檔到向量資料庫 - 需要用戶認證
    """
    document_ids_str_from_request = request_body.document_ids # 這是 List[str]
    try:
        logger.info(f"用戶 {current_user.username} 開始批量處理 {len(document_ids_str_from_request)} 個文檔到向量資料庫")
        
        from app.crud.crud_documents import get_document_by_id # 用於驗證
        
        valid_document_ids_for_processing = [] # 存儲通過驗證的文檔 ID 字符串
        
        for doc_id_str in document_ids_str_from_request:
            try:
                doc_uuid = uuid.UUID(doc_id_str) # 轉換為 UUID 以便查詢
            except ValueError:
                logger.warning(f"無效的文檔 ID 格式: {doc_id_str}，跳過處理")
                continue

            document = await get_document_by_id(db, doc_uuid) # 使用 UUID 對象查詢驗證
            if document and document.owner_id == current_user.id:
                valid_document_ids_for_processing.append(doc_id_str) # 添加原始的、有效的字符串 ID
            else:
                logger.warning(f"文檔 {doc_id_str} (UUID: {doc_uuid}) 不存在或用戶無權限，跳過處理")
        
        if not valid_document_ids_for_processing:
            raise HTTPException(
                status_code=400,
                detail="沒有找到有效的文檔或您沒有處理權限"
            )
        
        # 背景任務現在接收 List[str]
        background_tasks.add_task(
            semantic_summary_service.batch_process_documents, # 直接調用原方法
            db,
            valid_document_ids_for_processing 
        )
        
        return JSONResponse(
            status_code=202,
            content={
                "message": f"已開始批量處理 {len(valid_document_ids_for_processing)} 個文檔",
                "document_count": len(valid_document_ids_for_processing),
                "skipped_count": len(document_ids_str_from_request) - len(valid_document_ids_for_processing),
                "status": "processing"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"批量處理文檔失敗: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"批量處理文檔失敗: {str(e)}"
        )

@router.post("/semantic-search", response_model=List[SemanticSearchResult])
async def semantic_search(
    request: SemanticSearchRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    語義搜索端點 - 需要用戶認證
    
    直接進行向量搜索，不包含LLM處理
    """
    try:
        logger.info(f"用戶 {current_user.username} 收到語義搜索請求: {request.query[:100]}")
        
        # 將查詢轉換為向量
        query_vector = embedding_service.encode_text(request.query)
        
        # 執行向量搜索，傳入 owner_id 進行過濾
        vector_db_service_instance = get_vector_db_service()
        results = vector_db_service_instance.search_similar_vectors(
            query_vector=query_vector,
            top_k=request.top_k,
            similarity_threshold=request.similarity_threshold,
            owner_id_filter=str(current_user.id)
        )
        
        logger.info(f"用戶 {current_user.username} 語義搜索完成，查詢: '{request.query}', 返回 {len(results)} 個結果 (已在服務層過濾)")
        return results
    except ValueError as ve:
        logger.error(f"語義搜索失敗 for user {current_user.username}: {ve}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"語義搜索失敗: {str(ve)}"
        )

class BatchDeleteRequest(BaseModel):
    document_ids: List[str]

@router.delete("/documents", response_model=BasicResponse, summary="批量從向量數據庫刪除文檔")
async def batch_delete_documents_from_vector_db(
    request_data: BatchDeleteRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """根據文檔 ID 列表，批量從向量資料庫中刪除文檔的向量，並更新其在MongoDB中的vector_status。"""
    logger.info(f"用戶 {current_user.username} 請求批量刪除向量，文檔IDs: {request_data.document_ids}")
    
    doc_ids_to_process_str: List[str] = request_data.document_ids
    authorized_doc_ids_to_delete_str: List[str] = []
    successfully_updated_status_ids_str: List[str] = []
    errors_info: List[Dict[str, str]] = []
    
    # 1. Verify ownership for each document ID
    for doc_id_str in doc_ids_to_process_str:
        try:
            doc_uuid = uuid.UUID(doc_id_str)
            document = await get_document_by_id(db, doc_uuid)
            if not document:
                errors_info.append({"id": doc_id_str, "error": "Document not found"})
                logger.warning(f"Batch delete vector: Document ID {doc_id_str} not found for user {current_user.username}.")
                continue
            if document.owner_id != current_user.id:
                errors_info.append({"id": doc_id_str, "error": "Forbidden"})
                logger.warning(f"Batch delete vector: User {current_user.username} attempted to delete vector for document {doc_id_str} they do not own.")
                continue
            authorized_doc_ids_to_delete_str.append(doc_id_str)
        except ValueError:
            errors_info.append({"id": doc_id_str, "error": "Invalid document ID format"})
            logger.warning(f"Batch delete vector: Invalid document ID format {doc_id_str} for user {current_user.username}.")
        except Exception as e_check:
            errors_info.append({"id": doc_id_str, "error": f"Error checking document: {str(e_check)}"})
            logger.error(f"Batch delete vector: Error checking document {doc_id_str} for user {current_user.username}: {e_check}", exc_info=True)

    if not authorized_doc_ids_to_delete_str:
        if errors_info: # If all IDs failed validation
             return BasicResponse(success=False, message="沒有有效的文檔ID可供處理，或無權限。", details={"errors": errors_info})
        raise HTTPException(status_code=400, detail="沒有提供有效的文檔ID進行刪除，或無權限操作。")

    # 2. Call service layer to delete from ChromaDB
    vector_db_service_instance = get_vector_db_service()
    chroma_delete_result = {"deleted_count": 0, "failed_ids": [], "errors": []} # Default structure
    try:
        if authorized_doc_ids_to_delete_str: # Only proceed if there are authorized IDs
            chroma_delete_result = await vector_db_service_instance.delete_by_document_ids(authorized_doc_ids_to_delete_str)
            logger.info(f"ChromaDB batch delete report for user {current_user.username}: Attempted {len(authorized_doc_ids_to_delete_str)}, Chroma reported {chroma_delete_result.get('deleted_count', 0)} deleted, {len(chroma_delete_result.get('failed_ids',[]))} failed internally in Chroma.")

        # IDs considered successfully processed by Chroma (either deleted or didn't exist there)
        processed_in_chroma_ids_str = [
            doc_id for doc_id in authorized_doc_ids_to_delete_str 
            if doc_id not in chroma_delete_result.get("failed_ids", [])
        ]

        # 3. Update MongoDB status for documents successfully processed by Chroma
        for doc_id_str in processed_in_chroma_ids_str:
            try:
                doc_uuid = uuid.UUID(doc_id_str)
                updated_doc = await update_document_vector_status(
                    db, doc_uuid, VectorStatus.NOT_VECTORIZED
                )
                if updated_doc:
                    successfully_updated_status_ids_str.append(doc_id_str)
                else:
                    logger.warning(f"Batch delete vector: Failed to update vector_status for doc {doc_id_str} (user {current_user.username}) in MongoDB (document not found or DB error).")
                    errors_info.append({"id": doc_id_str, "error": "Failed to update MongoDB status (document not found or DB error after Chroma deletion)."})
            except ValueError: # Should not happen if it passed initial UUID check
                logger.error(f"Batch delete vector: Invalid UUID format {doc_id_str} during MongoDB status update (user {current_user.username}). This should have been caught earlier.")
                errors_info.append({"id": doc_id_str, "error": "Invalid ID format during MongoDB status update."})
            except Exception as e_mongo_update:
                logger.error(f"Batch delete vector: Unexpected error updating MongoDB status for doc {doc_id_str} (user {current_user.username}): {e_mongo_update}", exc_info=True)
                errors_info.append({"id": doc_id_str, "error": f"Unexpected error updating MongoDB status: {str(e_mongo_update)}"})
        
        # Compile final results
        final_success_count = len(successfully_updated_status_ids_str)
        total_authorized_requested = len(authorized_doc_ids_to_delete_str)
        
        message = (
            f"批量向量移除完成。請求處理 {len(doc_ids_to_process_str)} 個文檔。"
            f"其中 {total_authorized_requested} 個文檔通過權限驗證。"
            f"成功從向量庫移除並更新狀態: {final_success_count} 個。"
        )
        
        current_failed_ids = list(set(chroma_delete_result.get("failed_ids", [])))
        for err_info in errors_info: # Add errors from initial validation or MongoDB update stage
            if err_info["id"] not in current_failed_ids:
                 current_failed_ids.append(err_info["id"])


        if final_success_count == total_authorized_requested and total_authorized_requested > 0 and not errors_info and not chroma_delete_result.get("failed_ids"):
            return BasicResponse(success=True, message=message)
        else:
            # Add specific errors from Chroma if any
            if chroma_delete_result.get("errors"):
                 errors_info.extend(chroma_delete_result.get("errors"))
            logger.warning(message + f" 詳細錯誤/跳過列表: {errors_info}")
            return BasicResponse(success=False, message=message, details={"failed_or_skipped_ids": current_failed_ids, "errors": errors_info})

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"批量從向量數據庫刪除文檔時發生頂層錯誤 (user {current_user.username}): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"批量移除向量失敗: {str(e)}") 