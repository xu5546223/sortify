"""
QA 編排器服務

輕量級編排層，組合現有的模塊化服務，統一電腦端和手機端 QA 邏輯。

職責：
- 協調問題分類、搜索、答案生成等服務
- 實現智能路由（根據意圖分派到不同處理器）
- 實現標準 QA 流程
- 保持與現有 API 的向後兼容

遷移自 enhanced_ai_qa_service，但採用組合而非繼承的設計模式。
"""

import logging
import time
import json
import asyncio
from typing import Optional, List, Dict, Any, Tuple, AsyncGenerator
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.logging_utils import AppLogger, log_event, LogLevel
from app.models.vector_models import (
    AIQARequest, AIQAResponse, QueryRewriteResult, 
    SemanticSearchResult, SemanticContextDocument, LLMContextDocument
)
from app.models.question_models import QuestionIntent
from app.core.config import settings

# 導入已有服務
from app.services.qa_core.qa_query_rewriter import qa_query_rewriter
from app.services.qa_core.qa_search_coordinator import qa_search_coordinator
from app.services.qa_core.qa_answer_service import qa_answer_service
from app.services.qa_workflow.question_classifier_service import question_classifier_service
from app.services.qa_workflow.context_loader_service import context_loader_service
from app.services.qa.utils.search_strategy import extract_search_strategy

# 導入意圖處理器
from app.services.intent_handlers.greeting_handler import greeting_handler
from app.services.intent_handlers.clarification_handler import clarification_handler
from app.services.intent_handlers.simple_factual_handler import simple_factual_handler
from app.services.intent_handlers.document_search_handler import document_search_handler
from app.services.intent_handlers.document_detail_query_handler import document_detail_query_handler
from app.services.intent_handlers.complex_analysis_handler import complex_analysis_handler

logger = AppLogger(__name__, level=logging.DEBUG).get_logger()


class StreamEvent:
    """流式事件 - 用於手機端 SSE 輸出"""
    
    def __init__(self, event_type: str, data: dict):
        self.type = event_type
        self.data = data
    
    def to_sse(self) -> str:
        """轉換為 SSE 格式"""
        event_data = {'type': self.type, **self.data}
        return f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"


