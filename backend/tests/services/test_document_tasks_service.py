import pytest
import pytest_asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from sortify.backend.app.services.document_tasks_service import DocumentTasksService
from sortify.backend.app.models.document_models import Document, DocumentStatus
from sortify.backend.app.core.config import Settings

@pytest_asyncio.fixture
async def document_tasks_service():
    return DocumentTasksService()

@pytest_asyncio.fixture
async def mock_db():
    return AsyncMock()

@pytest_asyncio.fixture
async def mock_settings():
    settings_mock = MagicMock(spec=Settings)
    # Add any specific settings attributes needed by the service tests
    settings_mock.AI_MAX_INPUT_CHARS_TEXT_ANALYSIS = 10000 
    return settings_mock

# Tests for _setup_and_validate_document_for_processing
@pytest.mark.asyncio
@patch("sortify.backend.app.services.document_tasks_service.unified_ai_config.reload_task_configs", new_callable=AsyncMock)
@patch("sortify.backend.app.services.document_tasks_service.crud_documents.get_document_by_id", new_callable=AsyncMock)
@patch("sortify.backend.app.services.document_tasks_service.log_event", new_callable=AsyncMock) # Mock log_event
async def test_setup_validate_success(
    mock_log_event: AsyncMock, # Order matters for patchers
    mock_crud_get_doc: AsyncMock, 
    mock_reload_configs: AsyncMock, 
    document_tasks_service: DocumentTasksService, 
    mock_db: AsyncMock
):
    doc_id = uuid.uuid4()
    user_id = str(uuid.uuid4())
    mock_doc = Document(id=doc_id, owner_id=user_id, file_path="/fake/path/doc.pdf", status=DocumentStatus.UPLOADED, filename="doc.pdf", upload_date=MagicMock())
    mock_crud_get_doc.return_value = mock_doc
    
    with patch("sortify.backend.app.services.document_tasks_service.Path.exists", return_value=True):
        document = await document_tasks_service._setup_and_validate_document_for_processing(doc_id, mock_db, user_id, "req_id")

    assert document is not None
    assert document.id == doc_id
    mock_reload_configs.assert_called_once_with(mock_db)
    mock_crud_get_doc.assert_called_once_with(mock_db, doc_id)
    mock_log_event.assert_not_called() # No error log_events expected

@pytest.mark.asyncio
@patch("sortify.backend.app.services.document_tasks_service.unified_ai_config.reload_task_configs", new_callable=AsyncMock)
@patch("sortify.backend.app.services.document_tasks_service.crud_documents.get_document_by_id", new_callable=AsyncMock)
@patch("sortify.backend.app.services.document_tasks_service.log_event", new_callable=AsyncMock)
async def test_setup_validate_doc_not_found(
    mock_log_event: AsyncMock,
    mock_crud_get_doc: AsyncMock, 
    mock_reload_configs: AsyncMock, 
    document_tasks_service: DocumentTasksService, 
    mock_db: AsyncMock
):
    doc_id = uuid.uuid4()
    user_id = str(uuid.uuid4())
    mock_crud_get_doc.return_value = None # Simulate document not found

    document = await document_tasks_service._setup_and_validate_document_for_processing(doc_id, mock_db, user_id, "req_id")

    assert document is None
    mock_crud_get_doc.assert_called_once_with(mock_db, doc_id)
    mock_log_event.assert_called_once() # Expecting one error log_event call
    assert mock_log_event.call_args.kwargs['level'] == LogLevel.ERROR
    assert "文件記錄不存在" in mock_log_event.call_args.kwargs['message']

@pytest.mark.asyncio
@patch("sortify.backend.app.services.document_tasks_service.unified_ai_config.reload_task_configs", new_callable=AsyncMock)
@patch("sortify.backend.app.services.document_tasks_service.crud_documents.get_document_by_id", new_callable=AsyncMock)
@patch("sortify.backend.app.services.document_tasks_service.crud_documents.update_document_status", new_callable=AsyncMock)
@patch("sortify.backend.app.services.document_tasks_service.log_event", new_callable=AsyncMock)
async def test_setup_validate_no_file_path(
    mock_log_event: AsyncMock,
    mock_update_status: AsyncMock,
    mock_crud_get_doc: AsyncMock, 
    mock_reload_configs: AsyncMock, 
    document_tasks_service: DocumentTasksService, 
    mock_db: AsyncMock
):
    doc_id = uuid.uuid4()
    user_id = str(uuid.uuid4())
    mock_doc = Document(id=doc_id, owner_id=user_id, file_path=None, status=DocumentStatus.UPLOADED, filename="doc.pdf", upload_date=MagicMock()) # No file_path
    mock_crud_get_doc.return_value = mock_doc

    document = await document_tasks_service._setup_and_validate_document_for_processing(doc_id, mock_db, user_id, "req_id")

    assert document is None
    mock_crud_get_doc.assert_called_once_with(mock_db, doc_id)
    mock_update_status.assert_called_once_with(mock_db, doc_id, DocumentStatus.PROCESSING_ERROR, "文件記錄缺少路徑")
    mock_log_event.assert_called_once() 
    assert mock_log_event.call_args.kwargs['level'] == LogLevel.ERROR
    assert "文件記錄缺少路徑" in mock_log_event.call_args.kwargs['message']

