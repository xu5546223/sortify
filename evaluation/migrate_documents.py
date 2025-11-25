"""
遷移腳本：為現有文檔補充 extracted_text 和 line_mapping

這個腳本會：
1. 從 ai_analysis_output.extracted_text 提取帶行號的文本
2. 移除行號標記，生成純文本
3. 生成 line_mapping
4. 更新文檔的頂層欄位
"""
import asyncio
import aiohttp
import os
import re
from dotenv import load_dotenv

load_dotenv('.env', override=True)

# 行號標記正則表達式
LINE_MARKER_PATTERN = re.compile(r'\[L\d{3,}\]\s*')

def remove_line_markers(text: str) -> str:
    """移除行號標記"""
    return LINE_MARKER_PATTERN.sub('', text)

def generate_line_mapping(text: str) -> dict:
    """為純文本生成 line_mapping"""
    lines = text.split('\n')
    line_mapping = {}
    char_offset = 0
    
    for i, line in enumerate(lines):
        line_id = f"L{i+1:03d}"
        line_mapping[line_id] = {
            "line_number": i + 1,
            "char_start": char_offset,
            "char_end": char_offset + len(line),
            "length": len(line),
            "content_preview": line[:50] + "..." if len(line) > 50 else line
        }
        char_offset += len(line) + 1  # +1 for newline
    
    return line_mapping

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
        
        # 獲取所有文檔
        all_documents = []
        skip = 0
        limit = 100
        
        while True:
            docs_resp = await session.get(
                f'{api_url}/api/v1/documents/',
                headers=headers,
                params={'limit': limit, 'skip': skip}
            )
            docs_data = await docs_resp.json()
            documents = docs_data.get('items', [])
            all_documents.extend(documents)
            
            if len(documents) < limit:
                break
            skip += limit
        
        print(f"找到 {len(all_documents)} 個文檔")
        print("=" * 70)
        
        migrated_count = 0
        skipped_count = 0
        error_count = 0
        
        for doc in all_documents:
            doc_id = doc.get('id')
            filename = doc.get('filename', 'unknown')
            
            # 檢查是否已有 line_mapping
            if doc.get('line_mapping'):
                skipped_count += 1
                continue
            
            # 獲取 AI 分析結果中的 extracted_text
            analysis = doc.get('analysis', {})
            ai_output = analysis.get('ai_analysis_output', {}) or {}
            ai_extracted_text = ai_output.get('extracted_text', '')
            
            if not ai_extracted_text:
                print(f"⚠️ {filename[:30]}: 無 extracted_text，跳過")
                skipped_count += 1
                continue
            
            # 處理文本
            clean_text = remove_line_markers(ai_extracted_text)
            line_mapping = generate_line_mapping(clean_text)
            
            # 更新文檔
            update_payload = {
                "extracted_text": clean_text,
                "line_mapping": line_mapping
            }
            
            try:
                update_resp = await session.patch(
                    f'{api_url}/api/v1/documents/{doc_id}',
                    headers=headers,
                    json=update_payload
                )
                
                if update_resp.status == 200:
                    migrated_count += 1
                    print(f"✅ {filename[:40]}: 已遷移 ({len(clean_text)} 字符, {len(line_mapping)} 行)")
                else:
                    error_text = await update_resp.text()
                    print(f"❌ {filename[:30]}: 更新失敗 - {error_text[:100]}")
                    error_count += 1
            except Exception as e:
                print(f"❌ {filename[:30]}: 異常 - {e}")
                error_count += 1
        
        print("\n" + "=" * 70)
        print(f"📊 遷移完成:")
        print(f"   ✅ 成功遷移: {migrated_count}")
        print(f"   ⏭️ 跳過: {skipped_count}")
        print(f"   ❌ 錯誤: {error_count}")

if __name__ == "__main__":
    asyncio.run(main())
