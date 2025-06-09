import json
import asyncio
import logging
import argparse
import aiohttp
import os
import time
import signal
from typing import List, Dict, Any, Optional
from datetime import datetime
import uuid
from pathlib import Path
import random
from dotenv import load_dotenv
import google.generativeai as genai

# === 環境配置載入 ===
def load_environment_config():
    """載入環境配置，按優先順序查找 .env 文件"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    
    print("🔍 檢查運行環境...")
    print(f"📁 腳本目錄: {script_dir}")
    print(f"📁 項目根目錄: {project_root}")
    
    # 按優先順序查找 .env 文件
    possible_paths = [
        os.path.join(script_dir, '.env'),           # evaluation/.env
        os.path.join(project_root, '.env'),         # 項目根目錄/.env
        os.path.join(project_root, 'backend', '.env')  # backend/.env
    ]
    
    print("🔍 查找 .env 文件...")
    dotenv_path = None
    for i, path in enumerate(possible_paths, 1):
        print(f"   {i}. 檢查: {path}")
        if os.path.exists(path):
            print(f"      ✅ 找到文件")
            dotenv_path = path
            break
        else:
            print(f"      ❌ 文件不存在")
    
    if not dotenv_path:
        print("\n❌ 錯誤: 找不到 .env 文件")
        print("📝 請在以下任一位置創建 .env 文件:")
        for path in possible_paths:
            print(f"   - {path}")
        print("\n💡 可以參考 evaluation/.env.example 創建配置文件")
        exit(1)
    
    # 載入環境變數
    print(f"📝 正在載入: {dotenv_path}")
    result = load_dotenv(dotenv_path=dotenv_path, override=True)
    if result:
        print(f"✅ 成功載入環境配置文件: {dotenv_path}")
    else:
        print(f"⚠️  環境文件載入可能有問題: {dotenv_path}")
    
    return dotenv_path

def validate_required_env_vars():
    """驗證必要的環境變數"""
    required_vars = {
        'API_URL': '後端API的基礎URL (例如: http://localhost:8000)',
        'USERNAME': '登入用的用戶名',
        'PASSWORD': '登入用的密碼',
        'GOOGLE_API_KEY': 'Google Gemini API金鑰'
    }
    
    print("🔍 檢查環境變數...")
    missing_vars = []
    found_vars = []
    
    for var, description in required_vars.items():
        value = os.getenv(var)
        if not value or not value.strip():
            missing_vars.append((var, description))
            print(f"❌ {var}: 未設置或為空")
        else:
            found_vars.append(var)
            # 對於敏感信息只顯示前幾個字符
            if var in ['PASSWORD', 'GOOGLE_API_KEY']:
                display_value = value[:10] + "..." if len(value) > 10 else value[:5] + "..."
            else:
                display_value = value
            print(f"✅ {var}: {display_value}")
    
    if missing_vars:
        print("\n❌ 缺少必要的環境變數:")
        for var, desc in missing_vars:
            print(f"   - {var}: {desc}")
        
        print("\n📝 .env 文件配置示例:")
        print("API_URL=http://localhost:8000")
        print("USERNAME=your_username")
        print("PASSWORD=your_password")
        print("GOOGLE_API_KEY=your_google_api_key")
        print("# 可選配置")
        print("GENERATION_MODEL=gemini-1.5-flash")
        print("VALIDATION_MODEL=gemini-1.5-flash")
        print("API_RATE_LIMIT=15")
        print("ENABLE_AI_VALIDATION=true")
        print("DETAIL_QUESTIONS_PER_DOC=2")
        
        exit(1)
    
    print(f"✅ 所有 {len(found_vars)} 個必要的環境變數都已正確設置")

# 載入和驗證環境配置
load_environment_config()
validate_required_env_vars()

# === 日誌配置 ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(module)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('generate_test_dataset.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

class GoogleAPIRateLimiter:
    """Google免費API速率限制器 - 15次/分鐘"""
    
    def __init__(self, requests_per_minute: int = 15):
        self.requests_per_minute = requests_per_minute
        self.min_interval = 60.0 / requests_per_minute  # 4秒間隔
        self.request_times = []
        self.lock = asyncio.Lock()
        
        logger.info(f"🕐 API速率限制器初始化: {requests_per_minute}次/分鐘，最小間隔: {self.min_interval:.1f}秒")
    
    async def wait_if_needed(self):
        """等待適當的時間間隔以符合速率限制"""
        async with self.lock:
            now = time.time()
            
            # 清理1分鐘前的記錄
            self.request_times = [t for t in self.request_times if now - t < 60]
            
            # 如果達到分鐘限制，等待到最早請求的1分鐘後
            if len(self.request_times) >= self.requests_per_minute:
                wait_time = 60 - (now - self.request_times[0]) + 0.1  # 加0.1秒緩衝
                if wait_time > 0:
                    logger.info(f"⏳ 達到分鐘限制，等待 {wait_time:.1f} 秒...")
                    await asyncio.sleep(wait_time)
                    now = time.time()
                    self.request_times = [t for t in self.request_times if now - t < 60]
            
            # 確保最小間隔
            if self.request_times:
                time_since_last = now - self.request_times[-1]
                if time_since_last < self.min_interval:
                    wait_time = self.min_interval - time_since_last
                    logger.debug(f"⏱️  等待最小間隔: {wait_time:.1f} 秒")
                    await asyncio.sleep(wait_time)
                    now = time.time()
            
            # 記錄這次請求
            self.request_times.append(now)
            logger.debug(f"📊 當前請求計數: {len(self.request_times)}/分鐘")

class TestDatasetGenerator:
    """測試數據集生成器 - 直接使用Google API，實現1+N問題生成策略"""
    
    def __init__(self):
        """初始化生成器和API連接"""
        self.api_base_url = os.getenv('API_URL', 'http://localhost:8000')
        self.api_username = os.getenv('USERNAME')
        self.api_password = os.getenv('PASSWORD')
        
        # Google API 配置
        self.google_api_key = os.getenv('GOOGLE_API_KEY')
        if not self.google_api_key:
            raise ValueError("請在.env文件中設置 GOOGLE_API_KEY")
        
        genai.configure(api_key=self.google_api_key)
        
        # 模型配置 - 從環境變量讀取
        self.generation_model_name = os.getenv('GENERATION_MODEL', 'gemini-1.5-flash')
        self.validation_model_name = os.getenv('VALIDATION_MODEL', 'gemini-1.5-flash')
        
        print(f"🤖 生成模型: {self.generation_model_name}")
        print(f"🧐 驗證模型: {self.validation_model_name}")
        
        self.generation_model = genai.GenerativeModel(self.generation_model_name)
        self.validation_model = genai.GenerativeModel(self.validation_model_name)
        
        if not self.api_username or not self.api_password:
            raise ValueError("請在.env文件中設置 USERNAME 和 PASSWORD")
        
        # 用於緩存從API獲取的文檔塊
        self._chunks_cache = {}
        
        self.session = None
        self.access_token = None
        
        # 生成配置
        self.concurrent_limit = int(os.getenv('CONCURRENT_LIMIT', '1'))
        self.enable_ai_validation = os.getenv('ENABLE_AI_VALIDATION', 'true').lower() == 'true'
        
        # Google API速率限制
        api_rate_limit = int(os.getenv('API_RATE_LIMIT', '15'))  # 15次/分鐘
        self.rate_limiter = GoogleAPIRateLimiter(api_rate_limit)
        
        # 問題生成策略配置
        self.detail_questions_per_doc = int(os.getenv('DETAIL_QUESTIONS_PER_DOC', '2'))  # 每個文檔生成2個細節級問題
        
        # 優雅終止和中間保存配置
        self.graceful_shutdown = False
        self.intermediate_save_interval = 10  # 每處理10個文檔保存一次
        self.current_output_path = None
        self.current_qa_pairs = []
        
        logger.info(f"測試數據集生成器初始化完成")
        logger.info(f"🤖 生成模型: {self.generation_model_name}")
        logger.info(f"🧐 驗證模型: {self.validation_model_name}")
        logger.info(f"API速率限制: {api_rate_limit}次/分鐘")
        logger.info(f"AI驗證: {'啟用' if self.enable_ai_validation else '禁用'}")
        logger.info(f"每個文檔細節級問題數量: {self.detail_questions_per_doc}")
        logger.info(f"💾 中間保存間隔: 每{self.intermediate_save_interval}個文檔")
        
        # 設置信號處理
        self._setup_signal_handlers()

    async def initialize_api_connection(self):
        """初始化API連接和認證"""
        self.session = aiohttp.ClientSession()
        if not await self._login_and_get_token():
            raise Exception("無法獲取認證 token")
        logger.info("API認證成功")

    async def _login_and_get_token(self) -> bool:
        """登入並獲取 JWT token"""
        login_url = f"{self.api_base_url}/api/v1/auth/token"
        login_data = {"username": self.api_username, "password": self.api_password}
        
        try:
            async with self.session.post(login_url, data=login_data) as response:
                response.raise_for_status()
                result = await response.json()
                self.access_token = result.get("access_token")
                if self.access_token:
                    logger.info("登入成功，獲取到 JWT token")
                    return True
                else:
                    logger.error("登入失敗：響應中沒有 access_token")
                    return False
        except Exception as e:
            logger.error(f"登入時發生錯誤: {e}")
            return False

    def get_auth_headers(self) -> Dict[str, str]:
        """獲取認證標頭"""
        if not self.access_token:
            raise ValueError("未獲取到 access_token，請先登入")
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
    
    def _clean_json_response(self, response_text: str) -> str:
        """清理 Google AI 回應中的 markdown 代碼塊標記，支援多行JSON"""
        # 移除 ```json 和 ``` 標記
        cleaned = response_text.strip()
        
        # 檢查是否以 ```json 開頭
        if cleaned.startswith('```json'):
            cleaned = cleaned[7:]  # 移除 ```json
        elif cleaned.startswith('```'):
            cleaned = cleaned[3:]  # 移除 ```
        
        # 檢查是否以 ``` 結尾
        if cleaned.endswith('```'):
            cleaned = cleaned[:-3]  # 移除結尾的 ```
        
        # 處理可能的換行符和多餘空格
        cleaned = cleaned.strip()
        
        # 如果文本被截斷，嘗試找到完整的JSON
        if not cleaned.endswith('}') and '}' in cleaned:
            # 找到最後一個完整的 } 
            last_brace = cleaned.rfind('}')
            if last_brace != -1:
                cleaned = cleaned[:last_brace + 1]
        
        return cleaned.strip()

    async def get_all_user_documents(self) -> List[Dict]:
        """獲取用戶所有文檔"""
        headers = self.get_auth_headers()
        url = f"{self.api_base_url}/api/v1/documents/"
        
        all_documents = []
        skip = 0
        limit = 100
        
        while True:
            params = {"limit": limit, "skip": skip}
            
            try:
                async with self.session.get(url, headers=headers, params=params) as response:
                    response.raise_for_status()
                    result = await response.json()
                    documents = result.get("items", [])
                    
                    if not documents:
                        break
                        
                    all_documents.extend(documents)
                    skip += limit
                    
                    logger.debug(f"已獲取 {len(all_documents)} 個文檔...")
                    
            except Exception as e:
                logger.error(f"獲取用戶文檔失敗: {e}")
                break
        
        logger.info(f"總共獲取到 {len(all_documents)} 個用戶文檔")
        return all_documents

    async def _get_all_chunks_for_doc(self, doc_id: str) -> List[Dict]:
        """
        通過新的API端點，直接獲取一個文檔的所有塊（摘要和文本）。
        實現了本地緩存以避免重複調用。
        """
        if doc_id in self._chunks_cache:
            return self._chunks_cache[doc_id]

        headers = self.get_auth_headers()
        url = f"{self.api_base_url}/api/v1/vector-db/documents/{doc_id}/chunks"
        
        try:
            async with self.session.get(url, headers=headers) as response:
                # 新增調試日誌: 無論如何都打印狀態和內容
                logger.debug(f"API調用: GET {url} | 狀態碼: {response.status}")
                
                if response.status == 200:
                    chunks = await response.json()
                    # 提高日誌級別以便在終端中總是可見
                    logger.info(f"為文檔 {doc_id} 從API收到 {len(chunks)} 個塊")
                    self._chunks_cache[doc_id] = chunks
                    return chunks
                else:
                    # 如果狀態碼不為200，記錄錯誤並返回空列表
                    error_text = await response.text()
                    logger.error(f"為文檔 {doc_id} 獲取塊時API返回錯誤狀態 {response.status}: {error_text}")
                    self._chunks_cache[doc_id] = []
                    return []

        except aiohttp.ClientError as e:
            logger.error(f"為文檔 {doc_id} 獲取所有塊時發生網絡錯誤: {e}")
            self._chunks_cache[doc_id] = []
            return []

    async def get_document_summary(self, doc_id: str, doc_title: str) -> Optional[str]:
        """從所有塊中過濾出文檔摘要"""
        all_chunks = await self._get_all_chunks_for_doc(doc_id)
        if not all_chunks:
            return None
        
        # 修正：使用 'type' == 'summary' 來識別摘要塊
        for chunk in all_chunks:
            if chunk.get('metadata', {}).get('type') == 'summary':
                # 調試：打印摘要塊的完整結構
                logger.info(f"找到摘要塊！完整結構: {chunk}")
                
                # 修正：摘要內容直接存儲在 summary_text 字段中
                summary_content = chunk.get('summary_text')
                if not summary_content:
                    # 後備方案：嘗試從 payload.page_content 獲取
                    summary_content = chunk.get('payload', {}).get('page_content')
                
                if summary_content:
                    logger.info(f"成功提取摘要內容，長度: {len(summary_content)}")
                    return summary_content
                else:
                    logger.warning(f"摘要塊存在但內容為空。summary_text: {chunk.get('summary_text')}, payload: {chunk.get('payload')}")
        
        logger.warning(f"在文檔 {doc_id} 的 {len(all_chunks)} 個塊中找不到摘要塊")
        # 新增調試日誌: 打印所有塊的元數據以供分析
        if all_chunks:
            logger.debug(f"文檔 {doc_id} 的塊元數據如下:")
            for i, chunk in enumerate(all_chunks):
                logger.debug(f"  塊 {i+1}: metadata={chunk.get('metadata')}")
        return None

    async def get_document_chunks(self, doc_id: str, doc_title: str) -> List[Dict]:
        """從所有塊中過濾出文本內容塊"""
        all_chunks = await self._get_all_chunks_for_doc(doc_id)
        if not all_chunks:
            return []

        # 修正：使用 'type' == 'chunk' 來識別文本塊
        text_chunks = []
        for chunk in all_chunks:
            if chunk.get('metadata', {}).get('type') == 'chunk':
                # 修正：處理文本塊的內容提取
                chunk_content = chunk.get('summary_text')
                if not chunk_content:
                    # 後備方案：嘗試從 payload.page_content 獲取
                    chunk_content = chunk.get('payload', {}).get('page_content')
                
                if chunk_content and len(chunk_content.strip()) >= 20:  # 過濾太短的塊
                    # 構造統一的數據結構
                    formatted_chunk = {
                        'chunk_id': chunk.get('id', str(uuid.uuid4())),
                        'content': chunk_content,
                        'document_id': doc_id,
                        'document_title': doc_title,
                        'metadata': chunk.get('metadata', {}),
                        'similarity_score': chunk.get('similarity_score', 1.0)
                    }
                    text_chunks.append(formatted_chunk)
        
        logger.info(f"為文檔 {doc_id} 獲得 {len(text_chunks)} 個有效文本塊")
        return text_chunks

    async def generate_summary_question_via_google(self, doc_summary: str, doc_title: str, doc_id: str) -> Optional[Dict]:
        """直接通過Google API生成主題級問題"""
        if not doc_summary or not doc_summary.strip():
            return None
            
        # 等待速率限制
        await self.rate_limiter.wait_if_needed()
        
        prompt = f"""請基於以下文檔的摘要資訊，生成一個主題級問題。

