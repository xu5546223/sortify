import json
import asyncio
import logging
import uuid
import os
import sys
import argparse
from typing import List, Dict, Any
from collections import defaultdict
import numpy as np
import pandas as pd
import aiohttp
from dotenv import load_dotenv

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

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Dummy Rate Limiter ---
try:
    from api_rate_limiter import APIRateLimiter
except ImportError:
    logger.warning("api_rate_limiter.py not found. Using a dummy rate limiter.")
    class APIRateLimiter:
        def __init__(self, requests_per_minute: int):
            self.delay = 60.0 / requests_per_minute if requests_per_minute > 0 else 0
        async def wait_if_needed_async(self):
            if self.delay > 0:
                await asyncio.sleep(self.delay)

logger.info("評估系統：查詢優化系統 - 專注於查詢優化對檢索準確性的改善效果")


class QueryOptimizationRetrievalEvaluator:
    """查詢優化後檢索準確度評估器 - 使用API調用，支援智能觸發評估"""

    def __init__(self):
        self.api_base_url = os.getenv('API_URL', 'http://localhost:8000')
        self.api_username = os.getenv('USERNAME')
        self.api_password = os.getenv('PASSWORD')
        if not self.api_username or not self.api_password:
            raise ValueError("請在.env文件中設置 USERNAME 和 PASSWORD")
        self.session = None
        self.access_token = None
        
        self.rewrite_rate_limiter = APIRateLimiter(requests_per_minute=10)
        
        # 智能觸發配置
        self.confidence_threshold = 0.75  # 可調整的觸發門檻
        
        logger.info(f"查詢優化API速率限制器已初始化 (每分鐘最多 10 次請求 - 配合後端服務限制)")
        logger.info(f"向量搜索API無速率限制，可直接調用")
        logger.info(f"智能觸發門檻設定為: {self.confidence_threshold}")

    async def initialize_services(self):
        try:
            self.session = aiohttp.ClientSession()
            if not await self.login_and_get_token():
                raise Exception("無法獲取認證 token")
            await self._test_api_connection()
            logger.info("API連接初始化成功")
        except Exception as e:
            logger.error(f"API連接初始化失敗: {e}", exc_info=True)
            raise

    async def login_and_get_token(self) -> bool:
        if not self.session:
            self.session = aiohttp.ClientSession()
        login_url = f"{self.api_base_url}/api/v1/auth/token"
        login_data = {"username": self.api_username, "password": self.api_password}
        logger.info(f"嘗試登入到: {login_url}")
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
            logger.error(f"登入時發生錯誤: {e}", exc_info=True)
            return False

    def get_auth_headers(self) -> Dict[str, str]:
        if not self.access_token:
            raise ValueError("未獲取到 access_token，請先登入")
        return {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}

    async def _test_api_connection(self):
        try:
            headers = self.get_auth_headers()
            async with self.session.get(f"{self.api_base_url}/", headers=headers) as response:
                response.raise_for_status()
                logger.info("API連接測試成功")
        except Exception as e:
            logger.warning(f"API連接測試失敗: {e}")

    async def _rewrite_query_via_api(self, question: str, rewrite_count: int) -> List[str]:
        await self.rewrite_rate_limiter.wait_if_needed_async()
        headers = self.get_auth_headers()
        url = f"{self.api_base_url}/api/v1/unified-ai/rewrite-query"
        payload = {"query": question}
        try:
            async with self.session.post(url, json=payload, headers=headers) as response:
                response.raise_for_status()
                result = await response.json()
                
                rewritten_result_json = result.get('rewritten_result')
                if not rewritten_result_json:
                    logger.warning(f"查詢重寫 API 未回傳 'rewritten_result' for query '{question[:30]}...'")
                    return [question]
                
                rewritten_data = json.loads(rewritten_result_json)
                rewritten_queries = rewritten_data.get('rewritten_queries', [])
                
                if not rewritten_queries:
                    logger.info(f"查詢 '{question[:30]}...' 未生成任何重寫查詢，使用原始查詢")
                    return [question]

                final_queries = rewritten_queries[:rewrite_count]
                
                logger.info(f"查詢 '{question[:30]}...' 通過 API 獲得 {len(final_queries)} 個重寫查詢")
                return final_queries
        except Exception as e:
            logger.error(f"查詢重寫 API 調用異常 for query '{question[:30]}...': {e}", exc_info=True)
            return [question]

    async def _search_semantic_via_api(self, query: str, top_k: int, similarity_threshold: float) -> List[Dict]:
        headers = self.get_auth_headers()
        url = f"{self.api_base_url}/api/v1/vector-db/semantic-search"
        payload = {
            "query": query, 
            "top_k": top_k, 
            "similarity_threshold": similarity_threshold,
            "enable_hybrid_search": True,
            "search_type": "rrf_fusion",
            "rrf_weights": { "summary": 0.4, "chunks": 0.6 }
        }
        try:
            async with self.session.post(url, json=payload, headers=headers) as response:
                response.raise_for_status()
                results = await response.json()
                logger.info(f"語義搜索 (RRF Fusion) for query '{query[:30]}...' -> 檢索到 {len(results)} 個結果")
                
                # 調試：檢查API返回格式
                if results and logger.isEnabledFor(logging.DEBUG):
                    first_result = results[0]
                    logger.debug(f"第一個結果的字段: {list(first_result.keys())}")
                
                return results
        except Exception as e:
            logger.error(f"語義搜索 (RRF Fusion) API 調用異常 for query '{query[:30]}...': {e}", exc_info=True)
            return []

    async def _search_probe_via_api(self, query: str, top_k: int, similarity_threshold: float) -> List[Dict]:
        """執行探針搜索 - 僅對摘要進行快速向量搜索"""
        headers = self.get_auth_headers()
        url = f"{self.api_base_url}/api/v1/vector-db/semantic-search"
        payload = {
            "query": query, 
            "top_k": top_k, 
            "similarity_threshold": similarity_threshold,
            "enable_hybrid_search": False, # 關鍵：禁用混合搜索以獲取原始分數
            "search_type": "vector_only", # 關鍵：僅向量搜索
            "collection_weights": { "summaries": 1.0, "chunks": 0.0 } # 關鍵：僅搜索摘要
        }
        try:
            async with self.session.post(url, json=payload, headers=headers) as response:
                response.raise_for_status()
                results = await response.json()
                logger.info(f"🔬 探針搜索 for query '{query[:30]}...' -> 檢索到 {len(results)} 個結果")
                
                return results
        except Exception as e:
            logger.error(f"探針搜索 API 調用異常 for query '{query[:30]}...': {e}", exc_info=True)
            return []

    async def evaluate_smart_trigger_strategy(self, test_cases: List[Dict], eval_params: Dict) -> Dict[str, Any]:
        """評估智能觸發策略 vs 總是重寫 vs 從不重寫的性能比較
        
        注意：此評估方法真實模擬了智能觸發的流程：
        - 高置信度時：跳過AI重寫，僅執行基準檢索（節省成本）
        - 低置信度時：執行AI重寫和優化檢索
        - 為了評估決策品質，我們會在跳過重寫時額外執行重寫來比較結果，
          但在實際生產環境中，跳過的重寫調用不會被執行。
        """
        top_k = eval_params['top_k']
        similarity_threshold = eval_params['similarity_threshold']
        query_rewrite_count = eval_params['query_rewrite_count']
        confidence_threshold = eval_params.get('confidence_threshold', self.confidence_threshold)

        logger.info(f"開始評估智能觸發策略，參數: {eval_params}")
        logger.info(f"智能觸發門檻: {confidence_threshold}")
        
        # 預估時間 (智能觸發會節省部分AI重寫調用)
        total_test_cases = len(test_cases)
        estimated_skip_rate = 0.3  # 預估30%的案例會跳過重寫
        estimated_rewrite_calls = total_test_cases * (1 + estimated_skip_rate)  # 基準 + 部分重寫
        estimated_time_minutes = max(1, estimated_rewrite_calls / 10)
        logger.info(f"⏱️  預估評估時間: 約 {estimated_time_minutes:.1f} 分鐘")
        logger.info(f"💰 智能觸發預期節省約 {estimated_skip_rate*100:.0f}% 的AI重寫調用")
        
        probe_search_metrics = []    # 探針搜索 (僅摘要，用於觸發)
        no_rewrite_metrics = []      # 基準檢索 (原始查詢 + RRF)
        always_rewrite_metrics = []  # 總是重寫 (重寫查詢 + RRF)
        smart_trigger_metrics = []   # 智能觸發策略
        
        trigger_stats = {
            "skip_rewrite_cases": 0,    # 跳過重寫的案例數
            "trigger_rewrite_cases": 0,  # 觸發重寫的案例數
            "skip_correct_decisions": 0,  # 跳過重寫且結果更好的決策
            "skip_wrong_decisions": 0,   # 跳過重寫但重寫會更好的決策
            "trigger_correct_decisions": 0,  # 觸發重寫且結果更好的決策
            "trigger_wrong_decisions": 0    # 觸發重寫但不重寫會更好的決策
        }
        
        detailed_case_results = []
        verbose_mode = eval_params.get('verbose_mode', False)
        
        for i, test_case in enumerate(test_cases):
            question = test_case.get('question') or test_case.get('user_query')
            expected_doc_ids = test_case.get('expected_relevant_doc_ids', [])
            logger.info(f"--- [案例 {i+1}/{len(test_cases)}] 智能觸發評估: {question[:50]}... ---")
            
            if not question or not expected_doc_ids:
                logger.warning(f"跳過案例 {i+1}，缺少 'question' 或 'expected_relevant_doc_ids'")
                continue

            # 1. 探針搜索 (Probe Search) - 僅用於智能觸發決策
            logger.info("1️⃣  執行探針搜索 (用於決策)...")
            probe_results = await self._search_probe_via_api(question, top_k, 0.0)
            probe_retrieved_ids = [doc['document_id'] for doc in probe_results]
            
            # 從探針結果中獲取真實的 similarity_score
            if probe_results:
                first_result = probe_results[0]
                top_probe_score = first_result.get('similarity_score', 0.0)
                logger.info(f"   探針搜索最高分: {top_probe_score:.4f}")
            else:
                top_probe_score = 0.0

            # 計算探針搜索的指標 (僅供參考)
            probe_case_metrics = {
                "hit_rate": self._calculate_hit_rate(expected_doc_ids, probe_retrieved_ids),
                "mrr": self._calculate_mrr(expected_doc_ids, probe_retrieved_ids),
                "ndcg": self._calculate_ndcg(expected_doc_ids, probe_retrieved_ids)
            }
            probe_search_metrics.append(probe_case_metrics)

            # 2. 基準檢索 (No Rewrite) - 使用原始查詢和RRF，作為性能比較基準
            logger.info("2️⃣  執行基準檢索 (原始查詢 + RRF)...")
            no_rewrite_results = await self._search_semantic_via_api(question, top_k, similarity_threshold)
            no_rewrite_retrieved_ids = [doc['document_id'] for doc in no_rewrite_results]
            no_rewrite_case_metrics = {
                "hit_rate": self._calculate_hit_rate(expected_doc_ids, no_rewrite_retrieved_ids),
                "mrr": self._calculate_mrr(expected_doc_ids, no_rewrite_retrieved_ids),
                "ndcg": self._calculate_ndcg(expected_doc_ids, no_rewrite_retrieved_ids)
            }
            no_rewrite_metrics.append(no_rewrite_case_metrics)

            # 3. 總是重寫 (Always Rewrite) - 為了進行全面的比較，我們總是需要計算"總是重寫"的結果
            logger.info("3️⃣  執行'總是重寫'流程以供比較...")
            rewritten_queries = await self._rewrite_query_via_api(question, query_rewrite_count)
            
            search_tasks = [self._search_semantic_via_api(rq, top_k, similarity_threshold) for rq in rewritten_queries]
            list_of_results_per_query = await asyncio.gather(*search_tasks)

            rrf_input = {}
            for j, single_query_results in enumerate(list_of_results_per_query):
                rrf_input[f"q_{j}"] = [
                    {"doc_id": r.get('document_id'), "score": r.get('score', r.get('similarity_score', 0.5))} 
                    for r in single_query_results if r.get('document_id')
                ]

            merged_rewrite_results = self._reciprocal_rank_fusion(rrf_input)
            rewrite_retrieved_ids = [item['doc_id'] for item in merged_rewrite_results[:top_k]]

            always_rewrite_case_metrics = {
                "hit_rate": self._calculate_hit_rate(expected_doc_ids, rewrite_retrieved_ids),
                "mrr": self._calculate_mrr(expected_doc_ids, rewrite_retrieved_ids),
                "ndcg": self._calculate_ndcg(expected_doc_ids, rewrite_retrieved_ids)
            }
            always_rewrite_metrics.append(always_rewrite_case_metrics)

            # 4. 智能觸發決策 (基於探針分數)
            logger.info(f"4️⃣  智能觸發決策 (探針分數: {top_probe_score:.4f}, 門檻: {confidence_threshold})...")
            
            if top_probe_score > confidence_threshold:
                # 決策：跳過重寫，使用基準檢索結果
                smart_trigger_result_ids = no_rewrite_retrieved_ids
                smart_trigger_case_metrics = no_rewrite_case_metrics.copy()
                trigger_decision = "SKIP_REWRITE"
                trigger_stats["skip_rewrite_cases"] += 1
                
                logger.info(f"   決策: ✅ 跳過AI重寫 (使用基準RRF檢索結果)")
                
                # 判斷這個決策是否正確 (與"總是重寫"比較)
                if no_rewrite_case_metrics["mrr"] >= always_rewrite_case_metrics["mrr"]:
                    trigger_stats["skip_correct_decisions"] += 1
                    decision_quality = "CORRECT"
                else:
                    trigger_stats["skip_wrong_decisions"] += 1
                    decision_quality = "WRONG"
                
                logger.info(f"   決策品質: {decision_quality} (基準MRR={no_rewrite_case_metrics['mrr']:.3f} vs 重寫MRR={always_rewrite_case_metrics['mrr']:.3f})")
                
            else:
                # 決策：觸發重寫，使用RRF融合結果
                smart_trigger_result_ids = rewrite_retrieved_ids
                smart_trigger_case_metrics = always_rewrite_case_metrics.copy()
                trigger_decision = "TRIGGER_REWRITE"
                trigger_stats["trigger_rewrite_cases"] += 1
                
                logger.info(f"   決策: 🔄 觸發AI重寫 (使用RRF融合結果)")

                # 判斷這個決策是否正確 (與"基準檢索"比較)
                if always_rewrite_case_metrics["mrr"] >= no_rewrite_case_metrics["mrr"]:
                    trigger_stats["trigger_correct_decisions"] += 1
                    decision_quality = "CORRECT"
                else:
                    trigger_stats["trigger_wrong_decisions"] += 1
                    decision_quality = "WRONG"
                
                logger.info(f"   決策品質: {decision_quality} (重寫MRR={always_rewrite_case_metrics['mrr']:.3f} vs 基準MRR={no_rewrite_case_metrics['mrr']:.3f})")

            smart_trigger_metrics.append(smart_trigger_case_metrics)
            
            # 詳細案例結果
            if verbose_mode:
                detailed_case = {
                    "question": question,
                    "expected_doc_ids": expected_doc_ids,
                    "probe_top_score": top_probe_score,
                    "trigger_decision": trigger_decision,
                    "decision_quality": decision_quality,
                    "probe_metrics": probe_case_metrics,
                    "no_rewrite_metrics": no_rewrite_case_metrics,
                    "always_rewrite_metrics": always_rewrite_case_metrics,
                    "smart_trigger_metrics": smart_trigger_case_metrics,
                    "probe_retrieved_ids": probe_retrieved_ids,
                    "no_rewrite_retrieved_ids": no_rewrite_retrieved_ids,
                    "rewrite_retrieved_ids": rewrite_retrieved_ids,
                    "smart_trigger_retrieved_ids": smart_trigger_result_ids,
                    "rewritten_queries": rewritten_queries
                }
                detailed_case_results.append(detailed_case)
                
                # 即時顯示比較結果
                probe_mrr = probe_case_metrics['mrr']
                no_rewrite_mrr = no_rewrite_case_metrics['mrr']
                rewrite_mrr = always_rewrite_case_metrics['mrr']
                smart_mrr = smart_trigger_case_metrics['mrr']
                
                print(f"  案例 {i+1:2d}: 探針={probe_mrr:.3f} | 基準={no_rewrite_mrr:.3f} | 重寫={rewrite_mrr:.3f} | 智能={smart_mrr:.3f} | 決策={trigger_decision[:4]} ({decision_quality})")
            
            logger.info(f"  基準 MRR: {no_rewrite_case_metrics['mrr']:.3f}, 重寫 MRR: {always_rewrite_case_metrics['mrr']:.3f}, 智能 MRR: {smart_trigger_case_metrics['mrr']:.3f}")

        # 計算實際的成本節省
        processed_cases = len(no_rewrite_metrics)
        # 只有在觸發重寫時才消耗AI調用
        actual_rewrite_calls = trigger_stats["trigger_rewrite_cases"]
        total_possible_calls = len(test_cases)
        cost_saving_percentage = ((total_possible_calls - actual_rewrite_calls) / max(total_possible_calls, 1)) * 100

        logger.info(f"📊 智能觸發統計:")
        logger.info(f"   實際跳過率: {cost_saving_percentage:.1f}% ({trigger_stats['skip_rewrite_cases']}/{processed_cases})")
        logger.info(f"   節省AI調用: {trigger_stats['skip_rewrite_cases']} 次")
        
        # 匯總結果
        results = self._aggregate_smart_trigger_results(
            probe_search_metrics, no_rewrite_metrics, always_rewrite_metrics, smart_trigger_metrics, 
            trigger_stats, len(test_cases), eval_params
        )
        
        if verbose_mode:
            results["detailed_case_results"] = detailed_case_results
        
        return results

    async def evaluate_retrieval_accuracy(self, test_cases: List[Dict], eval_params: Dict) -> Dict[str, Any]:
        top_k = eval_params['top_k']
        similarity_threshold = eval_params['similarity_threshold']
        query_rewrite_count = eval_params['query_rewrite_count']

        logger.info(f"開始評估檢索系統，參數: {eval_params}")
        
        total_rewrite_calls = len(test_cases)
        estimated_rewrite_time_minutes = max(1, total_rewrite_calls / 10)
        logger.info(f"⏱️  預估評估時間: 至少 {estimated_rewrite_time_minutes:.1f} 分鐘 (受後端服務速率限制影響)")
        logger.info(f"📊 將處理 {total_rewrite_calls} 個查詢優化請求")
        
        baseline_metrics = []
        optimized_metrics = []
        comparison_stats = defaultdict(int)
        detailed_case_results = []  # 新增：詳細案例結果
        verbose_mode = eval_params.get('verbose_mode', False)
        
        for i, test_case in enumerate(test_cases):
            question = test_case.get('question') or test_case.get('user_query')
            expected_doc_ids = test_case.get('expected_relevant_doc_ids', [])
            logger.info(f"--- [案例 {i+1}/{len(test_cases)}] 原始問題: {question[:50]}... ---")
            
            if not question or not expected_doc_ids:
                logger.warning(f"跳過案例 {i+1}，缺少 'question' 或 'expected_relevant_doc_ids'")
                continue

            logger.info("執行基準測試 (原始查詢)...")
            baseline_results = await self._search_semantic_via_api(question, top_k, similarity_threshold)
            baseline_retrieved_ids = [doc['document_id'] for doc in baseline_results]
            
            current_baseline_metrics = {
                "hit_rate": self._calculate_hit_rate(expected_doc_ids, baseline_retrieved_ids),
                "mrr": self._calculate_mrr(expected_doc_ids, baseline_retrieved_ids),
                "ndcg": self._calculate_ndcg(expected_doc_ids, baseline_retrieved_ids)
            }
            baseline_metrics.append(current_baseline_metrics)

            logger.info("執行優化測試 (AI重寫查詢)...")
            rewritten_queries = await self._rewrite_query_via_api(question, query_rewrite_count)
            
            search_tasks = [self._search_semantic_via_api(rq, top_k, similarity_threshold) for rq in rewritten_queries]
            list_of_results_per_query = await asyncio.gather(*search_tasks)

            rrf_input = {}
            for i, single_query_results in enumerate(list_of_results_per_query):
                rrf_input[f"q_{i}"] = [
                    {"doc_id": r.get('document_id'), "score": (r.get('score') or r.get('similarity_score', 0.5))} 
                    for r in single_query_results if r.get('document_id')
                ]

            merged_optimized_results = self._reciprocal_rank_fusion(rrf_input)
            optimized_retrieved_ids = [item['doc_id'] for item in merged_optimized_results[:top_k]]

            current_optimized_metrics = {
                "hit_rate": self._calculate_hit_rate(expected_doc_ids, optimized_retrieved_ids),
                "mrr": self._calculate_mrr(expected_doc_ids, optimized_retrieved_ids),
                "ndcg": self._calculate_ndcg(expected_doc_ids, optimized_retrieved_ids)
            }
            optimized_metrics.append(current_optimized_metrics)
            
            optimized_results_for_comparison = [{"document_id": doc_id} for doc_id in optimized_retrieved_ids]
            case_status = self._compare_performance(expected_doc_ids, baseline_results, optimized_results_for_comparison)
            comparison_stats[case_status] += 1
            
            # 詳細案例結果（用於詳細模式輸出）
            if verbose_mode:
                detailed_case = {
                    "question": question,
                    "expected_doc_ids": expected_doc_ids,
                    "baseline_metrics": current_baseline_metrics,
                    "optimized_metrics": current_optimized_metrics,
                    "baseline_retrieved_ids": baseline_retrieved_ids,
                    "optimized_retrieved_ids": optimized_retrieved_ids,
                    "rewritten_queries": rewritten_queries,
                    "case_status": case_status
                }
                detailed_case_results.append(detailed_case)
                
                # 即時顯示詳細結果
                improvement = current_optimized_metrics['mrr'] - current_baseline_metrics['mrr']
                status_icon = "🚀" if improvement > 0.1 else "✅" if improvement > 0.01 else "❌" if improvement < -0.01 else "⚖️"
                print(f"  案例 {i+1:2d}: {status_icon} 基準MRR={current_baseline_metrics['mrr']:.3f} | 優化MRR={current_optimized_metrics['mrr']:.3f} | 變化={improvement:+.3f}")
            
            logger.info(f"  基準測試 Hit Rate: {current_baseline_metrics['hit_rate']['hit_rate']:.2f}, MRR: {current_baseline_metrics['mrr']:.2f}")
            logger.info(f"  優化測試 Hit Rate: {current_optimized_metrics['hit_rate']['hit_rate']:.2f}, MRR: {current_optimized_metrics['mrr']:.2f}")

        # 匯總結果
        results = self._aggregate_results(baseline_metrics, optimized_metrics, comparison_stats, len(test_cases), eval_params)
        
        # 添加詳細案例結果
        if verbose_mode:
            results["detailed_case_results"] = detailed_case_results
        
        return results

    def _reciprocal_rank_fusion(self, search_results_dict: Dict[str, List[Dict]], k: int = 60) -> List[Dict]:
        ranked_lists = defaultdict(dict)
        for query_id, results in search_results_dict.items():
            for i, result in enumerate(results):
                if result.get('doc_id'):
                    ranked_lists[query_id][result['doc_id']] = i + 1

        rrf_scores = defaultdict(float)
        all_doc_ids = set(res.get('doc_id') for q_results in search_results_dict.values() for res in q_results if res.get('doc_id'))
        
        for doc_id in all_doc_ids:
            for query_id, ranks in ranked_lists.items():
                rank = ranks.get(doc_id)
                if rank is not None:
                    rrf_scores[doc_id] += 1 / (k + rank)
        
        sorted_results = sorted(rrf_scores.items(), key=lambda item: item[1], reverse=True)
        return [{"doc_id": doc_id, "rrf_score": score} for doc_id, score in sorted_results]

    def _calculate_hit_rate(self, expected_ids: List[str], retrieved_ids: List[str]) -> Dict[str, float]:
        expected_set = set(expected_ids)
        hits = len(expected_set.intersection(set(retrieved_ids)))
        return {"hit_rate": hits / len(expected_ids) if expected_ids else 0.0, "hits": float(hits)}

    def _calculate_mrr(self, expected_ids: List[str], retrieved_ids: List[str]) -> float:
        for i, doc_id in enumerate(retrieved_ids):
            if doc_id in expected_ids:
                return 1.0 / (i + 1)
        return 0.0

    def _calculate_ndcg(self, expected_ids: List[str], retrieved_ids: List[str], k_val=10) -> float:
        relevance = [1 if doc_id in expected_ids else 0 for doc_id in retrieved_ids[:k_val]]
        
        dcg = sum((2**rel - 1) / np.log2(i + 2) for i, rel in enumerate(relevance))
        
        ideal_relevance = sorted(relevance, reverse=True)
        idcg = sum((2**rel - 1) / np.log2(i + 2) for i, rel in enumerate(ideal_relevance))
        
        return dcg / idcg if idcg > 0 else 0.0

    def _compare_performance(self, expected_ids: List[str], original_results: List[Dict], optimization_results: List[Dict], k: int = 5) -> str:
        """比較兩種方法的性能，使用 MRR 作為主要指標"""
        # 提取文件ID列表
        original_ids = [doc.get('document_id') for doc in original_results[:k]]
        optimized_ids = [doc.get('document_id') for doc in optimization_results[:k]]

        # 計算 MRR (Mean Reciprocal Rank)
        original_mrr = self._calculate_mrr(expected_ids, original_ids)
        optimized_mrr = self._calculate_mrr(expected_ids, optimized_ids)

        # 使用 MRR 來判斷性能變化，設定閾值為 0.01 以避免微小浮點數差異
        mrr_difference = optimized_mrr - original_mrr
        
        if mrr_difference > 0.01:  # MRR 提升超過 0.01
            return "IMPROVED"
        elif mrr_difference < -0.01:  # MRR 下降超過 0.01
            return "REGRESSED"
        else:
            return "NEUTRAL"

    def _aggregate_results(self, baseline_metrics: List[Dict], optimized_metrics: List[Dict], comparison_stats: Dict, total_cases: int, eval_params: Dict) -> Dict:
        def calculate_mean_scores(metrics_list):
            if not metrics_list:
                return {"hit_rate": {"hit_rate": 0.0}, "mrr": 0.0, "ndcg": 0.0}
            
            avg_hit_rate = np.mean([m['hit_rate']['hit_rate'] for m in metrics_list])
            avg_mrr = np.mean([m['mrr'] for m in metrics_list])
            avg_ndcg = np.mean([m['ndcg'] for m in metrics_list])
            
            return {"hit_rate": {"hit_rate": avg_hit_rate}, "mrr": avg_mrr, "ndcg": avg_ndcg}
        
        baseline_scores = calculate_mean_scores(baseline_metrics)
        optimized_scores = calculate_mean_scores(optimized_metrics)
        
        # 計算案例級別分析
        improved_cases = comparison_stats.get('IMPROVED', 0)
        degraded_cases = comparison_stats.get('REGRESSED', 0)
        unchanged_cases = comparison_stats.get('NEUTRAL', 0)
        processed_cases = improved_cases + degraded_cases + unchanged_cases
        
        # 生成智能建議
        mrr_improvement = optimized_scores['mrr'] - baseline_scores['mrr']
        mrr_improvement_pct = (mrr_improvement / max(baseline_scores['mrr'], 0.001)) * 100
        
        recommendations = []
        if mrr_improvement_pct > 15:
            recommendations.append("🚀 強烈建議啟用查詢重寫！性能提升非常顯著。")
        elif mrr_improvement_pct > 5:
            recommendations.append("✅ 建議啟用查詢重寫。它對檢索性能有明顯的正面影響。")
        elif mrr_improvement_pct > 0:
            recommendations.append("👍 查詢重寫帶來了輕微的性能提升，可以考慮啟用。")
        elif mrr_improvement_pct == 0:
            recommendations.append("⚖️ 查詢重寫對性能沒有影響。可以根據計算成本決定是否啟用。")
        
        # 添加具體的改進建議
        if improved_cases > 0:
            recommendations.append(f"📊 有 {improved_cases}/{processed_cases} 個案例獲得改進，建議分析成功案例的模式。")
        
        if degraded_cases > 0:
            recommendations.append(f"⚠️ 有 {degraded_cases}/{processed_cases} 個案例性能下降，建議檢查重寫質量。")

        final_results = {
            "evaluation_parameters": eval_params,
            "total_test_cases": total_cases,
            "processed_cases": processed_cases,
            "performance_comparison": dict(comparison_stats),
            "baseline_performance": {
                "description": "Using original query with semantic search.",
                "hit_rate": baseline_scores['hit_rate'],
                "mrr": baseline_scores['mrr'],
                "ndcg": baseline_scores['ndcg']
            },
            "optimized_performance": {
                "description": "Using AI-rewritten queries with semantic search and RRF fusion.",
                "hit_rate": optimized_scores['hit_rate'],
                "mrr": optimized_scores['mrr'],
                "ndcg": optimized_scores['ndcg']
            },
            "performance_delta": {
                "hit_rate_change": optimized_scores['hit_rate']['hit_rate'] - baseline_scores['hit_rate']['hit_rate'],
                "mrr_change": optimized_scores['mrr'] - baseline_scores['mrr'],
                "ndcg_change": optimized_scores['ndcg'] - baseline_scores['ndcg']
            },
            "case_level_analysis": {
                "improved_cases": improved_cases,
                "degraded_cases": degraded_cases,
                "unchanged_cases": unchanged_cases
            },
            "recommendations": recommendations,
            "query_rewrite_analysis": {
                "average_rewrites_per_query": eval_params.get('query_rewrite_count', 3),
                "successful_rewrite_rate": 100.0  # 這個需要在實際評估中計算
            }
        }
        return final_results
    
    def _aggregate_smart_trigger_results(
        self, 
        probe_metrics: List[Dict],
        no_rewrite_metrics: List[Dict],
        always_rewrite_metrics: List[Dict], 
        smart_trigger_metrics: List[Dict], 
        trigger_stats: Dict,
        total_cases: int, 
        eval_params: Dict
    ) -> Dict:
        """聚合智能觸發策略的評估結果"""
        
        def calculate_mean_scores(metrics_list):
            if not metrics_list:
                return {"hit_rate": {"hit_rate": 0.0}, "mrr": 0.0, "ndcg": 0.0}
            
            avg_hit_rate = np.mean([m['hit_rate']['hit_rate'] for m in metrics_list])
            avg_mrr = np.mean([m['mrr'] for m in metrics_list])
            avg_ndcg = np.mean([m['ndcg'] for m in metrics_list])
            
            return {"hit_rate": {"hit_rate": avg_hit_rate}, "mrr": avg_mrr, "ndcg": avg_ndcg}
        
        probe_scores = calculate_mean_scores(probe_metrics)
        no_rewrite_scores = calculate_mean_scores(no_rewrite_metrics)
        always_rewrite_scores = calculate_mean_scores(always_rewrite_metrics)
        smart_trigger_scores = calculate_mean_scores(smart_trigger_metrics)
        
        processed_cases = len(no_rewrite_metrics)
        
        # 計算智能觸發的效率分析
        cost_saving_estimation = trigger_stats["skip_rewrite_cases"] / max(processed_cases, 1) * 100
        trigger_rate = trigger_stats["trigger_rewrite_cases"] / max(processed_cases, 1) * 100
        
        # 計算決策準確率
        total_skip_decisions = trigger_stats["skip_rewrite_cases"]
        total_trigger_decisions = trigger_stats["trigger_rewrite_cases"]
        
        skip_accuracy = (trigger_stats["skip_correct_decisions"] / max(total_skip_decisions, 1)) * 100
        trigger_accuracy = (trigger_stats["trigger_correct_decisions"] / max(total_trigger_decisions, 1)) * 100
        overall_accuracy = ((trigger_stats["skip_correct_decisions"] + trigger_stats["trigger_correct_decisions"]) / max(processed_cases, 1)) * 100
        
        # 生成智能建議
        smart_vs_baseline_improvement = smart_trigger_scores['mrr'] - no_rewrite_scores['mrr']
        smart_vs_always_rewrite_comparison = smart_trigger_scores['mrr'] - always_rewrite_scores['mrr']
        
        recommendations = []
        
        # 性能分析
        if smart_vs_baseline_improvement > 0.05:
            recommendations.append(f"🚀 智能觸發策略相比基準檢索有顯著提升 (MRR {smart_vs_baseline_improvement:+.2%})！")
        elif smart_vs_baseline_improvement > 0.01:
            recommendations.append(f"✅ 智能觸發策略相比基準檢索有輕微提升 (MRR {smart_vs_baseline_improvement:+.2%})。")
        
        if smart_vs_always_rewrite_comparison >= -0.01:
            recommendations.append("🎯 智能觸發策略達到了與總是重寫相當的性能，同時節省了計算成本。")
        else:
            recommendations.append(f"⚠️ 智能觸發策略的性能略低於總是重寫 ({smart_vs_always_rewrite_comparison:.2%})，建議調整觸發門檻。")
        
        # 效率分析
        if cost_saving_estimation > 50:
            recommendations.append(f"💰 智能觸發策略跳過了 {cost_saving_estimation:.1f}% 的重寫操作，大幅節省計算成本。")
        elif cost_saving_estimation > 30:
            recommendations.append(f"💡 智能觸發策略跳過了 {cost_saving_estimation:.1f}% 的重寫操作，有效節省成本。")
        
        # 決策準確性分析
        if overall_accuracy > 80:
            recommendations.append(f"🎯 智能觸發的決策準確率很高 ({overall_accuracy:.1f}%)，策略運作良好。")
        elif overall_accuracy > 60:
            recommendations.append(f"👍 智能觸發的決策準確率尚可 ({overall_accuracy:.1f}%)，可考慮微調門檻。")
        else:
            recommendations.append(f"⚠️ 智能觸發的決策準確率較低 ({overall_accuracy:.1f}%)，建議重新評估觸發門檻。")
        
        # 門檻調整建議
        confidence_threshold = eval_params.get('confidence_threshold', 0.75)
        if trigger_stats["skip_wrong_decisions"] > trigger_stats["skip_correct_decisions"]:
            recommendations.append(f"📉 建議降低觸發門檻 (當前: {confidence_threshold})，以減少錯誤的跳過決策。")
        elif trigger_stats["trigger_wrong_decisions"] > trigger_stats["trigger_correct_decisions"]:
            recommendations.append(f"📈 建議提高觸發門檻 (當前: {confidence_threshold})，以減少不必要的重寫。")
        
        results = {
            "evaluation_type": "smart_trigger_strategy",
            "evaluation_parameters": eval_params,
            "total_test_cases": total_cases,
            "processed_cases": processed_cases,
            
            "probe_search_performance": {
                "description": "探針搜索 - 僅對摘要向量搜索 (用於觸發決策)",
                "hit_rate": probe_scores['hit_rate'],
                "mrr": probe_scores['mrr'],
                "ndcg": probe_scores['ndcg']
            },
            
            "no_rewrite_performance": {
                "description": "基準檢索 - 原始查詢 + RRF融合搜索",
                "hit_rate": no_rewrite_scores['hit_rate'],
                "mrr": no_rewrite_scores['mrr'],
                "ndcg": no_rewrite_scores['ndcg']
            },

            "always_rewrite_performance": {
                "description": "總是重寫 - 對所有查詢進行AI重寫和RRF融合",
                "hit_rate": always_rewrite_scores['hit_rate'],
                "mrr": always_rewrite_scores['mrr'],
                "ndcg": always_rewrite_scores['ndcg']
            },
            
            "smart_trigger_performance": {
                "description": f"智能觸發 - 根據探針分數 ({eval_params.get('confidence_threshold', 'N/A')}) 決定是否重寫",
                "hit_rate": smart_trigger_scores['hit_rate'],
                "mrr": smart_trigger_scores['mrr'],
                "ndcg": smart_trigger_scores['ndcg']
            },
            
            "performance_comparison": {
                "smart_vs_baseline": {
                    "hit_rate_change": smart_trigger_scores['hit_rate']['hit_rate'] - no_rewrite_scores['hit_rate']['hit_rate'],
                    "mrr_change": smart_vs_baseline_improvement,
                    "ndcg_change": smart_trigger_scores['ndcg'] - no_rewrite_scores['ndcg']
                },
                "smart_vs_always_rewrite": {
                    "hit_rate_change": smart_trigger_scores['hit_rate']['hit_rate'] - always_rewrite_scores['hit_rate']['hit_rate'],
                    "mrr_change": smart_vs_always_rewrite_comparison,
                    "ndcg_change": smart_trigger_scores['ndcg'] - always_rewrite_scores['ndcg']
                },
                "always_rewrite_vs_baseline": {
                    "hit_rate_change": always_rewrite_scores['hit_rate']['hit_rate'] - no_rewrite_scores['hit_rate']['hit_rate'],
                    "mrr_change": always_rewrite_scores['mrr'] - no_rewrite_scores['mrr'],
                    "ndcg_change": always_rewrite_scores['ndcg'] - no_rewrite_scores['ndcg']
                }
            },
            
            "trigger_analysis": {
                "skip_rewrite_rate": cost_saving_estimation,
                "trigger_rewrite_rate": trigger_rate,
                "skip_decision_accuracy": skip_accuracy,
                "trigger_decision_accuracy": trigger_accuracy,
                "overall_decision_accuracy": overall_accuracy,
                "cost_saving_estimation_percentage": cost_saving_estimation
            },
            
            "decision_breakdown": trigger_stats,
            "recommendations": recommendations
        }
        
        return results
    
    def print_results(self, results: Dict[str, Any]):
        """以對人類友好的格式輸出評估結果 - 改善版本，參考 evaluate_vector_retrieval.py"""
        print("\n" + "="*100)
        print("🚀 查詢重寫檢索 vs 基準檢索 - 詳細性能分析報告")
        print("="*100)
        
        # 基本統計信息
        total_cases = results.get("total_test_cases", 0)
        processed_cases = results.get("processed_cases", 0)
        eval_params = results.get("evaluation_parameters", {})
        
        print(f"\n📋 評估概況:")
        print(f"   🎯 總測試案例數: {total_cases}")
        print(f"   ✅ 已處理案例數: {processed_cases}")
        print(f"   ⚙️  評估參數: Top-K={eval_params.get('top_k', 'N/A')}, " +
              f"相似度閾值={eval_params.get('similarity_threshold', 'N/A')}, " +
              f"查詢重寫數量={eval_params.get('query_rewrite_count', 'N/A')}")
        
        # 顯示基準測試結果
        baseline_metrics = results.get("baseline_performance", {})
        print(f"\n📊 基準測試結果 (原始查詢):")
        if baseline_metrics:
            baseline_mrr = baseline_metrics.get("mrr", 0.0)
            baseline_hr = baseline_metrics.get("hit_rate", {}).get("hit_rate", 0.0)
            baseline_ndcg = baseline_metrics.get("ndcg", 0.0)
            
            print(f"   - MRR (Mean Reciprocal Rank): {baseline_mrr:.4f}")
            print(f"   - Hit Rate: {baseline_hr:.4f}")
            print(f"   - nDCG: {baseline_ndcg:.4f}")
        
        # 顯示優化測試結果
        optimized_metrics = results.get("optimized_performance", {})
        print(f"\n🚀 優化測試結果 (AI重寫查詢 + RRF融合):")
        if optimized_metrics:
            optimized_mrr = optimized_metrics.get("mrr", 0.0)
            optimized_hr = optimized_metrics.get("hit_rate", {}).get("hit_rate", 0.0)
            optimized_ndcg = optimized_metrics.get("ndcg", 0.0)
            
            print(f"   - MRR (Mean Reciprocal Rank): {optimized_mrr:.4f}")
            print(f"   - Hit Rate: {optimized_hr:.4f}")
            print(f"   - nDCG: {optimized_ndcg:.4f}")
        
        # 性能對比分析
        print(f"\n📈 性能對比分析:")
        
        # MRR對比
        mrr_improvement = optimized_mrr - baseline_mrr
        mrr_improvement_pct = (mrr_improvement / max(baseline_mrr, 0.001)) * 100
        
        print(f"   🎯 MRR 對比:")
        print(f"      基準: {baseline_mrr:.4f} → 優化: {optimized_mrr:.4f} (變化: {mrr_improvement:+.4f}, {mrr_improvement_pct:+.2f}%)")
        
        # Hit Rate對比
        print(f"   📊 Hit Rate 對比:")
        hr_improvement = optimized_hr - baseline_hr
        hr_improvement_pct = (hr_improvement / max(baseline_hr, 0.001)) * 100
        print(f"      平均: {baseline_hr:.4f} → {optimized_hr:.4f} (變化: {hr_improvement:+.4f}, {hr_improvement_pct:+.2f}%)")
        
        # nDCG對比
        print(f"   📈 nDCG 對比:")
        ndcg_improvement = optimized_ndcg - baseline_ndcg
        ndcg_improvement_pct = (ndcg_improvement / max(baseline_ndcg, 0.001)) * 100
        print(f"      平均: {baseline_ndcg:.4f} → {optimized_ndcg:.4f} (變化: {ndcg_improvement:+.4f}, {ndcg_improvement_pct:+.2f}%)")
        
        # 案例級別分析
        case_improvements = results.get("case_level_analysis", {})
        if case_improvements:
            improved_cases = case_improvements.get("improved_cases", 0)
            degraded_cases = case_improvements.get("degraded_cases", 0)
            unchanged_cases = case_improvements.get("unchanged_cases", 0)
            
            print(f"\n🔍 案例級別分析:")
            print(f"   📈 性能提升案例: {improved_cases} ({improved_cases/max(processed_cases, 1)*100:.1f}%)")
            print(f"   📉 性能下降案例: {degraded_cases} ({degraded_cases/max(processed_cases, 1)*100:.1f}%)")
            print(f"   ⚖️  性能持平案例: {unchanged_cases} ({unchanged_cases/max(processed_cases, 1)*100:.1f}%)")
        
        # 智能建議
        recommendations = results.get("recommendations", [])
        if recommendations:
            print(f"\n💡 智能建議:")
            for i, rec in enumerate(recommendations, 1):
                print(f"   {i}. {rec}")
        
        # 查詢重寫效果分析
        rewrite_analysis = results.get("query_rewrite_analysis", {})
        if rewrite_analysis:
            print(f"\n🤖 查詢重寫效果分析:")
            avg_rewrites = rewrite_analysis.get("average_rewrites_per_query", 0)
            successful_rewrites = rewrite_analysis.get("successful_rewrite_rate", 0)
            print(f"   平均每查詢重寫數量: {avg_rewrites:.1f}")
            print(f"   成功重寫率: {successful_rewrites:.1f}%")
        
        print("="*100 + "\n")
    
    def print_smart_trigger_results(self, results: Dict[str, Any]):
        """輸出智能觸發策略的評估結果"""
        print("\n" + "="*100)
        print("�� 智能觸發策略 vs 總是重寫 vs 基準檢索 - 綜合性能分析報告")
        print("="*100)
        
        # 基本統計信息
        total_cases = results.get("total_test_cases", 0)
        processed_cases = results.get("processed_cases", 0)
        eval_params = results.get("evaluation_parameters", {})
        
        print(f"\n📋 評估概況:")
        print(f"   🎯 總測試案例數: {total_cases}")
        print(f"   ✅ 已處理案例數: {processed_cases}")
        print(f"   ⚙️  評估參數: Top-K={eval_params.get('top_k', 'N/A')}, " +
              f"相似度閾值={eval_params.get('similarity_threshold', 'N/A')}, " +
              f"觸發門檻={eval_params.get('confidence_threshold', 'N/A')}")
        
        # 四種策略的性能比較
        probe_metrics = results.get("probe_search_performance", {})
        no_rewrite_metrics = results.get("no_rewrite_performance", {})
        always_rewrite_metrics = results.get("always_rewrite_performance", {})
        smart_trigger_metrics = results.get("smart_trigger_performance", {})
        
        print(f"\n📊 四種策略性能比較 (MRR: 平均倒數排名, Hit Rate: 命中率, nDCG: 標準化折扣累積增益):")
        
        # 表格形式顯示
        print(f"{'策略':<16} {'MRR':<8} {'Hit Rate':<10} {'nDCG':<8} {'說明'}")
        print(f"{'-'*16} {'-'*8} {'-'*10} {'-'*8} {'-'*30}")
        
        if probe_metrics:
            probe_mrr = probe_metrics.get("mrr", 0.0)
            probe_hr = probe_metrics.get("hit_rate", {}).get("hit_rate", 0.0)
            probe_ndcg = probe_metrics.get("ndcg", 0.0)
            print(f"{'探針搜索 (決策用)':<16} {probe_mrr:<8.4f} {probe_hr:<10.4f} {probe_ndcg:<8.4f} {'僅摘要搜索，用於觸發決策'}")
        
        if no_rewrite_metrics:
            no_rewrite_mrr = no_rewrite_metrics.get("mrr", 0.0)
            no_rewrite_hr = no_rewrite_metrics.get("hit_rate", {}).get("hit_rate", 0.0)
            no_rewrite_ndcg = no_rewrite_metrics.get("ndcg", 0.0)
            print(f"{'基準檢索 (RRF)':<16} {no_rewrite_mrr:<8.4f} {no_rewrite_hr:<10.4f} {no_rewrite_ndcg:<8.4f} {'原始查詢 + RRF融合'}")

        if always_rewrite_metrics:
            always_mrr = always_rewrite_metrics.get("mrr", 0.0)
            always_hr = always_rewrite_metrics.get("hit_rate", {}).get("hit_rate", 0.0)
            always_ndcg = always_rewrite_metrics.get("ndcg", 0.0)
            print(f"{'總是重寫':<16} {always_mrr:<8.4f} {always_hr:<10.4f} {always_ndcg:<8.4f} {'AI重寫查詢 + RRF融合'}")
        
        if smart_trigger_metrics:
            smart_mrr = smart_trigger_metrics.get("mrr", 0.0)
            smart_hr = smart_trigger_metrics.get("hit_rate", {}).get("hit_rate", 0.0)
            smart_ndcg = smart_trigger_metrics.get("ndcg", 0.0)
            print(f"{'智能觸發':<16} {smart_mrr:<8.4f} {smart_hr:<10.4f} {smart_ndcg:<8.4f} {'根據探針分數動態選擇策略'}")
        
        # 性能變化分析
        performance_comparison = results.get("performance_comparison", {})
        
        print(f"\n📈 性能變化分析 (以 MRR 為主要指標):")
        smart_vs_baseline = performance_comparison.get("smart_vs_baseline", {})
        always_vs_baseline = performance_comparison.get("always_rewrite_vs_baseline", {})
        smart_vs_always = performance_comparison.get("smart_vs_always_rewrite", {})
        
        if smart_vs_baseline:
            mrr_change_baseline = smart_vs_baseline.get("mrr_change", 0.0)
            mrr_change_pct_baseline = (mrr_change_baseline / max(no_rewrite_mrr, 0.001)) * 100
            print(f"   🎯 智能觸發 vs 基準檢索:")
            print(f"      MRR 變化: {mrr_change_baseline:+.4f} ({mrr_change_pct_baseline:+.2f}%)")

        if always_vs_baseline:
            mrr_change_always_vs_baseline = always_vs_baseline.get("mrr_change", 0.0)
            mrr_change_pct_always_vs_baseline = (mrr_change_always_vs_baseline / max(no_rewrite_mrr, 0.001)) * 100
            print(f"   🚀 總是重寫 vs 基準檢索:")
            print(f"      MRR 變化: {mrr_change_always_vs_baseline:+.4f} ({mrr_change_pct_always_vs_baseline:+.2f}%)")
        
        if smart_vs_always:
            mrr_change_always = smart_vs_always.get("mrr_change", 0.0)
            mrr_change_pct_always = (mrr_change_always / max(always_mrr, 0.001)) * 100
            print(f"   ⚖️  智能觸發 vs 總是重寫:")
            print(f"      MRR 變化: {mrr_change_always:+.4f} ({mrr_change_pct_always:+.2f}%)")
        
        # 觸發分析
        trigger_analysis = results.get("trigger_analysis", {})
        if trigger_analysis:
            print(f"\n🧠 智能觸發分析:")
            skip_rate = trigger_analysis.get("skip_rewrite_rate", 0.0)
            trigger_rate = trigger_analysis.get("trigger_rewrite_rate", 0.0)
            overall_accuracy = trigger_analysis.get("overall_decision_accuracy", 0.0)
            cost_saving = trigger_analysis.get("cost_saving_estimation_percentage", 0.0)
            
            print(f"   📊 觸發統計:")
            print(f"      跳過重寫比例: {skip_rate:.1f}%")
            print(f"      觸發重寫比例: {trigger_rate:.1f}%")
            print(f"      決策準確率: {overall_accuracy:.1f}%")
            print(f"      成本節省估計: {cost_saving:.1f}%")
        
        # 決策品質分析
        decision_breakdown = results.get("decision_breakdown", {})
        if decision_breakdown:
            print(f"\n🎯 決策品質分析:")
            skip_correct = decision_breakdown.get("skip_correct_decisions", 0)
            skip_wrong = decision_breakdown.get("skip_wrong_decisions", 0)
            trigger_correct = decision_breakdown.get("trigger_correct_decisions", 0)
            trigger_wrong = decision_breakdown.get("trigger_wrong_decisions", 0)
            
            print(f"   ✅ 正確的跳過決策: {skip_correct} 個")
            print(f"   ❌ 錯誤的跳過決策: {skip_wrong} 個")
            print(f"   ✅ 正確的觸發決策: {trigger_correct} 個")
            print(f"   ❌ 錯誤的觸發決策: {trigger_wrong} 個")
        
        # 智能建議
        recommendations = results.get("recommendations", [])
        if recommendations:
            print(f"\n💡 智能建議:")
            for i, rec in enumerate(recommendations, 1):
                print(f"   {i}. {rec}")
        
        print("="*100 + "\n")
    
    def print_detailed_case_analysis(self, results: Dict[str, Any]):
        """輸出詳細的案例分析（當啟用詳細模式時）"""
        if not results.get("evaluation_parameters", {}).get("verbose_mode", False):
            return
            
        case_details = results.get("detailed_case_results", [])
        if not case_details:
            return
        
        print("\n" + "🔍" + "="*90)
        print("📝 詳細案例分析報告")
        print("🔍" + "="*90)
        
        for i, case in enumerate(case_details, 1):
            question = case.get("question", "")[:80] + "..." if len(case.get("question", "")) > 80 else case.get("question", "")
            
            # For smart trigger, we compare smart vs baseline(no_rewrite)
            if results.get("evaluation_type") == "smart_trigger_strategy":
                baseline_mrr = case.get("no_rewrite_metrics", {}).get("mrr", 0.0)
                optimized_mrr = case.get("smart_trigger_metrics", {}).get("mrr", 0.0)
                optimized_label = "智能觸發"
            else: # For standard evaluation
                baseline_mrr = case.get("baseline_metrics", {}).get("mrr", 0.0)
                optimized_mrr = case.get("optimized_metrics", {}).get("mrr", 0.0)
                optimized_label = "優化"

            improvement = optimized_mrr - baseline_mrr
            
            # 狀態圖標
            if improvement > 0.1:
                status_icon = "🚀"  # 顯著提升
            elif improvement > 0.01:
                status_icon = "✅"  # 輕微提升
            elif improvement < -0.01:
                status_icon = "❌"  # 下降
            else:
                status_icon = "⚖️"   # 持平
            
            print(f"\n📋 案例 {i:2d}: {status_icon}")
            print(f"   問題: {question}")
            print(f"   基準 MRR: {baseline_mrr:.4f} | {optimized_label} MRR: {optimized_mrr:.4f} | 變化: {improvement:+.4f}")
            
            # 顯示重寫查詢
            rewritten_queries = case.get("rewritten_queries", [])
            if rewritten_queries:
                print(f"   重寫查詢 ({len(rewritten_queries)} 個):")
                for j, rq in enumerate(rewritten_queries, 1):
                    rq_short = rq[:60] + "..." if len(rq) > 60 else rq
                    print(f"     {j}. {rq_short}")
            
            # 顯示找到的相關文件
            expected_ids = set(case.get("expected_doc_ids", []))
            baseline_found = set(case.get("baseline_retrieved_ids", [])) & expected_ids
            optimized_found = set(case.get("optimized_retrieved_ids", [])) & expected_ids
            
            if baseline_found or optimized_found:
                print(f"   找到相關文件:")
                print(f"     基準: {list(baseline_found)} ({len(baseline_found)}/{len(expected_ids)})")
                print(f"     優化: {list(optimized_found)} ({len(optimized_found)}/{len(expected_ids)})")
        
        print("🔍" + "="*90 + "\n")

    def save_results(self, results: Dict[str, Any], output_path: str):
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=4, ensure_ascii=False)
            logger.info(f"評估結果已保存到: {output_path}")
        except Exception as e:
            logger.error(f"保存結果失敗: {e}", exc_info=True)

    async def run_evaluation_flow(self, dataset_path: str, eval_params: Dict):
        logger.info(f"從 {dataset_path} 加載測試數據集")
        try:
            with open(dataset_path, 'r', encoding='utf-8') as f:
                test_cases = json.load(f)
            logger.info(f"成功加載 {len(test_cases)} 個測試案例")
        except Exception as e:
            logger.error(f"加載測試數據集失敗: {e}", exc_info=True)
            return

        try:
            await self.initialize_services()
            
            # 根據評估模式選擇評估方法
            evaluation_mode = eval_params.get('evaluation_mode', 'standard')
            
            if evaluation_mode == 'smart_trigger':
                logger.info("🧠 執行智能觸發策略評估")
                results = await self.evaluate_smart_trigger_strategy(test_cases, eval_params)
                self.print_smart_trigger_results(results)
                output_prefix = "smart_trigger_evaluation"
            else:
                logger.info("📊 執行標準查詢重寫評估")
                results = await self.evaluate_retrieval_accuracy(test_cases, eval_params)
                self.print_results(results)
                output_prefix = "standard_evaluation"
            
            # 輸出詳細案例分析（如果啟用詳細模式）
            self.print_detailed_case_analysis(results)
            
            output_dir = os.path.join(os.path.dirname(__file__), 'extractions')
            os.makedirs(output_dir, exist_ok=True)
            timestamp = uuid.uuid4().hex[:8]
            output_filename = f"{output_prefix}_results_{timestamp}.json"
            output_path = os.path.join(output_dir, output_filename)
            self.save_results(results, output_path)

        finally:
            if self.session:
                await self.session.close()
                logger.info("HTTP session 已關閉")

