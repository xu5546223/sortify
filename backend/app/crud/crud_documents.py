from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid
import re # 用於不區分大小寫的搜尋
import logging

from ..models.document_models import (
    DocumentCreate, 
    Document, 
    DocumentStatus, 
    VectorStatus, # <-- Import VectorStatus
    DocumentInDBBase, # 用於構建更新返回
    # DocumentAnalysis # 移除此處的導入，因為函數參數類型改變
)
from ..core.config import settings
from ..core.logging_utils import AppLogger, log_event # Added log_event
from ..models.log_models import LogLevel # Added LogLevel
# from ..models.ai_models import AIImageAnalysisOutput # 移除此導入

DOCUMENT_COLLECTION = "documents"

# 初始化logger
logger = AppLogger(__name__, level=logging.INFO).get_logger()

def _build_document_filter_query(
    owner_id: uuid.UUID,
    uploader_device_id: Optional[str] = None,
    status_in: Optional[List[DocumentStatus]] = None,
    filename_contains: Optional[str] = None,
    tags_include: Optional[List[str]] = None
) -> Dict[str, Any]:
    query: Dict[str, Any] = {"owner_id": owner_id}
    if uploader_device_id:
        query["uploader_device_id"] = uploader_device_id
    if status_in:
        query["status"] = {"$in": [s.value for s in status_in]}
    if filename_contains:
        query["filename"] = {"$regex": re.escape(filename_contains), "$options": "i"}
    if tags_include and len(tags_include) > 0:
        query["tags"] = {"$in": tags_include}
    return query

async def create_document(
    db: AsyncIOMotorDatabase, 
    document_data: DocumentCreate, 
    owner_id: uuid.UUID, # 新增 owner_id
    uploader_device_id: Optional[str] = None,
    file_path: Optional[str] = None # 實際儲存路徑
) -> Document:
    """創建新的文件記錄。"""
    document_id_uuid = uuid.uuid4() # 生成 UUID 對象
    # document_id_str = str(document_id_uuid) # 不再需要此行，id 由模型層處理

    db_document_data = document_data.model_dump()
    db_document_data["_id"] = document_id_uuid # 存儲實際的 UUID 對象到 _id
    # db_document_data["id"] = document_id_str   # <--- 移除此行，讓模型和 root_validator 處理 id
    db_document_data["owner_id"] = owner_id # owner_id 來自參數，應該已是 UUID
    db_document_data["created_at"] = datetime.utcnow()
    db_document_data["updated_at"] = datetime.utcnow()
    db_document_data["status"] = DocumentStatus.UPLOADED
    db_document_data["vector_status"] = VectorStatus.NOT_VECTORIZED.value # <-- Set default vector_status
    db_document_data["uploader_device_id"] = uploader_device_id
    db_document_data["file_path"] = file_path
    
    try:
        await db[DOCUMENT_COLLECTION].insert_one(db_document_data)
        # 從資料庫讀取剛插入的記錄以確保一致性，並轉換為 Document 模型
        created_doc_raw = await db[DOCUMENT_COLLECTION].find_one({"_id": document_id_uuid})
        if created_doc_raw:
            created_document = Document(**created_doc_raw)
            # Log event
            await log_event(
                db=db,
                level=LogLevel.INFO,
                message="Document record created successfully.",
                source="crud_documents.create_document",
                details={
                    "document_id": str(created_document.id),
                    "filename": created_document.filename,
                    "user_id": str(created_document.owner_id) if created_document.owner_id else None
                }
            )
            return created_document
        else:
            # 這種情況理論上不應發生，除非插入後立即被其他操作刪除
            # Log an error here as well, as this is unexpected
            await log_event(
                db=db,
                level=LogLevel.ERROR,
                message="Failed to retrieve document immediately after apparent creation.",
                source="crud_documents.create_document",
                details={"document_data_used": db_document_data} # Log the data used for insertion attempt
            )
            raise Exception("Failed to retrieve document after creation")
    except Exception as e:
        # Log exception during creation process
        await log_event(
            db=db,
            level=LogLevel.ERROR,
            message=f"Exception during document creation: {str(e)}",
            source="crud_documents.create_document",
            details={
                "document_data_attempted": document_data.model_dump(),
                "owner_id": str(owner_id) if owner_id else None,
                "error": str(e),
                "error_type": type(e).__name__
            }
        )
        raise

