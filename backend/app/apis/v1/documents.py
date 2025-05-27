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

from ...dependencies import get_db, get_document_processing_service, get_settings, get_unified_ai_service # <--- 更新導入
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
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/markdown" # Added markdown as it's a text format
]

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

    user_folder = Path(settings.UPLOAD_DIR) / str(current_user.id) # <--- 修改此行
    user_folder.mkdir(parents=True, exist_ok=True)

    original_filename = file.filename if file.filename else "untitled"
    base_name, ext = os.path.splitext(original_filename)
    safe_base_name = secure_filename(base_name) if base_name else ""
    
    # 嘗試從原始文件名獲取擴展名，如果沒有，則從 MIME 類型猜測
    # secure_filename 通常會移除非 ASCII 字符，可能也會影響擴展名的點
    # 因此，我們最好分別處理基本名稱和擴展名

    # 清理原始擴展名 (去除點)
    if ext:
        safe_ext = ext.lower().lstrip('.')
    else:
        safe_ext = ""

    # 如果 secure_filename 清除了基本名稱，或者原始文件名就沒有基本名稱
    if not safe_base_name:
        safe_base_name = f"file_{uuid.uuid4().hex[:8]}"

    # 檢查 MIME 類型和擴展名是否匹配，或者是否缺少擴展名
    guessed_ext_from_mime = mimetypes.guess_extension(file.content_type) if file.content_type else None
    if guessed_ext_from_mime:
        guessed_ext_from_mime = guessed_ext_from_mime.lstrip('.')

    final_ext = ""
    if safe_ext: # 如果原始文件有擴展名
        # 可以選擇性地驗證 safe_ext 是否與 guessed_ext_from_mime 匹配或是否為已知類型
        # 這裡我們優先使用原始擴展名（清理後），除非它看起來不對
        final_ext = safe_ext
        # 如果原始擴展名和MIME猜測的擴展名不一致，可能需要警告或特殊處理
        # 例如，如果上傳 .jpg 但MIME是 png，這裡可以做決策
        # 目前簡單化：如果原始的有，就用原始的（小寫化，去除了點）
    elif guessed_ext_from_mime:
        final_ext = guessed_ext_from_mime
    else:
        # 最後的備份，如果MIME類型未知或無法猜測擴展名
        final_ext = "bin" # 或者 file.content_type.split('/')[-1] 如果確定 content_type 總是有值

    safe_filename = f"{safe_base_name}.{final_ext}"

    # 確保最終文件名仍然是安全的 (雖然各部分已經處理過，但多一層保障)
    # 實際上，因為我們是拼接 safe_base_name 和 final_ext，這可能不需要再次調用 secure_filename
    # safe_filename = secure_filename(safe_filename) 
    # 註：再次調用 secure_filename 可能會把我們剛加上的點和擴展名弄亂，所以要小心
    # 這裡我們假設 safe_base_name 和 final_ext 已經是安全的組件了。

    file_path = user_folder / safe_filename
    file_size = 0

    try:
        # 使用 aiofiles 進行異步文件寫入
        async with aiofiles.open(file_path, 'wb') as out_file:
            content = await file.read()  # 讀取文件內容
            await out_file.write(content) # 寫入磁盤
            file_size = len(content) # 獲取文件大小
        logger.info(f"文件 '{safe_filename}' 已保存到 '{file_path}'，大小: {file_size} bytes")
        
        # 初始化為上傳文件的聲明內容類型
        actual_content_type = file.content_type
        mime_type_warning = None
        original_mime_type = None
        
        # 檢查文件大小是否為 0
        if file_size == 0:
            logger.warning(f"警告：上傳的文件 '{safe_filename}' 大小為 0 字節")
            mime_type_warning = "文件大小為 0 字節，這可能不是一個有效的文件。"
            actual_content_type = "application/octet-stream" # 將空文件視為二進制文件
        # 若文件宣稱是 Office 文件或 PDF 等格式，但實際上不是有效的格式，則進行檢查
        elif file.content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document" or \
            file.content_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" or \
            file.content_type == "application/vnd.openxmlformats-officedocument.presentationml.presentation":
            # 檢查是否是有效的 ZIP 文件（Office 文件實際上是 ZIP 格式的容器）
            try:
                import zipfile
                # 同步方式直接檢查文件，因為這是驗證步驟
                with zipfile.ZipFile(file_path, 'r') as zip_check:
                    # 只需嘗試讀取 ZIP 內容列表，如果成功則文件有效
                    zip_check.namelist()
                logger.info(f"已驗證 '{safe_filename}' 是有效的 Office 文件格式")
            except zipfile.BadZipFile:
                logger.warning(f"文件 '{safe_filename}' 聲稱是 Office 格式，但不是有效的 ZIP 格式。MIME 類型: {file.content_type}")
                # 不要嘗試修改 file.content_type，它是唯讀的
                original_mime_type = file.content_type
                actual_content_type = "application/octet-stream"
                # 準備在之後的 document_data 中添加一個提示，以便後續處理知道文件可能不是聲稱的格式
                mime_type_warning = f"文件聲稱是 {original_mime_type}，但驗證失敗。已作為二進制文件處理。"
                logger.warning(mime_type_warning)
                await log_event(
                    db=db,
                    level=LogLevel.WARNING,
                    message=mime_type_warning,
                    source="documents.upload.validate_file",
                    user_id=str(current_user.id),
                    request_id=request.state.request_id if hasattr(request.state, 'request_id') else None,
                    details={"filename": safe_filename, "original_mime_type": original_mime_type, "new_mime_type": actual_content_type}
                )
        elif file.content_type == "application/pdf":
            # 可選：檢查 PDF 有效性
            pass
    except Exception as e:
        logger.error(f"保存文件 '{safe_filename}' 到 '{file_path}' 失敗: {e}")
        # 考慮是否刪除部分寫入的文件
        if file_path.exists():
            file_path.unlink(missing_ok=True)
        await log_event(
            db=db, # 確保傳遞了 db session
            level=LogLevel.ERROR,
            message=f"保存文件 '{safe_filename}' 失敗: {str(e)}",
            source="documents.upload.save_file",
            user_id=str(current_user.id), # <--- 確認轉換為 str
            request_id=request.state.request_id if hasattr(request.state, 'request_id') else None,
            details={"filename": safe_filename, "target_path": str(file_path)}
        )
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"無法保存文件: {safe_filename}")
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

