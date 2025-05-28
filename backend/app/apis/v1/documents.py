from fastapi import (
    APIRouter, 
    Depends, 
    HTTPException, 
    status, 
    UploadFile, 
    File, 
    Form,
    Request, # 新增
    Query,
    BackgroundTasks # <--- 新增 BackgroundTasks
)
from fastapi.responses import FileResponse # 導入 FileResponse
from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import List, Optional, Any, Dict # <--- 新增 Dict
import uuid
import os
import shutil # 用於文件操作
import aiofiles
from werkzeug.utils import secure_filename
import logging # Import logging module
from pathlib import Path # <--- 新增導入
import json # <--- 新增 json
from datetime import datetime
import mimetypes # <--- 新增導入 mimetypes

from ...db.mongodb_utils import get_db
from ...dependencies import get_document_processing_service, get_settings, get_unified_ai_service # <--- 更新導入
from ...models.document_models import (
    Document,
    DocumentCreate,
    DocumentUpdate,
    DocumentStatus,
    PaginatedDocumentResponse,
    DocumentAnalysis, # <--- 導入 DocumentAnalysis
    BatchDeleteRequest, # 這是我們剛才創建的
    BatchDeleteResponseDetail, # <--- 恢復導入
    BatchDeleteDocumentsResponse # <--- 恢復導入
)
from ...models.user_models import User
from ...models.ai_models_simplified import AIImageAnalysisOutput, TokenUsage, AITextAnalysisOutput, AIPromptRequest # <--- 導入 AIPromptRequest
from ...crud import crud_documents
from ...core.config import settings, Settings # Import Settings type and settings instance
from ...core.logging_utils import log_event, LogLevel
from ...core.security import get_current_active_user
from ...services.document_processing_service import DocumentProcessingService, SUPPORTED_IMAGE_TYPES_FOR_AI # <--- 導入 SUPPORTED_IMAGE_TYPES_FOR_AI
from ...services.unified_ai_service_simplified import unified_ai_service_simplified # <--- 導入簡化版統一AI服務
from ...services.unified_ai_config import unified_ai_config # <--- 導入 unified_ai_config
from app.services.vector_db_service import vector_db_service # 確保導入
from .vector_db import BatchDeleteRequest as VectorDBBatchDeleteRequest # 可能需要區分或重用

# Setup logger
logger = logging.getLogger(__name__)
# You might want to configure the logger further, e.g., set level
# logger.setLevel(logging.INFO) # Or get level from settings


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
        # Log this attempt for security auditing
        logger.warning(f"User {current_user.id} ({current_user.email}) attempted to access document {document_id} owned by {document.owner_id}.")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="您無權訪問或修改此文件")
        
    return document

router = APIRouter()

# 確保上傳目錄存在 (這個全局檢查是好的)
if not os.path.exists(settings.UPLOAD_DIR):
    os.makedirs(settings.UPLOAD_DIR)

# Placeholder for get_settings_override if not found in dependencies or config
# This will likely need to be adjusted based on where get_settings_override is defined.
# For now, to resolve the immediate error, let's assume it might come from config or a new import.
# If it's a simple function that just returns the `settings` instance, we can define it here temporarily
# or preferably import it from its actual location.
# Example: from ...core.config import get_settings_override (if it exists there)
# Example: from ...dependencies import get_settings_override (if it exists there)

# Attempting to find get_settings_override - if this is a common dependency, it should be in dependencies.py
# For now, let's assume it should be imported or defined. If it simply returns the settings instance:
# async def get_settings_override() -> Settings: # <--- 移除此函數
#     return settings

# Define supported text MIME types for AI analysis at module level or within the function context
SUPPORTED_TEXT_TYPES_FOR_AI_PROCESSING = [
    "text/plain",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document", # .docx
    "text/markdown"
]

def _prepare_upload_filepath(
    settings: Settings, 
    current_user_id: uuid.UUID, 
    original_filename_optional: Optional[str], 
    content_type: Optional[str]
) -> tuple[Path, str]:
    """
    Prepares the upload file path and a safe filename.
    """
    user_folder = Path(settings.UPLOAD_DIR) / str(current_user_id)
    user_folder.mkdir(parents=True, exist_ok=True)

    original_filename = original_filename_optional if original_filename_optional else "untitled"
    base_name, ext = os.path.splitext(original_filename)
    safe_base_name = secure_filename(base_name) if base_name else ""
    
    if ext:
        safe_ext = ext.lower().lstrip('.')
    else:
        safe_ext = ""

    if not safe_base_name:
        safe_base_name = f"file_{uuid.uuid4().hex[:8]}"

    guessed_ext_from_mime = mimetypes.guess_extension(content_type) if content_type else None
    if guessed_ext_from_mime:
        guessed_ext_from_mime = guessed_ext_from_mime.lstrip('.')

    final_ext = ""
    if safe_ext:
        final_ext = safe_ext
    elif guessed_ext_from_mime:
        final_ext = guessed_ext_from_mime
    else:
        final_ext = "bin"

    safe_filename = f"{safe_base_name}.{final_ext}"
    file_path = user_folder / safe_filename
    return file_path, safe_filename

