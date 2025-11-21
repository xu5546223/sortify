"""
文檔搜索處理器

處理標準的文檔搜索請求,使用兩階段混合檢索
"""
import time
import logging
from typing import Optional, List, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.logging_utils import AppLogger, log_event, LogLevel
from app.models.vector_models import (
    AIQARequest,
    AIQAResponse,
    QueryRewriteResult,
    SemanticContextDocument,
    SemanticSearchResult
)
from app.models.question_models import QuestionClassification
from app.services.vector.enhanced_search_service import enhanced_search_service
from app.services.vector.embedding_service import embedding_service
from app.services.ai.unified_ai_service_simplified import unified_ai_service_simplified
from app.services.qa_workflow.conversation_helper import conversation_helper
from app.crud.crud_documents import get_documents_by_ids

logger = AppLogger(__name__, level=logging.DEBUG).get_logger()


class DocumentSearchHandler:
    """文檔搜索處理器 - 標準兩階段檢索,2-3次API調用"""
    
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
        處理文檔搜索請求
        
        策略:
        1. 可選輕量級查詢重寫(如果置信度較低)
        2. 請求用戶批准搜索(漸進式交互)
        3. 執行兩階段混合檢索
        4. 顯示找到的文檔供用戶確認
        5. 生成答案
        
        Args:
            request: AI QA 請求
            classification: 問題分類結果
            context: 對話上下文
            db: 數據庫連接
            user_id: 用戶ID
            request_id: 請求ID
            
        Returns:
            AIQAResponse: 文檔搜索結果和答案
        """
        start_time = time.time()
        api_calls = 0
        
        logger.info(f"處理文檔搜索: {request.question}")
        
        # 檢查是否有審批狀態(從 workflow_action 參數獲取)
        workflow_action = getattr(request, 'workflow_action', None)
        
        # 如果用戶選擇跳過搜索,直接使用通用知識回答
        if workflow_action == 'skip_search':
            logger.info("用戶跳過文檔搜索,使用通用知識回答")
            return await self._handle_skip_search(
                request, classification, db, user_id, request_id, start_time
            )
        
        # Step 1: 檢查是否需要用戶批准（根據配置和置信度）
        # 策略: 所有document_search都需要批准,除非置信度非常高
        needs_approval = True
        auto_approve_threshold = 0.90  # 只有置信度 >= 0.90 才自動批准
        
        if classification.confidence >= auto_approve_threshold:
            logger.info(f"置信度{classification.confidence:.2f} >= {auto_approve_threshold},自動批准搜索")
            needs_approval = False
        
        # 如果需要批准且用戶未批准,先請求批准
        if needs_approval and workflow_action != 'approve_search' and not getattr(request, 'skip_classification', False):
            logger.info(f"請求用戶批准文檔搜索（置信度:{classification.confidence:.2f}）")
            processing_time = time.time() - start_time
            
            # 構建給用戶看的預覽信息（不使用正則提取，讓AI重寫處理）
            # 顯示AI的完整推理，讓用戶了解AI的理解
            search_preview = {
                "original_question": request.question,
                "ai_understanding": "將使用 AI 查詢重寫分析上下文並優化搜索",
                "will_use_rewrite": True,
                "reasoning": classification.reasoning[:200] + "..." if len(classification.reasoning) > 200 else classification.reasoning
            }
            
            return AIQAResponse(
                answer="",  # 暫時不生成答案
                source_documents=[],
                confidence_score=0.0,
                tokens_used=0,
                processing_time=processing_time,
                query_rewrite_result=QueryRewriteResult(
                    original_query=request.question,
                    rewritten_queries=[request.question],
                    extracted_parameters=search_preview,
                    intent_analysis=classification.reasoning
                ),
                semantic_search_contexts=[],
                session_id=request.session_id,
                classification=classification,
                workflow_state={
                    "current_step": "awaiting_search_approval",
                    "strategy_used": "document_search",
                    "api_calls": 0,
                    "classification": classification.model_dump() if hasattr(classification, 'model_dump') else {},
                    "search_preview": search_preview,  # 新增：搜索預覽信息
                    "estimated_documents": "未知",
                    "estimated_time": "3-5秒"
                },
                next_action="approve_search",
                pending_approval="search"
            )
        
        # 用戶已批准,繼續執行搜索
        logger.info("用戶已批准文檔搜索,開始執行")
        
        # Step 2: 智能查詢重寫（直接使用AI推理內容）
        # 策略：讓 AI 查詢重寫功能分析原始問題+分類推理，自動提取最佳查詢
        
        # 檢查是否已經有預先重寫的查詢結果（批准操作時由 orchestrator 提供）
        query_rewrite_result = None
        if context and 'pre_rewritten_query_result' in context:
            query_rewrite_result = context['pre_rewritten_query_result']
            logger.info(f"✅ 使用預先重寫的查詢結果（來自批准操作），包含 {len(query_rewrite_result.rewritten_queries)} 個查詢")
        else:
            # 構建給 AI 查詢重寫的輸入（包含原始問題和分類推理）
            if classification.reasoning and len(classification.reasoning) > 20:
                # 有推理內容，組合原始問題和AI的理解
                query_for_rewrite = f"{request.question}。上下文理解: {classification.reasoning[:300]}"
                logger.info(f"📝 查詢重寫輸入: 原始問題 + AI推理內容（{len(classification.reasoning)}字）")
            else:
                # 沒有推理內容，使用原始問題
                query_for_rewrite = request.question
                logger.info(f"📝 查詢重寫輸入: 原始問題（無推理內容）")
            
            # 步驟2.2: 執行智能查詢重寫（AI會自動分析推理內容）
            logger.info(f"🔄 執行智能查詢重寫")
            
            query_rewrite_result = await self._lightweight_query_rewrite(
                query_for_rewrite,  # 原始問題 + AI推理內容
                db,
                user_id,
                request.document_ids,  # ✅ 传递 @ 文件
                context  # ✅ 传递文档池详细信息
            )
            api_calls += 1
        
        # 步驟2.3: 構建最終查詢列表
        if query_rewrite_result and query_rewrite_result.rewritten_queries:
            # 查詢重寫成功（主要路徑）
            queries_to_search = query_rewrite_result.rewritten_queries[:2]
            logger.info(f"✅ 查詢重寫成功，最終查詢: {queries_to_search}")
        else:
            # 查詢重寫失敗，使用原始問題（退路）
            queries_to_search = [request.question]
            logger.warning(f"⚠️ 查詢重寫失敗，退路: 使用原始問題: {request.question}")
            
            # 手動構建query_rewrite_result
            query_rewrite_result = QueryRewriteResult(
                original_query=request.question,
                rewritten_queries=[request.question],
                extracted_parameters={"rewrite_failed": True},
                intent_analysis=classification.reasoning
            )
        
        # Step 2: 執行兩階段混合檢索（支持優先文檔）
        # 檢查是否有優先文檔（從統一上下文管理器傳遞）
        priority_document_ids = context.get('priority_document_ids', []) if context else []
        should_reuse_cached = context.get('should_reuse_cached', False) if context else False
        
        if priority_document_ids and should_reuse_cached:
            logger.info(f"🎯 優先從文檔池檢索: {len(priority_document_ids)} 個文檔")
            # 優先檢索文檔池中的文檔
            semantic_results = await self._perform_hybrid_search(
                db=db,
                queries=queries_to_search,
                top_k=request.context_limit or 5,
                user_id=user_id,
                document_ids=priority_document_ids  # 使用優先文檔
            )
            
            # 如果優先文檔結果不夠好，再擴展搜索
            if not semantic_results or (semantic_results and max(r.similarity_score for r in semantic_results) < 0.6):
                logger.info("📚 優先文檔相關性不足，擴展到全局搜索")
                semantic_results = await self._perform_hybrid_search(
                    db=db,
                    queries=queries_to_search,
                    top_k=request.context_limit or 5,
                    user_id=user_id,
                    document_ids=request.document_ids  # 全局搜索
                )
        else:
            # 正常檢索流程
            semantic_results = await self._perform_hybrid_search(
                db=db,
                queries=queries_to_search,
                top_k=request.context_limit or 5,
                user_id=user_id,
                document_ids=request.document_ids
            )
        
        # Step 3: 準備語義搜索上下文
        semantic_contexts = []
        for result in semantic_results:
            semantic_contexts.append(
                SemanticContextDocument(
                    document_id=result.document_id,
                    summary_or_chunk_text=result.summary_text,
                    similarity_score=result.similarity_score,
                    metadata=result.metadata
                )
            )
        
        # Step 4: 獲取文檔詳細信息
        if not semantic_results:
            logger.warning("未找到相關文檔,提供靈活選項")
            processing_time = time.time() - start_time
            
            # 使用工作流協調器生成智能建議
            from app.services.qa_workflow.workflow_coordinator import workflow_coordinator
            
            return await workflow_coordinator.handle_search_no_results(
                original_request=request,
                classification=classification,
                db=db,
                user_id=user_id,
                request_id=request_id
            )
        
        # 創建文檔ID到相關性評分的映射
        # ⚠️ 注意：RRF 融合搜索會用 RRF 分數覆蓋 similarity_score
        # 真正的向量相似度保存在 metadata["original_similarity"]
        doc_similarity_map = {}
        for result in semantic_results:
            # 優先使用原始向量相似度，如果沒有則使用 similarity_score
            original_sim = result.metadata.get("original_similarity") if result.metadata else None
            similarity = original_sim if original_sim is not None else result.similarity_score
            doc_similarity_map[result.document_id] = similarity
            
        logger.info(f"📊 相似度來源: {'原始向量相似度' if any(r.metadata and 'original_similarity' in r.metadata for r in semantic_results) else 'RRF分數'}")
        
        document_ids = [result.document_id for result in semantic_results]
        documents = await get_documents_by_ids(db, document_ids)
        
        # 過濾用戶有權限的文檔
        if user_id:
            from uuid import UUID
            user_uuid = UUID(str(user_id)) if not isinstance(user_id, UUID) else user_id
            documents = [
                doc for doc in documents
                if hasattr(doc, 'owner_id') and doc.owner_id == user_uuid
            ]
        
        if not documents:
            logger.warning("找到文檔但用戶無權訪問")
            processing_time = time.time() - start_time
            
            no_access_answer = "找到了相關文檔,但您可能沒有訪問權限。"
            
            # 保存對話記錄(無權限情況)
            if db is not None:
                await conversation_helper.save_qa_to_conversation(
                    db=db,
                    conversation_id=request.conversation_id,
                    user_id=str(user_id) if user_id else None,
                    question=request.question,
                    answer=no_access_answer,
                    tokens_used=api_calls * 100,
                    source_documents=[]
                )
            
            return AIQAResponse(
                answer=no_access_answer,
                source_documents=[],
                confidence_score=0.3,
                tokens_used=api_calls * 100,
                processing_time=processing_time,
                query_rewrite_result=query_rewrite_result,
                semantic_search_contexts=semantic_contexts,
                session_id=request.session_id,
                classification=classification
            )
        
        # ⭐ 過濾低相關性文檔（避免污染文檔池）
        # 降低閾值，避免過濾掉有用的文檔（從 0.55 降到 0.45）
        RELEVANCE_THRESHOLD = 0.45  # 相關性閾值
        high_relevance_documents = [
            doc for doc in documents
            if doc_similarity_map.get(str(doc.id), 0) >= RELEVANCE_THRESHOLD
        ]
        
        # 記錄詳細的相似度信息
        if documents:
            similarity_scores = [doc_similarity_map.get(str(doc.id), 0) for doc in documents]
            logger.info(f"📊 文檔相似度分布: 最高={max(similarity_scores):.3f}, 最低={min(similarity_scores):.3f}, 平均={sum(similarity_scores)/len(similarity_scores):.3f}")
        
        if high_relevance_documents:
            # 使用高相關性文檔
            logger.info(f"✅ 過濾後保留 {len(high_relevance_documents)}/{len(documents)} 個高相關性文檔（閾值>={RELEVANCE_THRESHOLD}）")
            documents_for_answer = high_relevance_documents
        else:
            # 如果所有文檔相關性都太低，使用最好的2-3個
            logger.warning(f"⚠️ 所有文檔相關性都低於閾值 {RELEVANCE_THRESHOLD}，使用top-3文檔")
            documents_for_answer = documents[:3] if len(documents) >= 3 else documents
        
        # Step 5: 生成答案(使用摘要+部分內容)
        answer = await self._generate_answer_from_documents(
            question=request.question,
            documents=documents_for_answer,
            semantic_results=semantic_results,
            query_rewrite_result=query_rewrite_result,
            db=db,
            user_id=user_id,
            conversation_id=request.conversation_id,
            context=context
        )
        api_calls += 1
        
        processing_time = time.time() - start_time
        
        # 保存對話記錄（使用過濾後的高相關性文檔）
        if db is not None:
            # ✅ 合併搜索結果 + 用戶 @ 的文件
            all_doc_ids = set()
            if documents_for_answer:
                all_doc_ids.update(str(doc.id) for doc in documents_for_answer)
            if request.document_ids:
                all_doc_ids.update(request.document_ids)
            
            await conversation_helper.save_qa_to_conversation(
                db=db,
                conversation_id=request.conversation_id,
                user_id=str(user_id) if user_id else None,
                question=request.question,
                answer=answer,
                tokens_used=api_calls * 150,
                source_documents=list(all_doc_ids)
            )
        
        # 記錄日誌
        if db is not None:
            await log_event(
                db=db,
                level=LogLevel.INFO,
                message="文檔搜索處理完成",
                source="handler.document_search",
                user_id=str(user_id) if user_id else None,
                request_id=request_id,
                details={
                    "question": request.question[:100],
                    "documents_found": len(documents),
                    "api_calls": api_calls,
                    "processing_time": processing_time
                }
            )
        
        logger.info(
            f"文檔搜索完成,耗時: {processing_time:.2f}秒, "
            f"找到 {len(documents_for_answer)} 個高相關性文檔, API調用: {api_calls}次"
        )
        
        return AIQAResponse(
            answer=answer,
            source_documents=[str(doc.id) for doc in documents_for_answer],
            confidence_score=0.85,
            tokens_used=api_calls * 150,
            processing_time=processing_time,
            query_rewrite_result=query_rewrite_result,
            semantic_search_contexts=semantic_contexts,
            session_id=request.session_id,
            classification=classification,
            workflow_state={
                "current_step": "completed",
                "strategy_used": "document_search_hybrid",
                "api_calls": api_calls,
                "documents_found": len(documents)
            }
        )
    
    async def _lightweight_query_rewrite(
        self,
        question: str,
        db: Optional[AsyncIOMotorDatabase],
        user_id: Optional[str],
        document_ids: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Optional[QueryRewriteResult]:
        """輕量級查詢重寫(生成1-2個變體即可)"""
        try:
            # ✅ 准备文档上下文（包括文档摘要信息）
            document_context = None
            if document_ids:
                logger.info(f"🎯 查询重写：用户选择了 {len(document_ids)} 个文件")
                
                # ✅ 从 context 中获取文档池详细信息（摘要）
                document_summaries = []
                if context and 'cached_documents' in context:
                    for doc in context['cached_documents']:
                        doc_id = doc.get('document_id')
                        if doc_id in document_ids:
                            document_summaries.append({
                                'document_id': doc_id,
                                'filename': doc.get('filename', ''),
                                'summary': doc.get('summary', ''),
                                'key_concepts': doc.get('key_concepts', [])
                            })
                    logger.info(f"📄 获取到 {len(document_summaries)} 个文档摘要用于查询重写")
                
                document_context = {
                    "document_ids": document_ids,
                    "document_count": len(document_ids),
                    "document_summaries": document_summaries  # ✅ 传递文档摘要
                }
            
            ai_response = await unified_ai_service_simplified.rewrite_query(
                original_query=question,
                db=db,
                user_id=user_id,
                document_context=document_context  # ✅ 传递完整文档上下文
            )
            
            if ai_response.success and ai_response.output_data:
                output = ai_response.output_data
                return QueryRewriteResult(
                    original_query=question,
                    rewritten_queries=output.rewritten_queries if hasattr(output, 'rewritten_queries') else [question],
                    extracted_parameters=output.extracted_parameters if hasattr(output, 'extracted_parameters') else {},
                    intent_analysis=output.intent_analysis if hasattr(output, 'intent_analysis') else "",
                    query_granularity=output.query_granularity if hasattr(output, 'query_granularity') else None,
                    search_strategy_suggestion=output.search_strategy_suggestion if hasattr(output, 'search_strategy_suggestion') else None,
                    reasoning=output.reasoning if hasattr(output, 'reasoning') else None
                )
        except Exception as e:
            logger.error(f"查詢重寫失敗: {e}", exc_info=True)
        
        return None
    
    async def _perform_hybrid_search(
        self,
        db: AsyncIOMotorDatabase,
        queries: List[str],
        top_k: int,
        user_id: Optional[str],
        document_ids: Optional[List[str]] = None
    ) -> List[SemanticSearchResult]:
        """執行兩階段混合檢索"""
        
        all_results = {}
        
        for query in queries:
            try:
                # 使用 enhanced_search_service 的 RRF 融合搜索
                results = await enhanced_search_service.two_stage_hybrid_search(
                    db=db,
                    query=query,
                    user_id=str(user_id) if user_id else None,
                    search_type="rrf_fusion",
                    stage1_top_k=min(top_k * 2, 15),
                    stage2_top_k=top_k,
                    similarity_threshold=0.3
                )
                
                # 合併結果(取最高分)
                for result in results:
                    if result.document_id not in all_results or result.similarity_score > all_results[result.document_id].similarity_score:
                        all_results[result.document_id] = result
                        
            except Exception as e:
                logger.error(f"混合搜索失敗(query: {query}): {e}", exc_info=True)
        
        # 排序並返回
        sorted_results = sorted(all_results.values(), key=lambda x: x.similarity_score, reverse=True)
        return sorted_results[:top_k]
    
    async def _generate_answer_from_documents(
        self,
        question: str,
        documents: list,
        semantic_results: list,
        query_rewrite_result: QueryRewriteResult,
        db: Optional[AsyncIOMotorDatabase],
        user_id: Optional[str],
        conversation_id: Optional[str] = None,
        context: Optional[dict] = None
    ) -> str:
        """從文檔生成答案(帶對話歷史)"""
        
        # 使用統一工具載入對話歷史
        from app.services.qa_workflow.unified_context_helper import unified_context_helper
        
        conversation_history_text = ""
        
        # 優先使用傳入的context
        if context and context.get('recent_messages'):
            # 手動格式化context中的消息（保留完整內容）
            conversation_history_text = "=== 對話歷史 ===\n"
            for msg in context['recent_messages']:
                role_name = "用戶" if msg.get("role") == "user" else "助手"
                content = msg.get("content", "")
                # 保留完整內容，最多2000字
                if len(content) > 2000:
                    content = content[:2000] + "...[內容較長，此處省略]"
                conversation_history_text += f"{role_name}: {content}\n"
            conversation_history_text += "=== 當前問題 ===\n"
            logger.info(f"document_search使用傳入的{len(context['recent_messages'])}條歷史")
        else:
            # 使用統一工具載入（保留完整內容）
            conversation_history_text = await unified_context_helper.load_and_format_conversation_history(
                db=db,
                conversation_id=conversation_id,
                user_id=user_id,
                limit=5,
                max_content_length=2000  # 保留完整內容
            )
        
        # 構建上下文(使用摘要+關鍵信息)
        context_parts = []
        if conversation_history_text:
            context_parts.append(conversation_history_text)
        
        for i, doc in enumerate(documents[:5], 1):  # 最多5個文檔
            doc_context = []
            doc_context.append(f"=== 文檔{i}（引用編號: citation:{i}）: {getattr(doc, 'filename', 'Unknown')} ===")
            
            # 嘗試獲取AI分析結果
            if hasattr(doc, 'analysis') and doc.analysis:
                if hasattr(doc.analysis, 'ai_analysis_output') and isinstance(doc.analysis.ai_analysis_output, dict):
                    key_info = doc.analysis.ai_analysis_output.get('key_information', {})
                    
                    # 摘要
                    if key_info.get('content_summary'):
                        doc_context.append(f"摘要: {key_info['content_summary']}")
                    
                    # 關鍵概念
                    if key_info.get('key_concepts'):
                        doc_context.append(f"關鍵概念: {', '.join(key_info['key_concepts'][:5])}")
                    
                    # 主題
                    if key_info.get('main_topics'):
                        doc_context.append(f"主題: {', '.join(key_info['main_topics'][:3])}")
            
            # 如果沒有AI分析,使用提取的文本片段
            if len(doc_context) == 1:  # 只有標題
                matching_result = next(
                    (r for r in semantic_results if r.document_id == str(doc.id)),
                    None
                )
                if matching_result:
                    doc_context.append(matching_result.summary_text[:500])
            
            context_parts.append("\n".join(doc_context))
        
        # 調用AI生成答案(使用用戶偏好的模型)
        try:
            ai_response = await unified_ai_service_simplified.generate_answer(
                user_question=question,
                intent_analysis=query_rewrite_result.intent_analysis or "",
                document_context=context_parts,
                db=db,
                user_id=user_id,
                model_preference=None  # 使用系統配置的用戶偏好模型
            )
            
            if ai_response.success and ai_response.output_data:
                return ai_response.output_data.answer_text
            else:
                logger.error(f"AI生成答案失敗: {ai_response.error_message}")
                return "抱歉,我無法根據找到的文檔生成滿意的答案。"
                
        except Exception as e:
            logger.error(f"生成答案時發生錯誤: {e}", exc_info=True)
            return "抱歉,生成答案時發生錯誤。"
    
    async def _handle_skip_search(
        self,
        request: AIQARequest,
        classification: QuestionClassification,
        db: Optional[AsyncIOMotorDatabase],
        user_id: Optional[str],
        request_id: Optional[str],
        start_time: float
    ) -> AIQAResponse:
        """處理用戶跳過文檔搜索的情況,使用通用知識回答"""
        
        try:
            # 使用 AI 基於通用知識回答
            ai_response = await unified_ai_service_simplified.generate_answer(
                user_question=request.question,
                intent_analysis=classification.reasoning or "",
                document_context=[],  # 空上下文
                db=db,
                user_id=user_id,
                model_preference=None
            )
            
            if ai_response.success and ai_response.output_data:
                answer = ai_response.output_data.answer_text
            else:
                answer = "抱歉,我無法在不查找文檔的情況下回答這個問題。建議您批准文檔搜索以獲得更準確的答案。"
                
        except Exception as e:
            logger.error(f"跳過搜索生成答案失敗: {e}", exc_info=True)
            answer = "抱歉,生成答案時發生錯誤。"
        
        processing_time = time.time() - start_time
        
        # 保存對話記錄
        if db is not None:
            await conversation_helper.save_qa_to_conversation(
                db=db,
                conversation_id=request.conversation_id,
                user_id=str(user_id) if user_id else None,
                question=request.question,
                answer=answer,
                tokens_used=200,  # 估算
                source_documents=[]
            )
        
        query_rewrite_result = QueryRewriteResult(
            original_query=request.question,
            rewritten_queries=[request.question],
            extracted_parameters={},
            intent_analysis="用戶跳過文檔搜索,使用通用知識回答"
        )
        
        return AIQAResponse(
            answer=answer,
            source_documents=[],
            confidence_score=0.5,
            tokens_used=200,
            processing_time=processing_time,
            query_rewrite_result=query_rewrite_result,
            semantic_search_contexts=[],
            session_id=request.session_id,
            classification=classification,
            workflow_state={
                "current_step": "completed",
                "strategy_used": "skip_search_general_knowledge",
                "api_calls": 1
            }
        )


# 創建全局實例
document_search_handler = DocumentSearchHandler()

