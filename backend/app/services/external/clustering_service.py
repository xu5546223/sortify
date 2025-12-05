"""
動態文檔聚類服務
使用HDBSCAN算法進行基於語義embedding的無監督聚類
"""

import logging
import uuid
import random
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorDatabase
import numpy as np

try:
    import hdbscan
    HDBSCAN_AVAILABLE = True
except ImportError:
    HDBSCAN_AVAILABLE = False
    logging.warning("hdbscan庫未安裝,聚類功能將不可用。請運行: pip install hdbscan")

from app.models.clustering_models import ClusterInfo, ClusteringJobStatus, ClusterSummary
from app.models.document_models import Document
from app.services.vector.vector_db_service import vector_db_service
from app.core.logging_utils import AppLogger, log_event, LogLevel
from app.crud import crud_documents

logger = AppLogger(__name__, level=logging.INFO).get_logger()

# MongoDB集合名稱
CLUSTERS_COLLECTION = "clusters"
CLUSTERING_JOBS_COLLECTION = "clustering_jobs"
DOCUMENTS_COLLECTION = "documents"


class ClusteringService:
    """
    動態文檔聚類服務 - 使用HDBSCAN算法
    
    HDBSCAN (Hierarchical Density-Based Spatial Clustering of Applications with Noise)
    是一種基於密度的聚類算法,能夠:
    - 自動確定聚類數量
    - 識別噪聲點
    - 處理不同密度和形狀的聚類
    - 對高維embeddings友好
    
    參數調優指南:
    - min_cluster_size: 增大 → 更少但更大的聚類
    - min_samples: 增大 → 更保守的聚類,更多噪聲點
    - metric='cosine': 適合歸一化的文本embeddings
    """
    
    def __init__(
        self, 
        min_cluster_size: int = 3,
        min_samples: int = 2,
        min_documents_for_clustering: int = 5
    ):
        """
        初始化聚類服務
        
        Args:
            min_cluster_size: 最小聚類大小 (默認3, 建議範圍: 2-10)
            min_samples: HDBSCAN核心樣本參數 (默認2, 建議範圍: 1-5)
            min_documents_for_clustering: 執行聚類所需的最少文檔數 (默認5)
        """
        self.min_cluster_size = min_cluster_size
        self.min_samples = min_samples
        self.min_documents_for_clustering = min_documents_for_clustering
    
    async def run_clustering_for_user(
        self,
        db: AsyncIOMotorDatabase,
        owner_id: uuid.UUID,
        force_recluster: bool = False,
        include_all_vectorized: bool = False  # 新增: 包含所有已向量化的文檔
    ) -> ClusteringJobStatus:
        """
        為特定用戶執行聚類
        
        Args:
            db: 數據庫連接
            owner_id: 用戶ID
            force_recluster: 是否強制重新聚類已聚類的文檔
        
        Returns:
            ClusteringJobStatus: 聚類任務狀態
        
        流程:
        1. 創建聚類任務記錄
        2. 從向量數據庫提取所有該用戶的summary embeddings
        3. 運行HDBSCAN聚類
        4. 為每個簇生成標籤(使用LLM)
        5. 更新文檔的cluster_info
        6. 保存聚類信息到clusters集合
        """
        if not HDBSCAN_AVAILABLE:
            raise RuntimeError("HDBSCAN庫未安裝,無法執行聚類")
        
        owner_id_str = str(owner_id)
        
        # 創建聚類任務
        job_status = ClusteringJobStatus(
            owner_id=owner_id,
            status="running",
            started_at=datetime.utcnow()
        )
        
        await log_event(
            db=db,
            level=LogLevel.INFO,
            message=f"開始為用戶 {owner_id_str} 執行聚類任務",
            source="clustering_service.run_clustering",
            user_id=owner_id_str,
            details={"job_id": job_status.job_id, "force_recluster": force_recluster}
        )
        
        try:
            # 保存初始任務狀態
            await db[CLUSTERING_JOBS_COLLECTION].insert_one(job_status.model_dump())
            
            # 如果是強制重新分類，先清除舊的聚類數據
            if force_recluster:
                logger.info(f"強制重新分類: 清除用戶 {owner_id_str} 的舊聚類數據")
                
                # 刪除所有舊的聚類
                await db[CLUSTERS_COLLECTION].delete_many({"owner_id": owner_id})
                
                # 重置所有文檔的分類狀態為 pending（包括 pending、clustered、excluded 所有狀態）
                # 這確保所有文檔都會被重新處理
                await db[DOCUMENTS_COLLECTION].update_many(
                    {
                        "owner_id": owner_id,
                        # 處理所有可能的狀態：clustered、excluded、pending，以及狀態為 null 或不存在的情況
                        "$or": [
                            {"clustering_status": {"$in": ["clustered", "excluded", "pending"]}},
                            {"clustering_status": {"$exists": False}},
                            {"clustering_status": None}
                        ]
                    },
                    {
                        "$set": {
                            "clustering_status": "pending",
                            "cluster_info": None
                        }
                    }
                )
                
                await log_event(
                    db=db,
                    level=LogLevel.INFO,
                    message=f"已清除用戶 {owner_id_str} 的舊聚類數據，準備重新分類",
                    source="clustering_service.run_clustering",
                    user_id=owner_id_str
                )
            
            # 1. 提取用戶的embeddings
            # 當 force_recluster=true 時，強制包含所有已向量化的文檔
            should_include_all = include_all_vectorized or force_recluster
            document_ids, embeddings = await self._extract_user_embeddings(
                db, owner_id, 
                include_clustered=force_recluster, 
                include_all_vectorized=should_include_all
            )
            
            if len(document_ids) < self.min_documents_for_clustering:
                job_status.status = "completed"
                job_status.completed_at = datetime.utcnow()
                job_status.error_message = f"文檔數量不足({len(document_ids)}),需要至少{self.min_documents_for_clustering}個文檔"
                
                await self._update_job_status(db, job_status)
                await log_event(
                    db=db,
                    level=LogLevel.INFO,
                    message=f"用戶 {owner_id_str} 文檔數量不足,跳過聚類",
                    source="clustering_service.run_clustering",
                    user_id=owner_id_str,
                    details={"document_count": len(document_ids)}
                )
                return job_status
            
            job_status.total_documents = len(document_ids)
            await self._update_job_status(db, job_status)
            
            # 2. 運行HDBSCAN聚類
            cluster_labels = self._run_hdbscan_clustering(embeddings)
            
            # 3. 處理聚類結果
            clusters_map = self._organize_clusters(document_ids, cluster_labels)
            
            logger.info(f"用戶 {owner_id_str} 聚類完成: {len(clusters_map)}個聚類, 噪聲點: {len(clusters_map.get(-1, []))}")
            
            # 4. 批量生成所有聚類標籤 (一次AI調用!)
            # 實現三層分類系統：
            # - 主要聚類：>= min_cluster_size 個文檔
            # - 小型聚類：2 個文檔（標記為「其他：XXX」）
            # - 未分類：噪聲點或單個文檔
            
            valid_clusters = {}  # {cluster_idx: doc_ids} - 主要聚類
            small_clusters = {}  # {cluster_idx: doc_ids} - 小型聚類（2個文檔）
            excluded_doc_ids = []  # 噪聲點
            
            # 分類處理
            for cluster_idx, doc_ids in clusters_map.items():
                if cluster_idx == -1:  # 噪聲點
                    excluded_doc_ids.extend(doc_ids)
                    continue
                
                if len(doc_ids) >= self.min_cluster_size:
                    # 主要聚類
                    valid_clusters[cluster_idx] = doc_ids
                elif len(doc_ids) == 2:
                    # 小型聚類：保留但特殊標記
                    small_clusters[cluster_idx] = doc_ids
                else:
                    # 單個文檔：視為未分類
                    excluded_doc_ids.extend(doc_ids)
            
            # 標記未分類文檔
            if excluded_doc_ids:
                await self._mark_documents_as_excluded(db, excluded_doc_ids)
            
            logger.info(f"聚類結果：主要聚類 {len(valid_clusters)} 個，小型聚類 {len(small_clusters)} 個，未分類 {len(excluded_doc_ids)} 個文檔")
            
            # 批量生成標籤 (一次AI調用處理所有聚類!)
            # 傳遞 embeddings 以支持多樣性採樣
            cluster_labels_map = await self._generate_all_cluster_labels_batch(
                db, owner_id_str, valid_clusters, 
                all_embeddings=embeddings, 
                all_doc_ids=document_ids
            )
            
            # 5. 保存主要聚類信息並更新文檔
            cluster_count = 0
            for cluster_idx, doc_ids in valid_clusters.items():
                cluster_id = f"cluster_{owner_id_str}_{cluster_idx}"
                cluster_name = cluster_labels_map.get(cluster_idx, f"分類 {cluster_idx}")
                
                # 獲取聚類的關鍵詞
                keywords = await self._extract_cluster_keywords(db, doc_ids)
                
                # 保存聚類信息
                cluster_info_doc = ClusterInfo(
                    cluster_id=cluster_id,
                    cluster_name=cluster_name,
                    owner_id=owner_id,
                    document_count=len(doc_ids),
                    representative_documents=doc_ids[:10],
                    keywords=keywords,
                    clustering_version="v1.0"
                )
                
                await self._save_cluster_info(db, cluster_info_doc)
                
                # 更新文檔的cluster_info
                await self._update_documents_cluster_info(
                    db, doc_ids, cluster_id, cluster_name, cluster_idx, len(doc_ids)
                )
                
                cluster_count += 1
                job_status.processed_documents += len(doc_ids)
                job_status.update_progress()
                await self._update_job_status(db, job_status)
            
            # 6. 處理小型聚類（2個文檔）
            if small_clusters:
                logger.info(f"處理 {len(small_clusters)} 個小型聚類...")
                small_cluster_labels = await self._generate_small_cluster_labels(
                    db, owner_id_str, small_clusters
                )
                
                for cluster_idx, doc_ids in small_clusters.items():
                    cluster_id = f"cluster_{owner_id_str}_small_{cluster_idx}"
                    # 小型聚類標記為「其他：XXX」
                    base_label = small_cluster_labels.get(cluster_idx, "其他項目")
                    cluster_name = f"其他：{base_label}"
                    
                    keywords = await self._extract_cluster_keywords(db, doc_ids)
                    
                    cluster_info_doc = ClusterInfo(
                        cluster_id=cluster_id,
                        cluster_name=cluster_name,
                        owner_id=owner_id,
                        document_count=len(doc_ids),
                        representative_documents=doc_ids,
                        keywords=keywords,
                        clustering_version="v1.0_small"
                    )
                    
                    await self._save_cluster_info(db, cluster_info_doc)
                    
                    await self._update_documents_cluster_info(
                        db, doc_ids, cluster_id, cluster_name, cluster_idx, len(doc_ids)
                    )
                    
                    cluster_count += 1
                    job_status.processed_documents += len(doc_ids)
                    job_status.update_progress()
                    await self._update_job_status(db, job_status)
            
            # 7. 完成任務
            job_status.status = "completed"
            job_status.clusters_created = cluster_count
            job_status.completed_at = datetime.utcnow()
            job_status.processed_documents = job_status.total_documents
            job_status.progress_percentage = 100.0
            
            await self._update_job_status(db, job_status)
            
            await log_event(
                db=db,
                level=LogLevel.INFO,
                message=f"用戶 {owner_id_str} 聚類任務完成",
                source="clustering_service.run_clustering.completed",
                user_id=owner_id_str,
                details={
                    "job_id": job_status.job_id,
                    "clusters_created": cluster_count,
                    "documents_processed": job_status.total_documents
                }
            )
            
            return job_status
            
        except Exception as e:
            logger.error(f"用戶 {owner_id_str} 聚類任務失敗: {e}", exc_info=True)
            
            job_status.status = "failed"
            job_status.error_message = str(e)
            job_status.completed_at = datetime.utcnow()
            
            await self._update_job_status(db, job_status)
            
            await log_event(
                db=db,
                level=LogLevel.ERROR,
                message=f"用戶 {owner_id_str} 聚類任務失敗: {str(e)}",
                source="clustering_service.run_clustering.error",
                user_id=owner_id_str,
                details={"job_id": job_status.job_id, "error": str(e)}
            )
            
            raise
    
    async def _extract_user_embeddings(
        self,
        db: AsyncIOMotorDatabase,
        owner_id: uuid.UUID,
        include_clustered: bool = False,
        include_all_vectorized: bool = False  # 新增: 包含所有已向量化的文檔
    ) -> Tuple[List[str], np.ndarray]:
        """
        從ChromaDB提取用戶的所有文檔embeddings
        
        Args:
            db: 數據庫連接
            owner_id: 用戶ID
            include_clustered: 是否包含已聚類的文檔
        
        Returns:
            Tuple[文檔ID列表, embeddings矩陣]
        """
        owner_id_str = str(owner_id)
        
        # 從向量數據庫獲取用戶的summary vectors
        # 使用vector_db_service的get_user_document_sample方法
        sample_data = vector_db_service.get_user_document_sample(
            user_id=owner_id_str,
            limit=10000,  # 設置一個較大的限制
            include_metadata=True,
            vector_type_filter="summary"  # 只獲取摘要向量
        )
        
        if not sample_data:
            logger.warning(f"用戶 {owner_id_str} 沒有可用的向量數據")
            return [], np.array([])
        
        # 根據選項決定過濾策略
        if include_all_vectorized:
            # 包含所有已向量化的文檔,不過濾
            logger.info(f"包含所有已向量化的文檔: {len(sample_data)} 個")
        elif not include_clustered:
            # 只包含 pending 狀態的文檔
            pending_doc_ids = set()
            cursor = db[DOCUMENTS_COLLECTION].find(
                {
                    "owner_id": owner_id,
                    "clustering_status": "pending",
                    "enriched_data": {"$ne": None}
                },
                {"_id": 1}
            )
            async for doc in cursor:
                pending_doc_ids.add(str(doc["_id"]))
            
            # 過濾sample_data
            filtered_data = [
                item for item in sample_data
                if item.get("document_id") in pending_doc_ids
            ]
            sample_data = filtered_data
            logger.info(f"只包含 pending 狀態的文檔: {len(sample_data)} 個")
        
        if not sample_data:
            logger.info(f"用戶 {owner_id_str} 沒有待聚類的文檔")
            return [], np.array([])
        
        # 提取document_ids和embeddings
        document_ids = []
        embeddings_list = []
        
        for item in sample_data:
            doc_id = item.get("document_id")
            embedding = item.get("embedding")
            
            # 檢查 doc_id 和 embedding 是否存在 (embedding 是數組,不能直接用 if)
            if doc_id and embedding is not None:
                document_ids.append(doc_id)
                embeddings_list.append(embedding)
        
        if not embeddings_list:
            return [], np.array([])
        
        embeddings = np.array(embeddings_list)
        
        logger.info(f"為用戶 {owner_id_str} 提取了 {len(document_ids)} 個文檔的embeddings")
        
        return document_ids, embeddings
    
    def _run_hdbscan_clustering(self, embeddings: np.ndarray) -> np.ndarray:
        """
        運行HDBSCAN聚類算法
        
        Args:
            embeddings: embeddings矩陣
        
        Returns:
            聚類標籤數組 (-1表示噪聲點)
        """
        if len(embeddings) < self.min_cluster_size:
            logger.warning(f"樣本數量({len(embeddings)})小於min_cluster_size({self.min_cluster_size})")
            return np.array([-1] * len(embeddings))
        
        logger.info(f"運行HDBSCAN聚類: {len(embeddings)} 個樣本")
        
        # 注意：embeddings 已經在 EmbeddingService.encode_text() 中通過 
        # normalize_embeddings=True 進行了 L2 歸一化，無需再次歸一化
        
        # 創建HDBSCAN聚類器
        # 參數說明:
        # - min_cluster_size: 最小聚類大小,控制聚類的粒度
        # - min_samples: 核心樣本的鄰域大小,影響噪聲點的判定
        # - metric: 使用euclidean距離(因為向量已經L2歸一化,等同於cosine相似度)
        # - cluster_selection_method: 'eom' (Excess of Mass) 通常對文本聚類效果更好
        # - prediction_data: True 允許對新數據進行軟聚類預測
        # - core_dist_n_jobs: -1 使用所有CPU核心加速計算
        clusterer = hdbscan.HDBSCAN(
            min_cluster_size=self.min_cluster_size,
            min_samples=self.min_samples,
            metric='euclidean',  # L2歸一化後的歐氏距離等同於余弦距離
            cluster_selection_method='eom',
            prediction_data=True,
            core_dist_n_jobs=-1  # 使用所有CPU核心
        )
        
        # 執行聚類
        cluster_labels = clusterer.fit_predict(embeddings)
        
        # 獲取聚類概率(置信度)
        # 可用於後續判斷聚類質量
        try:
            cluster_probabilities = clusterer.probabilities_
            avg_probability = np.mean(cluster_probabilities[cluster_labels != -1]) if len(cluster_probabilities[cluster_labels != -1]) > 0 else 0
            logger.info(f"平均聚類置信度: {avg_probability:.3f}")
        except Exception as e:
            logger.warning(f"無法獲取聚類概率: {e}")
        
        # 統計結果
        unique_labels = set(cluster_labels)
        n_clusters = len(unique_labels) - (1 if -1 in unique_labels else 0)
        n_noise = list(cluster_labels).count(-1)
        
        logger.info(f"HDBSCAN聚類完成: {n_clusters}個聚類, {n_noise}個噪聲點")
        
        # 記錄每個聚類的大小
        if n_clusters > 0:
            from collections import Counter
            cluster_sizes = Counter(cluster_labels[cluster_labels != -1])
            logger.info(f"聚類大小分佈: {dict(cluster_sizes)}")
        
        return cluster_labels
    
    def _organize_clusters(
        self,
        document_ids: List[str],
        cluster_labels: np.ndarray
    ) -> Dict[int, List[str]]:
        """
        組織聚類結果
        
        Args:
            document_ids: 文檔ID列表
            cluster_labels: 聚類標籤
        
        Returns:
            字典: {cluster_label: [doc_ids]}
        """
        clusters_map: Dict[int, List[str]] = {}
        
        for doc_id, label in zip(document_ids, cluster_labels):
            label_int = int(label)
            if label_int not in clusters_map:
                clusters_map[label_int] = []
            clusters_map[label_int].append(doc_id)
        
        return clusters_map
    
    def _select_diverse_samples(
        self,
        cluster_doc_ids: List[str],
        all_embeddings: np.ndarray,
        all_doc_ids: List[str],
        sample_size: int = 10
    ) -> List[str]:
        """
        使用 Embeddings 和 Farthest Point Sampling (FPS) 選擇多樣性樣本
        
        策略:
        1. 獲取該聚類所有文檔的 embeddings
        2. 計算聚類中心 (Centroid)
        3. 選擇離中心最近的點作為第一個樣本 (代表性)
        4. 之後每次選擇離已選點集距離最遠的點 (多樣性)
        5. 直到選滿 sample_size
        """
        if len(cluster_doc_ids) <= sample_size:
            return cluster_doc_ids
            
        try:
            # 建立 doc_id -> index 映射
            id_to_idx = {doc_id: i for i, doc_id in enumerate(all_doc_ids)}
            
            # 獲取聚類中所有文檔的 embeddings
            cluster_indices = [id_to_idx[doc_id] for doc_id in cluster_doc_ids if doc_id in id_to_idx]
            
            if not cluster_indices:
                return cluster_doc_ids[:sample_size]
                
            cluster_embeddings = all_embeddings[cluster_indices]
            
            # 記錄選中的局部索引 (相對於 cluster_embeddings)
            selected_local_indices = []
            cand_local_indices = list(range(len(cluster_embeddings)))
            
            # 1. 選擇第一個點：離中心最近
            centroid = np.mean(cluster_embeddings, axis=0)
            dists_to_centroid = np.linalg.norm(cluster_embeddings - centroid, axis=1)
            first_idx = np.argmin(dists_to_centroid)
            
            selected_local_indices.append(first_idx)
            cand_local_indices.remove(first_idx)
            
            # 初始化距離矩陣：每個候選點到最近已選點的距離
            # 初始時只有一個已選點，所以就是到該點的距離
            min_dists = np.linalg.norm(cluster_embeddings[cand_local_indices] - cluster_embeddings[first_idx], axis=1)
            
            # FPS 循環
            while len(selected_local_indices) < sample_size and cand_local_indices:
                # 選擇距離最大的點 (Maximize Minimum Distance)
                max_dist_idx_in_cand = np.argmax(min_dists)
                best_local_idx = cand_local_indices[max_dist_idx_in_cand]
                
                selected_local_indices.append(best_local_idx)
                
                # 從候選列表移除
                # 注意：min_dists 對應的是 cand_local_indices，需要同步移除
                cand_local_indices.pop(max_dist_idx_in_cand)
                min_dists = np.delete(min_dists, max_dist_idx_in_cand)
                
                if not cand_local_indices:
                    break
                    
                # 更新 min_dists
                # 計算剩餘候選點到新選中點的距離
                curr_embedding = cluster_embeddings[best_local_idx]
                new_dists = np.linalg.norm(cluster_embeddings[cand_local_indices] - curr_embedding, axis=1)
                
                # 更新為兩者較小值 (距離已選集合的最小距離)
                min_dists = np.minimum(min_dists, new_dists)
            
            # 轉換回 doc_ids
            selected_doc_ids = [cluster_doc_ids[i] for i in selected_local_indices]
            logger.info(f"FPS多樣性採樣: 從 {len(cluster_doc_ids)} 個文檔中選出 {len(selected_doc_ids)} 個樣本")
            return selected_doc_ids
            
        except Exception as e:
            logger.error(f"FPS採樣失敗: {e}, 降級為隨機採樣")
            return random.sample(cluster_doc_ids, min(sample_size, len(cluster_doc_ids)))

    async def _generate_all_cluster_labels_batch(
        self,
        db: AsyncIOMotorDatabase,
        owner_id_str: str,
        clusters_map: Dict[int, List[str]],  # {cluster_idx: [doc_ids]}
        all_embeddings: Optional[np.ndarray] = None,
        all_doc_ids: Optional[List[str]] = None
    ) -> Dict[int, str]:
        """
        批量生成所有聚類的標籤 (一次AI調用!)
        
        使用 Embedding FPS 採樣確保樣本多樣性，避免漏掉少數類別。
        
        Args:
            db: 數據庫連接
            owner_id_str: 用戶ID字符串
            clusters_map: 聚類映射 {cluster_idx: [doc_ids]}
            all_embeddings: 所有文檔的 embeddings (用於 FPS 採樣)
            all_doc_ids: 所有文檔的 ID (用於 FPS 採樣)
        """
        try:
            from app.services.ai.unified_ai_service_simplified import unified_ai_service_simplified, AIRequest, TaskType
            from app.services.ai.prompt_manager_simplified import prompt_manager_simplified, PromptType
            import json
            
            # 為每個聚類收集樣本文檔
            all_clusters_data = []
            
            for cluster_idx, doc_ids in clusters_map.items():
                # 使用多樣性採樣
                if all_embeddings is not None and all_doc_ids is not None:
                    sample_doc_ids = self._select_diverse_samples(doc_ids, all_embeddings, all_doc_ids, sample_size=10)
                else:
                    # 降級為均勻間隔抽樣
                    sample_size = min(10, len(doc_ids))
                    if len(doc_ids) <= sample_size:
                        sample_doc_ids = doc_ids
                    else:
                        shuffled_ids = doc_ids.copy()
                        random.shuffle(shuffled_ids)
                        step = len(shuffled_ids) / sample_size
                        sample_doc_ids = [shuffled_ids[int(i * step)] for i in range(sample_size)]
                
                cursor = db[DOCUMENTS_COLLECTION].find(
                    {"_id": {"$in": [uuid.UUID(doc_id) for doc_id in sample_doc_ids]}},
                    {
                        "filename": 1,
                        "analysis.ai_analysis_output": 1
                    }
                ).limit(len(sample_doc_ids))
                
                document_samples = []
                async for doc in cursor:
                    ai_output = doc.get("analysis", {}).get("ai_analysis_output", {})
                    key_info = ai_output.get("key_information", {})
                    
                    title = key_info.get("auto_title") or doc.get("filename", "")
                    summary = key_info.get("content_summary", "")
                    keywords = key_info.get("searchable_keywords", [])
                    
                    if title or summary:
                        keywords_str = ", ".join(keywords[:3]) if isinstance(keywords, list) else ""
                        document_samples.append(f"• {title} | {summary[:80] if summary else ''} | {keywords_str}")
                
                if document_samples:
                    all_clusters_data.append({
                        "cluster_index": cluster_idx,
                        "document_count": len(doc_ids),
                        "samples": "\n".join(document_samples)
                    })
            
            if not all_clusters_data:
                logger.warning("沒有可用的聚類數據生成標籤")
                return {idx: f"分類 {idx}" for idx in clusters_map.keys()}
            
            # 構建聚類數據文本
            clusters_text = "\n\n".join([
                f"聚類 {item['cluster_index']} (共{item['document_count']}個文檔):\n{item['samples']}"
                for item in all_clusters_data
            ])
            
            # 使用 UnifiedAIService 完整流程
            # 注意：UnifiedAIService 會自動：
            # 1. reload_task_configs 以獲取最新的用戶偏好
            # 2. 獲取提示詞模板
            # 3. 使用用戶設定的 prompt_input_max_length 格式化提示詞
            from app.services.ai.unified_ai_service_simplified import unified_ai_service_simplified, AIRequest
            
            # 創建AI請求 - 使用批量聚類標籤任務類型
            ai_request = AIRequest(
                task_type=TaskType.BATCH_CLUSTER_LABELS,
                content="",  # 內容在 prompt_params 中
                require_language_consistency=True,
                user_id=owner_id_str,
                prompt_params={
                    "cluster_count": len(all_clusters_data),
                    "clusters_data": clusters_text
                },
                generation_params_override={
                    "temperature": 0.5
                }
            )
            
            logger.info(f"使用 UnifiedAIService 批量生成 {len(all_clusters_data)} 個聚類標籤")
            
            # 調用統一AI服務
            ai_response = await unified_ai_service_simplified.process_request(ai_request, db)
            
            if ai_response.success and ai_response.output_data:
                # output_data 現在是 AIBatchClusterLabelsOutput 對象
                try:
                    from app.models.ai_models_simplified import AIBatchClusterLabelsOutput
                    output_data = ai_response.output_data
                    
                    # 檢查類型
                    if isinstance(output_data, AIBatchClusterLabelsOutput):
                        labels_list = output_data.labels
                    elif isinstance(output_data, dict) and "labels" in output_data:
                        # 降級處理:如果是字典,嘗試直接解析
                        labels_list = [item for item in output_data["labels"]]
                    else:
                        logger.error(f"AI返回了意外的數據類型: {type(output_data)}")
                        raise ValueError(f"Unexpected output type: {type(output_data)}")
                    
                    # 構建標籤映射
                    cluster_labels_map = {}
                    for item in labels_list:
                        if hasattr(item, 'cluster_index') and hasattr(item, 'label'):
                            # Pydantic 對象
                            cluster_idx = item.cluster_index
                            label = item.label
                        elif isinstance(item, dict):
                            # 字典
                            cluster_idx = item.get("cluster_index")
                            label = item.get("label", f"分類 {cluster_idx}")
                        else:
                            logger.warning(f"無法解析標籤項: {item}")
                            continue
                        
                        if cluster_idx is not None:
                            cluster_labels_map[cluster_idx] = label
                    
                    if cluster_labels_map:
                        logger.info(f"✅ AI批量生成 {len(cluster_labels_map)} 個聚類標籤成功!")
                        return cluster_labels_map
                    else:
                        logger.warning(f"AI返回的數據中沒有找到有效標籤")
                        
                except Exception as parse_error:
                    logger.warning(f"解析AI返回的標籤失敗: {parse_error}", exc_info=True)
                    
            else:
                logger.warning(f"AI批量生成標籤失敗: {ai_response.error_message}")
                
        except Exception as ai_error:
            logger.error(f"調用AI批量生成標籤失敗: {ai_error}", exc_info=True)
        
        # 降級方案: 使用關鍵詞頻率
        logger.info("使用降級方案:關鍵詞頻率統計生成標籤")
        cluster_labels_map = {}
        for cluster_idx, doc_ids in clusters_map.items():
            label = await self._generate_cluster_label_simple(db, doc_ids[:10])
            cluster_labels_map[cluster_idx] = label
        
        return cluster_labels_map
    
    async def _generate_small_cluster_labels(
        self,
        db: AsyncIOMotorDatabase,
        owner_id_str: str,
        clusters_map: Dict[int, List[str]]
    ) -> Dict[int, str]:
        """
        為小型聚類（2個文檔）生成簡短標籤
        
        Args:
            db: 數據庫連接
            owner_id_str: 用戶ID字符串
            clusters_map: 聚類映射 {cluster_idx: [doc_ids]}
        
        Returns:
            Dict[cluster_idx, label]: 聚類標籤映射（不含「其他：」前綴）
        """
        cluster_labels_map = {}
        
        try:
            # 為每個小型聚類生成簡短描述
            for cluster_idx, doc_ids in clusters_map.items():
                # 獲取這2個文檔的標題和摘要
                cursor = db[DOCUMENTS_COLLECTION].find(
                    {"_id": {"$in": [uuid.UUID(doc_id) for doc_id in doc_ids]}},
                    {
                        "filename": 1,
                        "analysis.ai_analysis_output.key_information": 1
                    }
                ).limit(2)
                
                titles = []
                keywords_set = set()
                async for doc in cursor:
                    ai_output = doc.get("analysis", {}).get("ai_analysis_output", {})
                    key_info = ai_output.get("key_information", {})
                    
                    title = key_info.get("auto_title") or doc.get("filename", "")
                    titles.append(title)
                    
                    keywords = key_info.get("searchable_keywords", [])
                    if isinstance(keywords, list):
                        keywords_set.update(keywords[:3])
                
                # 嘗試找出共同特徵
                if keywords_set:
                    # 使用共同關鍵詞
                    common_keywords = list(keywords_set)[:2]
                    label = " · ".join(common_keywords)
                elif titles:
                    # 使用第一個文檔的標題（縮短）
                    label = titles[0][:10]
                else:
                    label = "其他項目"
                
                cluster_labels_map[cluster_idx] = label
                
        except Exception as e:
            logger.error(f"生成小型聚類標籤失敗: {e}")
            # 降級：使用索引
            for cluster_idx in clusters_map.keys():
                cluster_labels_map[cluster_idx] = f"項目 {cluster_idx}"
        
        return cluster_labels_map
    
    async def _generate_cluster_label(
        self,
        db: AsyncIOMotorDatabase,
        cluster_id: str,
        document_ids: List[str]
    ) -> str:
        """
        使用LLM為聚類生成標籤 (單個聚類版本 - 已廢棄,請使用批量版本)
        
        從聚類中隨機抽取5-10個文檔的summary/title,
        請求LLM生成共通的分類名稱
        
        Args:
            db: 數據庫連接
            cluster_id: 聚類ID
            document_ids: 文檔ID列表
        
        Returns:
            聚類名稱
        """
        try:
            # 隨機抽取最多10個文檔
            sample_size = min(10, len(document_ids))
            sample_doc_ids = random.sample(document_ids, sample_size)
            
            # 優化: 直接從 AI 分析輸出獲取數據,避免重複存儲
            document_samples = []
            cursor = db[DOCUMENTS_COLLECTION].find(
                {"_id": {"$in": [uuid.UUID(doc_id) for doc_id in sample_doc_ids]}},
                {"analysis.ai_analysis_output": 1, "filename": 1}
            )
            
            async for doc in cursor:
                # 直接使用 AI 分析輸出
                ai_output = doc.get("analysis", {}).get("ai_analysis_output", {})
                key_info = ai_output.get("key_information", {})
                
                title = key_info.get("auto_title") or doc.get("filename", "")
                summary = key_info.get("content_summary", "")
                keywords = key_info.get("searchable_keywords", [])
                content_type = ai_output.get("content_type", "")
                
                if title or summary:
                    keywords_str = ", ".join(keywords[:5]) if isinstance(keywords, list) else ""
                    document_samples.append(
                        f"- 標題: {title}\n  摘要: {summary[:150]}\n  關鍵詞: {keywords_str}\n  類型: {content_type}"
                    )
            
            if not document_samples:
                logger.warning(f"聚類 {cluster_id} 沒有可用的文檔樣本")
                return "未分類文檔"
            
            # 使用UnifiedAIService生成標籤
            try:
                from app.services.ai.unified_ai_service_simplified import unified_ai_service_simplified, AIRequest, TaskType
                
                # 準備文檔樣本文本
                samples_text = "\n\n".join(document_samples)
                
                # 創建AI請求
                ai_request = AIRequest(
                    task_type=TaskType.CLUSTER_LABEL_GENERATION,
                    content="",  # 內容在 prompt_params 中
                    require_language_consistency=True,
                    prompt_params={
                        "sample_count": str(len(document_samples)),
                        "document_samples": samples_text
                    }
                )
                
                # 調用AI服務
                ai_response = await unified_ai_service_simplified.process_request(ai_request, db)
                
                if ai_response.success and ai_response.output_data:
                    cluster_name = ai_response.output_data.cluster_name
                    logger.info(f"AI生成聚類標籤: {cluster_name} (置信度: {ai_response.output_data.confidence})")
                    return cluster_name
                else:
                    logger.warning(f"AI生成標籤失敗: {ai_response.error_message}")
                    # 降級到簡單方法
                    return await self._generate_cluster_label_simple(db, sample_doc_ids)
                    
            except Exception as ai_error:
                logger.error(f"調用AI服務生成標籤失敗: {ai_error}", exc_info=True)
                # 降級到簡單方法
                return await self._generate_cluster_label_simple(db, sample_doc_ids)
            
        except Exception as e:
            logger.error(f"生成聚類標籤失敗 (cluster: {cluster_id}): {e}", exc_info=True)
            return "未命名分類"
    
    async def _generate_cluster_label_simple(
        self,
        db: AsyncIOMotorDatabase,
        sample_doc_ids: List[str]
    ) -> str:
        """
        簡單的聚類標籤生成方法 (備用)
        使用關鍵詞頻率統計
        """
        try:
            from collections import Counter
            keywords_counter: Counter = Counter()
            
            # 優化: 直接從 AI 輸出獲取關鍵詞
            cursor = db[DOCUMENTS_COLLECTION].find(
                {"_id": {"$in": [uuid.UUID(doc_id) for doc_id in sample_doc_ids]}},
                {"analysis.ai_analysis_output.key_information.searchable_keywords": 1}
            )
            
            async for doc in cursor:
                ai_output = doc.get("analysis", {}).get("ai_analysis_output", {})
                key_info = ai_output.get("key_information", {})
                keywords = key_info.get("searchable_keywords", [])
                
                if isinstance(keywords, list):
                    for keyword in keywords[:5]:  # 只取前5個關鍵詞
                        keywords_counter[keyword] += 1
            
            if keywords_counter:
                # 使用最常見的2-3個關鍵詞組合
                top_keywords = [kw for kw, _ in keywords_counter.most_common(3)]
                cluster_name = " · ".join(top_keywords)
                return cluster_name if len(cluster_name) <= 30 else top_keywords[0]
            
            return "一般文檔"
            
        except Exception as e:
            logger.error(f"簡單標籤生成失敗: {e}")
            return "未命名分類"
    
    async def _extract_cluster_keywords(
        self,
        db: AsyncIOMotorDatabase,
        document_ids: List[str],
        max_keywords: int = 10
    ) -> List[str]:
        """
        提取聚類的關鍵詞
        
        Args:
            db: 數據庫連接
            document_ids: 文檔ID列表
            max_keywords: 最多返回的關鍵詞數
        
        Returns:
            關鍵詞列表
        """
        from collections import Counter
        keywords_counter: Counter = Counter()
        
        # 使用與其他方法一致的關鍵詞來源: ai_analysis_output
        cursor = db[DOCUMENTS_COLLECTION].find(
            {"_id": {"$in": [uuid.UUID(doc_id) for doc_id in document_ids]}},
            {"analysis.ai_analysis_output.key_information.searchable_keywords": 1}
        )
        
        async for doc in cursor:
            ai_output = doc.get("analysis", {}).get("ai_analysis_output", {})
            key_info = ai_output.get("key_information", {})
            keywords = key_info.get("searchable_keywords", [])
            if isinstance(keywords, list):
                for keyword in keywords:
                    keywords_counter[keyword] += 1
        
        # 返回最常見的關鍵詞
        return [kw for kw, _ in keywords_counter.most_common(max_keywords)]
    
    async def _save_cluster_info(
        self,
        db: AsyncIOMotorDatabase,
        cluster_info: ClusterInfo
    ) -> None:
        """
        保存聚類信息到clusters集合
        
        Args:
            db: 數據庫連接
            cluster_info: 聚類信息
        """
        # 使用upsert: 如果已存在則更新,否則插入
        await db[CLUSTERS_COLLECTION].update_one(
            {"cluster_id": cluster_info.cluster_id},
            {"$set": cluster_info.model_dump()},
            upsert=True
        )
        
        logger.debug(f"保存聚類信息: {cluster_info.cluster_id} - {cluster_info.cluster_name}")
    
    async def _update_documents_cluster_info(
        self,
        db: AsyncIOMotorDatabase,
        document_ids: List[str],
        cluster_id: str,
        cluster_name: str,
        cluster_index: int,
        total_docs_in_cluster: int
    ) -> None:
        """
        更新文檔的cluster_info欄位
        
        Args:
            db: 數據庫連接
            document_ids: 文檔ID列表
            cluster_id: 聚類ID
            cluster_name: 聚類名稱
            cluster_index: 聚類索引
            total_docs_in_cluster: 聚類中的文檔總數
        """
        # 計算confidence (簡單實現: 基於聚類大小)
        confidence = min(0.5 + (total_docs_in_cluster / 100), 0.95)
        
        cluster_info_dict = {
            "cluster_id": cluster_id,
            "cluster_name": cluster_name,
            "cluster_confidence": confidence,
            "clustered_at": datetime.utcnow().isoformat(),
            "clustering_version": "v1.0"
        }
        
        # 批量更新
        result = await db[DOCUMENTS_COLLECTION].update_many(
            {"_id": {"$in": [uuid.UUID(doc_id) for doc_id in document_ids]}},
            {
                "$set": {
                    "cluster_info": cluster_info_dict,
                    "clustering_status": "clustered",
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        logger.debug(f"更新了 {result.modified_count} 個文檔的聚類信息 (cluster: {cluster_id})")
    
    async def _mark_documents_as_excluded(
        self,
        db: AsyncIOMotorDatabase,
        document_ids: List[str]
    ) -> None:
        """
        將文檔標記為excluded (噪聲點或太小的聚類)
        
        Args:
            db: 數據庫連接
            document_ids: 文檔ID列表
        """
        if not document_ids:
            return
        
        result = await db[DOCUMENTS_COLLECTION].update_many(
            {"_id": {"$in": [uuid.UUID(doc_id) for doc_id in document_ids]}},
            {
                "$set": {
                    "clustering_status": "excluded",
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        logger.debug(f"標記了 {result.modified_count} 個文檔為excluded")
    
    async def _update_job_status(
        self,
        db: AsyncIOMotorDatabase,
        job_status: ClusteringJobStatus
    ) -> None:
        """
        更新聚類任務狀態
        
        Args:
            db: 數據庫連接
            job_status: 任務狀態
        """
        await db[CLUSTERING_JOBS_COLLECTION].update_one(
            {"job_id": job_status.job_id},
            {"$set": job_status.model_dump()},
            upsert=True
        )
    
    async def get_structured_clusters_tree(
        self,
        db: AsyncIOMotorDatabase,
        owner_id: uuid.UUID
    ) -> Dict[str, Any]:
        """
        獲取結構化的聚類樹（三層結構）
        
        Args:
            db: 數據庫連接
            owner_id: 用戶ID
        
        Returns:
            {
                "main_clusters": [...],  # 主要聚類
                "small_clusters": [...],  # 小型聚類（其他：XXX）
                "unclustered_count": int  # 未分類文檔數量
            }
        """
        # 獲取所有聚類
        cursor = db[CLUSTERS_COLLECTION].find(
            {"owner_id": owner_id}
        ).sort("document_count", -1)
        
        main_clusters = []
        small_clusters = []
        
        async for cluster_doc in cursor:
            cluster_id = cluster_doc["cluster_id"]
            
            # 動態計算實際文檔數量（從 documents 集合查詢）
            actual_document_count = await db[DOCUMENTS_COLLECTION].count_documents({
                "owner_id": owner_id,
                "cluster_info.cluster_id": cluster_id
            })
            
            cluster_summary = ClusterSummary(
                cluster_id=cluster_id,
                cluster_name=cluster_doc["cluster_name"],
                document_count=actual_document_count,  # 使用動態計算的數量
                keywords=cluster_doc.get("keywords", []),
                created_at=cluster_doc.get("created_at"),
                updated_at=cluster_doc.get("updated_at")
            )
            
            # 根據 clustering_version 或 cluster_id 判斷是主要聚類還是小型聚類
            if (cluster_doc.get("clustering_version") == "v1.0_small" or 
                "_small_" in cluster_doc["cluster_id"]):
                small_clusters.append(cluster_summary)
            else:
                main_clusters.append(cluster_summary)
        
        # 按實際文檔數量重新排序
        main_clusters.sort(key=lambda c: c.document_count, reverse=True)
        small_clusters.sort(key=lambda c: c.document_count, reverse=True)
        
        # 統計未分類文檔數量（包括 excluded 和 pending 狀態）
        unclustered_count = await db[DOCUMENTS_COLLECTION].count_documents({
            "owner_id": owner_id,
            "$or": [
                {"clustering_status": "excluded"},
                {"clustering_status": "pending"},
                {"cluster_info": None}
            ]
        })
        
        return {
            "main_clusters": [c.model_dump() for c in main_clusters],
            "small_clusters": [c.model_dump() for c in small_clusters],
            "unclustered_count": unclustered_count,
            "total_clusters": len(main_clusters) + len(small_clusters)
        }
    
    async def get_user_clusters(
        self,
        db: AsyncIOMotorDatabase,
        owner_id: uuid.UUID
    ) -> List[ClusterSummary]:
        """
        獲取用戶的所有聚類
        
        Args:
            db: 數據庫連接
            owner_id: 用戶ID
        
        Returns:
            聚類摘要列表
        """
        cursor = db[CLUSTERS_COLLECTION].find(
            {"owner_id": owner_id}
        ).sort("updated_at", -1)
        
        clusters = []
        async for cluster_doc in cursor:
            cluster_summary = ClusterSummary(
                cluster_id=cluster_doc["cluster_id"],
                cluster_name=cluster_doc["cluster_name"],
                document_count=cluster_doc["document_count"],
                keywords=cluster_doc.get("keywords", []),
                created_at=cluster_doc.get("created_at"),
                updated_at=cluster_doc.get("updated_at")
            )
            clusters.append(cluster_summary)
        
        return clusters
    
    async def get_latest_job_status(
        self,
        db: AsyncIOMotorDatabase,
        owner_id: uuid.UUID
    ) -> Optional[ClusteringJobStatus]:
        """
        獲取用戶最新的聚類任務狀態
        
        Args:
            db: 數據庫連接
            owner_id: 用戶ID
        
        Returns:
            最新的任務狀態,如果不存在則返回None
        """
        job_doc = await db[CLUSTERING_JOBS_COLLECTION].find_one(
            {"owner_id": owner_id},
            sort=[("started_at", -1)]
        )
        
        if not job_doc:
            return None
        
        return ClusteringJobStatus(**job_doc)
    
    async def get_cluster_documents(
        self,
        db: AsyncIOMotorDatabase,
        cluster_id: str,
        owner_id: uuid.UUID
    ) -> List[Document]:
        """
        獲取特定聚類中的所有文檔
        
        Args:
            db: 數據庫連接
            cluster_id: 聚類ID
            owner_id: 用戶ID (用於權限檢查)
        
        Returns:
            文檔列表
        """
        cursor = db[DOCUMENTS_COLLECTION].find({
            "owner_id": owner_id,
            "cluster_info.cluster_id": cluster_id
        }).sort("created_at", -1)
        
        documents = []
        async for doc in cursor:
            try:
                document = Document(**doc)
                documents.append(document)
            except Exception as e:
                logger.error(f"解析文檔失敗: {e}")
                continue
        
        return documents
    
    
    async def run_hierarchical_clustering(
        self,
        db: AsyncIOMotorDatabase,
        owner_id: uuid.UUID,
        force_recluster: bool = False
    ) -> ClusteringJobStatus:
        """
        執行兩級階層聚類
        
        階層1 (Level 0 - 大類):
        - 使用較大的 min_cluster_size (例如 8)
        - 生成粗粒度分類 (超商、帳單、食品等)
        
        階層2 (Level 1 - 細分類):
        - 對每個大類內部再次聚類
        - 使用較小的 min_cluster_size (例如 3)
        - 生成細粒度分類 (7-11、全家、水費、電費等)
        
        結果示例:
        超商類 (Level 0)
          ├─ 7-11收據 (Level 1)
          ├─ 全家收據 (Level 1)
          └─ 萊爾富收據 (Level 1)
        """
        if not HDBSCAN_AVAILABLE:
            raise RuntimeError("HDBSCAN庫未安裝,無法執行聚類")
        
        owner_id_str = str(owner_id)
        
        job_status = ClusteringJobStatus(
            owner_id=owner_id,
            status="running",
            started_at=datetime.utcnow()
        )
        
        try:
            await db[CLUSTERING_JOBS_COLLECTION].insert_one(job_status.model_dump())
            
            # === 階層1: 粗粒度聚類 (大類) ===
            logger.info(f"[階層聚類] 階層1開始: 粗粒度聚類")
            
            # 使用較大的 min_cluster_size 獲得大類
            original_min_cluster_size = self.min_cluster_size
            self.min_cluster_size = 8  # 增大以獲得更少但更大的聚類
            
            # 提取所有embedding
            document_ids, embeddings = await self._extract_user_embeddings(
                db, owner_id, force_recluster, include_all_vectorized=True
            )
            
            if len(document_ids) < self.min_documents_for_clustering:
                job_status.status = "completed"
                job_status.error_message = f"文檔數量不足({len(document_ids)})"
                await self._update_job_status(db, job_status)
                return job_status
            
            job_status.total_documents = len(document_ids)
            await self._update_job_status(db, job_status)
            
            # 運行粗粒度聚類
            level0_labels = self._run_hdbscan_clustering(embeddings)
            level0_clusters = self._organize_clusters(document_ids, level0_labels)
            
            logger.info(f"[階層聚類] 階層1完成: {len(level0_clusters)}個大類")
            
            # 恢復原始設置以供細粒度聚類使用
            self.min_cluster_size = original_min_cluster_size
            
            total_subclusters = 0
            
            # === 收集所有需要處理的聚類信息 ===
            # 使用批量 AI 調用來減少 API 請求次數
            
            all_clusters_to_label = {}  # {temp_idx: doc_ids} 用於批量生成標籤
            cluster_metadata = {}  # 存儲每個聚類的元數據
            temp_idx = 0
            
            # 第一步：收集所有父聚類的文檔
            for parent_cluster_idx, parent_doc_ids in level0_clusters.items():
                if parent_cluster_idx == -1:  # 跳過噪聲點
                    await self._mark_documents_as_excluded(db, parent_doc_ids)
                    continue
                
                if len(parent_doc_ids) < 8:  # 大類文檔數太少,不再細分
                    await self._mark_documents_as_excluded(db, parent_doc_ids)
                    continue
                
                parent_cluster_id = f"cluster_{owner_id_str}_L0_{parent_cluster_idx}"
                
                # 添加父聚類到批量處理
                all_clusters_to_label[temp_idx] = parent_doc_ids
                cluster_metadata[temp_idx] = {
                    "type": "parent",
                    "cluster_id": parent_cluster_id,
                    "parent_cluster_idx": parent_cluster_idx,
                    "doc_ids": parent_doc_ids
                }
                temp_idx += 1
                
                # 提取這個大類的embeddings並進行細粒度聚類
                parent_doc_id_set = set(parent_doc_ids)
                parent_indices = [i for i, doc_id in enumerate(document_ids) if doc_id in parent_doc_id_set]
                parent_embeddings = embeddings[parent_indices]
                parent_doc_ids_ordered = [document_ids[i] for i in parent_indices]
                
                # 如果文檔數量足夠,進行細粒度聚類
                if len(parent_doc_ids) >= self.min_documents_for_clustering:
                    level1_labels = self._run_hdbscan_clustering(parent_embeddings)
                    level1_clusters = self._organize_clusters(parent_doc_ids_ordered, level1_labels)
                    
                    for child_cluster_idx, child_doc_ids in level1_clusters.items():
                        if child_cluster_idx == -1 or len(child_doc_ids) < self.min_cluster_size:
                            continue
                        
                        child_cluster_id = f"cluster_{owner_id_str}_L1_{parent_cluster_idx}_{child_cluster_idx}"
                        
                        # 添加子聚類到批量處理
                        all_clusters_to_label[temp_idx] = child_doc_ids
                        cluster_metadata[temp_idx] = {
                            "type": "child",
                            "cluster_id": child_cluster_id,
                            "parent_cluster_id": parent_cluster_id,
                            "parent_cluster_idx": parent_cluster_idx,
                            "child_cluster_idx": child_cluster_idx,
                            "doc_ids": child_doc_ids
                        }
                        temp_idx += 1
            
            # 第二步：批量生成所有標籤 (一次 AI 調用!)
            if all_clusters_to_label:
                logger.info(f"[階層聚類] 批量生成 {len(all_clusters_to_label)} 個聚類的標籤")
                cluster_labels_map = await self._generate_all_cluster_labels_batch(
                    db, owner_id_str, all_clusters_to_label
                )
            else:
                cluster_labels_map = {}
            
            # 第三步：處理和保存所有聚類
            parent_subclusters = {}  # {parent_cluster_id: [subcluster_ids]}
            
            for idx, metadata in cluster_metadata.items():
                cluster_name = cluster_labels_map.get(idx, f"分類 {idx}")
                cluster_id = metadata["cluster_id"]
                doc_ids = metadata["doc_ids"]
                keywords = await self._extract_cluster_keywords(db, doc_ids)
                
                if metadata["type"] == "child":
                    # 處理子聚類
                    parent_cluster_id = metadata["parent_cluster_id"]
                    child_cluster_idx = metadata["child_cluster_idx"]
                    
                    child_cluster_info = ClusterInfo(
                        cluster_id=cluster_id,
                        cluster_name=cluster_name,
                        owner_id=owner_id,
                        document_count=len(doc_ids),
                        representative_documents=doc_ids[:10],
                        keywords=keywords,
                        clustering_version="v2.0_hierarchical",
                        parent_cluster_id=parent_cluster_id,
                        level=1
                    )
                    
                    await self._save_cluster_info(db, child_cluster_info)
                    
                    await self._update_documents_cluster_info(
                        db, doc_ids, cluster_id, cluster_name,
                        child_cluster_idx, len(doc_ids)
                    )
                    
                    # 記錄子聚類到父聚類的映射
                    if parent_cluster_id not in parent_subclusters:
                        parent_subclusters[parent_cluster_id] = []
                    parent_subclusters[parent_cluster_id].append(cluster_id)
                    total_subclusters += 1
            
            # 第四步：保存父聚類信息
            for idx, metadata in cluster_metadata.items():
                if metadata["type"] == "parent":
                    cluster_name = cluster_labels_map.get(idx, f"分類 {idx}")
                    cluster_id = metadata["cluster_id"]
                    doc_ids = metadata["doc_ids"]
                    keywords = await self._extract_cluster_keywords(db, doc_ids)
                    subcluster_ids = parent_subclusters.get(cluster_id, [])
                    
                    parent_cluster_info = ClusterInfo(
                        cluster_id=cluster_id,
                        cluster_name=cluster_name,
                        owner_id=owner_id,
                        document_count=len(doc_ids),
                        representative_documents=doc_ids[:10],
                        keywords=keywords,
                        clustering_version="v2.0_hierarchical",
                        level=0,
                        subclusters=subcluster_ids
                    )
                    
                    await self._save_cluster_info(db, parent_cluster_info)
                    
                    logger.info(f"[階層聚類] 大類 '{cluster_name}' 包含 {len(subcluster_ids)} 個子類")
            
            # 完成任務
            job_status.status = "completed"
            job_status.clusters_created = len(level0_clusters) + total_subclusters
            job_status.completed_at = datetime.utcnow()
            job_status.processed_documents = len(document_ids)
            job_status.progress_percentage = 100.0
            
            await self._update_job_status(db, job_status)
            
            logger.info(
                f"[階層聚類] 完成! 大類: {len(level0_clusters)}, "
                f"子類: {total_subclusters}, 總計: {job_status.clusters_created}"
            )
            
            return job_status
            
        except Exception as e:
            logger.error(f"[階層聚類] 失敗: {e}", exc_info=True)
            job_status.status = "failed"
            job_status.error_message = str(e)
            job_status.completed_at = datetime.utcnow()
            await self._update_job_status(db, job_status)
            raise