async def _save_uploaded_file(file: UploadFile, file_path: Path, safe_filename: str) -> int:
    """
    Saves the uploaded file to the specified path and returns its size.
    Raises HTTPException if saving fails.
    """
    try:
        async with aiofiles.open(file_path, 'wb') as out_file:
            content = await file.read()  # Read file content
            await out_file.write(content) # Write to disk
            file_size = len(content) # Get file size
        logger.info(f"文件 '{safe_filename}' 已保存到 '{file_path}'，大小: {file_size} bytes")
        return file_size
    except Exception as e:
        logger.error(f"(_save_uploaded_file) 保存文件 '{safe_filename}' 到 '{file_path}' 失敗: {e}")
        if file_path.exists():
            try:
                os.remove(str(file_path)) # Ensure file_path is string for os.remove
                logger.info(f"(_save_uploaded_file) 已刪除部分寫入的文件: {file_path}")
            except OSError as rm_error:
                logger.error(f"(_save_uploaded_file) 刪除部分寫入的文件 {file_path} 失敗: {rm_error}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"無法保存文件: {safe_filename}")

async def _validate_and_correct_file_type(
    file_path: Path,
    declared_content_type: Optional[str],
    file_size: int,
    safe_filename: str,
    db: AsyncIOMotorDatabase,
    current_user_id: uuid.UUID, # Changed from User to uuid.UUID
    request_id: Optional[str]
) -> tuple[Optional[str], Optional[str]]: # actual_content_type can be None if declared is None
    """
    Validates the file type based on its content and corrects if necessary.
    Returns the actual content type and any warning message.
    """
    actual_content_type: Optional[str] = declared_content_type
    mime_type_warning: Optional[str] = None
    original_mime_type_for_log: Optional[str] = declared_content_type # Keep original for logging

    if file_size == 0:
        logger.warning(f"警告：上傳的文件 '{safe_filename}' 大小為 0 字節")
        mime_type_warning = "文件大小為 0 字節，這可能不是一個有效的文件。"
        actual_content_type = "application/octet-stream"
    elif declared_content_type in [
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    ]:
        try:
            import zipfile
            with zipfile.ZipFile(file_path, 'r') as zip_check:
                zip_check.namelist()
            logger.info(f"已驗證 '{safe_filename}' 是有效的 Office 文件格式 ({declared_content_type})")
        except zipfile.BadZipFile:
            logger.warning(f"文件 '{safe_filename}' 聲稱是 Office 格式 ({declared_content_type})，但不是有效的 ZIP 格式。")
            actual_content_type = "application/octet-stream"
            mime_type_warning = f"文件聲稱是 {declared_content_type}，但驗證失敗。已作為二進制文件處理。"
            await log_event(
                db=db,
                level=LogLevel.WARNING,
                message=mime_type_warning,
                source="documents.upload.validate_file_type",
                user_id=str(current_user_id),
                request_id=request_id,
                details={
                    "filename": safe_filename,
                    "declared_mime_type": declared_content_type,
                    "corrected_mime_type": actual_content_type
                }
            )
    elif declared_content_type == "application/pdf":
        # Placeholder for potential PDF validation (e.g., checking PDF magic bytes or basic structure)
        # For now, we accept it as is if declared as PDF and not 0 size.
        pass
    
    # Ensure actual_content_type is a string if not None, or handle None case if declared_content_type can be None
    # and no other condition sets it.
    # If declared_content_type is None and file_size > 0 and not an office file, actual_content_type would still be None.
    # This might be okay, or we might want a default like "application/octet-stream".
    # For now, it will return None if declared_content_type was None and no specific check changed it.
    # However, the UploadFile object usually provides a content_type.

    return actual_content_type, mime_type_warning

@router.post("/", response_model=Document, status_code=status.HTTP_201_CREATED, summary="上傳新文件並創建記錄")
async def upload_document(
    request: Request, # 添加 Request 參數以獲取 request_id
    file: UploadFile = File(...),
    tags: Optional[List[str]] = Form(None),
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    settings: Settings = Depends(get_settings), # <--- 更新為 get_settings
    # background_tasks: BackgroundTasks # 如果日誌操作需要較長時間，可以考慮後台任務
):
    """
    上傳新文件並在數據庫中創建相應的記錄。

    - **file**: 要上傳的文件。
    - **tags**: (可選) 與文件關聯的標籤列表。
    """
    logger.info(f"用戶 {current_user.email} (ID: {current_user.id}) 正在上傳文件: {file.filename}")

    file_path, safe_filename = _prepare_upload_filepath(
        settings=settings,
        current_user_id=current_user.id,
        original_filename_optional=file.filename,
        content_type=file.content_type
    )
    file_size = 0

    try:
        file_size = await _save_uploaded_file(file, file_path, safe_filename)
        
        request_id_for_log: Optional[str] = None
        if hasattr(request.state, 'request_id'):
            request_id_for_log = request.state.request_id
        elif request.headers.get("X-Request-ID"):
            request_id_for_log = request.headers.get("X-Request-ID")

        actual_content_type, mime_type_warning = await _validate_and_correct_file_type(
            file_path=file_path,
            declared_content_type=file.content_type, # from UploadFile
            file_size=file_size,
            safe_filename=safe_filename,
            db=db,
            current_user_id=current_user.id, # Pass the ID
            request_id=request_id_for_log
        )
        # Store original_mime_type for metadata if a warning occurred
        original_mime_type = file.content_type if mime_type_warning else None

    except Exception as e: # This will catch HTTPException from _save_uploaded_file or other errors
        # Log the error that occurred during the process within upload_document's try block
        logger.error(f"(upload_document) 處理文件 '{safe_filename}' 時發生錯誤: {e}")

        # Log the event of failure
        await log_event(
            db=db,
            level=LogLevel.ERROR,
            message=f"處理文件 '{safe_filename}' 時失敗: {str(e)}",
            source="documents.upload.processing_error", # Source indicates general processing error
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
        owner_id=current_user.id, # DocumentCreate 繼承自 DocumentBase，其中包含 owner_id
        file_type=actual_content_type, # 使用實際檢測到的內容類型，而不是 file.content_type
        size=file_size, # 使用計算得到的文件大小
        tags=tags if tags else [],
        # 添加 metadata 以包含有關文件的額外信息，例如 MIME 類型驗證結果
        metadata={
            "mime_type_verified": True, # 默認假設已驗證
            "upload_warnings": [] # 用於存儲任何上傳警告
        }
        # uploader_device_id: Optional[str] = Field(None, description="上傳設備的ID") # 可選，看是否需要從 request 中獲取
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
            owner_id=current_user.id, # 根據 crud_documents.create_document 函數簽名傳遞
            file_path=str(file_path)  # 根據 crud_documents.create_document 函數簽名傳遞
            # uploader_device_id=None # 如果需要，從 request 或其他地方獲取並傳遞
        )
        logger.info(f"文件 '{safe_filename}' (ID: {created_document.id}) 的數據庫記錄已創建")
    except Exception as e:
        logger.error(f"為文件 '{safe_filename}' 創建數據庫記錄失敗: {e}")
        # 如果數據庫記錄創建失敗，也應該刪除已保存的文件
        if file_path.exists():
            file_path.unlink(missing_ok=True)
            logger.info(f"因數據庫錯誤，已刪除物理文件: {file_path}")
        await log_event(
            db=db, # 確保傳遞了 db session
            level=LogLevel.ERROR,
            message=f"為文件 '{safe_filename}' 創建數據庫記錄失敗: {str(e)}",
            source="documents.upload.create_record",
            user_id=str(current_user.id), # <--- 確認轉換為 str
            request_id=request.state.request_id if hasattr(request.state, 'request_id') else None,
            details={"filename": safe_filename, "document_data": document_data.model_dump_json(exclude_none=True)}
        )
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="創建文件記錄時發生內部錯誤")

    # 異步記錄操作日誌 (可以考慮放入 background_tasks)
    await log_event(
        db=db, # 確保傳遞了 db session
        level=LogLevel.INFO,
        message=f"文件 '{safe_filename}' (ID: {created_document.id}) 已成功上傳並記錄。",
        source="documents.upload.success",
        user_id=str(current_user.id), # <--- 確認轉換為 str
        request_id=request.state.request_id if hasattr(request.state, 'request_id') else None,
        details={"document_id": str(created_document.id), "filename": safe_filename, "file_size": file_size, "file_type": file.content_type}
    )
    return created_document

