"""檢查文檔是否有 logical_chunks 和 line_mapping，以及 AI 分析結果"""
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
            params={'limit': 3}
        )
        docs_data = await docs_resp.json()
        documents = docs_data.get('items', [])
        
        print(f"檢查 {len(documents)} 個文檔的數據完整性")
        print("=" * 70)
        
        for doc in documents[:5]:
            doc_id = doc.get('id')
            filename = doc.get('filename', 'unknown')
            
            print(f"\n📄 文檔: {filename[:40]}")
            print(f"   ID: {doc_id}")
            
            # 檢查 line_mapping
            line_mapping = doc.get('line_mapping')
            has_line_mapping = bool(line_mapping) and len(line_mapping) > 0
            print(f"   line_mapping: {'✅ 有 (' + str(len(line_mapping)) + ' 行)' if has_line_mapping else '❌ 無'}")
            
            # 檢查 analysis 和 logical_chunks
            analysis = doc.get('analysis', {})
            ai_output = {}
            if analysis:
                ai_output = analysis.get('ai_analysis_output', {}) or {}
            
            logical_chunks = ai_output.get('logical_chunks', [])
            has_logical_chunks = bool(logical_chunks) and len(logical_chunks) > 0
            print(f"   logical_chunks: {'✅ 有 (' + str(len(logical_chunks)) + ' 個)' if has_logical_chunks else '❌ 無'}")
            
            # 檢查 extracted_text
            extracted_text = doc.get('extracted_text', '')
            has_extracted_text = bool(extracted_text) and len(extracted_text) > 0
            print(f"   extracted_text: {'✅ 有 (' + str(len(extracted_text)) + ' 字符)' if has_extracted_text else '❌ 無'}")
            
            # 判斷會使用哪種策略
            if has_line_mapping and has_logical_chunks:
                print(f"   ➡️ 預期策略: AI 邏輯分塊 ✅")
            else:
                print(f"   ➡️ 預期策略: 固定大小分塊 (fallback) ⚠️")
                if not has_line_mapping:
                    print(f"      原因: 缺少 line_mapping")
                if not has_logical_chunks:
                    print(f"      原因: 缺少 logical_chunks")
            
            # 檢查 AI 分析中的 extracted_text
            ai_extracted_text = ai_output.get('extracted_text', '')
            has_ai_extracted = bool(ai_extracted_text) and len(ai_extracted_text) > 0
            print(f"   ai_analysis_output.extracted_text: {'✅ 有 (' + str(len(ai_extracted_text)) + ' 字符)' if has_ai_extracted else '❌ 無'}")
            
            # 顯示 extracted_text 的前 100 字符
            if has_ai_extracted:
                preview = ai_extracted_text[:150].replace('\n', ' ')
                has_line_marker = '[L0' in ai_extracted_text or '[L1' in ai_extracted_text
                print(f"   包含行號標記: {'是' if has_line_marker else '否'}")
                print(f"   預覽: {preview}...")
            
            # 顯示 logical_chunks 的結構
            if has_logical_chunks:
                first_chunk = logical_chunks[0]
                print(f"   第一個 chunk: start_id={first_chunk.get('start_id')}, end_id={first_chunk.get('end_id')}, type={first_chunk.get('type')}")

if __name__ == "__main__":
    asyncio.run(main())