文檔標題：{doc_title}
文檔摘要：{doc_summary}

要求：
1. 問題應該測試對文檔整體核心主旨和主要內容的理解
2. 問題要自然、具體，適合用於檢索系統評估
3. 答案應該能從文檔的摘要內容中找到
4. 問題類型應該是"主題級"問題

請只回答一個JSON物件，格式如下：
{{"question": "問題內容", "answer": "基於摘要的答案", "question_type": "主題級", "confidence": 0.9}}

只回答JSON，不要其他文字。"""

        try:
            response = self.generation_model.generate_content(prompt)
            answer_text = response.text.strip()
            
            # 清理回應文本，移除可能的 markdown 代碼塊標記
            cleaned_text = self._clean_json_response(answer_text)
            
            # 嘗試解析JSON
            try:
                qa_data = json.loads(cleaned_text)
                
                if not qa_data.get('question') or not qa_data.get('answer'):
                    logger.warning(f"Google API回應缺少問題或答案: {qa_data}")
                    return None
                
                logger.debug(f"成功生成主題級問題: {qa_data['question'][:50]}...")
                
                return {
                    'question': qa_data['question'],
                    'ground_truth': qa_data['answer'],
                    'expected_relevant_doc_ids': [doc_id],
                    'question_type': '主題級',
                    'confidence': qa_data.get('confidence', 0.9),
                    'document_id': doc_id,
                    'document_title': doc_title,
                    'generated_at': datetime.now().isoformat(),
                    'generation_method': 'google_api_summary',
                    'generation_model': self.generation_model_name
                }
                
            except json.JSONDecodeError as e:
                logger.error(f"Google API回應JSON解析錯誤: {e}, 清理後文本: {cleaned_text[:200]}...")
                return None
                
        except Exception as e:
            logger.error(f"生成主題級問題時發生錯誤: {e}", exc_info=True)
            return None

    async def generate_detail_question_via_google(self, chunk: Dict) -> Optional[Dict]:
        """直接通過Google API生成細節級問題"""
        content = chunk.get('content', '').strip()
        if not content:
            return None
        
        # 等待速率限制
        await self.rate_limiter.wait_if_needed()
        
        prompt = f"""請基於以下文檔片段，生成一個細節級問題。

