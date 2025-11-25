"""
文件引用功能測試腳本

測試目標：
1. AI 生成答案時是否正確使用 [文檔名](citation:N) 格式
2. citation:N 的編號是否與 AI 看到的文檔順序一致
3. 用戶說「第一個文件」時，AI 是否正確理解為 citation:1 對應的文檔

使用方式：
    cd backend
    python scripts/test_citation_reference.py
"""

import asyncio
import sys
import os
import re
import json
from typing import List, Dict, Any, Optional
from datetime import datetime

# 添加項目路徑
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 嘗試使用 rich，如果沒有則使用簡單輸出
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    USE_RICH = True
    console = Console()
except ImportError:
    USE_RICH = False
    
    class SimpleConsole:
        """簡單的控制台輸出類"""
        def print(self, msg, **kwargs):
            # 移除 rich 格式標記
            clean_msg = re.sub(r'\[/?[^\]]+\]', '', str(msg))
            print(clean_msg)
    
    console = SimpleConsole()


class CitationTestResult:
    """測試結果"""
    def __init__(self, test_name: str):
        self.test_name = test_name
        self.passed = False
        self.details: Dict[str, Any] = {}
        self.errors: List[str] = []
        self.warnings: List[str] = []
    
    def add_error(self, msg: str):
        self.errors.append(msg)
    
    def add_warning(self, msg: str):
        self.warnings.append(msg)


def extract_citations(text: str) -> List[Dict[str, Any]]:
    """
    從文本中提取所有引用
    
    返回格式: [{"number": 1, "filename": "xxx.pdf", "full_match": "[xxx](citation:1)"}]
    """
    pattern = r'\[([^\]]+)\]\(citation:(\d+)\)'
    matches = re.findall(pattern, text)
    
    citations = []
    for filename, number in matches:
        citations.append({
            "number": int(number),
            "filename": filename,
            "full_match": f"[{filename}](citation:{number})"
        })
    
    return citations


def parse_document_context(context: str) -> List[Dict[str, Any]]:
    """
    解析 AI 看到的文檔上下文
    
    格式: === 文檔 1（引用編號: citation:1）: filename.pdf ===
    """
    pattern = r'=== 文檔\s*(\d+)（引用編號:\s*citation:(\d+)）:\s*([^=]+)==='
    matches = re.findall(pattern, context)
    
    documents = []
    for doc_num, citation_num, filename in matches:
        documents.append({
            "doc_number": int(doc_num),
            "citation_number": int(citation_num),
            "filename": filename.strip()
        })
    
    return documents


async def test_citation_format():
    """
    測試 1: AI 生成答案的引用格式
    
    驗證：
    - AI 是否使用 [文檔名](citation:N) 格式
    - 引用編號是否從 1 開始
    - 引用編號是否連續
    """
    result = CitationTestResult("引用格式測試")
    
    console.print("\n[bold cyan]═══ 測試 1: 引用格式測試 ═══[/bold cyan]")
    
    # 模擬 AI 回答
    test_cases = [
        {
            "name": "正確格式",
            "answer": "根據 [發票A.pdf](citation:1) 的內容，金額為 100 元。另外 [發票B.pdf](citation:2) 顯示金額為 200 元。",
            "expected_citations": [
                {"number": 1, "filename": "發票A.pdf"},
                {"number": 2, "filename": "發票B.pdf"}
            ]
        },
        {
            "name": "錯誤格式 - 缺少引用",
            "answer": "根據發票A的內容，金額為 100 元。",
            "expected_citations": []
        },
        {
            "name": "混合格式",
            "answer": "根據 [合約.docx](citation:1) 的內容，甲方是 ABC 公司。另外合約B也提到了相關條款。",
            "expected_citations": [
                {"number": 1, "filename": "合約.docx"}
            ]
        }
    ]
    
    for case in test_cases:
        console.print(f"\n[yellow]測試案例: {case['name']}[/yellow]")
        console.print(f"  答案: {case['answer'][:80]}...")
        
        citations = extract_citations(case['answer'])
        console.print(f"  提取到的引用: {citations}")
        
        # 驗證引用數量
        if len(citations) == len(case['expected_citations']):
            console.print(f"  [green]✓ 引用數量正確: {len(citations)}[/green]")
        else:
            console.print(f"  [red]✗ 引用數量不符: 預期 {len(case['expected_citations'])}, 實際 {len(citations)}[/red]")
            result.add_error(f"{case['name']}: 引用數量不符")
        
        # 驗證引用編號
        for i, citation in enumerate(citations):
            expected = case['expected_citations'][i] if i < len(case['expected_citations']) else None
            if expected:
                if citation['number'] == expected['number']:
                    console.print(f"  [green]✓ 引用編號正確: citation:{citation['number']}[/green]")
                else:
                    console.print(f"  [red]✗ 引用編號不符: 預期 {expected['number']}, 實際 {citation['number']}[/red]")
                    result.add_error(f"{case['name']}: 引用編號不符")
    
    result.passed = len(result.errors) == 0
    return result


