import pytest
import pytest_asyncio
from httpx import AsyncClient
from fastapi import FastAPI, status
from typing import AsyncGenerator
from unittest.mock import patch, MagicMock, AsyncMock
import uuid
import os
import shutil
from datetime import datetime, timezone

from sortify.backend.app.apis.v1.documents import router as documents_router
from sortify.backend.app.dependencies import get_db
from sortify.backend.app.models.document_models import Document, DocumentCreate, DocumentStatus
from sortify.backend.app.models.user_models import User # Added for mocking user
from sortify.backend.app.core.config import settings
from pathlib import Path # Added for Path object

# Create a minimal app for testing this specific router
test_app = FastAPI()

# Mock database dependency for the test_app
async def override_get_db_test():
    mock_db = AsyncMock()
    return mock_db

test_app.include_router(documents_router, prefix="/api/v1/documents", tags=["documents"])
test_app.dependency_overrides[get_db] = override_get_db_test


TEST_UPLOAD_DIR = "./test_upload_area_docs_api"

@pytest.fixture(scope="module", autouse=True)
def manage_test_upload_dir():
    original_upload_dir = getattr(settings, 'UPLOAD_DIR', None)
    
    settings.UPLOAD_DIR = TEST_UPLOAD_DIR
    if not os.path.exists(settings.UPLOAD_DIR):
        os.makedirs(settings.UPLOAD_DIR)
    
    yield
    
    if os.path.exists(settings.UPLOAD_DIR):
        shutil.rmtree(settings.UPLOAD_DIR)
    if original_upload_dir is not None:
        settings.UPLOAD_DIR = original_upload_dir
    elif hasattr(settings, 'UPLOAD_DIR'): # If it was None but attr existed
        delattr(settings, 'UPLOAD_DIR')


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(app=test_app, base_url="http://testserver") as ac:
        yield ac

# ----- Tests for POST / endpoint -----

@pytest.mark.asyncio
@patch("sortify.backend.app.utils.file_handling_utils.prepare_upload_filepath")
@patch("sortify.backend.app.utils.file_handling_utils.save_uploaded_file", new_callable=AsyncMock)
@patch("sortify.backend.app.utils.file_handling_utils.validate_and_correct_file_type", new_callable=AsyncMock)
@patch("sortify.backend.app.apis.v1.documents.crud_documents.create_document", new_callable=AsyncMock)
async def test_upload_document_success(
    mock_crud_create_document: AsyncMock,
    mock_validate_file_type: AsyncMock,
    mock_save_uploaded_file: AsyncMock,
    mock_prepare_upload_filepath: MagicMock,
    client: AsyncClient
):
    # Arrange
    test_original_filename = "test_file.txt"
    test_safe_filename = "test_file_safebase.txt" 
    test_content_type = "text/plain"
    test_file_size = 1024
    test_user_id_obj = uuid.uuid4() 

    mock_current_user = User(id=test_user_id_obj, email="test@example.com", is_active=True, is_superuser=False, hashed_password="xxx")

    mock_upload_dir = Path(settings.UPLOAD_DIR) # settings.UPLOAD_DIR is already a Path
    mock_file_path_obj = mock_upload_dir / test_safe_filename
    
    mock_prepare_upload_filepath.return_value = (mock_file_path_obj, test_safe_filename)
    mock_save_uploaded_file.return_value = test_file_size
    mock_validate_file_type.return_value = (test_content_type, None) # (actual_content_type, mime_type_warning)

    expected_doc_id = uuid.uuid4()
    fixed_datetime = datetime.now(timezone.utc).replace(microsecond=0)

    # This mock Document is what crud_documents.create_document is expected to return
    mock_created_doc_instance = Document(
        id=expected_doc_id,
        filename=test_safe_filename, 
        file_type=test_content_type,
        size=test_file_size,
        owner_id=test_user_id_obj, 
        upload_date=fixed_datetime,
        status=DocumentStatus.UPLOADED,
        file_path=str(mock_file_path_obj), 
        tags=["tag1", "tag2"],
        metadata={} 
    )
    mock_crud_create_document.return_value = mock_created_doc_instance

    file_content = b"This is a test file."
    files_payload = {"file": (test_original_filename, file_content, test_content_type)}
    form_data = {"tags": '["tag1", "tag2"]'} # Tags as JSON string, FastAPI handles parsing

    with patch("sortify.backend.app.apis.v1.documents.get_current_active_user", return_value=mock_current_user):
        response = await client.post("/api/v1/documents/", files=files_payload, data=form_data)

    # Assert
    assert response.status_code == status.HTTP_201_CREATED
    response_data = response.json()
    
    assert response_data["id"] == str(expected_doc_id)
    assert response_data["filename"] == test_safe_filename
    assert response_data["file_type"] == test_content_type
    assert response_data["size"] == test_file_size
    assert response_data["status"] == DocumentStatus.UPLOADED.value
    assert sorted(response_data["tags"]) == sorted(["tag1", "tag2"])
    assert response_data["file_path"] == str(mock_file_path_obj)
    assert response_data["owner_id"] == str(test_user_id_obj)

    mock_prepare_upload_filepath.assert_called_once_with(
        settings_obj=settings,
        current_user_id=test_user_id_obj,
        original_filename_optional=test_original_filename,
        content_type=test_content_type
    )
    mock_save_uploaded_file.assert_called_once() # Check arg File object and path
    mock_validate_file_type.assert_called_once()

    crud_call_kwargs = mock_crud_create_document.call_args.kwargs
    assert isinstance(crud_call_kwargs['document_data'], DocumentCreate)
    doc_create_arg: DocumentCreate = crud_call_kwargs['document_data']
    assert doc_create_arg.filename == test_safe_filename
    assert doc_create_arg.file_type == test_content_type
    assert doc_create_arg.size == test_file_size
    assert sorted(doc_create_arg.tags) == sorted(["tag1", "tag2"])
    assert crud_call_kwargs['owner_id'] == test_user_id_obj
    assert crud_call_kwargs['file_path'] == str(mock_file_path_obj)