async def get_document_by_id(db: AsyncIOMotorDatabase, document_id: uuid.UUID) -> Optional[Document]:
    """按 ID 檢索文件。"""
    document_raw = await db[DOCUMENT_COLLECTION].find_one({"_id": document_id})
    if document_raw:
        try:
            doc = Document(**document_raw)
            return doc
        except Exception as e:
            logger.error(f"[get_document_by_id] Error validating document data for ID {document_id}: {e}", exc_info=True)
            return None
    else:
        try:
            # 嘗試使用字串版本的 UUID 查找
            document_id_str = str(document_id)
            document_raw_str_check = await db[DOCUMENT_COLLECTION].find_one({"_id": document_id_str})
            if document_raw_str_check:
                try:
                    doc_str = Document(**document_raw_str_check)
                    return doc_str
                except Exception as e_str:
                    logger.error(f"[get_document_by_id] Error validating document data for string ID {document_id_str}: {e_str}", exc_info=True)
                    return None
        except Exception as fallback_err:
            logger.error(f"[get_document_by_id] Error during string ID fallback find_one: {fallback_err}", exc_info=True)
        return None

async def get_documents(
    db: AsyncIOMotorDatabase, 
    owner_id: uuid.UUID, # 新增 owner_id
    skip: int = 0, 
    limit: int = 100, 
    uploader_device_id: Optional[str] = None, # 此參數可以考慮移除或保留，取決於是否仍有基於設備的查詢需求
    status_in: Optional[List[DocumentStatus]] = None, # <--- 修改此處
    filename_contains: Optional[str] = None,
    tags_include: Optional[List[str]] = None,
    sort_by: Optional[str] = None, # <--- 新增排序參數
    sort_order: Optional[str] = "desc" # <--- 新增排序參數，預設為 desc
) -> List[Document]:
    """獲取文件列表，支持過濾、分頁和排序。"""
    query = _build_document_filter_query(
        owner_id=owner_id,
        uploader_device_id=uploader_device_id,
        status_in=status_in,
        filename_contains=filename_contains,
        tags_include=tags_include
    )
    cursor = db[DOCUMENT_COLLECTION].find(query)

    # 添加排序邏輯
    ALLOWED_SORT_FIELDS = ["created_at", "updated_at", "filename", "status", "file_size"] # 新增：允許排序的欄位列表
    if sort_by and sort_by in ALLOWED_SORT_FIELDS: # 修改：檢查 sort_by 是否在允許列表中
        direction = 1 if sort_order.lower() == "asc" else -1
        cursor = cursor.sort(sort_by, direction)
    elif sort_by:
        logger.warning(f"不允許的排序欄位: {sort_by}。將使用預設排序。") # 新增：對不允許的排序欄位發出警告

    documents_from_db = await cursor.skip(skip).limit(limit).to_list(length=limit) # 鏈式調用
    
    processed_documents = []
    for doc_data_from_db in documents_from_db: # documents_from_db is the list from MongoDB
        try:
            # Ensure '_id' is present for logging, even if other parts fail validation
            doc_id_for_log = str(doc_data_from_db.get('_id', 'Unknown ID'))
            document_instance = Document(**doc_data_from_db)
            processed_documents.append(document_instance)
        except Exception as e: # Catches Pydantic ValidationError and other potential errors
            logger.error(f"Error validating document data for ID {doc_id_for_log} in get_documents: {e}", exc_info=True)
            # Skip this document and continue with others
    # return [Document(**doc) for doc in documents_from_db] # 舊的返回方式
    return processed_documents

