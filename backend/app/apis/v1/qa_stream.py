"""
流式問答 API 端點

只在答案生成階段使用流式輸出，前面的分類、搜索等步驟實時發送進度
"""
import logging
import json
import asyncio
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import Optional, AsyncGenerator

from app.dependencies import get_db
from app.models.user_models import User
from app.core.security import get_current_active_user
from app.models.vector_models import AIQARequest
from app.core.logging_utils import AppLogger, log_event, LogLevel

router = APIRouter()
logger = AppLogger(__name__, level=logging.DEBUG).get_logger()


async def generate_streaming_answer(
    db: AsyncIOMotorDatabase,
    request: AIQARequest,
    user_id: str
) -> AsyncGenerator[str, None]:
    """
    流式生成答案的核心邏輯 - 實時發送每個處理步驟的進度
    
    工作流程：
    1. 智能分類（實時進度）
    2. 文檔搜索（實時進度，包含查詢重寫、向量搜索等）
    3. 工作流批准（如需要）
    4. 答案生成（流式輸出）⭐
    """
    try:
        # === 發送開始信號 ===
        yield f"data: {json.dumps({'type': 'progress', 'stage': 'start', 'message': '🚀 開始處理您的問題...'}, ensure_ascii=False)}\n\n"
        await asyncio.sleep(0.05)
        
        # === 步驟 1: 載入對話上下文 ===
        from app.services.qa_workflow.unified_context_helper import unified_context_helper
        from app.services.qa_workflow.question_classifier_service import question_classifier_service
        from app.models.question_models import QuestionIntent
        
        logger.info(f"🚀 [Stream QA] 開始處理問題: {request.question[:50]}...")
        
        conversation_context = None
        cached_documents_info_for_classifier = None
        
        # 載入對話歷史
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
            try:
                from app.crud import crud_conversations
                from uuid import UUID
                
                conversation_uuid = UUID(request.conversation_id)
                user_uuid = UUID(str(user_id)) if not isinstance(user_id, UUID) else user_id
                
                cached_doc_ids, _ = await crud_conversations.get_cached_documents(
                    db=db,
                    conversation_id=conversation_uuid,
                    user_id=user_uuid
                )
                
                if cached_doc_ids:
                    from app.crud.crud_documents import get_documents_by_ids
                    documents = await get_documents_by_ids(db, cached_doc_ids)
                    
                    cached_documents_info_for_classifier = []
                    for idx, doc in enumerate(documents, 1):
                        doc_info = {
                            "document_id": str(doc.id),
                            "filename": doc.filename,
                            "reference_number": idx,
                            "summary": ""
                        }
                        
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
                        
                        cached_documents_info_for_classifier.append(doc_info)
                    
                    logger.info(f"準備了 {len(cached_documents_info_for_classifier)} 個緩存文檔信息用於分類")
            except Exception as e:
                logger.warning(f"獲取緩存文檔信息失敗: {e}")
        
        # === 步驟 1.5: 處理澄清回答 ===
        effective_question = request.question
        if request.workflow_action == 'provide_clarification' and request.clarification_text:
            logger.info(f"📝 收到澄清回答: {request.clarification_text}")
            
            # 先保存用戶的澄清回答到對話歷史
            if request.conversation_id:
                from app.crud import crud_conversations
                from uuid import UUID
                try:
                    conversation_uuid = UUID(request.conversation_id)
                    user_uuid = UUID(str(user_id)) if not isinstance(user_id, UUID) else user_id
                    
                    # 直接添加用戶的澄清回答消息
                    await crud_conversations.add_message_to_conversation(
                        db=db,
                        conversation_id=conversation_uuid,
                        user_id=user_uuid,
                        role="user",
                        content=request.clarification_text,
                        tokens_used=None
                    )
                    logger.info(f"✅ 已保存澄清回答到對話歷史: {request.clarification_text}")
                    
                    # 使緩存失效並重新載入對話歷史（包含剛保存的澄清回答）
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
                    logger.info(f"🔄 重新載入對話歷史，現在有 {len(conversation_context) if conversation_context else 0} 條消息")
                except Exception as e:
                    logger.error(f"❌ 保存澄清回答失敗: {e}")
            
            # 將澄清回答組合到問題中，用於後續處理
            # 格式：「原始問題 → 澄清回答」
            effective_question = f"{request.question} → {request.clarification_text}"
            logger.info(f"🔀 組合後的有效問題: {effective_question}")
        
        # === 步驟 2: 問題分類（實時進度）===
        yield f"data: {json.dumps({'type': 'progress', 'stage': 'classifying', 'message': '🎯 AI 正在分析問題意圖...'}, ensure_ascii=False)}\n\n"
        await asyncio.sleep(0.05)
        
        classification = await question_classifier_service.classify_question(
            question=effective_question,  # 使用組合後的問題（如果有澄清回答）
            conversation_history=conversation_context,
            has_cached_documents=bool(request.conversation_id),
            cached_documents_info=cached_documents_info_for_classifier,
            db=db,
            user_id=str(user_id) if user_id else None
        )
        
        # 發送分類結果
        intent_label = {
            'greeting': '寒暄',
            'chitchat': '閒聊',
            'document_search': '文檔搜索',
            'simple_factual': '簡單查詢',
            'complex_analysis': '複雜分析',
            'clarification_needed': '需要澄清',
            'document_detail_query': 'MongoDB 詳細查詢'
        }.get(classification.intent, classification.intent)
        
        yield f"data: {json.dumps({'type': 'progress', 'stage': 'classified', 'message': f'✅ 問題分類：{intent_label}（置信度 {classification.confidence:.0%}）'}, ensure_ascii=False)}\n\n"
        await asyncio.sleep(0.1)
        
        # 顯示 AI 推理內容
        if hasattr(classification, 'reasoning') and classification.reasoning:
            yield f"data: {json.dumps({'type': 'progress', 'stage': 'reasoning', 'message': f'💭 AI 推理', 'detail': classification.reasoning}, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.1)
        
        # === 步驟 3: 根據意圖路由處理（實時進度）===
        from app.services.intent_handlers.greeting_handler import greeting_handler
        from app.services.intent_handlers.clarification_handler import clarification_handler
        from app.services.intent_handlers.simple_factual_handler import simple_factual_handler
        from app.services.intent_handlers.document_search_handler import document_search_handler
        from app.services.intent_handlers.document_detail_query_handler import document_detail_query_handler
        from app.services.intent_handlers.complex_analysis_handler import complex_analysis_handler
        from app.services.enhanced_ai_qa_service import enhanced_ai_qa_service
        
        # 簡單意圖直接處理
        if classification.intent in [QuestionIntent.GREETING, QuestionIntent.CHITCHAT]:
            logger.info("→ 處理寒暄/閒聊")
            response = await greeting_handler.handle(
                request, classification, db, user_id, None
            )
            yield f"data: {json.dumps({'type': 'complete', 'answer': response.answer}, ensure_ascii=False)}\n\n"
            return
        
        elif classification.intent == QuestionIntent.CLARIFICATION_NEEDED:
            logger.info("→ 需要澄清")
            response = await clarification_handler.handle(
                request, classification, db, user_id, None
            )
            yield f"data: {json.dumps({'type': 'approval_needed', 'workflow_state': response.workflow_state}, ensure_ascii=False)}\n\n"
            return
        
        # === 步驟 4: MongoDB 詳細查詢（直接使用緩存文檔） ===
        elif classification.intent == QuestionIntent.DOCUMENT_DETAIL_QUERY:
            logger.info("→ 處理 MongoDB 詳細查詢（流式輸出）")
            
            # 載入上下文
            context = await enhanced_ai_qa_service._load_context_if_needed(
                db, request, user_id, classification
            )
            
            # 檢查工作流操作
            workflow_action = getattr(request, 'workflow_action', None)
            
            # 獲取已知的文檔ID
            cached_doc_ids = []
            if context and context.get('cached_document_ids'):
                cached_doc_ids = context['cached_document_ids']
            
            target_doc_ids = []
            if classification.target_document_ids:
                target_doc_ids = classification.target_document_ids
            elif cached_doc_ids:
                target_doc_ids = cached_doc_ids
            
            if not target_doc_ids:
                yield f"data: {json.dumps({'type': 'error', 'message': '無法確定要查詢的文檔'}, ensure_ascii=False)}\n\n"
                return
            
            # 步驟4.1: 請求批准詳細查詢
            if workflow_action != 'approve_detail_query':
                logger.info("🔔 請求用戶批准 MongoDB 詳細查詢")
                
                # 獲取文檔名稱
                from app.crud.crud_documents import get_documents_by_ids
                doc_names = []
                try:
                    documents = await get_documents_by_ids(db, [str(doc_id) for doc_id in target_doc_ids])
                    doc_names = [doc.filename for doc in documents if hasattr(doc, 'filename')]
                    logger.info(f"獲取到 {len(doc_names)} 個文檔名稱用於顯示")
                except Exception as e:
                    logger.warning(f"獲取文檔名稱失敗: {e}")
                
                workflow_state = {
                    "current_step": "awaiting_detail_query_approval",
                    "classification": {
                        "intent": classification.intent,
                        "confidence": classification.confidence,
                        "reasoning": classification.reasoning if hasattr(classification, 'reasoning') else None
                    },
                    "question": request.question,
                    "pending_action": "approve_detail_query",
                    "target_documents": target_doc_ids,
                    "document_names": doc_names,  # 添加文檔名稱
                    "query_type": "詳細數據查詢",
                    "estimated_time": "2-4秒"
                }
                yield f"data: {json.dumps({'type': 'approval_needed', 'workflow_state': workflow_state}, ensure_ascii=False)}\n\n"
                return
            
            # 已批准，執行詳細查詢
            logger.info("✅ 用戶批准 MongoDB 詳細查詢")
            yield f"data: {json.dumps({'type': 'progress', 'stage': 'detail_query_approved', 'message': '✅ 開始執行詳細查詢...'}, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.1)
            
            # 步驟4.2: 執行 MongoDB 查詢
            all_detailed_data = []
            for doc_id in target_doc_ids:
                try:
                    # 使用 AI 生成查詢
                    from app.services.ai.unified_ai_service_simplified import unified_ai_service_simplified, AIRequest
                    from app.services.ai.unified_ai_config import TaskType
                    from uuid import UUID
                    
                    # 將字符串 ID 轉換為 UUID（如果需要）
                    doc_id_uuid = UUID(str(doc_id)) if not isinstance(doc_id, UUID) else doc_id
                    
                    doc_info = await db.documents.find_one({"_id": doc_id_uuid})
                    if not doc_info:
                        logger.warning(f"無法找到文檔 {doc_id}")
                        continue
                    
                    # 準備 schema 信息，避免包含無法序列化的對象
                    schema_info = {
                        "available_fields": ["filename", "extracted_text", "analysis"],
                        "document_filename": doc_info.get("filename", "未知文件")
                    }
                    
                    ai_request = AIRequest(
                        task_type=TaskType.MONGODB_DETAIL_QUERY_GENERATION,
                        content=f"用戶問題: {request.question}",
                        prompt_params={
                            "user_question": request.question,
                            "document_id": str(doc_id_uuid),
                            "document_schema_info": json.dumps(schema_info, ensure_ascii=False)
                        }
                    )
                    
                    ai_response = await unified_ai_service_simplified.process_request(ai_request, db)
                    
                    if ai_response.success:
                        from app.models.ai_models_simplified import AIMongoDBQueryDetailOutput
                        
                        if isinstance(ai_response.output_data, str):
                            query_output = AIMongoDBQueryDetailOutput(**json.loads(ai_response.output_data))
                        else:
                            query_output = ai_response.output_data
                        
                        projection = query_output.projection or {}
                        sub_filter = query_output.sub_filter or {}
                        
                        # 執行查詢
                        query_result = await db.documents.find_one(
                            {"_id": doc_id_uuid, **sub_filter},
                            projection
                        )
                        
                        if query_result:
                            query_result["_reference_number"] = target_doc_ids.index(doc_id) + 1
                            all_detailed_data.append(query_result)
                            logger.info(f"成功獲取文檔 {doc_info.get('filename')} 的詳細數據")
                        
                except Exception as e:
                    logger.error(f"查詢文檔 {doc_id} 失敗: {e}")
            
            if not all_detailed_data:
                yield f"data: {json.dumps({'type': 'error', 'message': '未能獲取任何文檔詳細數據'}, ensure_ascii=False)}\n\n"
                return
            
            # 步驟4.3: 流式生成答案
            yield f"data: {json.dumps({'type': 'progress', 'stage': 'ai_generating', 'message': '🤖 AI 正在生成答案...'}, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.1)
            
            full_answer = ""
            async for chunk in document_detail_query_handler.generate_answer_from_details_stream(
                question=request.question,
                detailed_data=all_detailed_data,
                classification=classification,
                db=db,
                user_id=user_id,
                conversation_id=request.conversation_id,
                context=context
            ):
                full_answer += chunk
                yield f"data: {json.dumps({'type': 'chunk', 'text': chunk}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.01)
            
            logger.info(f"✅ [Stream QA] 詳細查詢流式生成完成，總長度: {len(full_answer)} 字符")
            
            # 步驟4.4: 保存到對話
            if request.conversation_id and user_id:
                try:
                    from app.services.qa_workflow.conversation_helper import conversation_helper
                    await conversation_helper.save_qa_to_conversation(
                        db=db,
                        conversation_id=request.conversation_id,
                        user_id=user_id,
                        question=request.question,
                        answer=full_answer,
                        tokens_used=0,
                        source_documents=target_doc_ids
                    )
                    logger.info("💾 已保存到對話歷史")
                except Exception as e:
                    logger.error(f"❌ 保存對話失敗: {e}")
            
            # 發送元數據
            metadata = {
                'type': 'metadata',
                'tokens_used': 0,
                'source_documents': target_doc_ids,
                'processing_time': 0,
            }
            yield f"data: {json.dumps(metadata, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
            return
        
        # === 步驟 5: 需要搜索的意圖（文檔搜索、複雜分析）===
        if classification.intent in [
            QuestionIntent.DOCUMENT_SEARCH,
            QuestionIntent.COMPLEX_ANALYSIS
        ]:
            # 載入上下文
            context = await enhanced_ai_qa_service._load_context_if_needed(
                db, request, user_id, classification
            )
            
            # === 檢查是否需要搜索批准 ===
            from app.services.qa_workflow.workflow_coordinator import workflow_coordinator
            from app.core.config import settings
            
            # 檢查用戶是否已經批准過
            already_approved = request.workflow_action in ['approve_search', 'approve_detail_query']
            
            if already_approved:
                logger.info(f"✅ 用戶已批准操作: {request.workflow_action}，跳過批准檢查")
            else:
                config = {
                    'auto_approve_all_searches': getattr(settings, 'AUTO_APPROVE_ALL_SEARCHES', False),
                    'auto_approve_high_confidence': getattr(settings, 'AUTO_APPROVE_HIGH_CONFIDENCE', False)
                }
                
                needs_approval = workflow_coordinator.should_request_search_approval(classification, config)
                
                if needs_approval:
                    logger.info("🔔 需要用戶批准文檔搜索")
                    
                    workflow_state = {
                        "current_step": "awaiting_search_approval",
                        "classification": {
                            "intent": classification.intent,
                            "confidence": classification.confidence,
                            "reasoning": classification.reasoning if hasattr(classification, 'reasoning') else None
                        },
                        "question": request.question,
                        "pending_action": "approve_search"
                    }
                    
                    yield f"data: {json.dumps({'type': 'approval_needed', 'workflow_state': workflow_state}, ensure_ascii=False)}\n\n"
                    return
            
            # 已批准或自動批准，繼續處理
            logger.info("✅ 搜索已批准，開始執行...")
            
            # === 步驟 6: 執行查詢重寫（文檔搜索和複雜分析）===
            query_rewrite_result = None
            rewritten_queries = []
            
            if classification.intent in [QuestionIntent.DOCUMENT_SEARCH, QuestionIntent.COMPLEX_ANALYSIS]:
                yield f"data: {json.dumps({'type': 'progress', 'stage': 'query_rewriting', 'message': '🔄 正在優化查詢語句...'}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.05)
                
                # 執行查詢重寫
                from app.services.ai.unified_ai_service_simplified import unified_ai_service_simplified
                
                # 優先使用分類推理作為重寫輸入；若無則使用包含澄清的有效問題；最後回退到原始問題
                base_rewrite_input = classification.reasoning if hasattr(classification, 'reasoning') and classification.reasoning else effective_question
                query_rewrite_response = await unified_ai_service_simplified.rewrite_query(
                    original_query=base_rewrite_input,
                    model_preference=request.model_preference,
                    user_id=str(user_id) if user_id else None,
                    session_id=request.session_id,
                    db=db
                )
                
                if query_rewrite_response.success and query_rewrite_response.output_data:
                    from app.models.vector_models import QueryRewriteResult
                    from app.models.ai_models_simplified import AIQueryRewriteOutput
                    
                    ai_query_output = query_rewrite_response.output_data
                    if isinstance(ai_query_output, AIQueryRewriteOutput):
                        rewritten_queries = ai_query_output.rewritten_queries or [base_rewrite_input]
                        
                        query_rewrite_result = QueryRewriteResult(
                            original_query=base_rewrite_input,
                            rewritten_queries=rewritten_queries,
                            extracted_parameters=ai_query_output.extracted_parameters or {},
                            intent_analysis=ai_query_output.intent_analysis or "",
                            search_strategy_suggestion=getattr(ai_query_output, 'search_strategy_suggestion', None),
                            query_granularity=getattr(ai_query_output, 'query_granularity', None)
                        )
                        
                        # 發送查詢重寫結果
                        yield f"data: {json.dumps({'type': 'progress', 'stage': 'query_rewrite', 'message': f'✅ 查詢優化完成', 'detail': {'count': len(rewritten_queries), 'queries': rewritten_queries}}, ensure_ascii=False)}\n\n"
                        await asyncio.sleep(0.1)
                    else:
                        rewritten_queries = [base_rewrite_input]
                else:
                    logger.warning(f"查詢重寫失敗，使用原始查詢: {query_rewrite_response.error_message}")
                    rewritten_queries = [base_rewrite_input]
                
                # === 步驟 6: 向量搜索 ===
                yield f"data: {json.dumps({'type': 'progress', 'stage': 'vector_search', 'message': '🔍 正在向量資料庫中搜索相關文檔...'}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.05)
                
                # 決定搜索策略
                search_strategy = enhanced_ai_qa_service._extract_search_strategy(query_rewrite_result)
                logger.info(f"使用搜索策略: {search_strategy}")
                
                # 執行向量搜索
                semantic_results = await enhanced_ai_qa_service._unified_search(
                    db=db,
                    queries=rewritten_queries,
                    search_strategy=search_strategy,
                    top_k=getattr(request, 'top_k', 5),
                    user_id=str(user_id) if user_id else None,
                    request_id=None,
                    similarity_threshold=getattr(request, 'similarity_threshold', 0.3),
                    document_ids=request.document_ids if hasattr(request, 'document_ids') else None
                )
                
                # 發送搜索結果
                if semantic_results:
                    doc_count = len(semantic_results)
                    avg_similarity = sum(r.similarity_score for r in semantic_results) / doc_count if doc_count > 0 else 0
                    
                    yield f"data: {json.dumps({'type': 'progress', 'stage': 'search_complete', 'message': f'📄 找到 {doc_count} 個相關文檔（平均相似度 {avg_similarity:.1%}）'}, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0.1)
                else:
                    yield f"data: {json.dumps({'type': 'progress', 'stage': 'search_complete', 'message': '⚠️ 未找到相關文檔'}, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0.1)
                
                # === 步驟 7: 獲取完整文檔 ===
                if semantic_results:
                    yield f"data: {json.dumps({'type': 'progress', 'stage': 'loading_documents', 'message': '📚 正在載入文檔內容...'}, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0.05)
                    
                    from app.crud.crud_documents import get_documents_by_ids
                    document_ids_from_search = [result.document_id for result in semantic_results]
                    full_documents = await get_documents_by_ids(db, document_ids_from_search)
                    
                    logger.info(f"成功載入 {len(full_documents)} 個完整文檔")
                else:
                    full_documents = []
                
                # === 步驟 7: 準備上下文並生成答案 ===
                yield f"data: {json.dumps({'type': 'progress', 'stage': 'preparing_context', 'message': '📝 正在準備上下文...'}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.05)
                
                # 1. 載入對話歷史
                context_parts = []
                if request.conversation_id:
                    from app.services.qa_workflow.unified_context_helper import unified_context_helper
                    conversation_history_text = await unified_context_helper.load_and_format_conversation_history(
                        db=db,
                        conversation_id=request.conversation_id,
                        user_id=str(user_id) if user_id else None,
                        limit=10,  # 最多載入10輪對話
                        max_content_length=3000  # 限制歷史長度
                    )
                    if conversation_history_text:
                        context_parts.append(f"=== 對話歷史 ===\n{conversation_history_text}\n")
                        logger.info(f"已載入對話歷史，長度: {len(conversation_history_text)} 字符")
                
                # 2. 提取文檔內容作為上下文
                if full_documents:
                    for doc in full_documents[:5]:  # 最多使用5個文檔
                        doc_content = ""
                        
                        # 嘗試獲取 AI 分析摘要
                        if hasattr(doc, 'analysis') and doc.analysis:
                            if hasattr(doc.analysis, 'ai_analysis_output') and isinstance(doc.analysis.ai_analysis_output, dict):
                                try:
                                    from app.models.ai_models_simplified import AIDocumentAnalysisOutputDetail
                                    analysis_output = AIDocumentAnalysisOutputDetail(**doc.analysis.ai_analysis_output)
                                    if analysis_output.key_information and analysis_output.key_information.content_summary:
                                        doc_content = analysis_output.key_information.content_summary
                                except Exception:
                                    pass
                        
                        # 回退到原始文本
                        if not doc_content and hasattr(doc, 'extracted_text') and doc.extracted_text:
                            doc_content = doc.extracted_text[:2000]  # 限制長度
                        
                        if doc_content:
                            context_parts.append(f"文檔: {doc.filename}\n{doc_content}")
                
                # 如果沒有文檔但有對話歷史，也可以回答
                if not any("文檔:" in part or "===" in part for part in context_parts[1:] if len(context_parts) > 1):
                    if not context_parts:
                        context_parts = ["沒有可用的文檔上下文"]
                    else:
                        # 有對話歷史但沒有文檔
                        logger.info("只有對話歷史，沒有額外的文檔內容")
                
                # 獲取意圖分析
                intent_analysis = ""
                if query_rewrite_result and query_rewrite_result.intent_analysis:
                    intent_analysis = query_rewrite_result.intent_analysis
                elif hasattr(classification, 'reasoning'):
                    intent_analysis = classification.reasoning
                
                # === 步驟 8: 流式生成答案 ===
                yield f"data: {json.dumps({'type': 'progress', 'stage': 'ai_generating', 'message': '🤖 AI 正在生成答案...'}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.1)
                
                from app.services.ai.unified_ai_service_stream import generate_answer_stream
                
                full_answer = ""
                async for chunk in generate_answer_stream(
                    user_question=request.question,
                    intent_analysis=intent_analysis,
                    document_context=context_parts,
                    model_preference=request.model_preference,
                    user_id=user_id,
                    db=db,
                    detailed_text_max_length=getattr(request, 'detailed_text_max_length', 8000),
                    max_chars_per_doc=getattr(request, 'max_chars_per_doc', None)
                ):
                    full_answer += chunk
                    yield f"data: {json.dumps({'type': 'chunk', 'text': chunk}, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0.01)
                
                logger.info(f"✅ [Stream QA] 流式生成完成，總長度: {len(full_answer)} 字符")
                
                # === 步驟 9: 保存到對話 ===
                if request.conversation_id and user_id:
                    try:
                        from app.services.qa_workflow.conversation_helper import conversation_helper
                        await conversation_helper.save_qa_to_conversation(
                            db=db,
                            conversation_id=request.conversation_id,
                            user_id=user_id,
                            question=request.question,
                            answer=full_answer,
                            tokens_used=0,
                            source_documents=[str(doc.id) for doc in full_documents]
                        )
                        logger.info("💾 已保存到對話歷史")
                    except Exception as e:
                        logger.error(f"❌ 保存對話失敗: {e}")
                
                # 發送元數據
                metadata = {
                    'type': 'metadata',
                    'tokens_used': 0,
                    'source_documents': [str(doc.id) for doc in full_documents],
                    'processing_time': 0,
                }
                yield f"data: {json.dumps(metadata, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
                return
        
        # === 簡單事實查詢（不需要文檔搜索）===
        elif classification.intent == QuestionIntent.SIMPLE_FACTUAL:
            logger.info("→ 處理簡單事實查詢")
            response = await simple_factual_handler.handle(
                request, classification, db, user_id, None
            )
            
            if response.answer:
                yield f"data: {json.dumps({'type': 'complete', 'answer': response.answer}, ensure_ascii=False)}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'error', 'message': '處理失敗'}, ensure_ascii=False)}\n\n"
            return
        
        # === 未知意圖，回退到標準處理 ===
        else:
            logger.warning(f"未知意圖: {classification.intent}，使用標準流程")
            yield f"data: {json.dumps({'type': 'error', 'message': f'暫不支持的意圖類型: {classification.intent}'}, ensure_ascii=False)}\n\n"
            return
            
    except Exception as e:
        logger.error(f"❌ [Stream QA] 流式問答失敗: {e}", exc_info=True)
        error_msg = {
            'type': 'error',
            'message': f"流式問答失敗: {str(e)}"
        }
        yield f"data: {json.dumps(error_msg, ensure_ascii=False)}\n\n"


