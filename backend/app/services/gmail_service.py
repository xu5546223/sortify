import logging
import base64
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from email.mime.text import MIMEText
import google.auth.transport.requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import json
from html.parser import HTMLParser
import re
import asyncio

from app.core.config import settings
from app.core.logging_utils import AppLogger, log_event, LogLevel
from app.models.email_models import EmailMessage, GmailMessagePreview

logger = AppLogger(__name__, level=logging.DEBUG).get_logger()

# Gmail API 作用域
GMAIL_SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']


class SimpleHTMLToTextParser(HTMLParser):
    """將 HTML 轉換為純文本的簡單解析器"""
    
    def __init__(self):
        super().__init__()
        self.text_parts = []
        self.skip_content = False
        self.in_script_or_style = False
        self.previous_text_was_block = True
        
    def handle_starttag(self, tag, attrs):
        """處理開始標籤"""
        if tag in ('script', 'style'):
            self.in_script_or_style = True
        elif tag in ('p', 'div', 'br', 'tr', 'li'):
            # 塊級元素前後加換行
            if self.text_parts and not self.previous_text_was_block:
                self.text_parts.append('\n')
                self.previous_text_was_block = True
                
    def handle_endtag(self, tag):
        """處理結束標籤"""
        if tag in ('script', 'style'):
            self.in_script_or_style = False
        elif tag in ('p', 'div', 'tr', 'li'):
            if self.text_parts and not self.previous_text_was_block:
                self.text_parts.append('\n')
                self.previous_text_was_block = True
                
    def handle_data(self, data):
        """處理文本數據"""
        if not self.in_script_or_style:
            # 清理多餘空白
            text = data.strip()
            if text:
                self.text_parts.append(text)
                self.text_parts.append(' ')
                self.previous_text_was_block = False
                
    def get_text(self) -> str:
        """獲取轉換後的文本"""
        # 清理多餘的空白和換行
        text = ''.join(self.text_parts)
        # 移除多餘的連續空白
        text = re.sub(r'\s+', ' ', text)
        # 移除多餘的連續換行
        text = re.sub(r'\n\n+', '\n', text)
        return text.strip()


