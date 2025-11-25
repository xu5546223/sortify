"""
向量化策略評估腳本

專門評估 AI 邏輯分塊 vs 固定大小分塊 的召回準確度
不包含查詢重寫，純向量召回測試

評估指標：
- Hit Rate @K: 前 K 個結果中是否包含正確文檔
- MRR (Mean Reciprocal Rank): 正確文檔的平均倒數排名
- nDCG @K: 標準化折損累積增益

使用方式：
    python evaluate_chunking_strategy.py --dataset QA_dataset.json --top_k 5
"""

import json
import asyncio
import logging
import sys
import argparse
from typing import List, Dict, Any, Optional
from datetime import datetime
import numpy as np
import aiohttp
from dotenv import load_dotenv
import os

# --- .env 載入 ---
script_dir = os.path.dirname(os.path.abspath(__file__))
dotenv_path = os.path.join(script_dir, '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path=dotenv_path, override=True)
else:
    print(f"警告: 找不到 .env 文件: {dotenv_path}")

# --- 日誌設定 ---
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ChunkingStrategyEvaluator:
    """向量化策略評估器 - 純向量召回測試"""
    
    def __init__(self):
        self.api_base_url = os.getenv('API_URL', 'http://localhost:8000')
        self.api_username = os.getenv('USERNAME')
        self.api_password = os.getenv('PASSWORD')
        
        if not self.api_username or not self.api_password:
            raise ValueError("請在 .env 文件中設置 USERNAME 和 PASSWORD")
        
        self.session: Optional[aiohttp.ClientSession] = None
        self.access_token: Optional[str] = None
        
        logger.info(f"評估器初始化完成，API: {self.api_base_url}")
    
    async def initialize(self):
        """初始化 API 連接"""
        self.session = aiohttp.ClientSession()
        
        # 登入獲取 token
        login_url = f"{self.api_base_url}/api/v1/auth/token"
        login_data = {"username": self.api_username, "password": self.api_password}
        
        try:
            async with self.session.post(login_url, data=login_data) as response:
                response.raise_for_status()
                result = await response.json()
                self.access_token = result.get("access_token")
                
                if self.access_token:
                    logger.info("✅ 登入成功")
                else:
                    raise ValueError("登入響應中沒有 access_token")
        except Exception as e:
            logger.error(f"❌ 登入失敗: {e}")
            raise
    
    async def close(self):
        """關閉連接"""
        if self.session:
            await self.session.close()
    
    def _get_headers(self) -> Dict[str, str]:
        """獲取認證標頭"""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
    
    async def search_vectors(
        self, 
        query: str, 
        top_k: int = 5,
        similarity_threshold: float = 0.3
    ) -> List[Dict]:
        """執行向量搜索"""
        url = f"{self.api_base_url}/api/v1/vector-db/semantic-search"
        
        payload = {
            "query": query,
            "top_k": top_k,
            "similarity_threshold": similarity_threshold,
            "enable_hybrid_search": True,  # 使用兩階段混合搜索
            "enable_diversity_optimization": False  # 關閉多樣性優化，純召回測試
        }
        
        try:
            async with self.session.post(url, json=payload, headers=self._get_headers()) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    logger.error(f"搜索失敗 ({response.status}): {error_text[:200]}")
                    return []
        except Exception as e:
            logger.error(f"搜索異常: {e}")
            return []
    
    def calculate_hit_rate(self, expected_ids: List[str], retrieved_ids: List[str], k: int) -> float:
        """計算 Hit Rate @K"""
        expected_set = set(expected_ids)
        retrieved_set = set(retrieved_ids[:k])
        return 1.0 if expected_set.intersection(retrieved_set) else 0.0
    
    def calculate_mrr(self, expected_ids: List[str], retrieved_ids: List[str]) -> float:
        """計算 MRR (Mean Reciprocal Rank)"""
        expected_set = set(expected_ids)
        for rank, doc_id in enumerate(retrieved_ids, 1):
            if doc_id in expected_set:
                return 1.0 / rank
        return 0.0
    
    def calculate_ndcg(self, expected_ids: List[str], retrieved_ids: List[str], k: int) -> float:
        """計算 nDCG @K"""
        expected_set = set(expected_ids)
        
        # DCG
        relevance = [1 if doc_id in expected_set else 0 for doc_id in retrieved_ids[:k]]
        dcg = sum(rel / np.log2(i + 2) for i, rel in enumerate(relevance))
        
        # IDCG
        num_relevant = min(k, len(expected_ids))
        idcg = sum(1 / np.log2(i + 2) for i in range(num_relevant))
        
        return dcg / idcg if idcg > 0 else 0.0
    
    async def evaluate_dataset(
        self, 
        test_cases: List[Dict],
        top_k: int = 5,
        similarity_threshold: float = 0.3,
        verbose: bool = False
    ) -> Dict[str, Any]:
        """評估整個數據集"""
        
        logger.info(f"開始評估 {len(test_cases)} 個測試案例...")
        logger.info(f"參數: top_k={top_k}, similarity_threshold={similarity_threshold}")
        
        results = []
        hit_counts = {1: 0, 3: 0, 5: 0, 10: 0}
        mrr_sum = 0.0
        ndcg_sums = {1: 0.0, 3: 0.0, 5: 0.0, 10: 0.0}
        
        # 按問題類型分組統計
        stats_by_type = {}
        
        for i, case in enumerate(test_cases):
            question = case.get('question', '')
            expected_doc_ids = case.get('expected_relevant_doc_ids', [])
            question_type = case.get('question_type', 'unknown')
            
            if not question or not expected_doc_ids:
                continue
            
            # 執行搜索
            search_results = await self.search_vectors(question, top_k, similarity_threshold)
            retrieved_ids = [r.get('document_id', '') for r in search_results]
            
            # 計算指標
            mrr = self.calculate_mrr(expected_doc_ids, retrieved_ids)
            mrr_sum += mrr
            
            for k in [1, 3, 5, 10]:
                if self.calculate_hit_rate(expected_doc_ids, retrieved_ids, k) > 0:
                    hit_counts[k] += 1
                ndcg_sums[k] += self.calculate_ndcg(expected_doc_ids, retrieved_ids, k)
            
            # 按類型統計
            if question_type not in stats_by_type:
                stats_by_type[question_type] = {'count': 0, 'hits': 0, 'mrr_sum': 0.0}
            stats_by_type[question_type]['count'] += 1
            stats_by_type[question_type]['mrr_sum'] += mrr
            if self.calculate_hit_rate(expected_doc_ids, retrieved_ids, top_k) > 0:
                stats_by_type[question_type]['hits'] += 1
            
            # 記錄詳細結果
            case_result = {
                'question': question[:80] + '...' if len(question) > 80 else question,
                'question_type': question_type,
                'expected_doc_ids': expected_doc_ids,
                'retrieved_doc_ids': retrieved_ids[:5],
                'hit': bool(set(expected_doc_ids) & set(retrieved_ids[:top_k])),
                'mrr': mrr
            }
            results.append(case_result)
            
            # 進度顯示
            if verbose or (i + 1) % 10 == 0:
                hit_symbol = "✅" if case_result['hit'] else "❌"
                print(f"  [{i+1:3d}/{len(test_cases)}] {hit_symbol} MRR={mrr:.3f} | {question[:50]}...")
        
        # 計算平均指標
        n = len(results)
        if n == 0:
            return {"error": "沒有有效的測試案例"}
        
        evaluation_result = {
            "evaluation_type": "chunking_strategy_retrieval",
            "timestamp": datetime.now().isoformat(),
            "total_cases": len(test_cases),
            "processed_cases": n,
            "parameters": {
                "top_k": top_k,
                "similarity_threshold": similarity_threshold
            },
            "overall_metrics": {
                "hit_rate": {
                    "@1": hit_counts[1] / n,
                    "@3": hit_counts[3] / n,
                    "@5": hit_counts[5] / n,
                    "@10": hit_counts[10] / n
                },
                "mrr": mrr_sum / n,
                "ndcg": {
                    "@1": ndcg_sums[1] / n,
                    "@3": ndcg_sums[3] / n,
                    "@5": ndcg_sums[5] / n,
                    "@10": ndcg_sums[10] / n
                }
            },
            "metrics_by_question_type": {}
        }
        
        # 按問題類型的指標
        for qtype, stats in stats_by_type.items():
            if stats['count'] > 0:
                evaluation_result["metrics_by_question_type"][qtype] = {
                    "count": stats['count'],
                    "hit_rate": stats['hits'] / stats['count'],
                    "mrr": stats['mrr_sum'] / stats['count']
                }
        
        return evaluation_result
    
    def print_results(self, results: Dict[str, Any]):
        """格式化輸出評估結果"""
        print("\n" + "=" * 60)
        print("📊 向量化策略召回評估結果")
        print("=" * 60)
        
        metrics = results.get("overall_metrics", {})
        
        print(f"\n📈 整體指標 (共 {results.get('processed_cases', 0)} 個案例)")
        print("-" * 40)
        
        # Hit Rate
        hit_rate = metrics.get("hit_rate", {})
        print(f"  Hit Rate @1:  {hit_rate.get('@1', 0):.2%}")
        print(f"  Hit Rate @3:  {hit_rate.get('@3', 0):.2%}")
        print(f"  Hit Rate @5:  {hit_rate.get('@5', 0):.2%}")
        print(f"  Hit Rate @10: {hit_rate.get('@10', 0):.2%}")
        
        # MRR
        print(f"\n  MRR: {metrics.get('mrr', 0):.4f}")
        
        # nDCG
        ndcg = metrics.get("ndcg", {})
        print(f"\n  nDCG @1:  {ndcg.get('@1', 0):.4f}")
        print(f"  nDCG @3:  {ndcg.get('@3', 0):.4f}")
        print(f"  nDCG @5:  {ndcg.get('@5', 0):.4f}")
        print(f"  nDCG @10: {ndcg.get('@10', 0):.4f}")
        
        # 按問題類型
        by_type = results.get("metrics_by_question_type", {})
        if by_type:
            print(f"\n📋 按問題類型分析")
            print("-" * 40)
            for qtype, stats in by_type.items():
                print(f"  {qtype}:")
                print(f"    數量: {stats['count']}")
                print(f"    Hit Rate: {stats['hit_rate']:.2%}")
                print(f"    MRR: {stats['mrr']:.4f}")
        
        print("\n" + "=" * 60)


async def main():
    parser = argparse.ArgumentParser(description='向量化策略召回評估')
    parser.add_argument('--dataset', type=str, default='QA_dataset.json', help='測試數據集路徑')
    parser.add_argument('--top_k', type=int, default=5, help='檢索結果數量')
    parser.add_argument('--threshold', type=float, default=0.3, help='相似度閾值')
    parser.add_argument('--verbose', action='store_true', help='顯示詳細進度')
    parser.add_argument('--output', type=str, default=None, help='結果輸出文件')
    parser.add_argument('--limit', type=int, default=None, help='限制測試案例數量')
    
    args = parser.parse_args()
    
    # 載入數據集
    dataset_path = os.path.join(script_dir, args.dataset)
    if not os.path.exists(dataset_path):
        print(f"❌ 找不到數據集: {dataset_path}")
        sys.exit(1)
    
    with open(dataset_path, 'r', encoding='utf-8') as f:
        test_cases = json.load(f)
    
    if args.limit:
        test_cases = test_cases[:args.limit]
    
    print(f"📂 載入數據集: {args.dataset}")
    print(f"📝 測試案例數: {len(test_cases)}")
    
    # 執行評估
    evaluator = ChunkingStrategyEvaluator()
    
    try:
        await evaluator.initialize()
        
        results = await evaluator.evaluate_dataset(
            test_cases,
            top_k=args.top_k,
            similarity_threshold=args.threshold,
            verbose=args.verbose
        )
        
        # 輸出結果
        evaluator.print_results(results)
        
        # 保存結果
        if args.output:
            output_path = os.path.join(script_dir, args.output)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f"\n💾 結果已保存到: {output_path}")
        
    finally:
        await evaluator.close()


if __name__ == "__main__":
    asyncio.run(main())
