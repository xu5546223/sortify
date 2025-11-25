"""比較各搜索模式返回的具體結果差異"""
import asyncio
import aiohttp
import os
from dotenv import load_dotenv

load_dotenv('.env', override=True)

async def main():
    api_url = os.getenv('API_URL', 'http://localhost:8000')
    username = os.getenv('USERNAME')
    password = os.getenv('PASSWORD')
    
    # 測試查詢
    test_queries = [
        "這張發票的總金額是多少？",
        "租賃契約的租金是多少？",
        "膠原蛋白產品的價格",
    ]
    
    async with aiohttp.ClientSession() as session:
        # 登入
        login_resp = await session.post(
            f'{api_url}/api/v1/auth/token', 
            data={'username': username, 'password': password}
        )
        login_data = await login_resp.json()
        
        if 'access_token' not in login_data:
            print(f"登入失敗: {login_data}")
            return
        
        token = login_data['access_token']
        headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
        
        for query in test_queries:
            print("\n" + "=" * 80)
            print(f"🔍 查詢: {query}")
            print("=" * 80)
            
            # 測試各種搜索模式
            modes = [
                ("legacy", {"enable_hybrid_search": False}),
                ("summary_only", {"enable_hybrid_search": True, "search_type": "summary_only"}),
                ("chunks_only", {"enable_hybrid_search": True, "search_type": "chunks_only"}),
                ("hybrid", {"enable_hybrid_search": True, "search_type": "hybrid"}),
                ("rrf_fusion", {"enable_hybrid_search": True, "search_type": "rrf_fusion"}),
            ]
            
            results_by_mode = {}
            
            for mode_name, mode_params in modes:
                payload = {
                    "query": query,
                    "top_k": 5,
                    "similarity_threshold": 0.3,
                    **mode_params
                }
                
                try:
                    resp = await session.post(
                        f'{api_url}/api/v1/vector-db/semantic-search',
                        json=payload,
                        headers=headers
                    )
                    
                    if resp.status == 200:
                        results = await resp.json()
                        results_by_mode[mode_name] = results
                    else:
                        error = await resp.text()
                        print(f"  ❌ {mode_name}: 錯誤 {resp.status}")
                        results_by_mode[mode_name] = []
                except Exception as e:
                    print(f"  ❌ {mode_name}: 異常 {e}")
                    results_by_mode[mode_name] = []
            
            # 比較結果
            print("\n📊 各模式結果對比:")
            print("-" * 80)
            
            # 顯示每個模式的前 3 個結果
            for mode_name, results in results_by_mode.items():
                print(f"\n【{mode_name}】({len(results)} 個結果)")
                
                for i, r in enumerate(results[:3]):
                    doc_id = r.get('document_id', '')[:8]
                    score = r.get('similarity_score', 0)
                    metadata = r.get('metadata', {})
                    vec_type = metadata.get('type', 'unknown')
                    strategy = metadata.get('vectorization_strategy', '')
                    
                    # 獲取文本預覽
                    text = r.get('summary_text', '') or r.get('chunk_text', '')
                    preview = text[:60].replace('\n', ' ') if text else 'N/A'
                    
                    print(f"  {i+1}. [{vec_type:7}] score={score:.4f} | {doc_id}... | {preview}...")
            
            # 分析排名差異
            print("\n📈 排名分析:")
            print("-" * 80)
            
            # 獲取 legacy 的文檔 ID 排名
            legacy_ranking = [r.get('document_id') for r in results_by_mode.get('legacy', [])]
            
            for mode_name in ['summary_only', 'chunks_only', 'hybrid', 'rrf_fusion']:
                mode_results = results_by_mode.get(mode_name, [])
                mode_ranking = [r.get('document_id') for r in mode_results]
                
                if not mode_ranking:
                    print(f"  {mode_name}: 無結果")
                    continue
                
                # 計算第一個結果是否與 legacy 相同
                first_match = "✅" if (mode_ranking and legacy_ranking and mode_ranking[0] == legacy_ranking[0]) else "❌"
                
                # 計算前 3 個結果的重疊
                top3_overlap = len(set(mode_ranking[:3]) & set(legacy_ranking[:3]))
                
                print(f"  {mode_name:15}: 首位{first_match} | Top3重疊: {top3_overlap}/3")
            
            # 顯示向量類型分布
            print("\n📦 向量類型分布:")
            for mode_name, results in results_by_mode.items():
                types = {}
                for r in results:
                    t = r.get('metadata', {}).get('type', 'unknown')
                    types[t] = types.get(t, 0) + 1
                type_str = ", ".join([f"{k}:{v}" for k, v in types.items()])
                print(f"  {mode_name:15}: {type_str}")

if __name__ == "__main__":
    asyncio.run(main())
