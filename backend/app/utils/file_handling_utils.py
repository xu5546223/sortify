import os
import uuid
import aiofiles
import logging
from pathlib import Path
from typing import Optional, Tuple
import mimetypes
import zipfile # For _validate_and_correct_file_type

from fastapi import HTTPException, UploadFile, status
from werkzeug.utils import secure_filename

from ..core.config import Settings
from ..core.logging_utils import log_event, LogLevel
# User model no longer needed here after correcting type hint
# from ..models.user_models import User 
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

def prepare_upload_filepath(
    settings_obj: Settings, 
    current_user_id: uuid.UUID, 
    original_filename_optional: Optional[str], 
    content_type: Optional[str]
) -> Tuple[Path, str]:
    """
    Prepares the upload file path and a unique, safe filename.
    """
    user_folder = Path(settings_obj.UPLOAD_DIR) / str(current_user_id)
    user_folder.mkdir(parents=True, exist_ok=True)

    original_filename = original_filename_optional if original_filename_optional else "untitled"
    base_name, ext = os.path.splitext(original_filename)
    safe_base_name = secure_filename(base_name) if base_name else ""
    
    if ext:
        safe_ext = ext.lower().lstrip('.')
    else:
        safe_ext = ""

    if not safe_base_name: # 如果清理後的基礎名稱為空 (例如，檔名是 ".bashrc")
        safe_base_name = f"file"

    # 生成一個短的唯一標識符，以避免檔名衝突
    unique_suffix = uuid.uuid4().hex[:8]

    guessed_ext_from_mime = mimetypes.guess_extension(content_type) if content_type else None
    if guessed_ext_from_mime:
        guessed_ext_from_mime = guessed_ext_from_mime.lstrip('.')

    final_ext = ""
    if safe_ext:
        final_ext = safe_ext
    elif guessed_ext_from_mime:
        final_ext = guessed_ext_from_mime
    else:
        final_ext = "bin" # 保留一個預設的副檔名以防萬一

    # 更新檔名結構以包含唯一標識符
    safe_filename = f"{safe_base_name}_{unique_suffix}.{final_ext}"
    file_path = user_folder / safe_filename
    return file_path, safe_filename

async def save_uploaded_file(file: UploadFile, file_path: Path, safe_filename: str) -> int:
    """
    Saves the uploaded file to the specified path and returns its size.
    Raises HTTPException if saving fails.
    """
    try:
        async with aiofiles.open(file_path, 'wb') as out_file:
            content = await file.read()  # Read file content
            await out_file.write(content) # Write to disk
            file_size = len(content) # Get file size
        # Use the module-level logger
        logger.info(f"文件 '{safe_filename}' 已保存到 '{file_path}'，大小: {file_size} bytes")
        return file_size
    except Exception as e:
        # Use the module-level logger
        logger.error(f"(save_uploaded_file) 保存文件 '{safe_filename}' 到 '{file_path}' 失敗: {e}")
        if file_path.exists():
            try:
                os.remove(str(file_path)) # Ensure file_path is string for os.remove
                logger.info(f"(save_uploaded_file) 已刪除部分寫入的文件: {file_path}")
            except OSError as rm_error:
                logger.error(f"(save_uploaded_file) 刪除部分寫入的文件 {file_path} 失敗: {rm_error}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"無法保存文件: {safe_filename}")

async def validate_and_correct_file_type(
    file_path: Path,
    declared_content_type: Optional[str],
    file_size: int,
    safe_filename: str,
    db: AsyncIOMotorDatabase,
    current_user_id: uuid.UUID, 
    request_id: Optional[str]
) -> Tuple[Optional[str], Optional[str]]:
    """
    Validates the file type based on its content and corrects if necessary.
    Returns the actual content type and any warning message.
    """
    actual_content_type: Optional[str] = declared_content_type
    mime_type_warning: Optional[str] = None
    # Removed unused original_mime_type_for_log variable

    if file_size == 0:
        logger.warning(f"警告：上傳的文件 '{safe_filename}' 大小為 0 字節")
        mime_type_warning = "文件大小為 0 字節，這可能不是一個有效的文件。"
        actual_content_type = "application/octet-stream"
    elif declared_content_type in [
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    ]:
        try:
            # zipfile already imported at module level
            with zipfile.ZipFile(file_path, 'r') as zip_check:
                zip_check.namelist()
            logger.info(f"已驗證 '{safe_filename}' 是有效的 Office 文件格式 ({declared_content_type})")
        except zipfile.BadZipFile:
            logger.warning(f"文件 '{safe_filename}' 聲稱是 Office 格式 ({declared_content_type})，但不是有效的 ZIP 格式。")
            actual_content_type = "application/octet-stream"
            mime_type_warning = f"文件聲稱是 {declared_content_type}，但驗證失敗。已作為二進制文件處理。"
            await log_event(
                db=db,
                level=LogLevel.WARNING,
                message=mime_type_warning,
                source="file_handling_utils.validate_file_type", # Updated source
                user_id=str(current_user_id),
                request_id=request_id,
                details={
                    "filename": safe_filename,
                    "declared_mime_type": declared_content_type,
                    "corrected_mime_type": actual_content_type
                }
            )
    elif declared_content_type == "application/pdf":
        # Placeholder for potential PDF validation
        pass
    
    return actual_content_type, mime_type_warning