async def update_document(
    db: AsyncIOMotorDatabase, 
    document_id: uuid.UUID, 
    update_data: Dict[str, Any]
) -> Optional[Document]:
    """通用更新文件記錄的函數。
    update_data 應包含要更新的欄位及其新值。
    例如: {"status": DocumentStatus.TEXT_EXTRACTED, "extracted_text": "..."}
    """
    if not update_data: # 如果沒有提供任何更新數據，則直接返回現有文檔
        return await get_document_by_id(db, document_id)

    if "updated_at" not in update_data:
        update_data["updated_at"] = datetime.utcnow()
    
    if "status" in update_data and isinstance(update_data["status"], DocumentStatus):
        update_data["status"] = update_data["status"].value
    if "vector_status" in update_data and isinstance(update_data["vector_status"], VectorStatus):
        update_data["vector_status"] = update_data["vector_status"].value

    result = await db[DOCUMENT_COLLECTION].update_one(
        {"_id": document_id},
        {"$set": update_data}
    )
    if result.matched_count == 0:
        # Log if document not found for update
        await log_event(
            db=db,
            level=LogLevel.WARNING,
            message="Document record not found for update.",
            source="crud_documents.update_document",
            details={"document_id": str(document_id)}
        )
        return None

    updated_document = await get_document_by_id(db, document_id)
    if updated_document:
        # Log successful update
        await log_event(
            db=db,
            level=LogLevel.INFO,
            message="Document record updated successfully.",
            source="crud_documents.update_document",
            details={
                "document_id": str(document_id),
                "updated_fields": list(update_data.keys()) # Excludes updated_at if it was auto-added
            }
        )
    return updated_document

async def delete_document_by_id(db: AsyncIOMotorDatabase, document_id: uuid.UUID) -> bool:
    """按 ID 刪除文件記錄。"""
    logger.info(f"Attempting to delete document with UUID: {document_id} (type: {type(document_id)}))")
    # 注意：這裡只刪除資料庫記錄，實際的文件刪除需要在服務層處理
    result = await db[DOCUMENT_COLLECTION].delete_one({"_id": document_id})
    if result.deleted_count == 1:
        logger.info(f"Successfully deleted document with UUID: {document_id}")
        return True
    
    # 如果使用 UUID 對象刪除失敗，嘗試使用其字符串表示形式
    logger.warning(f"Failed to delete document with UUID: {document_id}. Delete result: {result.raw_result}. Attempting with string ID.")
    document_id_str = str(document_id)
    logger.info(f"Attempting to delete document with string ID: {document_id_str} (type: {type(document_id_str)}))")
    result_str = await db[DOCUMENT_COLLECTION].delete_one({"_id": document_id_str})
    if result_str.deleted_count == 1:
        logger.info(f"Successfully deleted document with string ID: {document_id_str} (original UUID: {document_id})")
        # Log successful deletion (string ID fallback)
        await log_event(
            db=db,
            level=LogLevel.INFO,
            message="Document record deleted successfully (using string ID fallback).",
            source="crud_documents.delete_document_by_id",
            details={"document_id": document_id_str, "original_uuid_attempt": str(document_id)}
        )
        return True
    
    logger.error(f"Failed to delete document with UUID {document_id} and string ID {document_id_str}. Last delete result: {result_str.raw_result}")
    # Log failed deletion
    await log_event(
        db=db,
        level=LogLevel.ERROR,
        message="Failed to delete document record after multiple attempts.",
        source="crud_documents.delete_document_by_id",
        details={"document_id_uuid": str(document_id), "document_id_str": document_id_str}
    )
    return False

