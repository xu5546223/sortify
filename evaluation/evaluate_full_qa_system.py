import json
import asyncio
import logging
import sys
import argparse
import time
from typing import List, Dict, Optional, Any
import numpy as np
import pandas as pd
import aiohttp
from dotenv import load_dotenv
import os

# --- Foolproof .env loading ---
try:
    script_dir = os.path.dirname(os.path.abspath(__file__))
except NameError:
    script_dir = os.getcwd()

dotenv_path = os.path.join(script_dir, '.env')
if not os.path.exists(dotenv_path):
    project_root = os.path.dirname(script_dir)
    dotenv_path_alt = os.path.join(project_root, 'evaluation', '.env')
    if os.path.exists(dotenv_path_alt):
        dotenv_path = dotenv_path_alt
    else:
        dotenv_path_root = os.path.join(project_root, '.env')
        if os.path.exists(dotenv_path_root):
            dotenv_path = dotenv_path_root
        else:
            print(f"FATAL: '.env' file not found at various checked paths.")
            sys.exit(1)
load_dotenv(dotenv_path=dotenv_path, override=True)
print(f"Successfully loaded .env file from: {dotenv_path}")

# --- Ragas & LangChain Imports ---
try:
    from ragas import evaluate
    from ragas.metrics import context_precision, context_recall, faithfulness, answer_relevancy, answer_correctness
    from datasets import Dataset
    use_google = os.getenv('USE_GOOGLE_MODELS', 'true').lower() == 'true'
    if use_google:
        from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
        google_api_key = os.getenv('GOOGLE_API_KEY')
        if not google_api_key: raise ValueError("請設置 GOOGLE_API_KEY")
        llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=0, google_api_key=google_api_key)
        embeddings = GoogleGenerativeAIEmbeddings(model="models/text-embedding-004", google_api_key=google_api_key)
    else:
        from langchain_openai import ChatOpenAI, OpenAIEmbeddings
        llm = ChatOpenAI(model="gpt-4", temperature=0)
        embeddings = OpenAIEmbeddings(model="text-embedding-ada-002")
except ImportError as e:
    print(f"Critical Import Error: {e}. Please ensure dependencies are correctly installed.", file=sys.stderr)
    sys.exit(1)

# --- Logging & Other Setups ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(message)s')
logger = logging.getLogger(__name__)

try:
    from api_rate_limiter import APIRateLimiter
except ImportError:
    logger.warning("api_rate_limiter.py not found. Using a dummy rate limiter.")
    class APIRateLimiter:
        def __init__(self, requests_per_minute: int):
            self.delay = 60.0 / requests_per_minute if requests_per_minute > 0 else 0
        async def wait_if_needed_async(self):
            if self.delay > 0: await asyncio.sleep(self.delay)

# --- AIQA Settings for High Precision Mode ---
AIQA_HIGH_PRECISION_SETTINGS = {
    "use_ai_detailed_query": True, "use_semantic_search": True, "use_structured_filter": True,
    "context_limit": 20, "similarity_threshold": 0.2, "max_documents_for_selection": 12,
    "ai_selection_limit": 5, "query_rewrite_count": 5, "detailed_text_max_length": 15000,
    "max_chars_per_doc": 5000, "enable_query_expansion": True, "context_window_overlap": 0.2,
    "prompt_input_max_length": 8000
}