@router.get("/", response_model=PaginatedDocumentResponse, summary="獲取當前用戶的文件列表")
async def list_documents(
    current_user: User = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
    skip: int = Query(0, ge=0, description="跳過的記錄數"),
    limit: int = Query(20, ge=1, le=100, description="返回的最大記錄數"),
    status_in: Optional[List[DocumentStatus]] = Query(None, description="根據一個或多個文件狀態列表進行過濾"),
    filename_contains: Optional[str] = Query(None, description="根據文件名包含的文字過濾 (不區分大小寫)"),
    tags_include: Optional[List[str]] = Query(None, description="根據包含的標籤過濾 (傳入一個或多個標籤)"),
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
        sort_by=sort_by,
        sort_order=sort_order
    )
    
    total_count = await crud_documents.count_documents(
        db,
        owner_id=current_user.id,
        status_in=status_in,
        filename_contains=filename_contains,
        tags_include=tags_include
    )
    
    return PaginatedDocumentResponse(items=documents, total=total_count)

@router.get("/{document_id}", response_model=Document, summary="獲取特定文件的詳細信息")
async def get_document_details(
    document: Document = Depends(get_owned_document)
):
    """
    獲取特定文件的詳細信息。
    權限檢查由 get_owned_document 依賴處理。
    """
    return document

@router.get("/{document_id}/file", summary="獲取/下載文件本身", response_class=FileResponse)
async def get_document_file(
    document: Document = Depends(get_owned_document)
):
    """
    根據文件ID獲取實際的文件內容，用於下載或客戶端預覽。
    只有文件擁有者才能下載。權限檢查由 get_owned_document 依賴處理。
    """
    if not document.file_path:
        # 考慮加入 user_id 和 request_id 到日誌
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"文件 {document.filename} (ID: {document.id}) 沒有記錄儲存路徑")

    if not os.path.exists(document.file_path):
        # 考慮加入 user_id 和 request_id 到日誌
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"文件 {document.filename} (ID: {document.id}) 在指定路徑 {document.file_path} 未找到")

    media_type = document.file_type if document.file_type else 'application/octet-stream'
    
    # For preview, try to display inline
    content_disposition_type = 'inline'
    if not document.file_type or not (
        document.file_type.startswith('image/') or 
        document.file_type == 'application/pdf' or 
        document.file_type.startswith('text/') # Common text types can also be inline
    ):
        # For unknown types or types not typically previewed inline, fallback to attachment
        content_disposition_type = 'attachment'

    return FileResponse(
        path=document.file_path, 
        media_type=media_type, 
        filename=document.filename,
        content_disposition_type=content_disposition_type
    )