class GmailService:
    """Gmail API 服務"""

    def __init__(self):
        self.service = None
        self.credentials = None
        self._credentials_token = None  # 用於比較憑證是否改變

    def build_service(self, credentials: Credentials):
        """使用憑證建立 Gmail 服務"""
        try:
            # 自動刷新過期的 token
            if credentials.expired and credentials.refresh_token:
                logger.info("Token is expired, refreshing...")
                credentials.refresh(Request())
                logger.info("Token refreshed successfully")
            
            self.credentials = credentials
            self._credentials_token = credentials.token  # 保存 token 用於比較
            self.service = build('gmail', 'v1', credentials=credentials)
            logger.info("Gmail service built successfully")
            return self.service
        except Exception as e:
            logger.error(f"Failed to build Gmail service: {e}")
            raise

    async def list_messages(
        self,
        credentials: Credentials,
        query: str = "",
        max_results: int = 20,
        page_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        列出 Gmail 中的郵件
        
        Args:
            credentials: OAuth 憑證
            query: Gmail 搜索查詢 (e.g., "from:someone@example.com", "has:attachment", "is:unread")
            max_results: 返回的最大結果數
            page_token: 分頁令牌
            
        Returns:
            包含郵件列表和分頁信息的字典
        """
        try:
            # 只在憑證改變或服務不存在時重新構建（比較 token 而不是對象）
            if self.service is None or self._credentials_token != credentials.token:
                self.build_service(credentials)
            
            # 構建請求
            request = self.service.users().messages().list(
                userId='me',
                q=query,
                maxResults=min(max_results, 100),  # Gmail API 最多 100 條
                pageToken=page_token
            )
            
            result = request.execute()
            messages = result.get('messages', [])
            
            logger.info(f"Retrieved {len(messages)} messages from Gmail")
            
            # 使用執行程池並發調用 Gmail API（真正的多線程）
            from concurrent.futures import ThreadPoolExecutor
            import time
            import threading
            
            start_time = time.time()
            
            # 在主線程創建一次 Gmail service，所有線程共用（避免重複初始化）
            shared_service = build('gmail', 'v1', credentials=credentials)
            service_lock = threading.Lock()
            
            def get_preview_sync(msg_id: str) -> Optional[Dict[str, Any]]:
                """同步版本的預覽獲取 - 使用共享的 Gmail service（加鎖保護）"""
                try:
                    with service_lock:
                        request = shared_service.users().messages().get(
                            userId='me',
                            id=msg_id,
                            format='metadata',
                            metadataHeaders=['From', 'To', 'Subject', 'Date']
                        )
                        message = request.execute()
                    
                    headers = {h['name']: h['value'] for h in message['payload'].get('headers', [])}
                    
                    # 計算郵件大小（以字節計）
                    size = int(message.get('sizeEstimate', 0))
                    
                    preview = GmailMessagePreview(
                        email_id=msg_id,
                        subject=headers.get('Subject', '[No Subject]'),
                        from_address=headers.get('From', '[Unknown]'),
                        snippet=message.get('snippet', ''),
                        date=self._parse_email_date(headers.get('Date', '')),
                        size=size,
                        is_unread=message.get('labelIds', []) and 'UNREAD' in message.get('labelIds', []),
                        is_starred=message.get('labelIds', []) and 'STARRED' in message.get('labelIds', [])
                    )
                    
                    return preview.model_dump()
                    
                except Exception as e:
                    logger.warning(f"Failed to get preview for {msg_id}: {e}")
                    return None
            
            # 使用執行程池，最多 5 個工作程緒（降低並發數以避免過載）
            with ThreadPoolExecutor(max_workers=15) as executor:
                previews_results = list(executor.map(
                    get_preview_sync,
                    [msg['id'] for msg in messages],
                    timeout=30
                ))
            
            # 過濾掉 None 結果
            previews = [p for p in previews_results if p is not None]
            
            elapsed = time.time() - start_time
            logger.info(f"Retrieved {len(previews)} message previews in {elapsed:.2f}s")
            
            return {
                'messages': previews,
                'next_page_token': result.get('nextPageToken'),
                'total_results': result.get('resultSizeEstimate', 0)
            }
        except HttpError as error:
            logger.error(f"An error occurred: {error}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in list_messages: {e}")
            raise

    async def get_message_preview(
        self,
        credentials: Credentials,
        message_id: str
    ) -> Optional[GmailMessagePreview]:
        """
        獲取郵件預覽信息
        
        Args:
            credentials: OAuth 憑證
            message_id: Gmail 郵件 ID
            
        Returns:
            郵件預覽對象
        """
        try:
            # 只在憑證改變或服務不存在時重新構建（比較 token 而不是對象）
            if self.service is None or self._credentials_token != credentials.token:
                self.build_service(credentials)
            
            request = self.service.users().messages().get(
                userId='me',
                id=message_id,
                format='metadata',
                metadataHeaders=['From', 'To', 'Subject', 'Date']
            )
            
            message = request.execute()
            headers = {h['name']: h['value'] for h in message['payload'].get('headers', [])}
            
            # 計算郵件大小（以字節計）
            size = int(message.get('sizeEstimate', 0))
            
            preview = GmailMessagePreview(
                email_id=message_id,
                subject=headers.get('Subject', '[No Subject]'),
                from_address=headers.get('From', '[Unknown]'),
                snippet=message.get('snippet', ''),
                date=self._parse_email_date(headers.get('Date', '')),
                size=size,
                is_unread=message.get('labelIds', []) and 'UNREAD' in message.get('labelIds', []),
                is_starred=message.get('labelIds', []) and 'STARRED' in message.get('labelIds', [])
            )
            
            return preview
        except HttpError as error:
            logger.error(f"Failed to get message preview: {error}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in get_message_preview: {e}")
            return None

    async def get_message_full(
        self,
        credentials: Credentials,
        message_id: str
    ) -> Optional[EmailMessage]:
        """
        獲取完整的郵件內容
        
        Args:
            credentials: OAuth 憑證
            message_id: Gmail 郵件 ID
            
        Returns:
            完整的郵件對象
        """
        try:
            # 只在憑證改變或服務不存在時重新構建（比較 token 而不是對象）
            if self.service is None or self._credentials_token != credentials.token:
                self.build_service(credentials)
            
            request = self.service.users().messages().get(
                userId='me',
                id=message_id,
                format='full'
            )
            
            message = request.execute()
            headers = {h['name']: h['value'] for h in message['payload'].get('headers', [])}
            
            # 提取郵件正文
            body = self._extract_body(message['payload'])
            
            # 提取附件信息
            attachments = self._extract_attachments(message['payload'].get('parts', []))
            
            # 解析收件人地址
            to_addresses = self._parse_email_addresses(headers.get('To', ''))
            cc_addresses = self._parse_email_addresses(headers.get('Cc', ''))
            bcc_addresses = self._parse_email_addresses(headers.get('Bcc', ''))
            
            email = EmailMessage(
                email_id=message_id,
                message_id=headers.get('Message-ID', ''),
                thread_id=message.get('threadId', ''),
                subject=headers.get('Subject', '[No Subject]'),
                from_address=headers.get('From', ''),
                to_addresses=to_addresses,
                cc_addresses=cc_addresses,
                bcc_addresses=bcc_addresses,
                date=self._parse_email_date(headers.get('Date', '')),
                body=body,
                snippet=message.get('snippet', ''),
                attachments=attachments,
                labels=message.get('labelIds', []),
                is_unread='UNREAD' in message.get('labelIds', []),
                is_starred='STARRED' in message.get('labelIds', []),
            )
            
            logger.info(f"Retrieved full message: {message_id}")
            return email
        except HttpError as error:
            logger.error(f"Failed to get full message: {error}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in get_message_full: {e}")
            raise

    def _extract_body(self, payload: Dict[str, Any]) -> str:
        """從郵件 payload 中提取正文（純文本，移除 HTML 標籤）"""
        body = ""
        html_content = ""
        
        if 'parts' in payload:
            # 多部分郵件，優先提取 text/plain，其次提取 text/html
            for part in payload['parts']:
                mime_type = part.get('mimeType', '')
                
                if mime_type == 'text/plain' and not body:
                    if 'data' in part.get('body', {}):
                        body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                elif mime_type == 'text/html' and not body:
                    # 如果沒有 text/plain，則使用 HTML
                    if 'data' in part.get('body', {}):
                        html_content = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
        else:
            # 簡單郵件
            if 'body' in payload and 'data' in payload['body']:
                content = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')
                # 判斷是否為 HTML（簡單啟發式）
                if '<' in content and '>' in content:
                    html_content = content
                else:
                    body = content
        
        # 如果只有 HTML，將其轉換為純文本
        if html_content and not body:
            try:
                parser = SimpleHTMLToTextParser()
                parser.feed(html_content)
                body = parser.get_text()
                logger.debug(f"Extracted text from HTML email, converted {len(html_content)} bytes to {len(body)} bytes")
            except Exception as e:
                logger.warning(f"Failed to parse HTML content: {e}, using HTML as-is")
                body = html_content
        
        return body.strip()

    def _extract_attachments(self, parts: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """從郵件部分中提取附件信息"""
        attachments = []
        for part in parts:
            if 'filename' in part and part['filename']:
                attachments.append({
                    'filename': part['filename'],
                    'mime_type': part.get('mimeType', ''),
                    'size': str(part.get('body', {}).get('size', 0))
                })
        return attachments

    def _parse_email_addresses(self, address_str: str) -> List[str]:
        """解析電子郵件地址字符串"""
        if not address_str:
            return []
        
        # 簡單解析，支持逗號分隔的地址
        addresses = []
        for addr in address_str.split(','):
            # 提取 <email@domain.com> 中的郵箱部分
            if '<' in addr and '>' in addr:
                email = addr[addr.find('<') + 1:addr.find('>')]
            else:
                email = addr.strip()
            if email:
                addresses.append(email)
        
        return addresses

    def _parse_email_date(self, date_str: str) -> datetime:
        """解析郵件日期字符串"""
        if not date_str:
            return datetime.utcnow()
        
        try:
            # Gmail 返回的日期格式: "Mon, 15 Jan 2024 10:30:00 +0000"
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(date_str)
        except Exception as e:
            logger.warning(f"Failed to parse date '{date_str}': {e}")
            return datetime.utcnow()