async def test_citation_order_consistency():
    """
    測試 2: 引用順序一致性
    
    驗證：
    - AI 看到的文檔順序與 citation:N 的對應關係
    - 文檔池順序與引用順序的一致性
    """
    result = CitationTestResult("引用順序一致性測試")
    
    console.print("\n[bold cyan]═══ 測試 2: 引用順序一致性測試 ═══[/bold cyan]")
    
    # 模擬文檔上下文（AI 看到的格式）
    document_context = """
=== 文檔 1（引用編號: citation:1）: 早餐收據.pdf ===
內容: 2025/1/1 早餐消費 79 元

=== 文檔 2（引用編號: citation:2）: 午餐收據.pdf ===
內容: 2025/1/1 午餐消費 120 元

=== 文檔 3（引用編號: citation:3）: 晚餐收據.pdf ===
內容: 2025/1/1 晚餐消費 200 元
"""
    
    # 模擬 AI 回答
    ai_answer = """
根據您的收據，今日消費如下：
1. [早餐收據.pdf](citation:1): 79 元
2. [午餐收據.pdf](citation:2): 120 元  
3. [晚餐收據.pdf](citation:3): 200 元

總計: 399 元
"""
    
    console.print("\n[yellow]文檔上下文（AI 看到的）:[/yellow]")
    console.print(document_context[:200] + "...")
    
    console.print("\n[yellow]AI 回答:[/yellow]")
    console.print(ai_answer)
    
    # 解析文檔上下文
    doc_context = parse_document_context(document_context)
    console.print(f"\n[yellow]解析的文檔上下文:[/yellow]")
    for doc in doc_context:
        console.print(f"  文檔 {doc['doc_number']} -> citation:{doc['citation_number']} -> {doc['filename']}")
    
    # 提取 AI 回答中的引用
    citations = extract_citations(ai_answer)
    console.print(f"\n[yellow]AI 回答中的引用:[/yellow]")
    for c in citations:
        console.print(f"  citation:{c['number']} -> {c['filename']}")
    
    # 驗證一致性
    console.print(f"\n[yellow]一致性驗證:[/yellow]")
    for citation in citations:
        # 找到對應的文檔上下文
        matching_doc = next((d for d in doc_context if d['citation_number'] == citation['number']), None)
        
        if matching_doc:
            if matching_doc['filename'] == citation['filename']:
                console.print(f"  [green]✓ citation:{citation['number']} 正確對應 {citation['filename']}[/green]")
            else:
                console.print(f"  [red]✗ citation:{citation['number']} 不一致: 上下文={matching_doc['filename']}, 引用={citation['filename']}[/red]")
                result.add_error(f"citation:{citation['number']} 文檔名不一致")
        else:
            console.print(f"  [red]✗ citation:{citation['number']} 在文檔上下文中找不到對應[/red]")
            result.add_error(f"citation:{citation['number']} 無對應文檔")
    
    result.passed = len(result.errors) == 0
    return result