async def _setup_and_validate_document_for_processing(
    doc_id_str: str, 
    db: AsyncIOMotorDatabase, 
    user_id_for_log: str, 
    request_id_for_log: Optional[str]
) -> Optional[Document]:
    """
    Helper function to perform initial setup and validation for document processing.
    Reloads AI config, converts doc_id to UUID, fetches document, and validates file path.
    Returns the Document object if successful, None otherwise.
    """
    try:
        await unified_ai_config.reload_task_configs(db)
        logger.info(f"AI配置已重新載入 (task for doc_id: {doc_id_str})")
    except Exception as e:
        logger.error(f"後台任務初始設定錯誤 (AI 配置重載 for doc_id {doc_id_str}): {e}", exc_info=True)
        # Not returning here, as this might not be fatal for all processing.
        # Or, if critical, one could update status and return None. For now, just log.

    doc_uuid: Optional[uuid.UUID] = None
    try:
        doc_uuid = uuid.UUID(doc_id_str)
    except ValueError:
        logger.error(f"Background task: Invalid UUID string for doc_id: {doc_id_str}. Cannot proceed.")
        await log_event(
            db=db, level=LogLevel.CRITICAL, message=f"Invalid document ID format '{doc_id_str}' in background task.",
            source="doc_processing.setup.id_conversion_error", user_id=user_id_for_log, request_id=request_id_for_log,
            details={"original_doc_id": doc_id_str}
        )
        return None

    document_from_db = await crud_documents.get_document_by_id(db, doc_uuid)
    if not document_from_db:
        logger.error(f"無法獲取文檔: ID {doc_uuid}")
        await log_event(db=db, level=LogLevel.ERROR, message=f"文件處理失敗: 文件記錄不存在 for {doc_uuid}",
                        source="doc_processing.setup.doc_not_found", user_id=user_id_for_log, request_id=request_id_for_log)
        return None

    if not document_from_db.file_path:
        logger.error(f"文件路徑未設定: ID {doc_uuid}")
        await crud_documents.update_document_status(db, doc_uuid, DocumentStatus.PROCESSING_ERROR, "文件記錄缺少路徑")
        await log_event(db=db, level=LogLevel.ERROR, message=f"文件處理失敗: 文件記錄缺少路徑 for {doc_uuid}",
                        source="doc_processing.setup.path_missing", user_id=user_id_for_log, request_id=request_id_for_log)
        return None

    doc_path = Path(document_from_db.file_path)
    if not doc_path.exists():
        logger.error(f"Document file not found at path: {document_from_db.file_path} for doc ID: {doc_uuid}")
        await crud_documents.update_document_status(db, doc_uuid, DocumentStatus.PROCESSING_ERROR, "文件未找到，無法處理")
        await log_event(db=db, level=LogLevel.ERROR, message=f"文件處理失敗: 文件不存在 {document_from_db.file_path}",
                        source="doc_processing.setup.file_not_found", user_id=user_id_for_log, request_id=request_id_for_log,
                        details={"doc_id": str(doc_uuid), "path": document_from_db.file_path})
        return None
        
    return document_from_db

async def _process_image_document(
    document: Document, 
    db: AsyncIOMotorDatabase, 
    user_id_for_log: str, 
    request_id_for_log: Optional[str], 
    ai_force_stable_model: Optional[bool], 
    ai_ensure_chinese_output: Optional[bool]
) -> tuple[Optional[Dict[str, Any]], Optional[TokenUsage], Optional[str], DocumentStatus]:
    """
    Helper function to process an image document for AI analysis.
    Returns analysis data, token usage, model used, and the resulting status.
    """
    analysis_data_to_save: Optional[Dict[str, Any]] = None
    token_usage_to_save: Optional[TokenUsage] = None
    model_used_for_analysis: Optional[str] = None
    new_status = DocumentStatus.ANALYZING # Default status if processing starts

    doc_uuid = document.id
    doc_file_path_str = str(document.file_path) if document.file_path else None
    doc_mime_type = document.file_type

    logger.info(f"Performing AI image analysis for document ID: {doc_uuid}, MIME: {doc_mime_type}")

    try:
        if not doc_file_path_str: # Should have been caught by _setup_and_validate... but double check
            raise ValueError("File path is missing for image document.")

        temp_doc_processing_service = DocumentProcessingService()
        image_bytes = await temp_doc_processing_service.get_image_bytes(doc_file_path_str)
        if not image_bytes:
            logger.error(f"無法讀取圖片文件字節數據 for doc ID: {doc_uuid}")
            new_status = DocumentStatus.PROCESSING_ERROR
            # No specific analysis data to save, but other values are defaults
            return analysis_data_to_save, token_usage_to_save, model_used_for_analysis, new_status

        ai_response = await unified_ai_service_simplified.analyze_image(
            image_data=image_bytes, 
            image_mime_type=doc_mime_type, 
            db=db,
            force_stable=ai_force_stable_model if ai_force_stable_model is not None else True,
            ensure_chinese_output=ai_ensure_chinese_output if ai_ensure_chinese_output is not None else True
        )
        
        if not ai_response.success or not isinstance(ai_response.content, AIImageAnalysisOutput):
            error_msg = ai_response.error_message or "AI image analysis returned unsuccessful or invalid content type."
            logger.error(f"圖片分析失敗 for doc ID {doc_uuid}: {error_msg}")
            new_status = DocumentStatus.ANALYSIS_FAILED # More specific than PROCESSING_ERROR for AI failure
            # Optionally, save error message if your model supports it
            # analysis_data_to_save = {"error": error_msg} 
            return analysis_data_to_save, token_usage_to_save, model_used_for_analysis, new_status
        
        ai_image_output = ai_response.content
        token_usage_to_save = ai_response.token_usage
        model_used_for_analysis = ai_response.model_used
        analysis_data_to_save = ai_image_output.model_dump()
        
        log_message = f"圖片 AI 分析成功完成 (doc ID: {doc_uuid})" # Will be logged by caller if needed
        if ai_image_output.error_message or \
           (hasattr(ai_image_output, 'content_type') and "Error" in str(ai_image_output.content_type)): # Check if content_type indicates an error
            new_status = DocumentStatus.ANALYSIS_FAILED
            log_message = f"圖片 AI 分析失敗或返回錯誤 (doc ID: {doc_uuid}): {ai_image_output.error_message or ai_image_output.initial_description[:100]}"
        else:
            new_status = DocumentStatus.ANALYSIS_COMPLETED
        logger.info(log_message) # Log result here or let caller do it.

    except ValueError as ve: # Specifically for get_image_bytes or other ValueErrors
        logger.error(f"ValueError during image processing for doc ID {doc_uuid}: {ve}", exc_info=True)
        new_status = DocumentStatus.PROCESSING_ERROR
    except Exception as e:
        logger.error(f"Unexpected error during image processing for doc ID {doc_uuid}: {e}", exc_info=True)
        new_status = DocumentStatus.PROCESSING_ERROR
        # analysis_data_to_save = {"error": f"Unexpected error: {str(e)}"} # Example of saving error info

    return analysis_data_to_save, token_usage_to_save, model_used_for_analysis, new_status

