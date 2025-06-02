import logging
import uuid
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
import io
from PIL import Image
import os
from fastapi import HTTPException, status

from motor.motor_asyncio import AsyncIOMotorDatabase

from ..models import Document, DocumentStatus, TokenUsage, AIImageAnalysisOutput, AITextAnalysisOutput
from ..crud import crud_documents
from ..core.config import Settings
from ..services.document_processing_service import DocumentProcessingService, SUPPORTED_IMAGE_TYPES_FOR_AI
from ..services.unified_ai_service_simplified import AIRequest, TaskType as AIServiceTaskType, unified_ai_service_simplified
from ..services import unified_ai_config
from ..core.logging_utils import log_event, LogLevel, AppLogger

logger = AppLogger(__name__, level=logging.DEBUG).get_logger()

SUPPORTED_TEXT_TYPES_FOR_AI_PROCESSING = {
    "application/pdf",
    "text/plain",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
    "application/msword",  # .doc
}

class DocumentTasksService:
    def __init__(self):
        pass

    async def _setup_and_validate_document_for_processing(self, doc_id: uuid.UUID, db: AsyncIOMotorDatabase, user_id_for_log: str, request_id_for_log: Optional[str]) -> Optional[Document]:
        """
        Helper function to perform initial setup and validation for document processing.
        Reloads AI config, fetches document by UUID, and validates file path.
        Returns the Document object if successful, None otherwise.
        """
        try:
            await unified_ai_config.reload_task_configs(db)
            logger.info(f"AI配置已重新載入 (task for doc_id: {doc_id})")
        except Exception as e:
            logger.error(f"後台任務初始設定錯誤 (AI 配置重載 for doc_id {doc_id}): {e}", exc_info=True)

        document_from_db = await crud_documents.get_document_by_id(db, doc_id)
        if not document_from_db:
            logger.error(f"無法獲取文檔: ID {doc_id}")
            await log_event(db=db, level=LogLevel.ERROR, message=f"文件處理失敗: 文件記錄不存在 for {doc_id}",
                            source="doc_tasks_service._setup.doc_not_found", user_id=user_id_for_log, request_id=request_id_for_log)
            return None

        if not document_from_db.file_path:
            logger.error(f"文件路徑未設定: ID {doc_id}")
            await crud_documents.update_document_status(db, doc_id, DocumentStatus.PROCESSING_ERROR, "文件記錄缺少路徑")
            await log_event(db=db, level=LogLevel.ERROR, message=f"文件處理失敗: 文件記錄缺少路徑 for {doc_id}",
                            source="doc_tasks_service._setup.path_missing", user_id=user_id_for_log, request_id=request_id_for_log)
            return None

        doc_path = Path(document_from_db.file_path)
        if not doc_path.exists():
            logger.error(f"Document file not found at path: {document_from_db.file_path} for doc ID: {doc_id}")
            await crud_documents.update_document_status(db, doc_id, DocumentStatus.PROCESSING_ERROR, "文件未找到，無法處理")
            await log_event(db=db, level=LogLevel.ERROR, message=f"文件處理失敗: 文件不存在 {document_from_db.file_path}",
                            source="doc_tasks_service._setup.file_not_found", user_id=user_id_for_log, request_id=request_id_for_log,
                            details={"doc_id": str(doc_id), "path": document_from_db.file_path})
            return None
            
        return document_from_db

    async def _process_image_document(self, document: Document, db: AsyncIOMotorDatabase, user_id_for_log: str, request_id_for_log: Optional[str], ai_ensure_chinese_output: Optional[bool], ai_model_preference: Optional[str] = None, ai_max_output_tokens: Optional[int] = None) -> tuple[Optional[Dict[str, Any]], Optional[TokenUsage], Optional[str], DocumentStatus]:
        analysis_data_to_save: Optional[Dict[str, Any]] = None
        token_usage_to_save: Optional[TokenUsage] = None
        model_used_for_analysis: Optional[str] = None
        new_status = DocumentStatus.ANALYZING

        doc_uuid = document.id
        doc_file_path_str = str(document.file_path) if document.file_path else None
        doc_mime_type = document.file_type
        logger.info(f"Performing AI image analysis for document ID: {doc_uuid}, MIME: {doc_mime_type}")

        try:
            if not doc_file_path_str:
                raise ValueError("File path is missing for image document.")
            temp_doc_processing_service = DocumentProcessingService()
            image_bytes = await temp_doc_processing_service.get_image_bytes(doc_file_path_str) # type: ignore
            if not image_bytes:
                logger.error(f"無法讀取圖片文件字節數據 for doc ID: {doc_uuid}")
                return None, None, None, DocumentStatus.PROCESSING_ERROR
            
            pil_image = Image.open(io.BytesIO(image_bytes))
            ai_response = await unified_ai_service_simplified.analyze_image( # type: ignore
                image=pil_image, model_preference=ai_model_preference, db=db
            )
            
            if not ai_response.success or not isinstance(ai_response.output_data, AIImageAnalysisOutput):
                error_msg = ai_response.error_message or "AI image analysis returned unsuccessful or invalid content type."
                logger.error(f"圖片分析失敗 for doc ID {doc_uuid}: {error_msg}")
                return None, None, None, DocumentStatus.ANALYSIS_FAILED
            
            ai_image_output = ai_response.output_data
            token_usage_to_save = ai_response.token_usage
            model_used_for_analysis = ai_response.model_used
            analysis_data_to_save = ai_image_output.model_dump()
            new_status = DocumentStatus.ANALYSIS_COMPLETED
            if ai_image_output.error_message or (hasattr(ai_image_output, 'content_type') and "Error" in str(ai_image_output.content_type)):
                new_status = DocumentStatus.ANALYSIS_FAILED
            logger.info(f"Image AI analysis status for {doc_uuid}: {new_status.value}")

        except ValueError as ve:
            logger.error(f"ValueError during image processing for doc ID {doc_uuid}: {ve}", exc_info=True)
            new_status = DocumentStatus.PROCESSING_ERROR
        except Exception as e:
            logger.error(f"Unexpected error during image processing for doc ID {doc_uuid}: {e}", exc_info=True)
            new_status = DocumentStatus.PROCESSING_ERROR
        return analysis_data_to_save, token_usage_to_save, model_used_for_analysis, new_status

    async def _process_text_document(self, document: Document, db: AsyncIOMotorDatabase, user_id_for_log: str, request_id_for_log: Optional[str], settings_obj: Settings, ai_ensure_chinese_output: Optional[bool], ai_model_preference: Optional[str] = None, ai_max_output_tokens: Optional[int] = None) -> tuple[Optional[Dict[str, Any]], Optional[TokenUsage], Optional[str], DocumentStatus]:
        analysis_data_to_save: Optional[Dict[str, Any]] = None
        token_usage_to_save: Optional[TokenUsage] = None
        model_used_for_analysis: Optional[str] = None
        new_status = DocumentStatus.ANALYZING
        extracted_text_content: Optional[str] = None

        doc_uuid = document.id
        doc_path = Path(str(document.file_path)) if document.file_path else None
        doc_mime_type = document.file_type
        logger.info(f"Performing text extraction and AI analysis for document ID: {doc_uuid}, MIME: {doc_mime_type}")

        try:
            if not doc_path or not document.file_path:
                logger.error(f"File path is missing for text document ID: {doc_uuid}")
                return None, None, None, DocumentStatus.PROCESSING_ERROR

            doc_processing_service_instance = DocumentProcessingService()
            extracted_text_result, extraction_status, extraction_error = \
                await doc_processing_service_instance.extract_text_from_document(str(doc_path), doc_path.suffix)

            if extraction_status == DocumentStatus.PROCESSING_ERROR or not extracted_text_result or not extracted_text_result.strip():
                error_detail = extraction_error or "未能從文件中提取到有效文本內容"
                logger.error(f"從文檔 {doc_uuid} ({doc_mime_type}) 提取文本時出錯或結果為空: {error_detail}", exc_info=bool(extraction_error))
                await crud_documents.update_document_status(db, doc_uuid, DocumentStatus.EXTRACTION_FAILED, error_detail)
                return None, None, None, DocumentStatus.EXTRACTION_FAILED

            extracted_text_content = extracted_text_result
            await crud_documents.update_document_on_extraction_success(db, doc_uuid, extracted_text_content)
            logger.info(f"成功從 {doc_uuid} 提取 {len(extracted_text_content)} 字元的文本。開始 AI 分析...")

            max_prompt_len = settings_obj.AI_MAX_INPUT_CHARS_TEXT_ANALYSIS
            if len(extracted_text_content) > max_prompt_len:
                logger.warning(f"提取的文本長度 ({len(extracted_text_content)}) 超過最大允許長度 ({max_prompt_len})。將進行截斷。 Doc ID: {doc_uuid}")
                extracted_text_content = extracted_text_content[:max_prompt_len]

            ai_response = await unified_ai_service_simplified.analyze_text( # type: ignore
                text=extracted_text_content, model_preference=ai_model_preference, db=db
            )
            
            if not ai_response.success or not isinstance(ai_response.output_data, AITextAnalysisOutput):
                error_msg = ai_response.error_message or "AI text analysis returned unsuccessful or invalid content type."
                logger.error(f"文本分析失敗 for doc ID {doc_uuid}: {error_msg}")
                return None, None, None, DocumentStatus.ANALYSIS_FAILED
                
            ai_text_output: AITextAnalysisOutput = ai_response.output_data
            token_usage_to_save = ai_response.token_usage
            model_used_for_analysis = ai_response.model_used
            analysis_data_to_save = ai_text_output.model_dump()
            new_status = DocumentStatus.ANALYSIS_COMPLETED
            if ai_text_output.error_message or (hasattr(ai_text_output, 'content_type') and "Error" in str(ai_text_output.content_type)):
                new_status = DocumentStatus.ANALYSIS_FAILED
            logger.info(f"Text AI analysis status for {doc_uuid}: {new_status.value}")

        except Exception as e:
            logger.error(f"Unexpected error during text processing for doc ID {doc_uuid}: {e}", exc_info=True)
            new_status = DocumentStatus.PROCESSING_ERROR
        return analysis_data_to_save, token_usage_to_save, model_used_for_analysis, new_status

    async def _save_analysis_results(self, document: Document, db: AsyncIOMotorDatabase, user_id_for_log: str, request_id_for_log: Optional[str], analysis_data: Optional[Dict[str, Any]], token_usage: Optional[TokenUsage], model_used: Optional[str], processing_status: DocumentStatus, processing_type: str) -> None:
        doc_uuid = document.id
        try:
            if analysis_data and token_usage and processing_status in [DocumentStatus.ANALYSIS_COMPLETED, DocumentStatus.ANALYSIS_FAILED]:
                await crud_documents.set_document_analysis(
                    db=db, document_id=doc_uuid, analysis_data_dict=analysis_data,
                    token_usage_dict=token_usage.model_dump(), model_used_str=model_used,
                    analysis_status_enum=processing_status, 
                    analyzed_content_type_str=analysis_data.get("content_type", "Unknown")
                )
                log_level = LogLevel.INFO if processing_status == DocumentStatus.ANALYSIS_COMPLETED else LogLevel.ERROR
                log_message = f"AI {processing_type} for doc ID {doc_uuid} status: {processing_status.value}."
            elif processing_status != DocumentStatus.ANALYZING: # Error or unsupported before full analysis
                await crud_documents.update_document_status(db, doc_uuid, processing_status, f"Processing concluded: {processing_status.value}")
                log_level = LogLevel.WARNING
                log_message = f"Document {doc_uuid} processing ended with status {processing_status.value} without new AI data."
            else: # Should not happen if logic is correct
                await crud_documents.update_document_status(db, doc_uuid, DocumentStatus.PROCESSING_ERROR, "Unknown state in save_analysis_results")
                log_level = LogLevel.ERROR
                log_message = f"Document {doc_uuid} in unexpected state {processing_status.value} at save_analysis_results."
            
            logger.log(logging.getLevelName(log_level.value), log_message) # Use logger's log method for dynamic level
            await log_event(
                db=db, level=log_level, message=log_message,
                source=f"doc_tasks_service._save_results.{processing_type}", user_id=user_id_for_log, request_id=request_id_for_log,
                details={"doc_id": str(doc_uuid), "status": processing_status.value, "tokens": token_usage.total_tokens if token_usage else 0}
            )
        except Exception as e:
            logger.error(f"Error saving analysis results for doc ID {doc_uuid}: {e}", exc_info=True)
            try:
                await crud_documents.update_document_status(db, doc_uuid, DocumentStatus.PROCESSING_ERROR, f"Save results error: {str(e)[:50]}")
            except Exception as db_err: #Nested
                logger.critical(f"CRITICAL: Failed to update doc status after save error for {doc_uuid}: {db_err}", exc_info=True)
            await log_event(db=db, level=LogLevel.CRITICAL, message=f"Critical error saving analysis results for {doc_uuid}: {e}",
                            source="doc_tasks_service._save_results.critical_failure", user_id=user_id_for_log, request_id=request_id_for_log)

    async def process_document_content_analysis(self, doc_id_str: str, db: AsyncIOMotorDatabase, user_id_for_log: str, request_id_for_log: Optional[str], settings_obj: Settings, ai_ensure_chinese_output: Optional[bool] = True, ai_model_preference: Optional[str] = None, ai_max_output_tokens: Optional[int] = None) -> None:
        try:
            doc_uuid = uuid.UUID(doc_id_str)
        except ValueError:
            logger.error(f"Background task: Invalid UUID string for doc_id: {doc_id_str}. Cannot proceed.")
            await log_event(db=db, level=LogLevel.CRITICAL, message=f"Invalid document ID format '{doc_id_str}' in background task.",
                            source="doc_tasks_service.process_doc_content.id_conversion_error", user_id=user_id_for_log, request_id=request_id_for_log,
                            details={"original_doc_id": doc_id_str})
            return

        document = await self._setup_and_validate_document_for_processing(doc_uuid, db, user_id_for_log, request_id_for_log)
        if document is None: return

        logger.info(f"Service task starting processing for document ID (UUID): {document.id}, Original passed ID: {doc_id_str}")
        analysis_data: Optional[Dict[str, Any]] = None
        token_usage: Optional[TokenUsage] = None
        model_used: Optional[str] = None
        processing_status = DocumentStatus.ANALYZING
        processing_type = "unknown"
        
        try:
            if document.file_type and document.file_type in SUPPORTED_IMAGE_TYPES_FOR_AI:
                processing_type = "image_analysis"
                analysis_data, token_usage, model_used, processing_status = await self._process_image_document(
                    document, db, user_id_for_log, request_id_for_log, ai_ensure_chinese_output, ai_model_preference, ai_max_output_tokens)
            elif document.file_type and document.file_type in SUPPORTED_TEXT_TYPES_FOR_AI_PROCESSING:
                processing_type = "text_analysis"
                analysis_data, token_usage, model_used, processing_status = await self._process_text_document(
                    document, db, user_id_for_log, request_id_for_log, settings_obj, ai_ensure_chinese_output, ai_model_preference, ai_max_output_tokens)
            else:
                processing_type = "unsupported"
                logger.warning(f"Document ID: {document.id} MIME type '{document.file_type}' unsupported for AI processing.")
                processing_status = DocumentStatus.PROCESSING_ERROR 
            
            await self._save_analysis_results(document, db, user_id_for_log, request_id_for_log, analysis_data, token_usage, model_used, processing_status, processing_type)
        except Exception as e:
            logger.error(f"Service task for doc {document.id} encountered top-level error: {e}", exc_info=True)
            await self._save_analysis_results(document, db, user_id_for_log, request_id_for_log, None, None, None, DocumentStatus.PROCESSING_ERROR, processing_type)

    async def trigger_document_analysis(self, db: AsyncIOMotorDatabase, doc_processor: DocumentProcessingService, document_id: uuid.UUID, current_user_id: uuid.UUID, settings_obj: Settings, processing_strategy: Optional[str] = None, custom_prompt_id: Optional[str] = None, analysis_type: Optional[str] = None, task_type_str: Optional[str] = None, request_id: Optional[str] = None, ai_model_preference: Optional[str] = None, ai_ensure_chinese_output: Optional[bool] = None, ai_max_output_tokens: Optional[int] = None) -> Document:
        logger.debug(f"(Service) Triggering analysis for doc ID: {document_id}, strategy: {processing_strategy}")
        
        # Use the centralized setup and validation method
        document = await self._setup_and_validate_document_for_processing(document_id, db, str(current_user_id), request_id)
        if not document:
            # _setup_and_validate_document_for_processing already logs and sets status
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document {document_id} not found or setup failed.")

        # Ownership Check (already part of _setup_and_validate if user_id_for_log is current_user_id, but explicit check here is also fine)
        if document.owner_id != current_user_id:
            logger.warning(f"(Service) User {current_user_id} attempt to analyze document {document_id} owned by {document.owner_id}")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="無權限分析此文件")

        await crud_documents.update_document_status(db, document.id, DocumentStatus.ANALYZING, "Analysis triggered by service (trigger_document_analysis).")

        effective_task_type: Optional[AIServiceTaskType] = None
        if task_type_str:
            try: effective_task_type = AIServiceTaskType[task_type_str.upper()]
            except KeyError: logger.warning(f"無效的 task_type_str: {task_type_str}, 將回退到根據文件類型決定。")
        
        if not effective_task_type:
            if document.file_type and document.file_type in SUPPORTED_IMAGE_TYPES_FOR_AI:
                effective_task_type = AIServiceTaskType.IMAGE_ANALYSIS
            elif document.file_type and document.file_type in SUPPORTED_TEXT_TYPES_FOR_AI_PROCESSING:
                effective_task_type = AIServiceTaskType.TEXT_GENERATION
            else:
                await self._save_analysis_results(document, db, str(current_user_id), request_id, None, None, None, DocumentStatus.PROCESSING_ERROR, "unsupported_type_determination")
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"不支持的文件類型 ({document.file_type}) 或無法確定任務類型。")

        content_for_ai: Any
        processing_type_for_save = "unknown_triggered_analysis"

        try:
            if effective_task_type == AIServiceTaskType.IMAGE_ANALYSIS:
                processing_type_for_save = "image_analysis_triggered"
                # This part is similar to _process_image_document's content prep
                if not document.file_path or not os.path.exists(document.file_path):
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="圖片文件路徑不存在。")
                image_bytes = await doc_processor.get_image_bytes(document.file_path) # type: ignore
                if not image_bytes:
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="無法讀取圖片文件。")
                content_for_ai = Image.open(io.BytesIO(image_bytes))
            elif effective_task_type == AIServiceTaskType.TEXT_GENERATION:
                processing_type_for_save = "text_analysis_triggered"
                # This part is similar to _process_text_document's content prep
                if not document.extracted_text:
                    if not document.file_path or not os.path.exists(document.file_path): # Check path before extraction
                         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文本文件路徑不存在。")
                    extracted_text_result, extraction_status, extraction_error = \
                        await doc_processor.extract_text_from_document(str(document.file_path), Path(str(document.file_path)).suffix if document.file_path else "") # type: ignore
                    if extraction_status == DocumentStatus.PROCESSING_ERROR or not extracted_text_result:
                        error_detail = extraction_error or "未能從文件中提取到有效文本內容以進行分析"
                        await self._save_analysis_results(document, db, str(current_user_id), request_id, None, None, None, DocumentStatus.EXTRACTION_FAILED, processing_type_for_save)
                        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error_detail)
                    document.extracted_text = extracted_text_result
                    await crud_documents.update_document_on_extraction_success(db, document.id, extracted_text_result)
                content_for_ai = document.extracted_text
                if not content_for_ai:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文檔無提取文本可供分析。")
                max_prompt_len = settings_obj.AI_MAX_INPUT_CHARS_TEXT_ANALYSIS
                if len(content_for_ai) > max_prompt_len:
                    logger.warning(f"提取的文本長度 ({len(content_for_ai)}) 超過最大允許長度 ({max_prompt_len})。將進行截斷。 Doc ID: {document.id}")
                    content_for_ai = content_for_ai[:max_prompt_len]
            else: # Should have been caught by earlier task type check
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"不支持的AI任務類型進行內部觸發: {effective_task_type}")

            ai_request = AIRequest(
                task_type=effective_task_type, content=content_for_ai, model_preference=ai_model_preference,
                require_language_consistency=ai_ensure_chinese_output if ai_ensure_chinese_output is not None else True,
                generation_params_override={"max_output_tokens": ai_max_output_tokens} if ai_max_output_tokens else None,
                prompt_params={"user_query": custom_prompt_id} if custom_prompt_id else None, user_id=str(current_user_id)
            )
            ai_response = await unified_ai_service_simplified.process_request(ai_request, db) # type: ignore

            analysis_data_to_save: Optional[dict] = None
            token_usage_to_save: Optional[TokenUsage] = None
            model_used: Optional[str] = None
            final_status: DocumentStatus

            if ai_response.success and ai_response.output_data:
                analysis_data_to_save = ai_response.output_data.model_dump()
                token_usage_to_save = ai_response.token_usage # type: ignore
                model_used = ai_response.model_used # type: ignore
                final_status = DocumentStatus.ANALYSIS_COMPLETED
                logger.info(f"文檔 {document.id} 的 AI 分析成功完成 (triggered)。")
            else:
                final_status = DocumentStatus.ANALYSIS_FAILED
                logger.error(f"文檔 {document.id} 的 AI 分析失敗 (triggered): {ai_response.error_message}")
                # analysis_data_to_save can include error details if needed, currently handled by _save_analysis_results
                analysis_data_to_save = {"error": ai_response.error_message or "Unknown AI error during trigger"}

            await self._save_analysis_results(document, db, str(current_user_id), request_id, 
                                              analysis_data_to_save, token_usage_to_save, model_used, 
                                              final_status, processing_type_for_save)
            
            updated_document = await crud_documents.get_document_by_id(db, document.id)
            if not updated_document:
                # This should ideally not happen if the document existed and status was updated
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="分析後無法重新獲取文檔。")
            return updated_document

        except HTTPException as http_exc: # Re-raise HTTPExceptions directly
            # If status was already ANALYSIS_FAILED by _save_analysis_results, this is fine.
            # Otherwise, ensure a generic error status if one wasn't set.
            if document and document.status == DocumentStatus.ANALYZING: # If still analyzing, mark as error
                 await self._save_analysis_results(document, db, str(current_user_id), request_id, 
                                                  {"error": str(http_exc.detail)}, None, None, 
                                                  DocumentStatus.ANALYSIS_FAILED, processing_type_for_save)
            raise http_exc
        except Exception as e:
            logger.error(f"(Service Trigger) 分析文檔 {document.id} 時發生頂層錯誤: {e}", exc_info=True)
            if document: # Ensure document exists before trying to save results
                 await self._save_analysis_results(document, db, str(current_user_id), request_id, 
                                                  {"error": str(e)}, None, None, 
                                                  DocumentStatus.PROCESSING_ERROR, processing_type_for_save)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"觸發文件分析時發生意外錯誤: {str(e)}")

```
