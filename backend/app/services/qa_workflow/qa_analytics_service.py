"""
QA問答統計分析服務

記錄和分析問答系統的性能指標
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.logging_utils import AppLogger
from app.models.question_models import QuestionClassification

logger = AppLogger(__name__, level=logging.DEBUG).get_logger()


class QAAnalyticsService:
    """問答統計分析服務"""
    
    def __init__(self):
        self.collection_name = "qa_analytics"
        logger.info("QA Analytics Service 初始化完成")
    
    async def log_qa_request(
        self,
        db: AsyncIOMotorDatabase,
        question: str,
        classification: QuestionClassification,
        processing_time: float,
        api_calls: int,
        strategy_used: str,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        tokens_used: int = 0,
        success: bool = True,
        error_message: Optional[str] = None
    ):
        """
        記錄單次問答請求的統計信息
        
        Args:
            db: 數據庫連接
            question: 用戶問題
            classification: 問題分類結果
            processing_time: 處理時間(秒)
            api_calls: API調用次數
            strategy_used: 使用的策略
            user_id: 用戶ID
            conversation_id: 對話ID
            tokens_used: 使用的Token數
            success: 是否成功
            error_message: 錯誤信息
        """
        try:
            record = {
                "question": question[:200],  # 限制長度
                "question_length": len(question),
                "classification": {
                    "intent": classification.intent,  # 已經是字符串,不需要 .value
                    "confidence": classification.confidence,
                    "strategy": classification.suggested_strategy,
                    "complexity": classification.query_complexity
                },
                "performance": {
                    "processing_time": processing_time,
                    "api_calls": api_calls,
                    "tokens_used": tokens_used,
                    "strategy_used": strategy_used
                },
                "user_id": user_id,
                "conversation_id": conversation_id,
                "success": success,
                "error_message": error_message,
                "created_at": datetime.utcnow()
            }
            
            await db[self.collection_name].insert_one(record)
            
            logger.debug(f"QA統計記錄已保存: intent={classification.intent}, time={processing_time:.2f}s")
            
        except Exception as e:
            logger.error(f"保存QA統計失敗: {e}", exc_info=True)
    
    async def get_statistics(
        self,
        db: AsyncIOMotorDatabase,
        user_id: Optional[str] = None,
        time_range: str = "24h",
        intent_filter: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        獲取問答統計數據
        
        Args:
            db: 數據庫連接
            user_id: 用戶ID(可選,用於獲取特定用戶統計)
            time_range: 時間範圍 (24h, 7d, 30d, all)
            intent_filter: 意圖類型過濾
            
        Returns:
            Dict: 統計數據
        """
        try:
            # 構建時間過濾器
            time_filter = {}
            if time_range != "all":
                hours_map = {"24h": 24, "7d": 24 * 7, "30d": 24 * 30}
                hours = hours_map.get(time_range, 24)
                cutoff_time = datetime.utcnow() - timedelta(hours=hours)
                time_filter["created_at"] = {"$gte": cutoff_time}
            
            # 構建查詢過濾器
            query_filter = {**time_filter}
            if user_id:
                query_filter["user_id"] = user_id
            if intent_filter:
                query_filter["classification.intent"] = intent_filter
            
            # 獲取總數
            total_questions = await db[self.collection_name].count_documents(query_filter)
            
            if total_questions == 0:
                return {
                    "total_questions": 0,
                    "time_range": time_range,
                    "by_intent": {},
                    "avg_api_calls": 0,
                    "avg_response_time": 0,
                    "success_rate": 0,
                    "cost_metrics": {}
                }
            
            # 按意圖統計
            intent_pipeline = [
                {"$match": query_filter},
                {
                    "$group": {
                        "_id": "$classification.intent",
                        "count": {"$sum": 1},
                        "avg_confidence": {"$avg": "$classification.confidence"},
                        "avg_api_calls": {"$avg": "$performance.api_calls"},
                        "avg_time": {"$avg": "$performance.processing_time"}
                    }
                }
            ]
            intent_stats = await db[self.collection_name].aggregate(intent_pipeline).to_list(None)
            
            by_intent = {}
            for stat in intent_stats:
                by_intent[stat["_id"]] = {
                    "count": stat["count"],
                    "avg_confidence": round(stat["avg_confidence"], 2),
                    "avg_api_calls": round(stat["avg_api_calls"], 1),
                    "avg_time": round(stat["avg_time"], 2)
                }
            
            # 計算整體指標
            overall_pipeline = [
                {"$match": query_filter},
                {
                    "$group": {
                        "_id": None,
                        "avg_api_calls": {"$avg": "$performance.api_calls"},
                        "avg_response_time": {"$avg": "$performance.processing_time"},
                        "total_tokens": {"$sum": "$performance.tokens_used"},
                        "success_count": {
                            "$sum": {"$cond": ["$success", 1, 0]}
                        }
                    }
                }
            ]
            overall_stats = await db[self.collection_name].aggregate(overall_pipeline).to_list(None)
            
            if overall_stats:
                stats = overall_stats[0]
                avg_api_calls = round(stats["avg_api_calls"], 2)
                avg_response_time = round(stats["avg_response_time"], 2)
                success_rate = round((stats["success_count"] / total_questions) * 100, 1)
                total_tokens = stats["total_tokens"]
            else:
                avg_api_calls = 0
                avg_response_time = 0
                success_rate = 0
                total_tokens = 0
            
            # 計算成本節省(相對於基線)
            baseline_api_calls = 4.5  # 舊系統的平均值
            cost_saved_percentage = 0
            if avg_api_calls > 0:
                cost_saved_percentage = round(
                    ((baseline_api_calls - avg_api_calls) / baseline_api_calls) * 100,
                    1
                )
            
            return {
                "total_questions": total_questions,
                "time_range": time_range,
                "by_intent": by_intent,
                "avg_api_calls": avg_api_calls,
                "avg_response_time": avg_response_time,
                "success_rate": success_rate,
                "cost_metrics": {
                    "total_tokens": total_tokens,
                    "avg_tokens_per_question": round(total_tokens / total_questions, 0) if total_questions > 0 else 0,
                    "cost_saved_percentage": cost_saved_percentage,
                    "baseline_comparison": {
                        "old_avg_api_calls": baseline_api_calls,
                        "new_avg_api_calls": avg_api_calls,
                        "improvement": f"{cost_saved_percentage}%"
                    }
                }
            }
            
        except Exception as e:
            logger.error(f"獲取QA統計失敗: {e}", exc_info=True)
            return {
                "error": str(e),
                "total_questions": 0
            }
    
    async def get_performance_trends(
        self,
        db: AsyncIOMotorDatabase,
        user_id: Optional[str] = None,
        days: int = 7
    ) -> Dict[str, Any]:
        """
        獲取性能趨勢數據
        
        Args:
            db: 數據庫連接
            user_id: 用戶ID
            days: 天數
            
        Returns:
            Dict: 趨勢數據
        """
        try:
            cutoff_time = datetime.utcnow() - timedelta(days=days)
            query_filter = {"created_at": {"$gte": cutoff_time}}
            
            if user_id:
                query_filter["user_id"] = user_id
            
            # 按天統計
            daily_pipeline = [
                {"$match": query_filter},
                {
                    "$group": {
                        "_id": {
                            "$dateToString": {
                                "format": "%Y-%m-%d",
                                "date": "$created_at"
                            }
                        },
                        "questions": {"$sum": 1},
                        "avg_api_calls": {"$avg": "$performance.api_calls"},
                        "avg_time": {"$avg": "$performance.processing_time"}
                    }
                },
                {"$sort": {"_id": 1}}
            ]
            
            daily_stats = await db[self.collection_name].aggregate(daily_pipeline).to_list(None)
            
            trends = {
                "daily_stats": [
                    {
                        "date": stat["_id"],
                        "questions": stat["questions"],
                        "avg_api_calls": round(stat["avg_api_calls"], 2),
                        "avg_time": round(stat["avg_time"], 2)
                    }
                    for stat in daily_stats
                ],
                "period": f"{days} days",
                "total_days": len(daily_stats)
            }
            
            return trends
            
        except Exception as e:
            logger.error(f"獲取性能趨勢失敗: {e}", exc_info=True)
            return {"error": str(e)}


# 創建全局實例
qa_analytics_service = QAAnalyticsService()