# 修改後的後台任務處理函數
async def _process_document_analysis_or_extraction(
    doc_id: str,
    db: AsyncIOMotorDatabase, # 直接傳遞 DB 實例
    user_id_for_log: str, # 直接傳遞用戶 ID
    request_id_for_log: Optional[str], # 直接傳遞請求 ID
    trigger_content_processing: bool = False,
    ai_force_stable_model: Optional[bool] = None,
    ai_ensure_chinese_output: Optional[bool] = True
    # background_tasks: BackgroundTasks = None, # 不再需要，因為不會在背景任務內部再添加任務
    # current_user: User = Depends(get_current_active_user), # 不能在背景任務中使用 Depends
) -> None:
    """
    後台任務：根據文件MIME類型處理文件內容（文本提取/AI分析等）
    """
    doc_uuid: Optional[uuid.UUID] = None # Declare here for broader scope, especially for logging in final except
    try:
        # 強制重新載入 AI 配置 - 確保從資料庫獲取最新的用戶偏好設定
        await unified_ai_config.reload_task_configs(db)
        logger.info(f"AI配置已重新載入，全局偏好: {unified_ai_config._user_global_ai_preferences}")
        
        # 將字串ID轉換為UUID以確保一致性
        try:
            doc_uuid = uuid.UUID(doc_id)
            logger.info(f"Background task: Converted doc_id string '{doc_id}' to UUID '{doc_uuid}'")
        except ValueError:
            logger.error(f"Background task: Invalid UUID string for doc_id: {doc_id}. Cannot proceed.")
            await log_event(
                db=db, level=LogLevel.CRITICAL, message=f"Invalid document ID format '{doc_id}' in background task, cannot update status.",
                source="doc_processing.bg_task.id_conversion_error", 
                user_id=user_id_for_log, # 使用傳入的 user_id
                request_id=request_id_for_log, # 使用傳入的 request_id
                details={"original_doc_id": str(doc_id)}
            )
            return
    except Exception as e: # Handling errors from AI config reload or other initial setup issues
        logger.error(f"處理文檔 ID {doc_id} 的後台任務時發生初始設定錯誤 (例如 AI 配置重載): {e}", exc_info=True)
        await log_event(
            db=db, level=LogLevel.CRITICAL,
            message=f"後台任務初始設定失敗 for doc_id '{doc_id}': {str(e)}",
            source="doc_processing.bg_task.initial_setup_error",
            user_id=user_id_for_log,
            request_id=request_id_for_log,
            details={"original_doc_id": str(doc_id), "error_details": str(e)}
        )
        return

    # logger.info(f"Background task started for document ID (UUID): {doc_uuid}, Original passed ID: {doc_id}")
    # 將此日誌移到 doc_uuid 確定有效之後

    analysis_data_to_save: Optional[Dict[str, Any]] = None
    token_usage_to_save: Optional[TokenUsage] = None
    model_used_for_analysis: Optional[str] = None
    new_status = DocumentStatus.ANALYZING
    extracted_text_content: Optional[str] = None
    processing_type = "unknown"
    # 將 doc_uuid 的聲明提前，並在 try 塊中賦值
    # doc_uuid: Optional[uuid.UUID] = None # 已提前

    try:
        # 在這裡重新確認 doc_uuid 是否已成功轉換，如果沒有則無法繼續
        if doc_uuid is None: # 如果上面的 try-except 捕獲了轉換錯誤並返回，這裡不會執行
            # 但如果上面的 try-except 結構改變，需要確保 doc_uuid 有效
            logger.error(f"Background task: doc_uuid is None for doc_id {doc_id}, cannot proceed with processing.")
            return # 提早退出

        logger.info(f"Background task started for document ID (UUID): {doc_uuid}, Original passed ID: {doc_id}")

        # 獲取文檔的實際文件路徑
        document_from_db = await crud_documents.get_document_by_id(db, doc_uuid)
        if not document_from_db or not document_from_db.file_path:
            logger.error(f"無法獲取文件路徑或文檔不存在於DB: ID {doc_uuid}")
            await crud_documents.update_document_status(db, doc_uuid, DocumentStatus.PROCESSING_ERROR, "文件記錄或路徑丟失")
            await log_event(db=db, level=LogLevel.ERROR, message=f"文件處理失敗: 文件記錄或路徑丟失 for {doc_uuid}",
                            source="doc_processing.bg_task.path_retrieval", user_id=user_id_for_log, request_id=request_id_for_log)
            return
        
        doc_file_path_str = document_from_db.file_path
        doc_mime_type = document_from_db.file_type # 從數據庫獲取MIME類型

        doc_path = Path(doc_file_path_str) # 使用從DB獲取的文件路徑
        if not doc_path.exists():
            logger.error(f"Document file not found at path: {doc_file_path_str} for doc ID: {doc_uuid}")
            new_status = DocumentStatus.PROCESSING_ERROR
            await crud_documents.update_document_status(
                db=db, document_id=doc_uuid, new_status=new_status, error_details="文件未找到，無法處理"
            )
            await log_event(
                db=db, level=LogLevel.ERROR, message=f"文件處理失敗: 文件不存在 {doc_file_path_str}",
                source="doc_processing.bg_task.file_not_found", user_id=user_id_for_log, request_id=request_id_for_log,
                details={"doc_id": str(doc_uuid), "path": doc_file_path_str}
            )
            return

        # 使用從DB獲取的MIME類型，而不是依賴文件後綴
        # 注意：SUPPORTED_IMAGE_TYPES_FOR_AI 之前是字典，現在需要檢查其結構或使用方法
        # 假設 SUPPORTED_IMAGE_TYPES_FOR_AI 是一個MIME類型列表/集合
        # 更新：SUPPORTED_IMAGE_TYPES_FOR_AI 是一個字典，鍵是後綴，值是MIME類型。
        # 我們應該檢查 doc_mime_type 是否在該字典的值中。
        if doc_mime_type and doc_mime_type in SUPPORTED_IMAGE_TYPES_FOR_AI.values():
            processing_type = "image_analysis"
            logger.info(f"Performing AI image analysis for document ID: {doc_uuid}, MIME: {doc_mime_type}")
            
            # 獲取 DocumentProcessingService 實例 (如果尚未在頂層注入)
            # 這裡我們假設它是可用的，或者需要調整依賴注入方式以適應背景任務
            # 由於我們無法在背景任務中直接使用 Depends，doc_processing_service 需要被傳遞或在此處創建
            # 暫時假設我們能在某處獲得 service 實例，或其方法是靜態/可導入的
            # 如果 get_document_processing_service 是一個簡單的工廠函數，可以嘗試調用它
            # 但它通常需要 settings。更安全的做法是從調用者傳遞 service 或其必要組件。
            # 為了簡化，我們假設 get_image_bytes 可以被調用。
            # 在實際應用中，service 的依賴需要被妥善管理。
            temp_doc_processing_service = DocumentProcessingService() # 臨時創建實例，移除 settings 參數

            image_bytes = await temp_doc_processing_service.get_image_bytes(doc_file_path_str)
            if not image_bytes:
                raise ValueError("無法讀取圖片文件字節數據")

            ai_response = await unified_ai_service_simplified.analyze_image(
                image_data=image_bytes, image_mime_type=doc_mime_type, db=db,
                force_stable=ai_force_stable_model if ai_force_stable_model is not None else True,
                ensure_chinese_output=ai_ensure_chinese_output if ai_ensure_chinese_output is not None else True
            )
            
            if not ai_response.success:
                raise ValueError(f"圖片分析失敗: {ai_response.error_message}")
            
            ai_image_output = ai_response.content
            token_usage = ai_response.token_usage
            token_usage_to_save = token_usage
            model_used_for_analysis = ai_response.model_used
            analysis_data_to_save = ai_image_output.model_dump()
            log_message = f"圖片 AI 分析成功完成 (doc ID: {doc_uuid})"
            if ai_image_output.error_message or "Error" in ai_image_output.content_type:
                new_status = DocumentStatus.ANALYSIS_FAILED
                log_message = f"圖片 AI 分析失敗或返回錯誤 (doc ID: {doc_uuid}): {ai_image_output.error_message or ai_image_output.initial_description[:100]}"
            else:
                new_status = DocumentStatus.ANALYSIS_COMPLETED

        elif doc_mime_type and doc_mime_type in SUPPORTED_TEXT_TYPES_FOR_AI_PROCESSING:
            processing_type = "text_analysis"
            logger.info(f"Performing text extraction and AI analysis for document ID: {doc_uuid}, MIME: {doc_mime_type}")
            extraction_status: DocumentStatus
            extraction_error: Optional[str]
            
            # 獲取服務實例
            doc_processing_service_instance = get_document_processing_service() 
            extracted_text_result, extraction_status, extraction_error = await doc_processing_service_instance.extract_text_from_document(str(doc_path), doc_path.suffix)

            if extraction_status == DocumentStatus.PROCESSING_ERROR or not extracted_text_result or not extracted_text_result.strip():
                logger.error(f"從文檔 {doc_uuid} ({doc_mime_type}) 提取文本時出錯或結果為空: {extraction_error or '無有效文本內容'}", exc_info=bool(extraction_error))
                new_status = DocumentStatus.EXTRACTION_FAILED
                await crud_documents.update_document_status(
                    db=db,
                    document_id=doc_uuid,
                    new_status=new_status,
                    error_details=extraction_error or "未能從文件中提取到有效文本內容"
                )
                await log_event(
                    db=db,
                    level=LogLevel.ERROR,
                    message=f"文本提取失敗/結果為空: {extraction_error or '無有效文本內容'}",
                    source="doc_processing.bg_task.text_extraction",
                    user_id=user_id_for_log,
                    request_id=request_id_for_log,
                    details={"doc_id": str(doc_uuid)}
                )
                return

            extracted_text_content = extracted_text_result
            await crud_documents.update_document_on_extraction_success(db, doc_uuid, extracted_text_content)
            logger.info(f"成功從 {doc_uuid} 提取 {len(extracted_text_content)} 字元的文本。開始 AI 分析...")

            max_prompt_len = settings.AI_MAX_INPUT_CHARS_TEXT_ANALYSIS
            if len(extracted_text_content) > max_prompt_len:
                logger.warning(f"提取的文本長度 ({len(extracted_text_content)}) 超過最大允許長度 ({max_prompt_len})。將進行截斷。 Doc ID: {doc_uuid}")
                extracted_text_content = extracted_text_content[:max_prompt_len]

            # 使用統一AI服務進行文本分析
            ai_response = await unified_ai_service_simplified.analyze_text(
                text_content=extracted_text_content,
                db=db,
                force_stable=ai_force_stable_model if ai_force_stable_model is not None else True,             # <--- 傳遞參數
                ensure_chinese_output=ai_ensure_chinese_output if ai_ensure_chinese_output is not None else True  # <--- 傳遞參數
            )
            
            if not ai_response.success:
                raise ValueError(f"文本分析失敗: {ai_response.error_message}")
            
            ai_text_output = ai_response.content
            token_usage = ai_response.token_usage
            token_usage_to_save = token_usage
            model_used_for_analysis = ai_response.model_used
            analysis_data_to_save = ai_text_output.model_dump()
            log_message = f"文本 AI 分析成功完成 (doc ID: {doc_uuid})"
            if ai_text_output.error_message or "Error" in ai_text_output.content_type:
                new_status = DocumentStatus.ANALYSIS_FAILED
                log_message = f"文本 AI 分析失敗或返回錯誤 (doc ID: {doc_uuid}): {ai_text_output.error_message or ai_text_output.initial_summary[:100]}"
            else:
                new_status = DocumentStatus.ANALYSIS_COMPLETED
        else:
            processing_type = "unsupported"
            logger.warning(f"Document ID: {doc_uuid} 的 MIME 類型 '{doc_mime_type}' 不支持 AI 分析。")
            new_status = DocumentStatus.PROCESSING_ERROR
            await crud_documents.update_document_status(
                db=db,
                document_id=doc_uuid, 
                new_status=new_status,
                error_details="不支持的文件類型進行 AI 分析"
            )
            await log_event(
                db=db,
                level=LogLevel.WARNING,
                message=f"不支持的 AI 分析文件類型: {doc_mime_type}",
                source="doc_processing.bg_task.unsupported_type",
                user_id=user_id_for_log,
                request_id=request_id_for_log,
                details={"doc_id": str(doc_uuid), "mime_type": doc_mime_type}
            )
            return

        if analysis_data_to_save and token_usage_to_save and new_status in [DocumentStatus.ANALYSIS_COMPLETED, DocumentStatus.ANALYSIS_FAILED]:
            await crud_documents.set_document_analysis(
                db=db,
                document_id=doc_uuid,
                analysis_data_dict=analysis_data_to_save,
                token_usage_dict=token_usage_to_save.model_dump(),
                model_used_str=model_used_for_analysis,
                analysis_status_enum=new_status,
                analyzed_content_type_str=analysis_data_to_save.get("content_type", "Unknown")
            )
            logger.info(log_message) # This log message uses doc_uuid
            await log_event(
                db=db,
                level=LogLevel.INFO if new_status == DocumentStatus.ANALYSIS_COMPLETED else LogLevel.ERROR,
                message=log_message, 
                source=f"doc_processing.bg_task.{processing_type}.complete",
                user_id=user_id_for_log, request_id=request_id_for_log,
                details={"doc_id": str(doc_uuid), "status": new_status.value, "tokens": token_usage_to_save.total_tokens if token_usage_to_save else 0}
            )
        elif new_status != DocumentStatus.ANALYZING and new_status not in [DocumentStatus.ANALYSIS_COMPLETED, DocumentStatus.ANALYSIS_FAILED]: # Check this condition
            logger.info(f"Document {doc_uuid} processing concluded with status: {new_status}. No AI analysis data to save at this stage.")
        else: # This case handles if new_status is still ANALYZING or if analysis_data/token_usage is missing when it shouldn't be.
            logger.error(f"Document {doc_uuid} processing finished unexpectedly. Status: {new_status}. Analysis Data Present: {bool(analysis_data_to_save)}. Token Usage Present: {bool(token_usage_to_save)}. This path should ideally not be reached if status is completed/failed.")
            if new_status == DocumentStatus.ANALYZING: 
                new_status = DocumentStatus.PROCESSING_ERROR 
            await crud_documents.update_document_status(
                db=db,
                document_id=doc_uuid, 
                new_status=new_status, 
                error_details="未知的處理錯誤或狀態未最終化"
            )
            await log_event(
                db=db,
                level=LogLevel.ERROR, 
                message=f"未知的文檔處理錯誤或狀態問題 for doc ID: {doc_uuid}",
                source="doc_processing.bg_task.unknown_error",
                user_id=user_id_for_log,
                request_id=request_id_for_log,
                details={"doc_id": str(doc_uuid), "final_status_attempted": new_status.value}
            )
    except Exception as e:
        logging_doc_id_str = str(doc_uuid if doc_uuid is not None else doc_id) # 使用已轉換的 doc_uuid (如果成功)
        logger.error(f"處理文檔 ID {logging_doc_id_str} 的後台任務時發生嚴重錯誤: {e}", exc_info=True)
        
        final_error_status = DocumentStatus.PROCESSING_ERROR
        id_for_status_update: Optional[uuid.UUID] = doc_uuid # 使用已轉換的 doc_uuid (如果成功)
        
        if id_for_status_update is None and isinstance(doc_id, str): # 如果轉換失敗，嘗試再次轉換原始 doc_id
            try: id_for_status_update = uuid.UUID(doc_id)
            except ValueError: pass

        if id_for_status_update:
            try:
                await crud_documents.update_document_status(
                    db=db, document_id=id_for_status_update, new_status=final_error_status,
                    error_details=f"後台任務嚴重失敗: {str(e)[:100]}"
                )
            except Exception as db_error_in_handler:
                 logger.error(f"在處理嚴重錯誤後更新文檔 {id_for_status_update} 狀態時再次失敗: {db_error_in_handler}", exc_info=True)
        else:
            logger.error(f"CRITICAL: Could not determine a valid UUID for doc_id '{doc_id}' to update status after critical error.")

        await log_event(
            db=db, level=LogLevel.ERROR, message=f"文檔處理後台任務嚴重失敗 for ID '{logging_doc_id_str}': {str(e)}",
            source=f"doc_processing.bg_task.{processing_type if processing_type != 'unknown' else 'general'}.critical_error",
            user_id=user_id_for_log, request_id=request_id_for_log,
            details={"doc_id": logging_doc_id_str, "error": str(e)}
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