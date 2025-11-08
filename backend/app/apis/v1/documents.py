from fastapi import (
    APIRouter, 
    Depends, 
    HTTPException, 
    status, 
    UploadFile, 
    File, 
    Form,
    Request, 
    Query,
    BackgroundTasks,
    Request
)
from fastapi.responses import FileResponse
from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import List, Optional, Any, Dict
import uuid
import os
# import shutil # Unused
import aiofiles
from werkzeug.utils import secure_filename
import logging
from pathlib import Path
# import json # Unused
# from datetime import datetime # Unused
import mimetypes
# import io # Unused
# from PIL import Image # Unused

from ...db.mongodb_utils import get_db
# get_unified_ai_service is no longer used directly in this file after refactorings
from ...dependencies import get_document_processing_service, get_settings 
from ...models.document_models import (
    Document,
    DocumentCreate,
    DocumentUpdate,
    DocumentStatus,
    PaginatedDocumentResponse,
    DocumentAnalysis,
    BatchDeleteRequest,
    BatchDeleteResponseDetail,
    BatchDeleteDocumentsResponse
)
from ...models.user_models import User
# AI models (AIImageAnalysisOutput, etc.) are no longer directly used in this file
# from ...models.ai_models_simplified import AIImageAnalysisOutput, TokenUsage, AITextAnalysisOutput, AIPromptRequest 
from ...crud import crud_documents
from ...core.config import settings, Settings
from ...core.logging_utils import log_event, LogLevel, AppLogger
from ...core.security import get_current_active_user
from ...services.document.document_processing_service import DocumentProcessingService, SUPPORTED_IMAGE_TYPES_FOR_AI
# unified_ai_service_simplified and its components are no longer directly used in this file
# from ...services.unified_ai_service_simplified import unified_ai_service_simplified, AIRequest, TaskType as AIServiceTaskType
# from ...services.unified_ai_config import unified_ai_config 
from ...services.document.document_tasks_service import DocumentTasksService
from app.services.vector.vector_db_service import vector_db_service
from .vector_db import BatchDeleteRequest as VectorDBBatchDeleteRequest
from ...utils import file_handling_utils # Added

# Setup logger
logger = AppLogger(__name__, level=logging.DEBUG).get_logger()


async def get_owned_document(
    document_id: uuid.UUID, 
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
) -> Document:
    """
    Dependency to get a document by ID and verify ownership.
    Raises HTTPException if not found or user is not the owner.
    """
    document = await crud_documents.get_document_by_id(db, document_id)
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"ID 為 {document_id} 的文件不存在")
    
    if document.owner_id != current_user.id:
        await log_event(
            db=db,
            level=LogLevel.WARNING,
            message="Unauthorized document access attempt.",
            source="api.documents.get_owned_document", # Standardized source
            user_id=str(current_user.id),
            details={
                "document_id": str(document_id),
                "document_owner_id": str(document.owner_id),
                "attempting_user_email": current_user.email # Masker should handle if sensitive
            }
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to access or modify this document.") # User-friendly message
        
    return document

router = APIRouter()

# 確保上傳目錄存在 (這個全局檢查是好的)
if not os.path.exists(settings.UPLOAD_DIR):
    os.makedirs(settings.UPLOAD_DIR)

# Dependency getter for DocumentTasksService
def get_document_tasks_service() -> DocumentTasksService:
    return DocumentTasksService()

@router.post("/", response_model=Document, status_code=status.HTTP_201_CREATED, summary="上傳新文件並創建記錄")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    tags: Optional[List[str]] = Form(None),
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings), # settings is used by file_handling_utils.prepare_upload_filepath
    background_tasks: BackgroundTasks = BackgroundTasks() 
):
    """
    上傳新文件並在數據庫中創建相應的記錄。

    - **file**: 要上傳的文件。
    - **tags**: (可選) 與文件關聯的標籤列表。
    """
    logger.info(f"用戶 {current_user.email} (ID: {current_user.id}) 正在上傳文件: {file.filename}")

    # Use functions from file_handling_utils
    file_path, safe_filename = file_handling_utils.prepare_upload_filepath(
        settings_obj=settings, # Pass settings as settings_obj
        current_user_id=current_user.id,
        original_filename_optional=file.filename,
        content_type=file.content_type
    )
    file_size = 0

    try:
        file_size = await file_handling_utils.save_uploaded_file(file, file_path, safe_filename)
        
        request_id_for_log = request.headers.get("X-Request-ID")

        actual_content_type, mime_type_warning = await file_handling_utils.validate_and_correct_file_type(
            file_path=file_path,
            declared_content_type=file.content_type,
            file_size=file_size,
            safe_filename=safe_filename,
            db=db, # Pass db
            current_user_id=current_user.id, # Pass current_user.id
            request_id=request_id_for_log
        )
        # Store original_mime_type for metadata if a warning occurred
        original_mime_type = file.content_type if mime_type_warning else None

    except Exception as e:
        logger.error(f"(upload_document) 處理文件 '{safe_filename}' 時發生錯誤: {e}")

        # Log the event of failure
        await log_event(
            db=db,
            level=LogLevel.ERROR,
            message=f"處理文件 '{safe_filename}' 時失敗: {str(e)}",
            source="documents.upload.processing_error",
            user_id=str(current_user.id),
            request_id=request.state.request_id if hasattr(request.state, 'request_id') else None,
            details={"filename": safe_filename, "target_path": str(file_path), "error_type": type(e).__name__, "error_detail": str(e)}
        )

        # If the exception is already an HTTPException (e.g., from _save_uploaded_file),
        # re-raise it directly. Otherwise, wrap it in a generic 500 error.
        if isinstance(e, HTTPException):
            raise
        else:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"處理文件 '{safe_filename}' 時發生意外錯誤。")
    finally:
        await file.close()

    # 創建 DocumentCreate Pydantic 模型實例
    document_data = DocumentCreate(
        filename=safe_filename,
        owner_id=current_user.id,
        file_type=actual_content_type,
        size=file_size,
        tags=tags if tags else [],
        metadata={
            "mime_type_verified": True,
            "upload_warnings": []
        }
    )

    # 如果在前面的代碼中檢測到 MIME 類型問題，則更新 metadata
    if mime_type_warning is not None:
        if not document_data.metadata:
            document_data.metadata = {}
        document_data.metadata["mime_type_verified"] = False
        if original_mime_type is not None:
            document_data.metadata["original_mime_type"] = original_mime_type
        document_data.metadata["upload_warnings"] = [mime_type_warning]

    try:
        created_document = await crud_documents.create_document(
            db=db, 
            document_data=document_data, 
            owner_id=current_user.id,
            file_path=str(file_path)
        )
        logger.info(f"文件 '{safe_filename}' (ID: {created_document.id}) 的數據庫記錄已創建")
    except Exception as e:
        logger.error(f"為文件 '{safe_filename}' 創建數據庫記錄失敗: {e}")
        # 如果數據庫記錄創建失敗，也應該刪除已保存的文件
        if file_path.exists():
            file_path.unlink(missing_ok=True)
            logger.info(f"因數據庫錯誤，已刪除物理文件: {file_path}")
        await log_event(
            db=db,
            level=LogLevel.ERROR,
            message=f"為文件 '{safe_filename}' 創建數據庫記錄失敗: {str(e)}",
            source="documents.upload.create_record",
            user_id=str(current_user.id),
            request_id=request.state.request_id if hasattr(request.state, 'request_id') else None,
            details={"filename": safe_filename, "document_data": document_data.model_dump_json(exclude_none=True)}
        )
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="創建文件記錄時發生內部錯誤")

    # 異步記錄操作日誌 (可以考慮放入 background_tasks)
    await log_event(
        db=db,
        level=LogLevel.INFO,
        message=f"文件 '{safe_filename}' (ID: {created_document.id}) 已成功上傳並記錄。",
        source="documents.upload.success",
        user_id=str(current_user.id),
        request_id=request.state.request_id if hasattr(request.state, 'request_id') else None,
        details={"document_id": str(created_document.id), "filename": safe_filename, "file_size": file_size, "file_type": file.content_type}
    )
    return created_document

