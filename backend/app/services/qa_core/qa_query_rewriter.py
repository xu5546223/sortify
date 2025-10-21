"""
QA查詢重寫服務

處理查詢優化和重寫
使用統一 AI 接口
"""
import logging
from typing import Tuple, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.logging_utils import AppLogger
from app.models.vector_models import QueryRewriteResult
from app.models.ai_models_simplified import AIQueryRewriteOutput
from app.services.ai.unified_ai_service_simplified import unified_ai_service_simplified

logger = AppLogger(__name__, level=logging.DEBUG).get_logger()


class QAQueryRewriter:
    """查詢重寫服務"""
    
    async def rewrite_query(
        self,
        db: AsyncIOMotorDatabase,
        original_query: str,
        user_id: Optional[str] = None,
        request_id: Optional[str] = None,
        query_rewrite_count: int = 3
    ) -> Tuple[QueryRewriteResult, int]:
        """
        重寫查詢以提升搜索效果
        
        Args:
            db: 數據庫連接
            original_query: 原始查詢
            user_id: 用戶ID
            request_id: 請求ID
            query_rewrite_count: 重寫查詢數量
            
        Returns:
            Tuple[QueryRewriteResult, tokens_used]
        """
        logger.info(f"查詢重寫: '{original_query[:50]}...'")
        
        # 調用統一 AI 服務
        ai_response = await unified_ai_service_simplified.rewrite_query(
            original_query=original_query,
            db=db
        )
        
        tokens = ai_response.token_usage.total_tokens if ai_response.token_usage else 0
        
        if ai_response.success and ai_response.output_data:
            # 解析新格式
            if isinstance(ai_response.output_data, AIQueryRewriteOutput):
                output = ai_response.output_data
                
                logger.info(f"🧠 AI意圖分析: {output.reasoning}")
                logger.info(f"📊 問題粒度: {output.query_granularity}")
                logger.info(f"🎯 建議策略: {output.search_strategy_suggestion}")
                logger.info(f"📝 重寫查詢數: {len(output.rewritten_queries)}")
                
                return QueryRewriteResult(
                    original_query=original_query,
                    rewritten_queries=output.rewritten_queries,
                    extracted_parameters=output.extracted_parameters,
                    intent_analysis=output.intent_analysis,
                    query_granularity=output.query_granularity,
                    search_strategy_suggestion=output.search_strategy_suggestion,
                    reasoning=output.reasoning
                ), tokens
            
            # 向後兼容舊格式
            elif hasattr(ai_response.output_data, 'rewritten_queries'):
                output = ai_response.output_data
                logger.warning("使用舊版查詢重寫格式")
                
                return QueryRewriteResult(
                    original_query=original_query,
                    rewritten_queries=output.rewritten_queries if hasattr(output, 'rewritten_queries') else [original_query],
                    extracted_parameters=output.extracted_parameters if hasattr(output, 'extracted_parameters') else {},
                    intent_analysis=output.intent_analysis if hasattr(output, 'intent_analysis') else "舊格式"
                ), tokens
        
        # 失敗回退
        logger.error("查詢重寫失敗,使用原始查詢")
        return QueryRewriteResult(
            original_query=original_query,
            rewritten_queries=[original_query],
            extracted_parameters={},
            intent_analysis="查詢重寫失敗"
        ), tokens


# 創建全局實例
qa_query_rewriter = QAQueryRewriter()

