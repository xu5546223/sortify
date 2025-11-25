"""
Cross-Encoder Reranker 服務

使用 Cross-Encoder 模型對召回結果進行重排序，提升排名精度。
Cross-Encoder 會同時編碼 Query 和 Document，計算更精確的相關性分數。
"""

from typing import List, Optional, Tuple
import logging
import os
from pathlib import Path

from app.core.logging_utils import AppLogger
from app.core.config import settings
from app.models.vector_models import SemanticSearchResult

logger = AppLogger(__name__, level=logging.DEBUG).get_logger()


class RerankerService:
    """Cross-Encoder 重排序服務"""
    
    def __init__(self, model_name: str = None):
        self.model_name = model_name or getattr(
            settings, 'RERANKER_MODEL', 'BAAI/bge-reranker-v2-m3'
        )
        self.model = None
        self._model_loaded = False
        self.enabled = getattr(settings, 'RERANKER_ENABLED', True)
        self.top_k = getattr(settings, 'RERANKER_TOP_K', 20)  # 對 top-k 結果重排序
        
        # 檢查模型緩存
        self._check_model_cache()
    
    def _check_model_cache(self):
        """檢查模型是否已緩存"""
        try:
            cache_dir = os.path.expanduser("~/.cache/huggingface/hub")
            model_cache_path = Path(cache_dir) / f"models--{self.model_name.replace('/', '--')}"
            
            if model_cache_path.exists():
                logger.debug(f"Reranker model cache detected: {self.model_name}")
            else:
                logger.info(f"Reranker model {self.model_name} not cached. Will download on first load.")
        except Exception as e:
            logger.warning(f"Failed to check reranker model cache: {e}")
    
    def _load_model(self):
        """懶加載 Cross-Encoder 模型"""
        if self._model_loaded:
            return
        
        if not self.enabled:
            logger.info("Reranker is disabled, skipping model load.")
            return
        
        logger.info(f"Loading reranker model: {self.model_name}")
        
        try:
            from sentence_transformers import CrossEncoder
            import torch
            
            device = "cuda" if torch.cuda.is_available() else "cpu"
            
            self.model = CrossEncoder(
                self.model_name,
                max_length=512,
                device=device
            )
            
            self._model_loaded = True
            logger.info(f"Reranker model loaded successfully on {device}")
            
        except Exception as e:
            logger.error(f"Failed to load reranker model: {e}")
            self.enabled = False
            raise
    
    def rerank(
        self,
        query: str,
        results: List[SemanticSearchResult],
        top_k: Optional[int] = None
    ) -> List[SemanticSearchResult]:
        """
        使用 Cross-Encoder 對搜索結果重排序
        
        Args:
            query: 查詢文本
            results: 原始搜索結果
            top_k: 返回的結果數量（默認使用配置值）
            
        Returns:
            重排序後的結果列表
        """
        if not self.enabled:
            logger.debug("Reranker disabled, returning original results")
            return results
        
        if not results:
            return results
        
        # 懶加載模型
        if not self._model_loaded:
            self._load_model()
        
        if not self.model:
            logger.warning("Reranker model not available, returning original results")
            return results
        
        top_k = top_k or self.top_k
        
        # 只對前 N 個結果重排序（節省計算資源）
        results_to_rerank = results[:min(len(results), self.top_k)]
        
        try:
            # 準備 query-document pairs
            pairs = []
            for result in results_to_rerank:
                # 使用 summary_text 或 chunk_text
                doc_text = result.summary_text or ""
                if not doc_text and result.metadata:
                    doc_text = result.metadata.get("chunk_text", "")
                
                if doc_text:
                    pairs.append([query, doc_text])
                else:
                    pairs.append([query, ""])
            
            if not pairs:
                return results
            
            # 計算 Cross-Encoder 分數
            scores = self.model.predict(pairs, show_progress_bar=False)
            
            # 將分數附加到結果
            scored_results = []
            for i, result in enumerate(results_to_rerank):
                # 創建新的結果對象，更新分數
                reranked_result = SemanticSearchResult(
                    document_id=result.document_id,
                    similarity_score=float(scores[i]),  # 使用 Cross-Encoder 分數
                    summary_text=result.summary_text,
                    metadata={
                        **(result.metadata or {}),
                        "original_score": result.similarity_score,
                        "reranker_score": float(scores[i]),
                        "reranked": True
                    },
                    start_line=result.start_line,
                    end_line=result.end_line,
                    chunk_type=result.chunk_type
                )
                scored_results.append((float(scores[i]), reranked_result))
            
            # 按 Cross-Encoder 分數排序
            scored_results.sort(key=lambda x: x[0], reverse=True)
            
            # 提取排序後的結果
            reranked_results = [r for _, r in scored_results[:top_k]]
            
            logger.info(f"Reranked {len(results_to_rerank)} results -> top {len(reranked_results)}")
            
            return reranked_results
            
        except Exception as e:
            logger.error(f"Reranking failed: {e}", exc_info=True)
            return results[:top_k] if top_k else results
    
    def get_model_info(self) -> dict:
        """獲取模型信息"""
        return {
            "model_name": self.model_name,
            "enabled": self.enabled,
            "model_loaded": self._model_loaded,
            "top_k": self.top_k
        }


# 創建全局實例
reranker_service = RerankerService()
