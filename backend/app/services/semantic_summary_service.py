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
from datetime import datetime

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
        doc_id_uuid: uuid.UUID = document.id 
        doc_id_str: str = str(document.id)
        
        # For overall timing and base details for log_event
        process_start_time = datetime.now() 
        log_details_base = {"document_id": doc_id_str, "filename": document.filename, "user_id": str(document.owner_id)}

        logger.info(f"[{process_start_time.isoformat()}] Starting processing for document {doc_id_str} for vector DB.")
        await log_event(db=db, level=LogLevel.INFO, message="Starting document processing for vector DB.",
                        source="service.semantic_summary.process_doc_for_vector_db.start", details=log_details_base)

        try:
            # Step 1: Update status to PROCESSING
            step_start_time = datetime.now()
            logger.info(f"[{step_start_time.isoformat()}] Updating status to PROCESSING for document {doc_id_str}.")
            await update_document_vector_status(db, doc_id_uuid, VectorStatus.PROCESSING)
            step_end_time = datetime.now()
            logger.info(f"[{step_end_time.isoformat()}] Status updated to PROCESSING for document {doc_id_str}. Duration: {step_end_time - step_start_time}")
            # log_event for this step is implicitly covered by the subsequent logs if successful, or error logs if failed.

            # Step 2: Delete old vectors
            step_start_time = datetime.now()
            logger.info(f"[{step_start_time.isoformat()}] Attempting to delete old vectors for document {doc_id_str}.")
            # Assuming vector_db_service.delete_by_document_id logs internally or is not critical for db log_event here
            vector_db_service.delete_by_document_id(doc_id_str) 
            step_end_time = datetime.now()
            logger.info(f"[{step_end_time.isoformat()}] Old vectors deleted (if existed) for document {doc_id_str}. Duration: {step_end_time - step_start_time}")
            await log_event(db=db, level=LogLevel.DEBUG, message="Old vectors deletion attempt completed.",
                            source="service.semantic_summary.process_doc_for_vector_db.delete_old_vectors", details=log_details_base)

            # Step 3: Generate semantic summary
            step_start_time = datetime.now()
            logger.info(f"[{step_start_time.isoformat()}] Generating semantic summary for document {doc_id_str}.")
            semantic_summary = await self.generate_semantic_summary(db, document) # generate_semantic_summary has its own log_events
            step_end_time = datetime.now()
            if not semantic_summary:
                logger.error(f"[{step_end_time.isoformat()}] Failed to generate semantic summary for document {doc_id_str}. Duration: {step_end_time - step_start_time}")
                # log_event is already called within generate_semantic_summary for failure
                await update_document_vector_status(db, doc_id_uuid, VectorStatus.FAILED, "語義摘要生成失敗") # crud_documents.update_document_vector_status also logs
                return False
            logger.info(f"[{step_end_time.isoformat()}] Semantic summary generated for document {doc_id_str}. Duration: {step_end_time - step_start_time}")
            
            # Step 4: Vectorize text
            step_start_time = datetime.now()
            logger.info(f"[{step_start_time.isoformat()}] Vectorizing text for document {doc_id_str}.")
            text_parts = []
            key_info = None

            if semantic_summary.full_ai_analysis and isinstance(semantic_summary.full_ai_analysis, dict):
                key_info = semantic_summary.full_ai_analysis.get("key_information")

            if isinstance(key_info, dict):
                # 1. content_summary
                content_summary = key_info.get("content_summary", "")
                if isinstance(content_summary, str) and content_summary.strip():
                    text_parts.append(content_summary.strip())

                # 2. searchable_keywords
                searchable_keywords = key_info.get("searchable_keywords", [])
                if isinstance(searchable_keywords, list):
                    valid_keywords = [str(kw).strip() for kw in searchable_keywords if kw and isinstance(kw, str) and str(kw).strip()]
                    if valid_keywords:
                        text_parts.append(" ".join(valid_keywords))

                # 3. semantic_tags
                semantic_tags = key_info.get("semantic_tags", [])
                if isinstance(semantic_tags, list):
                    valid_tags = [str(tag).strip() for tag in semantic_tags if tag and isinstance(tag, str) and str(tag).strip()]
                    if valid_tags:
                        text_parts.append(" ".join(valid_tags))

                # 4. knowledge_domains
                knowledge_domains = key_info.get("knowledge_domains", [])
                if isinstance(knowledge_domains, list):
                    valid_domains = [str(kd).strip() for kd in knowledge_domains if kd and isinstance(kd, str) and str(kd).strip()]
                    if valid_domains:
                        text_parts.append(" ".join(valid_domains))

                # 5. main_topics
                main_topics = key_info.get("main_topics", [])
                if isinstance(main_topics, list):
                    valid_topics = [str(topic).strip() for topic in main_topics if topic and isinstance(topic, str) and str(topic).strip()]
                    if valid_topics:
                        text_parts.append(" ".join(valid_topics))

                # 6. key_concepts
                key_concepts = key_info.get("key_concepts", [])
                if isinstance(key_concepts, list):
                    valid_concepts = [str(concept).strip() for concept in key_concepts if concept and isinstance(concept, str) and str(concept).strip()]
                    if valid_concepts:
                        text_parts.append(" ".join(valid_concepts))
            
            # Fallback: if key_info was not available or did not yield any text_parts,
            # try to use semantic_summary.summary_text (which might be from an older analysis or basic fallback)
            if not text_parts and semantic_summary.summary_text and semantic_summary.summary_text.strip():
                logger.info(f"No structured key_information found or it yielded no text parts for doc {doc_id_str}. Using semantic_summary.summary_text for embedding.")
                text_parts.append(semantic_summary.summary_text.strip())

            text_to_embed = "\n".join(filter(None, text_parts))

            if not text_to_embed.strip():
                fallback_reason = "Combined text for embedding was empty after processing key_information and summary_text"
                logger.warning(f"文檔 {doc_id_str} 的組合向量化文本為空，將使用文件名作為最終後備。")
                # The original code had semantic_summary.summary_text here, but if that was already tried and text_parts is empty,
                # it means it was also empty or not useful. So, proceeding to filename.
                if document.filename:
                     text_to_embed = document.filename # Removed "文件名：" prefix for cleaner embedding
                     fallback_reason += ", using filename."
                else:
                    text_to_embed = "文檔內容無法確定" 
                    fallback_reason += ", using placeholder as no content determinable."
                    logger.error(f"文檔 {doc_id_str} 無法確定用於向量化的文本。")
                await log_event(db=db, level=LogLevel.WARNING, message="Text to embed was empty, using fallback.",
                                source="service.semantic_summary.process_doc_for_vector_db.vectorize_fallback", 
                                details={**log_details_base, "fallback_reason": fallback_reason, "fallback_text_length": len(text_to_embed)})

            embedding_vector =  embedding_service.encode_text(text_to_embed) # encode_text is async now
            step_end_time = datetime.now()
            logger.info(f"[{step_end_time.isoformat()}] Text vectorized for document {doc_id_str}. Duration: {step_end_time - step_start_time}. Vector dim: {len(embedding_vector) if embedding_vector else 'N/A'}")
            
            # Step 5: Create VectorRecord
            vector_record = VectorRecord(
                document_id=doc_id_str,
                owner_id=str(document.owner_id),
                embedding_vector=embedding_vector,
                chunk_text=text_to_embed[:1000], # Store a snippet of the embedded text
                embedding_model=embedding_service.model_name,
                metadata={"file_type": document.file_type or ""}
            )
            
            # Step 6: Store vector to database
            step_start_time = datetime.now()
            logger.info(f"[{step_start_time.isoformat()}] Storing vector to database for document {doc_id_str}.")
            # vector_db_service.insert_vectors logs internally
            success = vector_db_service.insert_vectors([vector_record]) # This is sync in your provided code
            step_end_time = datetime.now()
            
            if success:
                logger.info(f"[{step_end_time.isoformat()}] Vector stored successfully for document {doc_id_str}. Duration: {step_end_time - step_start_time}")
                await self._save_semantic_summary_to_db(db, semantic_summary) # Assuming this is a quick metadata save or similar
                
                # Final status update to VECTORIZED
                await update_document_vector_status(db, doc_id_uuid, VectorStatus.VECTORIZED) # crud_documents.update_document_vector_status also logs
                
                total_duration = datetime.now() - process_start_time
                logger.info(f"[{datetime.now().isoformat()}] Successfully processed document {doc_id_str} for vector DB. Total duration: {total_duration}")
                await log_event(db=db, level=LogLevel.INFO, message="Document successfully processed and vectorized.",
                                source="service.semantic_summary.process_doc_for_vector_db.success", 
                                details={**log_details_base, "total_duration_seconds": total_duration.total_seconds()})
                return True
            else:
                logger.error(f"[{step_end_time.isoformat()}] Failed to store vector for document {doc_id_str}. Duration: {step_end_time - step_start_time}")
                await log_event(db=db, level=LogLevel.ERROR, message="Failed to store document vector in vector DB.",
                                source="service.semantic_summary.process_doc_for_vector_db.vector_storage_failed", details=log_details_base)
                await update_document_vector_status(db, doc_id_uuid, VectorStatus.FAILED, "向量存儲失敗") # crud_documents.update_document_vector_status also logs
                total_duration = datetime.now() - process_start_time
                logger.info(f"[{datetime.now().isoformat()}] Failed to process document {doc_id_str} for vector DB (vector storage). Total duration: {total_duration}")
                return False
                
        except Exception as e:
            current_time = datetime.now()
            logger.error(f"[{current_time.isoformat()}] Error processing document {doc_id_str} for vector DB: {str(e)}", exc_info=True)
            # Ensure log_event has the error string
            error_str = str(e)
            await log_event(db=db, level=LogLevel.ERROR, 
                            message=f"Unexpected error processing document for vector DB: {error_str}",
                            source="service.semantic_summary.process_doc_for_vector_db.exception", 
                            details={**log_details_base, "error": error_str, "error_type": type(e).__name__})
            try:
                await update_document_vector_status(db, doc_id_uuid, VectorStatus.FAILED, f"處理時發生意外錯誤: {error_str}")
            except Exception as e_update_status:
                 logger.error(f"[{datetime.now().isoformat()}] CRITICAL: Failed to update status to FAILED for doc {doc_id_str} after main processing exception: {str(e_update_status)}", exc_info=True)
                 await log_event(db=db, level=LogLevel.CRITICAL, 
                                 message=f"CRITICAL: Failed to update status to FAILED for doc {doc_id_str} after main processing exception: {str(e_update_status)}",
                                 source="service.semantic_summary.process_doc_for_vector_db.exception_status_update_failed",
                                 details={**log_details_base, "main_error": error_str, "status_update_error": str(e_update_status)})


            total_duration = datetime.now() - process_start_time
            logger.info(f"[{datetime.now().isoformat()}] Failed to process document {doc_id_str} for vector DB due to exception. Total duration: {total_duration}")
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