async def _process_text_document(
    document: Document, 
    db: AsyncIOMotorDatabase, 
    user_id_for_log: str, 
    request_id_for_log: Optional[str], 
    settings_obj: Settings, 
    ai_force_stable_model: Optional[bool], 
    ai_ensure_chinese_output: Optional[bool]
) -> tuple[Optional[Dict[str, Any]], Optional[TokenUsage], Optional[str], DocumentStatus]:
    """
    Helper function to process a text document (extraction and AI analysis).
    Returns analysis data, token usage, model used, and the resulting status.
    """
    analysis_data_to_save: Optional[Dict[str, Any]] = None
    token_usage_to_save: Optional[TokenUsage] = None
    model_used_for_analysis: Optional[str] = None
    new_status = DocumentStatus.ANALYZING
    extracted_text_content: Optional[str] = None # Keep track of extracted text for AI input

    doc_uuid = document.id
    doc_path = Path(str(document.file_path)) if document.file_path else None
    doc_mime_type = document.file_type

    logger.info(f"Performing text extraction and AI analysis for document ID: {doc_uuid}, MIME: {doc_mime_type}")

    try:
        if not doc_path or not document.file_path : # file_path should be validated by caller (_setup_and_validate...)
            logger.error(f"File path is missing for text document ID: {doc_uuid}")
            return None, None, None, DocumentStatus.PROCESSING_ERROR # Should ideally not happen if caller validates

        doc_processing_service_instance = get_document_processing_service()
        extracted_text_result, extraction_status, extraction_error = \
            await doc_processing_service_instance.extract_text_from_document(str(doc_path), doc_path.suffix)

        if extraction_status == DocumentStatus.PROCESSING_ERROR or not extracted_text_result or not extracted_text_result.strip():
            error_detail = extraction_error or "未能從文件中提取到有效文本內容"
            logger.error(f"從文檔 {doc_uuid} ({doc_mime_type}) 提取文本時出錯或結果為空: {error_detail}", exc_info=bool(extraction_error))
            new_status = DocumentStatus.EXTRACTION_FAILED
            await crud_documents.update_document_status(db, doc_uuid, new_status, error_detail)
            await log_event(
                db=db, level=LogLevel.ERROR, message=f"文本提取失敗/結果為空: {error_detail}",
                source="doc_processing.text_helper.extraction_error", user_id=user_id_for_log, request_id=request_id_for_log,
                details={"doc_id": str(doc_uuid)}
            )
            return None, None, None, new_status

        extracted_text_content = extracted_text_result
        await crud_documents.update_document_on_extraction_success(db, doc_uuid, extracted_text_content)
        logger.info(f"成功從 {doc_uuid} 提取 {len(extracted_text_content)} 字元的文本。開始 AI 分析...")

        # Truncate text if necessary
        max_prompt_len = settings_obj.AI_MAX_INPUT_CHARS_TEXT_ANALYSIS
        if len(extracted_text_content) > max_prompt_len:
            logger.warning(f"提取的文本長度 ({len(extracted_text_content)}) 超過最大允許長度 ({max_prompt_len})。將進行截斷。 Doc ID: {doc_uuid}")
            extracted_text_content = extracted_text_content[:max_prompt_len]

        ai_response = await unified_ai_service_simplified.analyze_text(
            text_content=extracted_text_content,
            db=db,
            force_stable=ai_force_stable_model if ai_force_stable_model is not None else True,
            ensure_chinese_output=ai_ensure_chinese_output if ai_ensure_chinese_output is not None else True
        )
        
        if not ai_response.success or not isinstance(ai_response.content, AITextAnalysisOutput):
            error_msg = ai_response.error_message or "AI text analysis returned unsuccessful or invalid content type."
            logger.error(f"文本分析失敗 for doc ID {doc_uuid}: {error_msg}")
            new_status = DocumentStatus.ANALYSIS_FAILED
            return None, None, None, new_status # analysis_data_to_save remains None
            
        ai_text_output = ai_response.content
        token_usage_to_save = ai_response.token_usage
        model_used_for_analysis = ai_response.model_used
        analysis_data_to_save = ai_text_output.model_dump()
        
        log_message = f"文本 AI 分析成功完成 (doc ID: {doc_uuid})"
        if ai_text_output.error_message or \
           (hasattr(ai_text_output, 'content_type') and "Error" in str(ai_text_output.content_type)):
            new_status = DocumentStatus.ANALYSIS_FAILED
            log_message = f"文本 AI 分析失敗或返回錯誤 (doc ID: {doc_uuid}): {ai_text_output.error_message or ai_text_output.initial_summary[:100]}"
        else:
            new_status = DocumentStatus.ANALYSIS_COMPLETED
        logger.info(log_message)

    except Exception as e:
        logger.error(f"Unexpected error during text processing for doc ID {doc_uuid}: {e}", exc_info=True)
        new_status = DocumentStatus.PROCESSING_ERROR
        # analysis_data_to_save remains None

    return analysis_data_to_save, token_usage_to_save, model_used_for_analysis, new_status