@pytest.mark.asyncio
@patch("sortify.backend.app.services.document_tasks_service.unified_ai_config.reload_task_configs", new_callable=AsyncMock)
@patch("sortify.backend.app.services.document_tasks_service.crud_documents.get_document_by_id", new_callable=AsyncMock)
@patch("sortify.backend.app.services.document_tasks_service.crud_documents.update_document_status", new_callable=AsyncMock)
@patch("sortify.backend.app.services.document_tasks_service.log_event", new_callable=AsyncMock)
async def test_setup_validate_file_not_exists(
    mock_log_event: AsyncMock,
    mock_update_status: AsyncMock,
    mock_crud_get_doc: AsyncMock, 
    mock_reload_configs: AsyncMock, 
    document_tasks_service: DocumentTasksService, 
    mock_db: AsyncMock
):
    doc_id = uuid.uuid4()
    user_id = str(uuid.uuid4())
    mock_doc = Document(id=doc_id, owner_id=user_id, file_path="/fake/path/nonexistent.pdf", status=DocumentStatus.UPLOADED, filename="doc.pdf", upload_date=MagicMock())
    mock_crud_get_doc.return_value = mock_doc

    with patch("sortify.backend.app.services.document_tasks_service.Path.exists", return_value=False): # Simulate file does not exist
        document = await document_tasks_service._setup_and_validate_document_for_processing(doc_id, mock_db, user_id, "req_id")

    assert document is None
    mock_crud_get_doc.assert_called_once_with(mock_db, doc_id)
    mock_update_status.assert_called_once_with(mock_db, doc_id, DocumentStatus.PROCESSING_ERROR, "文件未找到，無法處理")
    mock_log_event.assert_called_once()
    assert mock_log_event.call_args.kwargs['level'] == LogLevel.ERROR
    assert "文件不存在" in mock_log_event.call_args.kwargs['message']

# Tests for _process_image_document
@pytest.mark.asyncio
@patch("sortify.backend.app.services.document_tasks_service.DocumentProcessingService")
@patch("sortify.backend.app.services.document_tasks_service.unified_ai_service_simplified.analyze_image", new_callable=AsyncMock)
@patch("sortify.backend.app.services.document_tasks_service.Image.open") # Mock PIL Image.open
async def test_process_image_document_success(
    mock_pil_image_open: MagicMock,
    mock_analyze_image: AsyncMock,
    mock_doc_processing_service_class: MagicMock,
    document_tasks_service: DocumentTasksService,
    mock_db: AsyncMock
):
    # Arrange
    doc_id = uuid.uuid4()
    user_id = str(uuid.uuid4())
    request_id = "req_image_success"
    file_path_str = "/fake/image.png"
    document = Document(id=doc_id, owner_id=user_id, file_path=file_path_str, file_type="image/png", status=DocumentStatus.ANALYZING, filename="image.png", upload_date=MagicMock())

    mock_dps_instance = AsyncMock()
    mock_dps_instance.get_image_bytes.return_value = b"fake_image_bytes"
    mock_doc_processing_service_class.return_value = mock_dps_instance

    mock_pil_image_open.return_value = MagicMock() # Dummy PIL image object

    ai_output_data = AIImageAnalysisOutput(initial_description="A cat", content_type="image/png")
    mock_analyze_image.return_value = MagicMock(
        success=True, 
        output_data=ai_output_data,
        token_usage=TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
        model_used="gemini-pro-vision"
    )

    # Act
    analysis_data, token_usage, model_used, status = await document_tasks_service._process_image_document(
        document, mock_db, user_id, request_id, ai_ensure_chinese_output=True
    )

    # Assert
    assert status == DocumentStatus.ANALYSIS_COMPLETED
    assert analysis_data == ai_output_data.model_dump()
    assert token_usage is not None
    assert token_usage.total_tokens == 30
    assert model_used == "gemini-pro-vision"
    mock_dps_instance.get_image_bytes.assert_called_once_with(file_path_str)
    mock_pil_image_open.assert_called_once_with(io.BytesIO(b"fake_image_bytes"))
    mock_analyze_image.assert_called_once() # Further check args if needed

@pytest.mark.asyncio
@patch("sortify.backend.app.services.document_tasks_service.DocumentProcessingService")
async def test_process_image_document_get_bytes_fails(
    mock_doc_processing_service_class: MagicMock,
    document_tasks_service: DocumentTasksService,
    mock_db: AsyncMock
):
    doc_id = uuid.uuid4()
    user_id = str(uuid.uuid4())
    document = Document(id=doc_id, owner_id=user_id, file_path="/fake/image.jpg", file_type="image/jpeg", status=DocumentStatus.ANALYZING, filename="image.jpg", upload_date=MagicMock())

    mock_dps_instance = AsyncMock()
    mock_dps_instance.get_image_bytes.return_value = None # Simulate failure
    mock_doc_processing_service_class.return_value = mock_dps_instance

    analysis_data, token_usage, model_used, status = await document_tasks_service._process_image_document(
        document, mock_db, user_id, "req_id", ai_ensure_chinese_output=True
    )
    assert status == DocumentStatus.PROCESSING_ERROR
    assert analysis_data is None
    assert token_usage is None
    assert model_used is None

@pytest.mark.asyncio
@patch("sortify.backend.app.services.document_tasks_service.DocumentProcessingService")
@patch("sortify.backend.app.services.document_tasks_service.unified_ai_service_simplified.analyze_image", new_callable=AsyncMock)
@patch("sortify.backend.app.services.document_tasks_service.Image.open")
async def test_process_image_document_ai_fails(
    mock_pil_image_open: MagicMock,
    mock_analyze_image: AsyncMock,
    mock_doc_processing_service_class: MagicMock,
    document_tasks_service: DocumentTasksService,
    mock_db: AsyncMock
):
    doc_id = uuid.uuid4()
    user_id = str(uuid.uuid4())
    document = Document(id=doc_id, owner_id=user_id, file_path="/fake/image.webp", file_type="image/webp", status=DocumentStatus.ANALYZING, filename="image.webp", upload_date=MagicMock())

    mock_dps_instance = AsyncMock()
    mock_dps_instance.get_image_bytes.return_value = b"fake_bytes"
    mock_doc_processing_service_class.return_value = mock_dps_instance
    mock_pil_image_open.return_value = MagicMock()
    
    mock_analyze_image.return_value = MagicMock(success=False, error_message="AI vision error", output_data=None)

    analysis_data, token_usage, model_used, status = await document_tasks_service._process_image_document(
        document, mock_db, user_id, "req_id", ai_ensure_chinese_output=True
    )
    assert status == DocumentStatus.ANALYSIS_FAILED
    assert analysis_data is None
    assert token_usage is None # Based on current _process_image_document, token_usage is None if AI fails
    assert model_used is None # Same for model_used