async def main():
    parser = argparse.ArgumentParser(description="評估查詢重寫對檢索準確性的影響 - 支援智能觸發策略")
    parser.add_argument("--dataset", type=str, default="test_one.json", help="包含查詢和預期文檔ID的JSON數據集文件路徑")
    parser.add_argument("--top_k", type=int, default=10, help="檢索時返回的文檔數量")
    parser.add_argument("--similarity_threshold", type=float, default=0.2, help="檢索時的相似度閾值")
    parser.add_argument("--query_rewrite_count", type=int, default=3, help="為每個原始查詢生成多少個重寫版本")
    parser.add_argument("--verbose", action="store_true", help="啟用詳細模式，顯示每個測試案例的詳細結果")
    parser.add_argument("--save-detailed", action="store_true", help="保存詳細的個別案例分析結果")
    
    # 新增智能觸發相關參數
    parser.add_argument("--mode", type=str, choices=['standard', 'smart_trigger'], default='standard', 
                       help="評估模式: 'standard' 為標準重寫評估, 'smart_trigger' 為智能觸發策略評估")
    parser.add_argument("--confidence_threshold", type=float, default=0.75, 
                       help="智能觸發的置信度門檻 (僅在 smart_trigger 模式下生效)")
    
    args = parser.parse_args()

    eval_params = {
        "top_k": args.top_k,
        "similarity_threshold": args.similarity_threshold,
        "query_rewrite_count": args.query_rewrite_count,
        "verbose_mode": args.verbose,
        "save_detailed_analysis": args.save_detailed,
        "evaluation_mode": args.mode,
        "confidence_threshold": args.confidence_threshold
    }

    evaluator = QueryOptimizationRetrievalEvaluator()
    dataset_full_path = os.path.join(os.path.dirname(__file__), args.dataset)
    await evaluator.run_evaluation_flow(dataset_full_path, eval_params)

if __name__ == "__main__":
    asyncio.run(main()) 