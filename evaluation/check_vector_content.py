"""檢查向量數據庫中的內容，確認行號標記是否已移除"""
import asyncio
import aiohttp
import os
from dotenv import load_dotenv

load_dotenv('.env', override=True)

async def main():
    api_url = os.getenv('API_URL', 'http://localhost:8000')
    username = os.getenv('USERNAME')
    password = os.getenv('PASSWORD')
    
    # Debug: 顯示讀取的值
    print(f"DEBUG - 從 .env 讀取: USERNAME={username}")
    
    print(f"API: {api_url}")
    print(f"User: {username}")
    
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
        
        # 搜索測試
        payload = {
            'query': '發票 收據',
            'top_k': 5,
            'similarity_threshold': 0.2
        }
        
        search_resp = await session.post(
            f'{api_url}/api/v1/vector-db/semantic-search',
            json=payload,
            headers=headers
        )
        results = await search_resp.json()
        
        print(f"\n找到 {len(results)} 個結果")
        print("=" * 70)
        
        line_marker_count = 0
        
        for i, r in enumerate(results):
            print(f"\n【結果 {i+1}】")
            
            meta = r.get('metadata', {})
            print(f"  向量類型: {meta.get('type', 'unknown')}")
            print(f"  向量化策略: {meta.get('vectorization_strategy', 'unknown')}")
            print(f"  start_line: {r.get('start_line')}")
            print(f"  end_line: {r.get('end_line')}")
            print(f"  相似度: {r.get('similarity_score', 0):.4f}")
            
            text = r.get('summary_text', '')
            
            # 檢查是否包含行號標記
            has_marker = '[L0' in text or '[L1' in text or '[L2' in text
            if has_marker:
                line_marker_count += 1
                print(f"  ⚠️ 包含行號標記: YES")
            else:
                print(f"  ✅ 包含行號標記: NO")
            
            # 顯示內容預覽
            preview = text[:250].replace('\n', ' ')
            print(f"  內容預覽: {preview}...")
        
        print("\n" + "=" * 70)
        print(f"📊 統計: {line_marker_count}/{len(results)} 個結果包含行號標記")
        
        if line_marker_count > 0:
            print("⚠️ 仍有向量包含行號標記，需要重新向量化")
        else:
            print("✅ 所有向量都不包含行號標記")

if __name__ == "__main__":
    asyncio.run(main())