# Tests for _process_text_document
@pytest.mark.asyncio
@patch("sortify.backend.app.services.document_tasks_service.DocumentProcessingService")
@patch("sortify.backend.app.services.document_tasks_service.crud_documents.update_document_on_extraction_success", new_callable=AsyncMock)
@patch("sortify.backend.app.services.document_tasks_service.unified_ai_service_simplified.analyze_text", new_callable=AsyncMock)
async def test_process_text_document_success(
    mock_analyze_text: AsyncMock,
    mock_update_extraction_success: AsyncMock,
    mock_doc_processing_service_class: MagicMock,
    document_tasks_service: DocumentTasksService,
    mock_db: AsyncMock,
    mock_settings: Settings # Use the fixture
):
    # Arrange
    doc_id = uuid.uuid4()
    user_id = str(uuid.uuid4())
    request_id = "req_text_success"
    file_path_str = "/fake/document.pdf"
    document = Document(id=doc_id, owner_id=user_id, file_path=file_path_str, file_type="application/pdf", status=DocumentStatus.ANALYZING, filename="document.pdf", upload_date=MagicMock())
    extracted_text = "This is the extracted text from the document."

    mock_dps_instance = AsyncMock()
    mock_dps_instance.extract_text_from_document.return_value = (extracted_text, DocumentStatus.TEXT_EXTRACTED, None)
    mock_doc_processing_service_class.return_value = mock_dps_instance

    ai_output_data = AITextAnalysisOutput(initial_summary="Summary of text", content_type="text/plain")
    mock_analyze_text.return_value = MagicMock(
        success=True,
        output_data=ai_output_data,
        token_usage=TokenUsage(prompt_tokens=50, completion_tokens=100, total_tokens=150),
        model_used="gemini-pro"
    )

    # Act
    analysis_data, token_usage, model_used, status = await document_tasks_service._process_text_document(
        document, mock_db, user_id, request_id, mock_settings, ai_ensure_chinese_output=True
    )

    # Assert
    assert status == DocumentStatus.ANALYSIS_COMPLETED
    assert analysis_data == ai_output_data.model_dump()
    assert token_usage is not None
    assert token_usage.total_tokens == 150
    assert model_used == "gemini-pro"
    mock_dps_instance.extract_text_from_document.assert_called_once_with(file_path_str, ".pdf")
    mock_update_extraction_success.assert_called_once_with(mock_db, doc_id, extracted_text)
    mock_analyze_text.assert_called_once() # Further check args if needed

@pytest.mark.asyncio
@patch("sortify.backend.app.services.document_tasks_service.DocumentProcessingService")
@patch("sortify.backend.app.services.document_tasks_service.crud_documents.update_document_status", new_callable=AsyncMock)
@patch("sortify.backend.app.services.document_tasks_service.log_event", new_callable=AsyncMock)
async def test_process_text_document_extraction_fails(
    mock_log_event: AsyncMock,
    mock_update_status: AsyncMock,
    mock_doc_processing_service_class: MagicMock,
    document_tasks_service: DocumentTasksService,
    mock_db: AsyncMock,
    mock_settings: Settings
):
    doc_id = uuid.uuid4()
    user_id = str(uuid.uuid4())
    document = Document(id=doc_id, owner_id=user_id, file_path="/fake/doc.docx", file_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", status=DocumentStatus.ANALYZING, filename="doc.docx", upload_date=MagicMock())

    mock_dps_instance = AsyncMock()
    mock_dps_instance.extract_text_from_document.return_value = (None, DocumentStatus.EXTRACTION_FAILED, "Extraction error")
    mock_doc_processing_service_class.return_value = mock_dps_instance

    analysis_data, token_usage, model_used, status = await document_tasks_service._process_text_document(
        document, mock_db, user_id, "req_id", mock_settings, ai_ensure_chinese_output=True
    )
    assert status == DocumentStatus.EXTRACTION_FAILED
    assert analysis_data is None
    assert token_usage is None
    assert model_used is None
    mock_update_status.assert_called_once_with(mock_db, doc_id, DocumentStatus.EXTRACTION_FAILED, "Extraction error")
    mock_log_event.assert_called_once() # Check log_event details if necessary

@pytest.mark.asyncio
@patch("sortify.backend.app.services.document_tasks_service.DocumentProcessingService")
@patch("sortify.backend.app.services.document_tasks_service.crud_documents.update_document_on_extraction_success", new_callable=AsyncMock)
@patch("sortify.backend.app.services.document_tasks_service.unified_ai_service_simplified.analyze_text", new_callable=AsyncMock)
async def test_process_text_document_ai_analysis_fails(
    mock_analyze_text: AsyncMock,
    mock_update_extraction_success: AsyncMock,
    mock_doc_processing_service_class: MagicMock,
    document_tasks_service: DocumentTasksService,
    mock_db: AsyncMock,
    mock_settings: Settings
):
    doc_id = uuid.uuid4()
    user_id = str(uuid.uuid4())
    document = Document(id=doc_id, owner_id=user_id, file_path="/fake/doc.txt", file_type="text/plain", status=DocumentStatus.ANALYZING, filename="doc.txt", upload_date=MagicMock())
    extracted_text = "Some text"

    mock_dps_instance = AsyncMock()
    mock_dps_instance.extract_text_from_document.return_value = (extracted_text, DocumentStatus.TEXT_EXTRACTED, None)
    mock_doc_processing_service_class.return_value = mock_dps_instance

    mock_analyze_text.return_value = MagicMock(success=False, error_message="AI text error", output_data=None)

    analysis_data, token_usage, model_used, status = await document_tasks_service._process_text_document(
        document, mock_db, user_id, "req_id", mock_settings, ai_ensure_chinese_output=True
    )
    assert status == DocumentStatus.ANALYSIS_FAILED
    assert analysis_data is None
    assert token_usage is None
    assert model_used is None
    mock_update_extraction_success.assert_called_once() # Still called before AI fails

# TODO: Add test for text truncation in _process_text_document

# Tests for _save_analysis_results
@pytest.mark.asyncio
@patch("sortify.backend.app.services.document_tasks_service.crud_documents.set_document_analysis", new_callable=AsyncMock)
@patch("sortify.backend.app.services.document_tasks_service.crud_documents.update_document_status", new_callable=AsyncMock)
@patch("sortify.backend.app.services.document_tasks_service.log_event", new_callable=AsyncMock)
async def test_save_analysis_results_completed(
    mock_log_event: AsyncMock,
    mock_update_status: AsyncMock,
    mock_set_analysis: AsyncMock,
    document_tasks_service: DocumentTasksService,
    mock_db: AsyncMock
):
    doc_id = uuid.uuid4()
    user_id = str(uuid.uuid4())
    document = Document(id=doc_id, owner_id=user_id, file_path="dummy.txt", status=DocumentStatus.ANALYZING, filename="dummy.txt", upload_date=MagicMock())
    analysis_data = {"summary": "Test summary", "content_type": "text/plain"}
    token_usage_obj = TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30)
    model_used = "test_model"
    processing_status = DocumentStatus.ANALYSIS_COMPLETED
    processing_type = "text_analysis"

    await document_tasks_service._save_analysis_results(
        document, mock_db, user_id, "req_id", analysis_data, token_usage_obj, model_used, processing_status, processing_type
    )

    mock_set_analysis.assert_called_once_with(
        db=mock_db, document_id=doc_id, analysis_data_dict=analysis_data,
        token_usage_dict=token_usage_obj.model_dump(), model_used_str=model_used,
        analysis_status_enum=processing_status, analyzed_content_type_str="text/plain"
    )
    mock_update_status.assert_not_called()
    mock_log_event.assert_called_once()
    assert mock_log_event.call_args.kwargs['level'] == LogLevel.INFO

