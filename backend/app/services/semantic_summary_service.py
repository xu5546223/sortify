from typing import Optional, Dict, Any, List
import json
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.core.logging_utils import AppLogger, log_event, LogLevel # Added
from app.services.unified_ai_service_simplified import unified_ai_service_simplified, AIResponse as UnifiedAIResponse # Alias
from app.services.embedding_service import embedding_service # Assuming async methods
from app.services.vector_db_service import vector_db_service
from app.models.vector_models import SemanticSummary, VectorRecord
from app.models.ai_models_simplified import AIPromptRequest
from app.models.document_models import Document, VectorStatus
from app.services.prompt_manager_simplified import prompt_manager_simplified, PromptType
from app.crud.crud_documents import update_document_vector_status
import logging
import uuid

logger = AppLogger(__name__, level=logging.DEBUG).get_logger()

class SemanticSummaryService:
    """語義摘要生成服務"""
    
    def __init__(self):
        # 使用統一AI服務，不再需要單獨的AI服務實例
        pass
    
    async def generate_semantic_summary(
        self, 
        db: AsyncIOMotorDatabase,
        document: Document
    ) -> Optional[SemanticSummary]:
        """
        為文檔生成語義摘要文本 (使用 prompt_manager_simplified)
        優先從 document.analysis.ai_analysis_output 提取，否則調用AI進行新的文本分析。
        """
        doc_id_str = str(document.id)
        log_details_initial = {"document_id": doc_id_str, "filename": document.filename, "file_type": document.file_type}
        await log_event(db=db, level=LogLevel.INFO, message="Semantic summarization request received.",
                        source="service.semantic_summary.generate_summary", details=log_details_initial)

        try:
            if document.analysis and isinstance(document.analysis.ai_analysis_output, dict):
                await log_event(db=db, level=LogLevel.DEBUG, message=f"Existing AI analysis found for doc {doc_id_str}, attempting to use it.",
                                source="service.semantic_summary.generate_summary", details=log_details_initial)
                existing_analysis = document.analysis.ai_analysis_output
                key_info = existing_analysis.get("key_information", {})
                summary_text = key_info.get("content_summary", "")
                key_terms = key_info.get("semantic_tags", [])

                if isinstance(key_terms, str):
                    key_terms = [term.strip() for term in key_terms.split(',') if term.strip()]
                
                if summary_text and len(summary_text.strip()) >= 10:
                    await log_event(db=db, level=LogLevel.INFO, message=f"Successfully extracted summary from existing analysis for doc {doc_id_str}.",
                                    source="service.semantic_summary.generate_summary", details={**log_details_initial, "summary_length": len(summary_text), "key_terms_count": len(key_terms)})
                    return SemanticSummary(document_id=doc_id_str, summary_text=summary_text, file_type=document.file_type, key_terms=key_terms, full_ai_analysis=existing_analysis)
                else:
                    await log_event(db=db, level=LogLevel.WARNING, message=f"Existing AI analysis for doc {doc_id_str} lacked sufficient summary/tags. Proceeding to new analysis.",
                                    source="service.semantic_summary.generate_summary", details=log_details_initial)
            
            if not document.extracted_text or len(document.extracted_text.strip()) < 50:
                await log_event(db=db, level=LogLevel.WARNING, message=f"Document content too short for summarization: {doc_id_str} ({len(document.extracted_text.strip()) if document.extracted_text else 0} chars).",
                                source="service.semantic_summary.generate_summary", details=log_details_initial)
                return None

            await log_event(db=db, level=LogLevel.DEBUG, message=f"No usable existing summary for doc {doc_id_str}. Calling AI for new text analysis.",
                            source="service.semantic_summary.generate_summary", details=log_details_initial)

            prompt_template = await prompt_manager_simplified.get_prompt(PromptType.TEXT_ANALYSIS, db)
            if not prompt_template:
                await log_event(db=db, level=LogLevel.ERROR, message=f"Failed to get TEXT_ANALYSIS prompt template for doc {doc_id_str}. Using fallback summary.",
                                source="service.semantic_summary.generate_summary", details=log_details_initial)
                summary_text = await self._generate_fallback_summary(document, db=db) # Pass db
                return SemanticSummary(document_id=doc_id_str, summary_text=summary_text, file_type=document.file_type, key_terms=[])

            system_prompt, user_prompt = prompt_manager_simplified.format_prompt(
                prompt_template, text_content=document.extracted_text[:4000]
            )
            
            ai_response: UnifiedAIResponse = await unified_ai_service_simplified.analyze_with_prompts_and_parse_json(
                system_prompt=system_prompt, user_prompt=user_prompt, db=db, output_model_schema=None
            )

            if not ai_response.success or not ai_response.content:
                error_msg = ai_response.error_message or "AI service returned no content or failed."
                await log_event(db=db, level=LogLevel.WARNING, message=f"AI structured summarization failed for doc {doc_id_str}: {error_msg}. Using fallback.",
                                source="service.semantic_summary.generate_summary", details={**log_details_initial, "ai_error": error_msg})
                summary_text = await self._generate_fallback_summary(document, db=db) # Pass db
                return SemanticSummary(document_id=doc_id_str, file_type=document.file_type, summary_text=summary_text, key_terms=[])
            
            try:
                parsed_json = ai_response.content 
                key_info = parsed_json.get("key_information", {})
                summary_text = key_info.get("content_summary", "")
                key_terms = key_info.get("semantic_tags", [])

                if isinstance(key_terms, str):
                    key_terms = [term.strip() for term in key_terms.split(',') if term.strip()]

                if not summary_text or len(summary_text.strip()) < 10:
                    await log_event(db=db, level=LogLevel.WARNING, message=f"AI generated summary too short for doc {doc_id_str}. Using fallback.",
                                    source="service.semantic_summary.generate_summary", details={**log_details_initial, "ai_summary_snippet": summary_text[:50]})
                    summary_text = await self._generate_fallback_summary(document, db=db) # Pass db
                    key_terms = []

                semantic_summary_obj = SemanticSummary(
                    document_id=doc_id_str, summary_text=summary_text, file_type=document.file_type,
                    key_terms=key_terms, full_ai_analysis=parsed_json
                )
                await log_event(db=db, level=LogLevel.INFO, message=f"Structured semantic summary generated successfully for doc {doc_id_str}.",
                                source="service.semantic_summary.generate_summary", details={**log_details_initial, "summary_length": len(summary_text), "key_terms_count": len(key_terms)})
                return semantic_summary_obj
                
            except (json.JSONDecodeError, AttributeError, KeyError, TypeError) as e_parse:
                error_msg = f"Failed to parse AI structured summary response: {str(e_parse)}. AI response snippet: {str(ai_response.content)[:200]}"
                await log_event(db=db, level=LogLevel.ERROR, message=error_msg, source="service.semantic_summary.generate_summary",
                                exc_info=True, details={**log_details_initial, "parsing_error": str(e_parse)})
                summary_text = await self._generate_fallback_summary(document, db=db) # Pass db
                return SemanticSummary(document_id=doc_id_str, summary_text=summary_text, file_type=document.file_type, key_terms=[])
                
        except Exception as e_main:
            error_msg = f"Generic failure in semantic summary generation for doc {doc_id_str}: {str(e_main)}"
            await log_event(db=db, level=LogLevel.ERROR, message=error_msg, source="service.semantic_summary.generate_summary",
                            exc_info=True, details={**log_details_initial, "error": str(e_main), "error_type": type(e_main).__name__})
            summary_text = await self._generate_fallback_summary(document, db=db) # Pass db
            return SemanticSummary(document_id=doc_id_str, summary_text=summary_text, file_type=document.file_type, key_terms=[])
    
    async def _generate_fallback_summary(self, document: Document, db: AsyncIOMotorDatabase) -> str: # Added db for log_event
        """生成fallback語義摘要"""
        try:
            # 提取文本的前幾個句子
            text = document.extracted_text or ""
            sentences = text.split('。')[:3]  # 取前3個句子
            
            summary_parts = [
                f"這是一份{document.file_type or '文檔'}文件",
                f"文件名為{document.filename}"
            ]
            
            if sentences and sentences[0].strip():
                summary_parts.append(f"主要內容包括：{sentences[0].strip()}")
            
            if len(sentences) > 1 and sentences[1].strip():
                summary_parts.append(sentences[1].strip())
            
            summary = "，".join(summary_parts) + "。"
            
            # 確保摘要長度合適
            if len(summary) > 500:
                summary = summary[:500] + "..."
            
            return summary
            
        except Exception as e:
            # logger.error(f"生成fallback摘要失敗: {e}") # Replaced
            await log_event(db=db, level=LogLevel.ERROR,
                            message=f"Failed to generate fallback summary for doc ID {document.id}: {str(e)}",
                            source="service.semantic_summary.fallback_summary", exc_info=True,
                            details={"document_id": str(document.id), "filename": document.filename, "error": str(e), "error_type": type(e).__name__})
            return f"This is a document of type {document.file_type or 'unknown'} named {document.filename}." # English
    
    async def process_document_for_vector_db(
        self, 
        db: AsyncIOMotorDatabase,
        document: Document
    ) -> bool:
        """
        處理文檔並添加到向量資料庫
        
        完整流程：
        1. 更新狀態為 PROCESSING
        2. (可選) 刪除舊向量 (實現覆蓋)
        3. 生成語義摘要
        4. 向量化摘要文本
        5. 存儲到向量資料庫
        6. 更新文檔狀態 (VECTORIZED 或 FAILED)
        """
        # doc_id_str = document.id # Assuming document.id is already a string, if not, str(document.id)
        # doc_id_uuid = uuid.UUID(doc_id_str) # For crud operations

        # 修正UUID處理：document.id 是 uuid.UUID 對象
        doc_id_uuid: uuid.UUID = document.id 
        doc_id_str: str = str(document.id)
        log_details_base = {"document_id": doc_id_str, "filename": document.filename, "user_id": str(document.owner_id)}

        await log_event(db=db, level=LogLevel.INFO, message="Starting document processing for vector DB.",
                        source="service.semantic_summary.process_doc_for_vector_db", details=log_details_base)
        try:
            await update_document_vector_status(db, doc_id_uuid, VectorStatus.PROCESSING)
            
            await log_event(db=db, level=LogLevel.DEBUG, message="Attempting to delete old vectors.",
                            source="service.semantic_summary.process_doc_for_vector_db", details=log_details_base)
            vector_db_service.delete_by_document_id(doc_id_str) # This is sync
            await log_event(db=db, level=LogLevel.DEBUG, message="Old vectors deleted (if any).",
                            source="service.semantic_summary.process_doc_for_vector_db", details=log_details_base)

            semantic_summary = await self.generate_semantic_summary(db, document)
            if not semantic_summary:
                await log_event(db=db, level=LogLevel.ERROR, message="Failed to generate semantic summary.",
                                source="service.semantic_summary.process_doc_for_vector_db", details=log_details_base)
                await update_document_vector_status(db, doc_id_uuid, VectorStatus.FAILED, "Semantic summary generation failed.")
                return False
            
            text_parts = []
            if semantic_summary.summary_text and semantic_summary.summary_text.strip(): text_parts.append(semantic_summary.summary_text.strip())
            if semantic_summary.key_terms: 
                valid_key_terms = [str(term).strip() for term in semantic_summary.key_terms if term and str(term).strip()]
                if valid_key_terms: text_parts.append("Relevant tags: " + ", ".join(valid_key_terms)) # English
            
            # Simplified extraction from full_ai_analysis for brevity in this example
            if semantic_summary.full_ai_analysis and isinstance(semantic_summary.full_ai_analysis, dict):
                key_info = semantic_summary.full_ai_analysis.get("key_information")
                if isinstance(key_info, dict):
                    search_keywords = key_info.get("searchable_keywords")
                    if isinstance(search_keywords, list): text_parts.append("Keywords: " + ", ".join(filter(None, [str(kw).strip() for kw in search_keywords])))
                    knowledge_domains = key_info.get("knowledge_domains")
                    if isinstance(knowledge_domains, list): text_parts.append("Knowledge Domains: " + ", ".join(filter(None,[str(kd).strip() for kd in knowledge_domains])))
            
            text_to_embed = "\n".join(filter(None, text_parts))
            if not text_to_embed.strip():
                text_to_embed = semantic_summary.summary_text.strip() if semantic_summary.summary_text and semantic_summary.summary_text.strip() else document.filename or "document content unavailable"
                await log_event(db=db, level=LogLevel.WARNING, message="Combined text for embedding was empty, using fallback.",
                                source="service.semantic_summary.process_doc_for_vector_db", details={**log_details_base, "fallback_text_length": len(text_to_embed)})

            await log_event(db=db, level=LogLevel.DEBUG, message="Encoding text for vector DB.",
                            source="service.semantic_summary.process_doc_for_vector_db", details={**log_details_base, "text_to_embed_length": len(text_to_embed)})
            embedding_vector = await embedding_service.encode_text(text_to_embed) # Assumed async
            
            vector_record = VectorRecord(
                document_id=doc_id_str, owner_id=str(document.owner_id), embedding_vector=embedding_vector,
                chunk_text=text_to_embed[:1000], # Store a snippet
                embedding_model=embedding_service.model_name, metadata={"file_type": document.file_type or ""}
            )
            
            await log_event(db=db, level=LogLevel.DEBUG, message="Inserting vector into vector DB.",
                            source="service.semantic_summary.process_doc_for_vector_db", details={**log_details_base, "vector_dim": len(embedding_vector)})
            success = vector_db_service.insert_vectors([vector_record]) # This is sync
            
            if success:
                await self._save_semantic_summary_to_db(db, semantic_summary)
                await update_document_vector_status(db, doc_id_uuid, VectorStatus.VECTORIZED)
                await log_event(db=db, level=LogLevel.INFO, message="Document successfully processed and stored in vector DB.",
                                source="service.semantic_summary.process_doc_for_vector_db", details=log_details_base)
                return True
            else:
                await log_event(db=db, level=LogLevel.ERROR, message="Failed to store document vector in vector DB.",
                                source="service.semantic_summary.process_doc_for_vector_db", details=log_details_base)
                await update_document_vector_status(db, doc_id_uuid, VectorStatus.FAILED, "Vector storage failed.")
                return False
                
        except Exception as e:
            await log_event(db=db, level=LogLevel.ERROR, message=f"Unexpected error processing document {doc_id_str} for vector DB: {str(e)}",
                            source="service.semantic_summary.process_doc_for_vector_db", exc_info=True,
                            details={**log_details_base, "error": str(e), "error_type": type(e).__name__})
            await update_document_vector_status(db, doc_id_uuid, VectorStatus.FAILED, f"Unexpected processing error: {str(e)}")
            return False
    
    async def _save_semantic_summary_to_db(
        self, 
        db: AsyncIOMotorDatabase,
        semantic_summary: SemanticSummary
    ):
        """將生成的語義摘要保存到MongoDB (如果需要)"""
        # 實現取決於是否需要將 SemanticSummary 存儲回 Document 模型或單獨的集合
        # 目前假設它可能更新 Document 的某個欄位或記錄到日誌
        # 如果要更新 Document，需要 document_id 和相應的 CRUD 操作
        # logger.debug(f"語義摘要已生成，文檔ID: {semantic_summary.document_id}，摘要: {semantic_summary.summary_text[:100]}...")
        # 示例：如果 Document 模型有一個欄位來存儲摘要文本：
        # from app.crud.crud_documents import update_document
        # await update_document(db, uuid.UUID(semantic_summary.document_id), {"semantic_summary_text": semantic_summary.summary_text})
        pass # 暫時不實現具體的數據庫保存，因為它超出了向量化流程的核心

    async def batch_process_documents(
        self, 
        db: AsyncIOMotorDatabase,
        document_ids: List[str], # 確保傳入的是字符串ID列表
        batch_size: int = 5 # 保留 batch_size 但目前循環是逐個處理
    ) -> Dict[str, Any]:
        """
        批量處理文檔到向量資料庫。
        注意：當前的實現是逐個調用 process_document_for_vector_db。
        一個更優化的批量處理可以考慮批量生成摘要、批量向量化、批量插入。
        """
        await log_event(db=db, level=LogLevel.INFO,
                        message=f"Starting batch processing of {len(document_ids)} documents for vector DB.",
                        source="service.semantic_summary.batch_process",
                        details={"num_documents_to_process": len(document_ids), "batch_size_param": batch_size})

        from app.crud.crud_documents import get_document_by_id # Keep lazy import if it's for a specific reason

        results = {"processed_successfully": [], "failed_to_process": [], "not_found": []}
        processed_count = 0
        success_count = 0

        for doc_id_str in document_ids:
            processed_count +=1
            log_details_item = {"document_id": doc_id_str, "batch_total_count": len(document_ids)}
            try:
                doc_uuid = uuid.UUID(doc_id_str)
                document = await get_document_by_id(db, doc_uuid)
                if not document:
                    await log_event(db=db, level=LogLevel.WARNING, message=f"Document not found during batch processing: {doc_id_str}",
                                    source="service.semantic_summary.batch_process", details=log_details_item)
                    results["not_found"].append(doc_id_str)
                    continue
                
                # process_document_for_vector_db will log its own detailed steps and errors
                success = await self.process_document_for_vector_db(db, document)
                if success:
                    results["processed_successfully"].append(doc_id_str)
                    success_count +=1
                else:
                    results["failed_to_process"].append(doc_id_str) # Already logged by the called function
            except ValueError:
                await log_event(db=db, level=LogLevel.ERROR, message=f"Invalid document ID format in batch: {doc_id_str}",
                                source="service.semantic_summary.batch_process", details=log_details_item)
                results["failed_to_process"].append({"id": doc_id_str, "error": "Invalid ID format"})
            except Exception as e:
                await log_event(db=db, level=LogLevel.ERROR, message=f"Error processing document {doc_id_str} in batch: {str(e)}",
                                source="service.semantic_summary.batch_process", exc_info=True, details={**log_details_item, "error": str(e)})
                results["failed_to_process"].append({"id": doc_id_str, "error": str(e)})
                try: # Attempt to mark doc as failed if general error occurs here
                    doc_uuid_for_fail_update = uuid.UUID(doc_id_str)
                    await update_document_vector_status(db, doc_uuid_for_fail_update, VectorStatus.FAILED, f"Batch processing error: {str(e)}")
                except Exception as update_err:
                     await log_event(db=db, level=LogLevel.ERROR, message=f"Failed to update status to FAILED for doc {doc_id_str} after batch error: {update_err}",
                                    source="service.semantic_summary.batch_process", details=log_details_item)

        summary_message = f"Batch processing completed. Total requested: {len(document_ids)}, Processed: {processed_count}, Succeeded: {success_count}, Failed: {len(results['failed_to_process'])}, Not Found: {len(results['not_found'])}."
        await log_event(db=db, level=LogLevel.INFO, message=summary_message,
                        source="service.semantic_summary.batch_process",
                        details={
                            "total_requested": len(document_ids), "processed_count": processed_count,
                            "successful_vectorization": success_count,
                            "failed_vectorization": len(results['failed_to_process']),
                            "docs_not_found": len(results['not_found'])
                        })
        return results

# 全局語義摘要服務實例
semantic_summary_service = SemanticSummaryService() 