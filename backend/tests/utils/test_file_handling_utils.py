import pytest
import uuid
from pathlib import Path
from unittest.mock import MagicMock

from sortify.backend.app.utils.file_handling_utils import prepare_upload_filepath
from sortify.backend.app.core.config import Settings

# Minimal settings mock or fixture for testing
@pytest.fixture
def mock_settings() -> Settings:
    settings = MagicMock(spec=Settings)
    settings.UPLOAD_DIR = "/test_uploads" # Use a distinct path for testing
    return settings

def test_prepare_upload_filepath_basic(mock_settings: Settings):
    user_id = uuid.uuid4()
    original_filename = "test.txt"
    content_type = "text/plain"

    file_path, safe_filename = prepare_upload_filepath(mock_settings, user_id, original_filename, content_type)

    assert isinstance(file_path, Path)
    assert safe_filename.startswith("test_")
    assert safe_filename.endswith(".txt")
    assert str(user_id) in str(file_path)
    assert mock_settings.UPLOAD_DIR in str(file_path)
    assert len(safe_filename) > len(".txt") + 8 # original_basename + _ + 8char_uuid + .ext

def test_prepare_upload_filepath_no_extension(mock_settings: Settings):
    user_id = uuid.uuid4()
    original_filename = "testfile"
    content_type = "application/octet-stream"

    file_path, safe_filename = prepare_upload_filepath(mock_settings, user_id, original_filename, content_type)
    
    assert safe_filename.startswith("testfile_")
    # In this case, mimetypes might guess an extension if content_type is common, 
    # or it defaults to ".bin" if content_type is generic like "application/octet-stream"
    # and original filename had no extension.
    # Based on current logic: if original has no ext, and content_type is generic, it defaults to .bin
    assert safe_filename.endswith(".bin") # Default extension

def test_prepare_upload_filepath_with_special_chars(mock_settings: Settings):
    user_id = uuid.uuid4()
    original_filename = "s@fe&name!.docx"
    content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    _, safe_filename = prepare_upload_filepath(mock_settings, user_id, original_filename, content_type)
    
    assert "s_fe_name_.docx" in safe_filename # werkzeug.utils.secure_filename behavior
    assert safe_filename.endswith(".docx")

def test_prepare_upload_filepath_no_filename(mock_settings: Settings):
    user_id = uuid.uuid4()
    original_filename = None
    content_type = "image/jpeg"

    _, safe_filename = prepare_upload_filepath(mock_settings, user_id, original_filename, content_type)
    
    assert safe_filename.startswith("untitled_")
    assert safe_filename.endswith(".jpeg") # Guessed from content_type

def test_prepare_upload_filepath_empty_filename_with_ext(mock_settings: Settings):
    user_id = uuid.uuid4()
    original_filename = ".bashrc" # secure_filename results in empty string for basename
    content_type = "text/plain" 
    
    _, safe_filename = prepare_upload_filepath(mock_settings, user_id, original_filename, content_type)
    
    assert safe_filename.startswith("file_") # Default base name 'file' when secure_filename is empty
    assert safe_filename.endswith(".bashrc")

def test_prepare_upload_filepath_content_type_guessing(mock_settings: Settings):
    user_id = uuid.uuid4()
    original_filename = "archive"
    content_type = "application/zip" # Should guess .zip

    _, safe_filename = prepare_upload_filepath(mock_settings, user_id, original_filename, content_type)
    assert safe_filename.endswith(".zip")

    original_filename_no_ext = "my_image"
    content_type_jpeg = "image/jpeg"
    _, safe_filename_jpeg = prepare_upload_filepath(mock_settings, user_id, original_filename_no_ext, content_type_jpeg)
    assert safe_filename_jpeg.endswith(".jpeg")

# Tests for save_uploaded_file
@pytest.mark.asyncio
@patch("sortify.backend.app.utils.file_handling_utils.aiofiles.open", new_callable=MagicMock)
async def test_save_uploaded_file_success(mock_aio_open, tmp_path: Path):
    from sortify.backend.app.utils.file_handling_utils import save_uploaded_file
    
    mock_file_content = b"test content"
    mock_upload_file = MagicMock(spec=Uploa...) # Needs UploadFile from fastapi
    mock_upload_file.read = AsyncMock(return_value=mock_file_content)
    
    # Configure the async context manager for aiofiles.open
    mock_async_file = AsyncMock()
    mock_aio_open.return_value.__aenter__.return_value = mock_async_file

    file_path = tmp_path / "test_save.txt"
    safe_filename = "test_save.txt"

    file_size = await save_uploaded_file(mock_upload_file, file_path, safe_filename)

    assert file_size == len(mock_file_content)
    mock_aio_open.assert_called_once_with(file_path, 'wb')
    mock_upload_file.read.assert_called_once()
    mock_async_file.write.assert_called_once_with(mock_file_content)

