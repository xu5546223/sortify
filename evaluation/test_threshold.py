"""測試不同 similarity_threshold 對召回率的影響"""
import asyncio
import aiohttp
import os
import json
from dotenv import load_dotenv

load_dotenv('.env', override=True)

async def main():
    api_url = os.getenv('API_URL', 'http://localhost:8000')
    username = os.getenv('USERNAME')
    password = os.getenv('PASSWORD')
    
    # 載入 QA 數據集
    with open('QA_dataset.json', 'r', encoding='utf-8') as f:
        qa_data = json.load(f)
    
    # 取前 30 個測試案例
    test_cases = qa_data[:30]
    
    async with aiohttp.ClientSession() as session:
        # 登入
        login_resp = await session.post(
            f'{api_url}/api/v1/auth/token', 
            data={'username': username, 'password': password}
        )
        login_data = await login_resp.json()
        token = login_data['access_token']
        headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
        
        # 測試不同閾值
        thresholds = [0.2, 0.3, 0.4, 0.5, 0.6]
        
        print("=" * 80)
        print("測試不同 similarity_threshold 對召回率的影響")
        print("=" * 80)
        
        for threshold in thresholds:
            hits_at_10 = 0
            total_results = 0
            
            for case in test_cases:
                query = case.get('question', '')
                expected_ids = case.get('expected_relevant_doc_ids', [])
                
                payload = {
                    "query": query,
                    "top_k": 10,
                    "similarity_threshold": threshold,
                    "enable_hybrid_search": False  # 用 legacy 模式測試
                }
                
                resp = await session.post(
                    f'{api_url}/api/v1/vector-db/semantic-search',
                    json=payload,
                    headers=headers
                )
                
                if resp.status == 200:
                    results = await resp.json()
                    total_results += len(results)
                    
                    # 檢查是否命中
                    retrieved_ids = [r.get('document_id') for r in results]
                    if any(eid in retrieved_ids for eid in expected_ids):
                        hits_at_10 += 1
            
            hit_rate = hits_at_10 / len(test_cases) * 100
            avg_results = total_results / len(test_cases)
            
            print(f"\n閾值 {threshold}:")
            print(f"  Hit@10: {hit_rate:.1f}% ({hits_at_10}/{len(test_cases)})")
            print(f"  平均返回結果數: {avg_results:.1f}")
        
        # 分析分數分布
        print("\n" + "=" * 80)
        print("分析相似度分數分布（使用閾值 0.0）")
        print("=" * 80)
        
        all_scores = []
        for case in test_cases[:10]:
            query = case.get('question', '')
            
            payload = {
                "query": query,
                "top_k": 10,
                "similarity_threshold": 0.0,
                "enable_hybrid_search": False
            }
            
            resp = await session.post(
                f'{api_url}/api/v1/vector-db/semantic-search',
                json=payload,
                headers=headers
            )
            
            if resp.status == 200:
                results = await resp.json()
                scores = [r.get('similarity_score', 0) for r in results]
                all_scores.extend(scores)
        
        if all_scores:
            all_scores.sort(reverse=True)
            print(f"\n分數統計 ({len(all_scores)} 個結果):")
            print(f"  最高: {max(all_scores):.4f}")
            print(f"  最低: {min(all_scores):.4f}")
            print(f"  平均: {sum(all_scores)/len(all_scores):.4f}")
            print(f"  中位數: {all_scores[len(all_scores)//2]:.4f}")
            
            # 分數分布
            print(f"\n分數分布:")
            ranges = [(0.8, 1.0), (0.7, 0.8), (0.6, 0.7), (0.5, 0.6), (0.4, 0.5), (0.3, 0.4), (0.2, 0.3), (0.0, 0.2)]
            for low, high in ranges:
                count = sum(1 for s in all_scores if low <= s < high)
                if count > 0:
                    pct = count / len(all_scores) * 100
                    print(f"  {low:.1f}-{high:.1f}: {count:3} ({pct:.1f}%)")

if __name__ == "__main__":
    asyncio.run(main())
