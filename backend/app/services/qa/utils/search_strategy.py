"""
搜索策略工具模塊

提供搜索策略決策和結果優化功能。
遷移自 enhanced_ai_qa_service.py
"""

from typing import List, Optional
from app.models.vector_models import QueryRewriteResult, SemanticSearchResult


def extract_search_strategy(query_rewrite_result: Optional[QueryRewriteResult]) -> str:
    """
    提取搜索策略 - 統一策略決策邏輯
    
    Args:
        query_rewrite_result: 查詢重寫結果
        
    Returns:
        str: 搜索策略名稱 ("hybrid", "summary_only", "rrf_fusion")
    """
    if not query_rewrite_result:
        return "hybrid"
    
    suggested = getattr(query_rewrite_result, 'search_strategy_suggestion', None)
    granularity = getattr(query_rewrite_result, 'query_granularity', None)
    
    # 策略映射邏輯
    strategy_map = {
        "summary_only": "summary_only",
        "rrf_fusion": "rrf_fusion", 
        "keyword_enhanced_rrf": "rrf_fusion"
    }
    
    # 根據粒度自動選擇
    if granularity == "thematic":
        return "summary_only"
    elif granularity in ["detailed", "unknown"]:
        return "rrf_fusion"
    
    return strategy_map.get(suggested, "hybrid")


def apply_diversity_optimization(results: List[SemanticSearchResult], top_k: int) -> List[SemanticSearchResult]:
    """
    應用多樣性優化算法
    
    通過分析搜索結果的摘要文本關鍵詞重疊度，確保返回的結果具有多樣性。
    
    Args:
        results: 搜索結果列表
        top_k: 期望返回的結果數量
        
    Returns:
        List[SemanticSearchResult]: 多樣性優化後的結果列表
    """
    diversified_results = []
    seen_summary_keywords = set()
    
    for result in results:
        # 提取摘要的關鍵詞進行去重判斷
        summary_words = set(result.summary_text.lower().split()[:10])
        overlap = len(summary_words.intersection(seen_summary_keywords))
        
        # 如果重疊度不高，或者還沒有足夠的結果，則加入
        if overlap < 5 or len(diversified_results) < max(3, top_k // 2):
            diversified_results.append(result)
            seen_summary_keywords.update(summary_words)
            
            if len(diversified_results) >= top_k:
                break
    
    return diversified_results