文檔片段內容：{content}

要求：
1. 問題應該測試對片段中具體事實、細節的精確理解
2. 問題要針對片段中的具體信息（如數字、名稱、日期、定義等）
3. 答案必須只能從這個特定片段中找到
4. 問題要自然、具體，適合用於檢索系統評估
5. 問題類型應該是"細節級"問題

請只回答一個JSON物件，格式如下：
{{"question": "問題內容", "answer": "基於片段的具體答案", "question_type": "細節級", "confidence": 0.8}}

只回答JSON，不要其他文字。"""

        try:
            response = self.generation_model.generate_content(prompt)
            answer_text = response.text.strip()
            
            # 清理回應文本，移除可能的 markdown 代碼塊標記
            cleaned_text = self._clean_json_response(answer_text)
            
            # 嘗試解析JSON
            try:
                qa_data = json.loads(cleaned_text)
                
                if not qa_data.get('question') or not qa_data.get('answer'):
                    logger.warning(f"Google API回應缺少問題或答案: {qa_data}")
                    return None
                
                logger.debug(f"成功生成細節級問題: {qa_data['question'][:50]}...")
                
                return {
                    'question': qa_data['question'],
                    'ground_truth': qa_data['answer'],
                    'expected_relevant_doc_ids': [chunk.get('document_id', '')],
                    'question_type': '細節級',
                    'confidence': qa_data.get('confidence', 0.8),
                    'source_chunk_id': chunk.get('chunk_id', ''),
                    'document_id': chunk.get('document_id', ''),
                    'document_title': chunk.get('document_title', ''),
                    'generated_at': datetime.now().isoformat(),
                    'generation_method': 'google_api_chunk',
                    'generation_model': self.generation_model_name
                }
                
            except json.JSONDecodeError as e:
                logger.error(f"Google API回應JSON解析錯誤: {e}, 清理後文本: {cleaned_text[:200]}...")
                return None
                
        except Exception as e:
            logger.error(f"生成細節級問題時發生錯誤: {e}", exc_info=True)
            return None

    async def validate_qa_pair_via_google(self, qa_pair: Dict) -> bool:
        """通過Google API驗證問答對質量"""
        if not self.enable_ai_validation:
            return True
            
        # 等待速率限制
        await self.rate_limiter.wait_if_needed()
        
        question = qa_pair.get('question', '')
        answer = qa_pair.get('ground_truth', '')
        
        validation_prompt = f"""
