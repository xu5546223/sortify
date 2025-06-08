import json
import asyncio
import logging
import sys
import argparse
from typing import List, Dict, Any, Optional
from collections import defaultdict
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

logger.info("評估系統：RRF融合檢索 vs 兩階段混合檢索 vs 傳統向量檢索 - 全面準確度對比分析")


class VectorRetrievalEvaluator:
    """兩階段混合檢索準確度評估器 - 使用API調用，支援多種搜索模式對比"""
    
    def __init__(self):
        """初始化評估器"""
        self.api_base_url = os.getenv('API_URL', 'http://localhost:8000')
        self.api_username = os.getenv('USERNAME')
        self.api_password = os.getenv('PASSWORD')
        if not self.api_username or not self.api_password:
            raise ValueError("請在.env文件中設置 USERNAME 和 PASSWORD")
        self.session = None
        self.access_token = None
        
        # 支援的搜索模式
        self.search_modes = {
            'rrf_fusion': '🚀 RRF 融合檢索',
            'hybrid': '兩階段混合檢索',
            'summary_only': '僅摘要向量搜索',
            'chunks_only': '僅內容塊搜索',
            'legacy': '傳統單階段搜索'
        }
        
        logger.info("混合檢索評估器初始化完成 - 支援多種搜索模式對比 (包含 RRF 融合檢索)")

    async def initialize_services(self):
        """初始化API連接"""
        try:
            self.session = aiohttp.ClientSession()
            if not await self._login_and_get_token(): # <<< MODIFIED: 使用統一的 aiohttp 登入
                raise Exception("無法獲取認證 token")
            await self._test_api_connection()
            logger.info("API連接初始化成功")
        except Exception as e:
            logger.error(f"API連接初始化失敗: {e}", exc_info=True)
            raise
    
    # <<< MODIFIED: 統一使用 aiohttp 進行登入
    async def _login_and_get_token(self) -> bool:
        """登入並獲取 JWT token，統一使用 aiohttp"""
        if not self.session:
            self.session = aiohttp.ClientSession()
        login_url = f"{self.api_base_url}/api/v1/auth/token"
        login_data = {"username": self.api_username, "password": self.api_password}
        logger.info(f"嘗試登入到: {login_url}")
        try:
            async with self.session.post(login_url, data=login_data) as response:
                response.raise_for_status() # 如果狀態碼不是 2xx，則引發異常
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

    async def _search_vectors_via_api(self, query: str, top_k: int, similarity_threshold: float, 
                                     search_mode: str = 'hybrid', enable_diversity: bool = True,
                                     rrf_weights: Optional[Dict[str, float]] = None,
                                     rrf_k_constant: Optional[int] = None) -> List[Dict]:
        """通過API執行向量檢索 - 支援多種搜索模式和動態RRF權重"""
        headers = self.get_auth_headers()
        url = f"{self.api_base_url}/api/v1/vector-db/semantic-search"
        
        # 新的API請求參數
        payload = {
            "query": query, 
            "top_k": top_k, 
            "similarity_threshold": similarity_threshold,
            "enable_hybrid_search": search_mode != 'legacy',  # 非傳統模式都啟用混合搜索
            "enable_diversity_optimization": enable_diversity
        }
        
        # 只有非傳統模式才設置search_type
        if search_mode != 'legacy':
            payload["search_type"] = search_mode
        
        # 添加RRF權重配置（僅用於rrf_fusion模式）
        if search_mode == 'rrf_fusion':
            if rrf_weights:
                payload["rrf_weights"] = rrf_weights
            if rrf_k_constant:
                payload["rrf_k_constant"] = rrf_k_constant
        
        try:
            async with self.session.post(url, json=payload, headers=headers) as response:
                response.raise_for_status()
                results = await response.json()
                mode_name = self.search_modes.get(search_mode, search_mode)
                weight_info = f" (權重: {rrf_weights}, k: {rrf_k_constant})" if rrf_weights else ""
                logger.info(f"[{mode_name}{weight_info}] 查詢 '{query[:30]}...' -> 檢索到 {len(results)} 個結果")
                return results
        except Exception as e:
            logger.error(f"[{search_mode}] 向量檢索API調用異常 for query '{query[:30]}...': {e}")
            return []

    async def evaluate_all_search_modes(self, test_cases: List[Dict], eval_params: Dict) -> Dict[str, Any]:
        """評估所有搜索模式的準確度並進行對比"""
        logger.info(f"開始評估所有搜索模式，參數: {eval_params}")
        
        results_by_mode = {}
        
        # 評估每種搜索模式
        for mode_key, mode_name in self.search_modes.items():
            logger.info(f"\n{'='*60}")
            logger.info(f"🔍 評估搜索模式: {mode_name} ({mode_key})")
            logger.info(f"{'='*60}")
            
            mode_results = await self._evaluate_single_mode(test_cases, eval_params, mode_key)
            results_by_mode[mode_key] = mode_results
            
            # 即時顯示該模式的結果
            self._print_single_mode_results(mode_results, mode_name)
        
        # 生成綜合對比結果
        comparison_results = self._generate_comparison_results(results_by_mode, eval_params)
        
        return comparison_results

    async def _evaluate_single_mode(self, test_cases: List[Dict], eval_params: Dict, search_mode: str) -> Dict[str, Any]:
        """評估單一搜索模式的準確度"""
        all_metrics = []
        verbose_mode = eval_params.get('verbose_mode', False)
        case_details = []  # 儲存個案詳細結果
        
        for i, test_case in enumerate(test_cases):
            question = test_case.get('question') or test_case.get('user_query')
            expected_doc_ids = test_case.get('expected_relevant_doc_ids', [])
            
            if not question or not expected_doc_ids:
                logger.warning(f"跳過案例 {i+1}，缺少必要欄位")
                continue
            
            search_results = await self._search_vectors_via_api(
                question, eval_params['top_k'], eval_params['similarity_threshold'], search_mode
            )
            retrieved_doc_ids = [doc.get('document_id', '') for doc in search_results]

            metrics = {
                "hit_rate": self._calculate_hit_rate(expected_doc_ids, retrieved_doc_ids),
                "mrr": self._calculate_mrr(expected_doc_ids, retrieved_doc_ids),
                "ndcg": self._calculate_ndcg(expected_doc_ids, retrieved_doc_ids)
            }
            all_metrics.append(metrics)
            
            # 詳細模式：記錄個案結果
            if verbose_mode:
                case_detail = {
                    "case_index": i + 1,
                    "question": question[:100] + "..." if len(question) > 100 else question,
                    "expected_doc_ids": expected_doc_ids,
                    "retrieved_doc_ids": retrieved_doc_ids,
                    "hit_found": bool(set(expected_doc_ids) & set(retrieved_doc_ids)),
                    "metrics": metrics
                }
                case_details.append(case_detail)
                
                # 即時顯示個案結果
                hit_found = "✅" if case_detail["hit_found"] else "❌"
                print(f"  案例 {i+1:2d}: {hit_found} MRR={metrics['mrr']:.3f} | {question[:60]}...")
        
        results = self._aggregate_results(all_metrics, len(test_cases), eval_params, search_mode)
        
        # 如果啟用詳細模式，加入個案分析
        if verbose_mode:
            results["case_details"] = case_details
            results["detailed_analysis"] = self._analyze_case_details(case_details)
        
        return results

    # 保留原有的評估方法作為向後兼容
    async def evaluate_retrieval_accuracy(self, test_cases: List[Dict], eval_params: Dict) -> Dict[str, Any]:
        """評估純向量檢索的準確度 - 向後兼容方法"""
        logger.info(f"開始評估純向量檢索，參數: {eval_params}")
        return await self._evaluate_single_mode(test_cases, eval_params, 'legacy')

    def _calculate_hit_rate(self, expected_ids: List[str], retrieved_ids: List[str]) -> Dict[str, float]:
        expected_set = set(expected_ids)
        return {f"@_k{k}": 1.0 if expected_set.intersection(set(retrieved_ids[:k])) else 0.0 for k in [1, 3, 5, 10]}

    def _calculate_mrr(self, expected_ids: List[str], retrieved_ids: List[str]) -> float:
        expected_set = set(expected_ids)
        for rank, doc_id in enumerate(retrieved_ids, 1):
            if doc_id in expected_set:
                return 1.0 / rank
        return 0.0
        
    def _calculate_ndcg(self, expected_ids: List[str], retrieved_ids: List[str]) -> Dict[str, float]:
        expected_set = set(expected_ids)
        ndcg_scores = {}
        for k in [1, 3, 5, 10]:
            relevance = [1 if doc_id in expected_set else 0 for doc_id in retrieved_ids[:k]]
            dcg = sum(rel / np.log2(i + 2) for i, rel in enumerate(relevance))
            idcg = sum(1 / np.log2(i + 2) for i in range(min(k, len(expected_ids))))
            ndcg_scores[f"@_k{k}"] = dcg / idcg if idcg > 0 else 0.0
        return ndcg_scores

    def _aggregate_results(self, all_metrics: List[Dict], total_cases: int, eval_params: Dict, search_mode: str = None) -> Dict:
        """匯總所有評估指標"""
        if not all_metrics:
            return {"error": "No metrics were calculated."}

        df = pd.json_normalize(all_metrics)
        mean_scores = df.mean().to_dict()
        hit_rate_scores = {k.replace('hit_rate.@_k', '@'): v for k, v in mean_scores.items() if k.startswith('hit_rate')}
        ndcg_scores = {k.replace('ndcg.@_k', '@'): v for k, v in mean_scores.items() if k.startswith('ndcg')}

        evaluation_type = "hybrid_vector_retrieval" if search_mode == 'hybrid' else f"{search_mode}_vector_retrieval" if search_mode else "pure_vector_retrieval_baseline"

        return {
            "evaluation_type": evaluation_type,
            "search_mode": search_mode,
            "total_test_cases": total_cases,
            "processed_cases": len(all_metrics),
            "retrieval_metrics": {
                "hit_rate": hit_rate_scores,
                "mrr": mean_scores.get('mrr', 0.0),
                "ndcg": ndcg_scores
            },
            "evaluation_parameters": eval_params
        }
    
    def _generate_comparison_results(self, results_by_mode: Dict[str, Dict], eval_params: Dict) -> Dict[str, Any]:
        """生成搜索模式對比結果"""
        comparison = {
            "evaluation_type": "multi_mode_vector_retrieval_comparison",
            "evaluation_parameters": eval_params,
            "modes_compared": list(self.search_modes.keys()),
            "results_by_mode": results_by_mode,
            "performance_ranking": self._rank_modes_by_performance(results_by_mode),
            "improvement_analysis": self._analyze_improvements(results_by_mode)
        }
        
        return comparison

    def _rank_modes_by_performance(self, results_by_mode: Dict[str, Dict]) -> List[Dict]:
        """根據MRR分數排名各種搜索模式"""
        rankings = []
        
        for mode, results in results_by_mode.items():
            mrr_score = results.get('retrieval_metrics', {}).get('mrr', 0.0)
            hit_rate_at_5 = results.get('retrieval_metrics', {}).get('hit_rate', {}).get('@5', 0.0)
            
            rankings.append({
                "mode": mode,
                "mode_name": self.search_modes[mode],
                "mrr_score": mrr_score,
                "hit_rate_at_5": hit_rate_at_5,
                "composite_score": (mrr_score * 0.6) + (hit_rate_at_5 * 0.4)  # 綜合評分
            })
        
        # 按綜合評分排序
        rankings.sort(key=lambda x: x["composite_score"], reverse=True)
        
        return rankings

    def _analyze_improvements(self, results_by_mode: Dict[str, Dict]) -> Dict[str, Any]:
        """分析 RRF 融合檢索和兩階段混合檢索相對於傳統檢索的改進"""
        rrf_results = results_by_mode.get("rrf_fusion", {}).get("retrieval_metrics", {})
        hybrid_results = results_by_mode.get("hybrid", {}).get("retrieval_metrics", {})
        legacy_results = results_by_mode.get("legacy", {}).get("retrieval_metrics", {})
        
        if not legacy_results:
            return {"error": "缺少傳統檢索基準數據"}
        
        improvements = {}
        
        # MRR 改進分析
        legacy_mrr = legacy_results.get("mrr", 0.0)
        
        # 與傳統檢索對比
        comparisons = {}
        
        # RRF 融合檢索對比
        if rrf_results:
            rrf_mrr = rrf_results.get("mrr", 0.0)
            comparisons["rrf_vs_legacy"] = {
                "rrf": rrf_mrr,
                "legacy": legacy_mrr,
                "improvement_percentage": ((rrf_mrr - legacy_mrr) / max(legacy_mrr, 0.001)) * 100
            }
        
        # 兩階段混合檢索對比
        if hybrid_results:
            hybrid_mrr = hybrid_results.get("mrr", 0.0)
            comparisons["hybrid_vs_legacy"] = {
                "hybrid": hybrid_mrr,
                "legacy": legacy_mrr,
                "improvement_percentage": ((hybrid_mrr - legacy_mrr) / max(legacy_mrr, 0.001)) * 100
            }
        
        # RRF vs 兩階段混合檢索對比
        if rrf_results and hybrid_results:
            rrf_mrr = rrf_results.get("mrr", 0.0)
            hybrid_mrr = hybrid_results.get("mrr", 0.0)
            comparisons["rrf_vs_hybrid"] = {
                "rrf": rrf_mrr,
                "hybrid": hybrid_mrr,
                "improvement_percentage": ((rrf_mrr - hybrid_mrr) / max(hybrid_mrr, 0.001)) * 100
            }
        
        improvements["mrr_comparisons"] = comparisons
        
        # Hit Rate 改進分析
        improvements["hit_rate_comparisons"] = {}
        legacy_hr = legacy_results.get("hit_rate", {})
        
        # 對每個 Hit Rate 指標進行比較
        for key in legacy_hr.keys():
            legacy_hr_val = legacy_hr.get(key, 0.0)
            key_comparisons = {"legacy": legacy_hr_val}
            
            # RRF vs Legacy
            if rrf_results:
                rrf_hr = rrf_results.get("hit_rate", {})
                rrf_hr_val = rrf_hr.get(key, 0.0)
                key_comparisons["rrf_vs_legacy"] = {
                    "rrf": rrf_hr_val,
                    "improvement_percentage": ((rrf_hr_val - legacy_hr_val) / max(legacy_hr_val, 0.001)) * 100
                }
            
            # Hybrid vs Legacy
            if hybrid_results:
                hybrid_hr = hybrid_results.get("hit_rate", {})
                hybrid_hr_val = hybrid_hr.get(key, 0.0)
                key_comparisons["hybrid_vs_legacy"] = {
                    "hybrid": hybrid_hr_val,
                    "improvement_percentage": ((hybrid_hr_val - legacy_hr_val) / max(legacy_hr_val, 0.001)) * 100
                }
            
            # RRF vs Hybrid
            if rrf_results and hybrid_results:
                rrf_hr = rrf_results.get("hit_rate", {})
                hybrid_hr = hybrid_results.get("hit_rate", {})
                rrf_hr_val = rrf_hr.get(key, 0.0)
                hybrid_hr_val = hybrid_hr.get(key, 0.0)
                key_comparisons["rrf_vs_hybrid"] = {
                    "rrf": rrf_hr_val,
                    "hybrid": hybrid_hr_val,
                    "improvement_percentage": ((rrf_hr_val - hybrid_hr_val) / max(hybrid_hr_val, 0.001)) * 100
                }
            
            improvements["hit_rate_comparisons"][key] = key_comparisons
        
        # nDCG 改進分析
        improvements["ndcg_comparisons"] = {}
        legacy_ndcg = legacy_results.get("ndcg", {})
        
        # 對每個 nDCG 指標進行比較
        for key in legacy_ndcg.keys():
            legacy_ndcg_val = legacy_ndcg.get(key, 0.0)
            key_comparisons = {"legacy": legacy_ndcg_val}
            
            # RRF vs Legacy
            if rrf_results:
                rrf_ndcg = rrf_results.get("ndcg", {})
                rrf_ndcg_val = rrf_ndcg.get(key, 0.0)
                key_comparisons["rrf_vs_legacy"] = {
                    "rrf": rrf_ndcg_val,
                    "improvement_percentage": ((rrf_ndcg_val - legacy_ndcg_val) / max(legacy_ndcg_val, 0.001)) * 100
                }
            
            # Hybrid vs Legacy
            if hybrid_results:
                hybrid_ndcg = hybrid_results.get("ndcg", {})
                hybrid_ndcg_val = hybrid_ndcg.get(key, 0.0)
                key_comparisons["hybrid_vs_legacy"] = {
                    "hybrid": hybrid_ndcg_val,
                    "improvement_percentage": ((hybrid_ndcg_val - legacy_ndcg_val) / max(legacy_ndcg_val, 0.001)) * 100
                }
            
            # RRF vs Hybrid
            if rrf_results and hybrid_results:
                rrf_ndcg = rrf_results.get("ndcg", {})
                hybrid_ndcg = hybrid_results.get("ndcg", {})
                rrf_ndcg_val = rrf_ndcg.get(key, 0.0)
                hybrid_ndcg_val = hybrid_ndcg.get(key, 0.0)
                key_comparisons["rrf_vs_hybrid"] = {
                    "rrf": rrf_ndcg_val,
                    "hybrid": hybrid_ndcg_val,
                    "improvement_percentage": ((rrf_ndcg_val - hybrid_ndcg_val) / max(hybrid_ndcg_val, 0.001)) * 100
                }
            
            improvements["ndcg_comparisons"][key] = key_comparisons
        
        # 生成智能建議
        recommendations = []
        
        # 比較 RRF 與其他方法
        if rrf_results and hybrid_results:
            rrf_vs_legacy = comparisons.get("rrf_vs_legacy", {}).get("improvement_percentage", 0)
            rrf_vs_hybrid = comparisons.get("rrf_vs_hybrid", {}).get("improvement_percentage", 0)
            hybrid_vs_legacy = comparisons.get("hybrid_vs_legacy", {}).get("improvement_percentage", 0)
            
            # 確定最佳策略
            if rrf_vs_legacy > 15 and rrf_vs_hybrid > 5:
                recommendations.append("🚀 強烈建議使用 RRF 融合檢索！相比傳統檢索提升顯著，且優於兩階段混合檢索")
            elif rrf_vs_legacy > 10:
                recommendations.append("🎯 建議優先考慮 RRF 融合檢索，相比傳統檢索有明顯改進")
            elif hybrid_vs_legacy > 10:
                recommendations.append("✅ 建議使用兩階段混合檢索，性能穩定且有良好改進")
            elif rrf_vs_legacy > 0:
                recommendations.append("💡 RRF 融合檢索有輕微改進，可根據計算資源情況選擇")
            else:
                recommendations.append("⚠️  需要進一步調優檢索參數或檢查數據質量")
                
            # 添加具體的性能數據
            recommendations.append(f"📊 性能數據: RRF vs Legacy (+{rrf_vs_legacy:.1f}%), RRF vs Hybrid (+{rrf_vs_hybrid:.1f}%)")
        
        elif rrf_results:
            rrf_vs_legacy = comparisons.get("rrf_vs_legacy", {}).get("improvement_percentage", 0)
            if rrf_vs_legacy > 10:
                recommendations.append("🚀 建議採用 RRF 融合檢索，相比傳統檢索有顯著提升")
            else:
                recommendations.append("💡 RRF 融合檢索有改進，建議進一步評估")
        
        elif hybrid_results:
            hybrid_vs_legacy = comparisons.get("hybrid_vs_legacy", {}).get("improvement_percentage", 0)
            if hybrid_vs_legacy > 10:
                recommendations.append("✅ 建議採用兩階段混合檢索，相比傳統檢索有顯著改進")
            else:
                recommendations.append("⚠️  兩階段混合檢索改進有限，需要調優參數")
        
        improvements["recommendations"] = recommendations
        
        return improvements

    def _analyze_case_details(self, case_details: List[Dict]) -> Dict[str, Any]:
        """分析個案詳細結果，提供洞察"""
        if not case_details:
            return {}
        
        total_cases = len(case_details)
        successful_cases = [case for case in case_details if case["hit_found"]]
        failed_cases = [case for case in case_details if not case["hit_found"]]
        
        analysis = {
            "總案例數": total_cases,
            "成功案例數": len(successful_cases),
            "失敗案例數": len(failed_cases),
            "成功率": len(successful_cases) / total_cases if total_cases > 0 else 0,
            "平均MRR": sum(case["metrics"]["mrr"] for case in case_details) / total_cases if total_cases > 0 else 0
        }
        
        # 分析失敗案例的特徵
        if failed_cases:
            failed_questions = [case["question"] for case in failed_cases[:5]]  # 只顯示前5個
            analysis["失敗案例範例"] = failed_questions
        
        # 分析高分案例
        high_score_cases = [case for case in case_details if case["metrics"]["mrr"] >= 0.5]
        if high_score_cases:
            analysis["高分案例數"] = len(high_score_cases)
            analysis["高分案例佔比"] = len(high_score_cases) / total_cases
        
        return analysis

    def _print_single_mode_results(self, results: Dict[str, Any], mode_name: str):
        """打印單一模式的評估結果"""
        metrics = results.get("retrieval_metrics", {})
        
        hr_str = ", ".join([f"{k}:{v:.4f}" for k, v in metrics.get("hit_rate", {}).items()])
        ndcg_str = ", ".join([f"{k}:{v:.4f}" for k, v in metrics.get("ndcg", {}).items()])
        
        print(f"\n📊 {mode_name} 評估結果:")
        print(f"   - MRR: {metrics.get('mrr', 0.0):.4f}")
        print(f"   - Hit Rate: {hr_str}")
        print(f"   - nDCG: {ndcg_str}")

    def print_comparison_results(self, results: Dict[str, Any]):
        """以對人類友好的格式輸出對比評估結果"""
        print("\n" + "="*100)
        print("🏆 RRF 融合檢索 vs 兩階段混合檢索 vs 傳統向量檢索 - 全面性能對比")
        print("="*100)
        
        # 顯示每個模式的詳細指標
        results_by_mode = results.get("detailed_results_by_mode", {})
        
        print("\n📊 各搜索模式詳細指標:")
        for mode_name, mode_results in results_by_mode.items():
            metrics = mode_results.get("retrieval_metrics", {})
            hr_str = ", ".join([f"@{k}:{v:.4f}" for k, v in metrics.get("hit_rate", {}).items()])
            ndcg_str = ", ".join([f"@{k}:{v:.4f}" for k, v in metrics.get("ndcg", {}).items()])
            
            print(f"\n   🔍 {mode_name}:")
            print(f"      - MRR: {metrics.get('mrr', 0.0):.4f}")
            print(f"      - Hit Rate: {hr_str}")
            print(f"      - nDCG: {ndcg_str}")
        
        # 顯示性能排名
        rankings = results.get("performance_ranking", [])
        print("\n🥇 搜索模式性能排名:")
        for i, rank in enumerate(rankings, 1):
            print(f"   {i}. {rank['mode_name']:<25} | MRR: {rank['mrr_score']:.4f} | Hit@5: {rank['hit_rate_at_5']:.4f} | 綜合評分: {rank['composite_score']:.4f}")
        
        # 顯示改進分析
        improvements = results.get("improvement_analysis", {})
        if "error" not in improvements:
            print(f"\n📈 性能改進分析:")
            
            # MRR 對比分析
            mrr_comparisons = improvements.get("mrr_comparisons", {})
            if mrr_comparisons:
                print(f"   🎯 MRR 對比:")
                for comparison_type, comparison_data in mrr_comparisons.items():
                    if comparison_type.endswith("_vs_legacy"):
                        method = comparison_type.split("_vs_")[0].upper()
                        print(f"     {method} vs Legacy: {comparison_data.get('legacy', 0.0):.4f} → {comparison_data.get(comparison_type.split('_vs_')[0], 0.0):.4f} ({comparison_data.get('improvement_percentage', 0.0):+.2f}%)")
                    elif comparison_type == "rrf_vs_hybrid":
                        print(f"     RRF vs Hybrid: {comparison_data.get('hybrid', 0.0):.4f} → {comparison_data.get('rrf', 0.0):.4f} ({comparison_data.get('improvement_percentage', 0.0):+.2f}%)")
            
            # Hit Rate 對比分析
            hr_comparisons = improvements.get("hit_rate_comparisons", {})
            if hr_comparisons:
                print(f"   📊 Hit Rate 對比:")
                for metric, comparisons in hr_comparisons.items():
                    legacy_val = comparisons.get("legacy", 0.0)
                    print(f"     {metric} (基準: {legacy_val:.4f}):")
                    
                    if "rrf_vs_legacy" in comparisons:
                        rrf_data = comparisons["rrf_vs_legacy"]
                        print(f"       RRF: {rrf_data.get('rrf', 0.0):.4f} ({rrf_data.get('improvement_percentage', 0.0):+.2f}%)")
                    
                    if "hybrid_vs_legacy" in comparisons:
                        hybrid_data = comparisons["hybrid_vs_legacy"]
                        print(f"       Hybrid: {hybrid_data.get('hybrid', 0.0):.4f} ({hybrid_data.get('improvement_percentage', 0.0):+.2f}%)")
            
            # nDCG 對比分析
            ndcg_comparisons = improvements.get("ndcg_comparisons", {})
            if ndcg_comparisons:
                print(f"   📈 nDCG 對比:")
                for metric, comparisons in ndcg_comparisons.items():
                    legacy_val = comparisons.get("legacy", 0.0)
                    print(f"     {metric} (基準: {legacy_val:.4f}):")
                    
                    if "rrf_vs_legacy" in comparisons:
                        rrf_data = comparisons["rrf_vs_legacy"]
                        print(f"       RRF: {rrf_data.get('rrf', 0.0):.4f} ({rrf_data.get('improvement_percentage', 0.0):+.2f}%)")
                    
                    if "hybrid_vs_legacy" in comparisons:
                        hybrid_data = comparisons["hybrid_vs_legacy"]
                        print(f"       Hybrid: {hybrid_data.get('hybrid', 0.0):.4f} ({hybrid_data.get('improvement_percentage', 0.0):+.2f}%)")
            
            # 顯示建議
            recommendations = improvements.get("recommendations", [])
            if recommendations:
                print(f"\n💡 智能建議:")
                for rec in recommendations:
                    print(f"   {rec}")
        
        print("="*100 + "\n")

    # 保留原有的結果輸出函式作為向後兼容
    def print_results(self, results: Dict[str, Any]):
        """以對人類友好的格式輸出評估結果 - 向後兼容"""
        params = results.get("evaluation_parameters", {})
        metrics = results.get("retrieval_metrics", {})
        
        # 準備 Hit Rate 和 NDCG 的字串以便對齊打印
        hr_str = ", ".join([f"{k}:{v:.4f}" for k, v in metrics.get("hit_rate", {}).items()])
        ndcg_str = ", ".join([f"{k}:{v:.4f}" for k, v in metrics.get("ndcg", {}).items()])
        
        print("\n" + "="*80)
        print("📊 純向量檢索基準線 (Baseline) 評估結果")
        print("="*80)
        print(f"🎯 總案例數: {results.get('total_test_cases', 0):<5} | "
              f"已處理案例: {results.get('processed_cases', 0):<5}")
        print(f"⚙️  評估參數: Top-K={params.get('top_k')}, Threshold={params.get('similarity_threshold')}")
        print("-"*80)
        print("📈 檢索性能指標:")
        print(f"   - MRR (Mean Reciprocal Rank): {metrics.get('mrr', 0.0):.4f}")
        print(f"   - Hit Rate:                 {hr_str}")
        print(f"   - nDCG:                     {ndcg_str}")
        print("="*80 + "\n")

    def save_results_to_json(self, results: Dict[str, Any], output_path: str):
        """將詳細評估結果保存到JSON文件"""
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=4)
            logger.info(f"詳細評估結果已保存至: {output_path}")
        except Exception as e:
            logger.error(f"保存評估結果失敗: {e}")

    async def run_evaluation_flow(self, dataset_path: str, eval_params: Dict, comparison_mode: bool = True):
        """執行完整的評估流程 - 支援單模式或多模式對比"""
        mode_desc = "多模式對比評估" if comparison_mode else "單模式評估"
        logger.info(f"開始{mode_desc}流程...")
        
        if not os.path.isabs(dataset_path):
            dataset_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), dataset_path)
        logger.info(f"使用資料集: {dataset_path}")

        try:
            with open(dataset_path, 'r', encoding='utf-8') as f:
                test_cases = json.load(f)
            logger.info(f"成功載入 {len(test_cases)} 個測試案例")
        except Exception as e:
            logger.error(f"載入測試數據失敗: {e}")
            return
        
        try:
            await self.initialize_services()
            
            if comparison_mode:
                # 多模式對比評估
                results = await self.evaluate_all_search_modes(test_cases, eval_params)
                self.print_comparison_results(results)
                output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rrf_hybrid_legacy_retrieval_comparison.json")
            else:
                # 單模式評估（向後兼容）
                results = await self.evaluate_retrieval_accuracy(test_cases, eval_params)
                self.print_results(results)
                output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vector_retrieval_baseline_results.json")
            
            self.save_results_to_json(results, output_path)
        finally:
            if self.session and not self.session.closed:
                await self.session.close()
                logger.info("HTTP會話已關閉")

    async def _evaluate_rrf_with_weights(self, test_cases: List[Dict], eval_params: Dict, 
                                        rrf_weights: Dict[str, float], rrf_k_constant: int,
                                        description: str = "") -> Dict[str, Any]:
        """使用指定的RRF權重和K值評估檢索性能"""
        all_metrics = []
        verbose_mode = eval_params.get('verbose_mode', False)
        
        for i, test_case in enumerate(test_cases):
            question = test_case.get('question') or test_case.get('user_query')
            expected_doc_ids = test_case.get('expected_relevant_doc_ids', [])
            
            if not question or not expected_doc_ids:
                continue
            
            search_results = await self._search_vectors_via_api(
                question, eval_params['top_k'], eval_params['similarity_threshold'], 
                'rrf_fusion', True, rrf_weights, rrf_k_constant
            )
            retrieved_doc_ids = [doc.get('document_id', '') for doc in search_results]

            metrics = {
                "hit_rate": self._calculate_hit_rate(expected_doc_ids, retrieved_doc_ids),
                "mrr": self._calculate_mrr(expected_doc_ids, retrieved_doc_ids),
                "ndcg": self._calculate_ndcg(expected_doc_ids, retrieved_doc_ids)
            }
            all_metrics.append(metrics)
            
            if verbose_mode:
                hit_found = "✅" if set(expected_doc_ids) & set(retrieved_doc_ids) else "❌"
                weights_str = f"S:{rrf_weights['summary']:.1f}/C:{rrf_weights['chunks']:.1f}/k:{rrf_k_constant}"
                print(f"  [{weights_str}] 案例 {i+1:2d}: {hit_found} MRR={metrics['mrr']:.3f}")
        
        return self._aggregate_results(all_metrics, len(test_cases), eval_params, 'rrf_fusion')

    async def optimize_rrf_weights_and_k(self, test_cases: List[Dict], eval_params: Dict) -> Dict[str, Any]:
        """
        🎯 RRF 權重+K值 聯合調優：四步走策略
        
        步驟一：公平的起點 (1.0, 1.0, k=60)
        步驟二：K值敏感性分析
        步驟三：基於假設的權重微調
        步驟四：聯合網格搜索優化
        """
        logger.info("🚀 開始 RRF 權重+K值 聯合調優 - 四步走策略")
        
        # 定義測試範圍
        k_values_to_test = [20, 30, 45, 60, 80, 100, 120]  # K值測試範圍
        optimization_results = {}
        
        # === 步驟一：公平的起點 ===
        logger.info("\n" + "="*70)
        logger.info("📊 步驟一：公平的起點 (The Baseline)")
        logger.info("="*70)
        
        baseline_weights = {"summary": 1.0, "chunks": 1.0}
        baseline_k = 60
        baseline_result = await self._evaluate_rrf_with_weights(
            test_cases, eval_params, baseline_weights, baseline_k, description="公平起點 (1.0,1.0,k=60)"
        )
        optimization_results["baseline"] = {
            "weights": baseline_weights,
            "k_constant": baseline_k,
            "results": baseline_result,
            "description": "公平的起點 - 無偏見的基準線"
        }
        
        baseline_mrr = baseline_result.get("retrieval_metrics", {}).get("mrr", 0.0)
        logger.info(f"✅ 基準線 MRR (1.0,1.0,k=60): {baseline_mrr:.4f}")
        
        # === 步驟二：K值敏感性分析 ===
        logger.info("\n" + "="*70)
        logger.info("🔬 步驟二：K值敏感性分析 (K-Value Sensitivity)")
        logger.info("="*70)
        
        best_k_mrr = baseline_mrr
        best_k_value = baseline_k
        k_analysis_results = {}
        
        logger.info(f"🧪 測試 {len(k_values_to_test)} 個不同的 K 值")
        
        for i, k_val in enumerate(k_values_to_test):
            if k_val == baseline_k:  # 跳過基準線
                continue
                
            logger.info(f"🔍 K值測試 {i+1}/{len(k_values_to_test)}: k={k_val}")
            
            result = await self._evaluate_rrf_with_weights(
                test_cases, eval_params, baseline_weights, k_val, 
                description=f"K值敏感性測試 k={k_val}"
            )
            
            optimization_results[f"k_test_{k_val}"] = {
                "weights": baseline_weights,
                "k_constant": k_val,
                "results": result,
                "description": f"K值測試 k={k_val}"
            }
            
            mrr_score = result.get("retrieval_metrics", {}).get("mrr", 0.0)
            improvement = ((mrr_score - baseline_mrr) / max(baseline_mrr, 0.001)) * 100
            k_analysis_results[k_val] = {"mrr": mrr_score, "improvement": improvement}
            
            logger.info(f"   MRR: {mrr_score:.4f} (相對基準 {improvement:+.1f}%)")
            
            if mrr_score > best_k_mrr:
                best_k_mrr = mrr_score
                best_k_value = k_val
        
        logger.info(f"✨ K值分析完成，最佳 k={best_k_value}, MRR={best_k_mrr:.4f}")
        
        # === 步驟三：基於假設的權重微調 ===
        logger.info("\n" + "="*70)
        logger.info("🧠 步驟三：基於假設的權重微調 (Hypothesis-Driven)")
        logger.info("="*70)
        
        hypothesis_configs = [
            # 假設A：摘要為王 (使用最佳K值)
            {"summary": 1.2, "chunks": 1.0, "desc": "輕微偏重摘要"},
            {"summary": 1.5, "chunks": 1.0, "desc": "明顯偏重摘要"},
            {"summary": 2.0, "chunks": 1.0, "desc": "強烈偏重摘要"},
            
            # 假設B：細節為王 (使用最佳K值)
            {"summary": 1.0, "chunks": 1.2, "desc": "輕微偏重內容塊"},
            {"summary": 1.0, "chunks": 1.5, "desc": "明顯偏重內容塊"},
            {"summary": 1.0, "chunks": 2.0, "desc": "強烈偏重內容塊"},
            
            # 假設C：平衡但有微調
            {"summary": 0.8, "chunks": 1.0, "desc": "輕微懲罰摘要"},
            {"summary": 1.0, "chunks": 0.8, "desc": "輕微懲罰內容塊"},
            {"summary": 1.3, "chunks": 1.3, "desc": "同步提升"},
        ]
        
        best_hypothesis = None
        best_hypothesis_mrr = best_k_mrr
        best_hypothesis_k = best_k_value
        
        logger.info(f"🧪 使用最佳 k={best_k_value} 測試 {len(hypothesis_configs)} 個假設")
        
        for i, config in enumerate(hypothesis_configs):
            weights = {"summary": config["summary"], "chunks": config["chunks"]}
            logger.info(f"🧪 測試假設 {i+1}/{len(hypothesis_configs)}: {config['desc']} {weights} (k={best_k_value})")
            
            result = await self._evaluate_rrf_with_weights(
                test_cases, eval_params, weights, best_k_value, description=config['desc']
            )
            
            optimization_results[f"hypothesis_{i+1}"] = {
                "weights": weights,
                "k_constant": best_k_value,
                "results": result,
                "description": config['desc']
            }
            
            mrr_score = result.get("retrieval_metrics", {}).get("mrr", 0.0)
            improvement = ((mrr_score - baseline_mrr) / max(baseline_mrr, 0.001)) * 100
            
            logger.info(f"   MRR: {mrr_score:.4f} (相對基準 {improvement:+.1f}%)")
            
            if mrr_score > best_hypothesis_mrr:
                best_hypothesis = {**config, "k": best_k_value}
                best_hypothesis_mrr = mrr_score
                best_hypothesis_k = best_k_value
        
        logger.info(f"✨ 最佳假設: {best_hypothesis['desc'] if best_hypothesis else '基準線'}")
        logger.info(f"   MRR: {best_hypothesis_mrr:.4f}, k={best_hypothesis_k}")
        
        # === 步驟四：聯合網格搜索優化 ===
        logger.info("\n" + "="*70)
        logger.info("🔬 步驟四：聯合網格搜索 (Joint Grid Search)")
        logger.info("="*70)
        
        # 基於前面的結果選擇精細搜索範圍
        if best_hypothesis:
            base_summary = best_hypothesis["summary"]
            base_chunks = best_hypothesis["chunks"]
            fine_k_values = self._get_fine_k_range(best_k_value)
        else:
            base_summary = 1.0
            base_chunks = 1.0
            fine_k_values = [best_k_value - 10, best_k_value, best_k_value + 10]
        
        # 生成聯合搜索配置
        joint_configs = []
        for k_val in fine_k_values:
            if k_val <= 0:
                continue
            for s_delta in [-0.2, -0.1, 0, 0.1, 0.2]:
                for c_delta in [-0.2, -0.1, 0, 0.1, 0.2]:
                    new_summary = max(0.1, base_summary + s_delta)
                    new_chunks = max(0.1, base_chunks + c_delta)
                    joint_configs.append({
                        "summary": round(new_summary, 1),
                        "chunks": round(new_chunks, 1),
                        "k": k_val,
                        "desc": f"聯合搜索 S:{new_summary:.1f} C:{new_chunks:.1f} k:{k_val}"
                    })
        
        # 去重並限制數量
        unique_joint_configs = []
        seen_configs = set()
        for config in joint_configs:
            config_key = (config["summary"], config["chunks"], config["k"])
            baseline_key = (1.0, 1.0, 60)
            if config_key not in seen_configs and config_key != baseline_key:
                seen_configs.add(config_key)
                unique_joint_configs.append(config)
                if len(unique_joint_configs) >= 15:  # 限制搜索數量
                    break
        
        best_joint_mrr = best_hypothesis_mrr
        best_joint_config = None
        
        logger.info(f"🔍 將測試 {len(unique_joint_configs)} 個聯合配置")
        
        for i, config in enumerate(unique_joint_configs):
            weights = {"summary": config["summary"], "chunks": config["chunks"]}
            logger.info(f"🔬 聯合搜索 {i+1}/{len(unique_joint_configs)}: {weights} k={config['k']}")
            
            result = await self._evaluate_rrf_with_weights(
                test_cases, eval_params, weights, config['k'], description=config['desc']
            )
            
            optimization_results[f"joint_{i+1}"] = {
                "weights": weights,
                "k_constant": config['k'],
                "results": result,
                "description": config['desc']
            }
            
            mrr_score = result.get("retrieval_metrics", {}).get("mrr", 0.0)
            improvement = ((mrr_score - baseline_mrr) / max(baseline_mrr, 0.001)) * 100
            
            logger.info(f"   MRR: {mrr_score:.4f} (相對基準 {improvement:+.1f}%)")
            
            if mrr_score > best_joint_mrr:
                best_joint_config = config
                best_joint_mrr = mrr_score
        
        # 生成最終聯合優化報告
        joint_summary = self._generate_joint_optimization_summary(
            optimization_results, baseline_mrr, best_joint_mrr, best_joint_config,
            k_analysis_results, best_k_value
        )
        
        return {
            "optimization_type": "rrf_weight_and_k_joint_optimization",
            "baseline_mrr": baseline_mrr,
            "best_mrr": best_joint_mrr,
            "improvement_percentage": ((best_joint_mrr - baseline_mrr) / max(baseline_mrr, 0.001)) * 100,
            "best_configuration": best_joint_config,
            "best_k_from_sensitivity": best_k_value,
            "k_sensitivity_analysis": k_analysis_results,
            "all_results": optimization_results,
            "joint_optimization_summary": joint_summary,
            "evaluation_parameters": eval_params
        }

    def _get_fine_k_range(self, best_k: int) -> List[int]:
        """基於最佳K值生成精細搜索範圍"""
        fine_range = []
        
        # 在最佳K值周圍生成精細範圍
        for delta in [-15, -10, -5, 0, 5, 10, 15]:
            new_k = best_k + delta
            if 10 <= new_k <= 150:  # 合理的K值範圍
                fine_range.append(new_k)
        
        return sorted(list(set(fine_range)))

    def _generate_joint_optimization_summary(self, all_results: Dict, baseline_mrr: float, 
                                           best_mrr: float, best_config: Optional[Dict],
                                           k_analysis: Dict, best_k: int) -> Dict[str, Any]:
        """生成聯合優化總結"""
        
        summary = {
            "baseline_performance": baseline_mrr,
            "best_performance": best_mrr,
            "total_improvement": ((best_mrr - baseline_mrr) / max(baseline_mrr, 0.001)) * 100,
            "best_weights": {"summary": best_config["summary"], "chunks": best_config["chunks"]} if best_config else {"summary": 1.0, "chunks": 1.0},
            "best_k_constant": best_config["k"] if best_config else 60,
            "optimization_stages": {
                "stage1_baseline": {"mrr": baseline_mrr, "description": "公平起點 (1.0, 1.0, k=60)"},
                "stage2_k_sensitivity": self._analyze_k_sensitivity(k_analysis, baseline_mrr, best_k),
                "stage3_hypothesis": self._analyze_hypothesis_stage_with_k(all_results, baseline_mrr),
                "stage4_joint_search": self._analyze_joint_stage(all_results, baseline_mrr)
            }
        }
        
        # 生成智能建議
        total_improvement = summary["total_improvement"]
        k_improvement = k_analysis.get(best_k, {}).get("improvement", 0)
        
        if total_improvement > 20:
            summary["recommendation"] = f"🚀 強烈建議採用聯合優化配置！性能提升 {total_improvement:.1f}%"
        elif total_improvement > 10:
            summary["recommendation"] = f"✅ 建議採用聯合優化配置，有顯著改進 {total_improvement:.1f}%"
        elif k_improvement > 5:
            summary["recommendation"] = f"💡 建議至少調整K值到 {best_k}，K值優化帶來 {k_improvement:.1f}% 改進"
        elif total_improvement > 0:
            summary["recommendation"] = f"💡 聯合優化有輕微改進 {total_improvement:.1f}%，可根據實際情況選擇"
        else:
            summary["recommendation"] = "⚠️ 預設配置 (1.0, 1.0, k=60) 已經是較佳選擇"
        
        return summary

    def _analyze_k_sensitivity(self, k_analysis: Dict, baseline_mrr: float, best_k: int) -> Dict[str, Any]:
        """分析K值敏感性結果"""
        if not k_analysis:
            return {"best_k": 60, "improvement": 0.0, "sensitivity": "無數據"}
        
        best_k_data = k_analysis.get(best_k, {})
        
        # 計算K值敏感性程度
        improvements = [data.get("improvement", 0) for data in k_analysis.values()]
        max_improvement = max(improvements) if improvements else 0
        min_improvement = min(improvements) if improvements else 0
        sensitivity_range = max_improvement - min_improvement
        
        if sensitivity_range > 10:
            sensitivity_level = "高敏感性"
        elif sensitivity_range > 5:
            sensitivity_level = "中等敏感性"
        else:
            sensitivity_level = "低敏感性"
        
        return {
            "best_k": best_k,
            "best_mrr": best_k_data.get("mrr", baseline_mrr),
            "improvement": best_k_data.get("improvement", 0.0),
            "sensitivity_level": sensitivity_level,
            "sensitivity_range": sensitivity_range,
            "tested_k_values": len(k_analysis)
        }

    def _analyze_hypothesis_stage_with_k(self, all_results: Dict, baseline_mrr: float) -> Dict[str, Any]:
        """分析假設階段的結果（包含K值信息）"""
        hypothesis_results = {k: v for k, v in all_results.items() if k.startswith('hypothesis_')}
        
        if not hypothesis_results:
            return {"best_mrr": baseline_mrr, "improvement": 0.0, "best_hypothesis": "無"}
        
        best_hyp = max(hypothesis_results.items(), 
                      key=lambda x: x[1]["results"].get("retrieval_metrics", {}).get("mrr", 0.0))
        
        best_mrr = best_hyp[1]["results"].get("retrieval_metrics", {}).get("mrr", 0.0)
        improvement = ((best_mrr - baseline_mrr) / max(baseline_mrr, 0.001)) * 100
        
        return {
            "best_mrr": best_mrr,
            "improvement": improvement,
            "best_hypothesis": best_hyp[1]["description"],
            "best_weights": best_hyp[1]["weights"],
            "best_k": best_hyp[1]["k_constant"]
        }

    def _analyze_joint_stage(self, all_results: Dict, baseline_mrr: float) -> Dict[str, Any]:
        """分析聯合搜索階段的結果"""
        joint_results = {k: v for k, v in all_results.items() if k.startswith('joint_')}
        
        if not joint_results:
            return {"best_mrr": baseline_mrr, "improvement": 0.0, "configurations_tested": 0}
        
        best_joint = max(joint_results.items(), 
                        key=lambda x: x[1]["results"].get("retrieval_metrics", {}).get("mrr", 0.0))
        
        best_mrr = best_joint[1]["results"].get("retrieval_metrics", {}).get("mrr", 0.0)
        improvement = ((best_mrr - baseline_mrr) / max(baseline_mrr, 0.001)) * 100
        
        return {
            "best_mrr": best_mrr,
            "improvement": improvement,
            "configurations_tested": len(joint_results),
            "best_weights": best_joint[1]["weights"],
            "best_k": best_joint[1]["k_constant"]
        }

    async def run_joint_optimization_flow(self, dataset_path: str, eval_params: Dict):
        """執行 RRF 權重+K值 聯合調優流程"""
        logger.info("🚀 開始 RRF 權重+K值 聯合調優流程 - 四步走策略")
        
        if not os.path.isabs(dataset_path):
            dataset_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), dataset_path)
        logger.info(f"使用資料集: {dataset_path}")

        try:
            with open(dataset_path, 'r', encoding='utf-8') as f:
                test_cases = json.load(f)
            logger.info(f"成功載入 {len(test_cases)} 個測試案例")
        except Exception as e:
            logger.error(f"載入測試數據失敗: {e}")
            return
        
        try:
            await self.initialize_services()
            
            # 執行聯合調優
            optimization_results = await self.optimize_rrf_weights_and_k(test_cases, eval_params)
            
            # 輸出調優結果
            self.print_joint_optimization_results(optimization_results)
            
            # 保存詳細結果
            output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rrf_joint_optimization_results.json")
            self.save_results_to_json(optimization_results, output_path)
            
        finally:
            if self.session and not self.session.closed:
                await self.session.close()
                logger.info("HTTP會話已關閉")

    def print_joint_optimization_results(self, results: Dict[str, Any]):
        """輸出聯合優化結果（權重+K值）"""
        print("\n" + "🔥" + "="*90)
        print("🚀 RRF 權重+K值 聯合調優結果 - 四步走策略")
        print("🔥" + "="*90)
        
        baseline_mrr = results.get("baseline_mrr", 0.0)
        best_mrr = results.get("best_mrr", 0.0)
        improvement = results.get("improvement_percentage", 0.0)
        best_config = results.get("best_configuration", {})
        best_k_sensitivity = results.get("best_k_from_sensitivity", 60)
        k_analysis = results.get("k_sensitivity_analysis", {})
        
        print(f"\n📊 整體聯合優化結果:")
        print(f"   🎯 基準線 MRR (1.0, 1.0, k=60): {baseline_mrr:.4f}")
        print(f"   🏆 最佳 MRR: {best_mrr:.4f}")
        print(f"   📈 總性能提升: {improvement:+.2f}%")
        
        if best_config:
            print(f"   🎯 最佳聯合配置:")
            print(f"      - 摘要權重: {best_config.get('summary', 1.0):.2f}")
            print(f"      - 內容塊權重: {best_config.get('chunks', 1.0):.2f}")
            print(f"      - K常數: {best_config.get('k', 60)}")
            print(f"      - 配置描述: {best_config.get('desc', '未知配置')}")
        
        # 顯示各階段結果
        summary = results.get("joint_optimization_summary", {})
        stages = summary.get("optimization_stages", {})
        
        print(f"\n📈 四步聯合調優詳細結果:")
        
        # 步驟一：基準線
        stage1 = stages.get("stage1_baseline", {})
        print(f"   📊 步驟一 - 公平起點:")
        print(f"      MRR: {stage1.get('mrr', 0.0):.4f} | {stage1.get('description', '未知')}")
        
        # 步驟二：K值敏感性分析
        stage2 = stages.get("stage2_k_sensitivity", {})
        if stage2.get("tested_k_values", 0) > 0:
            print(f"   🔬 步驟二 - K值敏感性分析:")
            print(f"      測試K值數量: {stage2.get('tested_k_values', 0)}")
            print(f"      最佳K值: {stage2.get('best_k', 60)}")
            print(f"      最佳K值MRR: {stage2.get('best_mrr', 0.0):.4f} (改進 {stage2.get('improvement', 0.0):+.1f}%)")
            print(f"      K值敏感性: {stage2.get('sensitivity_level', '未知')}")
            print(f"      敏感性範圍: {stage2.get('sensitivity_range', 0.0):.1f}%")
        
        # 步驟三：假設驅動（基於最佳K值）
        stage3 = stages.get("stage3_hypothesis", {})
        if stage3.get("best_mrr", 0.0) > 0:
            print(f"   🧠 步驟三 - 假設驅動微調 (使用最佳K值):")
            print(f"      最佳 MRR: {stage3.get('best_mrr', 0.0):.4f} (改進 {stage3.get('improvement', 0.0):+.1f}%)")
            print(f"      最佳假設: {stage3.get('best_hypothesis', '未知')}")
            best_hyp_weights = stage3.get("best_weights", {})
            print(f"      最佳權重: 摘要 {best_hyp_weights.get('summary', 1.0):.2f}, 內容塊 {best_hyp_weights.get('chunks', 1.0):.2f}")
            print(f"      使用K值: {stage3.get('best_k', 60)}")
        
        # 步驟四：聯合網格搜索
        stage4 = stages.get("stage4_joint_search", {})
        if stage4.get("configurations_tested", 0) > 0:
            print(f"   🔬 步驟四 - 聯合網格搜索:")
            print(f"      測試配置數: {stage4.get('configurations_tested', 0)}")
            print(f"      最佳 MRR: {stage4.get('best_mrr', 0.0):.4f} (改進 {stage4.get('improvement', 0.0):+.1f}%)")
            best_joint_weights = stage4.get("best_weights", {})
            print(f"      最佳權重: 摘要 {best_joint_weights.get('summary', 1.0):.2f}, 內容塊 {best_joint_weights.get('chunks', 1.0):.2f}")
            print(f"      最佳K值: {stage4.get('best_k', 60)}")
        
        # K值分析詳情
        if k_analysis:
            print(f"\n🔍 K值敏感性詳細分析:")
            for k_val, k_data in sorted(k_analysis.items()):
                mrr_val = k_data.get("mrr", 0.0)
                improvement_val = k_data.get("improvement", 0.0)
                marker = "🏆" if k_val == best_k_sensitivity else "   "
                print(f"      {marker} k={k_val}: MRR={mrr_val:.4f} (改進 {improvement_val:+.1f}%)")
        
        # 智能建議
        recommendation = summary.get("recommendation", "無建議")
        print(f"\n💡 智能建議:")
        print(f"   {recommendation}")
        
        # 實用配置輸出
        if best_config:
            print(f"\n🔧 生產環境聯合配置建議:")
            print(f"   # 在 backend/app/core/config.py 中設置：")
            print(f"   RRF_WEIGHTS = {{'summary': {best_config.get('summary', 1.0):.2f}, 'chunks': {best_config.get('chunks', 1.0):.2f}}}")
            print(f"   RRF_K_CONSTANT = {best_config.get('k', 60)}  # 經過聯合優化的K值")
        
        print("🔥" + "="*90 + "\n")

    async def optimize_rrf_weights(self, test_cases: List[Dict], eval_params: Dict) -> Dict[str, Any]:
        """
        🎯 RRF 權重調優：三步走策略（保持向後兼容）
        
        步驟一：公平的起點 (1.0, 1.0)
        步驟二：基於假設的微調
        步驟三：數據驅動的網格搜索
        """
        logger.info("🚀 開始 RRF 權重調優 - 三步走策略（經典版本）")
        
        # 定義權重網格 - 三步策略
        weight_optimization_results = {}
        default_k = 60  # 固定K值
        
        # === 步驟一：公平的起點 ===
        logger.info("\n" + "="*70)
        logger.info("📊 步驟一：公平的起點")
        logger.info("="*70)
        
        baseline_weights = {"summary": 1.0, "chunks": 1.0}
        baseline_result = await self._evaluate_rrf_with_weights(
            test_cases, eval_params, baseline_weights, default_k, "公平起點 (1.0,1.0)"
        )
        weight_optimization_results["baseline"] = {
            "weights": baseline_weights,
            "results": baseline_result,
            "description": "公平的起點"
        }
        
        baseline_mrr = baseline_result.get("retrieval_metrics", {}).get("mrr", 0.0)
        logger.info(f"✅ 基準線 MRR (1.0,1.0): {baseline_mrr:.4f}")
        
        # === 步驟二：基於假設的微調 ===
        logger.info("\n" + "="*70)
        logger.info("🧠 步驟二：基於假設的微調")
        logger.info("="*70)
        
        hypothesis_configs = [
            {"summary": 1.2, "chunks": 1.0, "desc": "輕微偏重摘要"},
            {"summary": 1.5, "chunks": 1.0, "desc": "明顯偏重摘要"},
            {"summary": 2.0, "chunks": 1.0, "desc": "強烈偏重摘要"},
            {"summary": 1.0, "chunks": 1.2, "desc": "輕微偏重內容塊"},
            {"summary": 1.0, "chunks": 1.5, "desc": "明顯偏重內容塊"},
            {"summary": 1.0, "chunks": 2.0, "desc": "強烈偏重內容塊"},
            {"summary": 0.8, "chunks": 1.0, "desc": "輕微懲罰摘要"},
            {"summary": 1.0, "chunks": 0.8, "desc": "輕微懲罰內容塊"},
        ]
        
        best_hypothesis_mrr = baseline_mrr
        
        for i, config in enumerate(hypothesis_configs):
            weights = {"summary": config["summary"], "chunks": config["chunks"]}
            logger.info(f"🧪 測試假設 {i+1}: {config['desc']} {weights}")
            
            result = await self._evaluate_rrf_with_weights(
                test_cases, eval_params, weights, default_k, config['desc']
            )
            
            weight_optimization_results[f"hypothesis_{i+1}"] = {
                "weights": weights,
                "results": result,
                "description": config['desc']
            }
            
            mrr_score = result.get("retrieval_metrics", {}).get("mrr", 0.0)
            improvement = ((mrr_score - baseline_mrr) / max(baseline_mrr, 0.001)) * 100
            
            logger.info(f"   MRR: {mrr_score:.4f} (改進 {improvement:+.1f}%)")
            
            if mrr_score > best_hypothesis_mrr:
                best_hypothesis_mrr = mrr_score
        
        # === 步驟三：網格搜索 ===
        logger.info("\n" + "="*70)
        logger.info("🔬 步驟三：網格搜索")
        logger.info("="*70)
        
        grid_configs = []
        for s_weight in [0.5, 0.8, 1.0, 1.2, 1.5, 2.0]:
            for c_weight in [0.5, 0.8, 1.0, 1.2, 1.5, 2.0]:
                if s_weight == 1.0 and c_weight == 1.0:  # 跳過基準線
                    continue
                grid_configs.append({
                    "summary": s_weight,
                    "chunks": c_weight,
                    "desc": f"網格搜索 S:{s_weight} C:{c_weight}"
                })
        
        # 限制搜索數量
        grid_configs = grid_configs[:15]
        best_grid_mrr = best_hypothesis_mrr
        best_config = None
        
        for i, config in enumerate(grid_configs):
            weights = {"summary": config["summary"], "chunks": config["chunks"]}
            logger.info(f"🔬 網格搜索 {i+1}/{len(grid_configs)}: {weights}")
            
            result = await self._evaluate_rrf_with_weights(
                test_cases, eval_params, weights, default_k, config['desc']
            )
            
            weight_optimization_results[f"grid_{i+1}"] = {
                "weights": weights,
                "results": result,
                "description": config['desc']
            }
            
            mrr_score = result.get("retrieval_metrics", {}).get("mrr", 0.0)
            improvement = ((mrr_score - baseline_mrr) / max(baseline_mrr, 0.001)) * 100
            
            logger.info(f"   MRR: {mrr_score:.4f} (改進 {improvement:+.1f}%)")
            
            if mrr_score > best_grid_mrr:
                best_grid_mrr = mrr_score
                best_config = config
        
        return {
            "optimization_type": "rrf_weight_optimization",
            "baseline_mrr": baseline_mrr,
            "best_mrr": best_grid_mrr,
            "improvement_percentage": ((best_grid_mrr - baseline_mrr) / max(baseline_mrr, 0.001)) * 100,
            "best_configuration": best_config,
            "all_results": weight_optimization_results,
            "evaluation_parameters": eval_params
        }

    async def run_weight_optimization_flow(self, dataset_path: str, eval_params: Dict):
        """執行 RRF 權重調優流程"""
        logger.info("🚀 開始 RRF 權重調優流程")
        
        if not os.path.isabs(dataset_path):
            dataset_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), dataset_path)
        logger.info(f"使用資料集: {dataset_path}")

        try:
            with open(dataset_path, 'r', encoding='utf-8') as f:
                test_cases = json.load(f)
            logger.info(f"成功載入 {len(test_cases)} 個測試案例")
        except Exception as e:
            logger.error(f"載入測試數據失敗: {e}")
            return
        
        try:
            await self.initialize_services()
            
            # 執行權重調優
            optimization_results = await self.optimize_rrf_weights(test_cases, eval_params)
            
            # 輸出調優結果
            self.print_weight_optimization_results(optimization_results)
            
            # 保存詳細結果
            output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rrf_weight_optimization_results.json")
            self.save_results_to_json(optimization_results, output_path)
            
        finally:
            if self.session and not self.session.closed:
                await self.session.close()
                logger.info("HTTP會話已關閉")

    def print_weight_optimization_results(self, results: Dict[str, Any]):
        """輸出權重調優結果"""
        print("\n" + "🔥" + "="*80)
        print("🚀 RRF 權重調優結果")
        print("🔥" + "="*80)
        
        baseline_mrr = results.get("baseline_mrr", 0.0)
        best_mrr = results.get("best_mrr", 0.0)
        improvement = results.get("improvement_percentage", 0.0)
        best_config = results.get("best_configuration", {})
        
        print(f"\n📊 權重調優結果:")
        print(f"   🎯 基準線 MRR (1.0, 1.0): {baseline_mrr:.4f}")
        print(f"   🏆 最佳 MRR: {best_mrr:.4f}")
        print(f"   📈 性能提升: {improvement:+.2f}%")
        
        if best_config:
            print(f"   🎯 最佳權重配置:")
            print(f"      - 摘要權重: {best_config.get('summary', 1.0):.2f}")
            print(f"      - 內容塊權重: {best_config.get('chunks', 1.0):.2f}")
            print(f"      - 配置描述: {best_config.get('desc', '未知配置')}")
        
        # 建議
        if improvement > 10:
            recommendation = "🚀 強烈建議採用調優後的權重配置！"
        elif improvement > 5:
            recommendation = "✅ 建議採用調優後的權重配置"
        elif improvement > 0:
            recommendation = "💡 調優有輕微改進，可根據實際情況選擇"
        else:
            recommendation = "⚠️ 預設權重 (1.0, 1.0) 已經是較佳選擇"
        
        print(f"\n💡 建議: {recommendation}")
        print("🔥" + "="*80 + "\n")