@pytest.mark.asyncio
@patch("sortify.backend.app.services.document_tasks_service.crud_documents.set_document_analysis", new_callable=AsyncMock)
@patch("sortify.backend.app.services.document_tasks_service.crud_documents.update_document_status", new_callable=AsyncMock)
@patch("sortify.backend.app.services.document_tasks_service.log_event", new_callable=AsyncMock)
async def test_save_analysis_results_failed_with_data(
    mock_log_event: AsyncMock,
    mock_update_status: AsyncMock,
    mock_set_analysis: AsyncMock,
    document_tasks_service: DocumentTasksService,
    mock_db: AsyncMock
):
    doc_id = uuid.uuid4()
    user_id = str(uuid.uuid4())
    document = Document(id=doc_id, owner_id=user_id, file_path="dummy.png", status=DocumentStatus.ANALYZING, filename="dummy.png", upload_date=MagicMock())
    analysis_data = {"error": "AI error", "content_type": "image/png"}
    token_usage_obj = TokenUsage(prompt_tokens=5, completion_tokens=0, total_tokens=5) # e.g. error before completion
    model_used = "test_model_vision"
    processing_status = DocumentStatus.ANALYSIS_FAILED
    processing_type = "image_analysis"

    await document_tasks_service._save_analysis_results(
        document, mock_db, user_id, "req_id", analysis_data, token_usage_obj, model_used, processing_status, processing_type
    )

    mock_set_analysis.assert_called_once_with(
        db=mock_db, document_id=doc_id, analysis_data_dict=analysis_data,
        token_usage_dict=token_usage_obj.model_dump(), model_used_str=model_used,
        analysis_status_enum=processing_status, analyzed_content_type_str="image/png"
    )
    mock_update_status.assert_not_called()
    mock_log_event.assert_called_once()
    assert mock_log_event.call_args.kwargs['level'] == LogLevel.ERROR


@pytest.mark.asyncio
@patch("sortify.backend.app.services.document_tasks_service.crud_documents.set_document_analysis", new_callable=AsyncMock)
@patch("sortify.backend.app.services.document_tasks_service.crud_documents.update_document_status", new_callable=AsyncMock)
@patch("sortify.backend.app.services.document_tasks_service.log_event", new_callable=AsyncMock)
async def test_save_analysis_results_processing_error_no_data(
    mock_log_event: AsyncMock,
    mock_update_status: AsyncMock,
    mock_set_analysis: AsyncMock,
    document_tasks_service: DocumentTasksService,
    mock_db: AsyncMock
):
    doc_id = uuid.uuid4()
    user_id = str(uuid.uuid4())
    document = Document(id=doc_id, owner_id=user_id, file_path="dummy.dat", status=DocumentStatus.ANALYZING, filename="dummy.dat", upload_date=MagicMock()) # Status was ANALYZING before this save
    processing_status = DocumentStatus.PROCESSING_ERROR # Now an error state
    processing_type = "unsupported_type"

    await document_tasks_service._save_analysis_results(
        document, mock_db, user_id, "req_id", None, None, None, processing_status, processing_type
    )

    mock_set_analysis.assert_not_called()
    mock_update_status.assert_called_once_with(mock_db, doc_id, processing_status, f"Processing concluded: {processing_status.value}")
    mock_log_event.assert_called_once()
    assert mock_log_event.call_args.kwargs['level'] == LogLevel.WARNING # Or ERROR depending on status

