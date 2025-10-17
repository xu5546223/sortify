import logging
import json
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime
import uuid

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.email_models import EmailMessage, EmailSource
from app.models.document_models import DocumentCreate, DocumentStatus
from app.core.logging_utils import AppLogger, log_event, LogLevel
from app.core.config import settings

logger = AppLogger(__name__, level=logging.DEBUG).get_logger()


class EmailDocumentProcessor:
    """郵件文檔處理器 - 將 Gmail 郵件轉換為 Document 記錄"""

    def __init__(self):
        self.uploads_base_path = Path(settings.UPLOAD_DIR)

    async def save_email_content(
        self,
        email: EmailMessage,
        user_id: uuid.UUID,
        document_id: uuid.UUID
    ) -> Tuple[Path, int]:
        """
        保存郵件內容到本地磁盤
        
        Args:
            email: EmailMessage 對象
            user_id: 用戶 ID
            document_id: 文檔 ID
            
        Returns:
            (郵件正文文件路徑, 文件大小)
        """
        try:
            # 創建目錄結構: /uploads/{user_id}/emails/{document_id}/
            email_dir = self.uploads_base_path / str(user_id) / "emails" / str(document_id)
            email_dir.mkdir(parents=True, exist_ok=True)
            
            # 1. 保存郵件正文
            content_file = email_dir / "content.txt"
            content_file.write_text(email.body, encoding='utf-8')
            
            # 2. 保存郵件元數據
            metadata_file = email_dir / "metadata.json"
            metadata = {
                "email_id": email.email_id,
                "message_id": email.message_id,
                "thread_id": email.thread_id,
                "subject": email.subject,
                "from": email.from_address,
                "to": email.to_addresses,
                "cc": email.cc_addresses,
                "bcc": email.bcc_addresses,
                "date": email.date.isoformat(),
                "labels": email.labels,
                "is_unread": email.is_unread,
                "is_starred": email.is_starred,
                "attachments": email.attachments
            }
            metadata_file.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
            
            # 3. 保存完整的 RFC822 格式 (可選)
            full_file = email_dir / "full.eml"
            full_file.write_text(self._construct_rfc822(email), encoding='utf-8')
            
            file_size = len(email.body.encode('utf-8'))
            logger.info(f"Saved email content: {content_file} (size: {file_size} bytes)")
            
            return content_file, file_size
            
        except Exception as e:
            logger.error(f"Failed to save email content: {e}")
            raise

    async def create_document_from_email(
        self,
        email: EmailMessage,
        user_id: uuid.UUID,
        tags: Optional[list] = None,
        db: Optional[AsyncIOMotorDatabase] = None
    ) -> Tuple[DocumentCreate, Path]:
        """
        從 Gmail 郵件創建 Document 記錄
        
        Args:
            email: EmailMessage 對象
            user_id: 用戶 ID
            tags: 標籤列表
            db: 數據庫連接
            
        Returns:
            (DocumentCreate 對象, 文件路徑)
        """
        try:
            document_id = uuid.uuid4()
            
            # 保存郵件內容
            content_path, file_size = await self.save_email_content(email, user_id, document_id)
            
            # 生成文件名 (使用郵件主題)
            filename = self._sanitize_filename(f"{email.subject}_{email.email_id}")
            
            # 構造 DocumentCreate
            doc_create = DocumentCreate(
                filename=filename,
                file_type="text/plain",  # 郵件正文存儲為純文本
                size=file_size,
                owner_id=user_id,
                tags=tags or [],
                metadata={
                    "source": EmailSource.GMAIL.value,
                    "email_id": email.email_id,
                    "thread_id": email.thread_id,
                    "from": email.from_address,
                    "to": email.to_addresses,
                    "import_date": datetime.utcnow().isoformat()
                }
            )
            
            logger.info(f"Created DocumentCreate from email: {filename}")
            return doc_create, content_path
            
        except Exception as e:
            logger.error(f"Failed to create document from email: {e}")
            raise

    async def check_email_already_imported(
        self,
        db: AsyncIOMotorDatabase,
        user_id: uuid.UUID,
        email_id: str
    ) -> bool:
        """
        檢查郵件是否已經被導入
        
        Args:
            db: 數據庫連接
            user_id: 用戶 ID
            email_id: Gmail 郵件 ID
            
        Returns:
            是否已導入
        """
        try:
            existing = await db["documents"].find_one({
                "owner_id": user_id,
                "email_metadata.email_id": email_id
            })
            return existing is not None
        except Exception as e:
            logger.error(f"Error checking if email already imported: {e}")
            return False

    def _sanitize_filename(self, filename: str, max_length: int = 200) -> str:
        """
        清理文件名，移除不允許的字符
        
        Args:
            filename: 原始文件名
            max_length: 最大長度
            
        Returns:
            清理後的文件名
        """
        # 移除不允許的字符
        invalid_chars = '<>:"|?*\\/'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        
        # 限制長度
        if len(filename) > max_length:
            filename = filename[:max_length]
        
        return filename.strip()

    def _escape_html(self, text: str) -> str:
        """
        轉義 HTML 特殊字符
        
        Args:
            text: 原始文本
            
        Returns:
            轉義後的文本
        """
        return (text
                .replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;')
                .replace('"', '&quot;')
                .replace("'", '&#39;'))

    def _construct_rfc822(self, email: EmailMessage) -> str:
        """
        構造 RFC822 格式的郵件
        
        Args:
            email: EmailMessage 對象
            
        Returns:
            RFC822 格式的字符串
        """
        lines = []
        
        # Headers
        lines.append(f"From: {email.from_address}")
        lines.append(f"To: {', '.join(email.to_addresses)}")
        if email.cc_addresses:
            lines.append(f"Cc: {', '.join(email.cc_addresses)}")
        lines.append(f"Subject: {email.subject}")
        lines.append(f"Date: {email.date.isoformat()}")
        lines.append(f"Message-ID: {email.message_id}")
        
        # 添加自定義 Headers
        lines.append(f"X-Gmail-ID: {email.email_id}")
        lines.append(f"X-Gmail-Thread-ID: {email.thread_id}")
        
        # 空行分隔
        lines.append("")
        
        # Body
        lines.append(email.body)
        
        return "\n".join(lines)