async def _save_analysis_results(
    document: Document, 
    db: AsyncIOMotorDatabase, 
    user_id_for_log: str, 
    request_id_for_log: Optional[str], 
    analysis_data: Optional[Dict[str, Any]], 
    token_usage: Optional[TokenUsage], 
    model_used: Optional[str], 
    processing_status: DocumentStatus, 
    processing_type: str # e.g., "image_analysis", "text_analysis", "unsupported"
) -> None:
    """
    Saves the AI analysis results to the database and logs the outcome.
    Updates document status based on the processing outcome.
    """
    doc_uuid = document.id
    log_message = f"Processing for doc ID {doc_uuid} concluded with status {processing_status.value}."

    try:
        if analysis_data and token_usage and processing_status in [DocumentStatus.ANALYSIS_COMPLETED, DocumentStatus.ANALYSIS_FAILED]:
            await crud_documents.set_document_analysis(
                db=db,
                document_id=doc_uuid,
                analysis_data_dict=analysis_data,
                token_usage_dict=token_usage.model_dump(),
                model_used_str=model_used,
                analysis_status_enum=processing_status, # This is new_status from the caller
                analyzed_content_type_str=analysis_data.get("content_type", "Unknown")
            )
            # Specific log message based on status was handled by callers of this function before,
            # now we create a more generic one or pass it in.
            # For now, using a generic one, assuming specific success/failure messages are in processing helpers.
            if processing_status == DocumentStatus.ANALYSIS_COMPLETED:
                log_message = f"AI {processing_type} successfully completed for doc ID {doc_uuid}."
            else: # ANALYSIS_FAILED
                log_message = f"AI {processing_type} failed for doc ID {doc_uuid}. Analysis data may contain error details."
            
            logger.info(log_message)
            await log_event(
                db=db,
                level=LogLevel.INFO if processing_status == DocumentStatus.ANALYSIS_COMPLETED else LogLevel.ERROR,
                message=log_message, 
                source=f"doc_processing.save_results.{processing_type}.complete",
                user_id=user_id_for_log, request_id=request_id_for_log,
                details={"doc_id": str(doc_uuid), "status": processing_status.value, "tokens": token_usage.total_tokens if token_usage else 0}
            )
        elif processing_status != DocumentStatus.ANALYZING: # e.g. EXTRACTION_FAILED, PROCESSING_ERROR from sub-helpers, or UNSUPPORTED
            # This branch handles cases where processing concluded with an error before full AI analysis,
            # or if the type was unsupported. The status might have been set by helpers, 
            # or it's set here if it's an "unsupported" type scenario.
            logger.info(f"Document {document.id} processing concluded with status: {processing_status.value}. No new AI analysis data saved at this stage. Ensuring status is updated.")
            await crud_documents.update_document_status(
                db, 
                document.id, 
                processing_status, 
                f"Processing concluded with status: {processing_status.value}" # Or a more specific error if available and passed
            )
            await log_event(
                db=db,
                level=LogLevel.WARNING if processing_status not in [DocumentStatus.ANALYSIS_COMPLETED, DocumentStatus.TEXT_EXTRACTED] else LogLevel.INFO, # Adjust level based on status
                message=f"Document {document.id} final status {processing_status.value} set without new AI analysis data.",
                source=f"doc_processing.save_results.{processing_type}.status_update_only",
                user_id=user_id_for_log,
                request_id=request_id_for_log,
                details={"doc_id": str(document.id), "final_status": processing_status.value}
            )
        else: # Status is ANALYZING, but no data or token usage, or other unexpected state
            final_status = DocumentStatus.PROCESSING_ERROR
            error_details = "Unknown processing error or status not finalized correctly by helpers."
            logger.error(f"Document {doc_uuid} processing finished unexpectedly. Status: {processing_status}. Analysis Data: {bool(analysis_data)}. Token Usage: {bool(token_usage)}. {error_details}")
            await crud_documents.update_document_status(db, doc_uuid, final_status, error_details)
            await log_event(
                db=db, level=LogLevel.ERROR, 
                message=f"Unknown error or state issue for doc ID {doc_uuid}: {error_details}",
                source="doc_processing.save_results.unknown_error",
                user_id=user_id_for_log, request_id=request_id_for_log,
                details={"doc_id": str(doc_uuid), "attempted_status": processing_status.value, "final_status": final_status.value}
            )
    except Exception as e:
        logger.error(f"Error saving analysis results for doc ID {doc_uuid}: {e}", exc_info=True)
        try:
            await crud_documents.update_document_status(db, doc_uuid, DocumentStatus.PROCESSING_ERROR, f"Failed to save analysis results: {str(e)[:50]}")
        except Exception as db_update_err:
            logger.error(f"CRITICAL: Failed to update document status to error after failing to save analysis results for doc ID {doc_uuid}: {db_update_err}", exc_info=True)
        await log_event(
            db=db, level=LogLevel.CRITICAL, message=f"Critial error saving analysis results for doc ID {doc_uuid}: {str(e)}",
            source="doc_processing.save_results.critical_save_failure",
            user_id=user_id_for_log, request_id=request_id_for_log,
            details={"doc_id": str(doc_uuid), "error": str(e)}
        )

