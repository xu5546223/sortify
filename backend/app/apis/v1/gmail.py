import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Request, BackgroundTasks
from motor.motor_asyncio import AsyncIOMotorDatabase
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
import json
from datetime import datetime
import asyncio

from app.db.mongodb_utils import get_db
from app.core.security import get_current_active_user
from app.models.user_models import User
from app.models.email_models import (
    GmailMessagePreview,
    EmailImportResponse,
    BatchEmailImportRequest,
    BatchEmailImportResponse,
    EmailSource
)
from app.models.document_models import DocumentStatus
from app.services.gmail_service import GmailService
from app.services.email_document_processor import EmailDocumentProcessor
from app.crud.crud_users import crud_users
from app.crud import crud_documents
from app.core.logging_utils import AppLogger, log_event, LogLevel
from app.core.config import settings

logger = AppLogger(__name__, level=logging.DEBUG).get_logger()

router = APIRouter(tags=["Gmail"])

# 全局服務實例
gmail_service = GmailService()
email_processor = EmailDocumentProcessor()


@router.get("/authorize-url", summary="獲取 Gmail OAuth 授權 URL")
async def get_authorize_url(
    request: Request,
    current_user: User = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    獲取 Gmail OAuth 授權 URL，前端需要重定向到此 URL
    
    Returns:
        OAuth 授權 URL
    """
    try:
        if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "Google OAuth 未正確配置",
                    "message": "請在 .env 文件中設置 GOOGLE_CLIENT_ID 和 GOOGLE_CLIENT_SECRET",
                    "setup_guide": "https://developers.google.com/identity/protocols/oauth2"
                }
            )
        
        # 創建 OAuth Flow
        flow = Flow.from_client_config(
            {
                "installed": {
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [settings.GOOGLE_REDIRECT_URI]
                }
            },
            scopes=[
                'https://www.googleapis.com/auth/gmail.readonly',
                'https://www.googleapis.com/auth/userinfo.profile',
                'https://www.googleapis.com/auth/userinfo.email',
                'openid'
            ],
            redirect_uri=settings.GOOGLE_REDIRECT_URI
        )
        
        # 生成授權 URL
        auth_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'
        )
        
        logger.info(f"Generated Gmail OAuth URL for user {current_user.id}")
        logger.debug(f"Redirect URI: {settings.GOOGLE_REDIRECT_URI}")
        
        await log_event(
            db=db,
            level=LogLevel.INFO,
            message=f"Generated Gmail OAuth URL for user {current_user.id}",
            source="gmail.authorize_url",
            user_id=str(current_user.id),
            request_id=request.headers.get("X-Request-ID")
        )
        
        return {
            "auth_url": auth_url,
            "state": state
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate OAuth URL: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"生成授權 URL 失敗: {str(e)}"
        )


@router.post("/callback", summary="處理 Gmail OAuth 授權回調")
@router.get("/callback", summary="處理 Gmail OAuth 授權回調 (GET)")
async def oauth_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    處理 Gmail OAuth 授權回調，保存用戶的 credentials
    
    Google 會通過 GET 請求重定向到此端點
    
    Args:
        code: Google OAuth 授權碼
        state: OAuth state 參數（用於驗證）
        
    Returns:
        HTML 頁面，通過 postMessage 通知父窗口授權完成
    """
    try:
        if not code:
            error_msg = request.query_params.get('error', 'Unknown error')
            return {
                "status": "error",
                "message": f"OAuth 授權失敗: {error_msg}",
                "html": f"""
                <html>
                    <body>
                        <script>
                            window.opener.postMessage(
                                {{type: 'gmail_auth_error', error: '{error_msg}'}},
                                window.location.origin
                            );
                            window.close();
                        </script>
                    </body>
                </html>
                """
            }
        
        if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
            raise HTTPException(status_code=500, detail="Google OAuth 未正確配置")
        
        # 創建 OAuth Flow
        flow = Flow.from_client_config(
            {
                "installed": {
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [settings.GOOGLE_REDIRECT_URI]
                }
            },
            scopes=['https://www.googleapis.com/auth/gmail.readonly'],
            redirect_uri=settings.GOOGLE_REDIRECT_URI
        )
        
        # 交換 authorization code 為 access token
        # 不驗證 scopes，因為 Google 可能在授權時要求額外的 scopes
        try:
            flow.fetch_token(code=code)
        except Exception as e:
            # 如果是 scope 相關的錯誤，直接拋出詳細錯誤
            logger.error(f"Token exchange failed: {str(e)}")
            if "Scope has changed" in str(e) or "scope" in str(e).lower():
                raise HTTPException(
                    status_code=500,
                    detail=f"授權過程中發生 scope 驗證錯誤。請重新授權。錯誤: {str(e)}"
                )
            else:
                raise HTTPException(
                    status_code=500,
                    detail=f"交換授權碼失敗: {str(e)}"
                )
        
        credentials = flow.credentials
        
        # 將 credentials 保存到用戶數據庫
        credentials_dict = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes
        }
        
        # 更新用戶的 Google credentials
        update_data = {
            'google_credentials': credentials_dict,
            'google_credentials_encrypted_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        from app.models.user_models import UserUpdate
        user_update = UserUpdate(**update_data)
        result = await crud_users.update_user(db, current_user.id, user_update)
        
        await log_event(
            db=db,
            level=LogLevel.INFO,
            message=f"User {current_user.id} successfully authorized Gmail",
            source="gmail.oauth_callback.success",
            user_id=str(current_user.id),
            request_id=request.headers.get("X-Request-ID")
        )
        
        # 返回 HTML 頁面，通過 postMessage 通知父窗口
        from fastapi.responses import HTMLResponse
        html_content = """
        <html>
            <head>
                <title>Gmail 授權完成</title>
                <style>
                    body {
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    }
                    .container {
                        background: white;
                        padding: 40px;
                        border-radius: 10px;
                        box-shadow: 0 10px 25px rgba(0,0,0,0.2);
                        text-align: center;
                    }
                    h1 {
                        color: #333;
                        margin: 0 0 10px 0;
                    }
                    p {
                        color: #666;
                        margin: 0;
                    }
                    .spinner {
                        border: 4px solid #f3f3f3;
                        border-top: 4px solid #667eea;
                        border-radius: 50%;
                        width: 30px;
                        height: 30px;
                        animation: spin 1s linear infinite;
                        margin: 20px auto;
                    }
                    @keyframes spin {
                        0% { transform: rotate(0deg); }
                        100% { transform: rotate(360deg); }
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>✓ Gmail 授權成功！</h1>
                    <div class="spinner"></div>
                    <p>正在關閉此窗口...</p>
                </div>
                <script>
                    // 通知父窗口授權已完成
                    if (window.opener) {
                        window.opener.postMessage(
                            {type: 'gmail_auth_complete', success: true},
                            window.location.origin
                        );
                    }
                    // 2 秒後關閉窗口
                    setTimeout(() => {
                        window.close();
                    }, 2000);
                </script>
            </body>
        </html>
        """
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        logger.error(f"OAuth callback failed: {e}")
        await log_event(
            db=db,
            level=LogLevel.ERROR,
            message=f"Gmail OAuth callback failed: {str(e)}",
            source="gmail.oauth_callback.error",
            user_id=str(current_user.id),
            request_id=request.headers.get("X-Request-ID")
        )
        
        from fastapi.responses import HTMLResponse
        html_content = f"""
        <html>
            <head>
                <title>授權失敗</title>
                <style>
                    body {{
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    }}
                    .container {{
                        background: white;
                        padding: 40px;
                        border-radius: 10px;
                        box-shadow: 0 10px 25px rgba(0,0,0,0.2);
                        text-align: center;
                    }}
                    h1 {{
                        color: #e74c3c;
                        margin: 0 0 10px 0;
                    }}
                    p {{
                        color: #666;
                        margin: 0;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>✗ 授權失敗</h1>
                    <p>{str(e)}</p>
                    <p>5 秒後將自動關閉此窗口</p>
                </div>
                <script>
                    // 通知父窗口授權失敗
                    if (window.opener) {{
                        window.opener.postMessage(
                            {{type: 'gmail_auth_error', error: '{str(e)}'}},
                            window.location.origin
                        );
                    }}
                    // 5 秒後關閉窗口
                    setTimeout(() => {{
                        window.close();
                    }}, 5000);
                </script>
            </body>
        </html>
        """
        return HTMLResponse(content=html_content, status_code=500)


@router.post("/exchange-code", summary="交換 Gmail OAuth authorization code")
async def exchange_authorization_code(
    request: Request,
    code: str = None,  # 支持查詢參數
    current_user: User = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """
    交換 Gmail OAuth authorization code 為 credentials，
    保存用戶的 Google credentials
    
    Args:
        code: Google OAuth 授權碼
        
    Returns:
        成功或失敗消息
    """
    try:
        # 驗證 code 參數
        if not code:
            raise HTTPException(
                status_code=400,
                detail="Missing required parameter: code"
            )
        
        if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
            raise HTTPException(status_code=500, detail="Google OAuth 未正確配置")
        
        # 創建 OAuth Flow
        flow = Flow.from_client_config(
            {
                "installed": {
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [settings.GOOGLE_REDIRECT_URI]
                }
            },
            scopes=[
                'https://www.googleapis.com/auth/gmail.readonly',
                'https://www.googleapis.com/auth/userinfo.profile',
                'https://www.googleapis.com/auth/userinfo.email',
                'openid'
            ],
            redirect_uri=settings.GOOGLE_REDIRECT_URI
        )
        
        # 交換 authorization code 為 access token
        flow.fetch_token(code=code)
        credentials = flow.credentials
        
        # 將 credentials 保存到用戶數據庫
        credentials_dict = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes
        }
        
        # 更新用戶的 Google credentials
        update_data = {
            'google_credentials': credentials_dict,
            'google_credentials_encrypted_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        from app.models.user_models import UserUpdate
        user_update = UserUpdate(**update_data)
        result = await crud_users.update_user(db, current_user.id, user_update)
        
        await log_event(
            db=db,
            level=LogLevel.INFO,
            message=f"User {current_user.id} successfully authorized Gmail",
            source="gmail.exchange_code.success",
            user_id=str(current_user.id),
            request_id=request.headers.get("X-Request-ID")
        )
        
        return {
            "status": "success",
            "message": "Gmail 授權成功",
            "user_id": str(current_user.id)
        }
        
    except Exception as e:
        logger.error(f"Exchange code failed: {e}")
        await log_event(
            db=db,
            level=LogLevel.ERROR,
            message=f"Gmail exchange code failed: {str(e)}",
            source="gmail.exchange_code.error",
            user_id=str(current_user.id),
            request_id=request.headers.get("X-Request-ID")
        )
        raise HTTPException(status_code=500, detail=f"交換授權碼失敗: {str(e)}")


@router.get("/messages", summary="列出 Gmail 郵件")
async def list_gmail_messages(
    request: Request,
    query: str = "",  # Gmail 搜索查詢
    limit: int = 20,
    page_token: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
) -> dict:
    """
    列出用戶 Gmail 中的郵件
    
    Query examples:
    - "" (empty) - 列出最新郵件
    - "from:someone@example.com" - 特定發件人
    - "has:attachment" - 有附件的郵件
    - "is:unread" - 未讀郵件
    - "label:INBOX" - 收件箱郵件
    
    Returns:
        郵件列表和分頁信息
    """
    try:
        request_id = request.headers.get("X-Request-ID")
        logger.info(f"Listing Gmail messages for user {current_user.id}, query: {query}")
        
        # 從數據庫中獲取用戶的 Google OAuth credentials
        user_doc = await crud_users.get_user_by_id(db, current_user.id)
        
        if not user_doc or not user_doc.google_credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Gmail 功能需要先進行授權。請先點擊授權按鈕完成 Google 帳號連接。"
            )
        
        # 從保存的 credentials 重建 Credentials 對象
        credentials_dict = user_doc.google_credentials
        credentials = Credentials(
            token=credentials_dict.get('token'),
            refresh_token=credentials_dict.get('refresh_token'),
            token_uri=credentials_dict.get('token_uri'),
            client_id=credentials_dict.get('client_id'),
            client_secret=credentials_dict.get('client_secret'),
            scopes=credentials_dict.get('scopes')
        )
        
        # 調用 Gmail 服務列出郵件
        result = await gmail_service.list_messages(
            credentials=credentials,
            query=query,
            max_results=limit,
            page_token=page_token
        )
        
        # 如果 token 被刷新，保存更新的 credentials 到數據庫
        if credentials.expired or credentials.token != credentials_dict.get('token'):
            try:
                updated_credentials_dict = {
                    'token': credentials.token,
                    'refresh_token': credentials.refresh_token,
                    'token_uri': credentials.token_uri,
                    'client_id': credentials.client_id,
                    'client_secret': credentials.client_secret,
                    'scopes': credentials.scopes
                }
                
                from app.models.user_models import UserUpdate
                user_update = UserUpdate(google_credentials=updated_credentials_dict)
                await crud_users.update_user(db, current_user.id, user_update)
                logger.info(f"Updated refreshed Gmail credentials for user {current_user.id}")
            except Exception as e:
                logger.warning(f"Failed to save refreshed credentials: {e}")
                # 不失敗，因為刷新已經成功，只是保存失敗
        
        await log_event(
            db=db,
            level=LogLevel.INFO,
            message=f"Retrieved {len(result['messages'])} Gmail messages",
            source="gmail.list_messages",
            user_id=str(current_user.id),
            request_id=request_id,
            details={"query": query, "count": len(result['messages'])}
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list Gmail messages: {e}")
        await log_event(
            db=db,
            level=LogLevel.ERROR,
            message=f"Failed to list Gmail messages: {str(e)}",
            source="gmail.list_messages.error",
            user_id=str(current_user.id),
            request_id=request.headers.get("X-Request-ID")
        )
        raise HTTPException(status_code=500, detail="列出 Gmail 郵件時發生錯誤")


@router.get("/check-auth-status", summary="檢查 Gmail 授權狀態")
async def check_gmail_auth_status(
    current_user: User = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
) -> dict:
    """
    輕量級端點：檢查用戶是否已授權 Gmail
    
    無需調用 Gmail API，只檢查本地數據庫中的 credentials
    
    Returns:
        {
            "is_authorized": bool,           # 是否已授權且有效
            "has_credentials": bool,         # 數據庫中是否有 credentials
            "has_refresh_token": bool,       # 是否有 refresh_token（用於長期授權）
            "last_updated": datetime | null  # credentials 最後更新時間
        }
    """
    try:
        user_doc = await crud_users.get_user_by_id(db, current_user.id)
        
        if not user_doc or not user_doc.google_credentials:
            return {
                "is_authorized": False,
                "has_credentials": False,
                "has_refresh_token": False,
                "last_updated": None
            }
        
        creds_dict = user_doc.google_credentials
        
        # 檢查關鍵字段是否完整
        has_token = bool(creds_dict.get('token'))
        has_refresh = bool(creds_dict.get('refresh_token'))
        has_client_id = bool(creds_dict.get('client_id'))
        has_client_secret = bool(creds_dict.get('client_secret'))
        
        # 認為已授權的條件：有 token 且有 client 信息
        is_authorized = has_token and has_client_id and has_client_secret
        
        logger.info(f"Gmail auth status for user {current_user.id}: is_authorized={is_authorized}, has_refresh={has_refresh}")
        
        return {
            "is_authorized": is_authorized,
            "has_credentials": True,
            "has_refresh_token": has_refresh,
            "last_updated": user_doc.google_credentials_encrypted_at
        }
        
    except Exception as e:
        logger.error(f"Check auth status failed: {e}")
        return {
            "is_authorized": False,
            "has_credentials": False,
            "has_refresh_token": False,
            "last_updated": None
        }


@router.post("/messages/{email_id}/import", summary="導入單個郵件為文檔", response_model=EmailImportResponse)
async def import_single_email(
    request: Request,
    email_id: str,
    tags: Optional[List[str]] = None,
    trigger_analysis: bool = False,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user: User = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
) -> EmailImportResponse:
    """
    導入單個郵件為可分析的文檔
    
    流程：
    1. 檢查郵件是否已導入（去重）
    2. 從 Gmail 獲取完整郵件內容
    3. 保存郵件文本到本地存儲
    4. 創建 Document 記錄
    5. (可選) 觸發 AI 分析
    """
    try:
        request_id = request.headers.get("X-Request-ID")
        logger.info(f"Importing Gmail message: {email_id}")
        
        # 1. 檢查是否已導入
        already_imported = await email_processor.check_email_already_imported(
            db=db,
            user_id=current_user.id,
            email_id=email_id
        )
        
        if already_imported:
            logger.warning(f"Email {email_id} already imported")
            return EmailImportResponse(
                email_id=email_id,
                document_id=None,
                status="already_imported",
                message="此郵件已經被導入"
            )
        
        # 獲取用戶的 Google credentials
        user_doc = await crud_users.get_user_by_id(db, current_user.id)
        if not user_doc or not user_doc.google_credentials:
            raise HTTPException(
                status_code=401,
                detail="Gmail 未授權"
            )
        
        credentials_dict = user_doc.google_credentials
        credentials = Credentials(
            token=credentials_dict.get('token'),
            refresh_token=credentials_dict.get('refresh_token'),
            token_uri=credentials_dict.get('token_uri'),
            client_id=credentials_dict.get('client_id'),
            client_secret=credentials_dict.get('client_secret'),
            scopes=credentials_dict.get('scopes')
        )
        
        # 2. 從 Gmail 獲取郵件內容
        email = await gmail_service.get_message_full(credentials, email_id)
        
        # 3. 處理郵件並創建 Document
        doc_create, content_path = await email_processor.create_document_from_email(
            email=email,
            user_id=current_user.id,
            tags=tags,
            db=db
        )
        
        # 4. 創建 Document 記錄
        document = await crud_documents.create_document(
            db=db,
            document_data=doc_create,
            owner_id=current_user.id,
            file_path=str(content_path)
        )
        
        # 5. 設置郵件元數據
        update_data = {
            "email_source": EmailSource.GMAIL.value,
            "email_metadata": {
                "email_id": email.email_id,
                "thread_id": email.thread_id,
                "from": email.from_address,
                "to": email.to_addresses,
                "subject": email.subject,
                "date": email.date.isoformat()
            },
            "email_synced_at": datetime.utcnow()
        }
        
        await crud_documents.update_document(db, document.id, update_data)
        
        await log_event(
            db=db,
            level=LogLevel.INFO,
            message=f"Email imported: {email_id}",
            source="gmail.import.success",
            user_id=str(current_user.id),
            request_id=request_id,
            details={"email_id": email_id, "document_id": str(document.id)}
        )
        
        return EmailImportResponse(
            email_id=email_id,
            document_id=document.id,
            status="success",
            message="郵件導入成功"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to import email: {e}")
        await log_event(
            db=db,
            level=LogLevel.ERROR,
            message=f"Failed to import email {email_id}: {str(e)}",
            source="gmail.import.error",
            user_id=str(current_user.id),
            request_id=request.headers.get("X-Request-ID")
        )
        raise HTTPException(status_code=500, detail=f"Failed to import email: {str(e)}")


@router.post("/messages/batch-import", summary="批量導入郵件", response_model=BatchEmailImportResponse)
async def batch_import_emails(
    request: Request,
    import_request: BatchEmailImportRequest,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    current_user: User = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db)
) -> BatchEmailImportResponse:
    """
    批量導入多個郵件
    
    支持用戶選擇要導入的特定郵件，而不是全部導入
    支持並發導入以提高性能
    
    Args:
        import_request: 包含要導入的郵件 ID 列表
        
    Returns:
        批量導入結果
    """
    try:
        request_id = request.headers.get("X-Request-ID")
        total = len(import_request.email_ids)
        logger.info(f"Batch importing {total} emails for user {current_user.id} (concurrent mode)")
        
        # 使用 asyncio.gather 並發導入，限制並發數為 5 個
        
        async def import_email_safely(email_id: str) -> EmailImportResponse:
            """安全地導入郵件，捕獲任何異常"""
            try:
                result = await import_single_email(
                    request=request,
                    email_id=email_id,
                    tags=import_request.tags,
                    trigger_analysis=import_request.trigger_analysis,
                    background_tasks=background_tasks,
                    current_user=current_user,
                    db=db
                )
                return result
            except Exception as e:
                logger.error(f"Failed to import email {email_id}: {e}")
                return EmailImportResponse(
                    email_id=email_id,
                    document_id=None,
                    status="error",
                    message=str(e)
                )
        
        # 限制並發數，避免過多連接
        semaphore = asyncio.Semaphore(15)
        
        async def import_with_semaphore(email_id: str) -> EmailImportResponse:
            async with semaphore:
                return await import_email_safely(email_id)
        
        # 並發執行所有導入
        results = await asyncio.gather(
            *[import_with_semaphore(email_id) for email_id in import_request.email_ids],
            return_exceptions=False
        )
        
        details: List[EmailImportResponse] = results
        successful = sum(1 for r in details if r.status == "success")
        skipped = sum(1 for r in details if r.status == "already_imported")
        failed = sum(1 for r in details if r.status in ("error",))
        
        await log_event(
            db=db,
            level=LogLevel.INFO,
            message=f"Batch import completed: {successful} successful, {skipped} skipped, {failed} failed",
            source="gmail.batch_import.complete",
            user_id=str(current_user.id),
            request_id=request_id,
            details={"total": total, "successful": successful, "skipped": skipped, "failed": failed}
        )
        
        return BatchEmailImportResponse(
            total=total,
            successful=successful,
            skipped=skipped,
            failed=failed,
            details=details
        )
        
    except Exception as e:
        logger.error(f"Batch import failed: {e}")
        await log_event(
            db=db,
            level=LogLevel.ERROR,
            message=f"Batch import failed: {str(e)}",
            source="gmail.batch_import.error",
            user_id=str(current_user.id),
            request_id=request.headers.get("X-Request-ID")
        )
        raise HTTPException(status_code=500, detail="Batch import failed")
