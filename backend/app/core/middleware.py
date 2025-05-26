import time
import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

class RequestContextLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # 獲取或生成 request_id
        request_id = request.headers.get("X-Request-ID")
        if not request_id:
            request_id = str(uuid.uuid4())
        
        # 將 request_id 儲存到 request.state 以便在應用程式中訪問
        # request.state 是每個請求的臨時存儲區域
        request.state.request_id = request_id

        # 記錄請求開始時間
        start_time = time.time()

        # 在響應頭中設定 X-Request-ID
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id

        # 計算處理時間
        process_time = (time.time() - start_time) * 1000  # 毫秒
        response.headers["X-Process-Time-Ms"] = f"{process_time:.2f}"

        # 此處也可以添加基本的請求日誌記錄，但我們主要使用 log_event
        # print(f"Request: {request.method} {request.url.path} - ID: {request_id} - Status: {response.status_code} - Time: {process_time:.2f}ms")
        
        return response 