@pytest.mark.asyncio
@patch("sortify.backend.app.utils.file_handling_utils.prepare_upload_filepath")
@patch("sortify.backend.app.utils.file_handling_utils.save_uploaded_file", new_callable=AsyncMock)
async def test_upload_document_file_save_error(
    mock_save_uploaded_file: AsyncMock,
    mock_prepare_upload_filepath: MagicMock,
    client: AsyncClient
):
    # Arrange
    mock_uuid_val = uuid.uuid4()
    mock_uuid_uuid4.return_value = mock_uuid_val

    mock_shutil_copyfileobj.side_effect = Exception("Disk full")
    
    mock_file_object = MagicMock()
    mock_file_object.close = MagicMock() 
    mock_builtin_open.return_value.__enter__.return_value = mock_file_object

    file_content = b"This is a test file."
    files_payload = {"file": ("test_error.txt", file_content, "text/plain")}
    form_data = {"uploader_device_id": "test_device_error"}

    # Act
    response = await client.post("/api/v1/documents/", files=files_payload, data=form_data)

    # Assert
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    response_data = response.json()
    assert "文件儲存失敗: Disk full" in response_data["detail"]
    
    expected_file_location = os.path.join(settings.UPLOAD_DIR, f"{mock_uuid_val}.txt")
    mock_builtin_open.assert_called_once_with(expected_file_location, "wb+")
    mock_shutil_copyfileobj.assert_called_once()

@pytest.mark.asyncio
@patch("sortify.backend.app.utils.file_handling_utils.prepare_upload_filepath")
@patch("sortify.backend.app.utils.file_handling_utils.save_uploaded_file", new_callable=AsyncMock)
@patch("sortify.backend.app.utils.file_handling_utils.validate_and_correct_file_type", new_callable=AsyncMock)
@patch("sortify.backend.app.apis.v1.documents.crud_documents.create_document", new_callable=AsyncMock)
@patch("sortify.backend.app.apis.v1.documents.os.remove") # This os.remove is called directly by the API route
@patch("sortify.backend.app.apis.v1.documents.os.path.exists") # This os.path.exists is called directly by the API route
async def test_upload_document_db_create_error(
    mock_os_path_exists: MagicMock, # Patched to sortify.backend.app.apis.v1.documents.os.path.exists
    mock_os_remove: MagicMock,       # Patched to sortify.backend.app.apis.v1.documents.os.remove
    mock_crud_create_document: AsyncMock,
    mock_validate_file_type: AsyncMock,
    mock_save_uploaded_file: AsyncMock,
    mock_prepare_upload_filepath: MagicMock,
    client: AsyncClient
):
    # Arrange
    test_original_filename = "db_error_file.txt"
    test_safe_filename = "db_error_file_safe.txt"
    test_content_type = "text/plain"
    test_file_size = 1024
    test_user_id_obj = uuid.uuid4()

    mock_current_user = User(id=test_user_id_obj, email="test@example.com", is_active=True, is_superuser=False, hashed_password="xxx")

    mock_upload_dir = Path(settings.UPLOAD_DIR)
    mock_file_path_obj = mock_upload_dir / test_safe_filename
    
    mock_prepare_upload_filepath.return_value = (mock_file_path_obj, test_safe_filename)
    mock_save_uploaded_file.return_value = test_file_size
    mock_validate_file_type.return_value = (test_content_type, None) # No warning
    
    # Simulate that the file was physically saved before DB error
    mock_os_path_exists.return_value = True # This mock is for the os.path.exists in the API's exception handler

    mock_crud_create_document.side_effect = Exception("DB connection error")

    file_content = b"This is a test file for db error."
    files_payload = {"file": (test_original_filename, file_content, test_content_type)}
    form_data = {} # Tags and other form data not critical for this error path

    with patch("sortify.backend.app.apis.v1.documents.get_current_active_user", return_value=mock_current_user):
        # Act
        response = await client.post("/api/v1/documents/", files=files_payload, data=form_data)

    # Assert
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    response_data = response.json()
    # The API endpoint wraps the DB error in a generic message.
    assert "創建文件記錄時發生內部錯誤" in response_data["detail"]

    mock_prepare_upload_filepath.assert_called_once()
    mock_save_uploaded_file.assert_called_once()
    mock_validate_file_type.assert_called_once()
    mock_crud_create_document.assert_called_once()

    # Check that the API tried to clean up the file using its direct os calls
    mock_os_path_exists.assert_called_once_with(str(mock_file_path_obj))
    mock_os_remove.assert_called_once_with(str(mock_file_path_obj))