@pytest.mark.asyncio
@patch("sortify.backend.app.services.document_tasks_service.crud_documents.set_document_analysis", new_callable=AsyncMock)
@patch("sortify.backend.app.services.document_tasks_service.crud_documents.update_document_status", new_callable=AsyncMock)
@patch("sortify.backend.app.services.document_tasks_service.log_event", new_callable=AsyncMock)
async def test_save_analysis_results_unexpected_analyzing_state(
    mock_log_event: AsyncMock,
    mock_update_status: AsyncMock,
    mock_set_analysis: AsyncMock,
    document_tasks_service: DocumentTasksService,
    mock_db: AsyncMock
):
    doc_id = uuid.uuid4()
    user_id = str(uuid.uuid4())
    document = Document(id=doc_id, owner_id=user_id, file_path="dummy.dat", status=DocumentStatus.ANALYZING, filename="dummy.dat", upload_date=MagicMock())
    processing_status = DocumentStatus.ANALYZING # Status is still ANALYZING, but no data provided
    processing_type = "text_analysis"

    await document_tasks_service._save_analysis_results(
        document, mock_db, user_id, "req_id", None, None, None, processing_status, processing_type
    )

    mock_set_analysis.assert_not_called()
    mock_update_status.assert_called_once_with(mock_db, doc_id, DocumentStatus.PROCESSING_ERROR, "Unknown processing error or status not finalized correctly by helpers.")
    mock_log_event.assert_called_once()
    assert mock_log_event.call_args.kwargs['level'] == LogLevel.ERROR

# Tests for process_document_content_analysis
@pytest.mark.asyncio
async def test_process_document_content_analysis_setup_fails(
    document_tasks_service: DocumentTasksService, # Use the service fixture
    mock_db: AsyncMock,
    mock_settings: Settings
):
    doc_id_str = str(uuid.uuid4())
    user_id = str(uuid.uuid4())

    with patch.object(document_tasks_service, '_setup_and_validate_document_for_processing', new_callable=AsyncMock, return_value=None) as mock_setup, \
         patch.object(document_tasks_service, '_save_analysis_results', new_callable=AsyncMock) as mock_save: # Ensure save is not called if setup fails early

        await document_tasks_service.process_document_content_analysis(
            doc_id_str, mock_db, user_id, "req_id", mock_settings
        )

    mock_setup.assert_called_once()
    # mock_setup.assert_called_once_with(uuid.UUID(doc_id_str), mock_db, user_id, "req_id") # More specific check
    mock_save.assert_not_called()


@pytest.mark.asyncio
async def test_process_document_content_analysis_image_doc(
    document_tasks_service: DocumentTasksService,
    mock_db: AsyncMock,
    mock_settings: Settings
):
    doc_id = uuid.uuid4()
    doc_id_str = str(doc_id)
    user_id = str(uuid.uuid4())
    request_id = "req_img_proc"
    
    # Mock document returned by _setup_and_validate_document_for_processing
    mock_document = Document(
        id=doc_id, owner_id=user_id, file_path="/fake/image.png", 
        file_type="image/png", # Image type
        status=DocumentStatus.UPLOADED, filename="image.png", upload_date=MagicMock()
    )
    
    # Mock internal method calls
    with patch.object(document_tasks_service, '_setup_and_validate_document_for_processing', new_callable=AsyncMock, return_value=mock_document) as mock_setup, \
         patch.object(document_tasks_service, '_process_image_document', new_callable=AsyncMock, return_value=(MagicMock(), MagicMock(), "model", DocumentStatus.ANALYSIS_COMPLETED)) as mock_proc_img, \
         patch.object(document_tasks_service, '_process_text_document', new_callable=AsyncMock) as mock_proc_text, \
         patch.object(document_tasks_service, '_save_analysis_results', new_callable=AsyncMock) as mock_save:

        await document_tasks_service.process_document_content_analysis(
            doc_id_str, mock_db, user_id, request_id, mock_settings, 
            ai_model_preference="pref_model", ai_max_output_tokens=100
        )

    mock_setup.assert_called_once_with(doc_id, mock_db, user_id, request_id)
    mock_proc_img.assert_called_once()
    # Example of checking specific args passed to the mocked method:
    call_args_img = mock_proc_img.call_args.kwargs
    assert call_args_img['document'] == mock_document
    assert call_args_img['ai_model_preference'] == "pref_model"
    assert call_args_img['ai_max_output_tokens'] == 100

    mock_proc_text.assert_not_called()
    mock_save.assert_called_once() # Ensure results are saved

@pytest.mark.asyncio
async def test_process_document_content_analysis_text_doc(
    document_tasks_service: DocumentTasksService,
    mock_db: AsyncMock,
    mock_settings: Settings
):
    doc_id = uuid.uuid4()
    doc_id_str = str(doc_id)
    user_id = str(uuid.uuid4())
    request_id = "req_text_proc"

    mock_document = Document(
        id=doc_id, owner_id=user_id, file_path="/fake/doc.pdf", 
        file_type="application/pdf", # Text processable type
        status=DocumentStatus.UPLOADED, filename="doc.pdf", upload_date=MagicMock()
    )

    with patch.object(document_tasks_service, '_setup_and_validate_document_for_processing', new_callable=AsyncMock, return_value=mock_document) as mock_setup, \
         patch.object(document_tasks_service, '_process_image_document', new_callable=AsyncMock) as mock_proc_img, \
         patch.object(document_tasks_service, '_process_text_document', new_callable=AsyncMock, return_value=(MagicMock(), MagicMock(), "model_txt", DocumentStatus.ANALYSIS_COMPLETED)) as mock_proc_text, \
         patch.object(document_tasks_service, '_save_analysis_results', new_callable=AsyncMock) as mock_save:

        await document_tasks_service.process_document_content_analysis(
            doc_id_str, mock_db, user_id, request_id, mock_settings,
            ai_ensure_chinese_output=False
        )
    
    mock_setup.assert_called_once_with(doc_id, mock_db, user_id, request_id)
    mock_proc_text.assert_called_once()
    call_args_text = mock_proc_text.call_args.kwargs
    assert call_args_text['document'] == mock_document
    assert call_args_text['settings_obj'] == mock_settings
    assert call_args_text['ai_ensure_chinese_output'] is False

    mock_proc_img.assert_not_called()
    mock_save.assert_called_once()

