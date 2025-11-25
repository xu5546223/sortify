"""檢查 AI 分塊粒度是否合理"""
import asyncio
import aiohttp
import os
from dotenv import load_dotenv

load_dotenv('.env', override=True)

async def main():
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
        
        if 'access_token' not in login_data:
            print(f"登入失敗: {login_data}")
            return
        
        token = login_data['access_token']
        headers = {'Authorization': f'Bearer {token}'}
        
        # 獲取文檔列表
        docs_resp = await session.get(
            f'{api_url}/api/v1/documents/',
            headers=headers,
            params={'limit': 20}
        )
        docs_data = await docs_resp.json()
        documents = docs_data.get('items', [])
        
        print(f"分析 {len(documents)} 個文檔的分塊粒度")
        print("=" * 80)
        
        # 統計
        total_chunks = 0
        total_docs_with_chunks = 0
        chunk_lengths = []
        chunk_types = {}
        strategy_counts = {"hybrid": 0, "raw_only": 0, "sub_chunked": 0}
        
        for doc in documents:
            doc_id = doc.get('id')
            filename = doc.get('filename', 'unknown')
            extracted_text = doc.get('extracted_text', '')
            
            # 獲取 logical_chunks
            analysis = doc.get('analysis', {})
            ai_output = analysis.get('ai_analysis_output', {}) or {}
            logical_chunks = ai_output.get('logical_chunks', [])
            
            if not logical_chunks:
                continue
            
            total_docs_with_chunks += 1
            
            print(f"\n📄 {filename[:50]}")
            print(f"   文檔長度: {len(extracted_text)} 字符")
            print(f"   分塊數量: {len(logical_chunks)} 個")
            
            if len(extracted_text) > 0:
                avg_chunk_size = len(extracted_text) / len(logical_chunks)
                print(f"   平均塊大小: {avg_chunk_size:.0f} 字符")
            
            for i, chunk in enumerate(logical_chunks):
                chunk_type = chunk.get('type', 'unknown')
                start_id = chunk.get('start_id', '')
                end_id = chunk.get('end_id', '')
                summary = chunk.get('summary', '')
                
                # 統計類型
                chunk_types[chunk_type] = chunk_types.get(chunk_type, 0) + 1
                total_chunks += 1
                
                # 計算行數
                try:
                    start_num = int(start_id.replace('L', ''))
                    end_num = int(end_id.replace('L', ''))
                    line_count = end_num - start_num + 1
                except:
                    line_count = 0
                
                # 判斷向量化策略
                # 假設每行約 30 字符
                estimated_length = line_count * 30
                if estimated_length <= 350:
                    strategy = "hybrid"
                elif estimated_length <= 480:
                    strategy = "raw_only"
                else:
                    strategy = "sub_chunked"
                strategy_counts[strategy] += 1
                
                chunk_lengths.append(line_count)
                
                print(f"   [{i+1}] {chunk_type:12} | {start_id}-{end_id} ({line_count:2} 行) | {summary[:40]}...")
        
        # 總結統計
        print("\n" + "=" * 80)
        print("📊 分塊粒度統計")
        print("=" * 80)
        
        print(f"\n文檔統計:")
        print(f"   有分塊的文檔: {total_docs_with_chunks}")
        print(f"   總分塊數: {total_chunks}")
        if total_docs_with_chunks > 0:
            print(f"   平均每文檔分塊數: {total_chunks / total_docs_with_chunks:.1f}")
        
        print(f"\n分塊類型分布:")
        for chunk_type, count in sorted(chunk_types.items(), key=lambda x: -x[1]):
            pct = count / total_chunks * 100 if total_chunks > 0 else 0
            print(f"   {chunk_type:15}: {count:3} ({pct:.1f}%)")
        
        print(f"\n向量化策略分布 (估算):")
        for strategy, count in strategy_counts.items():
            pct = count / total_chunks * 100 if total_chunks > 0 else 0
            print(f"   {strategy:15}: {count:3} ({pct:.1f}%)")
        
        if chunk_lengths:
            print(f"\n分塊行數統計:")
            print(f"   最小: {min(chunk_lengths)} 行")
            print(f"   最大: {max(chunk_lengths)} 行")
            print(f"   平均: {sum(chunk_lengths) / len(chunk_lengths):.1f} 行")
            print(f"   中位數: {sorted(chunk_lengths)[len(chunk_lengths)//2]} 行")
            
            # 行數分布
            print(f"\n行數分布:")
            ranges = [(1, 5), (6, 10), (11, 20), (21, 30), (31, 50), (51, 100), (101, 999)]
            for low, high in ranges:
                count = sum(1 for l in chunk_lengths if low <= l <= high)
                if count > 0:
                    pct = count / len(chunk_lengths) * 100
                    print(f"   {low:3}-{high:3} 行: {count:3} ({pct:.1f}%)")

if __name__ == "__main__":
    asyncio.run(main())