# ----- Tests for GET / endpoint (list_documents) -----

@pytest.mark.asyncio
@patch("sortify.backend.app.apis.v1.documents.crud_documents.get_documents", new_callable=AsyncMock)
async def test_list_documents_no_filters(
    mock_crud_get_documents: AsyncMock,
    client: AsyncClient
):
    # Arrange
    fixed_datetime = datetime.now(timezone.utc).replace(microsecond=0)
    doc1_id = uuid.uuid4()
    doc2_id = uuid.uuid4()
    
    mock_docs = [
        Document(
            id=doc1_id, filename="file1.pdf", file_type="application/pdf", size=2048, 
            upload_date=fixed_datetime, status=DocumentStatus.UPLOADED, 
            uploader_device_id="dev1", file_path="/path/to/file1.pdf", tags=["work"]
        ),
        Document(
            id=doc2_id, filename="file2.txt", file_type="text/plain", size=1024, 
            upload_date=fixed_datetime, status=DocumentStatus.TEXT_EXTRACTED, 
            uploader_device_id="dev2", file_path="/path/to/file2.txt", tags=["personal"]
        )
    ]
    mock_crud_get_documents.return_value = mock_docs

    # Act
    response = await client.get("/api/v1/documents/?skip=0&limit=10")

    # Assert
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    assert len(response_data) == 2
    assert response_data[0]["id"] == str(doc1_id)
    assert response_data[0]["filename"] == "file1.pdf"
    assert response_data[1]["id"] == str(doc2_id)
    assert response_data[1]["filename"] == "file2.txt"
    
    mock_crud_get_documents.assert_called_once_with(
        db=await override_get_db_test(), # We need to pass the mock_db explicitly if it's used directly
        skip=0, 
        limit=10, 
        uploader_device_id=None, 
        status=None, 
        filename_contains=None,
        tags_include=None
    )

@pytest.mark.asyncio
@patch("sortify.backend.app.apis.v1.documents.crud_documents.get_documents", new_callable=AsyncMock)
async def test_list_documents_with_filters(
    mock_crud_get_documents: AsyncMock,
    client: AsyncClient
):
    # Arrange
    fixed_datetime = datetime.now(timezone.utc).replace(microsecond=0)
    doc_id = uuid.uuid4()
    mock_filtered_doc = Document(
        id=doc_id, filename="filtered_doc.jpg", file_type="image/jpeg", size=3000,
        upload_date=fixed_datetime, status=DocumentStatus.COMPLETED,
        uploader_device_id="filter_dev", file_path="/path/to/filtered.jpg", tags=["important", "project"]
    )
    mock_crud_get_documents.return_value = [mock_filtered_doc]
    
    query_params = {
        "skip": 5,
        "limit": 25,
        "uploader_device_id": "filter_dev",
        "status": DocumentStatus.COMPLETED.value,
        "filename_contains": "filtered",
        "tags_include": ["important", "project"]
    }

    # Act
    response = await client.get("/api/v1/documents/", params=query_params)

    # Assert
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    assert len(response_data) == 1
    assert response_data[0]["id"] == str(doc_id)
    assert response_data[0]["filename"] == "filtered_doc.jpg"

    mock_crud_get_documents.assert_called_once_with(
        db=await override_get_db_test(),
        skip=5,
        limit=25,
        uploader_device_id="filter_dev",
        status=DocumentStatus.COMPLETED,
        filename_contains="filtered",
        tags_include=["important", "project"]
    )

@pytest.mark.asyncio
@patch("sortify.backend.app.apis.v1.documents.crud_documents.get_documents", new_callable=AsyncMock)
async def test_list_documents_tags_include_single_tag(
    mock_crud_get_documents: AsyncMock,
    client: AsyncClient
):
    # Arrange
    mock_crud_get_documents.return_value = [] # The actual return value doesn't matter much for this call verification
    
    query_params = {
        "tags_include": "work" # Single tag
    }
    # Act
    await client.get("/api/v1/documents/", params=query_params)

    # Assert
    # The key is to check that the `tags_include` parameter in `crud_documents.get_documents`
    # is correctly passed as a list, even if only one tag is provided in the query.
    # FastAPI automatically converts single query parameters for List fields into a list with one item.
    mock_crud_get_documents.assert_called_once_with(
        db=await override_get_db_test(),
        skip=0, # default
        limit=20, # default
        uploader_device_id=None,
        status=None,
        filename_contains=None,
        tags_include=["work"] # Should be a list
    ) 