@pytest.mark.asyncio
async def test_process_document_content_analysis_unsupported_type(
    document_tasks_service: DocumentTasksService,
    mock_db: AsyncMock,
    mock_settings: Settings
):
    doc_id = uuid.uuid4()
    doc_id_str = str(doc_id)
    user_id = str(uuid.uuid4())
    request_id = "req_unsupported"

    mock_document = Document(
        id=doc_id, owner_id=user_id, file_path="/fake/data.zip", 
        file_type="application/zip", # Unsupported type
        status=DocumentStatus.UPLOADED, filename="data.zip", upload_date=MagicMock()
    )

    with patch.object(document_tasks_service, '_setup_and_validate_document_for_processing', new_callable=AsyncMock, return_value=mock_document) as mock_setup, \
         patch.object(document_tasks_service, '_process_image_document', new_callable=AsyncMock) as mock_proc_img, \
         patch.object(document_tasks_service, '_process_text_document', new_callable=AsyncMock) as mock_proc_text, \
         patch.object(document_tasks_service, '_save_analysis_results', new_callable=AsyncMock) as mock_save:

        await document_tasks_service.process_document_content_analysis(
            doc_id_str, mock_db, user_id, request_id, mock_settings
        )

    mock_setup.assert_called_once_with(doc_id, mock_db, user_id, request_id)
    mock_proc_img.assert_not_called()
    mock_proc_text.assert_not_called()
    mock_save.assert_called_once()
    # Check that save was called with PROCESSING_ERROR for unsupported type
    args, kwargs = mock_save.call_args
    assert kwargs['processing_status'] == DocumentStatus.PROCESSING_ERROR
    assert kwargs['processing_type'] == "unsupported"


@pytest.mark.asyncio
async def test_process_document_content_analysis_processing_exception(
    document_tasks_service: DocumentTasksService,
    mock_db: AsyncMock,
    mock_settings: Settings
):
    doc_id = uuid.uuid4()
    doc_id_str = str(doc_id)
    user_id = str(uuid.uuid4())
    request_id = "req_exception"

    mock_document = Document(
        id=doc_id, owner_id=user_id, file_path="/fake/image.png", 
        file_type="image/png", status=DocumentStatus.UPLOADED, filename="image.png", upload_date=MagicMock()
    )

    with patch.object(document_tasks_service, '_setup_and_validate_document_for_processing', new_callable=AsyncMock, return_value=mock_document) as mock_setup, \
         patch.object(document_tasks_service, '_process_image_document', new_callable=AsyncMock, side_effect=Exception("Unexpected processing error")) as mock_proc_img, \
         patch.object(document_tasks_service, '_save_analysis_results', new_callable=AsyncMock) as mock_save:

        await document_tasks_service.process_document_content_analysis(
            doc_id_str, mock_db, user_id, request_id, mock_settings
        )
    
    mock_setup.assert_called_once()
    mock_proc_img.assert_called_once() # It was called and raised an exception
    mock_save.assert_called_once()
    args, kwargs = mock_save.call_args
    assert kwargs['processing_status'] == DocumentStatus.PROCESSING_ERROR
    assert kwargs['analysis_data'] is None # Because an exception occurred before data could be formed

# Tests for trigger_document_analysis
@pytest.mark.asyncio
async def test_trigger_document_analysis_setup_fails(
    document_tasks_service: DocumentTasksService, mock_db: AsyncMock, mock_settings: Settings
):
    doc_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_doc_processor = AsyncMock(spec=DocumentProcessingService)

    with patch.object(document_tasks_service, '_setup_and_validate_document_for_processing', new_callable=AsyncMock, return_value=None) as mock_setup, \
         patch.object(document_tasks_service, '_save_analysis_results', new_callable=AsyncMock) as mock_save:
        
        with pytest.raises(HTTPException) as exc_info:
            await document_tasks_service.trigger_document_analysis(
                mock_db, mock_doc_processor, doc_id, user_id, mock_settings
            )
        
        assert exc_info.value.status_code == 404 # From the raise in trigger_document_analysis
        assert f"Document {doc_id} not found or setup failed" in exc_info.value.detail

    mock_setup.assert_called_once_with(doc_id, mock_db, str(user_id), None) # request_id is None by default
    mock_save.assert_not_called()


@pytest.mark.asyncio
async def test_trigger_document_analysis_owner_mismatch(
    document_tasks_service: DocumentTasksService, mock_db: AsyncMock, mock_settings: Settings
):
    doc_id = uuid.uuid4()
    actual_owner_id = uuid.uuid4()
    requesting_user_id = uuid.uuid4() # Different user
    mock_doc_processor = AsyncMock(spec=DocumentProcessingService)

    mock_document = Document(id=doc_id, owner_id=actual_owner_id, file_path="/path.txt", status=DocumentStatus.UPLOADED, filename="file.txt", upload_date=MagicMock())

    with patch.object(document_tasks_service, '_setup_and_validate_document_for_processing', new_callable=AsyncMock, return_value=mock_document) as mock_setup, \
         patch.object(document_tasks_service, '_save_analysis_results', new_callable=AsyncMock) as mock_save:

        with pytest.raises(HTTPException) as exc_info:
            await document_tasks_service.trigger_document_analysis(
                mock_db, mock_doc_processor, doc_id, requesting_user_id, mock_settings
            )
        
        assert exc_info.value.status_code == 403 # Forbidden
        assert "無權限分析此文件" in exc_info.value.detail
    
    mock_setup.assert_called_once()
    mock_save.assert_not_called() # Should not be called if permission denied early


