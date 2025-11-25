"""
QA 完整 API 流程測試腳本

測試問題: 幫我找所有的罰單
調用真實 API 端點，顯示每一步的結果
"""
import asyncio
import sys
import os
import json
from datetime import datetime
from typing import Optional

# 添加項目路徑
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings
from app.services.vector.embedding_service import embedding_service
from app.services.vector.vector_db_service import vector_db_service
from app.services.vector.enhanced_search_service import enhanced_search_service
from app.services.qa_core.qa_query_rewriter import QAQueryRewriter
from app.services.qa_core.qa_search_coordinator import QASearchCoordinator
from app.services.qa_core.qa_answer_service import QAAnswerService
from app.models.vector_models import AIQARequest, QueryRewriteResult


def print_separator(title: str, char: str = "="):
    """打印分隔線"""
    print(f"\n{char * 80}")
    print(f"📊 {title}")
    print(f"{char * 80}")


def print_json(data, indent: int = 2):
    """格式化打印 JSON"""
    if hasattr(data, 'model_dump'):
        data = data.model_dump()
    elif hasattr(data, '__dict__'):
        data = data.__dict__
    print(json.dumps(data, ensure_ascii=False, indent=indent, default=str))


async def test_qa_full_flow():
    """測試完整的 QA 流程"""
    
    print("=" * 80)
    print("🔍 QA 完整 API 流程測試")
    print("=" * 80)
    
    # 測試問題
    test_query = "幫我找所有的罰單"
    print(f"\n📝 測試問題: {test_query}")
    print("-" * 80)
    
    # 連接 MongoDB (使用正確的 UUID 表示方式)
    client = AsyncIOMotorClient(
        settings.MONGODB_URL,
        uuidRepresentation='standard'  # 重要：與應用程式保持一致
    )
    db = client[settings.DB_NAME]
    
    # 初始化向量資料庫集合
    vector_db_service.create_collection(768)
    
    # 獲取測試用戶
    import uuid as uuid_module
    sample_doc = await db.documents.find_one({})
    if not sample_doc:
        print("❌ 資料庫中沒有文檔")
        return
    
    owner_id = sample_doc.get("owner_id")
    if isinstance(owner_id, uuid_module.UUID):
        user_id = str(owner_id)
    elif isinstance(owner_id, bytes):
        user_id = str(uuid_module.UUID(bytes=owner_id))
    else:
        user_id = str(owner_id)
    print(f"👤 使用用戶 ID: {user_id}")
    
    # 初始化服務
    query_rewriter = QAQueryRewriter()
    search_coordinator = QASearchCoordinator()
    answer_service = QAAnswerService()
    
    total_tokens = 0
    
    # ========== Step 1: 查詢重寫 ==========
    print_separator("Step 1: 查詢重寫 (Query Rewrite)")
    
    query_rewrite_result, rewrite_tokens = await query_rewriter.rewrite_query(
        db=db,
        original_query=test_query,
        user_id=user_id,
        request_id="test_request_001",
        query_rewrite_count=3
    )
    total_tokens += rewrite_tokens
    
    print(f"\n✅ 查詢重寫完成，消耗 {rewrite_tokens} tokens")
    print(f"\n📋 原始查詢: {query_rewrite_result.original_query}")
    print(f"\n📋 重寫後的查詢:")
    for i, q in enumerate(query_rewrite_result.rewritten_queries, 1):
        print(f"   {i}. {q}")
    print(f"\n📋 意圖分析: {query_rewrite_result.intent_analysis}")
    print(f"\n📋 查詢粒度: {query_rewrite_result.query_granularity}")
    print(f"\n📋 建議搜索策略: {query_rewrite_result.search_strategy_suggestion}")
    print(f"\n📋 提取的參數:")
    print_json(query_rewrite_result.extracted_parameters)
    
    # ========== Step 2: 決定搜索策略 ==========
    print_separator("Step 2: 決定搜索策略")
    
    from app.services.qa_orchestrator import extract_search_strategy
    search_strategy = extract_search_strategy(query_rewrite_result)
    print(f"\n🎯 選擇的搜索策略: {search_strategy}")
    
    # ========== Step 3: 執行向量搜索 ==========
    print_separator("Step 3: 執行向量搜索")
    
    queries = query_rewrite_result.rewritten_queries if query_rewrite_result.rewritten_queries else [test_query]
    
    search_results = await search_coordinator.unified_search(
        db=db,
        queries=queries,
        user_id=user_id,
        search_strategy=search_strategy,
        top_k=5,
        similarity_threshold=0.3,
        enable_diversity_optimization=True
    )
    
    print(f"\n✅ 搜索完成，找到 {len(search_results)} 個結果")
    
    for i, result in enumerate(search_results, 1):
        print(f"\n--- 搜索結果 {i} ---")
        print(f"📎 Document ID: {result.document_id}")
        print(f"📈 相似度/RRF分數: {result.similarity_score:.4f}")
        print(f"📍 行號範圍: {result.start_line} - {result.end_line}")
        print(f"📦 Chunk 類型: {result.chunk_type}")
        print(f"📝 summary_text (前 400 字):")
        text_preview = result.summary_text[:400] + "..." if len(result.summary_text) > 400 else result.summary_text
        # 縮進顯示
        for line in text_preview.split('\n'):
            print(f"   {line}")
        
        # 顯示重要 metadata
        if result.metadata:
            print(f"🏷️ 關鍵 Metadata:")
            for key in ['type', 'vectorization_strategy', 'chunk_summary', 'search_strategy']:
                if result.metadata.get(key):
                    print(f"   - {key}: {result.metadata[key]}")
    
    # ========== Step 4: 獲取完整文檔 ==========
    print_separator("Step 4: 獲取完整文檔")
    
    documents = []
    if search_results:
        from app.crud.crud_documents import get_documents_by_ids
        document_ids = [result.document_id for result in search_results]
        
        try:
            documents = await get_documents_by_ids(db, document_ids)
            print(f"\n✅ 獲取到 {len(documents)} 個完整文檔")
            
            for i, doc in enumerate(documents, 1):
                print(f"\n--- 文檔 {i} ---")
                print(f"📎 ID: {doc.id}")
                print(f"📁 文件名: {doc.filename}")
                print(f"📂 文件類型: {doc.file_type}")
                
                # 獲取 AI 分析的摘要
                ai_summary = None
                if hasattr(doc, 'analysis') and doc.analysis:
                    if hasattr(doc.analysis, 'ai_analysis_output') and isinstance(doc.analysis.ai_analysis_output, dict):
                        key_info = doc.analysis.ai_analysis_output.get("key_information", {})
                        if isinstance(key_info, dict):
                            ai_summary = key_info.get("content_summary", "")
                
                print(f"📝 AI 摘要 (content_summary):")
                if ai_summary:
                    preview = ai_summary[:300] + "..." if len(ai_summary) > 300 else ai_summary
                    for line in preview.split('\n'):
                        print(f"   {line}")
                else:
                    print(f"   (無)")
        except Exception as e:
            print(f"⚠️ 獲取文檔失敗: {e}")
            documents = []
    
    # ========== Step 5: 使用搜索結果直接生成答案 (優化方案) ==========
    print_separator("Step 5: 使用搜索結果直接生成 AI 答案 (優化方案)")
    
    if search_results:
        print("\n🤖 正在使用搜索結果的 summary_text 直接生成答案...")
        print("📌 這是優化方案：直接使用向量搜索返回的 chunk 內容，不依賴 MongoDB 文檔")
        
        # 構建上下文 - 直接使用搜索結果的 summary_text
        context_parts = []
        for i, result in enumerate(search_results[:5], 1):
            chunk_type = result.metadata.get('type', 'unknown') if result.metadata else 'unknown'
            strategy = result.metadata.get('vectorization_strategy', '') if result.metadata else ''
            chunk_summary = result.metadata.get('chunk_summary', '') if result.metadata else ''
            
            context = f"""=== 文檔 {i}（引用編號: citation:{i}）===
Document ID: {result.document_id}
相似度分數: {result.similarity_score:.4f}
向量類型: {chunk_type}
向量化策略: {strategy}
行號範圍: {result.start_line or 'N/A'} - {result.end_line or 'N/A'}
Chunk 摘要: {chunk_summary}

內容:
{result.summary_text}
"""
            context_parts.append(context)
        
        # 顯示將要傳給 AI 的上下文
        print(f"\n📋 將傳給 AI 的上下文 ({len(context_parts)} 個):")
        print("-" * 40)
        for ctx in context_parts:
            print(ctx[:500] + "..." if len(ctx) > 500 else ctx)
            print("-" * 40)
        
        # 調用 AI 生成答案
        from app.services.ai.unified_ai_service_simplified import unified_ai_service_simplified
        
        ai_response = await unified_ai_service_simplified.generate_answer(
            user_question=test_query,
            intent_analysis=query_rewrite_result.intent_analysis or "",
            document_context=context_parts,
            db=db,
            model_preference=None
        )
        
        if ai_response.success and ai_response.output_data:
            answer_tokens = ai_response.token_usage.total_tokens if ai_response.token_usage else 0
            total_tokens += answer_tokens
            
            answer_text = ai_response.output_data.answer_text if hasattr(ai_response.output_data, 'answer_text') else str(ai_response.output_data)
            
            print(f"\n✅ AI 答案生成完成")
            print(f"📊 消耗 tokens: {answer_tokens}")
            print(f"📊 使用模型: {ai_response.model_used}")
            print(f"\n📝 AI 生成的答案:")
            print("=" * 60)
            print(answer_text)
            print("=" * 60)
        else:
            print(f"\n❌ AI 答案生成失敗: {ai_response.error_message}")
    else:
        print("\n⚠️ 沒有搜索結果可用於生成答案")
    
    # ========== 總結 ==========
    print_separator("總結", "=")
    
    print(f"\n📊 總消耗 tokens: {total_tokens}")
    print(f"\n⚠️ 關鍵發現:")
    print("-" * 40)
    print("1. 向量搜索返回的 summary_text 包含:")
    print("   - 摘要向量: 文件名+摘要+關鍵詞的組合")
    print("   - Chunk 向量: [Summary]+[Content] 混合內容 或 原始文本")
    print("")
    print("2. 目前 QA 流程:")
    print("   - 搜索結果的 summary_text 被丟棄")
    print("   - 重新從 MongoDB 獲取文檔")
    print("   - 使用文檔級的 content_summary 作為上下文")
    print("")
    print("3. 優化建議:")
    print("   - 將搜索到的 chunk 內容直接傳給 AI")
    print("   - 利用行號資訊提供精確引用")
    
    # 關閉連接
    client.close()
    
    print("\n" + "=" * 80)
    print("✅ 測試完成")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_qa_full_flow())
