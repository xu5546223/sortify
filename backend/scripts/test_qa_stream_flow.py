"""
QA 流式端點測試腳本 - 多輪對話上下文測試

測試目標：
1. 第一輪對話：問「幫我找所有的罰單」
2. 第二輪對話：問「第一張罰單的金額是多少」（測試上下文保留）
3. 第三輪對話：問「剛才那些罰單中，有沒有超速的？」（測試相關性衰減）
4. 第四輪對話：問「幫我找水費帳單」（測試新文檔加入 + 舊文檔衰減）

調用與電腦端完全相同的流式 API: qa_orchestrator.process_qa_request_intelligent_stream()
觀察多輪對話之間的上下文保留情況

上下文管理說明：
==================
1. 歷史對話 (messages): 保存問答對，用於 AI 理解對話脈絡
   - 最大保留 20 條消息（超過自動移除最舊的）
2. 文檔池 (cached_document_data): 保存文檔摘要，用於 AI 識別可用文檔
   - 最大保留 20 個文檔（超過按優先級移除）
   - 相關性會隨時間衰減（每輪未引用 -0.1）
   - 低相關性(<0.35) + 5輪未訪問的文檔會被清理
3. 上下文 ≠ 歷史對話：
   - 歷史對話：問題 + 答案
   - 上下文：歷史對話 + 文檔池 + 當前搜索結果
"""
import asyncio
import sys
import os
import json
from datetime import datetime
from uuid import UUID

# 添加項目路徑
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings
from app.services.vector.vector_db_service import vector_db_service
from app.services.qa_orchestrator import qa_orchestrator
from app.models.vector_models import AIQARequest
from app.crud import crud_conversations


def print_separator(title: str, char: str = "="):
    """打印分隔線"""
    print(f"\n{char * 80}")
    print(f"📊 {title}")
    print(f"{char * 80}")


async def get_conversation_state(db, conversation_id: str, user_uuid) -> dict:
    """獲取對話的完整狀態（歷史對話 + 文檔池）"""
    
    # 1. 獲取對話歷史
    conversation = await crud_conversations.get_conversation(
        db=db,
        conversation_id=UUID(conversation_id),
        user_id=user_uuid
    )
    
    message_count = len(conversation.messages) if conversation and conversation.messages else 0
    
    # 2. 獲取文檔池
    cached_doc_ids, cached_doc_data = await crud_conversations.get_cached_documents(
        db=db,
        conversation_id=UUID(conversation_id),
        user_id=user_uuid
    )
    
    doc_pool_size = len(cached_doc_data) if cached_doc_data else 0
    
    # 3. 收集文檔相關性信息
    doc_relevance_info = []
    if cached_doc_data:
        for doc_id, doc_info in cached_doc_data.items():
            if isinstance(doc_info, dict):
                doc_relevance_info.append({
                    'filename': doc_info.get('filename', 'Unknown')[:40],
                    'relevance_score': doc_info.get('relevance_score', 0),
                    'access_count': doc_info.get('access_count', 0),
                    'last_accessed_round': doc_info.get('last_accessed_round', 0),
                    'first_mentioned_round': doc_info.get('first_mentioned_round', 0)
                })
    
    return {
        'message_count': message_count,
        'doc_pool_size': doc_pool_size,
        'doc_relevance_info': doc_relevance_info
    }