async def get_documents_by_ids(
    db: AsyncIOMotorDatabase, 
    document_ids: List[str]  # 接受字符串ID列表
) -> List[Document]:
    """根據文檔ID列表批量獲取文檔"""
    if not document_ids:
        return []
    
    try:
        # 將字符串ID轉換為UUID
        uuid_ids = []
        for doc_id in document_ids:
            try:
                uuid_ids.append(uuid.UUID(doc_id))
            except ValueError:
                logger.warning(f"無效的文檔ID格式: {doc_id}")
                continue
        
        if not uuid_ids:
            return []
        
        # 查詢資料庫
        documents = await db[DOCUMENT_COLLECTION].find({"_id": {"$in": uuid_ids}}).to_list(length=None)
        
        # 轉換為Document模型
        result_documents = []
        for doc_data in documents:
            try:
                document = Document(**doc_data)
                result_documents.append(document)
            except Exception as e:
                logger.warning(f"轉換文檔模型失敗: {e}")
                continue
        
        return result_documents
        
    except Exception as e:
        logger.error(f"批量獲取文檔失敗: {e}")
        return []

# 更多專用更新函數可以按需添加，例如：
async def update_document_status(
    db: AsyncIOMotorDatabase, document_id: uuid.UUID, new_status: DocumentStatus, error_details: Optional[str] = None
) -> Optional[Document]:
    update_payload: Dict[str, Any] = {"status": new_status.value, "updated_at": datetime.utcnow()}
    
    # 檢查是否為特定的錯誤狀態
    # 假設 DocumentStatus 枚舉中已定義 EXTRACTION_FAILED 和 ANALYSIS_FAILED
    is_error_status = new_status in [
        DocumentStatus.PROCESSING_ERROR, 
        DocumentStatus.EXTRACTION_FAILED, 
        DocumentStatus.ANALYSIS_FAILED
    ]

    if error_details and is_error_status:
        update_payload["error_details"] = error_details
    elif not is_error_status: # 如果不是那幾個特定的錯誤狀態，則清除 error_details
        update_payload["error_details"] = None
    # 如果是 is_error_status 但 error_details 為 None，則現有 error_details (如果存在) 會被保留。
    # 如果希望在 is_error_status 且 error_details is None 時也清除，可以修改如下:
    # else:
    #     update_payload["error_details"] = None # 清除 error_details

    updated_doc = await update_document(db, document_id, update_payload)
    if updated_doc:
        await log_event(
            db=db,
            level=LogLevel.INFO,
            message=f"Document status updated to {new_status.value}.",
            source="crud_documents.update_document_status",
            details={
                "document_id": str(document_id),
                "new_status": new_status.value,
                "error_details_provided": error_details is not None
            }
        )
    return updated_doc

async def update_document_on_extraction_success(
    db: AsyncIOMotorDatabase, 
    document_id: uuid.UUID, 
    extracted_text: str
) -> Optional[Document]:
    """專門用於文本提取成功後更新文檔記錄。"""
    update_payload = {
        "extracted_text": extracted_text,
        "text_extraction_completed_at": datetime.utcnow(),
        "status": DocumentStatus.TEXT_EXTRACTED.value,
        "error_details": None,  # 清除任何先前的錯誤
        "updated_at": datetime.utcnow()
    }
    return await update_document(db, document_id, update_payload)

