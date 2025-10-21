"""
文檔詳細查詢處理器

處理對已知文檔的詳細數據查詢，使用 MongoDB 詳細查詢功能提取精確信息
"""
import time
import logging
import json
import uuid
from typing import Optional, List, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.logging_utils import AppLogger, log_event, LogLevel
from app.models.vector_models import (
    AIQARequest,
    AIQAResponse,
    QueryRewriteResult
)
from app.models.question_models import QuestionClassification
from app.models.ai_models_simplified import AIMongoDBQueryDetailOutput
from app.services.ai.unified_ai_service_simplified import unified_ai_service_simplified
from app.services.qa_workflow.conversation_helper import conversation_helper
from app.crud.crud_documents import get_documents_by_ids

logger = AppLogger(__name__, level=logging.DEBUG).get_logger()


def remove_projection_path_collisions(projection: dict) -> dict:
    """移除 MongoDB projection 中的父子欄位衝突"""
    if not projection or not isinstance(projection, dict):
        return projection
    keys = list(projection.keys())
    keys_to_remove = set()
    for k in keys:
        for other in keys:
            if k == other:
                continue
            if k.startswith(other + "."):
                keys_to_remove.add(other)
            elif other.startswith(k + "."):
                keys_to_remove.add(k)
    for k in keys_to_remove:
        projection.pop(k, None)
    return projection