class FullQASystemEvaluator:
    """完整AI問答系統準確度評估器 - 使用Ragas框架和API調用"""
    
    def __init__(self):
        """初始化評估器"""
        self.api_base_url = os.getenv('API_URL', 'http://localhost:8000')
        self.api_username = os.getenv('USERNAME')
        self.api_password = os.getenv('PASSWORD')
        if not self.api_username or not self.api_password:
            raise ValueError("請在.env文件中設置 USERNAME 和 PASSWORD")
        self.session = None
        self.access_token = None
        
        # AIQA API速率限制器 (每次AIQA約6次Google AI調用，每分鐘10次限制 → 最多1.5次AIQA)
        self.aiqa_rate_limiter = APIRateLimiter(requests_per_minute=1)
        
        # Ragas評估速率限制器 (每分鐘15次AI調用)
        self.ragas_rate_limiter = APIRateLimiter(requests_per_minute=15)
        
        logger.info(f"AIQA API速率限制器已初始化 (每分鐘最多 1 次請求 - 配合Google AI限制)")
        logger.info(f"Ragas評估速率限制器已初始化 (每分鐘最多 15 次AI調用)")
    
    async def initialize_services(self):
        """初始化API連接並登入"""
        try:
            self.session = aiohttp.ClientSession()
            if not await self._login_and_get_token():
                raise Exception("無法獲取認證 token")
            await self._test_api_connection()
            logger.info("API連接初始化成功")
        except Exception as e:
            logger.error(f"API連接初始化失敗: {e}", exc_info=True)
            raise

    async def _login_and_get_token(self) -> bool:
        """登入並獲取JWT token，統一使用aiohttp"""
        login_url = f"{self.api_base_url}/api/v1/auth/token"
        login_data = {"username": self.api_username, "password": self.api_password}
        logger.info(f"嘗試登入到: {login_url}")
        try:
            async with self.session.post(login_url, data=login_data) as response:
                response.raise_for_status()
                result = await response.json()
                self.access_token = result.get("access_token")
                if self.access_token:
                    logger.info("登入成功，獲取到JWT token")
                    return True
                else:
                    logger.error("登入失敗：響應中沒有access_token")
                    return False
        except Exception as e:
            logger.error(f"登入時發生錯誤: {e}", exc_info=True)
            return False

    def get_auth_headers(self) -> Dict[str, str]:
        if not self.access_token:
            raise ValueError("未獲取到access_token")
        return {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}

    async def _test_api_connection(self):
        try:
            async with self.session.get(f"{self.api_base_url}/", headers=self.get_auth_headers()) as r:
                r.raise_for_status()
                logger.info("API連接測試成功")
        except Exception as e:
            logger.warning(f"API連接測試失敗: {e}")

    async def _qa_via_api(self, question: str, model_preference: Optional[str]) -> Dict[str, Any]:
        """通過API執行完整問答 - 使用AIQA專用速率限制"""
        await self.aiqa_rate_limiter.wait_if_needed_async()
        start_time = time.time()
        
        # 正確的API endpoint和payload格式
        url = f"{self.api_base_url}/api/v1/unified-ai/qa"
        payload = {
            "question": question,  # 修正：API要求的字段是 question，不是 user_query
            **AIQA_HIGH_PRECISION_SETTINGS
        }
        if model_preference:
            payload["model_preference"] = model_preference
        
        try:
            async with self.session.post(url, json=payload, headers=self.get_auth_headers()) as response:
                logger.info(f"API響應狀態碼: {response.status}")
                
                if response.status != 200:
                    response_text = await response.text()
                    logger.error(f"API請求失敗，狀態碼: {response.status}, 響應: {response_text}")
                    return {"error": f"API返回錯誤狀態碼: {response.status}"}
                
                response_data = await response.json()
                end_time = time.time()
                response_data['processing_time'] = end_time - start_time
                
                # 調試：記錄響應數據的主要鍵
                main_keys = list(response_data.keys()) if isinstance(response_data, dict) else "非字典響應"
                logger.info(f"API響應主要鍵: {main_keys}")
                
                return response_data
                
        except Exception as e:
            end_time = time.time()
            logger.error(f"問答API調用異常 for query '{question[:30]}...': {e}")
            return {
                "error": str(e),
                "processing_time": end_time - start_time
            }

    async def _run_ragas_evaluation(self, ragas_data: List[Dict], answer_only_mode: bool = True) -> Dict:
        """執行Ragas評估 - 考慮AI調用速率限制"""
        if not ragas_data:
            logger.warning("沒有可用於Ragas評估的數據。")
            return {}
        
        # 根據評估模式選擇指標
        if answer_only_mode:
            # 僅答案評估模式：專為摘要架構設計
            metrics = [answer_relevancy, answer_correctness]  # 移除 faithfulness
            ai_calls_per_case = 2  # 每案例2次AI調用
            logger.info("🎯 摘要架構專用評估模式 - 評估答案相關性和正確性")
            logger.info("ℹ️  跳過 Faithfulness (摘要vs原文無法直接比較)")
            logger.info("ℹ️  跳過 Context Recall (摘要架構不適用)")
        else:
            # 完整評估模式：僅包含適用的檢索指標
            metrics = [context_precision, answer_relevancy, answer_correctness]  # 移除 context_recall 和 faithfulness
            ai_calls_per_case = 3  # 每案例3次AI調用  
            logger.info("📊 摘要架構完整評估模式")
            logger.info("ℹ️  包含 Context Precision (檢索精確度)")
            logger.info("ℹ️  跳過 Context Recall (摘要架構不適用)")
            logger.info("ℹ️  跳過 Faithfulness (摘要vs原文不適用)")
        
        # 計算Ragas評估時間預估
        estimated_ai_calls = len(ragas_data) * ai_calls_per_case
        estimated_time_minutes = max(1, estimated_ai_calls / 15)  # 每分鐘最多15次
        logger.info(f"⏱️  預估Ragas評估時間: 至少 {estimated_time_minutes:.1f} 分鐘 (約 {estimated_ai_calls} 次AI調用)")
        
        logger.info(f"準備執行Ragas評估，共 {len(ragas_data)} 個項目...")
        dataset = Dataset.from_list(ragas_data)
        
        try:
            # 由於Ragas內部的AI調用我們無法直接控制速率，
            # 我們通過減少併發或分批處理來間接控制
            if len(ragas_data) > 5:
                logger.warning(f"⚠️  大型數據集 ({len(ragas_data)} 項)，Ragas評估可能需要很長時間")
                logger.warning(f"⚠️  建議考慮分批評估或使用更小的測試集")
            
            # 為了遵守速率限制，我們可以添加一個預延遲
            if estimated_ai_calls > 15:
                pre_delay = (estimated_ai_calls - 15) * 4  # 每超出的調用延遲4秒
                logger.info(f"⏱️  為避免超過速率限制，先等待 {pre_delay} 秒...")
                await asyncio.sleep(pre_delay)
            
            result = await asyncio.to_thread(evaluate, dataset, metrics=metrics, llm=llm, embeddings=embeddings, raise_exceptions=False)
            logger.info("Ragas評估完成！")
            return result.to_pandas().mean(numeric_only=True).to_dict()
        except Exception as e:
            logger.error(f"Ragas評估失敗: {e}", exc_info=True)
            return {"error": str(e)}

    async def evaluate_full_qa_system(self, test_cases: List[Dict], model_preference: Optional[str], answer_only_mode: bool = True) -> Dict[str, Any]:
        """評估完整問答系統的準確度"""
        # 計算總體評估時間預估
        total_aiqa_calls = len(test_cases)
        aiqa_time_minutes = max(1, total_aiqa_calls / 1)  # 每分鐘最多1次AIQA
        
        # 根據評估模式計算Ragas AI調用次數
        ragas_calls_per_case = 2 if answer_only_mode else 3  # 僅答案模式2次，完整模式3次
        ragas_ai_calls = len(test_cases) * ragas_calls_per_case
        ragas_time_minutes = max(1, ragas_ai_calls / 15)  # 每分鐘最多15次
        total_estimated_time = aiqa_time_minutes + ragas_time_minutes
        
        logger.info(f"⏱️  預估總評估時間: 至少 {total_estimated_time:.1f} 分鐘")
        logger.info(f"   - AIQA階段: {aiqa_time_minutes:.1f} 分鐘 ({total_aiqa_calls} 次請求)")
        logger.info(f"   - Ragas評估階段: {ragas_time_minutes:.1f} 分鐘 ({ragas_ai_calls} 次AI調用)")
        
        ragas_data = []
        system_performance_data = []
        
        for i, test_case in enumerate(test_cases):
            question = test_case.get('question') or test_case.get('user_query')
            ground_truth = test_case.get('ground_truth')
            logger.info(f"--- [案例 {i+1}/{len(test_cases)}] 問題: {question[:50]}... ---")
            
            if not all([question, ground_truth]):
                logger.warning("跳過案例：缺少 'question' 或 'ground_truth'")
                continue

            qa_response = await self._qa_via_api(question, model_preference)
            
            # 調試：顯示API響應結構
            logger.info(f"QA API 響應結構: {list(qa_response.keys()) if qa_response else 'Empty response'}")
            
            answer = qa_response.get('answer', '').strip()
            
            # === 多層次上下文分析 ===
            semantic_search_contexts = qa_response.get('semantic_search_contexts', [])
            llm_context_documents = qa_response.get('llm_context_documents', [])
            detailed_document_data = qa_response.get('detailed_document_data_from_ai_query', [])
            
            # 新增：查詢重寫分析
            query_rewrite_result = qa_response.get('query_rewrite_result', {})
            ai_query_reasoning = qa_response.get('ai_generated_query_reasoning', '')
            
            # 提取不同層次的上下文用於評估
            contexts = []
            context_analysis = {
                "semantic_search_count": len(semantic_search_contexts),
                "llm_context_count": len(llm_context_documents),
                "detailed_data_count": len(detailed_document_data) if detailed_document_data else 0,
                "ai_selection_effectiveness": 0.0,
                "context_source_types": [],
                # 新增：查詢重寫分析
                "query_rewrite_count": len(query_rewrite_result.get('rewritten_queries', [])),
                "has_intent_analysis": bool(query_rewrite_result.get('intent_analysis', '')),
                "has_extracted_parameters": bool(query_rewrite_result.get('extracted_parameters', {})),
                "has_ai_query_reasoning": bool(ai_query_reasoning),
                # 新增：相似度分析
                "avg_similarity_score": 0.0,
                "max_similarity_score": 0.0,
                "min_similarity_score": 0.0,
                "similarity_score_std": 0.0
            }
            
            # 計算語義搜索的相似度統計
            if semantic_search_contexts:
                similarity_scores = [doc.get('similarity_score', 0) for doc in semantic_search_contexts]
                if similarity_scores:
                    context_analysis["avg_similarity_score"] = np.mean(similarity_scores)
                    context_analysis["max_similarity_score"] = np.max(similarity_scores)
                    context_analysis["min_similarity_score"] = np.min(similarity_scores)
                    context_analysis["similarity_score_std"] = np.std(similarity_scores)
            
            # 優先使用 LLM 實際使用的上下文（最準確）
            if llm_context_documents:
                contexts = [doc.get('content_used', '') for doc in llm_context_documents if doc.get('content_used')]
                context_analysis["context_source_types"] = [doc.get('source_type', 'unknown') for doc in llm_context_documents]
                logger.info(f"✅ 使用 LLM 實際上下文: {len(contexts)} 個片段")
                logger.info(f"   上下文來源類型: {set(context_analysis['context_source_types'])}")
                
                # 計算 AI 選擇效果（LLM 上下文數 vs 語義搜索結果數）
                if semantic_search_contexts:
                    context_analysis["ai_selection_effectiveness"] = len(llm_context_documents) / len(semantic_search_contexts)
                    logger.info(f"   AI 篩選效果: {len(llm_context_documents)}/{len(semantic_search_contexts)} = {context_analysis['ai_selection_effectiveness']:.2f}")
            
            # 備選：使用語義搜索的摘要
            elif semantic_search_contexts:
                contexts = [doc.get('summary_or_chunk_text', '') for doc in semantic_search_contexts if doc.get('summary_or_chunk_text')]
                logger.info(f"⚠️ 回退使用語義搜索上下文: {len(contexts)} 個摘要")
                
            # 最後備選：使用答案本身
            else:
                contexts = [answer] if answer else ["無上下文"]
                logger.warning("⚠️ 無上下文數據，使用答案本身作為虛擬上下文")
            
            # 增強版檢索分析日誌
            logger.info("📊 增強版檢索流程分析:")
            
            # Step 0: 查詢重寫分析
            logger.info(f"   0️⃣ 查詢重寫階段:")
            logger.info(f"      原始查詢: {question[:50]}...")
            if query_rewrite_result:
                rewritten_queries = query_rewrite_result.get('rewritten_queries', [])
                logger.info(f"      重寫查詢數: {len(rewritten_queries)} 個")
                if rewritten_queries:
                    logger.info(f"      重寫示例: {rewritten_queries[0][:50]}..." if rewritten_queries[0] else "無")
                intent_analysis = query_rewrite_result.get('intent_analysis', '')
                logger.info(f"      意圖分析: {'有' if intent_analysis else '無'} ({len(intent_analysis)} 字符)")
                extracted_params = query_rewrite_result.get('extracted_parameters', {})
                logger.info(f"      提取參數: {len(extracted_params)} 個 - {list(extracted_params.keys())[:3]}")
            
            # Step 1: 語義搜索分析
            logger.info(f"   1️⃣ 語義搜索階段: {len(semantic_search_contexts)} 個候選")
            if semantic_search_contexts:
                logger.info(f"      平均相似度: {context_analysis['avg_similarity_score']:.3f}")
                logger.info(f"      相似度範圍: {context_analysis['min_similarity_score']:.3f} - {context_analysis['max_similarity_score']:.3f}")
                logger.info(f"      相似度標準差: {context_analysis['similarity_score_std']:.3f}")
                doc_ids = [doc.get('document_id', 'unknown')[:8] for doc in semantic_search_contexts[:3]]
                logger.info(f"      Top-3 文檔ID: {doc_ids}")
            
            # Step 2: AI 智慧篩選分析
            logger.info(f"   2️⃣ AI 智慧篩選階段: {len(llm_context_documents)} 個")
            if llm_context_documents:
                source_types = [doc.get('source_type', 'unknown') for doc in llm_context_documents]
                source_distribution = dict(zip(*np.unique(source_types, return_counts=True))) if source_types else {}
                logger.info(f"      來源類型分布: {source_distribution}")
                
                # 分析上下文品質
                avg_content_length = np.mean([len(doc.get('content_used', '')) for doc in llm_context_documents])
                logger.info(f"      平均上下文長度: {avg_content_length:.0f} 字符")
            
            # Step 3: 詳細查詢分析
            logger.info(f"   3️⃣ 詳細查詢階段: {context_analysis['detailed_data_count']} 個")
            if ai_query_reasoning:
                logger.info(f"      AI 查詢推理: {'有' if ai_query_reasoning else '無'} ({len(ai_query_reasoning)} 字符)")
                logger.info(f"      推理摘要: {ai_query_reasoning[:100]}..." if len(ai_query_reasoning) > 100 else ai_query_reasoning)
            
            # 計算檢索管道效率指標
            pipeline_efficiency = {
                "retrieval_funnel_ratio": 0.0,  # 最終使用數 / 初始候選數
                "ai_filtering_precision": 0.0,  # AI篩選的精確度
                "detailed_query_success_rate": 0.0  # 詳細查詢成功率
            }
            
            if semantic_search_contexts and llm_context_documents:
                pipeline_efficiency["retrieval_funnel_ratio"] = len(llm_context_documents) / len(semantic_search_contexts)
                pipeline_efficiency["ai_filtering_precision"] = context_analysis["ai_selection_effectiveness"]
                
            if detailed_document_data and llm_context_documents:
                # 檢查有多少LLM上下文來自詳細查詢
                detailed_source_count = sum(1 for doc in llm_context_documents if doc.get('source_type') == 'ai_detailed_query')
                if len(llm_context_documents) > 0:
                    pipeline_efficiency["detailed_query_success_rate"] = detailed_source_count / len(llm_context_documents)
            
            # 將管道效率加入上下文分析
            context_analysis.update(pipeline_efficiency)
            
            logger.info(f"   📈 檢索管道效率:")
            logger.info(f"      檢索漏斗比率: {pipeline_efficiency['retrieval_funnel_ratio']:.2f}")
            logger.info(f"      AI篩選精確度: {pipeline_efficiency['ai_filtering_precision']:.2f}")
            logger.info(f"      詳細查詢成功率: {pipeline_efficiency['detailed_query_success_rate']:.2f}")
            
            system_performance_data.append({
                "response_time": qa_response.get('processing_time', 0.0),
                "tokens_used": qa_response.get('tokens_used', 0),
                **context_analysis  # 添加上下文分析數據
            })

            # 準備 Ragas 評估數據
            if answer:
                ragas_item = {
                    "question": question,
                    "answer": answer,
                    "contexts": contexts,
                    "ground_truth": ground_truth
                }
                
                # 添加增強版檢索分析元數據（用於後續分析）
                ragas_item["_metadata"] = {
                    # 基本檢索指標
                    "semantic_search_count": context_analysis["semantic_search_count"],
                    "llm_context_count": context_analysis["llm_context_count"],
                    "ai_selection_effectiveness": context_analysis["ai_selection_effectiveness"],
                    "context_source_types": context_analysis["context_source_types"],
                    "has_detailed_query_data": context_analysis["detailed_data_count"] > 0,
                    
                    # 查詢重寫指標
                    "query_rewrite_count": context_analysis["query_rewrite_count"],
                    "has_intent_analysis": context_analysis["has_intent_analysis"],
                    "has_extracted_parameters": context_analysis["has_extracted_parameters"],
                    "has_ai_query_reasoning": context_analysis["has_ai_query_reasoning"],
                    
                    # 相似度分析指標
                    "avg_similarity_score": context_analysis["avg_similarity_score"],
                    "max_similarity_score": context_analysis["max_similarity_score"],
                    "min_similarity_score": context_analysis["min_similarity_score"],
                    "similarity_score_std": context_analysis["similarity_score_std"],
                    
                    # 檢索管道效率指標
                    "retrieval_funnel_ratio": context_analysis["retrieval_funnel_ratio"],
                    "ai_filtering_precision": context_analysis["ai_filtering_precision"],
                    "detailed_query_success_rate": context_analysis["detailed_query_success_rate"]
                }
                
                ragas_data.append(ragas_item)
                logger.info(f"✅ 成功添加案例到Ragas評估數據（上下文品質: {len(contexts)} 個有效片段）")
            else:
                logger.warning(f"❌ API未返回有效答案，此案例將不被Ragas評估")
                logger.warning(f"  - 答案: {'有' if answer else '無'} ({len(answer) if answer else 0} 字符)")
                logger.warning(f"  - 檢索流程: 語義搜索 {context_analysis['semantic_search_count']} → AI篩選 {context_analysis['llm_context_count']} → 詳細查詢 {context_analysis['detailed_data_count']}")

        # 根據參數選擇評估模式
        ragas_scores = await self._run_ragas_evaluation(ragas_data, answer_only_mode=answer_only_mode)
        
        # 匯總結果
        sys_perf_df = pd.DataFrame(system_performance_data)
        
        # 計算增強版檢索流程分析統計
        retrieval_analysis = {}
        if len(sys_perf_df) > 0 and 'semantic_search_count' in sys_perf_df.columns:
            retrieval_analysis = {
                # 原有指標
                "average_semantic_search_candidates": sys_perf_df['semantic_search_count'].mean(),
                "average_llm_context_used": sys_perf_df['llm_context_count'].mean(),
                "average_ai_selection_effectiveness": sys_perf_df['ai_selection_effectiveness'].mean(),
                "detailed_query_usage_rate": (sys_perf_df['detailed_data_count'] > 0).mean(),
                "context_source_distribution": {},
                
                # 新增：查詢重寫分析
                "query_rewrite_analysis": {
                    "average_rewrite_count": sys_perf_df['query_rewrite_count'].mean() if 'query_rewrite_count' in sys_perf_df.columns else 0,
                    "intent_analysis_success_rate": sys_perf_df['has_intent_analysis'].mean() if 'has_intent_analysis' in sys_perf_df.columns else 0,
                    "parameter_extraction_success_rate": sys_perf_df['has_extracted_parameters'].mean() if 'has_extracted_parameters' in sys_perf_df.columns else 0,
                    "ai_reasoning_availability_rate": sys_perf_df['has_ai_query_reasoning'].mean() if 'has_ai_query_reasoning' in sys_perf_df.columns else 0
                },
                
                # 新增：相似度分析
                "similarity_analysis": {
                    "average_similarity_score": sys_perf_df['avg_similarity_score'].mean() if 'avg_similarity_score' in sys_perf_df.columns else 0,
                    "average_max_similarity": sys_perf_df['max_similarity_score'].mean() if 'max_similarity_score' in sys_perf_df.columns else 0,
                    "average_min_similarity": sys_perf_df['min_similarity_score'].mean() if 'min_similarity_score' in sys_perf_df.columns else 0,
                    "average_similarity_variance": sys_perf_df['similarity_score_std'].mean() if 'similarity_score_std' in sys_perf_df.columns else 0
                },
                
                # 新增：檢索管道效率
                "pipeline_efficiency": {
                    "average_retrieval_funnel_ratio": sys_perf_df['retrieval_funnel_ratio'].mean() if 'retrieval_funnel_ratio' in sys_perf_df.columns else 0,
                    "average_ai_filtering_precision": sys_perf_df['ai_filtering_precision'].mean() if 'ai_filtering_precision' in sys_perf_df.columns else 0,
                    "average_detailed_query_success_rate": sys_perf_df['detailed_query_success_rate'].mean() if 'detailed_query_success_rate' in sys_perf_df.columns else 0
                }
            }
            
            # 統計上下文來源類型分布
            all_source_types = []
            for context_types in sys_perf_df['context_source_types']:
                if isinstance(context_types, list):
                    all_source_types.extend(context_types)
            
            if all_source_types:
                from collections import Counter
                source_counter = Counter(all_source_types)
                total_sources = sum(source_counter.values())
                retrieval_analysis["context_source_distribution"] = {
                    source: count/total_sources for source, count in source_counter.items()
                }
        
        results = {
            "evaluation_type": "end_to_end_qa_system_with_ragas_enhanced",
            "total_test_cases": len(test_cases),
            "ragas_evaluated_cases": len(ragas_data),
            "ragas_metrics": {k: (v if pd.notna(v) else 0.0) for k, v in ragas_scores.items()},
            "system_performance": {
                "average_response_time_seconds": sys_perf_df['response_time'].mean(),
                "median_response_time_seconds": sys_perf_df['response_time'].median(),
                "average_tokens_used": sys_perf_df['tokens_used'].mean()
            },
            "retrieval_pipeline_analysis": retrieval_analysis,
            "evaluation_parameters": {
                "model_preference": model_preference or "default",
                "mode": "high_precision",
                **AIQA_HIGH_PRECISION_SETTINGS
            }
        }
        return results

    def print_results(self, results: Dict[str, Any]):
        """以對人類友好的格式輸出評估結果"""
        params = results.get("evaluation_parameters", {})
        ragas_metrics = results.get("ragas_metrics", {})
        sys_perf = results.get("system_performance", {})
        
        print("\n" + "="*80)
        print("🤖 端到端 (End-to-End) AI 問答系統評估報告")
        print("="*80)
        print(f"總案例數: {results.get('total_test_cases', 0):<5} | "
              f"有效 Ragas 評估案例: {results.get('ragas_evaluated_cases', 0):<5}")
        print(f"⚙️  評估模式: {params.get('mode', 'N/A')}, "
              f"偏好模型: {params.get('model_preference', 'default')}")
        
        # --- 答案品質評估 ---
        print("\n" + "─"*25 + " 🎯 摘要架構答案品質評估 " + "─"*25)
        print(f"  - Answer Correctness (正確性):  {ragas_metrics.get('answer_correctness', 0.0):.4f}")
        print(f"  - Answer Relevancy (相關性):    {ragas_metrics.get('answer_relevancy', 0.0):.4f}")
        
        # 顯示跳過的指標
        skipped_metrics = []
        if ragas_metrics.get('faithfulness') is None:
            skipped_metrics.append("Faithfulness (摘要vs原文不適用)")
        
        # --- 檢索品質 (僅在完整模式下顯示) ---
        if ragas_metrics.get('context_precision') is not None:
            print("\n" + "─"*25 + " 📊 摘要架構檢索品質評估 " + "─"*25)
            print(f"  - Context Precision (精確度):   {ragas_metrics.get('context_precision', 0.0):.4f}")
            skipped_metrics.append("Context Recall (摘要架構不適用)")
        else:
            print("\n" + "─"*20 + " ℹ️  摘要架構專用評估說明 " + "─"*20)
            skipped_metrics.extend([
                "Context Precision (完整模式才評估)",
                "Context Recall (摘要架構不適用)"
            ])
        
        # 顯示跳過的指標說明
        if skipped_metrics:
            print("\n" + "─"*25 + " ⚠️  跳過的評估指標 " + "─"*25)
            for metric in skipped_metrics:
                print(f"  - {metric}")
            print("  📝 原因：您的向量化使用摘要，非原始文本")
        
        # --- 增強版檢索流程分析 ---
        retrieval_analysis = results.get("retrieval_pipeline_analysis", {})
        if retrieval_analysis:
            print("\n" + "─"*20 + " 🔍 完整檢索流程效能分析 " + "─"*20)
            
            # Step 0: 查詢重寫效能
            query_rewrite = retrieval_analysis.get('query_rewrite_analysis', {})
            if query_rewrite:
                print("  📝 查詢重寫階段:")
                print(f"    - 平均重寫查詢數: {query_rewrite.get('average_rewrite_count', 0):.1f} 個")
                print(f"    - 意圖分析成功率: {query_rewrite.get('intent_analysis_success_rate', 0):.1%}")
                print(f"    - 參數提取成功率: {query_rewrite.get('parameter_extraction_success_rate', 0):.1%}")
                print(f"    - AI推理可用率: {query_rewrite.get('ai_reasoning_availability_rate', 0):.1%}")
            
            # Step 1: 語義搜索效能
            similarity_analysis = retrieval_analysis.get('similarity_analysis', {})
            print("  🔍 語義搜索階段:")
            print(f"    - 平均候選數: {retrieval_analysis.get('average_semantic_search_candidates', 0):.1f} 個")
            if similarity_analysis:
                print(f"    - 平均相似度分數: {similarity_analysis.get('average_similarity_score', 0):.3f}")
                print(f"    - 相似度品質範圍: {similarity_analysis.get('average_min_similarity', 0):.3f} - {similarity_analysis.get('average_max_similarity', 0):.3f}")
                print(f"    - 相似度變異度: {similarity_analysis.get('average_similarity_variance', 0):.3f}")
            
            # Step 2: AI 智慧篩選效能
            pipeline_eff = retrieval_analysis.get('pipeline_efficiency', {})
            print("  🤖 AI 智慧篩選階段:")
            print(f"    - 平均篩選後數量: {retrieval_analysis.get('average_llm_context_used', 0):.1f} 個")
            print(f"    - AI篩選效果: {retrieval_analysis.get('average_ai_selection_effectiveness', 0):.1%}")
            if pipeline_eff:
                print(f"    - 檢索漏斗比率: {pipeline_eff.get('average_retrieval_funnel_ratio', 0):.2f}")
                print(f"    - AI篩選精確度: {pipeline_eff.get('average_ai_filtering_precision', 0):.2f}")
            
            # Step 3: 詳細查詢效能
            print("  📋 詳細查詢階段:")
            print(f"    - 詳細查詢使用率: {retrieval_analysis.get('detailed_query_usage_rate', 0):.1%}")
            if pipeline_eff:
                print(f"    - 詳細查詢成功率: {pipeline_eff.get('average_detailed_query_success_rate', 0):.1%}")
            
            # 上下文來源分布
            source_dist = retrieval_analysis.get('context_source_distribution', {})
            if source_dist:
                print("  📊 最終上下文來源分布:")
                for source, ratio in sorted(source_dist.items(), key=lambda x: x[1], reverse=True):
                    source_name_map = {
                        "ai_detailed_query": "AI詳細查詢",
                        "general_ai_summary": "AI通用摘要", 
                        "general_extracted_text": "原始文本",
                        "general_placeholder": "佔位符"
                    }
                    display_name = source_name_map.get(source, source)
                    print(f"    • {display_name}: {ratio:.1%}")
        
        # --- 系統性能 ---
        print("\n" + "─"*32 + " ⚡ 系統性能 " + "─"*32)
        print(f"  - 平均回應時間: {sys_perf.get('average_response_time_seconds', 0.0):.2f} 秒")
        print(f"  - 中位回應時間: {sys_perf.get('median_response_time_seconds', 0.0):.2f} 秒")
        print(f"  - 平均Token用量: {sys_perf.get('average_tokens_used', 0.0):.0f}")
        
        # --- 智慧評估總結 ---
        print("\n" + "="*20 + " 📋 智慧檢索系統評估總結 " + "="*20)
        if retrieval_analysis:
            # 查詢重寫效能評估
            query_rewrite = retrieval_analysis.get('query_rewrite_analysis', {})
            if query_rewrite:
                intent_rate = query_rewrite.get('intent_analysis_success_rate', 0)
                reasoning_rate = query_rewrite.get('ai_reasoning_availability_rate', 0)
                if intent_rate > 0.8 and reasoning_rate > 0.8:
                    print("✅ 查詢理解優秀：AI成功理解用戶意圖並提供推理")
                elif intent_rate > 0.5:
                    print("⚠️ 查詢理解中等：建議優化意圖分析或推理生成")
                else:
                    print("❌ 查詢理解不佳：查詢重寫系統需要改善")
            
            # 語義搜索品質評估
            similarity_analysis = retrieval_analysis.get('similarity_analysis', {})
            if similarity_analysis:
                avg_similarity = similarity_analysis.get('average_similarity_score', 0)
                similarity_variance = similarity_analysis.get('average_similarity_variance', 0)
                if avg_similarity > 0.7:
                    print("✅ 語義搜索優秀：候選文檔與查詢高度相關")
                elif avg_similarity > 0.5:
                    print("⚠️ 語義搜索中等：部分檢索結果相關性待提升")
                else:
                    print("❌ 語義搜索不佳：向量模型或embedding品質需改善")
                
                if similarity_variance < 0.1:
                    print("✅ 檢索穩定性好：相似度分數變異度低")
                elif similarity_variance > 0.2:
                    print("⚠️ 檢索穩定性差：相似度分數變異度過高")
            
            # AI篩選效能評估
            effectiveness = retrieval_analysis.get('average_ai_selection_effectiveness', 0)
            pipeline_eff = retrieval_analysis.get('pipeline_efficiency', {})
            if effectiveness > 0.8:
                print("✅ AI篩選效果優秀：成功從候選中精選出高品質上下文")
            elif effectiveness > 0.5:
                print("⚠️ AI篩選效果中等：建議優化篩選策略或提示詞")
            else:
                print("❌ AI篩選效果不佳：AI文檔選擇邏輯需要調整")
            
            # 詳細查詢系統評估
            detailed_usage = retrieval_analysis.get('detailed_query_usage_rate', 0)
            detailed_success = pipeline_eff.get('average_detailed_query_success_rate', 0) if pipeline_eff else 0
            if detailed_usage > 0.7 and detailed_success > 0.7:
                print("✅ 詳細查詢系統優秀：高使用率且成功率佳")
            elif detailed_usage > 0.3:
                print("⚠️ 詳細查詢系統中等：可考慮提升使用率或成功率")
            else:
                print("❌ 詳細查詢系統不佳：主要依賴通用摘要，智慧查詢未充分發揮")
            
            # 整體檢索管道效率評估
            funnel_ratio = pipeline_eff.get('average_retrieval_funnel_ratio', 0) if pipeline_eff else 0
            if funnel_ratio > 0.3:
                print("✅ 檢索管道效率佳：良好的候選篩選比例")
            elif funnel_ratio > 0.1:
                print("⚠️ 檢索管道效率中等：篩選比例合理但有改善空間")
            else:
                print("❌ 檢索管道效率低：篩選過於嚴格或語義搜索品質不佳")
        
        print("📝 建議：專注優化整個檢索管道的協同效果，摘要架構已跳過不適用的檢索指標")
        print("🎯 重點：評估涵蓋從查詢重寫到詳細查詢的完整智慧檢索流程")
        print("="*80 + "\n")

    def save_results_to_json(self, results: Dict[str, Any], output_path: str):
        """將詳細評估結果保存到JSON文件"""
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=4)
            logger.info(f"詳細評估結果已保存至: {output_path}")
        except Exception as e:
            logger.error(f"保存評估結果失敗: {e}")

    async def run_evaluation_flow(self, dataset_path: str, model_preference: Optional[str], answer_only_mode: bool = True):
        """執行完整的評估流程"""
        logger.info("開始端到端評估流程...")
        if not os.path.isabs(dataset_path):
            dataset_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), dataset_path)
        
        try:
            with open(dataset_path, 'r', encoding='utf-8') as f:
                test_cases = json.load(f)
            logger.info(f"成功載入 {len(test_cases)} 個測試案例")
        except Exception as e:
            logger.error(f"載入測試數據失敗: {e}")
            return
        
        try:
            await self.initialize_services()
            results = await self.evaluate_full_qa_system(test_cases, model_preference, answer_only_mode=answer_only_mode)
            self.print_results(results)
            output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "full_qa_system_evaluation_results.json")
            self.save_results_to_json(results, output_path)
        finally:
            if self.session and not self.session.closed:
                await self.session.close()
                logger.info("HTTP會話已關閉")

