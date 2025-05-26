from typing import List, Optional, Dict, Any, Tuple, Union
import logging
from pathlib import Path
import chromadb
from chromadb.config import Settings
import uuid
from datetime import datetime
from app.core.logging_utils import AppLogger
from app.core.config import settings
from app.models.vector_models import VectorRecord, SemanticSearchResult

logger = AppLogger(__name__, level=logging.DEBUG).get_logger()

class VectorDatabaseService:
    """ChromaDB向量資料庫服務"""
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or getattr(settings, 'VECTOR_DB_PATH', './data/chromadb')
        self.collection_name = "document_vectors"
        self.client = None
        self.collection = None
        self.vector_dimension = None
        self._ensure_db_directory()
        self._initialize_connection()
    
    def _ensure_db_directory(self):
        """確保資料庫目錄存在"""
        db_dir = Path(self.db_path)
        db_dir.mkdir(parents=True, exist_ok=True)
    
    def _initialize_connection(self):
        """初始化ChromaDB連接"""
        try:
            logger.info(f"正在初始化ChromaDB連接: {self.db_path}")
            
            # 創建ChromaDB客戶端
            self.client = chromadb.PersistentClient(
                path=self.db_path,
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
            
            logger.info("ChromaDB連接成功")
            
        except Exception as e:
            logger.error(f"初始化ChromaDB失敗: {e}")
            raise e
    
    def is_initialized(self) -> bool:
        """檢查向量資料庫客戶端和集合是否已初始化"""
        initialized = self.client is not None and self.collection is not None
        if not initialized:
            logger.debug(f"Vector DB is_initialized check: client is {'set' if self.client else 'None'}, collection is {'set' if self.collection else 'None'}")
        return initialized
    
    def create_collection(self, vector_dimension: int):
        """創建向量集合"""
        try:
            self.vector_dimension = vector_dimension
            
            # 檢查集合是否已存在
            try:
                self.collection = self.client.get_collection(name=self.collection_name)
                logger.info(f"集合 {self.collection_name} 已存在")
                return
            except Exception:
                # 集合不存在，創建新集合
                pass
            
            # 創建集合
            self.collection = self.client.create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},  # 使用餘弦相似度
            )
            
            logger.info(f"成功創建集合 {self.collection_name}，向量維度: {vector_dimension}")
            
        except Exception as e:
            logger.error(f"創建集合失敗: {e}")
            raise e
    
    def insert_vectors(self, vector_records: List[VectorRecord]) -> bool:
        """批量插入向量記錄"""
        try:
            if not vector_records:
                return True
            
            if not self.collection:
                raise ValueError("集合未初始化")
            
            # 準備插入數據
            ids = []
            embeddings = []
            metadatas = []
            documents = []
            
            for record in vector_records:
                vector_id = str(uuid.uuid4())
                ids.append(vector_id)
                embeddings.append(record.embedding_vector)
                metadatas.append({
                    "document_id": record.document_id,
                    # TODO: "file_type" 應該從文檔元數據中獲取並填充
                    "file_type": record.metadata.get("file_type", "") if record.metadata else "", 
                    "created_at": record.created_at.isoformat()
                })
                # 使用 record.chunk_text (如果存在)，否則使用一個有意義的備用值
                document_content = record.chunk_text if record.chunk_text else f"內容片段 {record.document_id[:8]}..."
                documents.append(document_content)
            
            # 執行插入
            self.collection.add(
                ids=ids,
                embeddings=embeddings,
                metadatas=metadatas,
                documents=documents
            )
            
            logger.info(f"成功插入 {len(vector_records)} 條向量記錄")
            return True
            
        except Exception as e:
            logger.error(f"插入向量記錄失敗: {e}")
            return False
    
    def search_similar_vectors(
        self, 
        query_vector: List[float], 
        top_k: int = 10,
        similarity_threshold: float = 0.5
    ) -> List[SemanticSearchResult]:
        """搜索相似向量"""
        try:
            if not self.collection:
                raise ValueError("集合未初始化")
            
            # 執行搜索
            results = self.collection.query(
                query_embeddings=[query_vector],
                n_results=top_k,
                include=["documents", "metadatas", "distances"]
            )
            
            # 處理搜索結果
            search_results = []
            if results["ids"] and len(results["ids"]) > 0:
                for i, (doc_id, metadata, distance) in enumerate(zip(
                    results["ids"][0], results["metadatas"][0], results["distances"][0]
                )):
                    # ChromaDB返回的是距離，需要轉換為相似度
                    # 對於餘弦距離，相似度 = 1 - 距離
                    similarity_score = 1.0 - distance
                    
                    # 檢查相似度閾值
                    if similarity_score >= similarity_threshold:
                        search_result = SemanticSearchResult(
                            document_id=metadata.get("document_id", ""),
                            similarity_score=similarity_score,
                            summary_text=results["documents"][0][i] if results["documents"] else "",
                            metadata={
                                "file_type": metadata.get("file_type", ""),
                                "created_at": metadata.get("created_at", ""),
                                "vector_id": doc_id
                            }
                        )
                        search_results.append(search_result)
            
            logger.info(f"搜索完成，找到 {len(search_results)} 個相似結果")
            return search_results
            
        except Exception as e:
            logger.error(f"向量搜索失敗: {e}")
            return []
    
    def delete_by_document_id(self, document_id: str) -> bool:
        """根據文檔ID刪除向量"""
        try:
            if not self.collection:
                raise ValueError("集合未初始化")
            
            # 查詢需要刪除的記錄
            results = self.collection.get(
                where={"document_id": document_id},
                include=["metadatas"]
            )
            
            if results["ids"]:
                # 刪除記錄
                self.collection.delete(ids=results["ids"])
                logger.info(f"已刪除文檔 {document_id} 的 {len(results['ids'])} 條向量記錄")
                return True
            else:
                logger.info(f"未找到文檔 {document_id} 的向量記錄")
                return True
            
        except Exception as e:
            logger.error(f"刪除向量記錄失敗: {e}")
            return False
    
    async def delete_by_document_ids(self, document_ids: List[str]) -> Dict[str, Union[int, List[str]]]:
        """根據文檔ID列表從向量數據庫中刪除向量記錄。"""
        if not self.is_initialized():
            logger.warning("向量數據庫未初始化，無法刪除向量。")
            return {"deleted_count": 0, "failed_ids": document_ids, "errors": ["向量數據庫未初始化"]}

        deleted_count = 0
        failed_ids = []
        errors = []

        for doc_id_str in document_ids:
            try:
                # 假設 ChromaDB 使用 document_id 作為其 'id' 或在元數據中
                # 我們需要知道 ChromaDB 是如何存儲和通過什麼來刪除的。
                # 如果是通過 filter 刪除：
                self.collection.delete(where={"document_id": doc_id_str})
                # 或者如果是直接按ID刪除 (如果Chroma內部ID與我們的document_id一致或有關聯):
                # self.collection.delete(ids=[doc_id_str]) # 這需要確認Chroma是否這樣工作

                logger.info(f"已從向量數據庫刪除 document_id: {doc_id_str} 的向量。")
                deleted_count += 1
            except Exception as e:
                logger.error(f"從向量數據庫按 document_id {doc_id_str} 刪除時出錯: {e}")
                failed_ids.append(doc_id_str)
                errors.append(str(e))
        
        return {"deleted_count": deleted_count, "failed_ids": failed_ids, "errors": errors}
    
    async def get_collection_stats(self) -> Dict[str, Any]:
        """獲取向量數據庫集合的統計信息。"""
        try:
            if not self.collection:
                return {"error": "集合未初始化"}
            
            # 獲取集合統計信息
            count = self.collection.count()
            
            return {
                "collection_name": self.collection_name,
                "total_vectors": count,
                "vector_dimension": self.vector_dimension,
                "status": "ready"
            }
            
        except Exception as e:
            logger.error(f"獲取集合統計信息失敗: {e}")
            return {"error": str(e)}
    
    def close_connection(self):
        """關閉連接"""
        try:
            # ChromaDB會自動處理連接關閉
            self.client = None
            self.collection = None
            
            logger.info("ChromaDB連接已關閉")
            
        except Exception as e:
            logger.error(f"關閉ChromaDB連接失敗: {e}")

# 全局向量資料庫服務實例
vector_db_service = VectorDatabaseService() 