class QAOrchestrator:
    """
    QA 編排器 - 輕量級協調層
    
    使用組合模式整合已有的模塊化服務，避免重複實現業務邏輯。
    """
    
    def __init__(self):
        """初始化編排器，注入已有服務"""
        # 核心服務（已實例化的全局服務）
        self.query_rewriter = qa_query_rewriter
        self.search_coordinator = qa_search_coordinator
        self.answer_service = qa_answer_service
        self.classifier = question_classifier_service
        self.context_loader = context_loader_service
        
        # 意圖處理器映射
        self.intent_handlers = {
            QuestionIntent.GREETING: greeting_handler,
            QuestionIntent.CHITCHAT: greeting_handler,
            QuestionIntent.CLARIFICATION_NEEDED: clarification_handler,
            QuestionIntent.SIMPLE_FACTUAL: simple_factual_handler,
            QuestionIntent.DOCUMENT_SEARCH: document_search_handler,
            QuestionIntent.DOCUMENT_DETAIL_QUERY: document_detail_query_handler,
            QuestionIntent.COMPLEX_ANALYSIS: complex_analysis_handler,
        }
        
        # 配置
        self.enable_intelligent_routing = getattr(settings, 'ENABLE_INTELLIGENT_ROUTING', True)
        
        logger.info(f"QA 編排器初始化完成，智能路由: {self.enable_intelligent_routing}")
    
    async def process_qa_request_intelligent(
        self,
        db: AsyncIOMotorDatabase,
        request: AIQARequest,
        user_id: Optional[str] = None,
        request_id: Optional[str] = None
    ) -> AIQAResponse:
        """
        智能問答處理入口 - 根據問題意圖動態路由
        
        流程:
        1. 快速意圖分類
        2. 根據意圖路由到對應的處理器
        3. 延遲載入必要的上下文
        4. 返回優化的回答
        
        Args:
            db: 數據庫連接
            request: AI QA 請求
            user_id: 用戶ID
            request_id: 請求ID
            
        Returns:
            AIQAResponse: 問答響應
        """
        start_time = time.time()
        
        logger.info(f"🚀 [編排器] 智能問答請求: {request.question[:100]}...")
        
        # 檢查是否跳過智能路由
        if not self.enable_intelligent_routing or getattr(request, 'skip_classification', False):
            logger.info("智能路由已禁用或被跳過,使用標準流程")
            return await self.process_qa_request(db, request, user_id, request_id)
        
        try:
            # Step 1: 載入對話上下文（用於意圖分類）
            from app.services.qa_workflow.unified_context_helper import unified_context_helper
            
            conversation_context = await unified_context_helper.load_conversation_history_list(
                db=db,
                conversation_id=request.conversation_id,
                user_id=str(user_id) if user_id else None,
                limit=10
            )
            
            # Step 1.5: 獲取緩存文檔信息（用於分類）
            cached_documents_info_for_classifier = None
            if request.conversation_id and user_id:
                cached_documents_info_for_classifier = await self._get_cached_documents_info(
                    db, request.conversation_id, user_id
                )
            
            # Step 2: 快速意圖分類
            classification = await self.classifier.classify_question(
                question=request.question,
                conversation_history=conversation_context,
                has_cached_documents=bool(request.conversation_id),
                cached_documents_info=cached_documents_info_for_classifier,
                db=db,
                user_id=str(user_id) if user_id else None
            )
            
            logger.info(
                f"📊 問題分類完成: intent={classification.intent}, "
                f"confidence={classification.confidence:.2f}, "
                f"strategy={classification.suggested_strategy}"
            )
            
            # Step 3: 根據意圖路由到對應處理器
            handler = self.intent_handlers.get(classification.intent)
            
            if handler:
                logger.info(f"→ 路由到: {handler.__class__.__name__ if hasattr(handler, '__class__') else classification.intent}")
                
                # 延遲載入上下文（如果需要）
                context = await self._load_context_if_needed(
                    db, request, user_id, classification
                )
                
                return await handler.handle(
                    request, classification, context, db, user_id, request_id
                )
            else:
                logger.warning(f"未知的意圖類型: {classification.intent}, 使用標準流程")
                return await self.process_qa_request(db, request, user_id, request_id)
                
        except Exception as e:
            logger.error(f"智能路由處理失敗,回退到標準流程: {e}", exc_info=True)
            
            # 記錄錯誤
            await log_event(
                db=db,
                level=LogLevel.ERROR,
                message=f"智能路由失敗: {str(e)}",
                source="service.qa_orchestrator.intelligent_routing_error",
                user_id=str(user_id) if user_id else None,
                request_id=request_id,
                details={"error": str(e), "question": request.question[:100]}
            )
            
            # 回退到標準流程
            return await self.process_qa_request(db, request, user_id, request_id)
    
    async def process_qa_request(
        self,
        db: AsyncIOMotorDatabase,
        request: AIQARequest,
        user_id: Optional[str] = None,
        request_id: Optional[str] = None
    ) -> AIQAResponse:
        """
        標準 QA 流程 - 簡化版本，委託給已有服務
        
        流程:
        1. 查詢重寫
        2. 向量搜索
        3. 處理文檔
        4. 生成答案
        
        Args:
            db: 數據庫連接
            request: AI QA 請求
            user_id: 用戶ID
            request_id: 請求ID
            
        Returns:
            AIQAResponse: 問答響應
        """
        user_id_str = str(user_id) if user_id else None
        start_time = time.time()
        total_tokens = 0
        
        logger.info(f"📝 [編排器] 標準 QA 流程: {request.question[:100]}...")
        
        await log_event(
            db=db, level=LogLevel.INFO,
            message="QA Orchestrator: Standard flow started",
            source="service.qa_orchestrator.process_qa_request",
            user_id=user_id_str, request_id=request_id,
            details={"question_length": len(request.question) if request.question else 0}
        )
        
        try:
            # Step 1: 查詢重寫
            query_rewrite_result, rewrite_tokens = await self.query_rewriter.rewrite_query(
                db=db,
                original_query=request.question,
                user_id=user_id_str,
                request_id=request_id,
                query_rewrite_count=getattr(request, 'query_rewrite_count', 3)
            )
            total_tokens += rewrite_tokens
            
            # Step 2: 決定搜索策略
            search_strategy = extract_search_strategy(query_rewrite_result)
            logger.info(f"🎯 使用搜索策略: {search_strategy}")
            
            # Step 3: 執行搜索
            queries = query_rewrite_result.rewritten_queries if query_rewrite_result.rewritten_queries else [request.question]
            
            search_results = await self.search_coordinator.unified_search(
                db=db,
                queries=queries,
                user_id=user_id_str,
                search_strategy=search_strategy,
                top_k=getattr(request, 'max_documents_for_selection', request.context_limit),
                similarity_threshold=getattr(request, 'similarity_threshold', 0.3),
                enable_diversity_optimization=True,
                document_ids=request.document_ids if hasattr(request, 'document_ids') else None
            )
            
            # Step 4: 處理搜索結果
            if not search_results:
                logger.warning("向量搜索未找到相關文檔")
                return AIQAResponse(
                    answer="抱歉，我在您的文檔庫中沒有找到與您問題相關的內容。",
                    source_documents=[],
                    confidence_score=0.0,
                    tokens_used=total_tokens,
                    processing_time=time.time() - start_time,
                    query_rewrite_result=query_rewrite_result,
                    semantic_search_contexts=[],
                    session_id=request.session_id
                )
            
            # Step 5: 準備語義搜索上下文
            semantic_contexts_for_response: List[SemanticContextDocument] = []
            for res in search_results:
                semantic_contexts_for_response.append(
                    SemanticContextDocument(
                        document_id=res.document_id,
                        summary_or_chunk_text=res.summary_text,
                        similarity_score=res.similarity_score,
                        metadata=res.metadata
                    )
                )
            
            # Step 6: 獲取完整文檔
            from app.crud.crud_documents import get_documents_by_ids
            document_ids = [result.document_id for result in search_results]
            documents = await get_documents_by_ids(db, document_ids)
            
            if not documents:
                logger.warning("無法獲取完整文檔")
                return AIQAResponse(
                    answer="抱歉，無法獲取相關文檔的詳細內容。",
                    source_documents=[],
                    confidence_score=0.0,
                    tokens_used=total_tokens,
                    processing_time=time.time() - start_time,
                    query_rewrite_result=query_rewrite_result,
                    semantic_search_contexts=semantic_contexts_for_response,
                    session_id=request.session_id
                )
            
            # Step 7: 生成答案（使用 qa_answer_service）
            answer_result = await self.answer_service.generate_answer(
                db=db,
                original_query=request.question,
                documents_for_context=documents,
                query_rewrite_result=query_rewrite_result,
                detailed_document_data=None,  # 標準流程不使用詳細數據
                ai_generated_query_reasoning=None,  # 標準流程不使用 AI 查詢推理
                user_id=user_id_str,
                request_id=request_id,
                model_preference=request.model_preference,
                ensure_chinese_output=getattr(request, 'ensure_chinese_output', None),
                conversation_history=None  # 可以擴展支持
            )
            
            total_tokens += answer_result['tokens_used']
            
            # Step 8: 構建響應
            processing_time = time.time() - start_time
            
            response = AIQAResponse(
                answer=answer_result['answer'],
                source_documents=answer_result['source_documents'],
                confidence_score=answer_result['confidence_score'],
                tokens_used=total_tokens,
                processing_time=processing_time,
                query_rewrite_result=query_rewrite_result,
                semantic_search_contexts=semantic_contexts_for_response,
                llm_context_documents=answer_result['llm_context_documents'],
                session_id=request.session_id
            )
            
            logger.info(f"✅ [編排器] QA 完成，耗時 {processing_time:.2f}s，tokens={total_tokens}")
            
            return response
            
        except Exception as e:
            logger.error(f"❌ [編排器] 標準流程失敗: {e}", exc_info=True)
            
            await log_event(
                db=db, level=LogLevel.ERROR,
                message=f"QA Orchestrator failed: {str(e)}",
                source="service.qa_orchestrator.process_qa_request_error",
                user_id=user_id_str, request_id=request_id,
                details={"error": str(e)}
            )
            
            return AIQAResponse(
                answer=f"抱歉，處理您的問題時發生錯誤：{str(e)}",
                source_documents=[],
                confidence_score=0.0,
                tokens_used=total_tokens,
                processing_time=time.time() - start_time,
                query_rewrite_result=None,
                semantic_search_contexts=[],
                session_id=request.session_id
            )
    
    async def _get_cached_documents_info(
        self,
        db: AsyncIOMotorDatabase,
        conversation_id: str,
        user_id: str
    ) -> Optional[List[Dict]]:
        """獲取緩存文檔信息用於分類"""
        try:
            from app.crud import crud_conversations
            from uuid import UUID
            
            conversation_uuid = UUID(conversation_id)
            user_uuid = UUID(str(user_id)) if not isinstance(user_id, UUID) else user_id
            
            # 獲取緩存的文檔ID
            cached_doc_ids, _ = await crud_conversations.get_cached_documents(
                db=db,
                conversation_id=conversation_uuid,
                user_id=user_uuid
            )
            
            if not cached_doc_ids:
                return None
            
            # 獲取文檔詳細信息
            from app.crud.crud_documents import get_documents_by_ids
            documents = await get_documents_by_ids(db, cached_doc_ids)
            
            # 構建文檔信息列表
            cached_documents_info = []
            for idx, doc in enumerate(documents, 1):
                doc_info = {
                    "document_id": str(doc.id),
                    "filename": doc.filename,
                    "reference_number": idx,
                    "summary": ""
                }
                
                # 安全獲取摘要
                try:
                    enriched_data = getattr(doc, 'enriched_data', None)
                    if enriched_data and isinstance(enriched_data, dict):
                        doc_info["summary"] = enriched_data.get('summary', '')
                    
                    if not doc_info["summary"] and hasattr(doc, 'analysis') and doc.analysis:
                        if hasattr(doc.analysis, 'ai_analysis_output') and isinstance(doc.analysis.ai_analysis_output, dict):
                            key_info = doc.analysis.ai_analysis_output.get('key_information', {})
                            if isinstance(key_info, dict):
                                doc_info["summary"] = key_info.get('content_summary', '')
                except Exception as e:
                    logger.warning(f"獲取文檔 {idx} 摘要失敗: {e}")
                
                cached_documents_info.append(doc_info)
            
            logger.info(f"準備了 {len(cached_documents_info)} 個緩存文檔信息用於分類")
            return cached_documents_info
            
        except Exception as e:
            logger.warning(f"獲取緩存文檔信息失敗: {e}")
            return None
    
    async def _load_context_if_needed(
        self,
        db: AsyncIOMotorDatabase,
        request: AIQARequest,
        user_id: Optional[str],
        classification
    ) -> Optional[dict]:
        """延遲載入對話上下文"""
        try:
            context = await self.context_loader.load_conversation_context_if_needed(
                db=db,
                conversation_id=request.conversation_id,
                user_id=str(user_id) if user_id else None,
                requires_context=classification.requires_context
            )
            
            if context and context.recent_messages:
                logger.info(f"載入了 {len(context.recent_messages)} 條歷史消息")
            
            # 轉換為字典格式(保持兼容性)
            if context:
                return {
                    "conversation_id": context.conversation_id,
                    "recent_messages": context.recent_messages,
                    "cached_document_ids": context.cached_document_ids,
                    "cached_document_data": context.cached_document_data,
                    "message_count": context.message_count
                }
            
            return None
            
        except Exception as e:
            logger.warning(f"載入上下文失敗,繼續處理: {e}")
            return None


    async def process_qa_request_intelligent_stream(
        self,
        db: AsyncIOMotorDatabase,
        request: AIQARequest,
        user_id: Optional[str] = None,
        request_id: Optional[str] = None
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        智能問答處理 - 流式版本（手機端）
        
        保持與現有手機端完全一致的事件格式和流程：
        1. 發送進度事件（分類、搜索等）
        2. 在答案生成階段使用 generate_answer_stream() 真實流式輸出
        3. 支持批准流程（approval_needed）
        4. 支持澄清處理（clarification_text）
        
        Yields:
            StreamEvent: 流式事件（progress, chunk, metadata, complete, error, approval_needed）
        """
        try:
            # 檢查是否是批准操作（批准後不發送重複的進度事件）
            is_approval_action = getattr(request, 'workflow_action', None) in [
                'approve_search', 'skip_search', 
                'approve_detail_query', 'skip_detail_query'
            ]
            
            # === 發送開始事件（批准操作跳過）===
            if not is_approval_action:
                yield StreamEvent('progress', {
                    'stage': 'start',
                    'message': '🚀 開始處理您的問題...'
                })
                await asyncio.sleep(0.05)
            
            # === 步驟 1: 載入對話上下文 ===
            from app.services.qa_workflow.unified_context_helper import unified_context_helper
            
            conversation_context = None
            cached_documents_info_for_classifier = None
            
            if request.conversation_id:
                conversation_context = await unified_context_helper.load_conversation_history_list(
                    db=db,
                    conversation_id=request.conversation_id,
                    user_id=str(user_id) if user_id else None,
                    limit=10
                )
                
                if conversation_context:
                    logger.info(f"載入了 {len(conversation_context)} 條歷史消息")
                
                # 獲取緩存文檔信息
                cached_documents_info_for_classifier = await self._get_cached_documents_info(
                    db, request.conversation_id, user_id
                )
            
            # === 步驟 1.5: 處理澄清回答 ===
            effective_question = request.question
            if getattr(request, 'workflow_action', None) == 'provide_clarification' and getattr(request, 'clarification_text', None):
                logger.info(f"📝 收到澄清回答: {request.clarification_text}")
                
                # 保存澄清回答到對話
                if request.conversation_id:
                    from app.crud import crud_conversations
                    from uuid import UUID
                    try:
                        conversation_uuid = UUID(request.conversation_id)
                        user_uuid = UUID(str(user_id)) if not isinstance(user_id, UUID) else user_id
                        
                        await crud_conversations.add_message_to_conversation(
                            db=db,
                            conversation_id=conversation_uuid,
                            user_id=user_uuid,
                            role="user",
                            content=request.clarification_text,
                            tokens_used=None
                        )
                        
                        # 使緩存失效並重新載入
                        from app.services.cache.conversation_cache_service import conversation_cache_service
                        await conversation_cache_service.invalidate_conversation(
                            user_id=user_uuid,
                            conversation_id=conversation_uuid
                        )
                        
                        conversation_context = await unified_context_helper.load_conversation_history_list(
                            db=db,
                            conversation_id=request.conversation_id,
                            user_id=str(user_id) if user_id else None,
                            limit=10
                        )
                    except Exception as e:
                        logger.error(f"❌ 保存澄清回答失敗: {e}")
                
                effective_question = f"{request.question} → {request.clarification_text}"
            
            # === 步驟 2: 問題分類（批准操作跳過進度發送）===
            if not is_approval_action:
                yield StreamEvent('progress', {
                    'stage': 'classifying',
                    'message': '🎯 AI 正在分析問題意圖...'
                })
                await asyncio.sleep(0.05)
            
            classification = await self.classifier.classify_question(
                question=effective_question,
                conversation_history=conversation_context,
                has_cached_documents=bool(request.conversation_id),
                cached_documents_info=cached_documents_info_for_classifier,
                db=db,
                user_id=str(user_id) if user_id else None
            )
            
            # 發送分類結果（批准操作跳過）
            if not is_approval_action:
                intent_label = {
                    QuestionIntent.GREETING: '寒暄',
                    QuestionIntent.CHITCHAT: '閒聊',
                    QuestionIntent.DOCUMENT_SEARCH: '文檔搜索',
                    QuestionIntent.SIMPLE_FACTUAL: '簡單查詢',
                    QuestionIntent.COMPLEX_ANALYSIS: '複雜分析',
                    QuestionIntent.CLARIFICATION_NEEDED: '需要澄清',
                    QuestionIntent.DOCUMENT_DETAIL_QUERY: 'MongoDB 詳細查詢'
                }.get(classification.intent, str(classification.intent))
                
                yield StreamEvent('progress', {
                    'stage': 'classified',
                    'message': f'✅ 問題分類：{intent_label}（置信度 {classification.confidence:.0%}）'
                })
                await asyncio.sleep(0.1)
                
                # 發送推理內容
                if hasattr(classification, 'reasoning') and classification.reasoning:
                    yield StreamEvent('progress', {
                        'stage': 'reasoning',
                        'message': f'💭 AI 推理',
                        'detail': classification.reasoning
                    })
                    await asyncio.sleep(0.05)
            
            # === 步驟 3: 路由到處理器（流式版本）===
            handler = self.intent_handlers.get(classification.intent)
            
            if not handler:
                yield StreamEvent('error', {'message': f'未知的意圖類型: {classification.intent}'})
                return
            
            logger.info(f"→ 路由到: {handler.__class__.__name__ if hasattr(handler, '__class__') else classification.intent}")
            
            # 載入上下文
            context = await self._load_context_if_needed(
                db, request, user_id, classification
            )
            
            # 檢查 handler 是否有流式版本
            if hasattr(handler, 'handle_stream'):
                # 使用流式處理器
                async for event in handler.handle_stream(
                    request, classification, context, db, user_id, request_id
                ):
                    yield event
            else:
                # 使用普通處理器，根據意圖類型決定參數
                # 簡單意圖處理
                if classification.intent in [QuestionIntent.GREETING, QuestionIntent.CHITCHAT]:
                    # 簡單意圖直接處理（context = None）
                    response = await handler.handle(
                        request, classification, None, db, user_id, request_id
                    )
                    yield StreamEvent('complete', {'answer': response.answer})
                    
                elif classification.intent == QuestionIntent.CLARIFICATION_NEEDED:
                    # 需要澄清（可以使用 context 生成更好的澄清問題）
                    response = await handler.handle(
                        request, classification, context, db, user_id, request_id
                    )
                    # 發送澄清請求，包含完整信息
                    approval_data = {
                        'workflow_state': response.workflow_state,
                        'classification': response.classification.model_dump() if response.classification else None,
                        'next_action': response.next_action,
                        'pending_approval': response.pending_approval
                    }
                    yield StreamEvent('approval_needed', approval_data)
                    
                elif classification.intent == QuestionIntent.SIMPLE_FACTUAL:
                    # 簡單事實查詢（context = None）
                    response = await handler.handle(
                        request, classification, None, db, user_id, request_id
                    )
                    if response.answer:
                        yield StreamEvent('complete', {'answer': response.answer})
                    else:
                        yield StreamEvent('error', {'message': '處理失敗'})
                else:
                    # 其他意圖（DOCUMENT_SEARCH, DOCUMENT_DETAIL_QUERY, COMPLEX_ANALYSIS）需要 context
                    # 如果 handler 沒有實現 handle_stream，直接調用 handle
                    
                    # 如果是批准操作，先執行預處理並立即反饋
                    if is_approval_action and classification.intent == QuestionIntent.DOCUMENT_SEARCH:
                        yield StreamEvent('progress', {
                            'stage': 'query_rewriting',
                            'message': '🔄 正在優化查詢語句...'
                        })
                        await asyncio.sleep(0.05)
                        
                        # 執行查詢重寫
                        from app.services.qa_core.qa_query_rewriter import qa_query_rewriter
                        query_rewrite_result, rewrite_tokens = await qa_query_rewriter.rewrite_query(
                            db=db,
                            original_query=request.question,
                            user_id=user_id,
                            request_id=request_id
                        )
                        
                        # 立即發送查詢重寫結果
                        if query_rewrite_result and query_rewrite_result.rewritten_queries:
                            yield StreamEvent('progress', {
                                'stage': 'query_rewriting',
                                'message': f'✨ 已優化查詢（生成 {len(query_rewrite_result.rewritten_queries)} 個）',
                                'detail': {
                                    'queries': query_rewrite_result.rewritten_queries,
                                    'count': len(query_rewrite_result.rewritten_queries)
                                }
                            })
                            await asyncio.sleep(0.05)
                    
                    # 如果是詳細查詢批准，發送 MongoDB 查詢進度
                    if is_approval_action and classification.intent == QuestionIntent.DOCUMENT_DETAIL_QUERY:
                        yield StreamEvent('progress', {
                            'stage': 'mongodb_query',
                            'message': '🔍 正在執行 MongoDB 詳細查詢...'
                        })
                        await asyncio.sleep(0.05)
                    
                    # 調用 handler（這些 handlers 接受 context 參數）
                    response = await handler.handle(
                        request, classification, context, db, user_id, request_id
                    )
                    
                    # 發送完成進度
                    if is_approval_action:
                        # 如果是文檔搜索，顯示找到的文檔數
                        if classification.intent == QuestionIntent.DOCUMENT_SEARCH and response.source_documents:
                            doc_count = len(response.source_documents)
                            yield StreamEvent('progress', {
                                'stage': 'vector_search',
                                'message': f'✅ 已搜索到 {doc_count} 個相關文檔'
                            })
                            await asyncio.sleep(0.05)
                        
                        # 如果是詳細查詢，顯示 MongoDB 查詢結果
                        elif classification.intent == QuestionIntent.DOCUMENT_DETAIL_QUERY:
                            # 從 response 中提取詳細數據信息
                            detail_info = {}
                            mongodb_data = []
                            
                            if hasattr(response, 'semantic_search_contexts') and response.semantic_search_contexts:
                                detail_info['queried_documents'] = len(response.semantic_search_contexts)
                                # 計算總欄位數並收集數據
                                total_fields = 0
                                for ctx in response.semantic_search_contexts:
                                    if ctx.metadata:
                                        if 'fields_count' in ctx.metadata:
                                            total_fields += ctx.metadata['fields_count']
                                        # 將完整的 context 數據添加到 mongodb_data
                                        mongodb_data.append({
                                            'document_id': ctx.document_id,
                                            'metadata': ctx.metadata
                                        })
                                detail_info['total_fields'] = total_fields
                            
                            if response.source_documents:
                                detail_info['source_documents'] = len(response.source_documents)
                            
                            # 包含實際的 MongoDB 查詢數據
                            if mongodb_data:
                                detail_info['mongodb_data'] = mongodb_data
                            
                            message = f'✅ MongoDB 查詢完成'
                            if detail_info.get('queried_documents'):
                                message += f"（查詢 {detail_info['queried_documents']} 個文檔"
                                if detail_info.get('total_fields'):
                                    message += f"，提取 {detail_info['total_fields']} 個欄位"
                                message += "）"
                            
                            yield StreamEvent('progress', {
                                'stage': 'mongodb_query',
                                'message': message,
                                'detail': detail_info
                            })
                            await asyncio.sleep(0.05)
                    
                    # 檢查是否需要批准（pending_approval 是 response 的直接屬性）
                    if response.pending_approval or (response.workflow_state and response.workflow_state.get('pending_approval')):
                        logger.info(f"需要批准: {response.pending_approval or response.workflow_state.get('pending_approval')}")
                        # 發送批准請求，包含完整信息
                        approval_data = {
                            'workflow_state': response.workflow_state,
                            'query_rewrite_result': response.query_rewrite_result.model_dump() if response.query_rewrite_result else None,
                            'classification': response.classification.model_dump() if response.classification else None,
                            'next_action': response.next_action,
                            'pending_approval': response.pending_approval
                        }
                        yield StreamEvent('approval_needed', approval_data)
                        # 不繼續處理，等待用戶批准
                    elif response.answer:
                        # 有答案，發送流式輸出
                        # 發送生成進度
                        yield StreamEvent('progress', {
                            'stage': 'ai_generating',
                            'message': '🤖 AI 正在生成答案...'
                        })
                        await asyncio.sleep(0.05)
                        
                        # 模擬流式輸出答案
                        answer = response.answer
                        chunk_size = 50
                        for i in range(0, len(answer), chunk_size):
                            chunk = answer[i:i+chunk_size]
                            yield StreamEvent('chunk', {'text': chunk})
                            await asyncio.sleep(0.01)
                        
                        # 發送元數據
                        yield StreamEvent('metadata', {
                            'tokens_used': response.tokens_used,
                            'source_documents': response.source_documents if response.source_documents else [],
                            'processing_time': response.processing_time
                        })
                        
                        yield StreamEvent('complete', {'message': '✅ 處理完成'})
                    else:
                        # 沒有答案也沒有 workflow_state，可能是錯誤
                        yield StreamEvent('error', {'message': '處理失敗，未返回結果'})
            
        except Exception as e:
            logger.error(f"流式智能路由失敗: {e}", exc_info=True)
            yield StreamEvent('error', {'message': str(e)})


# 創建全局實例
qa_orchestrator = QAOrchestrator()
