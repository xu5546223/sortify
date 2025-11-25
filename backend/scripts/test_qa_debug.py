"""
QA 流程調試腳本

測試問題: 幫我找所有的罰單
顯示完整的搜索流程和 AI 原始結果
"""
import asyncio
import sys
import os
import json
from datetime import datetime

# 添加項目路徑
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings
from app.services.vector.embedding_service import embedding_service
from app.services.vector.vector_db_service import vector_db_service
from app.services.vector.enhanced_search_service import enhanced_search_service


async def test_vector_search_debug():
    """測試向量搜索並顯示詳細結果"""
    
    print("=" * 80)
    print("🔍 QA 流程調試測試")
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
    vector_db_service.create_collection(768)  # 768 維度 for multilingual-e5-base
    
    # 獲取一個測試用戶 ID (從資料庫中獲取第一個用戶)
    sample_doc = await db.documents.find_one({})
    if not sample_doc:
        print("❌ 資料庫中沒有文檔")
        return
    
    # 正確轉換 UUID
    import uuid as uuid_module
    owner_id = sample_doc.get("owner_id")
    if isinstance(owner_id, uuid_module.UUID):
        user_id = str(owner_id)
    elif isinstance(owner_id, bytes):
        user_id = str(uuid_module.UUID(bytes=owner_id))
    else:
        user_id = str(owner_id)
    print(f"👤 使用用戶 ID: {user_id}")
    
    # ========== Step 1: 向量化查詢 ==========
    print("\n" + "=" * 80)
    print("📊 Step 1: 向量化查詢")
    print("=" * 80)
    
    query_vector = embedding_service.encode_text(test_query)
    print(f"✅ 查詢向量維度: {len(query_vector)}")
    
    # ========== Step 2: 執行向量搜索 (傳統單階段) ==========
    print("\n" + "=" * 80)
    print("📊 Step 2: 傳統單階段搜索 (摘要 + chunk)")
    print("=" * 80)
    
    # 搜索摘要向量
    summary_results = vector_db_service.search_similar_vectors(
        query_vector=query_vector,
        top_k=5,
        owner_id_filter=user_id,
        similarity_threshold=0.3,
        metadata_filter={"type": "summary"}
    )
    
    print(f"\n📄 摘要向量搜索結果: {len(summary_results)} 個")
    for i, result in enumerate(summary_results, 1):
        print(f"\n  --- 摘要結果 {i} ---")
        print(f"  📎 Document ID: {result.document_id}")
        print(f"  📈 相似度: {result.similarity_score:.4f}")
        print(f"  📝 summary_text (前 300 字):")
        print(f"     {result.summary_text[:300]}..." if len(result.summary_text) > 300 else f"     {result.summary_text}")
        print(f"  🏷️ Metadata:")
        for key, value in (result.metadata or {}).items():
            if value:
                print(f"     - {key}: {value}")
    
    # 搜索 chunk 向量
    chunk_results = vector_db_service.search_similar_vectors(
        query_vector=query_vector,
        top_k=5,
        owner_id_filter=user_id,
        similarity_threshold=0.3,
        metadata_filter={"type": "chunk"}
    )
    
    print(f"\n📄 Chunk 向量搜索結果: {len(chunk_results)} 個")
    for i, result in enumerate(chunk_results, 1):
        print(f"\n  --- Chunk 結果 {i} ---")
        print(f"  📎 Document ID: {result.document_id}")
        print(f"  📈 相似度: {result.similarity_score:.4f}")
        print(f"  📍 行號範圍: {result.start_line} - {result.end_line}")
        print(f"  📦 Chunk 類型: {result.chunk_type}")
        print(f"  📝 summary_text (chunk_text, 前 500 字):")
        text_preview = result.summary_text[:500] + "..." if len(result.summary_text) > 500 else result.summary_text
        print(f"     {text_preview}")
        print(f"  🏷️ Metadata:")
        for key, value in (result.metadata or {}).items():
            if value:
                print(f"     - {key}: {value}")
    
    # ========== Step 3: 執行 RRF 融合搜索 ==========
    print("\n" + "=" * 80)
    print("📊 Step 3: RRF 融合搜索")
    print("=" * 80)
    
    rrf_results = await enhanced_search_service.two_stage_hybrid_search(
        db=db,
        query=test_query,
        user_id=user_id,
        search_type="rrf_fusion",
        stage2_top_k=5,
        similarity_threshold=0.3
    )
    
    print(f"\n📄 RRF 融合搜索結果: {len(rrf_results)} 個")
    for i, result in enumerate(rrf_results, 1):
        print(f"\n  --- RRF 結果 {i} ---")
        print(f"  📎 Document ID: {result.document_id}")
        print(f"  📈 RRF 分數: {result.similarity_score:.4f}")
        print(f"  📍 行號範圍: {result.start_line} - {result.end_line}")
        print(f"  📦 Chunk 類型: {result.chunk_type}")
        print(f"  📝 summary_text (前 500 字):")
        text_preview = result.summary_text[:500] + "..." if len(result.summary_text) > 500 else result.summary_text
        print(f"     {text_preview}")
        
        # 顯示 RRF 詳細信息
        if result.metadata and result.metadata.get("rrf_details"):
            rrf_details = result.metadata.get("rrf_details", {})
            print(f"  🎯 RRF 詳情:")
            print(f"     - 最終 RRF 分數: {rrf_details.get('final_rrf_score', 'N/A')}")
            for comp in rrf_details.get("components", []):
                print(f"     - {comp.get('type', 'unknown')}: rank={comp.get('rank', 'N/A')}, contribution={comp.get('contribution', 'N/A'):.4f}")
    
    # ========== Step 4: 獲取完整文檔 (模擬 QA 流程) ==========
    print("\n" + "=" * 80)
    print("📊 Step 4: 獲取完整文檔 (模擬 QA 流程)")
    print("=" * 80)
    
    if rrf_results:
        from app.crud.crud_documents import get_documents_by_ids
        document_ids = [result.document_id for result in rrf_results]
        documents = await get_documents_by_ids(db, document_ids)
        
        print(f"\n📄 獲取到 {len(documents)} 個完整文檔")
        for i, doc in enumerate(documents, 1):
            print(f"\n  --- 文檔 {i} ---")
            print(f"  📎 ID: {doc.id}")
            print(f"  📁 文件名: {doc.filename}")
            print(f"  📂 文件類型: {doc.file_type}")
            
            # 獲取 AI 分析的摘要 (這是目前 QA 流程使用的)
            ai_summary = None
            if hasattr(doc, 'analysis') and doc.analysis:
                if hasattr(doc.analysis, 'ai_analysis_output') and isinstance(doc.analysis.ai_analysis_output, dict):
                    key_info = doc.analysis.ai_analysis_output.get("key_information", {})
                    if isinstance(key_info, dict):
                        ai_summary = key_info.get("content_summary", "")
            
            print(f"  📝 AI 摘要 (content_summary, 目前 QA 使用的):")
            if ai_summary:
                preview = ai_summary[:300] + "..." if len(ai_summary) > 300 else ai_summary
                print(f"     {preview}")
            else:
                print(f"     (無)")
    
    # ========== Step 5: 對比分析 ==========
    print("\n" + "=" * 80)
    print("📊 Step 5: 對比分析 - 搜索結果 vs 目前 QA 使用的內容")
    print("=" * 80)
    
    print("\n⚠️ 關鍵發現:")
    print("-" * 40)
    print("1. 向量搜索返回的 summary_text 包含:")
    print("   - 對於摘要向量: 文件名+摘要+關鍵詞的組合")
    print("   - 對於 chunk 向量: 原始文本塊 或 [Summary]+[Content] 混合內容")
    print("")
    print("2. 目前 QA 流程:")
    print("   - 丟棄了搜索返回的 summary_text (chunk 內容)")
    print("   - 重新從 MongoDB 獲取文檔")
    print("   - 使用文檔級的 content_summary")
    print("")
    print("3. 建議優化:")
    print("   - 將搜索到的 chunk 內容傳遞給 AI")
    print("   - 利用行號資訊 (start_line, end_line) 提供精確引用")
    
    # 關閉連接
    client.close()
    
    print("\n" + "=" * 80)
    print("✅ 測試完成")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_vector_search_debug())