# 修改後的後台任務處理函數
async def _process_document_analysis_or_extraction(
    doc_id: str, # Keep original doc_id string for the helper
    db: AsyncIOMotorDatabase, 
    user_id_for_log: str, 
    request_id_for_log: Optional[str], 
    trigger_content_processing: bool = False,
    ai_force_stable_model: Optional[bool] = None,
    ai_ensure_chinese_output: Optional[bool] = True
) -> None:
    """
    後台任務：根據文件MIME類型處理文件內容（文本提取/AI分析等）
    """
    document = await _setup_and_validate_document_for_processing(
        doc_id_str=doc_id, # Pass the original string doc_id
        db=db,
        user_id_for_log=user_id_for_log,
        request_id_for_log=request_id_for_log
    )

    if document is None:
        return # Setup and validation failed, errors already logged by helper

    doc_uuid = document.id # Now a UUID
    doc_mime_type = document.file_type
    
    logger.info(f"Background task starting processing for document ID (UUID): {doc_uuid}, Original passed ID: {doc_id}")

    analysis_data_to_save: Optional[Dict[str, Any]] = None
    token_usage_to_save: Optional[TokenUsage] = None
    model_used_for_analysis: Optional[str] = None
    # new_status will be determined by the processing helpers
    current_processing_status = DocumentStatus.ANALYZING # Initial status before specific processing
    processing_type = "unknown"
    
    try:
        if doc_mime_type and doc_mime_type in SUPPORTED_IMAGE_TYPES_FOR_AI.values():
            processing_type = "image_analysis"
            analysis_data_to_save, token_usage_to_save, model_used_for_analysis, current_processing_status = \
                await _process_image_document(
                    document=document, db=db, user_id_for_log=user_id_for_log, request_id_for_log=request_id_for_log,
                    ai_force_stable_model=ai_force_stable_model, ai_ensure_chinese_output=ai_ensure_chinese_output
                )
        elif doc_mime_type and doc_mime_type in SUPPORTED_TEXT_TYPES_FOR_AI_PROCESSING:
            processing_type = "text_analysis"
            analysis_data_to_save, token_usage_to_save, model_used_for_analysis, current_processing_status = \
                await _process_text_document(
                    document=document, db=db, user_id_for_log=user_id_for_log, request_id_for_log=request_id_for_log,
                    settings_obj=settings, ai_force_stable_model=ai_force_stable_model, ai_ensure_chinese_output=ai_ensure_chinese_output
                )
        else:
            processing_type = "unsupported"
            logger.warning(f"Document ID: {doc_uuid} 的 MIME 類型 '{doc_mime_type}' 不支持 AI 分析。")
            current_processing_status = DocumentStatus.PROCESSING_ERROR # Set status before saving
            # No specific analysis data, so pass None for data, tokens, model
            # _save_analysis_results will handle logging and status update for unsupported type
            # Fall through to _save_analysis_results which will handle unsupported type status update
            
        # Call the centralized function to save results and log events
        await _save_analysis_results(
            document=document, db=db, user_id_for_log=user_id_for_log, request_id_for_log=request_id_for_log,
            analysis_data=analysis_data_to_save, 
            token_usage=token_usage_to_save, 
            model_used=model_used_for_analysis,
            processing_status=current_processing_status, # Pass the determined status
            processing_type=processing_type
        )

    except Exception as e: # Catch errors from _process_image/text_document or other unexpected issues
        # This block is now for truly unexpected errors not caught by sub-helpers or _save_analysis_results
        final_error_status = DocumentStatus.PROCESSING_ERROR
        error_details = f"後台任務處理文檔 {doc_uuid} 時發生頂層嚴重錯誤: {str(e)[:100]}"
        logger.error(error_details, exc_info=True)
        
        try:
            await crud_documents.update_document_status(db, doc_uuid, final_error_status, error_details)
        except Exception as db_error_in_handler:
            logger.error(f"CRITICAL: 在處理頂層錯誤後更新文檔 {doc_uuid} 狀態時再次失敗: {db_error_in_handler}", exc_info=True)

        await log_event(
            db=db, level=LogLevel.CRITICAL, message=error_details,
            source=f"doc_processing.bg_task.main_handler_critical_error",
            user_id=user_id_for_log, request_id=request_id_for_log,
            details={"doc_id": str(doc_uuid), "error": str(e)}
        )

