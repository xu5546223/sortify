"""
建議問題的 CRUD 操作
"""

import uuid
import logging
import random
from typing import List, Optional
from datetime import datetime, timedelta
import pytz
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.suggested_question_models import (
    SuggestedQuestion,
    SuggestedQuestionsDocument
)
from app.core.logging_utils import AppLogger

logger = AppLogger(__name__, level=logging.INFO).get_logger()

COLLECTION_NAME = "suggested_questions"


async def get_user_questions(
    db: AsyncIOMotorDatabase,
    user_id: str
) -> Optional[SuggestedQuestionsDocument]:
    """
    獲取用戶的所有建議問題
    
    Args:
        db: 數據庫連接
        user_id: 用戶ID
        
    Returns:
        SuggestedQuestionsDocument: 問題文檔，如果不存在則返回 None
    """
    collection = db[COLLECTION_NAME]
    doc = await collection.find_one({"user_id": user_id})
    
    if not doc:
        logger.info(f"用戶 {user_id} 尚無建議問題")
        return None
    
    # 移除 MongoDB 的 _id
    doc.pop('_id', None)
    
    return SuggestedQuestionsDocument(**doc)


async def get_random_questions(
    db: AsyncIOMotorDatabase,
    user_id: str,
    count: int = 4,
    exclude_recently_used: bool = True,
    recent_use_days: int = 7
) -> List[SuggestedQuestion]:
    """
    獲取隨機的建議問題（不重複）
    
    Args:
        db: 數據庫連接
        user_id: 用戶ID
        count: 需要的問題數量
        exclude_recently_used: 是否排除最近使用過的問題
        recent_use_days: 最近使用的天數定義
        
    Returns:
        List[SuggestedQuestion]: 隨機選擇的問題列表
    """
    questions_doc = await get_user_questions(db, user_id)
    
    if not questions_doc or not questions_doc.questions:
        logger.warning(f"用戶 {user_id} 沒有可用的建議問題")
        return []
    
    available_questions = questions_doc.questions
    
    # 如果需要排除最近使用的問題
    if exclude_recently_used:
        from datetime import timedelta
        cutoff_time = datetime.now(UTC) - timedelta(days=recent_use_days)
        available_questions = [
            q for q in available_questions
            if q.last_used_at is None or q.last_used_at < cutoff_time
        ]
        
        # 如果過濾後沒有足夠的問題，使用所有問題
        if len(available_questions) < count:
            logger.info(f"過濾後問題不足，使用所有問題")
            available_questions = questions_doc.questions
    
    # 隨機選擇
    selected_count = min(count, len(available_questions))
    selected_questions = random.sample(available_questions, selected_count)
    
    logger.info(f"為用戶 {user_id} 選擇了 {len(selected_questions)} 個建議問題")
    
    return selected_questions


async def save_user_questions(
    db: AsyncIOMotorDatabase,
    user_id: str,
    questions: List[SuggestedQuestion],
    total_documents: int
) -> bool:
    """
    保存用戶的建議問題
    
    Args:
        db: 數據庫連接
        user_id: 用戶ID
        questions: 問題列表
        total_documents: 文檔總數
        
    Returns:
        bool: 是否成功
    """
    collection = db[COLLECTION_NAME]
    
    questions_doc = SuggestedQuestionsDocument(
        user_id=user_id,
        questions=questions,
        last_generated=datetime.now(UTC),
        total_documents=total_documents,
        version=1
    )
    
    # Upsert 操作
    result = await collection.update_one(
        {"user_id": user_id},
        {"$set": questions_doc.model_dump()},
        upsert=True
    )
    
    success = result.acknowledged
    
    if success:
        logger.info(f"成功保存用戶 {user_id} 的 {len(questions)} 個建議問題")
    else:
        logger.error(f"保存用戶 {user_id} 的建議問題失敗")
    
    return success


async def mark_question_used(
    db: AsyncIOMotorDatabase,
    user_id: str,
    question_id: str
) -> bool:
    """
    標記問題已被使用
    
    Args:
        db: 數據庫連接
        user_id: 用戶ID
        question_id: 問題ID
        
    Returns:
        bool: 是否成功
    """
    collection = db[COLLECTION_NAME]
    
    result = await collection.update_one(
        {
            "user_id": user_id,
            "questions.id": question_id
        },
        {
            "$set": {
                "questions.$.last_used_at": datetime.now(UTC)
            },
            "$inc": {
                "questions.$.use_count": 1
            }
        }
    )
    
    if result.modified_count > 0:
        logger.info(f"標記問題 {question_id} 已使用")
        return True
    else:
        logger.warning(f"未找到問題 {question_id} 或更新失敗")
        return False


async def delete_user_questions(
    db: AsyncIOMotorDatabase,
    user_id: str
) -> bool:
    """
    刪除用戶的所有建議問題
    
    Args:
        db: 數據庫連接
        user_id: 用戶ID
        
    Returns:
        bool: 是否成功
    """
    collection = db[COLLECTION_NAME]
    
    result = await collection.delete_one({"user_id": user_id})
    
    if result.deleted_count > 0:
        logger.info(f"刪除用戶 {user_id} 的建議問題")
        return True
    else:
        logger.warning(f"用戶 {user_id} 沒有建議問題可刪除")
        return False


async def should_regenerate_questions(
    db: AsyncIOMotorDatabase,
    user_id: str,
    current_doc_count: int
) -> bool:
    """
    判斷是否需要重新生成問題
    
    條件：
    1. 沒有問題記錄
    2. 文檔數量增加了 20% 以上
    3. 超過 30 天沒有更新
    
    Args:
        db: 數據庫連接
        user_id: 用戶ID
        current_doc_count: 當前文檔數量
        
    Returns:
        bool: 是否需要重新生成
    """
    questions_doc = await get_user_questions(db, user_id)
    
    if not questions_doc:
        logger.info(f"用戶 {user_id} 沒有問題記錄，需要生成")
        return True
    
    # 檢查文檔數量變化
    if questions_doc.total_documents == 0:
        doc_increase_ratio = 1.0
    else:
        doc_increase_ratio = current_doc_count / questions_doc.total_documents
    
    if doc_increase_ratio >= 1.2:
        logger.info(f"用戶 {user_id} 文檔數量增加了 {(doc_increase_ratio - 1) * 100:.1f}%，需要重新生成")
        return True
    
    # 檢查時間
    from datetime import timedelta
    days_since_last_gen = (datetime.now(UTC) - questions_doc.last_generated).days
    if days_since_last_gen > 30:
        logger.info(f"用戶 {user_id} 已 {days_since_last_gen} 天未更新問題，需要重新生成")
        return True
    
    logger.info(f"用戶 {user_id} 的問題庫仍然有效")
    return False

