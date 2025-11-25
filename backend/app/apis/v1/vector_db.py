from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import List, Optional, Dict
import uuid

from pydantic import BaseModel, ValidationError
from app.db.mongodb_utils import get_db
from app.core.security import get_current_active_user, get_current_admin_user
from app.models.user_models import User
from app.models.vector_models import SemanticSearchRequest, SemanticSearchResult, BatchProcessRequest
from app.models.response_models import BasicResponse
from app.services.document.semantic_summary_service import semantic_summary_service
from app.services.vector.embedding_service import embedding_service
from app.services.document.vectorization_queue import vectorization_queue
from app.dependencies import get_vector_db_service
from app.core.logging_utils import AppLogger
import logging
from app.crud.crud_documents import get_document_by_id, update_document_vector_status
from app.models.document_models import VectorStatus
from fastapi import Request # Added
from app.core.logging_utils import log_event, LogLevel # Added
from app.core.logging_decorators import log_api_operation

logger = AppLogger(__name__, level=logging.DEBUG).get_logger() 

router = APIRouter()

@router.get("/queue/status")
@log_api_operation(operation_name="獲取向量化隊列狀態", log_success=True, success_level=LogLevel.DEBUG)
async def get_vectorization_queue_status(
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    獲取向量化隊列狀態
    
    返回信息：
    - 隊列是否正在處理
    - 隊列中等待的任務數
    - 當前正在處理的任務數
    - 已完成的任務數
    - 最大並發數
    """
    status = vectorization_queue.get_status()
    return {
        "status": "success",
        "data": status,
        "message": "向量化隊列狀態"
    }

@router.get("/stats")
@log_api_operation(operation_name="獲取向量資料庫統計", log_success=True, success_level=LogLevel.DEBUG)
async def get_vector_db_stats(
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """獲取向量資料庫統計信息 - 需要用戶認證"""
    vector_db_service_instance = get_vector_db_service()
    stats = await vector_db_service_instance.get_collection_stats()
    embedding_info = embedding_service.get_model_info()
    stats["embedding_model"] = embedding_info
    
    if not embedding_info["model_loaded"]:
        stats["initialization_required"] = True
        stats["initialization_message"] = "Embedding model not loaded. Initialize to start vector database."
    
    if 'error' in stats and 'collection has not been initialized' in stats.get('error', '').lower():
        stats["collection_initialization_required"] = True
    
    return stats

@router.post("/initialize")
@log_api_operation(operation_name="初始化向量資料庫", log_success=True)
async def initialize_vector_database(
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """初始化向量資料庫（創建集合和索引） - 需要管理員權限"""
    request_id_val = request.state.request_id if hasattr(request.state, 'request_id') else None
    await log_event(
        db=db, level=LogLevel.INFO,
        message=f"Admin user {current_user.username} initiated vector database initialization.",
        source="api.vector_db.initialize", user_id=str(current_user.id), request_id=request_id_val
    )
    try:
        if not embedding_service._model_loaded:
            logger.info("Embedding model not loaded, attempting to load...") # Keep internal logger for this detail
            embedding_service._load_model()
            await log_event(db=db, level=LogLevel.INFO, message="Embedding model loaded during initialization.", source="api.vector_db.initialize", user_id=str(current_user.id), request_id=request_id_val)
        
        vector_dimension = embedding_service.vector_dimension
        if not vector_dimension:
            await log_event(db=db, level=LogLevel.ERROR, message="Failed to get vector dimension during initialization.", source="api.vector_db.initialize", user_id=str(current_user.id), request_id=request_id_val)
            raise HTTPException(status_code=500, detail="Could not get vector dimension from embedding model.")
        
        vector_db_service_instance = get_vector_db_service()
        vector_db_service_instance.create_collection(vector_dimension)
        
        await log_event(
            db=db, level=LogLevel.INFO,
            message=f"Vector database initialized successfully by admin {current_user.username}.",
            source="api.vector_db.initialize", user_id=str(current_user.id), request_id=request_id_val,
            details={"vector_dimension": vector_dimension, "collection_name": vector_db_service_instance.collection_name}
        )
        return JSONResponse(
            content={
                "message": "Vector database initialized successfully.",
                "vector_dimension": vector_dimension,
                "collection_name": vector_db_service_instance.collection_name,
                "status": "initialized"
            }
        )
        
    except HTTPException: # Re-raise HTTPExceptions directly
        raise
    except Exception as e:
        await log_event(
            db=db, level=LogLevel.ERROR,
            message=f"Vector database initialization failed for admin {current_user.username}: {str(e)}",
            source="api.vector_db.initialize", user_id=str(current_user.id), request_id=request_id_val,
            details={"error": str(e), "error_type": type(e).__name__}
        )
        raise HTTPException(status_code=500, detail=f"Failed to initialize vector database: {str(e)}")

@router.delete("/document/{document_id}")
@log_api_operation(operation_name="刪除文檔向量", log_success=True)
async def delete_document_from_vector_db(
    document_id: str,
    request: Request,
    current_user: User = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """從向量資料庫中刪除文檔 - 需要用戶認證"""
    # 驗證 UUID 格式
    try:
        doc_id_as_uuid = uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid document ID format: {document_id}")
    
    # 檢查文檔存在和權限
    document = await get_document_by_id(db, doc_id_as_uuid)
    if not document:
        raise HTTPException(status_code=404, detail=f"Document not found: {document_id}")
    
    if document.owner_id != current_user.id:
        # 保留權限檢查日誌（重要的安全事件）
        await log_event(
            db=db, level=LogLevel.WARNING,
            message=f"Unauthorized vector deletion attempt",
            details={"document_id": document_id, "user": current_user.username}
        )
        raise HTTPException(status_code=403, detail="Not authorized to delete this document's vectors.")
    
    # 執行刪除
    vector_db_service_instance = get_vector_db_service()
    delete_success_from_chroma = vector_db_service_instance.delete_by_document_id(document_id)
    
    if not delete_success_from_chroma:
        raise HTTPException(status_code=500, detail="Failed to delete vectors from vector database (or vectors not found).")
    
    updated_doc = await update_document_vector_status(db, doc_id_as_uuid, VectorStatus.NOT_VECTORIZED)
    if not updated_doc:
        logger.warning(f"Vectors deleted from ChromaDB, but failed to update vector_status in MongoDB for doc: {document_id}")
    
    return JSONResponse(content={
        "message": f"Document vectors deleted and status updated: {document_id}",
        "document_id": document_id,
        "status": "deleted_and_status_updated"
    })

@router.post("/process-document/{document_id}")
@log_api_operation(operation_name="處理文檔向量化", log_success=True)
async def process_document_to_vector(
    document_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    將單個文檔處理並添加到向量資料庫 - 需要用戶認證
    (Background task)
    """
    try:
        doc_id_as_uuid = uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid document ID format: {document_id}")
    
    document = await get_document_by_id(db, doc_id_as_uuid)
    if not document:
        raise HTTPException(status_code=404, detail=f"Document not found: {document_id}")
    
    if document.owner_id != current_user.id:
        await log_event(
            db=db, level=LogLevel.WARNING,
            message=f"Unauthorized processing attempt",
            details={"document_id": document_id, "user": current_user.username}
        )
        raise HTTPException(status_code=403, detail="Not authorized to process this document.")
    
    background_tasks.add_task(
        semantic_summary_service.process_document_for_vector_db,
        db,
        document
    )
    
    return JSONResponse(
        status_code=202,
        content={
            "message": f"Document {document_id} has been queued for vector processing.",
            "document_id": document_id,
            "status": "processing_queued"
        }
    )

@router.post("/batch-process")
async def batch_process_documents(
    request_body: BatchProcessRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    current_user: User = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    批量處理文檔到向量資料庫 - 需要用戶認證
    """
    request_id_val = request.state.request_id if hasattr(request.state, 'request_id') else None
    document_ids_str_from_request = request_body.document_ids

    await log_event(
        db=db, level=LogLevel.INFO,
        message=f"User {current_user.username} requested batch processing of {len(document_ids_str_from_request)} documents.",
        source="api.vector_db.batch_process_documents", user_id=str(current_user.id), request_id=request_id_val,
        details={"requested_doc_ids": document_ids_str_from_request}
    )

    try:
        valid_document_ids_for_processing = []
        skipped_ids_details = []

        for doc_id_str in document_ids_str_from_request:
            try:
                doc_uuid = uuid.UUID(doc_id_str)
            except ValueError:
                logger.warning(f"Invalid document ID format in batch: {doc_id_str}, skipping.") # Keep for internal debug
                skipped_ids_details.append({"id": doc_id_str, "reason": "Invalid ID format"})
                await log_event(db=db, level=LogLevel.WARNING, message=f"Invalid document ID format in batch: {doc_id_str}", source="api.vector_db.batch_process_documents", user_id=str(current_user.id), request_id=request_id_val)
                continue

            document = await get_document_by_id(db, doc_uuid)
            if document and document.owner_id == current_user.id:
                valid_document_ids_for_processing.append(doc_id_str)
            else:
                reason = "Not found" if not document else "Unauthorized"
                logger.warning(f"Document {doc_id_str} (UUID: {doc_uuid}) {reason.lower()} or user unauthorized, skipping batch processing.") # Keep
                skipped_ids_details.append({"id": doc_id_str, "reason": reason})
                await log_event(db=db, level=LogLevel.WARNING, message=f"Skipping document in batch processing: {doc_id_str} - {reason}", source="api.vector_db.batch_process_documents", user_id=str(current_user.id), request_id=request_id_val)
        
        if not valid_document_ids_for_processing:
            await log_event(db=db, level=LogLevel.WARNING, message="Batch processing: No valid or authorized documents found.", source="api.vector_db.batch_process_documents", user_id=str(current_user.id), request_id=request_id_val, details={"skipped_ids": skipped_ids_details})
            raise HTTPException(status_code=400, detail="No valid documents found for processing or user unauthorized for all provided documents.")
        
        background_tasks.add_task(
            semantic_summary_service.batch_process_documents,
            db,
            valid_document_ids_for_processing 
        )
        
        final_message = f"{len(valid_document_ids_for_processing)} documents successfully queued for batch processing."
        await log_event(
            db=db, level=LogLevel.INFO,
            message=final_message,
            source="api.vector_db.batch_process_documents", user_id=str(current_user.id), request_id=request_id_val,
            details={
                "queued_count": len(valid_document_ids_for_processing),
                "skipped_count": len(skipped_ids_details),
                "skipped_details": skipped_ids_details
            }
        )
        return JSONResponse(
            status_code=202, # Accepted
            content={
                "message": final_message, # User-friendly
                "document_count": len(valid_document_ids_for_processing),
                "skipped_count": len(skipped_ids_details),
                "status": "processing_queued"
            }
        )
        
    except HTTPException: # Re-raise known HTTP exceptions
        raise
    except Exception as e:
        # logger.error(f"批量處理文檔失敗: {e}", exc_info=True) # Replaced
        await log_event(
            db=db, level=LogLevel.ERROR,
            message=f"Batch document processing request failed unexpectedly for user {current_user.username}: {str(e)}",
            source="api.vector_db.batch_process_documents", user_id=str(current_user.id), request_id=request_id_val,
            details={"error": str(e), "error_type": type(e).__name__}
        )
        raise HTTPException(status_code=500, detail="Failed to batch process documents.") # User-friendly

@router.post("/semantic-search", response_model=List[SemanticSearchResult])
async def semantic_search(
    request: SemanticSearchRequest, 
    fastapi_request: Request, 
    current_user: User = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db) 
):
    """
    語義搜索端點 - 支援兩階段混合檢索策略
    
    兩階段混合檢索：
    1. 第一階段：在摘要向量中快速找出候選文檔
    2. 第二階段：在候選文檔的內容塊中精確匹配
    
    搜索模式：
    - hybrid: 完整的兩階段混合檢索(預設)
    - summary_only: 僅搜索摘要向量(快速文檔級別搜索)
    - chunks_only: 僅搜索內容塊向量(精確內容級別搜索)
    - legacy: 傳統單階段搜索(向後兼容)
    """
    request_id_val = fastapi_request.state.request_id if hasattr(fastapi_request.state, 'request_id') else None
    await log_event(
        db=db, level=LogLevel.DEBUG,
        message=f"User {current_user.username} initiated semantic search.",
        source="api.vector_db.search", user_id=str(current_user.id), request_id=request_id_val,
        details={
            "query_text_length": len(request.query) if request.query else 0, 
            "top_k": request.top_k,
            "similarity_threshold": request.similarity_threshold,
            "collection_name": request.collection_name,
            "enable_hybrid_search": request.enable_hybrid_search,
            "enable_diversity_optimization": request.enable_diversity_optimization
        }
    )

    try:
        # 決定使用哪種搜索策略
        if request.enable_hybrid_search:
            # 使用兩階段混合檢索
            from app.services.vector.enhanced_search_service import enhanced_search_service
            
            # 根據前端指定的搜索類型決定策略
            search_type = request.search_type or "hybrid"
            
            # 驗證搜索類型
            valid_search_types = ["hybrid", "summary_only", "chunks_only", "rrf_fusion"]
            if search_type not in valid_search_types:
                search_type = "hybrid"  # 預設使用完整的兩階段檢索
            
            # 如果有特定的過濾條件，可能需要調整策略
            if request.filter_conditions:
                # 可以根據過濾條件智能選擇搜索策略
                pass
            
            # 確保 user_id 是字符串類型
            user_id_str = str(current_user.id) if current_user.id else None
            if not user_id_str:
                raise ValueError("用戶ID無效")
            
            results = await enhanced_search_service.two_stage_hybrid_search(
                db=db,
                query=request.query,
                user_id=user_id_str,
                search_type=search_type,
                stage1_top_k=min(request.top_k * 2, 20),  # 第一階段候選數
                stage2_top_k=request.top_k,  # 最終結果數
                similarity_threshold=request.similarity_threshold,
                # 修正：傳遞過濾條件
                filter_conditions=request.filter_conditions,
                # 傳遞動態 RRF 權重配置
                rrf_weights=request.rrf_weights,
                rrf_k_constant=request.rrf_k_constant
            )
            
            await log_event(
                db=db, level=LogLevel.INFO,
                message=f"Two-stage hybrid search completed for user {current_user.username}, found {len(results)} results.",
                source="api.vector_db.search", user_id=str(current_user.id), request_id=request_id_val,
                details={
                    "num_results": len(results), 
                    "search_strategy": "two_stage_hybrid",
                    "top_k": request.top_k
                }
            )
            
        else:
            # 使用傳統單階段搜索(向後兼容)
            query_vector = embedding_service.encode_text(request.query) 
            
            vector_db_service_instance = get_vector_db_service()
            results = vector_db_service_instance.search_similar_vectors(
                query_vector=query_vector,
                top_k=request.top_k,
                similarity_threshold=request.similarity_threshold,
                owner_id_filter=str(current_user.id), 
                metadata_filter=request.filter_conditions,  # 使用請求中的過濾條件
                collection_name=request.collection_name
            )
            
            await log_event(
                db=db, 
                level=LogLevel.INFO,
                message=f"Legacy semantic search completed for user {current_user.username}, found {len(results)} results.",
                source="api.vector_db.search", 
                user_id=str(current_user.id), 
                request_id=request_id_val,
                details={
                    "num_results": len(results), 
                    "search_strategy": "legacy",
                    "top_k": request.top_k
                }
            )
        
        return results
        
    except ValidationError as ve: # Pydantic validation error
        error_details = {
            "error": str(ve), 
            "error_type": type(ve).__name__, 
            "validation_errors": ve.errors(),
            "request_payload": {
                "query": request.query[:100] + "..." if len(request.query) > 100 else request.query,
                "top_k": request.top_k,
                "similarity_threshold": request.similarity_threshold,
                "enable_hybrid_search": request.enable_hybrid_search,
                "search_type": request.search_type,
                "current_user_id": str(current_user.id),
                "current_user_id_type": type(current_user.id).__name__
            }
        }
        
        await log_event(
            db=db, 
            level=LogLevel.WARNING,
            message=f"Semantic search failed for user {current_user.username} due to ValidationError: {str(ve)}",
            source="api.vector_db.search", 
            user_id=str(current_user.id), 
            request_id=request_id_val,
            details=error_details
        )
        raise HTTPException(status_code=400, detail=f"Semantic search input error: {str(ve)}")
    except ValueError as ve: # Specific error for embedding issues
        error_details = {
            "error": str(ve), 
            "error_type": type(ve).__name__, 
            "query_text_length": len(request.query) if request.query else 0,
            "request_payload": {
                "query": request.query[:100] + "..." if len(request.query) > 100 else request.query,
                "top_k": request.top_k,
                "similarity_threshold": request.similarity_threshold,
                "enable_hybrid_search": request.enable_hybrid_search,
                "search_type": request.search_type,
                "current_user_id": str(current_user.id),
                "current_user_id_type": type(current_user.id).__name__
            }
        }
        
        await log_event(
            db=db, 
            level=LogLevel.WARNING, # ValueError might be due to bad input, not necessarily server error
            message=f"Semantic search failed for user {current_user.username} due to ValueError: {str(ve)}",
            source="api.vector_db.search", 
            user_id=str(current_user.id), 
            request_id=request_id_val,
            details=error_details
        )
        raise HTTPException(status_code=400, detail=f"Semantic search input error: {str(ve)}") # User-friendly
    except Exception as e: # General errors
        await log_event(
            db=db, 
            level=LogLevel.ERROR,
            message=f"Semantic search failed unexpectedly for user {current_user.username}: {str(e)}",
            source="api.vector_db.search", 
            user_id=str(current_user.id), 
            request_id=request_id_val,
            details={"error": str(e), "error_type": type(e).__name__}
        )
        raise HTTPException(status_code=500, detail="An unexpected error occurred during semantic search.")


class BatchDeleteRequest(BaseModel):
    document_ids: List[str]

@router.delete("/documents", response_model=BasicResponse, summary="批量從向量數據庫刪除文檔")
async def batch_delete_documents_from_vector_db(
    request: Request, # Added
    request_data: BatchDeleteRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """根據文檔 ID 列表，批量從向量資料庫中刪除文檔的向量，並更新其在MongoDB中的vector_status。"""
    request_id_val = request.state.request_id if hasattr(request.state, 'request_id') else None
    await log_event(
        db=db, 
        level=LogLevel.INFO,
        message=f"User {current_user.username} requested batch deletion of document vectors.",
        source="api.vector_db.batch_delete_vectors", 
        user_id=str(current_user.id), 
        request_id=request_id_val,
        details={"requested_doc_id_count": len(request_data.document_ids)}
    )
    
    doc_ids_to_process_str: List[str] = request_data.document_ids
    authorized_doc_ids_to_delete_str: List[str] = []
    successfully_updated_status_ids_str: List[str] = []
    errors_info: List[Dict[str, str]] = [] # For user-facing error details
    
    for doc_id_str in doc_ids_to_process_str:
        try:
            doc_uuid = uuid.UUID(doc_id_str)
            document = await get_document_by_id(db, doc_uuid)
            if not document:
                errors_info.append({"id": doc_id_str, "error": "Document not found"})
                await log_event(db=db, level=LogLevel.WARNING, message=f"Batch delete vector: Document ID {doc_id_str} not found.", source="api.vector_db.batch_delete_vectors", user_id=str(current_user.id), request_id=request_id_val)
                continue
            if document.owner_id != current_user.id:
                errors_info.append({"id": doc_id_str, "error": "Forbidden"})
                await log_event(db=db, level=LogLevel.WARNING, message=f"Batch delete vector: User {current_user.username} unauthorized for doc {doc_id_str}.", source="api.vector_db.batch_delete_vectors", user_id=str(current_user.id), request_id=request_id_val)
                continue
            authorized_doc_ids_to_delete_str.append(doc_id_str)
        except ValueError:
            errors_info.append({"id": doc_id_str, "error": "Invalid document ID format"})
            await log_event(db=db, level=LogLevel.WARNING, message=f"Batch delete vector: Invalid ID format {doc_id_str}.", source="api.vector_db.batch_delete_vectors", user_id=str(current_user.id), request_id=request_id_val)
        except Exception as e_check:
            errors_info.append({"id": doc_id_str, "error": f"Error checking document: {str(e_check)}"})
            await log_event(db=db, level=LogLevel.ERROR, message=f"Batch delete vector: Error checking doc {doc_id_str}: {e_check}", source="api.vector_db.batch_delete_vectors", user_id=str(current_user.id), request_id=request_id_val, details={"error": str(e_check)})

    if not authorized_doc_ids_to_delete_str:
        # No need to log here again if all individual errors were logged above.
        if errors_info and len(errors_info) == len(doc_ids_to_process_str): # All failed validation
             return BasicResponse(success=False, message="No valid document IDs or permissions for processing.", details={"errors": errors_info})
        # If list was empty to begin with.
        await log_event(db=db, level=LogLevel.WARNING, message="Batch delete vector: No authorized document IDs to process.", source="api.vector_db.batch_delete_vectors", user_id=str(current_user.id), request_id=request_id_val)
        raise HTTPException(status_code=400, detail="No valid or authorized document IDs provided for deletion.")

    vector_db_service_instance = get_vector_db_service()
    chroma_delete_result = {"deleted_count": 0, "failed_ids": [], "errors": []}
    try:
        if authorized_doc_ids_to_delete_str:
            chroma_delete_result = await vector_db_service_instance.delete_by_document_ids(authorized_doc_ids_to_delete_str)
            await log_event(db=db, level=LogLevel.DEBUG, message=f"ChromaDB batch delete report: {chroma_delete_result}", source="api.vector_db.batch_delete_vectors", user_id=str(current_user.id), request_id=request_id_val)

        processed_in_chroma_ids_str = [
            doc_id for doc_id in authorized_doc_ids_to_delete_str 
            if doc_id not in chroma_delete_result.get("failed_ids", [])
        ]

        for doc_id_str in processed_in_chroma_ids_str:
            try:
                doc_uuid = uuid.UUID(doc_id_str) # Should be valid at this point
                updated_doc = await update_document_vector_status(db, doc_uuid, VectorStatus.NOT_VECTORIZED)
                if updated_doc:
                    successfully_updated_status_ids_str.append(doc_id_str)
                else:
                    errors_info.append({"id": doc_id_str, "error": "Failed to update MongoDB status post-Chroma deletion."})
                    await log_event(db=db, level=LogLevel.WARNING, message=f"Batch delete: Failed to update vector_status for doc {doc_id_str} in MongoDB.", source="api.vector_db.batch_delete_vectors", user_id=str(current_user.id), request_id=request_id_val)
            except Exception as e_mongo_update: # Catch error during mongo update for a specific ID
                errors_info.append({"id": doc_id_str, "error": f"Error updating MongoDB status: {str(e_mongo_update)}"})
                await log_event(db=db, level=LogLevel.ERROR, message=f"Batch delete: Error updating MongoDB status for doc {doc_id_str}: {e_mongo_update}", source="api.vector_db.batch_delete_vectors", user_id=str(current_user.id), request_id=request_id_val, details={"error": str(e_mongo_update)})
        
        final_success_count = len(successfully_updated_status_ids_str)
        total_authorized_requested = len(authorized_doc_ids_to_delete_str)
        
        message = f"Batch vector removal completed. Requested: {len(doc_ids_to_process_str)}, Authorized: {total_authorized_requested}, Successfully processed (vectorDB & status update): {final_success_count}."

        # Consolidate all failed/skipped IDs for the final report
        current_failed_ids = list(set(chroma_delete_result.get("failed_ids", []))) # From Chroma
        for err_item in errors_info: # From validation or Mongo update
            if err_item["id"] not in current_failed_ids:
                 current_failed_ids.append(err_item["id"])
        # Add IDs that were authorized but not in successfully_updated_status_ids_str and not already in current_failed_ids
        for doc_id_str in authorized_doc_ids_to_delete_str:
            if doc_id_str not in successfully_updated_status_ids_str and doc_id_str not in current_failed_ids:
                current_failed_ids.append(doc_id_str)
                if not any(d["id"] == doc_id_str for d in errors_info): # Add generic error if not already there
                    errors_info.append({"id": doc_id_str, "error": "Processing incomplete or status update failed."})


        is_overall_success = final_success_count == total_authorized_requested and total_authorized_requested > 0 and not errors_info and not chroma_delete_result.get("failed_ids")

        await log_event(db=db, level=LogLevel.INFO if is_overall_success else LogLevel.WARNING, message=message, source="api.vector_db.batch_delete_vectors", user_id=str(current_user.id), request_id=request_id_val, details={"summary": message, "errors_count": len(errors_info), "failed_ids_count": len(current_failed_ids)})

        if is_overall_success:
            return BasicResponse(success=True, message=message)
        else:
            return BasicResponse(success=False, message=message, details={"failed_or_skipped_ids": current_failed_ids, "errors": errors_info})

    except HTTPException: # Re-raise known HTTP exceptions
        raise
    except Exception as e: # Catch-all for unexpected errors in the main try block
        await log_event(
            db=db, level=LogLevel.ERROR,
            message=f"Batch vector deletion failed unexpectedly for user {current_user.username}: {str(e)}",
            source="api.vector_db.batch_delete_vectors", user_id=str(current_user.id), request_id=request_id_val,
            details={"error": str(e), "error_type": type(e).__name__}
        )
        raise HTTPException(status_code=500, detail=f"Batch vector removal failed: {str(e)}")

@router.get("/documents/{document_id}/chunks", response_model=List[SemanticSearchResult], summary="按文檔ID直接獲取所有向量塊")
@log_api_operation(operation_name="獲取文檔向量塊", log_success=True, success_level=LogLevel.DEBUG)
async def get_all_chunks_by_document_id(
    document_id: uuid.UUID,
    fastapi_request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    直接從向量數據庫中獲取指定文檔ID的所有相關向量塊（摘要和文本塊）。
    這是一個直接提取操作，而非語義搜索。
    """
    # 驗證文檔所有權
    doc = await get_document_by_id(db, document_id)
    if not doc or doc.owner_id != current_user.id:
        # 保留權限檢查日誌
        await log_event(
            db=db, level=LogLevel.WARNING,
            message=f"Unauthorized chunks access attempt",
            details={"document_id": str(document_id), "user": current_user.username}
        )
        raise HTTPException(status_code=404, detail="找不到文檔或無權訪問")
    
    # 從向量數據庫直接獲取塊
    vector_db_service_instance = get_vector_db_service()
    all_chunks = vector_db_service_instance.get_all_chunks_by_doc_id(
        owner_id=str(current_user.id),
        document_id=str(document_id)
    )
    
    return all_chunks

@router.post("/batch-process-summaries", response_model=BasicResponse)
async def batch_process_summaries(
    body: BatchProcessRequest, 
    background_tasks: BackgroundTasks,
    request: Request,
    current_user: User = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    批量處理文檔到向量資料庫 - 需要用戶認證
    """
    request_id_val = request.state.request_id if hasattr(request.state, 'request_id') else None
    document_ids_str_from_request = body.document_ids

    await log_event(
        db=db, level=LogLevel.INFO,
        message=f"User {current_user.username} requested batch processing of {len(document_ids_str_from_request)} documents.",
        source="api.vector_db.batch_process_summaries", user_id=str(current_user.id), request_id=request_id_val,
        details={"requested_doc_ids": document_ids_str_from_request} # Log requested IDs
    )

    try:
        valid_document_ids_for_processing = []
        skipped_ids_details = []

        for doc_id_str in document_ids_str_from_request:
            try:
                doc_uuid = uuid.UUID(doc_id_str)
            except ValueError:
                logger.warning(f"Invalid document ID format in batch: {doc_id_str}, skipping.") # Keep for internal debug
                skipped_ids_details.append({"id": doc_id_str, "reason": "Invalid ID format"})
                await log_event(db=db, level=LogLevel.WARNING, message=f"Invalid document ID format in batch: {doc_id_str}", source="api.vector_db.batch_process_summaries", user_id=str(current_user.id), request_id=request_id_val)
                continue

            document = await get_document_by_id(db, doc_uuid)
            if document and document.owner_id == current_user.id:
                valid_document_ids_for_processing.append(doc_id_str)
            else:
                reason = "Not found" if not document else "Unauthorized"
                logger.warning(f"Document {doc_id_str} (UUID: {doc_uuid}) {reason.lower()} or user unauthorized, skipping batch processing.") # Keep
                skipped_ids_details.append({"id": doc_id_str, "reason": reason})
                await log_event(db=db, level=LogLevel.WARNING, message=f"Skipping document in batch processing: {doc_id_str} - {reason}", source="api.vector_db.batch_process_summaries", user_id=str(current_user.id), request_id=request_id_val)
        
        if not valid_document_ids_for_processing:
            await log_event(db=db, level=LogLevel.WARNING, message="Batch processing: No valid or authorized documents found.", source="api.vector_db.batch_process_summaries", user_id=str(current_user.id), request_id=request_id_val, details={"skipped_ids": skipped_ids_details})
            raise HTTPException(status_code=400, detail="No valid documents found for processing or user unauthorized for all provided documents.")
        
        background_tasks.add_task(
            semantic_summary_service.batch_process_summaries,
            db,
            valid_document_ids_for_processing 
        )
        
        final_message = f"{len(valid_document_ids_for_processing)} documents successfully queued for batch processing."
        await log_event(
            db=db, level=LogLevel.INFO,
            message=final_message,
            source="api.vector_db.batch_process_summaries", user_id=str(current_user.id), request_id=request_id_val,
            details={
                "queued_count": len(valid_document_ids_for_processing),
                "skipped_count": len(skipped_ids_details),
                "skipped_details": skipped_ids_details
            }
        )
        return JSONResponse(
            status_code=202, # Accepted
            content={
                "message": final_message, # User-friendly
                "document_count": len(valid_document_ids_for_processing),
                "skipped_count": len(skipped_ids_details),
                "status": "processing_queued"
            }
        )
        
    except HTTPException: # Re-raise known HTTP exceptions
        raise
    except Exception as e:
        # logger.error(f"批量處理文檔失敗: {e}", exc_info=True) # Replaced
        await log_event(
            db=db, level=LogLevel.ERROR,
            message=f"Batch document processing request failed unexpectedly for user {current_user.username}: {str(e)}",
            source="api.vector_db.batch_process_summaries", user_id=str(current_user.id), request_id=request_id_val,
            details={"error": str(e), "error_type": type(e).__name__}
        )
        raise HTTPException(status_code=500, detail="Failed to batch process documents.") # User-friendly


@router.post("/reindex-all", response_model=BasicResponse, summary="重新索引所有文檔")
@log_api_operation(operation_name="重新索引所有文檔", log_success=True)
async def reindex_all_documents(
    background_tasks: BackgroundTasks,
    request: Request,
    current_user: User = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    重新索引當前用戶的所有文檔 - 將所有文檔重新向量化

    這個操作會：
    1. 獲取當前用戶的所有文檔
    2. 將它們全部加入向量化隊列
    3. 在背景執行向量化處理

    注意：這是一個耗時操作，大量文檔可能需要較長時間完成。
    """
    request_id_val = request.state.request_id if hasattr(request.state, 'request_id') else None

    await log_event(
        db=db, level=LogLevel.INFO,
        message=f"User {current_user.username} initiated full database reindex.",
        source="api.vector_db.reindex_all", user_id=str(current_user.id), request_id=request_id_val
    )

    try:
        # 獲取當前用戶的所有文檔 ID
        from app.crud.crud_documents import get_documents_by_owner

        all_documents = await get_documents_by_owner(db, current_user.id)

        if not all_documents:
            await log_event(
                db=db, level=LogLevel.WARNING,
                message=f"User {current_user.username} has no documents to reindex.",
                source="api.vector_db.reindex_all", user_id=str(current_user.id), request_id=request_id_val
            )
            return BasicResponse(
                success=True,
                message="沒有找到可重新索引的文檔",
                details={"document_count": 0}
            )

        # 提取所有文檔 ID
        document_ids = [str(doc.id) for doc in all_documents]

        await log_event(
            db=db, level=LogLevel.INFO,
            message=f"Queueing {len(document_ids)} documents for reindexing.",
            source="api.vector_db.reindex_all", user_id=str(current_user.id), request_id=request_id_val,
            details={"document_count": len(document_ids)}
        )

        # 在背景任務中批量處理
        background_tasks.add_task(
            semantic_summary_service.batch_process_documents,
            db,
            document_ids
        )

        return BasicResponse(
            success=True,
            message=f"已開始重新索引 {len(document_ids)} 個文檔，此操作將在背景執行",
            details={
                "document_count": len(document_ids),
                "status": "processing_queued"
            }
        )

    except Exception as e:
        await log_event(
            db=db, level=LogLevel.ERROR,
            message=f"Full database reindex failed for user {current_user.username}: {str(e)}",
            source="api.vector_db.reindex_all", user_id=str(current_user.id), request_id=request_id_val,
            details={"error": str(e), "error_type": type(e).__name__}
        )
        raise HTTPException(status_code=500, detail=f"重新索引失敗: {str(e)}")