@pytest.mark.asyncio
@patch("sortify.backend.app.services.document_tasks_service.crud_documents.update_document_status", new_callable=AsyncMock)
@patch("sortify.backend.app.services.document_tasks_service.unified_ai_service_simplified.process_request", new_callable=AsyncMock)
@patch("sortify.backend.app.services.document_tasks_service.crud_documents.get_document_by_id", new_callable=AsyncMock) # For the final fetch
async def test_trigger_document_analysis_image_success(
    mock_get_doc_final: AsyncMock,
    mock_ai_process_request: AsyncMock,
    mock_update_status_crud: AsyncMock,
    document_tasks_service: DocumentTasksService,
    mock_db: AsyncMock, 
    mock_settings: Settings
):
    doc_id = uuid.uuid4()
    user_id = uuid.uuid4()
    request_id = "req_trigger_img_succ"
    file_path_str = "/fake/trigger_image.png"
    
    mock_doc_processor = AsyncMock(spec=DocumentProcessingService)
    mock_doc_processor.get_image_bytes.return_value = b"fake_trigger_bytes"

    # Initial document state (after _setup_and_validate_document_for_processing)
    initial_document = Document(id=doc_id, owner_id=user_id, file_path=file_path_str, file_type="image/png", 
                                status=DocumentStatus.UPLOADED, filename="trigger_image.png", upload_date=MagicMock())
    
    # Document state after analysis (returned by the final get_document_by_id)
    final_analyzed_document = Document(id=doc_id, owner_id=user_id, file_path=file_path_str, file_type="image/png", 
                                       status=DocumentStatus.ANALYSIS_COMPLETED, filename="trigger_image.png", upload_date=MagicMock(),
                                       analysis=MagicMock()) # Simplified analysis mock
    mock_get_doc_final.return_value = final_analyzed_document
    
    # Mock AI response
    ai_output_obj = AIImageAnalysisOutput(initial_description="triggered cat", content_type="image/png")
    mock_ai_process_request.return_value = MagicMock(
        success=True, output_data=ai_output_obj,
        token_usage=TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2), model_used="triggered-vision"
    )

    with patch.object(document_tasks_service, '_setup_and_validate_document_for_processing', new_callable=AsyncMock, return_value=initial_document) as mock_setup, \
         patch("sortify.backend.app.services.document_tasks_service.Image.open"), \
         patch.object(document_tasks_service, '_save_analysis_results', new_callable=AsyncMock) as mock_save_results:

        returned_document = await document_tasks_service.trigger_document_analysis(
            mock_db, mock_doc_processor, doc_id, user_id, mock_settings, request_id=request_id, task_type_str="IMAGE_ANALYSIS"
        )

    assert returned_document == final_analyzed_document
    mock_setup.assert_called_once_with(doc_id, mock_db, str(user_id), request_id)
    mock_update_status_crud.assert_called_once_with(mock_db, doc_id, DocumentStatus.ANALYZING, "Analysis triggered by service (trigger_document_analysis).")
    mock_doc_processor.get_image_bytes.assert_called_once_with(file_path_str)
    mock_ai_process_request.assert_called_once()
    
    # Assert that _save_analysis_results was called correctly
    mock_save_results.assert_called_once()
    save_args, save_kwargs = mock_save_results.call_args
    assert save_kwargs['document'] == initial_document # Document before status change by this method
    assert save_kwargs['analysis_data'] == ai_output_obj.model_dump()
    assert save_kwargs['processing_status'] == DocumentStatus.ANALYSIS_COMPLETED
    assert save_kwargs['processing_type'] == "image_analysis_triggered"

    mock_get_doc_final.assert_called_once_with(mock_db, doc_id)