@router.get("/", response_model=PaginatedDocumentResponse, summary="獲取當前用戶的文件列表")
async def list_documents(
    request: Request,
    current_user: User = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
    skip: int = Query(0, ge=0, description="跳過的記錄數"),
    limit: int = Query(20, ge=1, le=100, description="返回的最大記錄數"),
    status_in: Optional[List[DocumentStatus]] = Query(None, description="根據一個或多個文件狀態列表進行過濾"),
    filename_contains: Optional[str] = Query(None, description="根據文件名包含的文字過濾 (不區分大小寫)"),
    tags_include: Optional[List[str]] = Query(None, description="根據包含的標籤過濾 (傳入一個或多個標籤)"),
    cluster_id: Optional[str] = Query(None, description="根據聚類ID過濾"),
    clustering_status: Optional[str] = Query(None, description="根據聚類狀態過濾 (pending, clustered, excluded)"),
    sort_by: Optional[str] = Query(None, description="排序欄位 (例如 filename, created_at)"),
    sort_order: Optional[str] = Query("desc", description="排序順序 (asc 或 desc)")
):
    """
    檢索當前登入用戶的文件列表，支持分頁、過濾和排序。
    - **skip**: 跳過的記錄數。
    - **limit**: 返回的最大記錄數。
    - **status_in**: 根據一個或多個文件狀態列表進行過濾。
    - **filename_contains**: 根據文件名包含的文字過濾 (不區分大小寫)。
    - **tags_include**: 根據包含的標籤過濾 (傳入一個或多個標籤)。
    - **cluster_id**: 根據聚類ID過濾,只返回屬於該聚類的文檔。
    - **clustering_status**: 根據聚類狀態過濾 (pending, clustered, excluded)。
    - **sort_by**: 用於排序的欄位名稱。
    - **sort_order**: 排序方向 ('asc' 或 'desc')。
    """
    if sort_order and sort_order.lower() not in ["asc", "desc"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="無效的排序順序，必須是 'asc' 或 'desc'")

    documents = await crud_documents.get_documents(
        db,
        owner_id=current_user.id,
        skip=skip,
        limit=limit,
        status_in=status_in,
        filename_contains=filename_contains,
        tags_include=tags_include,
        cluster_id=cluster_id,
        clustering_status=clustering_status,
        sort_by=sort_by,
        sort_order=sort_order
    )
    
    total_count = await crud_documents.count_documents(
        db,
        owner_id=current_user.id,
        status_in=status_in,
        filename_contains=filename_contains,
        tags_include=tags_include,
        cluster_id=cluster_id,
        clustering_status=clustering_status
    )
    
    
    request_id_for_log = request.state.request_id if hasattr(request.state, 'request_id') else None
    await log_event(
        db=db,
        level=LogLevel.DEBUG,
        message="Documents retrieved.",
        source="api.documents.list_documents",
        user_id=str(current_user.id),
        request_id=request_id_for_log,
        details={
            "user_id": str(current_user.id),
            "skip": skip,
            "limit": limit,
            "status_in": [s.value for s in status_in] if status_in else None,
            "filename_contains": filename_contains,
            "tags_include": tags_include,
            "sort_by": sort_by,
            "sort_order": sort_order,
            "returned_count": len(documents),
            "total_available_count": total_count
        }
    )
    return PaginatedDocumentResponse(items=documents, total=total_count)

