"""分析 QA 問題集的質量，找出可能影響召回率的問題"""
import json
import asyncio
import aiohttp
import os
from dotenv import load_dotenv

load_dotenv('.env', override=True)

async def main():
    # 載入 QA 數據集
    with open('QA_dataset.json', 'r', encoding='utf-8') as f:
        qa_data = json.load(f)
    
    print(f"總共 {len(qa_data)} 個測試問題")
    print("=" * 80)
    
    # 分析問題特徵
    question_lengths = []
    question_types = {}
    vague_questions = []  # 模糊問題
    specific_questions = []  # 具體問題
    
    # 模糊詞彙
    vague_keywords = ['什麼', '哪些', '如何', '怎樣', '為何', '為什麼', '主要', '關於']
    specific_keywords = ['多少', '幾', '日期', '金額', '號碼', '名稱', '地址', '編號']
    
    for i, case in enumerate(qa_data):
        question = case.get('question', '')
        q_type = case.get('question_type', 'unknown')
        
        question_lengths.append(len(question))
        question_types[q_type] = question_types.get(q_type, 0) + 1
        
        # 判斷問題是否模糊
        is_vague = any(kw in question for kw in vague_keywords)
        is_specific = any(kw in question for kw in specific_keywords)
        
        if is_vague and not is_specific:
            vague_questions.append((i, question[:80], q_type))
        elif is_specific:
            specific_questions.append((i, question[:80], q_type))
    
    # 統計
    print("\n📊 問題類型分布:")
    for q_type, count in sorted(question_types.items(), key=lambda x: -x[1]):
        pct = count / len(qa_data) * 100
        print(f"  {q_type:20}: {count:3} ({pct:.1f}%)")
    
    print(f"\n📏 問題長度統計:")
    print(f"  最短: {min(question_lengths)} 字符")
    print(f"  最長: {max(question_lengths)} 字符")
    print(f"  平均: {sum(question_lengths)/len(question_lengths):.1f} 字符")
    
    print(f"\n🔍 問題具體性分析:")
    print(f"  模糊問題: {len(vague_questions)} ({len(vague_questions)/len(qa_data)*100:.1f}%)")
    print(f"  具體問題: {len(specific_questions)} ({len(specific_questions)/len(qa_data)*100:.1f}%)")
    
    print(f"\n📝 模糊問題示例 (前 10 個):")
    for idx, q, qt in vague_questions[:10]:
        print(f"  [{idx}] ({qt}) {q}...")
    
    print(f"\n✅ 具體問題示例 (前 10 個):")
    for idx, q, qt in specific_questions[:10]:
        print(f"  [{idx}] ({qt}) {q}...")
    
    # 測試模糊 vs 具體問題的召回率差異
    api_url = os.getenv('API_URL', 'http://localhost:8000')
    username = os.getenv('USERNAME')
    password = os.getenv('PASSWORD')
    
    async with aiohttp.ClientSession() as session:
        # 登入
        login_resp = await session.post(
            f'{api_url}/api/v1/auth/token', 
            data={'username': username, 'password': password}
        )
        login_data = await login_resp.json()
        token = login_data['access_token']
        headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
        
        print("\n" + "=" * 80)
        print("🧪 測試模糊 vs 具體問題的召回率差異")
        print("=" * 80)
        
        # 測試模糊問題
        vague_hits = 0
        vague_test = vague_questions[:30] if len(vague_questions) >= 30 else vague_questions
        for idx, _, _ in vague_test:
            case = qa_data[idx]
            query = case.get('question', '')
            expected_ids = case.get('expected_relevant_doc_ids', [])
            
            payload = {
                "query": query,
                "top_k": 10,
                "similarity_threshold": 0.3,
                "enable_hybrid_search": False
            }
            
            resp = await session.post(
                f'{api_url}/api/v1/vector-db/semantic-search',
                json=payload,
                headers=headers
            )
            
            if resp.status == 200:
                results = await resp.json()
                retrieved_ids = [r.get('document_id') for r in results]
                if any(eid in retrieved_ids for eid in expected_ids):
                    vague_hits += 1
        
        vague_hit_rate = vague_hits / len(vague_test) * 100 if vague_test else 0
        
        # 測試具體問題
        specific_hits = 0
        specific_test = specific_questions[:30] if len(specific_questions) >= 30 else specific_questions
        for idx, _, _ in specific_test:
            case = qa_data[idx]
            query = case.get('question', '')
            expected_ids = case.get('expected_relevant_doc_ids', [])
            
            payload = {
                "query": query,
                "top_k": 10,
                "similarity_threshold": 0.3,
                "enable_hybrid_search": False
            }
            
            resp = await session.post(
                f'{api_url}/api/v1/vector-db/semantic-search',
                json=payload,
                headers=headers
            )
            
            if resp.status == 200:
                results = await resp.json()
                retrieved_ids = [r.get('document_id') for r in results]
                if any(eid in retrieved_ids for eid in expected_ids):
                    specific_hits += 1
        
        specific_hit_rate = specific_hits / len(specific_test) * 100 if specific_test else 0
        
        print(f"\n📊 召回率對比:")
        print(f"  模糊問題 Hit@10: {vague_hit_rate:.1f}% ({vague_hits}/{len(vague_test)})")
        print(f"  具體問題 Hit@10: {specific_hit_rate:.1f}% ({specific_hits}/{len(specific_test)})")
        print(f"  差異: {specific_hit_rate - vague_hit_rate:+.1f}%")
        
        if specific_hit_rate > vague_hit_rate:
            print("\n💡 結論: 具體問題的召回率更高，問題集中的模糊問題可能拉低了整體指標")
        else:
            print("\n💡 結論: 模糊問題的召回率不比具體問題差，問題集質量可能不是主要原因")

if __name__ == "__main__":
    asyncio.run(main())