@router.patch("/{document_id}", response_model=Document, summary="更新文件信息或觸發操作")
async def update_document_details(
    request: Request,
    doc_update: DocumentUpdate, 
    background_tasks: BackgroundTasks,
    existing_document: Document = Depends(get_owned_document), # Use the dependency
    db: AsyncIOMotorDatabase = Depends(get_db), # Still needed for operations
    current_user: User = Depends(get_current_active_user), # Still needed for logging user
    settings_di: Settings = Depends(get_settings) # Still needed for settings
    # document_id is now part of existing_document.id
):
    # existing_document is now provided by the get_owned_document dependency
    # The checks for existence and ownership are handled by the dependency.
    document_id = existing_document.id # Use existing_document.id for document_id

    update_fields = doc_update.model_dump(exclude_unset=True)
    
    # 獲取 request_id
    request_id_for_log: Optional[str] = None
    if hasattr(request.state, 'request_id'):
        request_id_for_log = request.state.request_id
    elif request.headers.get("X-Request-ID"): # 作為備份
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
                _process_document_analysis_or_extraction,
                doc_id=str(document_id), # 傳遞原始 string ID
                db=db, # 傳遞 DB 實例
                user_id_for_log=str(current_user.id), # 傳遞用戶 ID
                request_id_for_log=request_id_for_log, # 傳遞請求 ID
                trigger_content_processing=doc_update.trigger_content_processing,
                ai_force_stable_model=doc_update.ai_force_stable_model if doc_update.ai_force_stable_model is not None else True,
                ai_ensure_chinese_output=doc_update.ai_ensure_chinese_output if doc_update.ai_ensure_chinese_output is not None else True
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
            message=f"資料庫記錄刪除失敗，但文件可能仍存在: {document_id} (user {user_id_for_log_str})",
            source="documents_api",
            user_id=user_id_for_log_str, 
            request_id=request_id_for_log, 
            details={"document_id": str(document_id), "file_path": file_path_to_delete}
        )
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="刪除文件記錄時發生錯誤")

    # 從向量數據庫中刪除向量化數據
    try:
        document_id_str = str(document_id)
        logger.info(f"嘗試從向量數據庫刪除文檔 {document_id_str} 的向量...")
        vector_delete_success = vector_db_service.delete_by_document_id(document_id_str)
        if vector_delete_success:
            logger.info(f"成功從向量數據庫刪除文檔 {document_id_str} 的向量")
            await log_event(
                db=db, level=LogLevel.INFO, 
                message=f"向量數據已成功刪除: 文檔 {document_id_str} (user {user_id_for_log_str})",
                source="documents_api_delete_vector", 
                user_id=user_id_for_log_str, 
                request_id=request_id_for_log, 
                details={"document_id": document_id_str}
            )
        else:
            logger.warning(f"從向量數據庫刪除文檔 {document_id_str} 的向量時可能遇到問題")
            await log_event(
                db=db, level=LogLevel.WARNING, 
                message=f"向量數據刪除可能不完整: 文檔 {document_id_str} (user {user_id_for_log_str})",
                source="documents_api_delete_vector_warning", 
                user_id=user_id_for_log_str, 
                request_id=request_id_for_log, 
                details={"document_id": document_id_str}
            )
    except Exception as e:
        logger.error(f"從向量數據庫刪除文檔 {document_id} 的向量時發生錯誤: {e}")
        await log_event(
            db=db, level=LogLevel.ERROR, 
            message=f"向量數據刪除失敗: 文檔 {document_id} 錯誤: {str(e)} (user {user_id_for_log_str})",
            source="documents_api_delete_vector_error", 
            user_id=user_id_for_log_str, 
            request_id=request_id_for_log, 
            details={"document_id": str(document_id), "error": str(e)}
        )
        # 不會因為向量刪除失敗而中斷整個刪除流程，只記錄錯誤

    if file_path_to_delete and os.path.exists(file_path_to_delete):
        try:
            os.remove(file_path_to_delete)
            await log_event(
                db=db, level=LogLevel.INFO, 
                message=f"文件實體成功刪除: {file_path_to_delete} (user {user_id_for_log_str})",
                source="documents_api_delete_file", 
                user_id=user_id_for_log_str, 
                request_id=request_id_for_log, 
                details={"document_id": str(document_id), "file_path": file_path_to_delete}
            )
        except Exception as e:
            await log_event(
                db=db, level=LogLevel.ERROR, 
                message=f"文件實體刪除失敗: {file_path_to_delete}. 錯誤: {str(e)} (user {user_id_for_log_str})",
                source="documents_api_delete_file_error", 
                user_id=user_id_for_log_str, 
                request_id=request_id_for_log, 
                details={"document_id": str(document_id), "file_path": file_path_to_delete, "error": str(e)}
            )
    elif file_path_to_delete: # 路徑存在但文件不存在
        await log_event(
            db=db, level=LogLevel.WARNING, 
            message=f"文件實體在指定路徑未找到，無法刪除: {file_path_to_delete} (user {user_id_for_log_str})",
            source="documents_api_delete_file_not_found", 
            user_id=user_id_for_log_str, 
            request_id=request_id_for_log, 
            details={"document_id": str(document_id), "file_path": file_path_to_delete}
        )
    else: # file_path_to_delete 為 None
        await log_event(
            db=db, level=LogLevel.WARNING, 
            message=f"文件記錄沒有有效的 file_path，無法嘗試刪除實體文件. Document ID: {document_id} (user {user_id_for_log_str})",
            source="documents_api_delete_file_no_path", 
            user_id=user_id_for_log_str, 
            request_id=request_id_for_log, 
            details={"document_id": str(document_id)}
        )
    return 

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
                    db=db, level=LogLevel.INFO, 
                    message=f"批量刪除：成功從向量數據庫移除文檔 {doc_id_str} 的向量 (user {user_id_for_log_str})",
                    source="batch_delete_documents_vector_success", 
                    user_id=user_id_for_log_str, 
                    request_id=None, # 批量操作可能沒有明確的 request_id
                    details={"document_id": doc_id_str}
                )
            else:
                # 這可能意味著刪除操作在ChromaDB內部失敗，或者文檔本來就不在裡面
                # delete_by_document_id 目前的實現是如果未找到也返回 True
                logger.info(f"批量刪除：從向量數據庫移除文檔 {doc_id_str} 的向量（可能本來就不存在或操作未成功）。")
        except Exception as e_vector:
            logger.error(f"批量刪除：從向量數據庫移除文檔 {doc_id_str} 的向量時發生錯誤: {e_vector}")
            # 記錄向量刪除錯誤，但不將其視為整個文件刪除操作的失敗
            await log_event(
                db=db, level=LogLevel.ERROR, 
                message=f"批量刪除：從向量數據庫移除文檔 {doc_id_str} 的向量時發生錯誤: {str(e_vector)} (user {user_id_for_log_str})",
                source="batch_delete_documents_vector_error", 
                user_id=user_id_for_log_str, 
                request_id=None, 
                details={"document_id": doc_id_str, "error": str(e_vector)}
            )

        if not delete_error: # 如果核心的DB刪除成功了
            success_count += 1
            action_details.append(BatchDeleteResponseDetail(id=doc_id_uuid, status="deleted", message="文件已成功刪除"))
        # 如果 delete_error 為 True，則相應的錯誤信息已在上面添加

    final_message = f"批量刪除操作完成。總共請求處理 {processed_count} 個文件。成功刪除 {success_count} 個。"
    overall_success = processed_count == success_count and processed_count > 0

    if processed_count == 0:
        final_message = "沒有提供要刪除的文件ID。"
        overall_success = False # 或者 True 如果認為空請求是成功的
        # raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="沒有提供要刪除的文件ID。")


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

# @router.post("/{document_id}/trigger-analysis", response_model=Document, summary="觸發AI分析")
# async def trigger_ai_analysis_endpoint(...):
#     ... 

# ... (其他後續代碼如觸發端點註釋保持不變) 