@router.get("/{document_id}", response_model=Document, summary="獲取特定文件的詳細信息")
async def get_document_details(
    request: Request,
    document: Document = Depends(get_owned_document),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    獲取特定文件的詳細信息。
    權限檢查由 get_owned_document 依賴處理。
    """
   
    request_id_for_log = request.state.request_id if hasattr(request.state, 'request_id') else None
    await log_event(
        db=db,
        level=LogLevel.DEBUG,
        message="Document details retrieved.",
        source="api.documents.get_document_details",
        user_id=str(document.owner_id),
        request_id=request_id_for_log,
        details={"document_id": str(document.id), "filename": document.filename}
    )
    return document

@router.get("/{document_id}/file", summary="獲取/下載文件本身", response_class=FileResponse)
async def get_document_file(
    request: Request, # Added Request for request_id
    document: Document = Depends(get_owned_document),
    db: AsyncIOMotorDatabase = Depends(get_db) # Added db for logging
    # current_user is implicitly part of get_owned_document, and document.owner_id can be used
):
    """
    根據文件ID獲取實際的文件內容，用於下載或客戶端預覽。
    只有文件擁有者才能下載。權限檢查由 get_owned_document 依賴處理。
    """
    request_id_val = request.state.request_id if hasattr(request.state, 'request_id') else None
    user_id_val = str(document.owner_id) # Owner is validated by get_owned_document

    if not document.file_path:
        await log_event(
            db=db, level=LogLevel.WARNING,
            message=f"Document file access failed: File path not recorded for document.",
            source="api.documents.get_document_file", user_id=user_id_val, request_id=request_id_val,
            details={"document_id": str(document.id), "filename": document.filename}
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"File path not recorded for document {document.filename}")

    if not os.path.exists(document.file_path):
        await log_event(
            db=db, level=LogLevel.ERROR, # Error because path is recorded but file is missing
            message=f"Document file access failed: File not found at recorded path.",
            source="api.documents.get_document_file", user_id=user_id_val, request_id=request_id_val,
            details={"document_id": str(document.id), "filename": document.filename, "recorded_path": document.file_path}
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"File not found at path: {document.file_path}")

    media_type = document.file_type if document.file_type else 'application/octet-stream'
    
    # For preview, try to display inline
    content_disposition_type = 'inline'
    if not document.file_type or not (
        document.file_type.startswith('image/') or 
        document.file_type == 'application/pdf' or 
        document.file_type.startswith('text/')
    ):
        content_disposition_type = 'attachment'

    await log_event(
        db=db, level=LogLevel.DEBUG,
        message="Document file accessed.",
        source="api.documents.get_document_file", user_id=user_id_val, request_id=request_id_val,
        details={"document_id": str(document.id), "filename": document.filename, "media_type": media_type}
    )
    return FileResponse(
        path=document.file_path, 
        media_type=media_type, 
        filename=document.filename,
        content_disposition_type=content_disposition_type
    )

@router.patch("/{document_id}", response_model=Document, summary="更新文件信息或觸發操作")
async def update_document_details(
    request: Request,
    doc_update: DocumentUpdate, 
    background_tasks: BackgroundTasks,
    existing_document: Document = Depends(get_owned_document), # Use the dependency
    db: AsyncIOMotorDatabase = Depends(get_db), # Still needed for operations
    current_user: User = Depends(get_current_active_user), # Still needed for logging user
    settings_di: Settings = Depends(get_settings), # Still needed for settings
    document_tasks_service: DocumentTasksService = Depends(get_document_tasks_service) # Added
):
    # existing_document is now provided by the get_owned_document dependency
    # The checks for existence and ownership are handled by the dependency.
    document_id = existing_document.id # Use existing_document.id for document_id

    update_fields = doc_update.model_dump(exclude_unset=True)
    
    # 獲取 request_id
    request_id_for_log = request.headers.get("X-Request-ID")

    logger.info(f"用戶 {current_user.email} 請求更新文件 ID: {document_id}，更新內容: {update_fields}")
    await log_event(
        db=db, level=LogLevel.INFO, message=f"用戶請求更新文件 ID: {document_id}",
        source="documents.update.request", user_id=str(current_user.id), request_id=request_id_for_log,
        details={"document_id": str(document_id), "update_data": update_fields}
    )

    if doc_update.trigger_content_processing:
        if existing_document.status in [DocumentStatus.ANALYZING]:
            logger.warning(f"文件 {document_id} 已在分析中 (狀態: {existing_document.status.value})，跳過新的 AI 分析觸發。")
        else:
            logger.info(f"為文件 ID: {document_id} 觸發後台 AI 分析/提取任務。")
            if not existing_document.file_path or not Path(existing_document.file_path).exists():
                logger.error(f"無法觸發分析：文件 {document_id} 的路徑不存在或未設定。路徑: {existing_document.file_path}")
                await crud_documents.update_document_status(db, document_id, DocumentStatus.ANALYSIS_FAILED, error_details="文件路徑無效，無法開始分析")
                await log_event(
                    db=db, level=LogLevel.ERROR, message=f"文件路徑無效，無法開始分析: {document_id}", 
                    source="documents.update.trigger_error", user_id=str(current_user.id), request_id=request_id_for_log, 
                    details={"doc_id": str(document_id), "file_path": existing_document.file_path}
                )
                updated_doc_for_error = await crud_documents.get_document_by_id(db, document_id)
                if updated_doc_for_error: return updated_doc_for_error
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件路徑無效，無法開始分析")
            
            await crud_documents.update_document_status(db, document_id, DocumentStatus.ANALYZING)
            
            background_tasks.add_task(
                document_tasks_service.process_document_content_analysis, # Changed to service method
                doc_id_str=str(document_id), # Corrected parameter name from doc_id to doc_id_str
                db=db, 
                user_id_for_log=str(current_user.id), 
                request_id_for_log=request_id_for_log, 
                settings_obj=settings_di, # Pass settings_di as settings_obj
                ai_ensure_chinese_output=doc_update.ai_ensure_chinese_output if doc_update.ai_ensure_chinese_output is not None else True,
                ai_model_preference=doc_update.ai_model_preference if doc_update.ai_model_preference is not None else None,
                ai_max_output_tokens=doc_update.ai_max_output_tokens if doc_update.ai_max_output_tokens is not None else None
            )
            await log_event(
                db=db, level=LogLevel.INFO, message=f"後台文件處理任務已為文件 {document_id} 啟動。", 
                source="documents.update.trigger_success", user_id=str(current_user.id), request_id=request_id_for_log,
                details={"doc_id": str(document_id)}
            )
        
        # After triggering, we don't want trigger_content_processing to be part of the direct update data
        # as it's an action, not a field to set to True in the DB directly via standard update.
        # However, DocumentUpdate model has it, so crud_documents.update_document needs to handle it or ignore it.
        # For now, let's assume crud_documents.update_document knows to ignore trigger_content_processing 
        # or we can create a new dict for update_data excluding it.
        update_data_for_crud = doc_update.model_dump(exclude_unset=True, exclude={"trigger_content_processing"})
        if not update_data_for_crud: # If only trigger was set, no other fields to update now
            # Fetch the document again to return its current state (now ANALYZING)
            doc_after_trigger = await crud_documents.get_document_by_id(db, document_id)
            if doc_after_trigger: return doc_after_trigger
            # Fallback, should not happen if doc exists
            return existing_document 

    # Prepare data for actual update (excluding trigger_content_processing if it was the only thing)
    # If trigger_content_processing was true, update_data_for_crud was prepared above.
    # If trigger_content_processing was false or not present, use all fields.
    if not doc_update.trigger_content_processing:
        update_data_for_crud = doc_update.model_dump(exclude_unset=True)
    # If update_data_for_crud is empty at this point (e.g. only trigger_content_processing=True was passed and handled)
    # and no other fields were in doc_update, we might not need to call update_document.
    # However, if other fields *were* present alongside trigger_content_processing=True, 
    # update_data_for_crud would contain them.

    updated_document: Optional[Document] = None
    if update_data_for_crud: # Only call update if there are actual fields to update
        logger.info(f"對文件 {document_id} 執行常規欄位更新: {update_data_for_crud}")
        updated_document = await crud_documents.update_document(
            db=db,
            document_id=document_id,
            update_data=update_data_for_crud
        )
        if not updated_document:
            # This case should ideally be handled by get_document_by_id or raise specific error from CRUD
            logger.error(f"更新文件 {document_id} 後未能檢索到更新後的文檔。可能已被刪除或發生錯誤。")
            await log_event(
                db=db, 
                level=LogLevel.ERROR, 
                message=f"更新文件 {document_id} 後未能檢索。", 
                source="documents.update.retrieve_fail", 
                user_id=str(current_user.id), 
                request_id=request_id_for_log, 
                details={"doc_id": str(document_id)}
            )
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="更新後文件未找到，可能已被刪除")
        logger.info(f"文件 {document_id} 的常規欄位已更新。")
        await log_event(
            db=db, 
            level=LogLevel.INFO, 
            message=f"文件 {document_id} 的欄位已更新。", 
            source="documents.update.fields_updated", 
            user_id=str(current_user.id), 
            request_id=request_id_for_log, 
            details={"doc_id": str(document_id), "updated_fields": list(update_data_for_crud.keys())}
        )
    
    # Determine what to return
    if updated_document: # If fields were updated
        return updated_document
    elif doc_update.trigger_content_processing: # If only trigger was processed and no other fields
        # Fetch the document again to reflect its current state (e.g., status might have changed to ANALYZING)
        doc_after_trigger = await crud_documents.get_document_by_id(db, document_id)
        if doc_after_trigger: 
            return doc_after_trigger
        # If somehow the document is not found after triggering, it's an issue
        logger.error(f"Document {document_id} not found after triggering processing, though it existed before.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"文件 {document_id} 在觸發處理後未找到。")
    else: # No updates and no trigger
        return existing_document

@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT, summary="刪除文件")
async def delete_document_route(
    request: Request,
    existing_document: Document = Depends(get_owned_document), # Use the dependency
    db: AsyncIOMotorDatabase = Depends(get_db), # Still needed for DB operations
    current_user: User = Depends(get_current_active_user) # Still needed for logging
    # document_id is now part of existing_document.id
):
    """
    刪除指定ID的文件記錄及其在伺服器上的實際文件。
    只有文件擁有者才能刪除。權限檢查由 get_owned_document 依賴處理。
    """
    document_id = existing_document.id # Use existing_document.id for document_id

    request_id_for_log = request.headers.get("X-Request-ID")
    if hasattr(request.state, 'request_id'): 
        request_id_for_log = request.state.request_id
    
    user_id_for_log_str = str(current_user.id)

    # The get_owned_document dependency has already performed existence and ownership checks.
    # No need for:
    # existing_document = await crud_documents.get_document_by_id(db, document_id)
    # if not existing_document: ...
    # if existing_document.owner_id != current_user.id: ...

    file_path_to_delete = existing_document.file_path

    logger.info(f"[delete_document_route] Preparing to delete document. existing_document.id: {existing_document.id} (type: {type(existing_document.id)})")
    deleted_from_db = await crud_documents.delete_document_by_id(db, existing_document.id)
    
    if not deleted_from_db:
        await log_event(
            db=db, level=LogLevel.ERROR, 
            message=f"Document deletion failed: Database record not deleted for {document_id}.",
            source="api.documents.delete_document", # Standardized source
            user_id=user_id_for_log_str, 
            request_id=request_id_for_log, 
            details={"document_id": str(document_id), "filename": existing_document.filename, "file_path_at_time_of_error": file_path_to_delete}
        )
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error deleting document record.")

    # From here, DB record is deleted. Proceed with vector and file system cleanup.
    # Log overall success at the end. Individual errors in cleanup are logged but don't make the whole operation fail.

    # Attempt to delete from vector database
    try:
        document_id_str = str(document_id)
        logger.info(f"Attempting to delete vectors for document {document_id_str}...")
        vector_delete_success = vector_db_service.delete_by_document_id(document_id_str)
        if vector_delete_success:
            logger.info(f"Successfully deleted vectors for document {document_id_str}")
            await log_event(
                db=db, level=LogLevel.DEBUG, # Changed to DEBUG as it's a sub-step
                message=f"Document vectors deleted from vector database.",
                source="api.documents.delete_document",
                user_id=user_id_for_log_str, 
                request_id=request_id_for_log, 
                details={"document_id": document_id_str}
            )
        else:
            # This condition might mean "not found" or actual failure depending on service implementation
            logger.warning(f"Problem deleting vectors for document {document_id_str} (or vectors not found).")
            await log_event(
                db=db, level=LogLevel.WARNING, 
                message=f"Document vectors not found or not deleted from vector database.",
                source="api.documents.delete_document",
                user_id=user_id_for_log_str, 
                request_id=request_id_for_log, 
                details={"document_id": document_id_str, "reason": "delete_by_document_id returned false"}
            )
    except Exception as e_vector:
        logger.error(f"Error deleting vectors for document {document_id}: {e_vector}", exc_info=True)
        await log_event(
            db=db, level=LogLevel.ERROR, 
            message=f"Document vector deletion failed.",
            source="api.documents.delete_document",
            user_id=user_id_for_log_str, 
            request_id=request_id_for_log, 
            details={"document_id": str(document_id), "error": str(e_vector), "error_type": type(e_vector).__name__}
        )

    # Attempt to delete from file system
    if file_path_to_delete:
        if os.path.exists(file_path_to_delete):
            try:
                os.remove(file_path_to_delete)
                await log_event(
                    db=db, level=LogLevel.DEBUG, # Changed to DEBUG as it's a sub-step
                    message=f"Document file deleted from filesystem.",
                    source="api.documents.delete_document",
                    user_id=user_id_for_log_str,
                    request_id=request_id_for_log,
                    details={"document_id": str(document_id), "file_path": file_path_to_delete}
                )
            except Exception as e_os:
                logger.error(f"Error deleting file from filesystem {file_path_to_delete}: {e_os}", exc_info=True)
                await log_event(
                    db=db, level=LogLevel.ERROR,
                    message=f"Document file system deletion failed.",
                    source="api.documents.delete_document",
                    user_id=user_id_for_log_str,
                    request_id=request_id_for_log,
                    details={"document_id": str(document_id), "file_path": file_path_to_delete, "error": str(e_os), "error_type": type(e_os).__name__}
                )
        else: # Path recorded, but file not there
            await log_event(
                db=db, level=LogLevel.WARNING,
                message=f"Document file not found at recorded path for deletion.",
                source="api.documents.delete_document",
                user_id=user_id_for_log_str, 
                request_id=request_id_for_log, 
                details={"document_id": str(document_id), "recorded_path": file_path_to_delete}
            )
    else: # No file path recorded
        await log_event(
            db=db, level=LogLevel.WARNING, 
            message=f"Document deletion: No file path recorded, skipping filesystem delete.",
            source="api.documents.delete_document",
            user_id=user_id_for_log_str, 
            request_id=request_id_for_log, 
            details={"document_id": str(document_id)}
        )

    # Overall success log for the main action (DB record deletion)
    await log_event(
        db=db, level=LogLevel.INFO,
        message="Document deleted successfully.", # This signifies the main DB operation was successful
        source="api.documents.delete_document",
        user_id=user_id_for_log_str,
        request_id=request_id_for_log,
        details={"document_id": str(document_id), "filename": existing_document.filename}
    )
    return # FastAPI handles 204 No Content

@router.post("/batch-delete", response_model=BatchDeleteDocumentsResponse, summary="批量刪除文件")
async def batch_delete_documents_route(
    request_data: BatchDeleteRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    # vector_db_service_instance: VectorDatabaseService = Depends(get_vector_db_service) # 如果需要單獨調用
):
    """
    批量刪除指定ID列表的文件記錄、其實際文件以及相關的向量數據庫條目。
    只有文件擁有者才能刪除其文件。
    """
    processed_count = 0
    success_count = 0
    action_details: List[BatchDeleteResponseDetail] = []

    # 獲取 request_id (如果有的話，用於日誌)
    # request_id_for_log = getattr(request.state, 'request_id', None) if hasattr(request, 'state') else None
    # ^^^ request is not directly available here, would need to pass Request object or handle differently if needed for logs

    user_id_for_log_str = str(current_user.id)

    doc_ids_to_delete_str = [str(doc_id) for doc_id in request_data.document_ids]


    for doc_id_uuid in request_data.document_ids:
        processed_count += 1
        doc_id_str = str(doc_id_uuid)
        existing_document: Optional[Document] = None # Define for this scope
        
        try:
            document_to_check = await crud_documents.get_document_by_id(db, doc_id_uuid)
            if not document_to_check:
                action_details.append(BatchDeleteResponseDetail(id=doc_id_uuid, status="not_found", message="文件不存在"))
                logger.warning(f"批量刪除：文件 ID {doc_id_str} 不存在 (請求者: {user_id_for_log_str})")
                continue
            if document_to_check.owner_id != current_user.id:
                action_details.append(BatchDeleteResponseDetail(id=doc_id_uuid, status="forbidden", message="無權限刪除此文件"))
                logger.warning(f"批量刪除授權失敗：用戶 {user_id_for_log_str} 嘗試刪除不屬於自己的文件 ID {doc_id_str}")
                continue
            existing_document = document_to_check # Assign if checks pass
        except Exception as e_loop:
            logger.error(f"Error processing document {doc_id_uuid} in batch delete during ownership check: {e_loop}", exc_info=True)
            action_details.append(BatchDeleteResponseDetail(id=doc_id_uuid, status="error", message=f"檢查文件時發生錯誤: {str(e_loop)}"))
            continue
        
        # If existing_document is still None here, it means one of the continue statements above was hit.
        if not existing_document:
            # This case should ideally not be reached if the logic above is correct,
            # but as a safeguard:
            logger.error(f"批量刪除：文件 ID {doc_id_str} 在檢查後未成功賦值，跳過。")
            continue

        file_path_to_delete = existing_document.file_path
        delete_error = False

        # 1. 從 MongoDB 刪除
        # Use existing_document.id which is a UUID, same as doc_id_uuid here.
        deleted_from_db = await crud_documents.delete_document_by_id(db, existing_document.id)
        if not deleted_from_db:
            action_details.append(BatchDeleteResponseDetail(id=doc_id_uuid, status="error", message="從數據庫刪除記錄失敗"))
            logger.error(f"批量刪除：數據庫記錄刪除失敗: {doc_id_str} (請求者: {user_id_for_log_str})")
            delete_error = True
            # 即使DB刪除失敗，也可能嘗試刪除文件和向量，或在此中止此文件的處理
            # 這裡選擇繼續嘗試刪除其他部分，但標記錯誤
        
        # 2. 從文件系統刪除
        if file_path_to_delete and os.path.exists(file_path_to_delete):
            try:
                os.remove(file_path_to_delete)
                logger.info(f"批量刪除：文件實體成功刪除: {file_path_to_delete} (請求者: {user_id_for_log_str})")
            except Exception as e:
                logger.error(f"批量刪除：文件實體刪除失敗: {file_path_to_delete}. 錯誤: {str(e)}")
                # 記錄錯誤，但不一定將其視為此文件刪除操作的完全失敗（如果DB記錄已刪）
        elif file_path_to_delete:
            logger.warning(f"批量刪除：文件實體在指定路徑未找到: {file_path_to_delete}")

        # 3. 從向量數據庫刪除 (如果存在)
        try:
            # vector_db_service 是全局實例，直接使用
            # 假設 delete_by_document_id 是同步的，如果它是異步的，需要 await
            # 並且它應該能處理文檔ID不存在於向量庫中的情況（即靜默成功或返回特定狀態）
            delete_vector_success = vector_db_service.delete_by_document_id(doc_id_str)
            if delete_vector_success:
                logger.info(f"批量刪除：成功從向量數據庫移除文檔 {doc_id_str} 的向量。")
                # 在這裡添加日誌，記錄每個成功刪除的向量
                await log_event(
                    db=db, level=LogLevel.DEBUG, # DEBUG for sub-operation success
                    message=f"Batch delete: Successfully removed vectors for document {doc_id_str}.",
                    source="api.documents.batch_delete",
                    user_id=user_id_for_log_str, 
                    request_id=None,
                    details={"document_id": doc_id_str}
                )
            else:
                logger.info(f"Batch delete: Vectors for document {doc_id_str} not found or not deleted by vector_db_service.")
                await log_event(
                    db=db, level=LogLevel.WARNING,
                    message=f"Batch delete: Vectors not found/deleted for document {doc_id_str}.",
                    source="api.documents.batch_delete",
                    user_id=user_id_for_log_str,
                    request_id=None,
                    details={"document_id": doc_id_str, "reason": "vector_db_service.delete_by_document_id returned false"}
                )
        except Exception as e_vector:
            logger.error(f"批量刪除：從向量數據庫移除文檔 {doc_id_str} 的向量時發生錯誤: {e_vector}")
            await log_event(
                db=db, level=LogLevel.ERROR, 
                message=f"Batch delete: Error removing vectors for document {doc_id_str}.",
                source="api.documents.batch_delete",
                user_id=user_id_for_log_str, 
                request_id=None, 
                details={"document_id": doc_id_str, "error": str(e_vector), "error_type": type(e_vector).__name__}
            )

        if not delete_error:
            success_count += 1
            action_details.append(BatchDeleteResponseDetail(id=doc_id_uuid, status="deleted", message="Document deleted successfully."))
        # Error details already added if delete_error is True

    final_message = f"Batch delete operation completed. Requested: {len(request_data.document_ids)}, Processed: {processed_count}, Succeeded: {success_count}."
    overall_success = success_count == len(request_data.document_ids) and processed_count == len(request_data.document_ids)


    if processed_count == 0 and not request_data.document_ids: # No IDs provided
        final_message = "No document IDs provided for batch deletion."
        overall_success = True # Or False, depending on desired semantics for empty request

    # Log the overall batch operation result
    await log_event(
        db=db, level=LogLevel.INFO,
        message=final_message,
        source="api.documents.batch_delete",
        user_id=user_id_for_log_str,
        request_id=None, # No single request_id for batch
        details={
            "requested_count": len(request_data.document_ids),
            "processed_count": processed_count,
            "success_count": success_count,
            "overall_success_status": overall_success
        }
    )

    return BatchDeleteDocumentsResponse(
        success=overall_success,
        message=final_message,
        processed_count=processed_count,
        success_count=success_count,
        details=action_details
    )

# 可以根據需要添加更專門的觸發端點，或者將邏輯保留在 PATCH 中
# @router.post("/{document_id}/trigger-extraction", response_model=Document, summary="觸發文本提取")
# async def trigger_text_extraction_endpoint(...):
#     ...

@router.put("/documents/{document_id}", response_model=Document, summary="更新文檔屬性或觸發處理")
async def update_document_endpoint(
    document_id: uuid.UUID, 
    doc_update: DocumentUpdate, 
    background_tasks: BackgroundTasks,
    request: Request, 
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    doc_processor: DocumentProcessingService = Depends(get_document_processing_service),
    settings_obj: Settings = Depends(get_settings),
    document_tasks_service: DocumentTasksService = Depends(get_document_tasks_service) # Added service
):
    # 檢查文件是否存在及所有權
    existing_document = await crud_documents.get_document_by_id(db, document_id)
    if not existing_document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文檔不存在")
    if existing_document.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="無權限修改此文件")

    request_id_for_log = request.headers.get("X-Request-ID") 
    
    updated_doc: Optional[Document] = None

    should_trigger_analysis = False
    if hasattr(doc_update, 'trigger_processing') and doc_update.trigger_processing:
        should_trigger_analysis = True
    if hasattr(doc_update, 'trigger_reanalysis') and doc_update.trigger_reanalysis:
        should_trigger_analysis = True
        if hasattr(doc_update, 'processing_strategy') and not doc_update.processing_strategy:
            doc_update.processing_strategy = "full_reanalysis" 

    if should_trigger_analysis:
        if existing_document.status == DocumentStatus.ANALYZING:
            logger.warning(f"文件 {document_id} 已在分析中，跳過重複觸發。")
        else:
            logger.info(f"為文件 {document_id} 觸發服務端同步分析...")
            try:
                updated_doc = await document_tasks_service.trigger_document_analysis(
                    db=db,
                    doc_processor=doc_processor,
                    document_id=document_id,
                    current_user_id=current_user.id,
                    settings_obj=settings_obj,
                    processing_strategy=doc_update.processing_strategy if hasattr(doc_update, 'processing_strategy') else None,
                    custom_prompt_id=doc_update.custom_prompt_id if hasattr(doc_update, 'custom_prompt_id') else None,
                    analysis_type=doc_update.analysis_type if hasattr(doc_update, 'analysis_type') else None,
                    task_type_str=doc_update.task_type if hasattr(doc_update, 'task_type') else None,
                    request_id=request_id_for_log,
                    ai_model_preference=doc_update.ai_model_preference if hasattr(doc_update, 'ai_model_preference') else None,
                    ai_ensure_chinese_output=doc_update.ai_ensure_chinese_output if hasattr(doc_update, 'ai_ensure_chinese_output') else None,
                    ai_max_output_tokens=doc_update.ai_max_output_tokens if hasattr(doc_update, 'ai_max_output_tokens') else None
                )
            except HTTPException as e: 
                raise e
            except Exception as e: 
                logger.error(f"觸發文件 {document_id} 分析時發生錯誤: {e}", exc_info=True)
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"觸發分析時發生錯誤: {str(e)}")


    # 更新其他常規文檔欄位
    # 創建一個不包含觸發標誌的更新字典
    update_data_dict = doc_update.model_dump(exclude_unset=True, exclude_none=True)
    trigger_flags = ["trigger_processing", "trigger_reanalysis", "processing_strategy", "custom_prompt_id", "analysis_type", "task_type",
                     "ai_model_preference", "ai_ensure_chinese_output", "ai_max_output_tokens"] # 也排除AI選項，因為它們用於觸發
    
    regular_update_data = {k: v for k, v in update_data_dict.items() if k not in trigger_flags}

    if regular_update_data:
        logger.info(f"更新文件 {document_id} 的常規欄位: {regular_update_data}")
        db_updated_doc = await crud_documents.update_document(db, document_id, regular_update_data)
        if not db_updated_doc:
            # 如果 trigger_analysis 成功但常規更新失敗或未找到文檔，updated_doc 可能是分析後的版本
            # 如果 trigger_analysis 未執行，則這是主要錯誤
            if not updated_doc:
                 raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="更新常規欄位後未找到文檔。")
        else:
            updated_doc = db_updated_doc # 常規更新成功，這是最新的文檔版本

    if not updated_doc: # 如果既沒有觸發分析，也沒有常規更新，或更新失敗
        # 返回現有文檔（如果沒有任何操作被執行）或拋出錯誤（如果更新失敗）
        # 為安全起見，重新獲取一次以確保狀態最新
        current_doc_state = await crud_documents.get_document_by_id(db, document_id)
        if not current_doc_state: # 這不應該發生，因為我們開始時檢查了它
             raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文檔在操作過程中消失。")
        return current_doc_state

    return updated_doc

@router.post("/documents/process-batch", response_model=List[Document], summary="處理一批文檔")
async def process_batch_documents_endpoint(
    background_tasks: BackgroundTasks, 
    request: Request, 
    # Depends() 參數
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    doc_processor: DocumentProcessingService = Depends(get_document_processing_service),
    settings_obj: Settings = Depends(get_settings),
    document_tasks_service: DocumentTasksService = Depends(get_document_tasks_service), # Added service
    # Form 參數 (帶隱式預設值)
    document_ids: List[uuid.UUID] = Form(...),
    processing_strategy: Optional[str] = Form(None),
    custom_prompt_id: Optional[str] = Form(None),
    analysis_type: Optional[str] = Form(None),
    task_type: Optional[str] = Form(None),
    ai_model_preference: Optional[str] = Form(None),
    ai_ensure_chinese_output: Optional[bool] = Form(None),
    ai_max_output_tokens: Optional[int] = Form(None)
):
    results: List[Document] = []
    request_id_for_log = request.headers.get("X-Request-ID") # Simplified

    for doc_id in document_ids:
        try:
            logger.info(f"開始批量處理文檔 ID: {doc_id}")
            result_doc = await document_tasks_service.trigger_document_analysis(
                db=db,
                doc_processor=doc_processor,
                document_id=doc_id,
                current_user_id=current_user.id,
                settings_obj=settings_obj, # 傳遞 settings_obj
                processing_strategy=processing_strategy,
                custom_prompt_id=custom_prompt_id,
                analysis_type=analysis_type,
                task_type_str=task_type, # 傳遞 task_type (即 task_type_str)
                request_id=request_id_for_log, # 傳遞 request_id
                ai_model_preference=ai_model_preference,
                ai_ensure_chinese_output=ai_ensure_chinese_output,
                ai_max_output_tokens=ai_max_output_tokens
            )
            results.append(result_doc)
        except HTTPException as e:
            logger.error(f"批量處理文檔 {doc_id} 時發生 HTTP 錯誤 (狀態: {e.status_code}): {e.detail}")
            # 根據需要決定是否要將錯誤的文檔信息加入 results 列表，或者僅記錄錯誤
            # 為了簡單起見，這裡我們跳過錯誤的文檔，只記錄
            # results.append({"id": doc_id, "status": "error", "detail": e.detail}) # 如果 DocumentResponse 結構允許
        except Exception as e:
            logger.error(f"批量處理文檔 {doc_id} 時發生未知錯誤: {e}", exc_info=True)
            # 同上，決定如何處理錯誤
    return results

@router.post("/documents/process-unprocessed", summary="處理所有未處理的文檔")
async def process_unprocessed_documents_endpoint(
    background_tasks: BackgroundTasks, 
    request: Request, 
    # Depends() 參數
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    doc_processor: DocumentProcessingService = Depends(get_document_processing_service),
    settings_obj: Settings = Depends(get_settings),
    document_tasks_service: DocumentTasksService = Depends(get_document_tasks_service), # Added service
    # Form 參數 (帶隱式預設值)
    ai_model_preference: Optional[str] = Form(None),
    ai_ensure_chinese_output: Optional[bool] = Form(None),
    ai_max_output_tokens: Optional[int] = Form(None)
):
    # 1. 查找所有狀態為 PENDING 或 EXTRACTION_FAILED 或 ANALYSIS_FAILED 的文檔
    #    或者，根據您的定義，"未處理"可能意味著其他狀態
    unprocessed_statuses = [
        DocumentStatus.PENDING, 
        DocumentStatus.UPLOADED, # 假設剛上傳也是未處理
        DocumentStatus.EXTRACTION_FAILED, 
        DocumentStatus.ANALYSIS_FAILED
    ]
    
    # 獲取符合條件的文檔 ID 列表
    # crud_documents 中可能需要一個新方法 get_documents_by_statuses
    # 這裡假設我們有一個方法可以獲取這些文檔的 ID
    # documents_to_process = await crud_documents.get_documents_by_statuses(db, current_user.id, unprocessed_statuses)
    # 簡化：假設我們直接獲取ID列表
    
    # 為了演示，我們將使用更簡單的方法：獲取所有 PENDING 的文檔
    # 在實際應用中，您需要一個更健壯的方法來獲取未處理的文檔ID
    documents_to_process_full = await crud_documents.get_documents(
        db, owner_id=current_user.id, status_in=unprocessed_statuses, limit=1000 # 限制以防過多
    )
    
    document_ids_to_process = [doc.id for doc in documents_to_process_full if doc.id is not None]

    if not document_ids_to_process:
        return {"message": "沒有找到需要處理的文檔。", "processed_count": 0}

    logger.info(f"找到 {len(document_ids_to_process)} 個未處理的文檔，將開始處理...")
    
    results: List[Document] = []
    processed_count = 0
    failed_count = 0
    request_id_for_log = request.headers.get("X-Request-ID") # Simplified

    for doc_id in document_ids_to_process:
        try:
            result_doc = await document_tasks_service.trigger_document_analysis(
                db=db,
                doc_processor=doc_processor,
                document_id=doc_id,
                current_user_id=current_user.id,
                settings_obj=settings_obj,
                request_id=request_id_for_log,
                ai_model_preference=ai_model_preference,
                ai_ensure_chinese_output=ai_ensure_chinese_output,
                ai_max_output_tokens=ai_max_output_tokens
                # processing_strategy, custom_prompt_id, analysis_type, task_type 留空或設預設
            )
            results.append(result_doc)
            processed_count +=1
        except Exception as e:
            logger.error(f"處理未處理文檔 {doc_id} 時發生錯誤: {e}", exc_info=True)
            failed_count += 1
            # 可以選擇更新文檔狀態為某種錯誤狀態
            try:
                await crud_documents.update_document_status(db, doc_id, DocumentStatus.ANALYSIS_FAILED, f"自動批量處理失敗: {str(e)[:50]}")
            except Exception as status_err:
                 logger.error(f"更新文檔 {doc_id} 狀態為失敗時再次發生錯誤: {status_err}")


    return {
        "message": f"處理了 {processed_count} 個文檔，{failed_count} 個失敗。",
        "processed_documents": results # 返回處理過的文檔列表 (如果需要)
    }

@router.post("/documents/retry-failed-analysis", summary="重試所有分析失敗的文檔")
async def retry_failed_documents_endpoint(
    background_tasks: BackgroundTasks, 
    request: Request, 
    # Depends() 參數
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: User = Depends(get_current_active_user), 
    doc_processor: DocumentProcessingService = Depends(get_document_processing_service), 
    settings_obj: Settings = Depends(get_settings), 
    document_tasks_service: DocumentTasksService = Depends(get_document_tasks_service), # Added service
    # Form 參數 (帶隱式預設值)
    ai_model_preference: Optional[str] = Form(None),
    ai_ensure_chinese_output: Optional[bool] = Form(None),
    ai_max_output_tokens: Optional[int] = Form(None)
):
    failed_statuses = [DocumentStatus.ANALYSIS_FAILED, DocumentStatus.EXTRACTION_FAILED] # 也重試提取失敗的
    
    # 獲取符合條件的文檔 ID 列表
    documents_to_retry_full = await crud_documents.get_documents(
        db, owner_id=current_user.id, status_in=failed_statuses, limit=1000 # 限制以防過多
    )
    document_ids_to_retry = [doc.id for doc in documents_to_retry_full if doc.id is not None]

    if not document_ids_to_retry:
        return {"message": "沒有找到分析失敗需要重試的文檔。", "retried_count": 0}

    logger.info(f"找到 {len(document_ids_to_retry)} 個分析失敗的文檔，將開始重試...")
    
    results: List[Document] = []
    retried_count = 0
    newly_failed_count = 0
    request_id_for_log = request.headers.get("X-Request-ID") # Simplified

    for doc_id in document_ids_to_retry:
        try:
            # 重試時，可能需要特定的 strategy 或 analysis_type，這裡簡化
            result_doc = await document_tasks_service.trigger_document_analysis(
                db=db,
                doc_processor=doc_processor,
                document_id=doc_id,
                current_user_id=current_user.id,
                settings_obj=settings_obj,
                request_id=request_id_for_log,
                ai_model_preference=ai_model_preference,
                ai_ensure_chinese_output=ai_ensure_chinese_output,
                ai_max_output_tokens=ai_max_output_tokens,
                processing_strategy="full_reanalysis" # 例如，指定一個重試策略
            )
            results.append(result_doc)
            if result_doc.status == DocumentStatus.ANALYSIS_COMPLETED or result_doc.status == DocumentStatus.TEXT_EXTRACTED:
                retried_count += 1
            else: # 如果重試後狀態仍然是失敗或錯誤
                newly_failed_count +=1
        except Exception as e:
            logger.error(f"重試分析失敗的文檔 {doc_id} 時發生錯誤: {e}", exc_info=True)
            newly_failed_count += 1
            try:
                await crud_documents.update_document_status(db, doc_id, DocumentStatus.ANALYSIS_FAILED, f"重試分析失敗: {str(e)[:50]}")
            except Exception as status_err:
                 logger.error(f"更新文檔 {doc_id} 狀態為重試失敗時再次發生錯誤: {status_err}")

    return {
        "message": f"嘗試重試 {len(document_ids_to_retry)} 個文檔。成功重試 {retried_count} 個，仍然失敗 {newly_failed_count} 個。",
        "retried_documents": results # 返回處理過的文檔列表 (如果需要)
    }