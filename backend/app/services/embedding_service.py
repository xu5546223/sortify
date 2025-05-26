from typing import List, Optional, Dict, Any
import torch
import numpy as np
from sentence_transformers import SentenceTransformer
import logging
import os
from pathlib import Path
from app.core.logging_utils import AppLogger
from app.core.config import settings

logger = AppLogger(__name__, level=logging.DEBUG).get_logger()

class EmbeddingService:
    """文本向量化服務"""
    
    def __init__(self, model_name: str = None):
        self.model_name = model_name or getattr(settings, 'EMBEDDING_MODEL', 'paraphrase-multilingual-mpnet-base-v2')
        self.model = None
        self.vector_dimension = None
        self._model_loaded = False
        
        # 檢查模型是否已緩存
        self._check_model_cache()
    
    def _check_model_cache(self):
        """檢查模型是否已經緩存到本地"""
        try:
            # Hugging Face 模型緩存路徑
            cache_dir = os.path.expanduser("~/.cache/huggingface/hub")
            model_cache_path = Path(cache_dir) / f"models--sentence-transformers--{self.model_name.replace('/', '--')}"
            
            if model_cache_path.exists():
                logger.info(f"檢測到模型緩存: {self.model_name}")
                logger.info(f"緩存路徑: {model_cache_path}")
            else:
                logger.info(f"模型 {self.model_name} 尚未緩存，首次加載將下載模型文件")
                
        except Exception as e:
            logger.warning(f"檢查模型緩存失敗: {e}")
    
    def _load_model(self):
        """加載Sentence Transformers模型（懶加載）"""
        if self._model_loaded:
            logger.debug("模型已經加載，跳過重新加載")
            return
            
        try:
            logger.info(f"正在加載Embedding模型: {self.model_name}")
            start_time = torch.cuda.Event(enable_timing=True) if torch.cuda.is_available() else None
            end_time = torch.cuda.Event(enable_timing=True) if torch.cuda.is_available() else None
            
            if start_time:
                start_time.record()
            
            # 設置模型緩存目錄（可選）
            cache_folder = os.path.expanduser("~/.cache/huggingface/hub")
            
            self.model = SentenceTransformer(
                self.model_name,
                cache_folder=cache_folder,
                device="cuda" if torch.cuda.is_available() else "cpu"
            )
            
            # 獲取向量維度
            test_embedding = self.model.encode("test", convert_to_tensor=False)
            self.vector_dimension = len(test_embedding)
            
            if end_time:
                end_time.record()
                torch.cuda.synchronize()
                loading_time = start_time.elapsed_time(end_time) / 1000.0  # 轉換為秒
                logger.info(f"Embedding模型加載成功，耗時: {loading_time:.2f}秒，向量維度: {self.vector_dimension}")
            else:
                logger.info(f"Embedding模型加載成功，向量維度: {self.vector_dimension}")
            
            # 檢查GPU可用性
            if torch.cuda.is_available():
                gpu_name = torch.cuda.get_device_name()
                logger.info(f"已啟用GPU加速: {gpu_name}")
            else:
                logger.info("使用CPU進行Embedding")
            
            self._model_loaded = True
                
        except Exception as e:
            logger.error(f"加載Embedding模型失敗: {e}")
            raise e
    
    def encode_text(self, text: str) -> List[float]:
        """
        將單個文本編碼為向量
        
        Args:
            text: 要編碼的文本
            
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
            
            # 生成向量
            embedding = self.model.encode(text, convert_to_tensor=False, normalize_embeddings=True)
            return embedding.tolist()
            
        except Exception as e:
            logger.error(f"文本編碼失敗: {e}")
            # 返回零向量作為fallback
            return [0.0] * self.vector_dimension
    
    def encode_batch(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """
        批量編碼文本為向量
        
        Args:
            texts: 文本列表
            batch_size: 批次大小
            
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
            processed_texts = []
            for text in texts:
                if not text or not text.strip():
                    processed_texts.append("")
                elif len(text) > max_length:
                    processed_texts.append(text[:max_length])
                else:
                    processed_texts.append(text)
            
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