# ----- Tests for GET /{document_id} endpoint (get_document_details) -----

@pytest.mark.asyncio
@patch("sortify.backend.app.apis.v1.documents.crud_documents.get_document_by_id", new_callable=AsyncMock)
async def test_get_document_details_success(
    mock_crud_get_document_by_id: AsyncMock,
    client: AsyncClient
):
    # Arrange
    doc_id = uuid.uuid4()
    fixed_datetime = datetime.now(timezone.utc).replace(microsecond=0)
    mock_document = Document(
        id=doc_id,
        filename="detail_test.docx",
        file_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        size=5000,
        upload_date=fixed_datetime,
        status=DocumentStatus.PENDING_EXTRACTION,
        uploader_device_id="dev_detail",
        file_path=os.path.join(settings.UPLOAD_DIR, f"{uuid.uuid4()}.docx"),
        tags=["detail", "test"],
        extracted_text="Some pre-extracted text for detail.",
        summary="A summary for detail test.",
        analysis_results={"sentiment": "positive"},
        metadata={"author": "tester"}
    )
    mock_crud_get_document_by_id.return_value = mock_document

    # Act
    response = await client.get(f"/api/v1/documents/{doc_id}")

    # Assert
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    assert response_data["id"] == str(doc_id)
    assert response_data["filename"] == "detail_test.docx"
    assert response_data["file_type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert response_data["size"] == 5000
    assert response_data["upload_date"] == fixed_datetime.isoformat()
    assert response_data["status"] == DocumentStatus.PENDING_EXTRACTION.value
    assert response_data["uploader_device_id"] == "dev_detail"
    assert response_data["file_path"] == mock_document.file_path
    assert sorted(response_data["tags"]) == sorted(["detail", "test"])
    assert response_data["extracted_text"] == "Some pre-extracted text for detail."
    assert response_data["summary"] == "A summary for detail test."
    assert response_data["analysis_results"] == {"sentiment": "positive"}
    assert response_data["metadata"] == {"author": "tester"}

    mock_crud_get_document_by_id.assert_called_once_with(db=await override_get_db_test(), document_id=doc_id)

@pytest.mark.asyncio
@patch("sortify.backend.app.apis.v1.documents.crud_documents.get_document_by_id", new_callable=AsyncMock)
async def test_get_document_details_not_found(
    mock_crud_get_document_by_id: AsyncMock,
    client: AsyncClient
):
    # Arrange
    non_existent_doc_id = uuid.uuid4()
    mock_crud_get_document_by_id.return_value = None

    # Act
    response = await client.get(f"/api/v1/documents/{non_existent_doc_id}")

    # Assert
    assert response.status_code == status.HTTP_404_NOT_FOUND
    response_data = response.json()
    assert response_data["detail"] == f"ID 為 {non_existent_doc_id} 的文件不存在"
    mock_crud_get_document_by_id.assert_called_once_with(db=await override_get_db_test(), document_id=non_existent_doc_id)

# ----- Tests for GET /{document_id}/file endpoint (get_document_file) -----

@pytest.mark.asyncio
@patch("sortify.backend.app.apis.v1.documents.os.path.exists")
@patch("sortify.backend.app.apis.v1.documents.crud_documents.get_document_by_id", new_callable=AsyncMock)
async def test_get_document_file_success(
    mock_crud_get_document_by_id: AsyncMock,
    mock_os_path_exists: MagicMock,
    client: AsyncClient
):
    # Arrange
    doc_id = uuid.uuid4()
    file_content = b"Actual file content for download."
    file_name = "download_me.pdf"
    file_type = "application/pdf"
    # Ensure a unique filename for the dummy file to avoid clashes
    unique_dummy_filename = f"{uuid.uuid4()}_{file_name}"
    dummy_file_path = os.path.join(settings.UPLOAD_DIR, unique_dummy_filename)

    mock_document = Document(
        id=doc_id,
        filename=file_name,
        file_type=file_type,
        size=len(file_content),
        upload_date=datetime.now(timezone.utc),
        status=DocumentStatus.UPLOADED,
        file_path=dummy_file_path
    )
    mock_crud_get_document_by_id.return_value = mock_document
    mock_os_path_exists.return_value = True

    # Create the dummy file
    with open(dummy_file_path, "wb") as f:
        f.write(file_content)

    # Act
    response = await client.get(f"/api/v1/documents/{doc_id}/file")

    # Assert
    assert response.status_code == status.HTTP_200_OK
    assert response.content == file_content
    assert response.headers["content-type"] == file_type
    assert f'filename="{file_name}"' in response.headers["content-disposition"]

    mock_crud_get_document_by_id.assert_called_once_with(db=await override_get_db_test(), document_id=doc_id)
    mock_os_path_exists.assert_called_once_with(dummy_file_path)

    # Clean up the dummy file
    if os.path.exists(dummy_file_path):
        os.remove(dummy_file_path)

@pytest.mark.asyncio
@patch("sortify.backend.app.apis.v1.documents.crud_documents.get_document_by_id", new_callable=AsyncMock)
async def test_get_document_file_record_not_found(
    mock_crud_get_document_by_id: AsyncMock,
    client: AsyncClient
):
    # Arrange
    non_existent_doc_id = uuid.uuid4()
    mock_crud_get_document_by_id.return_value = None

    # Act
    response = await client.get(f"/api/v1/documents/{non_existent_doc_id}/file")

    # Assert
    assert response.status_code == status.HTTP_404_NOT_FOUND
    response_data = response.json()
    assert response_data["detail"] == f"ID 為 {non_existent_doc_id} 的文件記錄不存在"
    mock_crud_get_document_by_id.assert_called_once_with(db=await override_get_db_test(), document_id=non_existent_doc_id)

@pytest.mark.asyncio
@patch("sortify.backend.app.apis.v1.documents.crud_documents.get_document_by_id", new_callable=AsyncMock)
async def test_get_document_file_no_file_path_in_record(
    mock_crud_get_document_by_id: AsyncMock,
    client: AsyncClient
):
    # Arrange
    doc_id = uuid.uuid4()
    mock_document = Document(
        id=doc_id,
        filename="no_path.txt",
        file_type="text/plain",
        size=100,
        upload_date=datetime.now(timezone.utc),
        status=DocumentStatus.UPLOADED,
        file_path=None # No file_path
    )
    mock_crud_get_document_by_id.return_value = mock_document

    # Act
    response = await client.get(f"/api/v1/documents/{doc_id}/file")

    # Assert
    assert response.status_code == status.HTTP_404_NOT_FOUND
    response_data = response.json()
    assert response_data["detail"] == f"文件 {mock_document.filename} (ID: {doc_id}) 沒有記錄儲存路徑"
    mock_crud_get_document_by_id.assert_called_once_with(db=await override_get_db_test(), document_id=doc_id)

@pytest.mark.asyncio
@patch("sortify.backend.app.apis.v1.documents.os.path.exists")
@patch("sortify.backend.app.apis.v1.documents.crud_documents.get_document_by_id", new_callable=AsyncMock)
async def test_get_document_file_actual_file_not_found_on_disk(
    mock_crud_get_document_by_id: AsyncMock,
    mock_os_path_exists: MagicMock,
    client: AsyncClient
):
    # Arrange
    doc_id = uuid.uuid4()
    file_name = "disk_missing.dat"
    non_existent_path = os.path.join(settings.UPLOAD_DIR, "this_file_does_not_exist.dat")

    mock_document = Document(
        id=doc_id,
        filename=file_name,
        file_type="application/octet-stream",
        size=200,
        upload_date=datetime.now(timezone.utc),
        status=DocumentStatus.UPLOADED,
        file_path=non_existent_path
    )
    mock_crud_get_document_by_id.return_value = mock_document
    mock_os_path_exists.return_value = False # Simulate file not existing on disk

    # Act
    response = await client.get(f"/api/v1/documents/{doc_id}/file")

    # Assert
    assert response.status_code == status.HTTP_404_NOT_FOUND
    response_data = response.json()
    assert response_data["detail"] == f"文件 {file_name} (ID: {doc_id}) 在指定路徑 {non_existent_path} 未找到"

    mock_crud_get_document_by_id.assert_called_once_with(db=await override_get_db_test(), document_id=doc_id)
    mock_os_path_exists.assert_called_once_with(non_existent_path) 

# ----- Tests for PATCH /{document_id} endpoint (update_document_details) -----

@pytest.mark.asyncio
@patch("sortify.backend.app.apis.v1.documents.crud_documents.update_document_status", new_callable=AsyncMock)
@patch("sortify.backend.app.apis.v1.documents.crud_documents.update_document", new_callable=AsyncMock)
@patch("sortify.backend.app.apis.v1.documents.crud_documents.get_document_by_id", new_callable=AsyncMock)
async def test_update_document_details_success_update_fields(
    mock_get_doc_by_id: AsyncMock,
    mock_update_doc: AsyncMock,
    mock_update_status: AsyncMock, # Not used in this specific test but good for consistency
    client: AsyncClient
):
    # Arrange
    doc_id = uuid.uuid4()
    original_datetime = datetime.now(timezone.utc).replace(microsecond=123456)
    
    existing_document = Document(
        id=doc_id, filename="original.txt", file_type="text/plain", size=100,
        upload_date=original_datetime, status=DocumentStatus.UPLOADED,
        file_path="/path/original.txt", tags=["old_tag"]
    )
    mock_get_doc_by_id.return_value = existing_document

    updated_filename = "updated_filename.txt"
    updated_tags = ["new_tag1", "new_tag2"]
    updated_metadata = {"project": "Sortify"}
    
    # Simulate that the update_document crud function returns the updated document
    # In a real scenario, the datetime might be updated, or other fields could change
    # For this test, we focus on the fields being updated by the request
    updated_doc_from_crud = Document(
        id=doc_id, filename=updated_filename, file_type="text/plain", size=100,
        upload_date=original_datetime, # Assuming upload_date doesn't change on this type of update
        status=DocumentStatus.UPLOADED, # Status doesn't change without triggers
        file_path="/path/original.txt", # File path doesn't change
        tags=updated_tags,
        metadata=updated_metadata
    )
    mock_update_doc.return_value = updated_doc_from_crud

    update_payload = {
        "filename": updated_filename,
        "tags": updated_tags,
        "metadata": updated_metadata
    }

    # Act
    response = await client.patch(f"/api/v1/documents/{doc_id}", json=update_payload)

    # Assert
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    assert response_data["id"] == str(doc_id)
    assert response_data["filename"] == updated_filename
    assert sorted(response_data["tags"]) == sorted(updated_tags)
    assert response_data["metadata"] == updated_metadata
    assert response_data["status"] == DocumentStatus.UPLOADED.value # Status should remain unchanged

    mock_get_doc_by_id.assert_called_once_with(db=await override_get_db_test(), document_id=doc_id)
    mock_update_doc.assert_called_once()
    update_doc_call_args = mock_update_doc.call_args.args
    assert update_doc_call_args[1] == doc_id
    # Pydantic v2: doc_update.model_dump(exclude_unset=True) was used in API
    # So the dict passed to crud should only contain filename, tags, metadata
    assert update_doc_call_args[2] == update_payload 
    mock_update_status.assert_not_called() # No status change triggered

@pytest.mark.asyncio
@patch("sortify.backend.app.apis.v1.documents.crud_documents.get_document_by_id", new_callable=AsyncMock)
async def test_update_document_details_not_found(
    mock_get_doc_by_id: AsyncMock,
    client: AsyncClient
):
    # Arrange
    non_existent_doc_id = uuid.uuid4()
    mock_get_doc_by_id.return_value = None
    update_payload = {"filename": "wont_matter.txt"}

    # Act
    response = await client.patch(f"/api/v1/documents/{non_existent_doc_id}", json=update_payload)

    # Assert
    assert response.status_code == status.HTTP_404_NOT_FOUND
    response_data = response.json()
    assert f"ID 為 {non_existent_doc_id} 的文件不存在，無法更新" in response_data["detail"]
    mock_get_doc_by_id.assert_called_once_with(db=await override_get_db_test(), document_id=non_existent_doc_id)

@pytest.mark.asyncio
@patch("sortify.backend.app.apis.v1.documents.crud_documents.get_document_by_id", new_callable=AsyncMock)
async def test_update_document_no_update_data_or_trigger(
    mock_get_doc_by_id: AsyncMock,
    client: AsyncClient
):
    # Arrange
    doc_id = uuid.uuid4()
    existing_document = Document( # Need to mock this as it's fetched first
        id=doc_id, filename="file.txt", status=DocumentStatus.UPLOADED,
        file_path="/path/file.txt", upload_date=datetime.now(timezone.utc)
    )
    mock_get_doc_by_id.return_value = existing_document 
    update_payload = {} # Empty payload

    # Act
    response = await client.patch(f"/api/v1/documents/{doc_id}", json=update_payload)

    # Assert
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    response_data = response.json()
    assert "沒有提供任何更新數據或觸發操作" in response_data["detail"]
    mock_get_doc_by_id.assert_called_once_with(db=await override_get_db_test(), document_id=doc_id)

@pytest.mark.asyncio
@patch("sortify.backend.app.apis.v1.documents.BackgroundTasks.add_task")
@patch("sortify.backend.app.apis.v1.documents.crud_documents.update_document_status", new_callable=AsyncMock)
@patch("sortify.backend.app.apis.v1.documents.crud_documents.get_document_by_id", new_callable=AsyncMock)
async def test_update_document_trigger_content_processing(
    mock_get_doc_by_id: AsyncMock,
    mock_update_status: AsyncMock,
    mock_add_task: MagicMock,
    client: AsyncClient,
    # Re-add document_tasks_service when it's injected via Depends
    # For now, we mock the call path to its method if not using DI for service in test
):
    # Arrange
    doc_id = uuid.uuid4()
    test_user_id_obj = uuid.uuid4()
    mock_current_user = User(id=test_user_id_obj, email="test@example.com", is_active=True, is_superuser=False, hashed_password="xxx")

    existing_document = Document(
        id=doc_id, 
        filename="processable_doc.txt", 
        status=DocumentStatus.UPLOADED, # A status that allows processing
        file_path=os.path.join(settings.UPLOAD_DIR, "processable_doc.txt"), 
        owner_id=test_user_id_obj, # Ensure document is owned by mock_current_user
        upload_date=datetime.now(timezone.utc)
    )
    mock_get_doc_by_id.return_value = existing_document

    # Mock the document returned after status is updated to ANALYZING
    doc_after_status_update = Document(
        **existing_document.model_dump(exclude={'status'}), status=DocumentStatus.ANALYZING
    )
    mock_update_status.return_value = doc_after_status_update
    
    # Create a dummy file for os.path.exists check in the endpoint
    if not os.path.exists(settings.UPLOAD_DIR):
        os.makedirs(settings.UPLOAD_DIR)
    with open(existing_document.file_path, "w") as f:
        f.write("dummy content")

    update_payload = {
        "trigger_content_processing": True,
        "ai_model_preference": "test_model",
        "ai_ensure_chinese_output": False,
        "ai_max_output_tokens": 500
    }
    
    # Mock the DocumentTasksService instance and its method if it were injected via Depends
    # For now, the add_task will have the actual service method path
    # from sortify.backend.app.services.document_tasks_service import DocumentTasksService # Import for type
    
    # Path to the method that BackgroundTasks.add_task will call
    # This path is relative to where BackgroundTasks is used (i.e., documents.py)
    # and how DocumentTasksService is instantiated or injected.
    # Assuming get_document_tasks_service() returns a real instance,
    # we are checking that add_task is called with its method.
    
    with patch("sortify.backend.app.apis.v1.documents.get_current_active_user", return_value=mock_current_user), \
         patch("sortify.backend.app.apis.v1.documents.settings_di", return_value=settings): # Mock settings_di if needed by service
        # Act
        response = await client.patch(f"/api/v1/documents/{doc_id}", json=update_payload)

    # Assert
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    assert response_data["status"] == DocumentStatus.ANALYZING.value # Status updated

    mock_get_doc_by_id.assert_called_once_with(db=await override_get_db_test(), document_id=doc_id)
    mock_update_status.assert_called_once_with(db=await override_get_db_test(), document_id=doc_id, new_status=DocumentStatus.ANALYZING)
    
    mock_add_task.assert_called_once()
    args, kwargs = mock_add_task.call_args
    # args[0] should be document_tasks_service.process_document_content_analysis
    # For now, we can check the name or type if possible, or specific args
    assert args[0].__name__ == "process_document_content_analysis" # Check the method name

    # Check keyword arguments passed to process_document_content_analysis
    assert kwargs['doc_id'] == str(doc_id)
    # db is passed as a positional arg after the method, or as a kwarg.
    # Here, it's likely a positional arg to the task function itself, not a kwarg to add_task.
    # So, args[1] would be db, args[2] user_id etc. if we were to check all.
    # For this test, checking that it's called with the correct method and key parameters like doc_id is primary.
    assert kwargs['user_id_for_log'] == str(test_user_id_obj)
    assert kwargs['settings_obj'] == settings # Check if settings_di was passed correctly
    assert kwargs['ai_model_preference'] == "test_model"
    assert kwargs['ai_ensure_chinese_output'] is False
    assert kwargs['ai_max_output_tokens'] == 500

    # Clean up dummy file
    if os.path.exists(existing_document.file_path):
        os.remove(existing_document.file_path)

# ----- Tests for DELETE /{document_id} endpoint (delete_document_route) -----

@pytest.mark.asyncio
@patch("sortify.backend.app.apis.v1.documents.crud_documents.delete_document_by_id", new_callable=AsyncMock)
@patch("sortify.backend.app.apis.v1.documents.os.remove")
@patch("sortify.backend.app.apis.v1.documents.os.path.exists")
@patch("sortify.backend.app.apis.v1.documents.crud_documents.get_document_by_id", new_callable=AsyncMock)
async def test_delete_document_success(
    mock_get_doc_by_id: AsyncMock,
    mock_os_path_exists: MagicMock,
    mock_os_remove: MagicMock,
    mock_delete_doc_db: AsyncMock,
    client: AsyncClient
):
    # Arrange
    doc_id = uuid.uuid4()
    file_path_to_delete = os.path.join(settings.UPLOAD_DIR, f"{doc_id}_to_delete.dat")
    
    mock_document = Document(
        id=doc_id, filename="delete_me.dat", file_path=file_path_to_delete,
        upload_date=datetime.now(timezone.utc), status=DocumentStatus.UPLOADED, size=1
    )
    mock_get_doc_by_id.return_value = mock_document
    mock_os_path_exists.return_value = True # Simulate file exists on disk
    mock_delete_doc_db.return_value = True # Simulate DB deletion success

    # Act
    response = await client.delete(f"/api/v1/documents/{doc_id}")

    # Assert
    assert response.status_code == status.HTTP_204_NO_CONTENT
    mock_get_doc_by_id.assert_called_once_with(db=await override_get_db_test(), document_id=doc_id)
    mock_os_path_exists.assert_called_once_with(file_path_to_delete)
    mock_os_remove.assert_called_once_with(file_path_to_delete)
    mock_delete_doc_db.assert_called_once_with(db=await override_get_db_test(), document_id=doc_id)

@pytest.mark.asyncio
@patch("sortify.backend.app.apis.v1.documents.crud_documents.get_document_by_id", new_callable=AsyncMock)
async def test_delete_document_not_found(
    mock_get_doc_by_id: AsyncMock,
    client: AsyncClient
):
    # Arrange
    non_existent_doc_id = uuid.uuid4()
    mock_get_doc_by_id.return_value = None

    # Act
    response = await client.delete(f"/api/v1/documents/{non_existent_doc_id}")

    # Assert
    assert response.status_code == status.HTTP_404_NOT_FOUND
    response_data = response.json()
    assert f"ID 為 {non_existent_doc_id} 的文件不存在，無法刪除" in response_data["detail"]
    mock_get_doc_by_id.assert_called_once_with(db=await override_get_db_test(), document_id=non_existent_doc_id)

@pytest.mark.asyncio
@patch("sortify.backend.app.apis.v1.documents.crud_documents.delete_document_by_id", new_callable=AsyncMock)
@patch("sortify.backend.app.apis.v1.documents.os.remove")
@patch("sortify.backend.app.apis.v1.documents.os.path.exists")
@patch("sortify.backend.app.apis.v1.documents.crud_documents.get_document_by_id", new_callable=AsyncMock)
async def test_delete_document_file_deletion_os_error(
    mock_get_doc_by_id: AsyncMock,
    mock_os_path_exists: MagicMock,
    mock_os_remove: MagicMock,
    mock_delete_doc_db: AsyncMock,
    client: AsyncClient
):
    # Arrange
    doc_id = uuid.uuid4()
    file_path_to_delete = os.path.join(settings.UPLOAD_DIR, f"{doc_id}_os_error.dat")

    mock_document = Document(
        id=doc_id, filename="os_error_delete.dat", file_path=file_path_to_delete,
        upload_date=datetime.now(timezone.utc), status=DocumentStatus.UPLOADED, size=1
    )
    mock_get_doc_by_id.return_value = mock_document
    mock_os_path_exists.return_value = True
    mock_os_remove.side_effect = OSError("Permission denied") # Simulate OS error during file deletion
    mock_delete_doc_db.return_value = True # DB deletion still succeeds

    # Act
    response = await client.delete(f"/api/v1/documents/{doc_id}")

    # Assert
    # The API currently logs the OSError but still returns 204 if DB deletion is successful.
    assert response.status_code == status.HTTP_204_NO_CONTENT
    mock_get_doc_by_id.assert_called_once_with(db=await override_get_db_test(), document_id=doc_id)
    mock_os_path_exists.assert_called_once_with(file_path_to_delete)
    mock_os_remove.assert_called_once_with(file_path_to_delete)
    mock_delete_doc_db.assert_called_once_with(db=await override_get_db_test(), document_id=doc_id)
    # Add a check for the print statement if you have capturing setup for stdout, or use logging mock if API uses logging.

@pytest.mark.asyncio
@patch("sortify.backend.app.apis.v1.documents.crud_documents.delete_document_by_id", new_callable=AsyncMock)
@patch("sortify.backend.app.apis.v1.documents.os.remove") # os.remove might not be called if DB fails first or if file_path is None
@patch("sortify.backend.app.apis.v1.documents.os.path.exists") # os.path.exists might not be called either
@patch("sortify.backend.app.apis.v1.documents.crud_documents.get_document_by_id", new_callable=AsyncMock)
async def test_delete_document_db_deletion_fails(
    mock_get_doc_by_id: AsyncMock,
    mock_os_path_exists: MagicMock,
    mock_os_remove: MagicMock,
    mock_delete_doc_db: AsyncMock,
    client: AsyncClient
):
    # Arrange
    doc_id = uuid.uuid4()
    file_path_attempt_delete = os.path.join(settings.UPLOAD_DIR, f"{doc_id}_db_fail.dat")
    
    mock_document = Document(
        id=doc_id, filename="db_fail_delete.dat", file_path=file_path_attempt_delete,
        upload_date=datetime.now(timezone.utc), status=DocumentStatus.UPLOADED, size=1
    )
    mock_get_doc_by_id.return_value = mock_document
    mock_os_path_exists.return_value = True # Assume file exists
    mock_delete_doc_db.return_value = False # Simulate DB deletion failure

    # Act
    response = await client.delete(f"/api/v1/documents/{doc_id}")

    # Assert
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    response_data = response.json()
    assert f"從資料庫刪除 ID 為 {doc_id} 的文件記錄失敗" in response_data["detail"]
    
    mock_get_doc_by_id.assert_called_once_with(db=await override_get_db_test(), document_id=doc_id)
    # os.remove should have been called before the DB deletion attempt
    mock_os_path_exists.assert_called_once_with(file_path_attempt_delete)
    mock_os_remove.assert_called_once_with(file_path_attempt_delete)
    mock_delete_doc_db.assert_called_once_with(db=await override_get_db_test(), document_id=doc_id) 