async def set_document_analysis(
    db: AsyncIOMotorDatabase, 
    document_id: uuid.UUID, 
    analysis_data_dict: Dict[str, Any], # AI Pydantic 模型的 model_dump() 結果
    token_usage_dict: Dict[str, Any], # TokenUsage Pydantic 模型的 model_dump() 結果
    model_used_str: Optional[str],
    analysis_status_enum: DocumentStatus, # 傳入枚舉成員
    analyzed_content_type_str: Optional[str] # 從AI分析結果中獲取的 content_type
) -> Optional[Document]:
    """
    保存 AI 分析結果到文檔記錄。
    此函數現在接收更明確的、已經 dump 成字典的數據。
    """
    
    # 直接查詢一次，看看情況
    raw_doc_check = await db[DOCUMENT_COLLECTION].find_one({"_id": document_id})

    current_doc = await get_document_by_id(db, document_id)
    if not current_doc:
        return None
    
    # DocumentAnalysis 模型的字段
    db_analysis_payload: Dict[str, Any] = {
        "ai_analysis_output": analysis_data_dict, # 存儲完整的 AI 分析結果字典
        "tokens_used": token_usage_dict.get("total_tokens"),
        "analysis_model_used": model_used_str,
        "error_message": analysis_data_dict.get("error_message"), # 從 AI 分析結果字典獲取
        # 'analysis_started_at' 可以由後台任務開始時設置，或在這裡設置為 utcnow()
        # 'analysis_completed_at' 應在此處設置
        "analysis_completed_at": datetime.utcnow() if analysis_status_enum == DocumentStatus.ANALYSIS_COMPLETED else None,
    }
    # 如果 analysis_data_dict 中有 "analysis_started_at"，可以使用它，否則後台任務可能需要更早設置
    # For simplicity, if not provided, we don't set it here, assuming it might be set earlier
    # if "analysis_started_at" in analysis_data_dict:
    #    db_analysis_payload["analysis_started_at"] = analysis_data_dict["analysis_started_at"]


    update_payload = {
        "analysis": db_analysis_payload,
        "status": analysis_status_enum.value, # 使用傳入的枚舉值的 .value
        "updated_at": datetime.utcnow()
    }
    # 可以考慮也更新一個頂層的 `analyzed_content_type` 字段到 Document 模型本身（如果有的話）
    # 假設 Document 模型有一個這樣的字段 (如果沒有，此行無效)
    # if "analyzed_content_type" in Document.model_fields: # Pydantic v2
    #    update_payload["analyzed_content_type"] = analyzed_content_type_str


    return await update_document(db, document_id, update_payload)

async def count_documents(
    db: AsyncIOMotorDatabase,
    owner_id: uuid.UUID,
    status_in: Optional[List[DocumentStatus]] = None, # <--- 修改此處
    filename_contains: Optional[str] = None,
    tags_include: Optional[List[str]] = None,
    uploader_device_id: Optional[str] = None # 與 get_documents 保持一致性
) -> int:
    """計算符合條件的文件總數。"""
    query = _build_document_filter_query(
        owner_id=owner_id,
        uploader_device_id=uploader_device_id,
        status_in=status_in,
        filename_contains=filename_contains,
        tags_include=tags_include
    )
    count = await db[DOCUMENT_COLLECTION].count_documents(query)
    return count 

# update_document_after_extraction 函數可以被 update_document_on_extraction_success 
# 和 update_document_status(..., DocumentStatus.EXTRACTION_FAILED, error_message) 替代
# 因此，可以考慮移除它，除非它有其他特定用途。
# 為了更清晰，我們移除它，並確保 documents.py 使用新的/調整後的函數。
# async def update_document_after_extraction(...): 
#    ... (舊代碼)

# 移除了 set_extracted_text，因為 update_document_on_extraction_success 提供了更完整的專用功能。

# 更多專用更新函數可以按需添加，例如：
# async def update_document_status(
#     db: AsyncIOMotorDatabase, document_id: uuid.UUID, new_status: DocumentStatus, error_details: Optional[str] = None
# ) -> Optional[Document]:
#     update_payload: Dict[str, Any] = {"status": new_status.value, "updated_at": datetime.utcnow()}
#     if error_details and new_status == DocumentStatus.PROCESSING_ERROR:
#         update_payload["error_details"] = error_details
#     elif new_status != DocumentStatus.PROCESSING_ERROR and "error_details" in update_payload:
#         # 如果狀態不是ERROR，清除之前的錯誤信息
#         update_payload["error_details"] = None 
#     return await update_document(db, document_id, update_payload)

