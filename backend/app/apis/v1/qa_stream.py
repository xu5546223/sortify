"""
流式問答 API 端點 - 重構版本

✅ 代碼從 715 行減少到 ~150 行
✅ 邏輯統一到 qa_orchestrator
✅ 保持所有事件格式一致
✅ 保持真實流式輸出
"""
import logging
import json
import asyncio
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import Optional, AsyncGenerator

from app.dependencies import get_db
from app.models.user_models import User
from app.core.security import get_current_active_user
from app.models.vector_models import AIQARequest
from app.core.logging_utils import AppLogger, log_event, LogLevel
from app.services.qa_orchestrator import qa_orchestrator

router = APIRouter()
logger = AppLogger(__name__, level=logging.DEBUG).get_logger()


async def generate_streaming_answer(
    db: AsyncIOMotorDatabase,
    request: AIQARequest,
    user_id: str
) -> AsyncGenerator[str, None]:
    """
    流式生成答案的核心邏輯 - 統一調用 qa_orchestrator
    
    ✅ 重構後：調用 qa_orchestrator.process_qa_request_intelligent_stream()
    ✅ 保持所有事件格式一致（progress, chunk, metadata, complete, error, approval_needed）
    ✅ 保持真實流式輸出（使用 generate_answer_stream）
    ✅ 代碼從 650+ 行減少到 ~20 行
    """
    try:
        logger.info(f"🚀 [Stream QA] 開始處理問題: {request.question[:50]}...")
        
        # 調用統一的流式編排器
        async for event in qa_orchestrator.process_qa_request_intelligent_stream(
            db=db,
            request=request,
            user_id=user_id,
            request_id=None
        ):
            # 轉換為 SSE 格式並立即發送（不緩衝）
            sse_data = event.to_sse()
            logger.debug(f"📤 [Stream] 發送事件: type={event.type}")
            yield sse_data
            # 確保立即刷新，不等待緩衝區滿
            await asyncio.sleep(0)
        
        logger.info(f"✅ [Stream QA] 流式處理完成")
        
    except Exception as e:
        logger.error(f"❌ [Stream QA] 流式處理失敗: {e}", exc_info=True)
        error_event = {'type': 'error', 'message': str(e)}
        yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"


@router.post("/qa/stream")
async def stream_qa(
    request: AIQARequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    流式問答端點 - 實時發送每個處理步驟的進度
    
    返回 Server-Sent Events (SSE) 流
    
    事件類型：
    - progress: 處理進度（動態，只有實際執行的步驟才發送）
    - chunk: 答案文本塊
    - approval_needed: 需要用戶批准
    - complete: 完整答案（對於不需要流式的簡短回答）
    - metadata: 元數據信息
    - error: 錯誤信息
    """
    logger.info(f"📨 [Stream API] 收到流式問答請求: user={current_user.username}, question={request.question[:50]}")
    
    try:
        return StreamingResponse(
            generate_streaming_answer(db, request, str(current_user.id)),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # 禁用 Nginx 緩衝
            }
        )
    except Exception as e:
        logger.error(f"❌ [Stream API] 創建流式響應失敗: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"創建流式響應失敗: {str(e)}")
