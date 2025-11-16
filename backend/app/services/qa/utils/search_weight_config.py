"""
搜索權重配置模塊

提供查詢權重管理功能，用於多查詢搜索場景的結果加權和合併。
遷移自 enhanced_ai_qa_service.py
"""

from typing import List, Dict
from app.models.vector_models import SemanticSearchResult


class SearchWeightConfig:
    """搜索權重配置類 - 統一管理所有權重相關邏輯"""
    
    QUERY_TYPE_WEIGHTS = {
        0: 1.3,  # 類型A：自然語言摘要風格 - 最高權重
        1: 1.1,  # 類型B：關鍵詞密集查詢 - 中等權重  
        2: 1.0   # 類型C：領域專業查詢 - 標準權重
    }
    
    @classmethod
    def apply_query_weights(cls, results: List[SemanticSearchResult], query_index: int) -> List[SemanticSearchResult]:
        """應用查詢權重到搜索結果"""
        weight = cls.QUERY_TYPE_WEIGHTS.get(query_index, 1.0)
        for result in results:
            result.similarity_score *= weight
        return results
    
    @classmethod
    def get_query_weight(cls, query_index: int) -> float:
        """獲取特定查詢索引的權重"""
        return cls.QUERY_TYPE_WEIGHTS.get(query_index, 1.0)
    
    @classmethod
    def merge_weighted_results(cls, all_results_map: Dict[str, SemanticSearchResult], new_results: List[SemanticSearchResult], query_index: int) -> None:
        """合併加權結果到總結果集"""
        weight = cls.get_query_weight(query_index)
        
        for result in new_results:
            weighted_score = result.similarity_score * weight
            
            if result.document_id not in all_results_map:
                # 創建新結果
                all_results_map[result.document_id] = SemanticSearchResult(
                    document_id=result.document_id,
                    similarity_score=weighted_score,
                    summary_text=result.summary_text,
                    metadata=result.metadata
                )
            else:
                # 已存在的文檔，取最高分數
                if weighted_score > all_results_map[result.document_id].similarity_score:
                    all_results_map[result.document_id].similarity_score = weighted_score
                    all_results_map[result.document_id].summary_text = result.summary_text