def requires_streaming(response) -> bool:
    """判斷是否需要流式輸出"""
    # 如果是寒暄、澄清等短回答，不需要流式
    if hasattr(response, 'classification') and response.classification:
        intent = response.classification.intent if hasattr(response.classification, 'intent') else ''
        if intent in ['greeting', 'chitchat', 'clarification_needed']:
            return False
    
    # 如果答案很短（<100字符），不需要流式
    if hasattr(response, 'answer') and response.answer and len(response.answer) < 100:
        return False
    
    return True


@router.post("/qa/stream")
async def stream_qa(
    request: AIQARequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    流式問答端點 - 實時發送每個處理步驟的進度
    
    返回 Server-Sent Events (SSE) 流
    
    事件類型：
    - progress: 處理進度（動態，只有實際執行的步驟才發送）
    - chunk: 答案文本塊
    - approval_needed: 需要用戶批准
    - complete: 完整答案（對於不需要流式的簡短回答）
    - metadata: 元數據信息
    - error: 錯誤信息
    """
    logger.info(f"📨 [Stream API] 收到流式問答請求: user={current_user.username}, question={request.question[:50]}")
    
    try:
        return StreamingResponse(
            generate_streaming_answer(db, request, str(current_user.id)),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # 禁用 Nginx 緩衝
            }
        )
    except Exception as e:
        logger.error(f"❌ [Stream API] 創建流式響應失敗: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"創建流式響應失敗: {str(e)}")
