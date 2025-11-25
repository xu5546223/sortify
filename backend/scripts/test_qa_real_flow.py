"""
QA 真實流程測試腳本

測試問題: 幫我找所有的罰單
調用真實的 qa_orchestrator 流程，顯示每一步的實際結果
用於診斷目前系統的問題
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
from app.services.vector.vector_db_service import vector_db_service
from app.services.qa_orchestrator import qa_orchestrator
from app.models.vector_models import AIQARequest


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


async def test_qa_real_flow():
    """測試真實的 QA 流程"""
    
    print("=" * 80)
    print("🔍 QA 真實流程測試 (使用 qa_orchestrator)")
    print("=" * 80)
    
    # 測試問題
    test_query = "幫我找所有的罰單"
    print(f"\n📝 測試問題: {test_query}")
    print("-" * 80)
    
    # 連接 MongoDB (使用正確的 UUID 表示方式)
    client = AsyncIOMotorClient(
        settings.MONGODB_URL,
        uuidRepresentation='standard'
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
        user_id = owner_id
    elif isinstance(owner_id, bytes):
        user_id = uuid_module.UUID(bytes=owner_id)
    else:
        user_id = uuid_module.UUID(str(owner_id))
    
    print(f"👤 使用用戶 ID: {user_id}")
    
    # ========== 構建真實的 QA 請求 ==========
    print_separator("構建 QA 請求")
    
    qa_request = AIQARequest(
        question=test_query,
        context_limit=5,
        use_semantic_search=True,
        model_preference=None,
        query_rewrite_count=3,
        similarity_threshold=0.3
    )
    
    print(f"📋 請求參數:")
    print(f"   - question: {qa_request.question}")
    print(f"   - context_limit: {qa_request.context_limit}")
    print(f"   - query_rewrite_count: {qa_request.query_rewrite_count}")
    print(f"   - similarity_threshold: {qa_request.similarity_threshold}")
    
    # ========== 調用真實的 QA 流程 ==========
    print_separator("調用 qa_orchestrator.process_qa_request (真實流程)")
    
    print("\n🚀 開始執行真實 QA 流程...")
    print("📌 這會調用完整的: 查詢重寫 → 向量搜索 → 獲取文檔 → 生成答案")
    print("-" * 40)
    
    start_time = datetime.now()
    
    try:
        # 調用真實的 QA 流程
        response = await qa_orchestrator.process_qa_request(
            db=db,
            request=qa_request,
            user_id=user_id,
            request_id="test_real_flow_001"
        )
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        print(f"\n✅ QA 流程完成，耗時: {duration:.2f} 秒")
        
        # ========== 顯示查詢重寫結果 ==========
        print_separator("Step 1: 查詢重寫結果")
        
        if response.query_rewrite_result:
            qr = response.query_rewrite_result
            print(f"\n📋 原始查詢: {qr.original_query}")
            print(f"\n📋 重寫後的查詢:")
            for i, q in enumerate(qr.rewritten_queries or [], 1):
                print(f"   {i}. {q}")
            print(f"\n📋 意圖分析: {qr.intent_analysis}")
            print(f"📋 查詢粒度: {qr.query_granularity}")
            print(f"📋 建議搜索策略: {qr.search_strategy_suggestion}")
        else:
            print("⚠️ 無查詢重寫結果")
        
        # ========== 顯示向量搜索結果 ==========
        print_separator("Step 2: 向量搜索結果 (semantic_search_contexts)")
        
        if response.semantic_search_contexts:
            print(f"\n📄 搜索到 {len(response.semantic_search_contexts)} 個結果")
            
            for i, ctx in enumerate(response.semantic_search_contexts, 1):
                print(f"\n--- 搜索結果 {i} ---")
                print(f"📎 Document ID: {ctx.document_id}")
                print(f"📈 相似度: {ctx.similarity_score:.4f}")
                print(f"📝 summary_or_chunk_text (前 400 字):")
                text_preview = ctx.summary_or_chunk_text[:400] + "..." if len(ctx.summary_or_chunk_text) > 400 else ctx.summary_or_chunk_text
                for line in text_preview.split('\n')[:10]:
                    print(f"   {line}")
                if ctx.metadata:
                    print(f"🏷️ Metadata:")
                    for key in ['type', 'vectorization_strategy', 'chunk_summary']:
                        if ctx.metadata.get(key):
                            print(f"   - {key}: {ctx.metadata[key]}")
        else:
            print("⚠️ 無向量搜索結果")
        
        # ========== 顯示實際提供給 LLM 的上下文 ==========
        print_separator("Step 3: 實際提供給 LLM 的上下文 (llm_context_documents)")
        
        if response.llm_context_documents:
            print(f"\n📄 提供給 LLM 的上下文數量: {len(response.llm_context_documents)}")
            
            for i, ctx in enumerate(response.llm_context_documents, 1):
                print(f"\n--- LLM 上下文 {i} ---")
                print(f"📎 Document ID: {ctx.document_id}")
                print(f"📦 來源類型: {ctx.source_type}")
                print(f"📝 content_used (前 400 字):")
                text_preview = ctx.content_used[:400] + "..." if len(ctx.content_used) > 400 else ctx.content_used
                for line in text_preview.split('\n')[:10]:
                    print(f"   {line}")
        else:
            print("⚠️ 無 LLM 上下文文檔")
        
        # ========== 顯示 AI 生成的答案 ==========
        print_separator("Step 4: AI 生成的答案")
        
        print(f"\n📊 消耗 tokens: {response.tokens_used}")
        print(f"📊 信心分數: {response.confidence_score}")
        print(f"📊 處理時間: {response.processing_time:.2f} 秒")
        print(f"📊 來源文檔數: {len(response.source_documents)}")
        
        print(f"\n📝 AI 生成的答案:")
        print("=" * 60)
        print(response.answer)
        print("=" * 60)
        
        # ========== 問題診斷 ==========
        print_separator("問題診斷", "!")
        
        print("\n🔍 對比分析:")
        print("-" * 40)
        
        # 檢查搜索結果和 LLM 上下文的差異
        if response.semantic_search_contexts and response.llm_context_documents:
            search_content_sample = response.semantic_search_contexts[0].summary_or_chunk_text[:200] if response.semantic_search_contexts else ""
            llm_content_sample = response.llm_context_documents[0].content_used[:200] if response.llm_context_documents else ""
            
            print(f"\n📌 向量搜索返回的內容 (前 200 字):")
            print(f"   {search_content_sample}...")
            
            print(f"\n📌 實際提供給 LLM 的內容 (前 200 字):")
            print(f"   {llm_content_sample}...")
            
            # 檢查是否相同
            if search_content_sample != llm_content_sample:
                print(f"\n⚠️ 問題發現: 搜索結果和 LLM 上下文不一致！")
                print(f"   - 搜索結果包含具體的 chunk 內容")
                print(f"   - 但 LLM 收到的是文檔級摘要 (content_summary)")
                print(f"   - 這意味著搜索到的精確內容被丟棄了！")
            else:
                print(f"\n✅ 搜索結果和 LLM 上下文一致")
        
        # 檢查 source_type
        if response.llm_context_documents:
            source_types = [ctx.source_type for ctx in response.llm_context_documents]
            print(f"\n📌 LLM 上下文來源類型: {source_types}")
            
            if "ai_summary" in source_types:
                print(f"   ⚠️ 使用的是 'ai_summary' (文檔級摘要)")
                print(f"   ⚠️ 而不是搜索到的具體 chunk 內容")
        
    except Exception as e:
        print(f"\n❌ QA 流程失敗: {e}")
        import traceback
        traceback.print_exc()
    
    # 關閉連接
    client.close()
    
    print("\n" + "=" * 80)
    print("✅ 測試完成")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_qa_real_flow())
