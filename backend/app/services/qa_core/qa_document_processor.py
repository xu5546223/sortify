"""
QA文檔處理器

處理文檔選擇、詳細查詢等功能
保留所有原有的 AI 文檔選擇和 MongoDB 查詢功能
"""
import logging
import uuid
from typing import List, Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.logging_utils import AppLogger, log_event, LogLevel
from app.models.vector_models import SemanticContextDocument
from app.models.ai_models_simplified import AIDocumentSelectionOutput
from app.services.ai.unified_ai_service_simplified import unified_ai_service_simplified
from app.crud.crud_documents import get_documents_by_ids

logger = AppLogger(__name__, level=logging.DEBUG).get_logger()


def remove_projection_path_collisions(projection: dict) -> dict:
    """
    移除 MongoDB projection 中的父子欄位衝突,只保留最底層欄位
    
    保留原有邏輯,確保 MongoDB 查詢正常工作
    """
    if not projection or not isinstance(projection, dict):
        return projection
    
    keys = list(projection.keys())
    keys_to_remove = set()
    
    for k in keys:
        for other in keys:
            if k == other:
                continue
            # k 是 other 的子欄位,則移除父欄位 other
            if k.startswith(other + "."):
                keys_to_remove.add(other)
            # other 是 k 的子欄位,則移除父欄位 k
            elif other.startswith(k + "."):
                keys_to_remove.add(k)
    
    for k in keys_to_remove:
        projection.pop(k, None)
    
    return projection