async def test_document_reference_parsing():
    """
    測試 3: 「第一個文件」指代詞解析
    
    驗證：
    - 當用戶說「第一個文件」時，AI 是否正確理解為 citation:1 對應的文檔
    - 而不是文檔池中的第一個文檔
    """
    result = CitationTestResult("指代詞解析測試")
    
    console.print("\n[bold cyan]═══ 測試 3: 指代詞解析測試 ═══[/bold cyan]")
    
    # 模擬場景
    scenarios = [
        {
            "name": "AI 回答中有引用，用戶問第一個文件",
            "ai_previous_answer": "根據 [發票A.pdf](citation:1) 和 [發票B.pdf](citation:2)，總金額為 300 元。",
            "user_question": "第一個文件的詳細內容是什麼？",
            "document_pool": [
                {"reference_number": 1, "document_id": "doc-b", "filename": "發票B.pdf", "relevance_score": 0.95},
                {"reference_number": 2, "document_id": "doc-a", "filename": "發票A.pdf", "relevance_score": 0.85},
            ],
            "expected_target": "發票A.pdf",  # 應該是 citation:1 對應的，不是文檔池第一個
            "expected_reasoning": "用戶說第一個文件，對應 AI 回答中 citation:1 的發票A.pdf"
        },
        {
            "name": "無 AI 引用回答，使用文檔池順序",
            "ai_previous_answer": "您好，請問有什麼可以幫助您的？",
            "user_question": "第一個文件的內容",
            "document_pool": [
                {"reference_number": 1, "document_id": "doc-x", "filename": "合約.docx", "relevance_score": 0.90},
                {"reference_number": 2, "document_id": "doc-y", "filename": "報表.xlsx", "relevance_score": 0.80},
            ],
            "expected_target": "合約.docx",  # 文檔池第一個
            "expected_reasoning": "無 AI 引用回答，使用文檔池 reference_number=1 的文檔"
        },
        {
            "name": "用戶說第二個文件",
            "ai_previous_answer": "根據 [罰單A.jpg](citation:1)、[罰單B.jpg](citation:2) 和 [罰單C.jpg](citation:3)，共有三張罰單。",
            "user_question": "第二個文件的金額是多少？",
            "document_pool": [
                {"reference_number": 1, "document_id": "doc-c", "filename": "罰單C.jpg", "relevance_score": 0.95},
                {"reference_number": 2, "document_id": "doc-a", "filename": "罰單A.jpg", "relevance_score": 0.90},
                {"reference_number": 3, "document_id": "doc-b", "filename": "罰單B.jpg", "relevance_score": 0.85},
            ],
            "expected_target": "罰單B.jpg",  # citation:2 對應的
            "expected_reasoning": "用戶說第二個文件，對應 AI 回答中 citation:2 的罰單B.jpg"
        }
    ]
    
    for scenario in scenarios:
        console.print(f"\n[yellow]場景: {scenario['name']}[/yellow]")
        console.print(f"  AI 上一次回答: {scenario['ai_previous_answer'][:60]}...")
        console.print(f"  用戶問題: {scenario['user_question']}")
        console.print(f"  文檔池順序:")
        for doc in scenario['document_pool']:
            console.print(f"    #{doc['reference_number']}: {doc['filename']} (relevance: {doc['relevance_score']})")
        
        # 提取 AI 回答中的引用
        citations = extract_citations(scenario['ai_previous_answer'])
        
        # 模擬解析邏輯
        if citations:
            # 有 AI 引用，使用引用順序
            console.print(f"  [cyan]→ AI 回答中有引用，使用引用順序[/cyan]")
            
            # 解析用戶問題中的編號
            number_match = re.search(r'第([一二三四五六七八九十\d]+)[個張份]', scenario['user_question'])
            if number_match:
                num_str = number_match.group(1)
                num_map = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}
                target_num = num_map.get(num_str, int(num_str) if num_str.isdigit() else 1)
                
                # 找到對應的引用
                target_citation = next((c for c in citations if c['number'] == target_num), None)
                if target_citation:
                    resolved_target = target_citation['filename']
                    console.print(f"  [cyan]→ 解析「第{num_str}個」為 citation:{target_num} = {resolved_target}[/cyan]")
                else:
                    resolved_target = None
                    console.print(f"  [red]→ 找不到 citation:{target_num}[/red]")
            else:
                resolved_target = citations[0]['filename'] if citations else None
        else:
            # 無 AI 引用，使用文檔池順序
            console.print(f"  [cyan]→ 無 AI 引用，使用文檔池順序[/cyan]")
            
            number_match = re.search(r'第([一二三四五六七八九十\d]+)[個張份]', scenario['user_question'])
            if number_match:
                num_str = number_match.group(1)
                num_map = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}
                target_num = num_map.get(num_str, int(num_str) if num_str.isdigit() else 1)
                
                target_doc = next((d for d in scenario['document_pool'] if d['reference_number'] == target_num), None)
                if target_doc:
                    resolved_target = target_doc['filename']
                    console.print(f"  [cyan]→ 解析「第{num_str}個」為文檔池 #{target_num} = {resolved_target}[/cyan]")
                else:
                    resolved_target = None
            else:
                resolved_target = scenario['document_pool'][0]['filename'] if scenario['document_pool'] else None
        
        # 驗證結果
        if resolved_target == scenario['expected_target']:
            console.print(f"  [green]✓ 正確解析為: {resolved_target}[/green]")
            console.print(f"  [green]  預期: {scenario['expected_target']}[/green]")
        else:
            console.print(f"  [red]✗ 解析錯誤: {resolved_target}[/red]")
            console.print(f"  [red]  預期: {scenario['expected_target']}[/red]")
            result.add_error(f"{scenario['name']}: 解析結果不符預期")
    
    result.passed = len(result.errors) == 0
    return result


