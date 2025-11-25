from typing import List, Optional, Dict, Any
import torch
import numpy as np
from sentence_transformers import SentenceTransformer
import logging
import os
from pathlib import Path
from app.core.logging_utils import AppLogger, log_event, LogLevel # Added log_event, LogLevel
from app.core.config import settings

logger = AppLogger(__name__, level=logging.DEBUG).get_logger() # Existing AppLogger can remain for very fine-grained internal logs

class EmbeddingService:
    """文本向量化服務"""
    
    # 需要前綴的模型列表
    MODELS_REQUIRING_PREFIX = [
        'intfloat/multilingual-e5',
        'intfloat/e5-',
        'BAAI/bge-',
    ]
    
    def __init__(self, model_name: str = None):
        self.model_name = model_name or getattr(settings, 'EMBEDDING_MODEL', 'intfloat/multilingual-e5-base')
        self.model = None
        self.vector_dimension = None
        self._model_loaded = False
        
        # 檢查是否需要前綴
        self._requires_prefix = any(prefix in self.model_name for prefix in self.MODELS_REQUIRING_PREFIX)
        
        # 檢查模型是否已緩存
        self._check_model_cache()
    
    def _check_model_cache(self):
        """檢查模型是否已經緩存到本地"""
        try:
            # Hugging Face 模型緩存路徑
            cache_dir = os.path.expanduser("~/.cache/huggingface/hub")
            model_cache_path = Path(cache_dir) / f"models--sentence-transformers--{self.model_name.replace('/', '--')}"
            
            if model_cache_path.exists():
                logger.debug(f"Embedding model cache detected for {self.model_name}.",
                           extra={"model_name": self.model_name, "cache_path": str(model_cache_path)})
            else:
                logger.info(f"Embedding model {self.model_name} not cached. Will download on first load.",
                          extra={"model_name": self.model_name})
                
        except Exception as e:
            logger.warning(f"Failed to check model cache for {self.model_name}: {str(e)}",
                         extra={"model_name": self.model_name, "error": str(e)})
    
    def _load_model(self):
        """加載Sentence Transformers模型（懶加載）"""
        if self._model_loaded:
            logger.debug("Embedding model already loaded, skipping reload.",
                        extra={"model_name": self.model_name})
            return
            
        logger.info(f"Attempting to load embedding model: {self.model_name}.",
                   extra={"model_name": self.model_name})
        try:
            start_time_event = torch.cuda.Event(enable_timing=True) if torch.cuda.is_available() else None
            end_time_event = torch.cuda.Event(enable_timing=True) if torch.cuda.is_available() else None # Renamed variables
            
            if start_time_event:
                start_time_event.record()
            
            cache_folder = os.path.expanduser("~/.cache/huggingface/hub")
            
            device_selected = "cuda" if torch.cuda.is_available() else "cpu"
            self.model = SentenceTransformer(
                self.model_name,
                cache_folder=cache_folder,
                device=device_selected
            )
            
            test_embedding = self.model.encode("test", convert_to_tensor=False) # type: ignore
            self.vector_dimension = len(test_embedding)
            
            loading_time_sec = None
            if end_time_event and start_time_event: # Check both are not None
                end_time_event.record()
                torch.cuda.synchronize()
                loading_time_sec = start_time_event.elapsed_time(end_time_event) / 1000.0
            
            self._model_loaded = True

            log_details = {
                "model_name": self.model_name,
                "vector_dimension": self.vector_dimension,
                "device_used": device_selected,
                "gpu_available": torch.cuda.is_available()
            }
            if loading_time_sec is not None:
                log_details["loading_time_seconds"] = round(loading_time_sec, 2)
            if torch.cuda.is_available() and device_selected == "cuda":
                log_details["gpu_name"] = torch.cuda.get_device_name()

            logger.info("Embedding model loaded successfully.",
                        extra={"model_name": self.model_name, "details": log_details})
                
        except Exception as e:
            logger.error(f"Failed to load embedding model: {self.model_name}. Error: {str(e)}",
                         extra={"model_name": self.model_name, "error": str(e), "error_type": type(e).__name__})
            raise # Re-raise the exception so the service knows loading failed
    
    def encode_text(self, text: str, is_query: bool = True) -> List[float]:
        """
        將單個文本編碼為向量
        
        Args:
            text: 要編碼的文本
            is_query: 是否為查詢文本（對於 e5/bge 模型需要不同前綴）
            
        Returns:
            向量列表
        """
        # 懶加載模型
        if not self._model_loaded:
            self._load_model()
            
        try:
            if not text or not text.strip():
                logger.warning("嘗試編碼空文本，返回零向量")
                return [0.0] * self.vector_dimension
            
            # 預處理文本（截斷過長的文本）
            max_length = getattr(settings, 'EMBEDDING_MAX_LENGTH', 512)
            if len(text) > max_length:
                text = text[:max_length]
                logger.debug(f"文本過長，已截斷到{max_length}字符")
            
            # 為 e5/bge 模型添加前綴
            if self._requires_prefix:
                prefix = "query: " if is_query else "passage: "
                text = prefix + text
            
            # 生成向量
            embedding = self.model.encode(text, convert_to_tensor=False, normalize_embeddings=True)
            return embedding.tolist()
            
        except Exception as e:
            logger.error(f"文本編碼失敗: {e}")
            # 返回零向量作為fallback
            return [0.0] * self.vector_dimension
    
    def encode_batch(self, texts: List[str], batch_size: int = 32, is_query: bool = False) -> List[List[float]]:
        """
        批量編碼文本為向量
        
        Args:
            texts: 文本列表
            batch_size: 批次大小
            is_query: 是否為查詢文本（對於 e5/bge 模型需要不同前綴）
            
        Returns:
            向量列表的列表
        """
        # 懶加載模型
        if not self._model_loaded:
            self._load_model()
            
        try:
            if not texts:
                return []
            
            logger.info(f"開始批量編碼 {len(texts)} 個文本，批次大小: {batch_size}")
            
            # 預處理文本
            max_length = getattr(settings, 'EMBEDDING_MAX_LENGTH', 512)
            prefix = ""
            if self._requires_prefix:
                prefix = "query: " if is_query else "passage: "
            
            processed_texts = []
            for text in texts:
                if not text or not text.strip():
                    processed_texts.append("")
                elif len(text) > max_length:
                    processed_texts.append(prefix + text[:max_length])
                else:
                    processed_texts.append(prefix + text)
            
            # 批量生成向量
            embeddings = self.model.encode(
                processed_texts, 
                batch_size=batch_size,
                convert_to_tensor=False,
                normalize_embeddings=True,
                show_progress_bar=len(texts) > 10  # 只有較大批次才顯示進度條
            )
            
            logger.info(f"批量編碼完成，共生成 {len(embeddings)} 個向量")
            return [embedding.tolist() for embedding in embeddings]
            
        except Exception as e:
            logger.error(f"批量文本編碼失敗: {e}")
            # 返回零向量作為fallback
            return [[0.0] * self.vector_dimension] * len(texts)
    
    def calculate_similarity(self, vector1: List[float], vector2: List[float]) -> float:
        """
        計算兩個向量的餘弦相似度
        
        Args:
            vector1: 第一個向量
            vector2: 第二個向量
            
        Returns:
            相似度分數 (0-1)
        """
        try:
            # 轉換為numpy數組
            v1 = np.array(vector1)
            v2 = np.array(vector2)
            
            # 計算餘弦相似度
            dot_product = np.dot(v1, v2)
            norms = np.linalg.norm(v1) * np.linalg.norm(v2)
            
            if norms == 0:
                return 0.0
                
            similarity = dot_product / norms
            return float(similarity)
            
        except Exception as e:
            logger.error(f"計算向量相似度失敗: {e}")
            return 0.0
    
    def get_model_info(self) -> Dict[str, Any]:
        """獲取模型信息"""
        return {
            "model_name": self.model_name,
            "vector_dimension": self.vector_dimension,
            "device": "cuda" if torch.cuda.is_available() and self._model_loaded and next(self.model.parameters()).is_cuda else "cpu",
            "model_loaded": self._model_loaded,
            "cache_available": self._check_model_cache_exists()
        }
    
    def _check_model_cache_exists(self) -> bool:
        """檢查模型緩存是否存在"""
        try:
            cache_dir = os.path.expanduser("~/.cache/huggingface/hub")
            model_cache_path = Path(cache_dir) / f"models--sentence-transformers--{self.model_name.replace('/', '--')}"
            return model_cache_path.exists()
        except:
            return False

# 全局Embedding服務實例
embedding_service = EmbeddingService() 