class QADocumentProcessor:
    """QA文檔處理器 - 保留所有原有功能"""
    
    async def select_documents_for_detailed_query(
        self,
        db: AsyncIOMotorDatabase,
        user_question: str,
        semantic_contexts: List[SemanticContextDocument],
        user_id: Optional[str],
        request_id: Optional[str],
        ai_selection_limit: int = 3,
        similarity_threshold: float = 0.3
    ) -> List[str]:
        """
        使用 AI 從候選文件中智能選擇最相關的文件進行詳細查詢
        
        保留原有的 AI 文檔選擇邏輯
        """
        if not semantic_contexts:
            return []
        
        # 去重 - 每個文檔只保留最高分
        filtered_contexts = {}
        for ctx in semantic_contexts:
            if ctx.document_id not in filtered_contexts or \
               ctx.similarity_score > filtered_contexts[ctx.document_id].similarity_score:
                filtered_contexts[ctx.document_id] = ctx
        
        # 按分數排序
        unique_contexts = sorted(
            filtered_contexts.values(),
            key=lambda x: x.similarity_score,
            reverse=True
        )
        
        # 動態決定候選數量
        max_candidates = min(ai_selection_limit * 2, len(unique_contexts))
        candidates_for_ai = unique_contexts[:max_candidates]
        
        if len(candidates_for_ai) < 2:
            logger.info(f"候選文件數量不足({len(candidates_for_ai)}),直接返回所有候選")
            return [ctx.document_id for ctx in candidates_for_ai]
        
        # 準備候選文件資料給 AI 分析
        candidate_docs_for_ai = [
            {
                "document_id": ctx.document_id,
                "summary": ctx.summary_or_chunk_text,
                "similarity_score": ctx.similarity_score
            }
            for ctx in candidates_for_ai
        ]
        
        await log_event(
            db=db,
            level=LogLevel.INFO,
            message=f"請AI從 {len(candidate_docs_for_ai)} 個候選文件中選擇最相關的(限制:{ai_selection_limit}個)",
            source="service.qa_document_processor.select_documents",
            user_id=user_id,
            request_id=request_id,
            details={
                "candidates": [
                    {"id": doc["document_id"], "score": doc["similarity_score"]}
                    for doc in candidate_docs_for_ai
                ],
                "user_selection_limit": ai_selection_limit
            }
        )
        
        # 調用統一 AI 服務進行文檔選擇
        selection_response = await unified_ai_service_simplified.select_documents_for_detailed_query(
            user_question=user_question,
            candidate_documents=candidate_docs_for_ai,
            db=db,
            user_id=user_id,
            session_id=request_id,
            max_selections=ai_selection_limit
        )
        
        if selection_response.success and isinstance(selection_response.output_data, AIDocumentSelectionOutput):
            selected_ids = selection_response.output_data.selected_document_ids
            reasoning = selection_response.output_data.reasoning
            
            # 驗證選擇的文件ID是否有效
            valid_candidate_ids = {doc["document_id"] for doc in candidate_docs_for_ai}
            validated_selected_ids = [
                doc_id for doc_id in selected_ids
                if doc_id in valid_candidate_ids
            ]
            
            if len(validated_selected_ids) != len(selected_ids):
                dropped_ids = set(selected_ids) - set(validated_selected_ids)
                logger.warning(f"AI選擇了一些無效的文件ID,已過濾: {dropped_ids}")
            
            await log_event(
                db=db,
                level=LogLevel.INFO,
                message=f"AI智能選擇了 {len(validated_selected_ids)} 個文件",
                source="service.qa_document_processor.select_documents_success",
                user_id=user_id,
                request_id=request_id,
                details={
                    "selected_ids": validated_selected_ids,
                    "reasoning": reasoning,
                    "original_candidates": len(semantic_contexts),
                    "after_dedup": len(candidates_for_ai),
                    "final_selected": len(validated_selected_ids)
                }
            )
            
            return validated_selected_ids
        
        else:
            # AI 選擇失敗,使用回退策略
            await log_event(
                db=db,
                level=LogLevel.WARNING,
                message=f"AI文件選擇失敗,回退:選擇前{min(ai_selection_limit, len(candidates_for_ai))}個",
                source="service.qa_document_processor.select_documents_fallback",
                user_id=user_id,
                request_id=request_id,
                details={
                    "error": selection_response.error_message,
                    "fallback_count": min(ai_selection_limit, len(candidates_for_ai))
                }
            )
            
            fallback_count = min(ai_selection_limit, len(candidates_for_ai))
            return [ctx.document_id for ctx in candidates_for_ai[:fallback_count]]
    
    async def query_document_details(
        self,
        db: AsyncIOMotorDatabase,
        document_id: str,
        user_question: str,
        document_schema_info: Dict[str, Any],
        user_id: Optional[str] = None,
        model_preference: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        對單個文檔執行 AI 生成的詳細查詢
        
        保留原有的 MongoDB 詳細查詢功能
        """
        try:
            # 獲取文檔對象
            documents = await get_documents_by_ids(db, [document_id])
            if not documents:
                logger.warning(f"文檔 {document_id} 不存在")
                return None
            
            target_document = documents[0]
            
            # 使用 AI 生成 MongoDB 查詢
            ai_query_response = await unified_ai_service_simplified.generate_mongodb_detail_query(
                user_question=user_question,
                document_id=str(target_document.id),
                document_schema_info=document_schema_info,
                db=db,
                model_preference=model_preference,
                user_id=user_id
            )
            
            if not ai_query_response.success or not ai_query_response.output_data:
                logger.error(f"AI生成MongoDB查詢失敗: {ai_query_response.error_message}")
                return await self._fallback_basic_query(db, target_document)
            
            from app.models.ai_models_simplified import AIMongoDBQueryDetailOutput
            if not isinstance(ai_query_response.output_data, AIMongoDBQueryDetailOutput):
                return await self._fallback_basic_query(db, target_document)
            
            query_components = ai_query_response.output_data
            
            # 構建 MongoDB 查詢
            mongo_filter = {"_id": target_document.id}
            mongo_projection = query_components.projection
            
            if query_components.sub_filter:
                mongo_filter.update(query_components.sub_filter)
            
            if mongo_projection or query_components.sub_filter:
                # 執行 AI 生成的詳細查詢
                logger.debug(f"執行AI查詢 - Filter: {mongo_filter}, Projection: {mongo_projection}")
                safe_projection = remove_projection_path_collisions(mongo_projection) if mongo_projection else None
                fetched_data = await db.documents.find_one(mongo_filter, projection=safe_projection)
                
                if fetched_data:
                    # 清理數據
                    def sanitize(data: Any) -> Any:
                        if isinstance(data, dict):
                            return {k: sanitize(v) for k, v in data.items()}
                        if isinstance(data, list):
                            return [sanitize(i) for i in data]
                        if isinstance(data, uuid.UUID):
                            return str(data)
                        return data
                    
                    logger.info(f"成功獲取文檔 {document_id} 的詳細資料")
                    return sanitize(fetched_data)
                else:
                    # AI 查詢沒有返回結果,使用回退查詢
                    logger.warning(f"文檔 {document_id} 的AI查詢無結果,使用回退查詢")
                    return await self._fallback_basic_query(db, target_document)
            else:
                return await self._fallback_basic_query(db, target_document)
                
        except Exception as e:
            logger.error(f"查詢文檔詳細資料失敗: {e}", exc_info=True)
            return None
    
    async def _fallback_basic_query(self, db: AsyncIOMotorDatabase, document) -> Optional[Dict[str, Any]]:
        """回退到基本查詢"""
        try:
            fallback_projection = {
                "_id": 1,
                "filename": 1,
                "extracted_text": 1,
                "analysis.ai_analysis_output.key_information.content_summary": 1,
                "analysis.ai_analysis_output.key_information.semantic_tags": 1,
                "analysis.ai_analysis_output.key_information.key_concepts": 1
            }
            
            safe_projection = remove_projection_path_collisions(fallback_projection)
            fetched_data = await db.documents.find_one(
                {"_id": document.id},
                projection=safe_projection
            )
            
            if fetched_data:
                def sanitize(data: Any) -> Any:
                    if isinstance(data, dict):
                        return {k: sanitize(v) for k, v in data.items()}
                    if isinstance(data, list):
                        return [sanitize(i) for i in data]
                    if isinstance(data, uuid.UUID):
                        return str(data)
                    return data
                
                logger.info(f"回退查詢成功獲取文檔 {document.id} 的基本資料")
                return sanitize(fetched_data)
            
            return None
            
        except Exception as e:
            logger.error(f"回退查詢也失敗: {e}")
            return None


# 創建全局實例
qa_document_processor = QADocumentProcessor()

