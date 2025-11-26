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


def sanitize_for_json(obj: Any) -> Any:
    """清理數據中的不可 JSON 序列化的對象（UUID、datetime 等）"""
    from datetime import datetime
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_for_json(item) for item in obj]
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj


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
        
        # 步驟1: 獲取已知的文檔ID（優先使用優先文檔）
        # 優先使用統一上下文管理器提供的優先文檔
        priority_doc_ids = context.get('priority_document_ids', []) if context else []
        cached_doc_ids = context.get('cached_document_ids', []) if context else []
        
        # 優先文檔優先級更高（基於相關性和訪問頻率）
        available_doc_ids = priority_doc_ids if priority_doc_ids else cached_doc_ids
        
        if priority_doc_ids:
            logger.info(f"🎯 使用優先文檔: {len(priority_doc_ids)} 個（來自文檔池）")
        elif cached_doc_ids:
            logger.info(f"從上下文獲取 {len(cached_doc_ids)} 個已知文檔（舊方式）")
        
        if not available_doc_ids:
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
                request, classification, None, db, user_id, request_id
            )
        
        # 步驟2: 如果用戶未批准，獲取目標文檔然後請求批准
        if workflow_action != 'approve_detail_query' and not getattr(request, 'skip_classification', False):
            logger.info(f"獲取目標文檔（共 {len(available_doc_ids)} 個候選）")
            
            # 優先從分類結果獲取目標文檔 ID（分類器已經識別過了）
            target_doc_ids = []
            if classification.target_document_ids:
                target_doc_ids = classification.target_document_ids
                logger.info(f"✅ 從分類器直接獲取目標文檔: {len(target_doc_ids)} 個，跳過重複識別")
                if classification.target_document_reasoning:
                    logger.info(f"分類器推理: {classification.target_document_reasoning}")
            else:
                # 回退：如果分類器沒有識別，優先使用優先文檔（最多3個）
                if priority_doc_ids:
                    logger.info("✅ 使用優先文檔作為目標（最相關的文檔）")
                    target_doc_ids = priority_doc_ids[:3]
                else:
                    logger.warning("⚠️ 分類器未提供目標文檔，使用前3個緩存文檔作為回退")
                    target_doc_ids = available_doc_ids[:3]
            
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
        
        # 優先級3: 回退方案 - 使用前3個可用文檔（優先文檔或緩存文檔）
        else:
            logger.warning("⚠️ 未找到目標文檔ID，使用前3個可用文檔作為回退")
            target_doc_ids = available_doc_ids[:3]
        
        # 步驟4: 使用固定的 projection 直接查詢文檔（簡化策略）
        logger.info(f"📋 準備查詢 {len(target_doc_ids)} 個文檔的完整文本內容...")

        # ✅ 簡化方案：固定查詢欄位，不需要 AI 生成查詢
        # 只查詢必要的欄位：_id、filename、extracted_text
        fixed_projection = {
            "_id": 1,
            "filename": 1,
            "extracted_text": 1  # 完整的提取文本（適用於所有文件類型）
        }

        logger.info(f"✅ 使用固定 projection 查詢策略（extracted_text）")

        # 步驟5: 對選定的文檔執行 MongoDB 詳細查詢
        all_detailed_data = []
        document_reference_map = {}  # 用於保存文檔ID到參考編號的映射
        
        # 構建文檔ID到參考編號的映射（從可用文檔列表，優先使用優先文檔）
        # 確保 key 統一為字符串格式，以便後續查找
        for idx, doc_id in enumerate(available_doc_ids, 1):
            document_reference_map[str(doc_id)] = idx
        
        documents = await get_documents_by_ids(db, target_doc_ids)

        # 過濾權限
        if user_id:
            from uuid import UUID
            user_uuid = UUID(str(user_id)) if not isinstance(user_id, UUID) else user_id
            documents = [doc for doc in documents if hasattr(doc, 'owner_id') and doc.owner_id == user_uuid]

        # ✅ 直接查詢文檔，不需要 AI 生成查詢（簡化且可靠）
        for doc in documents:
            logger.info(f"對文檔 {doc.filename} 執行詳細查詢（fixed projection）")

            try:
                # 直接使用固定 projection 查詢
                fetched_data = await db.documents.find_one(
                    {"_id": doc.id},
                    projection=fixed_projection
                )

                if fetched_data:
                    # 資料清理
                    sanitized_data = sanitize_for_json(fetched_data)

                    # 添加元數據：原始的參考編號（文檔幾）
                    doc_id_str = str(doc.id)
                    if doc_id_str in document_reference_map:
                        sanitized_data['_reference_number'] = document_reference_map[doc_id_str]

                    all_detailed_data.append(sanitized_data)
                    logger.info(f"✅ 成功獲取文檔 {doc.filename} 的詳細數據（{len(fetched_data.get('extracted_text', ''))} 字符）")
                else:
                    logger.warning(f"⚠️ 文檔 {doc.filename} 查詢結果為空")

            except Exception as e:
                logger.error(f"❌ 查詢文檔 {doc.filename} 失敗: {e}", exc_info=True)

        # 步驟6: 使用詳細數據生成答案
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
            # ⭐ 合併目標文檔 + 用戶 @ 的文件（保持順序）
            # all_detailed_data 的順序就是 AI 看到的順序
            all_doc_ids_ordered = []
            for data in all_detailed_data:
                doc_id = str(data.get('_id', ''))
                if doc_id and doc_id not in all_doc_ids_ordered:
                    all_doc_ids_ordered.append(doc_id)
            
            # 添加用戶 @ 的文件（如果不在列表中）
            if request.document_ids:
                for doc_id in request.document_ids:
                    if doc_id not in all_doc_ids_ordered:
                        all_doc_ids_ordered.append(doc_id)
            
            await conversation_helper.save_qa_to_conversation(
                db=db,
                conversation_id=request.conversation_id,
                user_id=str(user_id) if user_id else None,
                question=request.question,
                answer=answer,
                tokens_used=api_calls * 150,
                source_documents=all_doc_ids_ordered  # ⭐ 使用有序列表
            )
        
        logger.info(f"詳細查詢完成，耗時: {processing_time:.2f}秒, API調用: {api_calls}次")
        
        # 構建包含詳細數據的 semantic_search_contexts
        from app.models.vector_models import SemanticContextDocument
        semantic_contexts = []
        for data in all_detailed_data:
            # 提取文檔信息
            doc_filename = data.get('filename', '未知文檔')
            reference_num = data.get('_reference_number', 0)
            
            # 創建一個包含詳細數據的 context
            context_doc = SemanticContextDocument(
                document_id=str(data.get('_id', '')),
                summary_or_chunk_text=f"MongoDB 查詢結果：{json.dumps(data, ensure_ascii=False, indent=2)}",
                similarity_score=1.0,
                metadata={
                    'source': 'mongodb_detail_query',
                    'filename': doc_filename,
                    'reference_number': reference_num,
                    'fields_count': len(data) - 2,  # 排除 _id 和 _reference_number
                    'detailed_data': data  # 保存完整的詳細數據
                }
            )
            semantic_contexts.append(context_doc)
        
        # ⭐ 修復：source_documents 的順序必須與 AI 看到的順序一致
        # AI 看到的是 all_detailed_data 的順序（按 _reference_number 排序）
        # 從 all_detailed_data 中提取文檔 ID，保持與 AI 看到的相同順序
        source_doc_ids_in_ai_order = []
        for data in all_detailed_data:
            doc_id = str(data.get('_id', ''))
            if doc_id and doc_id not in source_doc_ids_in_ai_order:
                source_doc_ids_in_ai_order.append(doc_id)
        
        # 如果沒有詳細數據，使用 target_doc_ids 作為 fallback
        if not source_doc_ids_in_ai_order:
            source_doc_ids_in_ai_order = target_doc_ids
        
        return AIQAResponse(
            answer=answer,
            source_documents=source_doc_ids_in_ai_order,  # ⭐ 修復：使用與 AI 看到的相同順序
            confidence_score=0.90,
            tokens_used=api_calls * 150,
            processing_time=processing_time,
            query_rewrite_result=QueryRewriteResult(
                original_query=request.question,
                rewritten_queries=[request.question],
                extracted_parameters={
                    "detail_query_count": len(all_detailed_data),
                    "target_document_count": len(target_doc_ids),
                    "total_fields": sum(len(data) - 2 for data in all_detailed_data)  # 排除 _id 和 _reference_number
                },
                intent_analysis=classification.reasoning
            ),
            semantic_search_contexts=semantic_contexts,  # 包含詳細數據
            session_id=request.session_id,
            classification=classification,
            workflow_state={
                "current_step": "completed",
                "strategy_used": "document_detail_query",
                "api_calls": api_calls,
                "documents_queried": len(all_detailed_data),
                "target_documents": target_doc_ids,
                "mongodb_results": all_detailed_data  # 同時保留在 workflow_state 中
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
        """使用詳細數據生成答案（非流式）"""
        
        # 載入對話歷史
        from app.services.qa_workflow.unified_context_helper import unified_context_helper
        
        conversation_history_text = await unified_context_helper.load_and_format_conversation_history(
            db=db,
            conversation_id=conversation_id,
            user_id=user_id
        )
        
        # 構建上下文
        context_parts = []
        if conversation_history_text:
            context_parts.append(conversation_history_text)

        # 添加詳細數據（✅ 簡化方案：只使用 extracted_text）
        for i, data in enumerate(detailed_data, 1):
            filename = data.get('filename', '未知文件')
            extracted_text = data.get('extracted_text', '')

            # 容錯處理：如果沒有提取文本，記錄警告
            if not extracted_text or len(extracted_text.strip()) < 10:
                logger.warning(f"⚠️ 文檔 {filename} 沒有足夠的提取文本（長度: {len(extracted_text)}）")
                extracted_text = "[此文檔沒有可用的提取文本]"

            # 構建清晰的標題，使用循環編號（citation:i）
            doc_label = f"文檔{i}（引用編號: citation:{i}）"

            # ✅ 直接提供完整文本，不使用 JSON 格式
            context_parts.append(f"=== {doc_label}: {filename} ===\n\n{extracted_text}\n\n")

            logger.debug(f"添加文檔上下文: {doc_label}，文本長度: {len(extracted_text)} 字符")

        # 調用 AI 生成答案（使用更大的上下文限制）
        from app.core.config import settings
        try:
            ai_response = await unified_ai_service_simplified.generate_answer(
                user_question=question,
                intent_analysis=classification.reasoning,
                document_context=context_parts,
                db=db,
                user_id=user_id,
                detailed_text_max_length=settings.DETAIL_QUERY_MAX_CONTEXT_LENGTH,
                max_chars_per_doc=settings.DETAIL_QUERY_MAX_CHARS_PER_DOC
            )
            
            if ai_response.success and ai_response.output_data:
                return ai_response.output_data.answer_text
            else:
                return "抱歉，無法從文檔詳細數據中生成答案。"
        except Exception as e:
            logger.error(f"生成答案失敗: {e}", exc_info=True)
            return "抱歉，生成答案時發生錯誤。"
    
    async def generate_answer_from_details_stream(
        self,
        question: str,
        detailed_data: List[Dict],
        classification: QuestionClassification,
        db: Optional[AsyncIOMotorDatabase],
        user_id: Optional[str],
        conversation_id: Optional[str],
        context: Optional[dict]
    ):
        """使用詳細數據生成答案（流式）"""
        
        # 載入對話歷史
        from app.services.qa_workflow.unified_context_helper import unified_context_helper
        
        conversation_history_text = await unified_context_helper.load_and_format_conversation_history(
            db=db,
            conversation_id=conversation_id,
            user_id=user_id
        )
        
        # 構建上下文
        context_parts = []
        if conversation_history_text:
            context_parts.append(conversation_history_text)

        # 添加詳細數據（✅ 簡化方案：只使用 extracted_text）
        for i, data in enumerate(detailed_data, 1):
            filename = data.get('filename', '未知文件')
            extracted_text = data.get('extracted_text', '')

            # 容錯處理：如果沒有提取文本，記錄警告
            if not extracted_text or len(extracted_text.strip()) < 10:
                logger.warning(f"⚠️ 文檔 {filename} 沒有足夠的提取文本（長度: {len(extracted_text)}）")
                extracted_text = "[此文檔沒有可用的提取文本]"

            # 構建清晰的標題，使用循環編號（citation:i）
            doc_label = f"文檔{i}（引用編號: citation:{i}）"

            # ✅ 直接提供完整文本，不使用 JSON 格式
            context_parts.append(f"=== {doc_label}: {filename} ===\n\n{extracted_text}\n\n")

            logger.debug(f"添加文檔上下文: {doc_label}，文本長度: {len(extracted_text)} 字符")

        # 調用 AI 流式生成答案（使用更大的上下文限制）
        from app.core.config import settings
        try:
            from app.services.ai.unified_ai_service_stream import generate_answer_stream

            async for chunk in generate_answer_stream(
                user_question=question,
                intent_analysis=classification.reasoning,
                document_context=context_parts,
                model_preference=None,
                user_id=user_id,
                db=db,
                detailed_text_max_length=settings.DETAIL_QUERY_MAX_CONTEXT_LENGTH,
                max_chars_per_doc=settings.DETAIL_QUERY_MAX_CHARS_PER_DOC
            ):
                yield chunk
                
        except Exception as e:
            logger.error(f"流式生成答案失敗: {e}", exc_info=True)
            yield "抱歉，生成答案時發生錯誤。"


# 創建全局實例
document_detail_query_handler = DocumentDetailQueryHandler()