async def main():
    """主函數，解析參數並啟動評估"""
    parser = argparse.ArgumentParser(description='RRF融合檢索 vs 兩階段混合檢索 vs 傳統向量檢索 - 全面性能對比評估')
    parser.add_argument('--dataset', type=str, required=True, help='測試資料集檔案路徑 (必須)')
    parser.add_argument('--top-k', type=int, default=10, help='檢索結果數量 (預設: 10)')
    parser.add_argument('--threshold', type=float, default=0.3, help='相似度閾值 (預設: 0.3)')
    parser.add_argument(
        '--mode', 
        default='compare', 
        choices=['compare', 'individual', 'optimize_weights', 'optimize_weights_k'],
        help='執行模式：compare（對比）, individual（單一評估）, optimize_weights（權重調優）, optimize_weights_k（權重+K值聯合調優）'
    )
    
    # 新增：詳細評估選項
    parser.add_argument('--verbose', action='store_true', help='顯示每個測試案例的詳細結果')
    parser.add_argument('--save-detailed', action='store_true', help='保存詳細的個別案例分析結果')
    
    args = parser.parse_args()
    
    eval_params = {
        "top_k": args.top_k,
        "similarity_threshold": args.threshold,
        "verbose_mode": args.verbose,
        "save_detailed_analysis": args.save_detailed
    }
    
    for var in ['USERNAME', 'PASSWORD', 'API_URL']:
        if not os.getenv(var):
            logger.error(f"缺少必要的環境變數: {var}，請在 .env 文件中設置。")
            return
            
    evaluator = VectorRetrievalEvaluator()
    try:
        if args.mode == 'optimize_weights':
            # 權重調優模式
            await evaluator.run_weight_optimization_flow(
                dataset_path=args.dataset,
                eval_params=eval_params
            )
        elif args.mode == 'optimize_weights_k':
            # 權重+K值聯合調優模式
            await evaluator.run_joint_optimization_flow(
                dataset_path=args.dataset,
                eval_params=eval_params
            )
        elif args.mode == 'compare':
            # 多模式對比
            await evaluator.run_evaluation_flow(
                dataset_path=args.dataset,
                eval_params=eval_params,
                comparison_mode=True
            )
        elif args.mode == 'individual':
            # 單一策略評估 (傳統向量檢索)
            await evaluator.run_evaluation_flow(
                dataset_path=args.dataset,
                eval_params=eval_params,
                comparison_mode=False
            )
    except Exception as e:
        logger.error(f"評估腳本執行時發生未預期錯誤: {e}", exc_info=True)

if __name__ == "__main__":
    # <<< MODIFIED: 移除了 nest_asyncio，因在標準腳本中 asyncio.run() 是更好的選擇
    try:
        asyncio.run(main())
        logger.info("程式執行完成，正常退出。")
    except SystemExit as e:
        if e.code != 0:
             logger.error("因參數錯誤導致程式退出。")
    except Exception as e:
        logger.error(f"程式在頂層執行時崩潰: {e}", exc_info=True)