# async def set_extracted_text(
#     db: AsyncIOMotorDatabase, document_id: uuid.UUID, text: str
# ) -> Optional[Document]:
#     update_payload = {
#         "extracted_text": text,
#         "text_extraction_completed_at": datetime.utcnow(),
#         "status": DocumentStatus.TEXT_EXTRACTED.value,
#         "updated_at": datetime.utcnow()
#     }
#     return await update_document(db, document_id, update_payload)

# async def set_document_analysis(
#     db: AsyncIOMotorDatabase, 
#     document_id: uuid.UUID, 
#     analysis_result: Dict[str, Any], # AI 服務返回的 model_dump() 結果
#     tokens_consumed: Optional[int] = None,
#     # model_used 參數將從 analysis_result 中獲取，不再單獨傳遞
# ) -> Optional[Document]:
#     current_doc = await get_document_by_id(db, document_id)
#     if not current_doc:
#         return None

#     analysis_data_to_update: Dict[str, Any] = {}

#     # 將 AI 服務的完整分析結果儲存起來
#     analysis_data_to_update["ai_analysis_output"] = analysis_result

#     # 從 analysis_result 中提取 model_used
#     model_used_from_result = analysis_result.get("model_used")
#     if model_used_from_result:
#         analysis_data_to_update["analysis_model_used"] = model_used_from_result
#     
#     if tokens_consumed is not None:
#         analysis_data_to_update["tokens_used"] = tokens_consumed

#     # 檢查 analysis_result 中是否有錯誤信息 (假設 AI 服務返回的字典中會包含 error_message 鍵)
#     # 或者，調用此函數的地方應該已經處理了錯誤，並相應地設置狀態
#     # 這裡我們簡化：如果 analysis_result 中有 error_message，則認為是錯誤
#     has_error = bool(analysis_result.get("error_message"))

#     final_status = DocumentStatus.PROCESSING_ERROR if has_error else DocumentStatus.ANALYSIS_COMPLETED
#     
#     # 確保分析完成時間被設定
#     # 假設 analysis_result 裡可能包含 analysis_started_at, analysis_completed_at
#     # 為了簡化，我們在這裡統一設置，如果 AI 服務那邊已經設置了，會被覆蓋
#     analysis_data_to_update["analysis_started_at"] = analysis_result.get("analysis_started_at", datetime.utcnow())
#     if not has_error:
#         analysis_data_to_update["analysis_completed_at"] = analysis_result.get("analysis_completed_at", datetime.utcnow())
#     else:
#         analysis_data_to_update["analysis_completed_at"] = None # 錯誤情況下不設置完成時間
#         # 將錯誤信息也記錄在 DocumentAnalysis 層級，如果有的話
#         if analysis_result.get("error_message"):
#              analysis_data_to_update["error_message"] = analysis_result.get("error_message")

#     update_payload = {
#         "analysis": analysis_data_to_update,
#         "status": final_status.value,
#         "updated_at": datetime.utcnow()
#     }
#     
#     return await update_document(db, document_id, update_payload) 

async def update_document_vector_status(
    db: AsyncIOMotorDatabase, 
    document_id: uuid.UUID, 
    new_vector_status: VectorStatus, 
    error_details: Optional[str] = None
) -> Optional[Document]:
    """更新文檔的向量化狀態。"""
    update_payload: Dict[str, Any] = {
        "vector_status": new_vector_status.value, 
        "updated_at": datetime.utcnow()
    }
    # 如果是失敗狀態且有錯誤詳情，則記錄
    if new_vector_status == VectorStatus.FAILED and error_details:
        update_payload["error_details"] = error_details # 可以考慮用一個專門的 vectorization_error_details 欄位
    
    updated_doc = await update_document(db, document_id, update_payload)
    if updated_doc:
        await log_event(
            db=db,
            level=LogLevel.INFO,
            message=f"Document vector status updated to {new_vector_status.value}.",
            source="crud_documents.update_document_vector_status",
            details={
                "document_id": str(document_id),
                "new_vector_status": new_vector_status.value,
                "error_details_provided": error_details is not None
            }
        )
    return updated_doc