async def main():
    """主函數，解析參數並啟動評估"""
    parser = argparse.ArgumentParser(description='端到端AI問答系統評估 (使用Ragas)')
    parser.add_argument('--dataset', type=str, required=True, help='測試資料集檔案路徑 (必須)')
    parser.add_argument('--model', type=str, help='指定使用的AI模型 (可選)')
    parser.add_argument('--full-context', action='store_true', help='啟用完整評估模式（包含上下文檢索品質）')
    args = parser.parse_args()
    
    # 決定評估模式
    answer_only_mode = not args.full_context
    
    # 顯示Google AI速率限制警告
    logger.warning("⚠️  注意：本評估使用Google AI免費API")
    logger.warning("⚠️  AIQA限制：每分鐘最多1次請求 (每次約6次Google AI調用)")
    logger.warning("⚠️  Ragas限制：每分鐘最多15次AI調用")
    logger.warning("⚠️  大型資料集評估可能需要數小時完成")
    
    for var in ['USERNAME', 'PASSWORD', 'API_URL']:
        if not os.getenv(var):
            logger.error(f"缺少必要的環境變數: {var}，請在.env文件中設置。")
            return
            
    evaluator = FullQASystemEvaluator()
    try:
        await evaluator.run_evaluation_flow(
            dataset_path=args.dataset,
            model_preference=args.model,
            answer_only_mode=answer_only_mode
        )
    except Exception as e:
        logger.error(f"評估腳本執行時發生未預期錯誤: {e}", exc_info=True)

if __name__ == "__main__":
    # 移除了 nest_asyncio，因在標準腳本中 asyncio.run() 是更好的選擇
    try:
        asyncio.run(main())
        logger.info("程式執行完成，正常退出。")
    except SystemExit as e:
        if e.code != 0:
             logger.error("因參數錯誤導致程式退出。")
    except Exception as e:
        logger.error(f"程式在頂層執行時崩潰: {e}", exc_info=True)