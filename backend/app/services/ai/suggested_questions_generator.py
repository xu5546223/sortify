"""
基於用戶文檔和聚類信息生成建議問題的服務
使用統一的 AI 調用邏輯確保配置一致
"""

import uuid
import logging
import json
import random
from typing import List, Dict, Any, Optional, Callable, Awaitable
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.logging_utils import AppLogger
from app.services.ai.unified_ai_service_simplified import unified_ai_service_simplified
from app.services.ai.unified_ai_config import TaskType
from app.services.external.clustering_service import ClusteringService
from app.crud import crud_documents, crud_suggested_questions
from app.models.suggested_question_models import (
    SuggestedQuestion,
    QuestionType,
    AIGeneratedQuestionsOutput
)

logger = AppLogger(__name__, level=logging.INFO).get_logger()


class SuggestedQuestionsGenerator:
    """
    建議問題生成器
    
    基於以下信息生成問題：
    1. 文檔聚類信息（從 clustering_service 獲取）
    2. 文檔摘要和關鍵信息
    3. 文檔元數據（上傳時間、類型等）
    
    生成策略：
    - 每個分類生成 N 個問題
    - 生成跨分類的綜合問題
    - 生成時間相關的問題
    """
    
    def __init__(self):
        self.ai_service = unified_ai_service_simplified
        self.clustering_service = ClusteringService()
    
    async def generate_questions_for_user(
        self,
        db: AsyncIOMotorDatabase,
        user_id: str,
        questions_per_category: int = 5,
        include_cross_category: bool = True,
        force_regenerate: bool = False,
        progress_callback: Optional[Callable[[int, str, int], Awaitable[None]]] = None
    ) -> List[SuggestedQuestion]:
        """
        為用戶生成建議問題
        
        Args:
            db: 數據庫連接
            user_id: 用戶ID
            questions_per_category: 每個分類生成的問題數量
            include_cross_category: 是否包含跨分類問題
            force_regenerate: 是否強制重新生成
            
        Returns:
            List[SuggestedQuestion]: 生成的問題列表
        """
        logger.info(f"開始為用戶 {user_id} 生成建議問題")
        
        # 1. 檢查是否需要生成
        if not force_regenerate:
            # 使用 UUID 轉換
            from uuid import UUID
            owner_uuid = UUID(user_id)
            documents = await crud_documents.get_documents(db, owner_id=owner_uuid, limit=10000)
            doc_count = len(documents)
            should_gen = await crud_suggested_questions.should_regenerate_questions(
                db, user_id, doc_count
            )
            
            if not should_gen:
                logger.info(f"用戶 {user_id} 的問題庫仍然有效，跳過生成")
                existing_questions = await crud_suggested_questions.get_user_questions(db, user_id)
                return existing_questions.questions if existing_questions else []
        
        # 2. 獲取用戶的文檔和聚類信息
        clusters = await self._get_user_clusters(db, user_id)
        
        if not clusters:
            logger.warning(f"用戶 {user_id} 沒有聚類信息，無法生成問題")
            return []
        
        # 使用 UUID 轉換
        from uuid import UUID
        owner_uuid = UUID(user_id)
        documents = await crud_documents.get_documents(db, owner_id=owner_uuid, limit=10000)
        
        if len(documents) < 3:
            logger.warning(f"用戶 {user_id} 文檔數量不足（{len(documents)}），無法生成有意義的問題")
            return []
        
        # 3. 為每個聚類生成問題（並發執行）
        all_questions = []
        total_clusters = len(clusters)
        
        # 使用信號量控制並發數量（每分鐘最多 5 個請求）
        import asyncio
        semaphore = asyncio.Semaphore(5)  # 最多 5 個並發
        completed_count = 0
        
        async def generate_with_semaphore(idx: int, cluster: Dict[str, Any]):
            nonlocal completed_count
            async with semaphore:
                logger.info(f"為聚類 '{cluster['cluster_name']}' 生成問題...")
                
                # 更新進度（total_clusters + 1 是因為還有時間相關問題）
                if progress_callback:
                    progress = int(completed_count / (total_clusters + 1) * 100)
                    await progress_callback(progress, f"正在為聚類「{cluster['cluster_name']}」生成問題...", completed_count)
                
                cluster_questions = await self._generate_questions_for_cluster(
                    db=db,
                    user_id=user_id,
                    cluster=cluster,
                    documents=documents,
                    count=questions_per_category
                )
                
                completed_count += 1
                
                # 更新進度
                if progress_callback:
                    progress = int(completed_count / (total_clusters + 1) * 100)
                    await progress_callback(progress, f"已完成 {completed_count}/{total_clusters} 個聚類", completed_count)
                
                logger.info(f"聚類 '{cluster['cluster_name']}' 生成了 {len(cluster_questions)} 個問題")
                
                # 為了避免超過 API 限制，每個請求完成後等待 12 秒（5 requests/min = 12s/request）
                await asyncio.sleep(12)
                
                return cluster_questions
        
        # 並發執行所有聚類的問題生成
        tasks = [generate_with_semaphore(idx, cluster) for idx, cluster in enumerate(clusters, 1)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 收集結果
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"生成聚類問題時發生錯誤: {result}")
            elif isinstance(result, list):
                all_questions.extend(result)
        
        # 4. 跨分類問題已停用
        # if include_cross_category and len(clusters) > 1:
        #     logger.info("生成跨分類問題...")
        #     ...
        
        # 5. 生成時間相關問題
        if progress_callback:
            progress = int(total_clusters / (total_clusters + 1) * 100)
            await progress_callback(progress, "正在生成時間相關問題...", total_clusters)
        
        time_questions = await self._generate_time_based_questions(
            documents=documents,
            count=3
        )
        
        all_questions.extend(time_questions)
        
        logger.info(f"生成了 {len(time_questions)} 個時間相關問題")
        
        # 6. 保存到數據庫
        if progress_callback:
            await progress_callback(95, "正在保存問題到數據庫...", total_clusters + 1)
        
        success = await crud_suggested_questions.save_user_questions(
            db=db,
            user_id=user_id,
            questions=all_questions,
            total_documents=len(documents)
        )
        
        if success:
            logger.info(f"✅ 成功為用戶 {user_id} 生成並保存了 {len(all_questions)} 個建議問題")
        else:
            logger.error(f"❌ 保存問題失敗")
        
        if progress_callback:
            await progress_callback(100, "問題生成完成！", total_clusters + 1)
        
        return all_questions
    
    async def _get_user_clusters(
        self,
        db: AsyncIOMotorDatabase,
        user_id: str
    ) -> List[Dict[str, Any]]:
        """
        獲取用戶的聚類信息
        
        Returns:
            List[Dict]: 聚類信息列表
            [
                {
                    "cluster_id": "...",
                    "cluster_name": "財務報表",
                    "document_ids": ["doc1", "doc2"],
                    "summary": "..."
                }
            ]
        """
        try:
            from uuid import UUID
            
            # 從 clusters 集合獲取用戶的聚類信息
            clusters_collection = db["clusters"]
            
            # 嘗試兩種查詢方式：UUID 和字符串
            owner_uuid = UUID(user_id)
            
            # 先嘗試使用 UUID 查詢
            cursor = clusters_collection.find({"owner_id": owner_uuid})
            clusters = await cursor.to_list(length=100)
            
            # 如果沒有結果，嘗試使用字符串查詢
            if not clusters:
                logger.info(f"使用 UUID 查詢無結果，嘗試使用字符串查詢")
                cursor = clusters_collection.find({"owner_id": user_id})
                clusters = await cursor.to_list(length=100)
            
            result = []
            for cluster in clusters:
                # 獲取文檔 IDs - 可能存儲在不同的字段中
                doc_ids = (
                    cluster.get("document_ids", []) or 
                    cluster.get("representative_documents", []) or
                    []
                )
                
                result.append({
                    "cluster_id": str(cluster.get("_id", cluster.get("cluster_id", ""))),
                    "cluster_name": cluster.get("cluster_name", "未命名分類"),
                    "document_ids": doc_ids,
                    "summary": cluster.get("summary", "")
                })
            
            logger.info(f"獲取到 {len(result)} 個聚類（用戶: {user_id}）")
            if result:
                logger.info(f"聚類名稱列表: {[c['cluster_name'] for c in result]}")
                logger.debug(f"聚類示例: {result[0] if result else 'None'}")
            return result
            
        except Exception as e:
            logger.error(f"獲取聚類信息失敗: {e}", exc_info=True)
            return []
    
    async def _generate_questions_for_cluster(
        self,
        db: AsyncIOMotorDatabase,
        user_id: str,
        cluster: Dict[str, Any],
        documents: List[Any],
        count: int
    ) -> List[SuggestedQuestion]:
        """
        為單個聚類生成問題
        """
        cluster_name = cluster["cluster_name"]
        cluster_doc_ids = cluster["document_ids"]
        
        # 獲取該聚類的文檔摘要
        cluster_docs = [doc for doc in documents if str(doc.id) in cluster_doc_ids]
        
        if not cluster_docs:
            logger.warning(f"聚類 '{cluster_name}' 沒有有效文檔")
            return []
        
        # 隨機選擇最多 10 個文檔（如果文檔數量少於10個，則全部使用）
        selected_docs = random.sample(cluster_docs, min(10, len(cluster_docs)))
        
        # 準備文檔摘要信息
        docs_info = []
        for doc in selected_docs:
            summary = ""
            if doc.analysis and doc.analysis.ai_analysis_output:
                key_info = doc.analysis.ai_analysis_output.get("key_information", {})
                summary = key_info.get("content_summary", "")[:200]
            
            docs_info.append({
                "filename": doc.filename,
                "file_type": doc.file_type,
                "summary": summary
            })
        
        logger.debug(f"從 {len(cluster_docs)} 個文檔中隨機選擇了 {len(selected_docs)} 個文檔用於生成問題")
        
        # 構建問題生成的數據內容
        docs_text = "\n".join([
            f"- {doc['filename']} ({doc['file_type']}): {doc['summary']}"
            for doc in docs_info
        ])
        
        prompt_content = f"""請基於以下文檔聚類信息，生成 {count} 個用戶可能會問的問題。

聚類名稱：{cluster_name}

包含的文檔：
{docs_text}

要求：
1. 問題應該自然、實用、有針對性
2. 涵蓋不同類型：總結、比較、分析、詳細查詢
3. 問題應該基於實際文檔內容
4. 使用繁體中文
"""
        
        try:
            # 使用統一 AI 服務生成問題
            from app.services.ai.unified_ai_service_simplified import AIRequest
            
            request = AIRequest(
                task_type=TaskType.QUESTION_GENERATION,
                content=prompt_content,
                model_preference=None,
                user_id=user_id,
                prompt_params={"prompt_content": prompt_content}
            )
            
            response = await self.ai_service.process_request(request, db)
            
            if not response.success:
                logger.error(f"AI 生成問題失敗: {response.error_message}")
                return []
            
            # 解析 AI 輸出
            ai_output = response.output_data
            
            # 如果 output_data 是字符串，需要先解析 JSON
            if isinstance(ai_output, str):
                import json
                try:
                    ai_output_dict = json.loads(ai_output)
                    ai_output = AIGeneratedQuestionsOutput(**ai_output_dict)
                except Exception as parse_error:
                    logger.error(f"解析 AI 輸出 JSON 失敗: {parse_error}, 原始輸出: {ai_output[:200]}")
                    return []
            elif isinstance(ai_output, dict):
                ai_output = AIGeneratedQuestionsOutput(**ai_output)
            elif not isinstance(ai_output, AIGeneratedQuestionsOutput):
                logger.error(f"AI 輸出類型錯誤: {type(ai_output)}")
                return []
            
            # 轉換為 SuggestedQuestion 對象
            questions = []
            for q_data in ai_output.questions:
                question = SuggestedQuestion(
                    id=str(uuid.uuid4()),
                    question=q_data["question"],
                    category=cluster_name,
                    category_id=cluster["cluster_id"],
                    related_documents=[str(doc.id) for doc in cluster_docs],
                    is_cross_category=False,
                    question_type=self._parse_question_type(q_data.get("question_type", "summary")),
                    created_at=datetime.utcnow()
                )
                questions.append(question)
            
            return questions
            
        except Exception as e:
            logger.error(f"生成聚類問題時發生錯誤: {e}", exc_info=True)
            return []
    
    async def _generate_cross_category_questions(
        self,
        db: AsyncIOMotorDatabase,
        clusters: List[Dict[str, Any]],
        documents: List[Any],
        count: int
    ) -> List[SuggestedQuestion]:
        """
        生成跨分類問題
        """
        # 準備聚類摘要
        clusters_text = "\n".join([
            f"- {cluster['cluster_name']} ({len(cluster['document_ids'])} 個文檔)"
            for cluster in clusters
        ])
        
        # 構建問題生成的數據內容
        prompt_content = f"""請基於以下多個文檔分類，生成 {count} 個跨分類的綜合性問題。

文檔分類：
{clusters_text}

要求：
1. 問題應該涉及多個分類之間的關聯
2. 問題應該綜合性強、有深度
3. 適合進行跨領域分析
4. 使用繁體中文
"""
        
        try:
            from app.services.ai.unified_ai_service_simplified import AIRequest
            
            request = AIRequest(
                task_type=TaskType.QUESTION_GENERATION,
                content=prompt_content,
                model_preference=None,
                prompt_params={"prompt_content": prompt_content}
            )
            
            response = await self.ai_service.process_request(request, db)
            
            if not response.success:
                logger.error(f"AI 生成跨分類問題失敗: {response.error_message}")
                return []
            
            # 解析 AI 輸出
            ai_output = response.output_data
            
            # 如果 output_data 是字符串，需要先解析 JSON
            if isinstance(ai_output, str):
                import json
                try:
                    ai_output_dict = json.loads(ai_output)
                    ai_output = AIGeneratedQuestionsOutput(**ai_output_dict)
                except Exception as parse_error:
                    logger.error(f"解析跨分類 AI 輸出 JSON 失敗: {parse_error}, 原始輸出: {ai_output[:200]}")
                    return []
            elif isinstance(ai_output, dict):
                ai_output = AIGeneratedQuestionsOutput(**ai_output)
            elif not isinstance(ai_output, AIGeneratedQuestionsOutput):
                logger.error(f"跨分類 AI 輸出類型錯誤: {type(ai_output)}")
                return []
            
            questions = []
            for q_data in ai_output.questions:
                question = SuggestedQuestion(
                    id=str(uuid.uuid4()),
                    question=q_data["question"],
                    category=None,
                    category_id=None,
                    related_documents=[str(doc.id) for doc in documents],
                    is_cross_category=True,
                    question_type=QuestionType.CROSS_CATEGORY,
                    created_at=datetime.utcnow()
                )
                questions.append(question)
            
            return questions
            
        except Exception as e:
            logger.error(f"生成跨分類問題時發生錯誤: {e}", exc_info=True)
            return []
    
    async def _generate_time_based_questions(
        self,
        documents: List[Any],
        count: int
    ) -> List[SuggestedQuestion]:
        """
        生成時間相關問題（基於文檔上傳時間）
        """
        questions = []
        
        # 預定義的時間相關問題模板
        time_templates = [
            "幫我總結最近上傳的文件",
            "最近更新的文件有哪些重要信息？",
            "比較最近一週和上個月的文件有什麼變化",
            "最新的文件提到了哪些重要事項？",
        ]
        
        for i, template in enumerate(time_templates[:count]):
            question = SuggestedQuestion(
                id=str(uuid.uuid4()),
                question=template,
                category=None,
                category_id=None,
                related_documents=[str(doc.id) for doc in documents],
                is_cross_category=False,
                question_type=QuestionType.TIME_BASED,
                created_at=datetime.utcnow()
            )
            questions.append(question)
        
        return questions
    
    
    def _parse_question_type(self, type_str: str) -> QuestionType:
        """解析問題類型"""
        type_mapping = {
            "summary": QuestionType.SUMMARY,
            "comparison": QuestionType.COMPARISON,
            "analysis": QuestionType.ANALYSIS,
            "time_based": QuestionType.TIME_BASED,
            "detail_query": QuestionType.DETAIL_QUERY,
            "cross_category": QuestionType.CROSS_CATEGORY
        }
        
        return type_mapping.get(type_str.lower(), QuestionType.SUMMARY)


# 全局實例
suggested_questions_generator = SuggestedQuestionsGenerator()