@pytest.mark.asyncio
@patch("sortify.backend.app.services.document_tasks_service.crud_documents.update_document_status", new_callable=AsyncMock)
@patch("sortify.backend.app.services.document_tasks_service.unified_ai_service_simplified.process_request", new_callable=AsyncMock)
@patch("sortify.backend.app.services.document_tasks_service.crud_documents.get_document_by_id", new_callable=AsyncMock)
@patch("sortify.backend.app.services.document_tasks_service.crud_documents.update_document_on_extraction_success", new_callable=AsyncMock)
async def test_trigger_document_analysis_text_needs_extraction_success(
    mock_update_extraction_crud: AsyncMock,
    mock_get_doc_final: AsyncMock,
    mock_ai_process_request: AsyncMock,
    mock_update_status_crud: AsyncMock,
    document_tasks_service: DocumentTasksService,
    mock_db: AsyncMock, 
    mock_settings: Settings
):
    doc_id = uuid.uuid4()
    user_id = uuid.uuid4()
    file_path_str = "/fake/trigger_doc.pdf"
    
    mock_doc_processor = AsyncMock(spec=DocumentProcessingService)
    extracted_text_content = "Text extracted by trigger."
    mock_doc_processor.extract_text_from_document.return_value = (extracted_text_content, DocumentStatus.TEXT_EXTRACTED, None)

    initial_document = Document(id=doc_id, owner_id=user_id, file_path=file_path_str, file_type="application/pdf", 
                                status=DocumentStatus.UPLOADED, filename="trigger_doc.pdf", extracted_text=None, upload_date=MagicMock()) # No pre-extracted text
    
    final_analyzed_document = Document(id=doc_id, owner_id=user_id, file_path=file_path_str, file_type="application/pdf", 
                                       status=DocumentStatus.ANALYSIS_COMPLETED, filename="trigger_doc.pdf", 
                                       extracted_text=extracted_text_content, analysis=MagicMock(), upload_date=MagicMock())
    mock_get_doc_final.return_value = final_analyzed_document
    
    ai_output_obj = AITextAnalysisOutput(initial_summary="triggered summary", content_type="text/plain")
    mock_ai_process_request.return_value = MagicMock(
        success=True, output_data=ai_output_obj,
        token_usage=TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2), model_used="triggered-text"
    )

    with patch.object(document_tasks_service, '_setup_and_validate_document_for_processing', new_callable=AsyncMock, return_value=initial_document) as mock_setup, \
         patch.object(document_tasks_service, '_save_analysis_results', new_callable=AsyncMock) as mock_save_results:

        returned_document = await document_tasks_service.trigger_document_analysis(
            mock_db, mock_doc_processor, doc_id, user_id, mock_settings, task_type_str="TEXT_GENERATION"
        )

    assert returned_document == final_analyzed_document
    mock_setup.assert_called_once()
    mock_doc_processor.extract_text_from_document.assert_called_once_with(file_path_str, ".pdf")
    mock_update_extraction_crud.assert_called_once_with(mock_db, doc_id, extracted_text_content)
    mock_ai_process_request.assert_called_once()
    mock_save_results.assert_called_once()
    assert mock_save_results.call_args.kwargs['processing_status'] == DocumentStatus.ANALYSIS_COMPLETED
    assert mock_save_results.call_args.kwargs['processing_type'] == "text_analysis_triggered"

@pytest.mark.asyncio
async def test_trigger_document_analysis_ai_call_fails(
    document_tasks_service: DocumentTasksService, mock_db: AsyncMock, mock_settings: Settings
):
    doc_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_doc_processor = AsyncMock(spec=DocumentProcessingService)
    initial_document = Document(id=doc_id, owner_id=user_id, file_path="/path.txt", file_type="text/plain", 
                                status=DocumentStatus.UPLOADED, filename="file.txt", extracted_text="some text", upload_date=MagicMock())

    mock_ai_response = MagicMock(success=False, error_message="AI exploded", output_data=None, token_usage=None, model_used=None)

    with patch.object(document_tasks_service, '_setup_and_validate_document_for_processing', new_callable=AsyncMock, return_value=initial_document), \
         patch("sortify.backend.app.services.document_tasks_service.unified_ai_service_simplified.process_request", new_callable=AsyncMock, return_value=mock_ai_response) as mock_process_req, \
         patch.object(document_tasks_service, '_save_analysis_results', new_callable=AsyncMock) as mock_save, \
         patch("sortify.backend.app.services.document_tasks_service.crud_documents.get_document_by_id", new_callable=AsyncMock, return_value=initial_document) as mock_get_final_doc: # Simulate doc re-fetch

        returned_document = await document_tasks_service.trigger_document_analysis(
            mock_db, mock_doc_processor, doc_id, user_id, mock_settings, task_type_str="TEXT_GENERATION"
        )
    
    mock_process_req.assert_called_once()
    mock_save.assert_called_once()
    assert mock_save.call_args.kwargs['processing_status'] == DocumentStatus.ANALYSIS_FAILED
    assert mock_save.call_args.kwargs['analysis_data'] == {"error": "AI exploded"}
    assert returned_document is not None # Should return the document even if AI failed, with status updated
    mock_get_final_doc.assert_called_once()


# Example of how to test text truncation would require more specific setup
# @pytest.mark.asyncio
# async def test_process_text_document_truncation(
#     document_tasks_service: DocumentTasksService, 
#     mock_db: AsyncMock, 
#     mock_settings: Settings # Settings fixture
# ):
#     # Arrange
#     doc_id = uuid.uuid4()
#     user_id = str(uuid.uuid4())
#     document = Document(id=doc_id, owner_id=user_id, file_path="/fake/longtext.txt", file_type="text/plain", status=DocumentStatus.ANALYZING, filename="longtext.txt")
    
#     very_long_text = "a" * (mock_settings.AI_MAX_INPUT_CHARS_TEXT_ANALYSIS + 100)
#     truncated_text = very_long_text[:mock_settings.AI_MAX_INPUT_CHARS_TEXT_ANALYSIS]

#     mock_dps_instance = AsyncMock()
#     mock_dps_instance.extract_text_from_document.return_value = (very_long_text, DocumentStatus.TEXT_EXTRACTED, None)
    
#     ai_output_data = AITextAnalysisOutput(initial_summary="Summary", content_type="text/plain")
#     mock_ai_response = MagicMock(success=True, output_data=ai_output_data, token_usage=MagicMock(), model_used="test")

#     with patch("sortify.backend.app.services.document_tasks_service.DocumentProcessingService", return_value=mock_dps_instance), \
#          patch("sortify.backend.app.services.document_tasks_service.crud_documents.update_document_on_extraction_success", new_callable=AsyncMock), \
#          patch("sortify.backend.app.services.document_tasks_service.unified_ai_service_simplified.analyze_text", new_callable=AsyncMock, return_value=mock_ai_response) as mock_analyze_text_call:
        
#         await document_tasks_service._process_text_document(
#             document, mock_db, user_id, "req_id_truncate", mock_settings, ai_ensure_chinese_output=True
#         )
#     mock_analyze_text_call.assert_called_once()
#     called_with_text = mock_analyze_text_call.call_args.kwargs.get('text')
#     assert called_with_text == truncated_text
#     assert len(called_with_text) == mock_settings.AI_MAX_INPUT_CHARS_TEXT_ANALYSIS
