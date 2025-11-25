"""
上下文評估測試腳本

專門用於評估電腦端 QA 流程中提供給 AI 的上下文內容
通過 monkey-patching 來攔截實際傳給 AI 的上下文
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
from app.services.vector.vector_db_service import vector_db_service
from app.models.vector_models import AIQARequest


def print_separator(title: str, char: str = "="):
    """打印分隔線"""
    print(f"\n{char * 80}")
    print(f"📊 {title}")
    print(f"{char * 80}")


# 全局變量用於捕獲上下文
captured_contexts = []


async def test_context_evaluation():
    """評估電腦端 QA 流程中提供給 AI 的上下文"""
    
    print("=" * 80)
    print("🔍 電腦端 QA 上下文評估")
    print("=" * 80)
    
    # 測試問題
    test_query = "幫我找所有的罰單"
    print(f"\n📝 測試問題: {test_query}")
    
    # 連接 MongoDB
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
        user_id = str(owner_id)
    elif isinstance(owner_id, bytes):
        user_id = str(uuid_module.UUID(bytes=owner_id))
    else:
        user_id = str(owner_id)
    
    print(f"👤 使用用戶 ID: {user_id}")
    
    # Monkey-patch unified_ai_service_simplified.generate_answer 來捕獲上下文
    from app.services.ai import unified_ai_service_simplified as ai_module
    original_generate_answer = ai_module.unified_ai_service_simplified.generate_answer
    
    async def patched_generate_answer(
        user_question,
        intent_analysis,
        document_context,
        db=None,
        **kwargs
    ):
        """攔截並記錄傳給 AI 的上下文"""
        captured_contexts.append({
            'user_question': user_question,
            'intent_analysis': intent_analysis,
            'document_context': document_context,
            'kwargs': kwargs
        })
        
        # 調用原始方法
        return await original_generate_answer(
            user_question=user_question,
            intent_analysis=intent_analysis,
            document_context=document_context,
            db=db,
            **kwargs
        )
    
    # 應用 patch
    ai_module.unified_ai_service_simplified.generate_answer = patched_generate_answer
    
    try:
        # 構建 QA 請求
        qa_request = AIQARequest(
            question=test_query,
            context_limit=5,
            use_semantic_search=True,
            model_preference=None,
            query_rewrite_count=3,
            similarity_threshold=0.3,
            workflow_action='approve_search'
        )
        
        print_separator("執行流式 QA 處理")
        
        # 導入並調用流式處理
        from app.services.qa_orchestrator import qa_orchestrator
        
        event_count = 0
        final_answer = ""
        
        async for event in qa_orchestrator.process_qa_request_intelligent_stream(
            db=db,
            request=qa_request,
            user_id=user_id,
            request_id="test_context_eval"
        ):
            event_count += 1
            if event.type == 'progress':
                print(f"   📍 {event.data.get('stage', '')}: {event.data.get('message', '')}")
            elif event.type == 'chunk':
                final_answer += event.data.get('text', '')
            elif event.type == 'complete':
                if event.data.get('answer'):
                    final_answer = event.data.get('answer')
        
        print(f"\n✅ 處理完成，共 {event_count} 個事件")
        
        # 分析捕獲的上下文
        print_separator("上下文評估結果")
        
        if not captured_contexts:
            print("❌ 未捕獲到任何上下文！")
        else:
            for i, ctx in enumerate(captured_contexts, 1):
                print(f"\n{'='*60}")
                print(f"📋 捕獲的上下文 #{i}")
                print(f"{'='*60}")
                
                print(f"\n📝 用戶問題: {ctx['user_question']}")
                print(f"\n💭 意圖分析: {ctx['intent_analysis'][:200]}..." if len(ctx['intent_analysis']) > 200 else f"\n💭 意圖分析: {ctx['intent_analysis']}")
                
                print(f"\n📄 文檔上下文數量: {len(ctx['document_context'])}")
                
                # 詳細分析每個上下文
                for j, doc_ctx in enumerate(ctx['document_context'], 1):
                    print(f"\n--- 上下文 {j} ---")
                    
                    # 檢查是否包含優化的 chunk 內容 (精簡格式)
                    if '引用編號: citation:' in doc_ctx and '摘要:' in doc_ctx and '內容:' in doc_ctx:
                        print(f"✅ 使用優化的精簡上下文")
                        
                        # 提取關鍵信息
                        lines = doc_ctx.split('\n')
                        for line in lines[:15]:  # 顯示前 15 行
                            print(f"   {line}")
                        if len(lines) > 15:
                            print(f"   ... (還有 {len(lines) - 15} 行)")
                    
                    elif '摘要:' in doc_ctx and '關鍵概念:' in doc_ctx:
                        print(f"⚠️ 使用舊的文檔摘要上下文")
                        print(f"   {doc_ctx[:400]}...")
                    
                    elif '對話歷史' in doc_ctx:
                        print(f"ℹ️ 對話歷史上下文")
                        print(f"   {doc_ctx[:200]}...")
                    
                    else:
                        print(f"📄 其他上下文類型")
                        print(f"   {doc_ctx[:400]}...")
        
        # 評估總結
        print_separator("評估總結", "!")
        
        if captured_contexts:
            ctx = captured_contexts[-1]  # 使用最後一個（答案生成的上下文）
            
            has_optimized_context = any(
                '引用編號: citation:' in doc_ctx and '摘要:' in doc_ctx and '內容:' in doc_ctx
                for doc_ctx in ctx['document_context']
            )
            
            has_old_summary = any(
                '摘要:' in doc_ctx and '關鍵概念:' in doc_ctx and '向量類型:' not in doc_ctx
                for doc_ctx in ctx['document_context']
            )
            
            if has_optimized_context:
                print("\n✅ 評估結果: 優化生效！")
                print("   - 使用了搜索結果的 chunk 內容 (方案 C)")
                print("   - AI 可以看到具體的違規事實、法條、金額等")
            elif has_old_summary:
                print("\n⚠️ 評估結果: 優化未生效！")
                print("   - 仍在使用舊的文檔摘要")
                print("   - 需要檢查 document_search_handler 的修改")
            else:
                print("\n❓ 評估結果: 無法確定")
                print("   - 上下文格式不符合預期")
        
        # 顯示最終答案
        if final_answer:
            print_separator("AI 生成的答案")
            print(final_answer[:1500] + "..." if len(final_answer) > 1500 else final_answer)
        
    finally:
        # 恢復原始方法
        ai_module.unified_ai_service_simplified.generate_answer = original_generate_answer
        client.close()
    
    print("\n" + "=" * 80)
    print("✅ 評估完成")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_context_evaluation())
