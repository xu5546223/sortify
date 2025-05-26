from typing import Optional, Dict, Any, List
import json
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.core.logging_utils import AppLogger
from app.services.unified_ai_service_simplified import unified_ai_service_simplified
from app.services.embedding_service import embedding_service
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
        try:
            logger.info(f"正在為文檔 {document.id} 生成語義摘要 (彈性模式，優先使用現有分析)")

            # 檢查文檔是否有AI分析結果，並且結果是字典類型
            if document.analysis and isinstance(document.analysis.ai_analysis_output, dict):
                logger.info(f"文檔 {document.id} 找到現有的 AI 分析結果，嘗試直接提取摘要。")
                existing_analysis = document.analysis.ai_analysis_output
                key_info = existing_analysis.get("key_information", {})
                summary_text = key_info.get("content_summary", "")
                key_terms = key_info.get("semantic_tags", [])

                if isinstance(key_terms, str):
                    key_terms = [term.strip() for term in key_terms.split(',') if term.strip()]
                
                if summary_text and len(summary_text.strip()) >= 10:
                    logger.info(f"從現有分析中成功提取摘要和標籤: {document.id}")
                    return SemanticSummary(
                        document_id=document.id,
                        summary_text=summary_text,
                        file_type=document.file_type,
                        key_terms=key_terms,
                        full_ai_analysis=existing_analysis
                    )
                else:
                    logger.warning(f"現有 AI 分析結果中未能提取有效摘要或標籤，文檔ID: {document.id}。將進行新的文本分析。")
            
            # 如果沒有現成的有效摘要，或者文檔內容本身不足，則進行新的處理
            if not document.extracted_text or len(document.extracted_text.strip()) < 50:
                logger.warning(f"文檔 {document.id} 內容過少 ({len(document.extracted_text.strip()) if document.extracted_text else 0} chars)，跳過語義摘要生成")
                return None

            logger.info(f"文檔 {document.id} 未找到可用摘要或需重新分析，開始調用AI進行新的文本分析。")
            # 1. 獲取文本分析的提示詞模板
            prompt_template = await prompt_manager_simplified.get_prompt(PromptType.TEXT_ANALYSIS, db)
            if not prompt_template:
                logger.error(f"無法獲取 {PromptType.TEXT_ANALYSIS.value} 的提示詞模板，文檔 ID: {document.id}")
                # Fallback to simpler summary if prompt is missing
                summary_text = self._generate_fallback_summary(document)
                return SemanticSummary(
                    document_id=document.id,
                    summary_text=summary_text,
                    file_type=document.file_type,
                    key_terms=[]
                )

            # 2. 格式化提示詞
            system_prompt, user_prompt = prompt_manager_simplified.format_prompt(
                prompt_template,
                text_content=document.extracted_text[:4000] # 限制輸入長度以符合模型限制
            )
            
            # 3. 調用AI進行結構化分析 (假設 unified_ai_service_simplified 可以處理 system_prompt 和 user_prompt)
            # 注意：這裡的 unified_ai_service_simplified.analyze_text 可能需要調整
            # 如果它不接受 system_prompt, user_prompt 分開傳遞, 
            # 可能需要一個新的方法如 analyze_with_prompts(system_prompt, user_prompt, db)
            # 或者 analyze_text 內部會處理 prompt_template
            
            # 為了繼續，我們假設 analyze_text 可以通過某種方式利用 system 和 user prompt
            # 或我們直接傳遞拼接後的內容，由AI自行解析。
            # 但更理想的是 analyze_text 支持結構化提示詞。
            # 暫時使用拼接方式，並期望AI能正確處理JSON輸出。
            
            # 修正：unified_ai_service_simplified 的 analyze_text 接受單一 text_content
            # 它內部會選擇合適的 prompt (如果設計如此) 或使用通用 prompt
            # 為了實現結構化輸出，我們應該讓 analyze_text 能夠接受更明確的指示
            # 或者，我們需要一個更專門的方法。
            # 由於 prompt_manager 已定義了完整的 system 和 user prompts，
            # 我們將直接使用它們調用AI，期望它遵循指示輸出JSON。

            ai_response = await unified_ai_service_simplified.analyze_with_prompts_and_parse_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                db=db,
                output_model_schema=None # 讓AI根據Prompt的JSON結構輸出
            )

            if not ai_response.success or not ai_response.content:
                logger.warning(f"AI結構化摘要生成失敗: {ai_response.error_message}，使用fallback策略。文檔 ID: {document.id}")
                summary_text = self._generate_fallback_summary(document)
                return SemanticSummary(
                    document_id=document.id,
                    summary_text=summary_text,
                    file_type=document.file_type,
                    key_terms=[]
                )
            
            # 4. 解析AI回應的JSON
            try:
                # ai_response.content 應該已經是解析後的字典 (如果 analyze_with_prompts_and_parse_json 按預期工作)
                parsed_json = ai_response.content 
                
                # 5. 從JSON中提取所需資訊
                key_info = parsed_json.get("key_information", {})
                summary_text = key_info.get("content_summary", "")
                key_terms = key_info.get("semantic_tags", [])

                if isinstance(key_terms, str): # AI有時可能返回逗號分隔的字串
                    key_terms = [term.strip() for term in key_terms.split(',') if term.strip()]

                if not summary_text or len(summary_text.strip()) < 10: # 摘要至少需要一些內容
                    logger.warning(f"AI生成的結構化摘要過短或缺失，使用fallback策略。文檔 ID: {document.id}")
                    summary_text = self._generate_fallback_summary(document)
                    key_terms = [] # Fallback時清空AI生成的標籤

                semantic_summary = SemanticSummary(
                    document_id=document.id,
                    summary_text=summary_text,
                    file_type=document.file_type, # 保留原始文件類型
                    key_terms=key_terms,
                    # 可以考慮在這裡加入更多來自 key_information 的欄位，如果 SemanticSummary 模型支持
                    full_ai_analysis=parsed_json # 存儲完整的分析結果
                )
                
                logger.info(f"成功為文檔 {document.id} 生成結構化語義摘要，長度: {len(summary_text)}")
                return semantic_summary
                
            except (json.JSONDecodeError, AttributeError, KeyError, TypeError) as e:
                logger.error(f"解析AI結構化摘要回應失敗: {e}。AI原始回應片段: {str(ai_response.content)[:500]}... 使用fallback策略。文檔 ID: {document.id}", exc_info=True)
                summary_text = self._generate_fallback_summary(document)
                return SemanticSummary(
                    document_id=document.id,
                    summary_text=summary_text,
                    file_type=document.file_type,
                    key_terms=[]
                )
                
        except Exception as e:
            logger.error(f"生成語義摘要 (彈性模式) 失敗: {e}，文檔 ID: {document.id}", exc_info=True)
            summary_text = self._generate_fallback_summary(document)
            return SemanticSummary(
                document_id=document.id,
                summary_text=summary_text,
                file_type=document.file_type,
                key_terms=[]
            )
    
    def _generate_fallback_summary(self, document: Document) -> str:
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
            logger.error(f"生成fallback摘要失敗: {e}")
            return f"這是一份{document.file_type or '文檔'}文件，文件名為{document.filename}。"
    
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
        doc_id_str = document.id # Assuming document.id is already a string, if not, str(document.id)
        doc_id_uuid = uuid.UUID(doc_id_str) # For crud operations

        try:
            logger.info(f"開始處理文檔 {doc_id_str} 以添加到向量資料庫")
            # 步驟1: 更新狀態為 PROCESSING
            await update_document_vector_status(db, doc_id_uuid, VectorStatus.PROCESSING)
            
            # 步驟2: 刪除舊向量 (實現覆蓋)
            # 即使是第一次向量化，這個操作也應該是安全的
            logger.info(f"為文檔 {doc_id_str} 嘗試刪除舊向量...")
            # delete_by_document_id 是同步的，不需要 await
            vector_db_service.delete_by_document_id(doc_id_str) 
            logger.info(f"為文檔 {doc_id_str} 刪除舊向量完成 (如果存在)。")

            # 步驟3: 生成語義摘要
            semantic_summary = await self.generate_semantic_summary(db, document)
            if not semantic_summary:
                logger.error(f"無法為文檔 {doc_id_str} 生成語義摘要")
                await update_document_vector_status(db, doc_id_uuid, VectorStatus.FAILED, "語義摘要生成失敗")
                return False
            
            # 步驟4: 向量化摘要文本
            text_parts = []
            if semantic_summary.summary_text and semantic_summary.summary_text.strip():
                text_parts.append(semantic_summary.summary_text.strip())

            if semantic_summary.key_terms: 
                valid_key_terms = [
                    str(term).strip() for term in semantic_summary.key_terms 
                    if term and str(term).strip()
                ]
                if valid_key_terms:
                    text_parts.append("相關標籤：" + "，".join(valid_key_terms))
            
            if semantic_summary.full_ai_analysis and isinstance(semantic_summary.full_ai_analysis, dict):
                key_info = semantic_summary.full_ai_analysis.get("key_information")
                if isinstance(key_info, dict):
                    searchable_keywords = key_info.get("searchable_keywords")
                    if isinstance(searchable_keywords, list):
                        valid_keywords = [
                            str(kw).strip() for kw in searchable_keywords 
                            if kw and str(kw).strip()
                        ]
                        if valid_keywords:
                            text_parts.append("搜索關鍵詞：" + "，".join(valid_keywords))
                    
                    knowledge_domains = key_info.get("knowledge_domains")
                    if isinstance(knowledge_domains, list):
                        valid_domains = [
                            str(kd).strip() for kd in knowledge_domains
                            if kd and str(kd).strip()
                        ]
                        if valid_domains:
                            text_parts.append("知識領域：" + "，".join(valid_domains))

            text_to_embed = "\n".join(text_parts)
            
            if not text_to_embed.strip():
                logger.warning(f"文檔 {doc_id_str} 的組合向量化文本為空，將僅使用摘要或文件名作為後備。")
                if semantic_summary.summary_text and semantic_summary.summary_text.strip():
                    text_to_embed = semantic_summary.summary_text.strip()
                elif document.filename:
                     text_to_embed = f"文件名：{document.filename}"
                else:
                    text_to_embed = "文檔內容無法確定" 
                    logger.error(f"文檔 {doc_id_str} 無法確定用於向量化的文本。")

            embedding_vector = embedding_service.encode_text(text_to_embed)
            
            # 步驟5: 創建向量記錄
            vector_record = VectorRecord(
                document_id=doc_id_str, # Use string ID for VectorRecord
                embedding_vector=embedding_vector,
                chunk_text=text_to_embed, 
                embedding_model=embedding_service.model_name,
                # status field in VectorRecord might be for internal Chroma state, not our Document.vector_status
                metadata={"file_type": document.file_type or ""}
            )
            
            # 步驟6: 存儲到向量資料庫
            success = vector_db_service.insert_vectors([vector_record])
            
            if success:
                logger.info(f"文檔 {doc_id_str} 成功存儲到向量資料庫")
                await self._save_semantic_summary_to_db(db, semantic_summary) # 保存摘要
                await update_document_vector_status(db, doc_id_uuid, VectorStatus.VECTORIZED)
                return True
            else:
                logger.error(f"文檔 {doc_id_str} 存儲到向量資料庫失敗")
                await update_document_vector_status(db, doc_id_uuid, VectorStatus.FAILED, "向量存儲失敗")
                return False
                
        except Exception as e:
            logger.error(f"處理文檔 {doc_id_str} 到向量資料庫時發生意外錯誤: {e}", exc_info=True)
            await update_document_vector_status(db, doc_id_uuid, VectorStatus.FAILED, f"處理時發生意外錯誤: {str(e)}")
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
        logger.info(f"開始批量處理 {len(document_ids)} 個文檔到向量資料庫")
        from app.crud.crud_documents import get_document_by_id # 延遲導入

        results = {
            "processed_successfully": [],
            "failed_to_process": [],
            "not_found": []
        }

        for doc_id_str in document_ids:
            try:
                doc_uuid = uuid.UUID(doc_id_str)
                document = await get_document_by_id(db, doc_uuid)
                if not document:
                    logger.warning(f"批量處理：未找到文檔 {doc_id_str}")
                    results["not_found"].append(doc_id_str)
                    continue
                
                # 調用單個文檔處理函數，它內部會處理狀態更新和覆蓋邏輯
                success = await self.process_document_for_vector_db(db, document)
                if success:
                    results["processed_successfully"].append(doc_id_str)
                else:
                    results["failed_to_process"].append(doc_id_str)
            except ValueError:
                 logger.error(f"批量處理：無效的文檔ID格式 {doc_id_str}")
                 results["failed_to_process"].append({"id": doc_id_str, "error": "無效的ID格式"})
            except Exception as e:
                logger.error(f"批量處理文檔 {doc_id_str} 時發生錯誤: {e}", exc_info=True)
                results["failed_to_process"].append({"id": doc_id_str, "error": str(e)})
                # 確保即使發生未知錯誤，文檔狀態也能被更新為 FAILED (如果 process_document_for_vector_db 內部未處理)
                try:
                    doc_uuid_for_fail_update = uuid.UUID(doc_id_str)
                    await update_document_vector_status(db, doc_uuid_for_fail_update, VectorStatus.FAILED, f"批量處理時發生錯誤: {str(e)}")
                except Exception as update_err:
                    logger.error(f"嘗試更新失敗狀態時再次發生錯誤，文檔ID {doc_id_str}: {update_err}")

        logger.info(f"批量處理完成。成功: {len(results['processed_successfully'])}, 失敗: {len(results['failed_to_process'])}, 未找到: {len(results['not_found'])}")
        return results

# 全局語義摘要服務實例
semantic_summary_service = SemanticSummaryService() 