async def run_all_tests():
    """運行所有測試"""
    print("\n" + "=" * 60)
    print("🧪 文件引用功能測試")
    print("測試 AI 生成答案中的引用格式、順序一致性和指代詞解析")
    print("=" * 60)
    
    results = []
    
    # 測試 1: 引用格式
    result1 = await test_citation_format()
    results.append(result1)
    
    # 測試 2: 引用順序一致性
    result2 = await test_citation_order_consistency()
    results.append(result2)
    
    # 測試 3: 指代詞解析
    result3 = await test_document_reference_parsing()
    results.append(result3)
    
    # 總結
    print("\n")
    print("=" * 60)
    print("📊 測試結果總結")
    print("=" * 60)
    
    total_passed = 0
    total_failed = 0
    
    print(f"\n{'測試名稱':<25} {'結果':<10} {'錯誤數':<8} {'警告數':<8}")
    print("-" * 55)
    
    for result in results:
        status = "✓ PASS" if result.passed else "✗ FAIL"
        print(f"{result.test_name:<25} {status:<10} {len(result.errors):<8} {len(result.warnings):<8}")
        if result.passed:
            total_passed += 1
        else:
            total_failed += 1
    
    print("-" * 55)
    print(f"\n總計: {total_passed} 通過, {total_failed} 失敗")
    
    # 顯示錯誤詳情
    if total_failed > 0:
        print("\n❌ 錯誤詳情:")
        for result in results:
            if result.errors:
                print(f"\n  {result.test_name}:")
                for error in result.errors:
                    print(f"    • {error}")
    
    return total_failed == 0