async def run_single_qa_round(
    db,
    user_id: str,
    question: str,
    conversation_id: str,
    round_num: int,
    workflow_action: str = 'approve_search',
    simulate_real_flow: bool = True  # 是否模擬真實的兩階段流程
) -> dict:
    """執行單輪 QA 對話並返回結果"""
    
    print_separator(f"第 {round_num} 輪對話", "=")
    print(f"\n📝 問題: {question}")
    print(f"💬 對話 ID: {conversation_id}")
    print(f"🔧 預期批准動作: {workflow_action}")
    print(f"🔄 模擬真實流程: {simulate_real_flow}")
    print("-" * 80)
    
    start_time = datetime.now()
    event_count = 0
    final_answer = None
    llm_contexts = []
    document_pool = []
    cached_doc_ids = []
    
    try:
        # ========== 階段 1: 首次請求（不帶 workflow_action）==========
        if simulate_real_flow:
            print("\n   🔹 階段 1: 首次請求（等待批准）")
            
            qa_request_phase1 = AIQARequest(
                question=question,
                context_limit=5,
                use_semantic_search=True,
                model_preference=None,
                query_rewrite_count=3,
                similarity_threshold=0.3,
                workflow_action=None,  # 首次請求不帶 workflow_action
                conversation_id=conversation_id
            )
            
            approval_received = False
            approval_data = None
            
            async for event in qa_orchestrator.process_qa_request_intelligent_stream(
                db=db,
                request=qa_request_phase1,
                user_id=user_id,
                request_id=f"test_round_{round_num}_phase1"
            ):
                event_count += 1
                event_type = event.type
                event_data = event.data
                
                if event_type == 'progress':
                    stage = event_data.get('stage', '')
                    message = event_data.get('message', '')
                    print(f"   📍 [{stage}] {message}")
                
                elif event_type == 'approval_needed':
                    approval_received = True
                    approval_data = event_data
                    pending = event_data.get('pending_approval', '')
                    print(f"\n   ⏸️ 收到批准請求: {pending}")
                
                elif event_type == 'complete':
                    # 某些意圖（如 GREETING）不需要批准，直接完成
                    final_answer = event_data.get('answer', '')
                    print(f"\n   ✅ 直接完成（無需批准）: {len(final_answer)} 字")
                
                elif event_type == 'error':
                    print(f"   ❌ 錯誤: {event_data.get('message', '')}")
            
            # 如果收到批准請求，進入階段 2
            if approval_received:
                print(f"\n   🔹 階段 2: 批准請求（{workflow_action}）")
                await asyncio.sleep(0.1)  # 模擬用戶思考時間
            elif final_answer:
                # 已經完成，不需要階段 2
                end_time = datetime.now()
                duration = (end_time - start_time).total_seconds()
                print(f"\n⏱️ 耗時: {duration:.2f} 秒 | 事件數: {event_count}")
                return {
                    "answer": final_answer,
                    "llm_contexts": llm_contexts,
                    "document_pool": document_pool,
                    "cached_doc_ids": cached_doc_ids,
                    "duration": duration
                }
        
        # ========== 階段 2: 批准請求（帶 workflow_action）==========
        qa_request_phase2 = AIQARequest(
            question=question,
            context_limit=5,
            use_semantic_search=True,
            model_preference=None,
            query_rewrite_count=3,
            similarity_threshold=0.3,
            workflow_action=workflow_action,  # 帶上批准動作
            conversation_id=conversation_id
        )
        
        async for event in qa_orchestrator.process_qa_request_intelligent_stream(
            db=db,
            request=qa_request_phase2,
            user_id=user_id,
            request_id=f"test_round_{round_num}_phase2"
        ):
            event_count += 1
            event_type = event.type
            event_data = event.data
            
            if event_type == 'progress':
                stage = event_data.get('stage', '')
                message = event_data.get('message', '')
                print(f"   📍 [{stage}] {message}")
            
            elif event_type == 'chunk':
                # 流式輸出，不打印每個 chunk
                pass
            
            elif event_type == 'complete':
                final_answer = event_data.get('answer', '')
                print(f"\n   ✅ 收到完整答案 ({len(final_answer)} 字)")
            
            elif event_type == 'metadata':
                if 'llm_context_documents' in event_data:
                    llm_contexts = event_data['llm_context_documents']
                if 'document_pool' in event_data:
                    document_pool = event_data['document_pool']
                if 'cached_document_ids' in event_data:
                    cached_doc_ids = event_data['cached_document_ids']
            
            elif event_type == 'error':
                print(f"   ❌ 錯誤: {event_data.get('message', '')}")
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        print(f"\n⏱️ 耗時: {duration:.2f} 秒 | 事件數: {event_count}")
        
        return {
            "answer": final_answer,
            "llm_contexts": llm_contexts,
            "document_pool": document_pool,
            "cached_doc_ids": cached_doc_ids,
            "duration": duration
        }
        
    except Exception as e:
        print(f"\n❌ 處理失敗: {e}")
        import traceback
        traceback.print_exc()
        return None