@pytest.mark.asyncio
@patch("sortify.backend.app.utils.file_handling_utils.aiofiles.open", new_callable=MagicMock)
@patch("sortify.backend.app.utils.file_handling_utils.os.remove")
@patch("sortify.backend.app.utils.file_handling_utils.os.path.exists")
async def test_save_uploaded_file_write_exception(mock_os_path_exists, mock_os_remove, mock_aio_open, tmp_path: Path):
    from sortify.backend.app.utils.file_handling_utils import save_uploaded_file, HTTPException, status

    mock_upload_file = MagicMock(spec=Uploa...) # Needs UploadFile
    mock_upload_file.read = AsyncMock(return_value=b"test")

    mock_async_file = AsyncMock()
    mock_async_file.write.side_effect = IOError("Disk full")
    mock_aio_open.return_value.__aenter__.return_value = mock_async_file
    
    file_path = tmp_path / "error_save.txt"
    safe_filename = "error_save.txt"
    mock_os_path_exists.return_value = True # Assume file was created before error

    with pytest.raises(HTTPException) as exc_info:
        await save_uploaded_file(mock_upload_file, file_path, safe_filename)
    
    assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert f"無法保存文件: {safe_filename}" in exc_info.value.detail
    mock_os_path_exists.assert_called_once_with(file_path)
    mock_os_remove.assert_called_once_with(str(file_path))


# Tests for validate_and_correct_file_type
@pytest.mark.asyncio
@patch("sortify.backend.app.utils.file_handling_utils.log_event", new_callable=AsyncMock)
async def test_validate_and_correct_file_type_zero_size(mock_log_event, tmp_path: Path):
    from sortify.backend.app.utils.file_handling_utils import validate_and_correct_file_type
    mock_db = AsyncMock()
    file_path = tmp_path / "zero.txt" # Doesn't need to exist for this test part
    
    content_type, warning = await validate_and_correct_file_type(
        file_path, "text/plain", 0, "zero.txt", mock_db, uuid.uuid4(), "req_id_1"
    )
    assert content_type == "application/octet-stream"
    assert "文件大小為 0 字節" in warning
    mock_log_event.assert_not_called() # No log_event for zero size file directly in this func, only logger.warning

@pytest.mark.asyncio
@patch("sortify.backend.app.utils.file_handling_utils.zipfile.ZipFile")
@patch("sortify.backend.app.utils.file_handling_utils.log_event", new_callable=AsyncMock)
async def test_validate_and_correct_file_type_valid_docx(mock_log_event, mock_zipfile, tmp_path: Path):
    from sortify.backend.app.utils.file_handling_utils import validate_and_correct_file_type
    mock_db = AsyncMock()
    file_path = tmp_path / "valid.docx" # Doesn't need to exist if ZipFile is mocked
    
    # Mock ZipFile to simulate a valid DOCX
    mock_zip_instance = MagicMock()
    mock_zipfile.return_value.__enter__.return_value = mock_zip_instance

    content_type, warning = await validate_and_correct_file_type(
        file_path, "application/vnd.openxmlformats-officedocument.wordprocessingml.document", 
        1024, "valid.docx", mock_db, uuid.uuid4(), "req_id_2"
    )
    assert content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert warning is None
    mock_log_event.assert_not_called() # No warning log_event for valid docx

@pytest.mark.asyncio
@patch("sortify.backend.app.utils.file_handling_utils.zipfile.ZipFile")
@patch("sortify.backend.app.utils.file_handling_utils.log_event", new_callable=AsyncMock)
async def test_validate_and_correct_file_type_invalid_docx_bad_zip(mock_log_event, mock_zipfile, tmp_path: Path):
    from sortify.backend.app.utils.file_handling_utils import validate_and_correct_file_type, zipfile
    mock_db = AsyncMock()
    file_path = tmp_path / "invalid.docx"

    # Mock ZipFile to raise BadZipFile
    mock_zipfile.side_effect = zipfile.BadZipFile

    declared_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    content_type, warning = await validate_and_correct_file_type(
        file_path, declared_type, 
        1024, "invalid.docx", mock_db, uuid.uuid4(), "req_id_3"
    )
    assert content_type == "application/octet-stream"
    assert f"文件聲稱是 {declared_type}，但驗證失敗。" in warning
    mock_log_event.assert_called_once()
    log_args = mock_log_event.call_args.kwargs
    assert log_args['message'] == warning
    assert log_args['details']['declared_mime_type'] == declared_type

@pytest.mark.asyncio
@patch("sortify.backend.app.utils.file_handling_utils.log_event", new_callable=AsyncMock)
async def test_validate_and_correct_file_type_pdf(mock_log_event, tmp_path: Path):
    from sortify.backend.app.utils.file_handling_utils import validate_and_correct_file_type
    mock_db = AsyncMock()
    file_path = tmp_path / "test.pdf"
    declared_type = "application/pdf"
    
    content_type, warning = await validate_and_correct_file_type(
        file_path, declared_type, 5000, "test.pdf", mock_db, uuid.uuid4(), "req_id_4"
    )
    assert content_type == declared_type
    assert warning is None
    mock_log_event.assert_not_called()

# Need to import UploadFile for the mock_upload_file spec
from fastapi import UploadFile