請評估以下問答對的質量：

問題：{question}
答案：{answer}

評估標準：
1. 問題是否清晰、具體、有意義？
2. 答案是否準確、完整、與問題相關？
3. 問題是否適合用於檢索系統評估？
4. 整體質量是否達到測試數據標準？

請以以下JSON格式回答：
{{
    "is_valid": true/false,
    "quality_score": 0.0-1.0,
    "issues": ["發現的問題列表"],
    "recommendation": "改進建議"
}}
"""
        
        try:
            response = self.validation_model.generate_content(validation_prompt)
            answer_text = response.text.strip()
            
            # 清理回應文本，移除可能的 markdown 代碼塊標記
            cleaned_text = self._clean_json_response(answer_text)
            
            try:
                validation_data = json.loads(cleaned_text)
                is_valid = validation_data.get('is_valid', False)
                quality_score = validation_data.get('quality_score', 0.0)
                
                # 設定質量閾值 - 可調整標準 (0.5=寬鬆, 0.6=標準, 0.7=嚴格)
                return is_valid and quality_score >= 0.6
                
            except json.JSONDecodeError:
                logger.warning(f"驗證回應格式錯誤: {answer_text[:100]}...")
                logger.debug(f"清理後文本: {cleaned_text[:100]}...")
                return False
                
        except Exception as e:
            logger.warning(f"驗證問答對時發生錯誤: {e}")
            return True  # 如果驗證失敗，默認接受

    def estimate_generation_time(self, num_documents: int) -> Dict[str, float]:
        """估算生成時間"""
        # 每個文檔：1個主題級問題 + N個細節級問題
        questions_per_doc = 1 + self.detail_questions_per_doc
        total_questions = num_documents * questions_per_doc
        
        # 如果啟用驗證，每個問題需要額外的驗證調用
        api_calls_per_question = 2 if self.enable_ai_validation else 1
        total_api_calls = total_questions * api_calls_per_question
        
        # 基於15次/分鐘的限制計算
        estimated_minutes = total_api_calls / self.rate_limiter.requests_per_minute
        estimated_seconds = estimated_minutes * 60
        
        return {
            'num_documents': num_documents,
            'questions_per_doc': questions_per_doc,
            'total_questions': total_questions,
            'api_calls_per_question': api_calls_per_question,
            'total_api_calls': total_api_calls,
            'estimated_minutes': estimated_minutes,
            'estimated_seconds': estimated_seconds
        }

    async def generate_test_dataset(self, target_document_ratio: float = 0.5, output_path: str = None) -> Dict[str, Any]:
        """生成測試數據集主流程 - 1+N問題生成策略，支援優雅終止"""
        logger.info(f"開始生成測試數據集，文檔選擇比例: {target_document_ratio}")
        
        # 設置輸出路徑和初始化中間保存
        self.current_output_path = output_path
        self.current_qa_pairs = []
        
        # 步驟1: 獲取所有文檔
        logger.info("步驟1: 獲取用戶所有文檔...")
        all_documents = await self.get_all_user_documents()
        
        if not all_documents:
            raise Exception("無法獲取文檔，請檢查用戶是否有文檔數據")
        
        # 步驟2: 隨機選擇一半文檔
        num_selected = max(1, int(len(all_documents) * target_document_ratio))
        selected_documents = random.sample(all_documents, num_selected)
        
        logger.info(f"步驟2: 從 {len(all_documents)} 個文檔中隨機選擇 {num_selected} 個文檔")
        
        # 估算時間
        time_estimate = self.estimate_generation_time(num_selected)
        logger.info(f"⏱️  預估生成時間: {time_estimate['estimated_minutes']:.1f} 分鐘")
        logger.info(f"📞 預估API調用次數: {time_estimate['total_api_calls']} 次")
        logger.info(f"📋 每個文檔將生成: 1個主題級問題 + {self.detail_questions_per_doc}個細節級問題")
        if self.enable_ai_validation:
            logger.info(f"🔍 AI驗證已啟用，每個問題將進行質量驗證")
        logger.info(f"💾 支援 Ctrl+C 優雅終止，會自動保存已生成的問答對")
        
        # 步驟3: 為每個文檔生成1+N問題
        logger.info("步驟3: 開始生成問答對...")
        
        all_qa_pairs = []
        start_time = time.time()
        
        summary_question_count = 0
        detail_question_count = 0
        validated_count = 0
        
        for i, doc in enumerate(selected_documents):
            # 檢查是否需要優雅終止
            if self.graceful_shutdown:
                logger.info(f"收到終止信號，停止處理。已處理 {i}/{num_selected} 個文檔")
                break
            doc_id = doc.get('id', '')
            doc_title = doc.get('title') or doc.get('filename', 'Unknown')
            
            if not doc_id:
                logger.warning(f"文檔 {doc_title} 沒有ID，跳過")
                continue
            
            logger.info(f"📄 處理文檔 {i+1}/{num_selected}: {doc_title}")
            
            # 生成主題級問題（基於文檔摘要）
            logger.info(f"   🎯 生成主題級問題...")
            doc_summary = await self.get_document_summary(doc_id, doc_title)
            
            if doc_summary:
                summary_qa = await self.generate_summary_question_via_google(doc_summary, doc_title, doc_id)
                if summary_qa:
                    # 驗證問答對
                    if await self.validate_qa_pair_via_google(summary_qa):
                        all_qa_pairs.append(summary_qa)
                        self.current_qa_pairs = all_qa_pairs.copy()  # 更新中間保存副本
                        summary_question_count += 1
                        validated_count += 1
                        logger.info(f"   ✅ 主題級問題生成並驗證成功")
                    else:
                        logger.warning(f"   ❌ 主題級問題未通過驗證")
                else:
                    logger.warning(f"   ❌ 主題級問題生成失敗")
            else:
                logger.warning(f"   ⚠️  無法獲取文檔摘要，跳過主題級問題")
            
            # 生成細節級問題（基於文檔chunks）
            logger.info(f"   🔍 生成細節級問題...")
            doc_chunks = await self.get_document_chunks(doc_id, doc_title)
            
            if doc_chunks:
                # 選擇最好的N個chunks
                selected_chunks = doc_chunks[:self.detail_questions_per_doc]
                
                for j, chunk in enumerate(selected_chunks):
                    detail_qa = await self.generate_detail_question_via_google(chunk)
                    if detail_qa:
                        # 驗證問答對
                        if await self.validate_qa_pair_via_google(detail_qa):
                            all_qa_pairs.append(detail_qa)
                            self.current_qa_pairs = all_qa_pairs.copy()  # 更新中間保存副本
                            detail_question_count += 1
                            validated_count += 1
                            logger.info(f"   ✅ 細節級問題 {j+1} 生成並驗證成功")
                        else:
                            logger.warning(f"   ❌ 細節級問題 {j+1} 未通過驗證")
                    else:
                        logger.warning(f"   ❌ 細節級問題 {j+1} 生成失敗")
            else:
                logger.warning(f"   ⚠️  無法獲取文檔chunks，跳過細節級問題")
            
            # 中間保存檢查
            if output_path and (i + 1) % self.intermediate_save_interval == 0:
                self._save_intermediate_results()
                logger.info(f"💾 已自動保存進度 ({i+1}/{num_selected} 文檔)")
            
            # 顯示進度
            elapsed = time.time() - start_time
            if i > 0:
                avg_time_per_doc = elapsed / (i + 1)
                remaining_docs = num_selected - (i + 1)
                estimated_remaining = avg_time_per_doc * remaining_docs
                logger.info(f"📊 進度: {i+1}/{num_selected} 文檔處理完成，預估剩餘時間: {estimated_remaining/60:.1f}分鐘")
        
        # 生成統計信息
        total_time = time.time() - start_time
        total_generated = summary_question_count + detail_question_count
        expected_total = num_selected * (1 + self.detail_questions_per_doc)
        
        statistics = {
            "total_documents_available": len(all_documents),
            "documents_selected": num_selected,
            "document_selection_ratio": target_document_ratio,
            "summary_questions_generated": summary_question_count,
            "detail_questions_generated": detail_question_count,
            "total_qa_pairs": len(all_qa_pairs),
            "total_generated_before_validation": total_generated,
            "validation_success_count": validated_count,
            "questions_per_document_target": 1 + self.detail_questions_per_doc,
            "questions_per_document_actual": len(all_qa_pairs) / num_selected if num_selected > 0 else 0,
            "generation_success_rate": total_generated / expected_total if expected_total > 0 else 0,
            "validation_success_rate": validated_count / total_generated if total_generated > 0 else 0,
            "overall_success_rate": len(all_qa_pairs) / expected_total if expected_total > 0 else 0,
            "total_generation_time_seconds": total_time,
            "average_time_per_document": total_time / num_selected if num_selected > 0 else 0,
            "api_rate_limit": self.rate_limiter.requests_per_minute,
            "ai_validation_enabled": self.enable_ai_validation,
            "generation_model": self.generation_model_name,
            "validation_model": self.validation_model_name,
            "generated_at": datetime.now().isoformat(),
            "generation_strategy": "1+N_questions_per_document"
        }
        
        logger.info(f"🎉 測試數據集生成完成！")
        logger.info(f"📊 統計信息:")
        logger.info(f"   - 可用文檔: {statistics['total_documents_available']}")
        logger.info(f"   - 選擇文檔: {statistics['documents_selected']}")
        logger.info(f"   - 主題級問題: {statistics['summary_questions_generated']}")
        logger.info(f"   - 細節級問題: {statistics['detail_questions_generated']}")
        logger.info(f"   - 總問答對: {statistics['total_qa_pairs']}")
        logger.info(f"   - 生成成功率: {statistics['generation_success_rate']:.2%}")
        logger.info(f"   - 驗證成功率: {statistics['validation_success_rate']:.2%}")
        logger.info(f"   - 整體成功率: {statistics['overall_success_rate']:.2%}")
        logger.info(f"   - 總耗時: {statistics['total_generation_time_seconds']/60:.1f} 分鐘")
        logger.info(f"   - 平均時間/文檔: {statistics['average_time_per_document']:.1f} 秒")
        
        # 保存結果
        if output_path:
            # 確保輸出路徑有正確的副檔名
            eval_output_path = output_path
            if not eval_output_path.endswith('.json'):
                eval_output_path += '.json'
                logger.info(f"已自動添加 .json 副檔名: {eval_output_path}")
            
            # 為評估腳本保存純測試案例格式 (標準JSON數組)
            with open(eval_output_path, 'w', encoding='utf-8') as f:
                json.dump(all_qa_pairs, f, ensure_ascii=False, indent=2)
            logger.info(f"📁 評估用測試數據集已保存到: {eval_output_path}")
            logger.info(f"📊 格式: 純JSON數組，包含 {len(all_qa_pairs)} 個測試案例")
            
            # 保存包含完整元數據的詳細版本
            detailed_output_path = eval_output_path.replace('.json', '_detailed.json')
            detailed_output_data = {
                "test_cases": all_qa_pairs,
                "metadata": {
                    "dataset_version": "2.0",
                    "generated_by": "google_api_1_plus_n_strategy",
                    "statistics": statistics,
                    "generation_completed": not self.graceful_shutdown
                }
            }
            
            with open(detailed_output_path, 'w', encoding='utf-8') as f:
                json.dump(detailed_output_data, f, ensure_ascii=False, indent=2)
            logger.info(f"📁 詳細測試數據集已保存到: {detailed_output_path}")
            
            # 如果是優雅終止，額外說明
            if self.graceful_shutdown:
                logger.warning(f"⚠️  生成被中斷，但已保存 {len(all_qa_pairs)} 個有效問答對")
        
        return {
            "qa_pairs": all_qa_pairs,
            "statistics": statistics
        }

    def _setup_signal_handlers(self):
        """設置信號處理"""
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    def _handle_signal(self, signum, frame):
        """處理信號"""
        logger.info(f"收到信號 {signum}，開始優雅終止...")
        self.graceful_shutdown = True
        # 立即保存當前進度
        if self.current_qa_pairs and self.current_output_path:
            self._save_intermediate_results()

    def _save_intermediate_results(self):
        """保存中間結果"""
        if not self.current_qa_pairs or not self.current_output_path:
            return
        
        try:
            # 確保輸出路徑有正確的副檔名
            output_path = self.current_output_path
            if not output_path.endswith('.json'):
                output_path += '.json'
            
            # 保存評估用的純測試案例格式
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(self.current_qa_pairs, f, ensure_ascii=False, indent=2)
            
            # 保存帶統計信息的詳細版本
            detailed_path = output_path.replace('.json', '_detailed.json')
            detailed_data = {
                "test_cases": self.current_qa_pairs,
                "metadata": {
                    "dataset_version": "2.0",
                    "generated_by": "google_api_1_plus_n_strategy_interrupted",
                    "intermediate_save": True,
                    "save_timestamp": datetime.now().isoformat(),
                    "total_qa_pairs": len(self.current_qa_pairs)
                }
            }
            
            with open(detailed_path, 'w', encoding='utf-8') as f:
                json.dump(detailed_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"💾 中間結果已保存: {len(self.current_qa_pairs)} 個問答對")
            logger.info(f"📁 評估格式: {output_path}")
            logger.info(f"📁 詳細格式: {detailed_path}")
            
        except Exception as e:
            logger.error(f"保存中間結果時發生錯誤: {e}")

    async def close(self):
        """關閉連接"""
        if self.session and not self.session.closed:
            await self.session.close()

async def main():
    """主函數"""
    parser = argparse.ArgumentParser(description='基於Google API的1+N測試數據集生成器')
    parser.add_argument('--document-ratio', type=float, default=0.5, help='選擇文檔的比例 (預設: 0.5，即一半文檔)')
    parser.add_argument('--detail-questions', type=int, default=2, help='每個文檔生成的細節級問題數量 (預設: 2)')
    parser.add_argument('--output', type=str, help='輸出文件路徑')
    parser.add_argument('--disable-validation', action='store_true', help='禁用AI驗證以節省API調用')
    
    args = parser.parse_args()
    
    # 檢查必要的環境變數
    required_vars = ['API_URL', 'USERNAME', 'PASSWORD', 'GOOGLE_API_KEY']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        logger.error(f"缺少必要的環境變數: {', '.join(missing_vars)}")
        logger.error("請在 .env 文件中配置這些變數")
        return
    
    # 設定輸出路徑，確保有正確的 .json 副檔名
    if not args.output:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        args.output = f"test_dataset_1plus{args.detail_questions}_{timestamp}.json"
    else:
        # 如果用戶指定了輸出路徑，確保有 .json 副檔名
        if not args.output.endswith('.json'):
            args.output += '.json'
            logger.info(f"已自動添加 .json 副檔名: {args.output}")
    
    # 設定細節級問題數量
    os.environ['DETAIL_QUESTIONS_PER_DOC'] = str(args.detail_questions)
    
    # 設定驗證選項
    if args.disable_validation:
        os.environ['ENABLE_AI_VALIDATION'] = 'false'
        logger.info("🚫 AI驗證已禁用")
    
    generator = TestDatasetGenerator()
    
    try:
        await generator.initialize_api_connection()
        
        result = await generator.generate_test_dataset(
            target_document_ratio=args.document_ratio,
            output_path=args.output
        )
        
        # 輸出統計信息
        stats = result['statistics']
        print(f"\n🎉 測試數據集生成完成！")
        print(f"📊 最終統計:")
        print(f"   - 可用文檔總數: {stats['total_documents_available']}")
        print(f"   - 選擇文檔數量: {stats['documents_selected']} ({stats['document_selection_ratio']:.1%})")
        print(f"   - 主題級問題: {stats['summary_questions_generated']}")
        print(f"   - 細節級問題: {stats['detail_questions_generated']}")
        print(f"   - 總問答對數量: {stats['total_qa_pairs']}")
        print(f"   - 每文檔實際問題數: {stats['questions_per_document_actual']:.1f}")
        print(f"   - 生成成功率: {stats['generation_success_rate']:.2%}")
        print(f"   - 驗證成功率: {stats['validation_success_rate']:.2%}")
        print(f"   - 整體成功率: {stats['overall_success_rate']:.2%}")
        print(f"   - 總耗時: {stats['total_generation_time_seconds']/60:.1f} 分鐘")
        print(f"   - 平均時間/文檔: {stats['average_time_per_document']:.1f} 秒")
        print(f"📁 評估用文件: {args.output}")
        print(f"📁 詳細文件: {args.output.replace('.json', '_detailed.json')}")
        
    except Exception as e:
        logger.error(f"生成測試數據集失敗: {e}")
        raise
    finally:
        await generator.close()

if __name__ == "__main__":
    asyncio.run(main()) 