async def test_qa_stream_flow():
    """測試多輪對話的上下文保留情況"""
    
    print("=" * 80)
    print("🔍 多輪對話上下文測試（四輪）")
    print("📌 測試目標：文檔池加載、上下文管理、文檔選用、相關性衰減")
    print("=" * 80)
    
    # 連接 MongoDB
    client = AsyncIOMotorClient(
        settings.MONGODB_URL,
        uuidRepresentation='standard'
    )
    db = client[settings.DB_NAME]
    
    # 初始化向量資料庫
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
        user_uuid = owner_id
    elif isinstance(owner_id, bytes):
        user_uuid = uuid_module.UUID(bytes=owner_id)
        user_id = str(user_uuid)
    else:
        user_uuid = uuid_module.UUID(str(owner_id))
        user_id = str(owner_id)
    
    print(f"\n👤 使用用戶 ID: {user_id}")
    
    # 載入配置
    from app.models.context_config import context_config
    
    # ========== 創建新對話 ==========
    print_separator("創建新對話")
    
    first_question = "幫我找所有的罰單"
    conversation = await crud_conversations.create_conversation(
        db=db,
        user_id=user_uuid,
        first_question=first_question
    )
    conversation_id = str(conversation.id)
    print(f"✅ 創建對話成功: {conversation_id}")
    
    # ========== 收集每輪數據 ==========
    round_data = []  # 收集每輪的狀態數據
    
    # 定義四輪對話
    # 注意：action 需要根據 AI 分類結果來設定
    # - approve_search: 用於 DOCUMENT_SEARCH 意圖
    # - approve_detail_query: 用於 DOCUMENT_DETAIL_QUERY 意圖
    rounds = [
        {"question": "幫我找所有的罰單", "action": "approve_search", "desc": "搜索罰單"},
        {"question": "第一張罰單的金額是多少", "action": "approve_detail_query", "desc": "查詢詳情"},
        {"question": "剛才那些罰單中，有沒有超速的？如果有，是哪一張？", "action": "approve_detail_query", "desc": "追問超速（詳細查詢）"},
        {"question": "幫我找水費帳單", "action": "approve_search", "desc": "搜索水費（新主題）"},
    ]
    
    # ========== 執行四輪對話 ==========
    for i, round_info in enumerate(rounds, 1):
        print_separator(f"第 {i} 輪對話 - {round_info['desc']}", "=" if i == 1 else "-")
        
        # 獲取對話前狀態
        state_before = await get_conversation_state(db, conversation_id, user_uuid)
        
        # 執行對話
        result = await run_single_qa_round(
            db=db,
            user_id=user_id,
            question=round_info['question'],
            conversation_id=conversation_id,
            round_num=i,
            workflow_action=round_info['action']
        )
        
        # 等待數據保存
        await asyncio.sleep(0.5)
        
        # 獲取對話後狀態
        state_after = await get_conversation_state(db, conversation_id, user_uuid)
        
        # 簡要顯示答案
        if result and result['answer']:
            print(f"\n📝 AI 答案（前 200 字）:")
            print(f"   {result['answer'][:200]}...")
        
        # 收集本輪數據
        round_data.append({
            'round': i,
            'question': round_info['question'],
            'desc': round_info['desc'],
            'state_before': state_before,
            'state_after': state_after,
            'answer': result['answer'] if result else None
        })
    
    # ========== 最終統一輸出 ==========
    print("\n")
    print("█" * 80)
    print("█" + " " * 30 + "📊 測試結果總覽" + " " * 31 + "█")
    print("█" * 80)
    
    # 1. 配置信息
    print(f"""
┌─────────────────────────────────────────────────────────────────────────────┐
│                              📋 上下文管理配置                               │
├─────────────────────────────────────────────────────────────────────────────┤
│  MAX_MESSAGES_PER_CONVERSATION: {context_config.MAX_MESSAGES_PER_CONVERSATION:<5}  │  最大歷史消息數              │
│  DEFAULT_HISTORY_LIMIT:         {context_config.DEFAULT_HISTORY_LIMIT:<5}  │  默認載入歷史數              │
│  MAX_DOCUMENT_POOL_SIZE:        {context_config.MAX_DOCUMENT_POOL_SIZE:<5}  │  文檔池最大大小              │
│  MIN_RELEVANCE_SCORE:           {context_config.MIN_RELEVANCE_SCORE:<5}  │  最低相關性閾值              │
│  MAX_IDLE_ROUNDS:               {context_config.MAX_IDLE_ROUNDS:<5}  │  最大閒置輪次                │
│  RELEVANCE_DECAY_RATE:          {context_config.RELEVANCE_DECAY_RATE:<5}  │  每輪衰減率                  │
└─────────────────────────────────────────────────────────────────────────────┘
""")
    
    # 2. 每輪對話狀態變化
    print("""
┌─────────────────────────────────────────────────────────────────────────────┐
│                           📈 每輪對話狀態變化                                │
├─────────────────────────────────────────────────────────────────────────────┤""")
    
    for rd in round_data:
        before = rd['state_before']
        after = rd['state_after']
        print(f"""
│  【第 {rd['round']} 輪】{rd['desc']:<20}                                      │
│  ├── 問題: {rd['question'][:50]:<50}│
│  ├── 消息數: {before['message_count']} → {after['message_count']}                                                   │
│  └── 文檔池: {before['doc_pool_size']} → {after['doc_pool_size']} 個文檔                                            │""")
    
    print("""└─────────────────────────────────────────────────────────────────────────────┘""")
    
    # 3. 最終文檔池狀態（相關性詳情）
    final_state = round_data[-1]['state_after']
    print("""
┌─────────────────────────────────────────────────────────────────────────────┐
│                         📁 最終文檔池狀態（相關性詳情）                       │
├─────────────────────────────────────────────────────────────────────────────┤
│  文件名                              │ 相關性 │ 訪問次數 │ 首次輪次 │ 最後輪次│
├──────────────────────────────────────┼────────┼──────────┼──────────┼─────────┤""")
    
    for doc in final_state['doc_relevance_info']:
        filename = doc['filename'][:36].ljust(36)
        relevance = f"{doc['relevance_score']:.2f}".center(6)
        access = str(doc['access_count']).center(8)
        first_round = str(doc['first_mentioned_round']).center(8)
        last_round = str(doc['last_accessed_round']).center(7)
        print(f"│  {filename} │ {relevance} │ {access} │ {first_round} │ {last_round} │")
    
    print("""└──────────────────────────────────────┴────────┴──────────┴──────────┴─────────┘""")
    
    # 4. 驗證結果
    final_msg_count = final_state['message_count']
    final_doc_count = final_state['doc_pool_size']
    
    # 檢查是否有衰減發生
    has_decay = any(doc['relevance_score'] < 1.0 for doc in final_state['doc_relevance_info'])
    
    print(f"""
┌─────────────────────────────────────────────────────────────────────────────┐
│                              ✅ 驗證結果                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1️⃣  歷史對話管理                                                           │
│      ├── 當前消息數: {final_msg_count}                                                     │
│      ├── 最大限制: {context_config.MAX_MESSAGES_PER_CONVERSATION}                                                      │
│      └── 狀態: {'✓ 正常' if final_msg_count <= context_config.MAX_MESSAGES_PER_CONVERSATION else '⚠️ 超出限制'}                                                      │
│                                                                             │
│  2️⃣  文檔池管理                                                             │
│      ├── 當前文檔數: {final_doc_count}                                                     │
│      ├── 最大限制: {context_config.MAX_DOCUMENT_POOL_SIZE}                                                      │
│      └── 狀態: {'✓ 正常' if final_doc_count <= context_config.MAX_DOCUMENT_POOL_SIZE else '⚠️ 超出限制'}                                                      │
│                                                                             │
│  3️⃣  相關性衰減                                                             │
│      └── 狀態: {'✓ 有文檔發生衰減' if has_decay else '⚠️ 未觀察到衰減（可能都被引用）'}                                     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
""")
    
    # 5. 機制說明
    print("""
┌─────────────────────────────────────────────────────────────────────────────┐
│                        多輪對話上下文管理機制                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  【會保留到下一輪的數據】                                                    │
│  ├── 歷史對話 (messages)                                                    │
│  │   • 問題 + 答案，讓 AI 理解對話脈絡                                      │
│  │   • ⚡ 最大保留 20 條（超過自動移除最舊的）                               │
│  │                                                                          │
│  └── 文檔池 (cached_document_data)                                          │
│      • 文檔 ID + 文件名 + 摘要 + 相關性分數                                 │
│      • ⚡ 最大保留 20 個（超過按優先級移除）                                 │
│      • ⚡ 未被引用的文檔每輪衰減 0.1                                         │
│      • ⚡ 相關性 < 0.35 且 5 輪未訪問 → 自動清理                             │
│                                                                             │
│  【優先級計算】                                                              │
│  priority = relevance_score × 0.7 + recency_score × 0.3                     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
""")
    
    # 關閉連接
    client.close()
    
    print("\n" + "=" * 80)
    print("✅ 四輪對話測試完成")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_qa_stream_flow())
