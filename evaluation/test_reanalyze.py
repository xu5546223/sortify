"""
測試重新分析一個圖片文檔，確認 line_mapping 和 extracted_text 是否正確儲存
"""
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
        headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
        
        # 獲取一個圖片文檔
        docs_resp = await session.get(
            f'{api_url}/api/v1/documents/',
            headers=headers,
            params={'limit': 1}
        )
        docs_data = await docs_resp.json()
        documents = docs_data.get('items', [])
        
        if not documents:
            print("沒有找到文檔")
            return
        
        doc = documents[0]
        doc_id = doc.get('id')
        filename = doc.get('filename')
        file_type = doc.get('file_type', '')
        
        print(f"選擇文檔: {filename}")
        print(f"ID: {doc_id}")
        print(f"類型: {file_type}")
        
        # 檢查是否為圖片
        is_image = 'image' in file_type.lower()
        print(f"是否為圖片: {is_image}")
        
        # 檢查當前狀態
        print(f"\n--- 重新分析前 ---")
        print(f"line_mapping: {'有' if doc.get('line_mapping') else '無'}")
        print(f"extracted_text: {'有' if doc.get('extracted_text') else '無'}")
        
        # 觸發重新分析
        print(f"\n🔄 觸發重新分析...")
        trigger_resp = await session.patch(
            f'{api_url}/api/v1/documents/{doc_id}',
            headers=headers,
            json={"trigger_content_processing": True}
        )
        
        if trigger_resp.status != 200:
            error = await trigger_resp.text()
            print(f"❌ 觸發失敗: {error}")
            return
        
        print("✅ 已觸發分析，等待 10 秒...")
        await asyncio.sleep(10)
        
        # 重新獲取文檔檢查結果
        doc_resp = await session.get(
            f'{api_url}/api/v1/documents/{doc_id}',
            headers=headers
        )
        updated_doc = await doc_resp.json()
        
        print(f"\n--- 重新分析後 ---")
        print(f"status: {updated_doc.get('status')}")
        
        line_mapping = updated_doc.get('line_mapping')
        extracted_text = updated_doc.get('extracted_text')
        
        print(f"line_mapping: {'✅ 有 (' + str(len(line_mapping)) + ' 行)' if line_mapping else '❌ 無'}")
        print(f"extracted_text: {'✅ 有 (' + str(len(extracted_text)) + ' 字符)' if extracted_text else '❌ 無'}")
        
        if extracted_text:
            # 檢查是否包含行號標記
            has_marker = '[L0' in extracted_text or '[L1' in extracted_text
            print(f"包含行號標記: {'❌ 是 (問題!)' if has_marker else '✅ 否 (正確)'}")
            print(f"預覽: {extracted_text[:150]}...")
        
        # 檢查 logical_chunks
        analysis = updated_doc.get('analysis', {})
        ai_output = analysis.get('ai_analysis_output', {}) or {}
        logical_chunks = ai_output.get('logical_chunks', [])
        print(f"logical_chunks: {'✅ 有 (' + str(len(logical_chunks)) + ' 個)' if logical_chunks else '❌ 無'}")
        
        if logical_chunks:
            first_chunk = logical_chunks[0]
            print(f"第一個 chunk: start_id={first_chunk.get('start_id')}, end_id={first_chunk.get('end_id')}")

if __name__ == "__main__":
    asyncio.run(main())