class DocumentDetailQueryHandler:
    """文檔詳細查詢處理器 - 對已知文檔執行 MongoDB 精確查詢"""
    
    async def handle(
        self,
        request: AIQARequest,
        classification: QuestionClassification,
        context: Optional[dict],
        db: Optional[AsyncIOMotorDatabase] = None,
        user_id: Optional[str] = None,
        request_id: Optional[str] = None
    ) -> AIQAResponse:
        """
        處理文檔詳細查詢請求
        
        流程:
        1. 從對話上下文獲取已知的文檔ID
        2. 請求用戶批准詳細查詢
        3. 使用 AI 生成 MongoDB 查詢
        4. 執行查詢獲取精確數據
        5. 生成答案
        """
        start_time = time.time()
        api_calls = 0
        
        logger.info(f"處理文檔詳細查詢: {request.question}")
        
        # 檢查工作流操作
        workflow_action = getattr(request, 'workflow_action', None)
        
        # 步驟1: 獲取已知的文檔ID（從對話上下文或緩存）
        cached_doc_ids = []
        if context and context.get('cached_document_ids'):
            cached_doc_ids = context['cached_document_ids']
            logger.info(f"從上下文獲取 {len(cached_doc_ids)} 個已知文檔")
        
        if not cached_doc_ids:
            # 沒有已知文檔，退化為 document_search
            logger.warning("沒有找到已知文檔，轉為文檔搜索")
            from app.services.intent_handlers.document_search_handler import document_search_handler
            return await document_search_handler.handle(
                request, classification, context, db, user_id, request_id
            )
        
        # 如果用戶選擇跳過，使用摘要回答
        if workflow_action == 'skip_detail_query':
            logger.info("用戶跳過詳細查詢，使用文檔摘要回答")
            # 轉發給 simple_factual_handler 使用摘要
            from app.services.intent_handlers.simple_factual_handler import simple_factual_handler
            return await simple_factual_handler.handle(
                request, classification, db, user_id, request_id
            )
        
        # 步驟2: 如果用戶未批准，獲取目標文檔然後請求批准
        if workflow_action != 'approve_detail_query' and not getattr(request, 'skip_classification', False):
            logger.info(f"獲取目標文檔（共 {len(cached_doc_ids)} 個候選）")
            
            # 優先從分類結果獲取目標文檔 ID（分類器已經識別過了）
            target_doc_ids = []
            if classification.target_document_ids:
                target_doc_ids = classification.target_document_ids
                logger.info(f"✅ 從分類器直接獲取目標文檔: {len(target_doc_ids)} 個，跳過重複識別")
                if classification.target_document_reasoning:
                    logger.info(f"分類器推理: {classification.target_document_reasoning}")
            else:
                # 回退：如果分類器沒有識別，使用所有緩存文檔（最多3個）
                logger.warning("⚠️ 分類器未提供目標文檔，使用前3個緩存文檔作為回退")
                target_doc_ids = cached_doc_ids[:3]
            
            processing_time = time.time() - start_time
            
            # 獲取目標文檔名稱（用於顯示）
            doc_names = []
            try:
                documents = await get_documents_by_ids(db, target_doc_ids)
                doc_names = [doc.filename for doc in documents if hasattr(doc, 'filename')]
            except Exception as e:
                logger.warning(f"獲取文檔名稱失敗: {e}")
            
            return AIQAResponse(
                answer="",
                source_documents=[],
                confidence_score=0.0,
                tokens_used=0,
                processing_time=processing_time,
                query_rewrite_result=QueryRewriteResult(
                    original_query=request.question,
                    rewritten_queries=[request.question],
                    extracted_parameters={},
                    intent_analysis=classification.reasoning
                ),
                semantic_search_contexts=[],
                session_id=request.session_id,
                classification=classification,
                workflow_state={
                    "current_step": "awaiting_detail_query_approval",
                    "strategy_used": "document_detail_query",
                    "api_calls": 0,
                    "target_documents": target_doc_ids,  # 只顯示識別出的目標文檔
                    "document_names": doc_names,
                    "query_type": "詳細數據查詢",
                    "estimated_time": "2-4秒"
                },
                next_action="approve_detail_query",
                pending_approval="detail_query"
            )
        
        # 用戶已批准，執行詳細查詢
        logger.info("用戶已批准詳細查詢，開始執行")
        
        # 步驟3: 獲取目標文檔ID（三種來源，優先級遞減）
        target_doc_ids = []
        
        # 優先級1: 從分類結果獲取（最準確，分類時已識別）
        if classification.target_document_ids:
            target_doc_ids = classification.target_document_ids
            logger.info(f"✅ 從分類器獲取目標文檔: {len(target_doc_ids)} 個（避免重複識別）")
        
        # 優先級2: 從請求參數獲取（前端可能傳回）
        elif hasattr(request, 'document_ids') and request.document_ids:
            target_doc_ids = request.document_ids
            logger.info(f"📥 從請求參數獲取目標文檔: {len(target_doc_ids)} 個")
        
        # 優先級3: 回退方案 - 使用前3個緩存文檔
        else:
            logger.warning("⚠️ 未找到目標文檔ID，使用前3個緩存文檔作為回退")
            target_doc_ids = cached_doc_ids[:3]
        
        # 步驟4: 準備文檔 Schema 信息
        document_schema_info = {
            "description": "MongoDB 文檔 Schema",
            "fields": {
                "filename": "文件名",
                "extracted_text": "文本內容",
                "analysis.ai_analysis_output.key_information": "結構化信息（金額、日期、人名等）",
                "analysis.ai_analysis_output.key_information.dynamic_fields": "動態欄位"
            }
        }
        
        # 步驟5: 對選定的文檔執行 MongoDB 詳細查詢
        all_detailed_data = []
        document_reference_map = {}  # 用於保存文檔ID到參考編號的映射
        
        # 構建文檔ID到參考編號的映射（從緩存文檔列表）
        for idx, doc_id in enumerate(cached_doc_ids, 1):
            document_reference_map[doc_id] = idx
        
        documents = await get_documents_by_ids(db, target_doc_ids)
        
        # 過濾權限
        if user_id:
            from uuid import UUID
            user_uuid = UUID(str(user_id)) if not isinstance(user_id, UUID) else user_id
            documents = [doc for doc in documents if hasattr(doc, 'owner_id') and doc.owner_id == user_uuid]
        
        for doc in documents:
            logger.info(f"對文檔 {doc.filename} 執行詳細查詢")
            
            ai_query_response = await unified_ai_service_simplified.generate_mongodb_detail_query(
                user_question=request.question,
                document_id=str(doc.id),
                document_schema_info=document_schema_info,
                db=db,
                model_preference=request.model_preference,
                user_id=user_id,
                session_id=request.session_id
            )
            api_calls += 1
            
            if ai_query_response.success and isinstance(ai_query_response.output_data, AIMongoDBQueryDetailOutput):
                query_components = ai_query_response.output_data
                
                mongo_filter = {"_id": doc.id}
                mongo_projection = query_components.projection
                
                if query_components.sub_filter:
                    mongo_filter.update(query_components.sub_filter)
                
                if mongo_projection or query_components.sub_filter:
                    safe_projection = remove_projection_path_collisions(mongo_projection) if mongo_projection else None
                    fetched_data = await db.documents.find_one(mongo_filter, projection=safe_projection)
                    
                    if fetched_data:
                        # 資料清理
                        def sanitize(data: Any) -> Any:
                            if isinstance(data, dict):
                                return {k: sanitize(v) for k, v in data.items()}
                            if isinstance(data, list):
                                return [sanitize(i) for i in data]
                            if isinstance(data, uuid.UUID):
                                return str(data)
                            return data
                        
                        sanitized_data = sanitize(fetched_data)
                        
                        # 添加元數據：原始的參考編號（文檔幾）
                        doc_id_str = str(doc.id)
                        if doc_id_str in document_reference_map:
                            sanitized_data['_reference_number'] = document_reference_map[doc_id_str]
                        
                        all_detailed_data.append(sanitized_data)
                        logger.info(f"成功獲取文檔 {doc.filename} 的詳細數據")
        
        # 步驟5: 使用詳細數據生成答案
        answer = await self._generate_answer_from_details(
            question=request.question,
            detailed_data=all_detailed_data,
            classification=classification,
            db=db,
            user_id=user_id,
            conversation_id=request.conversation_id,
            context=context
        )
        api_calls += 1
        
        processing_time = time.time() - start_time
        
        # 保存對話
        if db is not None:
            await conversation_helper.save_qa_to_conversation(
                db=db,
                conversation_id=request.conversation_id,
                user_id=str(user_id) if user_id else None,
                question=request.question,
                answer=answer,
                tokens_used=api_calls * 150,
                source_documents=target_doc_ids
            )
        
        logger.info(f"詳細查詢完成，耗時: {processing_time:.2f}秒, API調用: {api_calls}次")
        
        return AIQAResponse(
            answer=answer,
            source_documents=target_doc_ids,
            confidence_score=0.90,
            tokens_used=api_calls * 150,
            processing_time=processing_time,
            query_rewrite_result=QueryRewriteResult(
                original_query=request.question,
                rewritten_queries=[request.question],
                extracted_parameters={
                    "detail_query_count": len(all_detailed_data),
                    "target_document_count": len(target_doc_ids)
                },
                intent_analysis=classification.reasoning
            ),
            semantic_search_contexts=[],
            session_id=request.session_id,
            classification=classification,
            workflow_state={
                "current_step": "completed",
                "strategy_used": "document_detail_query",
                "api_calls": api_calls,
                "documents_queried": len(all_detailed_data),
                "target_documents": target_doc_ids
            },
            detailed_document_data_from_ai_query=all_detailed_data
        )
    
    async def _generate_answer_from_details(
        self,
        question: str,
        detailed_data: List[Dict],
        classification: QuestionClassification,
        db: Optional[AsyncIOMotorDatabase],
        user_id: Optional[str],
        conversation_id: Optional[str],
        context: Optional[dict]
    ) -> str:
        """使用詳細數據生成答案"""
        
        # 載入對話歷史
        from app.services.qa_workflow.unified_context_helper import unified_context_helper
        
        conversation_history_text = await unified_context_helper.load_and_format_conversation_history(
            db=db,
            conversation_id=conversation_id,
            user_id=user_id,
            limit=5,
            max_content_length=2000
        )
        
        # 構建上下文
        context_parts = []
        if conversation_history_text:
            context_parts.append(conversation_history_text)
        
        # 添加詳細數據
        for i, data in enumerate(detailed_data, 1):
            data_str = json.dumps(data, ensure_ascii=False, indent=2)
            
            # 獲取文檔的原始參考編號（文檔幾）
            filename = data.get('filename', '未知文件')
            reference_number = data.get('_reference_number', i)  # 如果有原始編號就用，沒有就用循環編號
            
            # 構建清晰的標題，包含參考編號和文件名
            doc_label = f"文檔{reference_number} ({filename})"
            context_parts.append(f"=== {doc_label} 的詳細數據 ===\n{data_str}\n")
            
            logger.debug(f"添加文檔上下文: {doc_label}")
        
        # 調用 AI 生成答案
        try:
            ai_response = await unified_ai_service_simplified.generate_answer(
                user_question=question,
                intent_analysis=classification.reasoning,
                document_context=context_parts,
                db=db,
                user_id=user_id
            )
            
            if ai_response.success and ai_response.output_data:
                return ai_response.output_data.answer_text
            else:
                return "抱歉，無法從文檔詳細數據中生成答案。"
        except Exception as e:
            logger.error(f"生成答案失敗: {e}", exc_info=True)
            return "抱歉，生成答案時發生錯誤。"


# 創建全局實例
document_detail_query_handler = DocumentDetailQueryHandler()

