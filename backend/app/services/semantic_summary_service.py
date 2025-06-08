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
from app.core.config import settings
import logging
import uuid
from datetime import datetime
import re

logger = AppLogger(__name__, level=logging.DEBUG).get_logger()

class SemanticSummaryService:
    """語義摘要生成服務"""
    
    def __init__(self):
        # 使用統一AI服務，不再需要單獨的AI服務實例
        pass
    
    def _get_document_text(self, document: Document) -> tuple[str, str]:
        """
        從文檔中獲取最佳的文本內容
        
        按優先級順序嘗試不同的文本來源：
        1. document.extracted_text (頂層)
        2. document.analysis.ai_analysis_output.extracted_text
        3. document.analysis.text_content.full_text (如果存在)
        4. document.analysis.extracted_text (如果存在)
        
        Returns:
            tuple[str, str]: (找到的最佳文本內容, 文本來源說明)
        """
        # 1. 優先使用頂層 extracted_text
        if document.extracted_text and document.extracted_text.strip():
            return document.extracted_text.strip(), "document.extracted_text"
        
        # 如果沒有 analysis，返回空字符串
        if not document.analysis:
            return "", "no_analysis"
        
        # 2. 嘗試 analysis.ai_analysis_output.extracted_text
        if (document.analysis.ai_analysis_output and 
            isinstance(document.analysis.ai_analysis_output, dict) and
            document.analysis.ai_analysis_output.get("extracted_text")):
            extracted_text = document.analysis.ai_analysis_output["extracted_text"]
            if isinstance(extracted_text, str) and extracted_text.strip():
                return extracted_text.strip(), "analysis.ai_analysis_output.extracted_text"
        
        # 3. 嘗試 analysis.text_content.full_text (如果存在這個結構)
        if hasattr(document.analysis, 'text_content') and hasattr(document.analysis.text_content, 'full_text'):
            full_text = document.analysis.text_content.full_text
            if isinstance(full_text, str) and full_text.strip():
                return full_text.strip(), "analysis.text_content.full_text"
        
        # 4. 嘗試 analysis.extracted_text (如果存在)
        if hasattr(document.analysis, 'extracted_text') and document.analysis.extracted_text:
            extracted_text = document.analysis.extracted_text
            if isinstance(extracted_text, str) and extracted_text.strip():
                return extracted_text.strip(), "analysis.extracted_text"
        
        return "", "no_text_found"

    def _create_text_chunks(self, text: str, chunk_size: int = None, chunk_overlap: int = 50) -> List[str]:
        """
        將長文本切分成帶有重疊的塊
        
        Args:
            text: 要分塊的文本
            chunk_size: 每個塊的字符數（如果為None，使用embedding模型的限制）
            chunk_overlap: 塊之間的重疊字符數
            
        Returns:
            文本塊列表
        """
        if not text or not text.strip():
            return []
        
        # 如果沒有指定chunk_size，使用embedding模型的限制，並預留一些空間
        if chunk_size is None:
            max_embedding_length = getattr(settings, 'EMBEDDING_MAX_LENGTH', 512)
            chunk_size = max_embedding_length - 50  # 預留50字符的安全邊界
        
        # 清理文本
        text = text.strip()
        
        # 如果文本長度小於分塊大小，直接返回
        if len(text) <= chunk_size:
            return [text]
        
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + chunk_size
            
            # 如果不是最後一塊，嘗試在句子邊界處切分
            if end < len(text):
                # 尋找句子結束符號（句號、問號、感嘆號）
                sentence_end_pattern = r'[。！？.!?]'
                
                # 在當前塊的後半部分尋找句子邊界
                search_start = max(start + chunk_size // 2, end - 100)
                search_text = text[search_start:end + 50]  # 稍微延展搜索範圍
                
                matches = list(re.finditer(sentence_end_pattern, search_text))
                if matches:
                    # 使用最後一個句子邊界
                    last_match = matches[-1]
                    actual_end = search_start + last_match.end()
                    if actual_end > start:  # 確保不會產生空塊
                        end = actual_end
            
            chunk = text[start:end].strip()
            if chunk:  # 只添加非空塊
                chunks.append(chunk)
            
            # 計算下一個開始位置，考慮重疊
            start = max(start + 1, end - chunk_overlap)
            
            # 防止無限循環
            if start >= len(text):
                break
        
        return chunks
    
    def _smart_truncate(self, text: str, max_length: int) -> str:
        """
        智能截斷文本，盡量在句子或詞語邊界截斷
        
        Args:
            text: 要截斷的文本
            max_length: 最大長度
            
        Returns:
            截斷後的文本
        """
        if not text or max_length <= 0:
            return ""
        
        if len(text) <= max_length:
            return text
        
        # 如果需要截斷，嘗試在較好的位置截斷
        truncated = text[:max_length-3]  # 預留 "..." 的空間
        
        # 嘗試在句子邊界截斷
        sentence_endings = ['。', '！', '？', '.', '!', '?']
        best_cut = -1
        for ending in sentence_endings:
            pos = truncated.rfind(ending)
            if pos > len(truncated) * 0.7:  # 至少保留70%的內容
                best_cut = pos + 1
                break
        
        # 如果沒找到句子邊界，嘗試在詞語邊界截斷
        if best_cut == -1:
            word_boundaries = [' ', '，', '、', ',', ';', '；']
            for boundary in word_boundaries:
                pos = truncated.rfind(boundary)
                if pos > len(truncated) * 0.8:  # 至少保留80%的內容
                    best_cut = pos
                    break
        
        if best_cut > 0:
            return text[:best_cut] + "..."
        else:
            return truncated + "..."
    
    def _smart_compress_list(self, items: List[str], max_length: int) -> str:
        """
        智能壓縮列表為字符串，優先保留更多項目
        
        Args:
            items: 要壓縮的字符串列表
            max_length: 最大長度
            
        Returns:
            壓縮後的字符串
        """
        if not items or max_length <= 0:
            return ""
        
        # 如果沒有長度限制問題，直接返回
        full_string = ', '.join(items)
        if len(full_string) <= max_length:
            return full_string
        
        # 需要壓縮：優先保留更多項目，必要時截短每個項目
        compressed_items = []
        current_length = 0
        separator_length = 2  # ", " 的長度
        
        # 計算平均每個項目可以分配的長度
        estimated_item_length = (max_length - (len(items) - 1) * separator_length) // len(items)
        estimated_item_length = max(estimated_item_length, 3)  # 至少保留3個字符
        
        for i, item in enumerate(items):
            if not item:
                continue
                
            # 如果是最後一個項目，使用剩餘的所有空間
            if i == len(items) - 1:
                remaining_space = max_length - current_length
                if remaining_space > 0:
                    compressed_item = self._smart_truncate(item, remaining_space)
                    if compressed_item:
                        compressed_items.append(compressed_item)
                break
            
            # 壓縮當前項目
            compressed_item = self._smart_truncate(item, estimated_item_length)
            if compressed_item:
                # 檢查添加這個項目是否會超長
                item_with_separator = compressed_item + (", " if compressed_items else "")
                if current_length + len(item_with_separator) <= max_length:
                    compressed_items.append(compressed_item)
                    current_length += len(item_with_separator)
                else:
                    # 沒有空間了，停止添加
                    break
        
        result = ', '.join(compressed_items)
        
        # 如果還有項目沒有包含，添加省略號提示
        if len(compressed_items) < len([item for item in items if item]):
            remaining_count = len([item for item in items if item]) - len(compressed_items)
            ellipsis = f"...+{remaining_count}項"
            if len(result) + len(ellipsis) <= max_length:
                result += ellipsis
            elif len(ellipsis) < max_length:
                # 縮短結果為省略號騰出空間
                result = result[:max_length - len(ellipsis)] + ellipsis
        
        return result
    
    def _create_enhanced_metadata(self, document: Document, semantic_summary: SemanticSummary) -> Dict[str, Any]:
        """
        創建增強的元數據，將語義摘要信息作為豐富的過濾和搜索條件
        
        Args:
            document: 原始文檔
            semantic_summary: 生成的語義摘要
            
        Returns:
            增強的元數據字典
        """
        metadata = {
            "file_type": document.file_type or "",
            "filename": document.filename or "",
            "document_summary": semantic_summary.summary_text,
            "key_terms": semantic_summary.key_terms,
        }
        
        # 如果有完整的AI分析結果，提取更多結構化信息
        if semantic_summary.full_ai_analysis and isinstance(semantic_summary.full_ai_analysis, dict):
            key_info = semantic_summary.full_ai_analysis.get("key_information", {})
            
            if isinstance(key_info, dict):
                # 提取可搜索的關鍵詞
                searchable_keywords = key_info.get("searchable_keywords", [])
                if isinstance(searchable_keywords, list):
                    metadata["searchable_keywords"] = [str(kw).strip() for kw in searchable_keywords if kw]
                
                # 提取知識領域
                knowledge_domains = key_info.get("knowledge_domains", [])
                if isinstance(knowledge_domains, list):
                    metadata["knowledge_domains"] = [str(kd).strip() for kd in knowledge_domains if kd]
                
                # 提取內容類型或主題
                content_type = key_info.get("content_type", "")
                if content_type:
                    metadata["content_type"] = str(content_type).strip()
                
                # 儲存完整的AI分析（可選，用於調試）
                metadata["full_ai_analysis"] = semantic_summary.full_ai_analysis
        
        return metadata

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
            
            # 使用新的文本獲取方法
            document_text, text_source = self._get_document_text(document)
            
            if not document_text or len(document_text.strip()) < 50:
                await log_event(db=db, level=LogLevel.WARNING, message=f"Document content too short for summarization: {doc_id_str} ({len(document_text.strip())} chars). Text source: {text_source}",
                                source="service.semantic_summary.generate_summary", details=log_details_initial)
                return None

            await log_event(db=db, level=LogLevel.DEBUG, message=f"No usable existing summary for doc {doc_id_str}. Calling AI for new text analysis. Text length: {len(document_text)} chars. Text source: {text_source}",
                            source="service.semantic_summary.generate_summary", details=log_details_initial)

            prompt_template = await prompt_manager_simplified.get_prompt(PromptType.TEXT_ANALYSIS, db)
            if not prompt_template:
                await log_event(db=db, level=LogLevel.ERROR, message=f"Failed to get TEXT_ANALYSIS prompt template for doc {doc_id_str}. Using fallback summary.",
                                source="service.semantic_summary.generate_summary", details=log_details_initial)
                summary_text = await self._generate_fallback_summary(document, db=db) # Pass db
                return SemanticSummary(document_id=doc_id_str, summary_text=summary_text, file_type=document.file_type, key_terms=[])

            # 使用設定中的AI文本分析最大字符限制
            max_text_length = settings.AI_MAX_INPUT_CHARS_TEXT_ANALYSIS
            text_content = document_text[:max_text_length] if len(document_text) > max_text_length else document_text
            
            system_prompt, user_prompt = prompt_manager_simplified.format_prompt(
                prompt_template, text_content=text_content
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
            # 使用新的文本獲取方法
            text, text_source = self._get_document_text(document)
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
        處理文檔並實現兩階段混合檢索策略 (Two-Stage Hybrid Retrieval)
        
        完整流程：
        1. 更新狀態為 PROCESSING
        2. 刪除舊向量 (實現覆蓋)
        3. 生成語義摘要
        4. 創建摘要向量 (Summary Vector) - 用於第一階段粗篩選
        5. 對文檔文本進行分塊
        6. 創建內容塊向量 (Chunk Vectors) - 用於第二階段精排序
        7. 批量存儲到向量資料庫
        8. 更新文檔狀態 (VECTORIZED 或 FAILED)
        """
        doc_id_uuid: uuid.UUID = document.id 
        doc_id_str: str = str(document.id)
        
        # For overall timing and base details for log_event
        process_start_time = datetime.now() 
        log_details_base = {"document_id": doc_id_str, "filename": document.filename, "user_id": str(document.owner_id)}

        logger.info(f"[{process_start_time.isoformat()}] Starting Two-Stage Hybrid Retrieval processing for document {doc_id_str}.")
        await log_event(db=db, level=LogLevel.INFO, message="Starting Two-Stage Hybrid Retrieval document processing.",
                        source="service.semantic_summary.process_doc_hybrid.start", details=log_details_base)

        try:
            # Step 1: Update status to PROCESSING
            step_start_time = datetime.now()
            logger.info(f"[{step_start_time.isoformat()}] Updating status to PROCESSING for document {doc_id_str}.")
            await update_document_vector_status(db, doc_id_uuid, VectorStatus.PROCESSING)
            step_end_time = datetime.now()
            logger.info(f"[{step_end_time.isoformat()}] Status updated to PROCESSING for document {doc_id_str}. Duration: {step_end_time - step_start_time}")

            # Step 2: Delete old vectors
            step_start_time = datetime.now()
            logger.info(f"[{step_start_time.isoformat()}] Attempting to delete old vectors for document {doc_id_str}.")
            vector_db_service.delete_by_document_id(doc_id_str) 
            step_end_time = datetime.now()
            logger.info(f"[{step_end_time.isoformat()}] Old vectors deleted (if existed) for document {doc_id_str}. Duration: {step_end_time - step_start_time}")
            await log_event(db=db, level=LogLevel.DEBUG, message="Old vectors deletion attempt completed.",
                            source="service.semantic_summary.process_doc_hybrid.delete_old_vectors", details=log_details_base)

            # Step 3: Generate semantic summary (用於摘要向量和元數據)
            step_start_time = datetime.now()
            logger.info(f"[{step_start_time.isoformat()}] Generating semantic summary for document {doc_id_str}.")
            semantic_summary = await self.generate_semantic_summary(db, document) # generate_semantic_summary has its own log_events
            step_end_time = datetime.now()
            
            if not semantic_summary:
                logger.error(f"[{step_end_time.isoformat()}] Failed to generate semantic summary for document {doc_id_str}. Duration: {step_end_time - step_start_time}")
                await update_document_vector_status(db, doc_id_uuid, VectorStatus.FAILED, "語義摘要生成失敗")
                return False
            logger.info(f"[{step_end_time.isoformat()}] Semantic summary generated for document {doc_id_str}. Duration: {step_end_time - step_start_time}")
            
            # Step 4: 創建摘要向量 (Summary Vector) - 第一階段粗篩選
            step_start_time = datetime.now()
            logger.info(f"[{step_start_time.isoformat()}] Creating summary vector for document {doc_id_str}.")
            
            summary_vector = await self._create_summary_vector(document, semantic_summary)
            
            step_end_time = datetime.now()
            logger.info(f"[{step_end_time.isoformat()}] Summary vector created for document {doc_id_str}. Duration: {step_end_time - step_start_time}")
            
            # Step 5: 對文檔的原始文本進行分塊
            step_start_time = datetime.now()
            logger.info(f"[{step_start_time.isoformat()}] Creating text chunks for document {doc_id_str}.")
            
            # 設定分塊參數（自動適配embedding模型限制）
            chunk_overlap = getattr(settings, 'VECTOR_CHUNK_OVERLAP', 50)  # 可配置的重疊大小
            
            # 使用新的文本獲取方法
            document_text, text_source = self._get_document_text(document)
            text_chunks = self._create_text_chunks(
                document_text,
                chunk_size=None,  # 使用自動計算的大小
                chunk_overlap=chunk_overlap
            )
            
            step_end_time = datetime.now()
            
            if not text_chunks:
                logger.warning(f"[{step_end_time.isoformat()}] Document {doc_id_str} has no valid text content for chunking. Duration: {step_end_time - step_start_time}. Text source: {text_source}, Text length: {len(document_text)}")
                # 即使沒有chunks，我們仍然可以繼續，只使用摘要向量
                text_chunks = []
                logger.info(f"Document {doc_id_str} will only have summary vector (no content chunks).")

            # 計算實際使用的chunk_size（用於日誌）
            max_embedding_length = getattr(settings, 'EMBEDDING_MAX_LENGTH', 512)
            actual_chunk_size = max_embedding_length - 50  # 與_create_text_chunks中的邏輯一致
            
            logger.info(f"[{step_end_time.isoformat()}] Document {doc_id_str} split into {len(text_chunks)} chunks. Duration: {step_end_time - step_start_time}. Text source: {text_source}")
            await log_event(db=db, level=LogLevel.INFO, message=f"Document successfully split into {len(text_chunks)} text chunks from {text_source}.",
                            source="service.semantic_summary.process_doc_hybrid.chunks_created", 
                            details={**log_details_base, "chunk_count": len(text_chunks), "chunk_size": actual_chunk_size, "chunk_overlap": chunk_overlap, "text_source": text_source, "text_length": len(document_text)})

            # Step 6: 創建內容塊向量 (Chunk Vectors) - 第二階段精排序
            step_start_time = datetime.now()
            logger.info(f"[{step_start_time.isoformat()}] Creating chunk vectors for document {doc_id_str}.")
            
            chunk_vectors = await self._create_chunk_vectors(document, semantic_summary, text_chunks)
            
            step_end_time = datetime.now()
            logger.info(f"[{step_end_time.isoformat()}] Created {len(chunk_vectors)} chunk vectors for document {doc_id_str}. Duration: {step_end_time - step_start_time}")

            # Step 7: 組合所有向量記錄
            all_vector_records = [summary_vector] + chunk_vectors
            
            if not all_vector_records:
                logger.error(f"No vector records created for document {doc_id_str}.")
                await log_event(db=db, level=LogLevel.ERROR, message="No vector records created for document.",
                                source="service.semantic_summary.process_doc_hybrid.no_vectors", details=log_details_base)
                await update_document_vector_status(db, doc_id_uuid, VectorStatus.FAILED, "未創建任何向量記錄")
                return False

            # Step 8: 批量插入所有向量記錄
            step_start_time = datetime.now()
            logger.info(f"[{step_start_time.isoformat()}] Batch inserting {len(all_vector_records)} vector records for document {doc_id_str}.")
            
            success = vector_db_service.insert_vectors(all_vector_records)
            step_end_time = datetime.now()
            
            if success:
                logger.info(f"[{step_end_time.isoformat()}] Successfully inserted {len(all_vector_records)} vector records for document {doc_id_str}. Duration: {step_end_time - step_start_time}")
                await self._save_semantic_summary_to_db(db, semantic_summary)
                
                # Final status update to VECTORIZED
                await update_document_vector_status(db, doc_id_uuid, VectorStatus.VECTORIZED)
                
                total_duration = datetime.now() - process_start_time
                logger.info(f"[{datetime.now().isoformat()}] Successfully processed document {doc_id_str} with Two-Stage Hybrid Retrieval strategy. Total duration: {total_duration}")
                await log_event(db=db, level=LogLevel.INFO, message="Document successfully processed with Two-Stage Hybrid Retrieval strategy.",
                                source="service.semantic_summary.process_doc_hybrid.success", 
                                details={
                                    **log_details_base, 
                                    "total_duration_seconds": total_duration.total_seconds(),
                                    "summary_vectors": 1,
                                    "chunk_vectors": len(chunk_vectors),
                                    "total_vectors": len(all_vector_records),
                                    "vectorization_strategy": "two_stage_hybrid"
                                })
                return True
            else:
                logger.error(f"[{step_end_time.isoformat()}] Failed to batch insert vector records for document {doc_id_str}. Duration: {step_end_time - step_start_time}")
                await log_event(db=db, level=LogLevel.ERROR, message="Failed to batch insert document vector records.",
                                source="service.semantic_summary.process_doc_hybrid.insert_failed", 
                                details={**log_details_base, "attempted_vectors": len(all_vector_records)})
                await update_document_vector_status(db, doc_id_uuid, VectorStatus.FAILED, "向量批量存儲失敗")
                total_duration = datetime.now() - process_start_time
                logger.info(f"[{datetime.now().isoformat()}] Failed to process document {doc_id_str} with Two-Stage Hybrid Retrieval (batch insert failed). Total duration: {total_duration}")
                return False
                
        except Exception as e:
            current_time = datetime.now()
            logger.error(f"[{current_time.isoformat()}] Error processing document {doc_id_str} with Two-Stage Hybrid Retrieval: {str(e)}", exc_info=True)
            error_str = str(e)
            await log_event(db=db, level=LogLevel.ERROR, 
                            message=f"Unexpected error in Two-Stage Hybrid Retrieval processing: {error_str}",
                            source="service.semantic_summary.process_doc_hybrid.exception", 
                            details={**log_details_base, "error": error_str, "error_type": type(e).__name__})
            try:
                await update_document_vector_status(db, doc_id_uuid, VectorStatus.FAILED, f"兩階段混合檢索處理時發生意外錯誤: {error_str}")
            except Exception as e_update_status:
                 logger.error(f"[{datetime.now().isoformat()}] CRITICAL: Failed to update status to FAILED for doc {doc_id_str} after Two-Stage Hybrid Retrieval exception: {str(e_update_status)}", exc_info=True)
                 await log_event(db=db, level=LogLevel.CRITICAL, 
                                 message=f"CRITICAL: Failed to update status to FAILED for doc {doc_id_str} after Two-Stage Hybrid Retrieval exception: {str(e_update_status)}",
                                 source="service.semantic_summary.process_doc_hybrid.exception_status_update_failed",
                                 details={**log_details_base, "main_error": error_str, "status_update_error": str(e_update_status)})

            total_duration = datetime.now() - process_start_time
            logger.info(f"[{datetime.now().isoformat()}] Failed to process document {doc_id_str} with Two-Stage Hybrid Retrieval due to exception. Total duration: {total_duration}")
            return False
    
    async def _create_summary_vector(self, document: Document, semantic_summary: SemanticSummary) -> VectorRecord:
        """
        創建摘要向量 (Summary Vector) - 用於第一階段粗篩選
        
        這個向量代表整個文檔的高層次語義，用於快速找出相關文檔
        """
        doc_id_str = str(document.id)
        
        # 組合摘要文本，創建豐富的文檔級別向量化內容
        summary_parts = []
        
        # 1. 文件基本信息
        summary_parts.append(f"文件名: {document.filename}")
        
        # 2. 核心內容摘要
        if semantic_summary.summary_text:
            summary_parts.append(f"內容摘要: {semantic_summary.summary_text}")
        
        # 3. 語義標籤和關鍵詞 (來自AI分析)
        if semantic_summary.key_terms:
            summary_parts.append(f"關鍵詞: {', '.join(semantic_summary.key_terms)}")
        
        # 4. 如果有完整的AI分析，提取更多信息
        if semantic_summary.full_ai_analysis and isinstance(semantic_summary.full_ai_analysis, dict):
            key_info = semantic_summary.full_ai_analysis.get("key_information", {})
            
            if isinstance(key_info, dict):
                # 可搜索關鍵詞
                searchable_keywords = key_info.get("searchable_keywords", [])
                if isinstance(searchable_keywords, list) and searchable_keywords:
                    summary_parts.append(f"搜索關鍵詞: {', '.join(searchable_keywords[:10])}")
                
                # 知識領域
                knowledge_domains = key_info.get("knowledge_domains", [])
                if isinstance(knowledge_domains, list) and knowledge_domains:
                    summary_parts.append(f"知識領域: {', '.join(knowledge_domains)}")
                
                # 內容類型
                content_type = key_info.get("content_type", "")
                if content_type:
                    summary_parts.append(f"內容類型: {content_type}")
        
        # 組合最終的摘要文本
        summary_text_for_vector = "\n".join(summary_parts)
        
        # 動態調整摘要文本，保留所有類型的信息但智能壓縮
        max_embedding_length = getattr(settings, 'EMBEDDING_MAX_LENGTH', 512)
        if len(summary_text_for_vector) > max_embedding_length:
            logger.info(f"摘要文本超長({len(summary_text_for_vector)}字符)，開始動態壓縮以保留所有信息類型")
            
            # 提取所有信息組件
            filename = document.filename
            summary_text = semantic_summary.summary_text
            key_terms = semantic_summary.key_terms or []
            
            # 從AI分析中提取更多信息
            searchable_keywords = []
            knowledge_domains = []
            content_type = ""
            
            if semantic_summary.full_ai_analysis and isinstance(semantic_summary.full_ai_analysis, dict):
                key_info = semantic_summary.full_ai_analysis.get("key_information", {})
                if isinstance(key_info, dict):
                    searchable_keywords = key_info.get("searchable_keywords", [])
                    if not isinstance(searchable_keywords, list):
                        searchable_keywords = []
                    
                    knowledge_domains = key_info.get("knowledge_domains", [])
                    if not isinstance(knowledge_domains, list):
                        knowledge_domains = []
                    
                    content_type = key_info.get("content_type", "")
            
            # 計算基礎組件的空間需求
            base_labels_length = len("文件名: ") + len("內容摘要: ") + len("關鍵詞: ") + len("搜索關鍵詞: ") + len("知識領域: ") + len("內容類型: ")
            separators_length = 5  # 5個換行符
            buffer_space = 20  # 緩衝空間
            
            available_content_space = max_embedding_length - base_labels_length - separators_length - buffer_space
            
            # 動態分配空間給各個組件（按重要性分配權重）
            weights = {
                'filename': 0.15,      # 15% - 文件名
                'summary': 0.50,       # 50% - 內容摘要（最重要）
                'key_terms': 0.15,     # 15% - 關鍵詞
                'searchable': 0.10,    # 10% - 搜索關鍵詞
                'domains': 0.08,       # 8% - 知識領域
                'content_type': 0.02   # 2% - 內容類型
            }
            
            # 智能壓縮各個組件
            compressed_filename = self._smart_truncate(filename, int(available_content_space * weights['filename']))
            compressed_summary = self._smart_truncate(summary_text, int(available_content_space * weights['summary']))
            compressed_key_terms = self._smart_compress_list(key_terms, int(available_content_space * weights['key_terms']))
            compressed_searchable = self._smart_compress_list(searchable_keywords, int(available_content_space * weights['searchable']))
            compressed_domains = self._smart_compress_list(knowledge_domains, int(available_content_space * weights['domains']))
            compressed_content_type = self._smart_truncate(content_type, int(available_content_space * weights['content_type']))
            
            # 重新組合摘要文本
            compressed_parts = []
            compressed_parts.append(f"文件名: {compressed_filename}")
            if compressed_summary:
                compressed_parts.append(f"內容摘要: {compressed_summary}")
            if compressed_key_terms:
                compressed_parts.append(f"關鍵詞: {compressed_key_terms}")
            if compressed_searchable:
                compressed_parts.append(f"搜索關鍵詞: {compressed_searchable}")
            if compressed_domains:
                compressed_parts.append(f"知識領域: {compressed_domains}")
            if compressed_content_type:
                compressed_parts.append(f"內容類型: {compressed_content_type}")
            
            summary_text_for_vector = "\n".join(compressed_parts)
            
            # 如果還是太長，進行最終調整
            if len(summary_text_for_vector) > max_embedding_length:
                summary_text_for_vector = summary_text_for_vector[:max_embedding_length-3] + "..."
            
            logger.info(f"摘要向量文本動態壓縮完成：{len('\n'.join(summary_parts))} → {len(summary_text_for_vector)} 字符，保留了所有信息類型")
        
        # 向量化摘要文本
        embedding_vector = embedding_service.encode_text(summary_text_for_vector)
        
        # 創建摘要向量的元數據
        summary_metadata = self._create_enhanced_metadata(document, semantic_summary)
        summary_metadata.update({
            "type": "summary",  # 標記為摘要向量
            "vector_purpose": "coarse_filtering",  # 用於粗篩選
            "summary_text_for_vector": summary_text_for_vector  # 保存向量化的文本
        })
        
        # 創建摘要向量記錄
        summary_vector = VectorRecord(
            document_id=doc_id_str,
            owner_id=str(document.owner_id),
            embedding_vector=embedding_vector,
            chunk_text=summary_text_for_vector,  # 儲存向量化的摘要文本
            embedding_model=embedding_service.model_name,
            metadata=summary_metadata
        )
        
        return summary_vector
    
    async def _create_chunk_vectors(
        self, 
        document: Document, 
        semantic_summary: SemanticSummary, 
        text_chunks: List[str]
    ) -> List[VectorRecord]:
        """
        創建內容塊向量 (Chunk Vectors) - 用於第二階段精排序
        
        這些向量代表文檔的具體內容片段，用於精確匹配
        """
        doc_id_str = str(document.id)
        chunk_vectors = []
        
        # 獲取基礎元數據
        base_metadata = self._create_enhanced_metadata(document, semantic_summary)
        
        for i, chunk_text in enumerate(text_chunks):
            chunk_id = f"{doc_id_str}_chunk_{i}"
            
            try:
                # 向量化每個 chunk
                embedding_vector = embedding_service.encode_text(chunk_text)
                
                if not embedding_vector or len(embedding_vector) == 0:
                    logger.warning(f"Chunk {chunk_id} vectorization returned empty vector, skipping.")
                    continue
                
                # 創建chunk向量的元數據
                chunk_metadata = base_metadata.copy()
                chunk_metadata.update({
                    "type": "chunk",  # 標記為內容塊向量
                    "vector_purpose": "fine_ranking",  # 用於精排序
                    "chunk_id": chunk_id,  # 唯一的塊識別符
                    "chunk_index": i,  # 在文檔中的順序
                    "total_chunks": len(text_chunks),  # 總塊數
                    "chunk_length": len(chunk_text)  # 塊的字符長度
                })
                
                # 創建內容塊向量記錄
                chunk_vector = VectorRecord(
                    document_id=doc_id_str,
                    owner_id=str(document.owner_id),
                    embedding_vector=embedding_vector,
                    chunk_text=chunk_text,  # 儲存完整的文本塊
                    embedding_model=embedding_service.model_name,
                    metadata=chunk_metadata
                )
                chunk_vectors.append(chunk_vector)
                
            except Exception as e_chunk:
                logger.warning(f"Failed to vectorize chunk {chunk_id}: {str(e_chunk)}")
                continue
        
        return chunk_vectors
    
    async def _save_semantic_summary_to_db(
        self, 
        db: AsyncIOMotorDatabase,
        semantic_summary: SemanticSummary
    ):
        """將生成的語義摘要和完整的AI分析結果保存到MongoDB"""
        if not semantic_summary.full_ai_analysis:
            logger.debug(f"文檔 {semantic_summary.document_id} 沒有完整的AI分析結果可保存。")
            return

        try:
            doc_id = uuid.UUID(semantic_summary.document_id)
            
            # 構建更新操作，只更新頂層的 analysis 欄位以避免路徑衝突
            update_operation = {
                "$set": {
                    "analysis.ai_analysis_output": semantic_summary.full_ai_analysis
                }
            }
            
            result = await db.documents.update_one({"_id": doc_id}, update_operation)
            
            if result.modified_count > 0:
                await log_event(
                    db=db,
                    level=LogLevel.INFO,
                    message=f"成功將AI分析結果保存到文檔 {doc_id}",
                    source="service.semantic_summary._save_semantic_summary_to_db",
                    details={"document_id": str(doc_id)}
                )
            elif result.matched_count == 0:
                logger.warning(f"嘗試保存AI分析結果時未找到文檔: {doc_id}")

        except Exception as e:
            await log_event(
                db=db,
                level=LogLevel.ERROR,
                message=f"保存AI分析結果到文檔 {semantic_summary.document_id} 時失敗: {e}",
                source="service.semantic_summary._save_semantic_summary_to_db",
                details={"document_id": semantic_summary.document_id, "error": str(e)},
                exc_info=True
            )

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
                        message=f"Starting batch chunked processing of {len(document_ids)} documents for vector DB.",
                        source="service.semantic_summary.batch_process_chunked",
                        details={"num_documents_to_process": len(document_ids), "batch_size_param": batch_size, "strategy": "chunking"})

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
                    await log_event(db=db, level=LogLevel.WARNING, message=f"Document not found during batch chunked processing: {doc_id_str}",
                                    source="service.semantic_summary.batch_process_chunked", details=log_details_item)
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
                await log_event(db=db, level=LogLevel.ERROR, message=f"Invalid document ID format in batch chunked processing: {doc_id_str}",
                                source="service.semantic_summary.batch_process_chunked", details=log_details_item)
                results["failed_to_process"].append({"id": doc_id_str, "error": "Invalid ID format"})
            except Exception as e:
                await log_event(db=db, level=LogLevel.ERROR, message=f"Error processing document {doc_id_str} in batch chunked processing: {str(e)}",
                                source="service.semantic_summary.batch_process_chunked", exc_info=True, details={**log_details_item, "error": str(e)})
                results["failed_to_process"].append({"id": doc_id_str, "error": str(e)})
                try: # Attempt to mark doc as failed if general error occurs here
                    doc_uuid_for_fail_update = uuid.UUID(doc_id_str)
                    await update_document_vector_status(db, doc_uuid_for_fail_update, VectorStatus.FAILED, f"Batch chunked processing error: {str(e)}")
                except Exception as update_err:
                     await log_event(db=db, level=LogLevel.ERROR, message=f"Failed to update status to FAILED for doc {doc_id_str} after batch chunked error: {update_err}",
                                    source="service.semantic_summary.batch_process_chunked", details=log_details_item)

        summary_message = f"Batch chunked processing completed. Total requested: {len(document_ids)}, Processed: {processed_count}, Succeeded: {success_count}, Failed: {len(results['failed_to_process'])}, Not Found: {len(results['not_found'])}."
        await log_event(db=db, level=LogLevel.INFO, message=summary_message,
                        source="service.semantic_summary.batch_process_chunked",
                        details={
                            "total_requested": len(document_ids), "processed_count": processed_count,
                            "successful_vectorization": success_count,
                            "failed_vectorization": len(results['failed_to_process']),
                            "docs_not_found": len(results['not_found']),
                            "processing_strategy": "chunking"
                        })
        return results

# 全局語義摘要服務實例
semantic_summary_service = SemanticSummaryService() 