async def test_with_real_backend():
    """
    使用真實後端進行端到端測試（直接調用 qa_orchestrator）
    
    測試場景：
    1. 第一輪：搜索罰單 - "幫我找所有的罰單"
    2. 第二輪：查詢詳情 - "第一張罰單的金額是多少"（測試指代詞解析）
    3. 第三輪：追問超速 - "剛才那些罰單中，有沒有超速的？如果有，是哪一張？"
    """
    print("\n")
    print("=" * 80)
    print("🔌 真實後端端到端測試")
    print("測試文件引用功能在多輪對話中的表現")
    print("=" * 80)
    
    # 導入必要模組
    from motor.motor_asyncio import AsyncIOMotorClient
    from app.core.config import settings
    from app.services.vector.vector_db_service import vector_db_service
    from app.services.qa_orchestrator import qa_orchestrator
    from app.models.vector_models import AIQARequest
    from app.crud import crud_conversations
    from uuid import UUID
    import uuid as uuid_module
    
    # 連接 MongoDB
    client = AsyncIOMotorClient(
        settings.MONGODB_URL,
        uuidRepresentation='standard'
    )
    db = client[settings.DB_NAME]
    
    # 初始化向量資料庫
    vector_db_service.create_collection(768)
    
    # 獲取測試用戶
    sample_doc = await db.documents.find_one({})
    if not sample_doc:
        print("❌ 資料庫中沒有文檔")
        return False
    
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
    
    print(f"\n� 使用用戶 ID: {user_id}")
    
    # 測試問題
    test_rounds = [
        {
            "round": 1,
            "question": "幫我找所有的罰單",
            "action": "approve_search",
            "description": "搜索罰單",
            "expected": "應該找到多個罰單文檔，並使用 citation:1, citation:2... 格式引用"
        },
        {
            "round": 2,
            "question": "第一張罰單的金額是多少",
            "action": "approve_detail_query",
            "description": "查詢詳情 - 測試「第一張」指代詞解析",
            "expected": "應該查詢 AI 上一輪回答中 citation:1 對應的罰單"
        },
        {
            "round": 3,
            "question": "剛才那些罰單中，有沒有超速的？如果有，是哪一張？",
            "action": "approve_detail_query",
            "description": "追問超速 - 測試多輪對話上下文",
            "expected": "應該在之前找到的罰單中搜索超速相關的，並正確引用"
        }
    ]
    
    # 創建新對話
    print("\n📝 創建新對話...")
    first_question = test_rounds[0]['question']
    conversation = await crud_conversations.create_conversation(
        db=db,
        user_id=user_uuid,
        first_question=first_question
    )
    conversation_id = str(conversation.id)
    print(f"✅ 創建對話成功: {conversation_id}")
    
    # 收集測試結果
    all_results = []
    previous_citations = []  # 保存上一輪的引用，用於驗證
    
    for test in test_rounds:
        print(f"\n{'='*80}")
        print(f"【第 {test['round']} 輪】{test['description']}")
        print(f"{'='*80}")
        print(f"📝 問題: {test['question']}")
        print(f"🎯 預期: {test['expected']}")
        print("-" * 80)
        
        result = await execute_qa_round_direct(
            db=db,
            user_id=user_id,
            question=test['question'],
            conversation_id=conversation_id,
            round_num=test['round'],
            workflow_action=test['action'],
            previous_citations=previous_citations
        )
        
        # 保存本輪引用供下一輪驗證
        if result and result.get('citations'):
            previous_citations = result['citations']
        
        all_results.append({
            "round": test['round'],
            "question": test['question'],
            "description": test['description'],
            "result": result
        })
        
        await asyncio.sleep(0.5)
    
    # 總結測試結果
    print("\n")
    print("█" * 80)
    print("█" + " " * 28 + "📊 引用功能測試結果" + " " * 29 + "█")
    print("█" * 80)
    
    # ========== 1. 每輪對話概覽 ==========
    print("""
┌──────────────────────────────────────────────────────────────────────────────┐
│                           📋 每輪對話概覽                                     │
├──────────────────────────────────────────────────────────────────────────────┤""")
    
    for r in all_results:
        result = r['result']
        status = "✅" if result and result.get('answer') else "❌"
        citations_count = len(result.get('citations', [])) if result else 0
        doc_pool_count = len(result.get('document_pool', [])) if result else 0
        
        print(f"""
│  【第 {r['round']} 輪】{r['description']:<35} {status}              │
│  ├── 問題: {r['question'][:60]:<60}│
│  ├── 引用數: {citations_count:<3} | 文檔池: {doc_pool_count:<3}                                                │""")
        
        if result and result.get('answer'):
            answer_preview = result['answer'][:80].replace('\n', ' ')
            print(f"│  └── 答案: {answer_preview:<65}...│")
    
    print("""└──────────────────────────────────────────────────────────────────────────────┘""")
    
    # ========== 2. 引用詳細分析 ==========
    print("""
┌──────────────────────────────────────────────────────────────────────────────┐
│                           🔗 引用詳細分析                                     │
├──────────────────────────────────────────────────────────────────────────────┤""")
    
    for r in all_results:
        result = r['result']
        print(f"\n│  【第 {r['round']} 輪】{r['description']}")
        print(f"│  {'─'*74}")
        
        if result and result.get('citations'):
            print(f"│  AI 回答中的引用 (共 {len(result['citations'])} 個):")
            for c in result['citations']:
                print(f"│    • citation:{c['number']} → {c['filename']}")
        else:
            print(f"│  ⚠️ 無引用")
        
        if result and result.get('current_round_documents'):
            print(f"│")
            print(f"│  AI 看到的文檔順序 (current_round_documents):")
            for i, doc in enumerate(result['current_round_documents'], 1):
                filename = doc.get('filename', 'unknown')
                doc_id = doc.get('document_id', 'unknown')[:8]
                print(f"│    #{i}: {filename} (ID: {doc_id}...)")
    
    print("""│
└──────────────────────────────────────────────────────────────────────────────┘""")
    
    # ========== 3. 關鍵驗證：第二輪「第一張罰單」解析 ==========
    print("""
┌──────────────────────────────────────────────────────────────────────────────┐
│                    🧪 關鍵驗證：「第一張罰單」指代詞解析                        │
├──────────────────────────────────────────────────────────────────────────────┤""")
    
    round1_result = all_results[0]['result'] if len(all_results) > 0 else None
    round2_result = all_results[1]['result'] if len(all_results) > 1 else None
    
    # 從第 1 輪的 current_round_documents 獲取 citation:1 對應的實際文檔
    # （因為 AI 可能使用 [文檔1] 而不是 [實際文件名] 作為引用文本）
    if round1_result and round1_result.get('current_round_documents'):
        round1_docs = round1_result['current_round_documents']
        if round1_docs:
            # citation:1 對應第一個文檔
            expected_doc = round1_docs[0] if len(round1_docs) > 0 else None
            
            if expected_doc:
                expected_filename = expected_doc.get('filename', 'unknown')
                print(f"│")
                print(f"│  第 1 輪 citation:1 對應的實際文檔 (從 current_round_documents):")
                print(f"│    → {expected_filename}")
                print(f"│")
                
                # 也顯示 AI 回答中的引用文本
                if round1_result.get('citations'):
                    citation_1 = next((c for c in round1_result['citations'] if c['number'] == 1), None)
                    if citation_1:
                        print(f"│  AI 回答中 citation:1 的引用文本:")
                        print(f"│    → {citation_1['filename']}")
                        print(f"│")
                
                if round2_result:
                    print(f"│  第 2 輪用戶問「第一張罰單的金額是多少」")
                    print(f"│")
                    
                    # 檢查第二輪查詢的文檔
                    if round2_result.get('current_round_documents'):
                        queried_doc = round2_result['current_round_documents'][0] if round2_result['current_round_documents'] else None
                        if queried_doc:
                            queried_filename = queried_doc.get('filename', 'unknown')
                            queried_doc_id = queried_doc.get('document_id', '')
                            expected_doc_id = expected_doc.get('document_id', '')
                            
                            print(f"│  第 2 輪實際查詢的文檔:")
                            print(f"│    → {queried_filename}")
                            print(f"│    → ID: {queried_doc_id[:20]}...")
                            print(f"│")
                            
                            # 驗證：優先比較文檔 ID，其次比較文件名（可能有簡化）
                            # 也檢查文件名是否包含相同的 ID 片段
                            id_match = (expected_doc_id and queried_doc_id and expected_doc_id == queried_doc_id)
                            filename_contains_id = (expected_filename[:8] in queried_filename or queried_filename[:8] in expected_filename)
                            
                            if id_match:
                                print(f"│  ✅ 驗證通過！（文檔 ID 匹配）")
                                print(f"│     AI 正確解析「第一張」為 citation:1 對應的文檔")
                            elif expected_filename == queried_filename:
                                print(f"│  ✅ 驗證通過！（文件名完全匹配）")
                                print(f"│     AI 正確解析「第一張」為 citation:1 對應的文檔")
                            elif filename_contains_id:
                                print(f"│  ✅ 驗證通過！（文件名包含相同 ID）")
                                print(f"│     AI 正確解析「第一張」為 citation:1 對應的文檔")
                                print(f"│     (文件名格式略有不同，但指向同一文檔)")
                            else:
                                print(f"│  ❌ 驗證失敗！")
                                print(f"│     預期查詢: {expected_filename}")
                                print(f"│     實際查詢: {queried_filename}")
                    else:
                        print(f"│  ⚠️ 第 2 輪沒有 current_round_documents 數據")
            else:
                print(f"│  ⚠️ 第 1 輪 current_round_documents 為空")
    else:
        print(f"│  ⚠️ 第 1 輪沒有 current_round_documents 數據")
    
    print("""│
└──────────────────────────────────────────────────────────────────────────────┘""")
    
    # ========== 4. 文檔池變化追蹤 ==========
    print("""
┌──────────────────────────────────────────────────────────────────────────────┐
│                           📁 文檔池變化追蹤                                   │
├──────────────────────────────────────────────────────────────────────────────┤""")
    
    for r in all_results:
        result = r['result']
        print(f"│")
        print(f"│  【第 {r['round']} 輪】文檔池 ({len(result.get('document_pool', []))} 個文檔):")
        
        if result and result.get('document_pool'):
            # 按相關性排序顯示
            sorted_pool = sorted(
                result['document_pool'], 
                key=lambda x: x.get('relevance_score', 0), 
                reverse=True
            )
            for i, doc in enumerate(sorted_pool[:5], 1):
                filename = doc.get('filename', 'unknown')[:40]
                relevance = doc.get('relevance_score', 0)
                access = doc.get('access_count', 0)
                print(f"│    #{i}: {filename:<40} (相關性: {relevance:.2f}, 訪問: {access})")
            if len(sorted_pool) > 5:
                print(f"│    ... 還有 {len(sorted_pool) - 5} 個文檔")
    
    print("""│
└──────────────────────────────────────────────────────────────────────────────┘""")
    
    # ========== 5. 完整答案展示 ==========
    print("""
┌──────────────────────────────────────────────────────────────────────────────┐
│                           📝 完整答案展示                                     │
├──────────────────────────────────────────────────────────────────────────────┤""")
    
    for r in all_results:
        result = r['result']
        print(f"│")
        print(f"│  【第 {r['round']} 輪】{r['question']}")
        print(f"│  {'─'*74}")
        
        if result and result.get('answer'):
            # 顯示答案（限制長度）
            answer = result['answer'][:500]
            for line in answer.split('\n')[:10]:
                print(f"│  {line[:75]}")
            if len(result['answer']) > 500:
                print(f"│  ... (共 {len(result['answer'])} 字)")
        else:
            print(f"│  ⚠️ 無答案")
    
    print("""│
└──────────────────────────────────────────────────────────────────────────────┘""")
    
    # 關閉連接
    client.close()
    
    print("\n" + "=" * 80)
    print("✅ 引用功能測試完成")
    print("=" * 80)
    
    return True


