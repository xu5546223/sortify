from typing import List, Optional, Dict, Any, Tuple, Union
import logging
from pathlib import Path
import chromadb
from chromadb.config import Settings
import uuid
from datetime import datetime
from app.core.logging_utils import AppLogger, log_event, LogLevel # Added
from app.core.config import settings
from app.models.vector_models import VectorRecord, SemanticSearchResult

logger = AppLogger(__name__, level=logging.DEBUG).get_logger() # Existing AppLogger for sync methods

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
                    "owner_id": record.owner_id,
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
        similarity_threshold: float = 0.5,
        owner_id_filter: Optional[str] = None,
        collection_name: Optional[str] = None
    ) -> List[SemanticSearchResult]:
        """搜索相似向量，可選根據 owner_id 過濾，並可指定集合"""
        try:
            target_collection = self.collection 
            if collection_name:
                if not self.client:
                    logger.error("ChromaDB client not initialized, cannot switch collection.")
                    raise ValueError("ChromaDB client not initialized.")
                try:
                    target_collection = self.client.get_collection(name=collection_name)
                    logger.info(f"Performing search on specified collection: {collection_name}")
                except Exception as e_get_coll: 
                    logger.error(f"Failed to get specified collection '{collection_name}': {e_get_coll}. Falling back to default collection or erroring.")
                    raise ValueError(f"Specified collection '{collection_name}' not found or not accessible.")

            if not target_collection: 
                logger.error("Target collection for search is not initialized.")
                raise ValueError("集合未初始化")
            
            # 準備查詢參數
            query_params: Dict[str, Any] = {
                "query_embeddings": [query_vector],
                "n_results": top_k,
                "include": ["documents", "metadatas", "distances"]
            }

            if owner_id_filter:
                query_params["where"] = {"owner_id": owner_id_filter}
            
            # 執行搜索
            results = target_collection.query(**query_params)
            
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
                                "owner_id": metadata.get("owner_id", ""),
                                "vector_id": doc_id
                            }
                        )
                        search_results.append(search_result)
            
            logger.info(f"搜索完成，在集合 '{target_collection.name}' 中找到 {len(search_results)} 個相似結果。Owner filter: {'applied' if owner_id_filter else 'not applied'}")
            return search_results
            
        except ValueError as ve: 
            logger.warning(f"向量搜索中的輸入或配置錯誤: {ve}")
            raise
        except Exception as e:
            logger.error(f"向量搜索失敗: {e}", exc_info=True) 
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
    
    async def delete_by_document_ids(self, document_ids: List[str], request_id: Optional[str] = None, user_id: Optional[str] = None) -> Dict[str, Union[int, List[str]]]: # Added request_id, user_id
        """根據文檔ID列表從向量數據庫中刪除向量記錄。"""
        log_details_initial = {"num_document_ids": len(document_ids)}
        await log_event(db=None, level=LogLevel.DEBUG, message="Attempting batch deletion of document vectors.",
                        source="service.vector_db.delete_by_doc_ids_batch", details=log_details_initial, request_id=request_id, user_id=user_id)

        if not self.is_initialized():
            await log_event(db=None, level=LogLevel.WARNING, message="Vector DB not initialized for batch deletion.",
                            source="service.vector_db.delete_by_doc_ids_batch", details=log_details_initial, request_id=request_id, user_id=user_id)
            return {"deleted_count": 0, "failed_ids": document_ids, "errors": ["Vector database not initialized."]}

        deleted_count = 0
        failed_ids = []
        errors = []

        for doc_id_str in document_ids:
            item_log_details = {**log_details_initial, "current_doc_id": doc_id_str}
            try:
                # This is a synchronous call to ChromaDB client
                self.collection.delete(where={"document_id": doc_id_str})
                # Assuming if it doesn't error, it worked or the item wasn't there.
                # ChromaDB's delete with a where clause doesn't throw error if no items match.
                await log_event(db=None, level=LogLevel.DEBUG, message=f"Vector DB deletion processed for doc_id: {doc_id_str} (may not have existed).",
                                source="service.vector_db.delete_by_doc_ids_batch", details=item_log_details, request_id=request_id, user_id=user_id)
                deleted_count += 1 # This counts attempts that didn't error, not necessarily actual deletions by Chroma.
                                   # ChromaDB's delete with 'where' doesn't return count of deleted items.
            except Exception as e:
                await log_event(db=None, level=LogLevel.ERROR, message=f"Error deleting vectors for doc_id {doc_id_str} in batch: {str(e)}",
                                source="service.vector_db.delete_by_doc_ids_batch", exc_info=True, details=item_log_details, request_id=request_id, user_id=user_id)
                failed_ids.append(doc_id_str)
                errors.append(str(e))
        
        summary_details = {**log_details_initial, "processed_count": deleted_count, "failed_count": len(failed_ids)}
        await log_event(db=None, level=LogLevel.INFO, message=f"Batch vector deletion process completed. Processed: {deleted_count}, Failed: {len(failed_ids)}.",
                        source="service.vector_db.delete_by_doc_ids_batch", details=summary_details, request_id=request_id, user_id=user_id)
        return {"deleted_count": deleted_count, "failed_ids": failed_ids, "errors": errors} # Note: deleted_count here is more like "processed_without_error_count"
    
    async def get_collection_stats(self, request_id: Optional[str] = None, user_id: Optional[str] = None) -> Dict[str, Any]: # Added request_id, user_id
        """獲取向量數據庫集合的統計信息。"""
        await log_event(db=None, level=LogLevel.DEBUG, message="Attempting to get collection stats.",
                        source="service.vector_db.get_stats", request_id=request_id, user_id=user_id)
        try:
            if not self.collection:
                await log_event(db=None, level=LogLevel.WARNING, message="Collection not initialized, cannot get stats.",
                                source="service.vector_db.get_stats", request_id=request_id, user_id=user_id)
                return {"error": "Collection not initialized."} # User-friendly
            
            count = self.collection.count() # Sync call
            
            stats = {
                "collection_name": self.collection_name,
                "total_vectors": count,
                "vector_dimension": self.vector_dimension,
                "status": "ready"
            }
            await log_event(db=None, level=LogLevel.DEBUG, message="Successfully retrieved collection stats.",
                            source="service.vector_db.get_stats", details=stats, request_id=request_id, user_id=user_id)
            return stats
            
        except Exception as e:
            await log_event(db=None, level=LogLevel.ERROR, message=f"Failed to get collection stats: {str(e)}",
                            source="service.vector_db.get_stats", exc_info=True,
                            details={"error": str(e), "error_type": type(e).__name__}, request_id=request_id, user_id=user_id)
            return {"error": f"Failed to retrieve collection stats: {str(e)}"} # User-friendly part
    
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