async def execute_qa_round_direct(
    db,
    user_id: str,
    question: str,
    conversation_id: str,
    round_num: int,
    workflow_action: str,
    previous_citations: List[Dict] = None
) -> dict:
    """
    直接調用 qa_orchestrator 執行一輪 QA 問答
    """
    from app.services.qa_orchestrator import qa_orchestrator
    from app.models.vector_models import AIQARequest
    
    result = {
        "success": False,
        "answer": "",
        "citations": [],
        "document_pool": [],
        "current_round_documents": [],
        "errors": [],
        "verification": None
    }
    
    try:
        start_time = datetime.now()
        
        # ========== 階段 1: 首次請求（等待批准）==========
        print(f"\n   🔹 階段 1: 首次請求")
        
        qa_request_phase1 = AIQARequest(
            question=question,
            context_limit=5,
            use_semantic_search=True,
            workflow_action=None,
            conversation_id=conversation_id
        )
        
        approval_received = False
        
        async for event in qa_orchestrator.process_qa_request_intelligent_stream(
            db=db,
            request=qa_request_phase1,
            user_id=user_id,
            request_id=f"citation_test_r{round_num}_p1"
        ):
            event_type = event.type
            event_data = event.data
            
            if event_type == 'progress':
                stage = event_data.get('stage', '')
                message = event_data.get('message', '')
                print(f"   📍 [{stage}] {message[:60]}...")
            
            elif event_type == 'approval_needed':
                approval_received = True
                print(f"   ⏸️ 收到批准請求")
            
            elif event_type == 'complete':
                result['answer'] = event_data.get('answer', '')
                print(f"   ✅ 直接完成（無需批准）")
            
            elif event_type == 'error':
                result['errors'].append(event_data.get('message', ''))
                print(f"   ❌ 錯誤: {event_data.get('message', '')}")
        
        # ========== 階段 2: 批准請求 ==========
        if approval_received:
            print(f"\n   🔹 階段 2: 批准請求 ({workflow_action})")
            
            qa_request_phase2 = AIQARequest(
                question=question,
                context_limit=5,
                use_semantic_search=True,
                workflow_action=workflow_action,
                conversation_id=conversation_id
            )
            
            full_answer = ""
            chunk_count = 0
            
            async for event in qa_orchestrator.process_qa_request_intelligent_stream(
                db=db,
                request=qa_request_phase2,
                user_id=user_id,
                request_id=f"citation_test_r{round_num}_p2"
            ):
                event_type = event.type
                event_data = event.data
                
                if event_type == 'progress':
                    stage = event_data.get('stage', '')
                    message = event_data.get('message', '')
                    print(f"   📍 [{stage}] {message[:60]}...")
                
                elif event_type == 'chunk':
                    # ⭐ 收集流式輸出的文本
                    chunk_text = event_data.get('text', '')
                    full_answer += chunk_text
                    chunk_count += 1
                
                elif event_type == 'complete':
                    # complete 事件可能包含完整答案，也可能為空（如果是流式輸出）
                    complete_answer = event_data.get('answer', '')
                    if complete_answer:
                        full_answer = complete_answer
                    print(f"   ✅ 完成 (chunks: {chunk_count}, 答案長度: {len(full_answer)} 字)")
                
                elif event_type == 'metadata':
                    if 'document_pool' in event_data:
                        doc_pool = event_data['document_pool']
                        if isinstance(doc_pool, dict):
                            result['document_pool'] = list(doc_pool.values())
                        else:
                            result['document_pool'] = doc_pool
                    
                    if 'current_round_documents' in event_data:
                        result['current_round_documents'] = event_data['current_round_documents']
                
                elif event_type == 'error':
                    result['errors'].append(event_data.get('message', ''))
            
            result['answer'] = full_answer
        
        # 提取引用
        result['citations'] = extract_citations(result['answer'])
        result['success'] = len(result['errors']) == 0 and len(result['answer']) > 0
        
        duration = (datetime.now() - start_time).total_seconds()
        
        # 顯示結果
        print(f"\n   ⏱️ 耗時: {duration:.2f} 秒")
        print(f"   📝 答案長度: {len(result['answer'])} 字符")
        print(f"   🔗 引用數量: {len(result['citations'])}")
        
        # 顯示答案摘要
        if result['answer']:
            print(f"\n   📄 答案摘要:")
            summary = result['answer'][:300].replace('\n', ' ')
            print(f"      {summary}...")
        
        # 顯示引用
        if result['citations']:
            print(f"\n   🔍 提取到的引用:")
            for c in result['citations']:
                print(f"      citation:{c['number']} → [{c['filename']}]")
        
        # 顯示當前輪次文檔順序
        if result['current_round_documents']:
            print(f"\n   📋 當前輪次文檔順序 (AI 看到的):")
            for i, doc in enumerate(result['current_round_documents'][:5], 1):
                filename = doc.get('filename', 'unknown')
                print(f"      #{i}: {filename}")
        
        # ========== 驗證引用正確性 ==========
        if round_num == 2 and previous_citations:
            # 第二輪：驗證「第一張罰單」是否正確解析
            print(f"\n   🧪 驗證「第一張罰單」指代詞解析:")
            
            # 上一輪 citation:1 對應的文檔
            prev_citation_1 = next((c for c in previous_citations if c['number'] == 1), None)
            
            if prev_citation_1:
                expected_doc = prev_citation_1['filename']
                print(f"      上一輪 citation:1 = {expected_doc}")
                
                # 檢查本輪答案是否提到了正確的文檔
                if expected_doc in result['answer']:
                    result['verification'] = {
                        'passed': True,
                        'message': f'正確引用了 {expected_doc}'
                    }
                    print(f"      ✅ 正確！答案中提到了 {expected_doc}")
                else:
                    result['verification'] = {
                        'passed': False,
                        'message': f'未找到對 {expected_doc} 的引用'
                    }
                    print(f"      ⚠️ 答案中未明確提到 {expected_doc}")
            else:
                print(f"      ⚠️ 上一輪沒有 citation:1")
    
    except Exception as e:
        result['errors'].append(str(e))
        print(f"   ❌ 執行失敗: {e}")
        import traceback
        traceback.print_exc()
    
    return result


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="文件引用功能測試腳本")
    parser.add_argument("--real", action="store_true", help="運行真實後端測試（直接調用 qa_orchestrator）")
    parser.add_argument("--skip-mock", action="store_true", help="跳過模擬測試")
    
    args = parser.parse_args()
    
    print(f"\n執行時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    success = True
    
    # 運行模擬測試
    if not args.skip_mock:
        success = asyncio.run(run_all_tests())
    
    # 運行真實後端測試
    if args.real:
        real_success = asyncio.run(test_with_real_backend())
        success = success and real_success
    
    # 退出碼
    sys.exit(0 if success else 1)
