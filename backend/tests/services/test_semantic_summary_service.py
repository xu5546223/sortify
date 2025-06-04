import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

from app.services.semantic_summary_service import SemanticSummaryService
from app.models.document_models import Document, DocumentAnalysis, VectorStatus
from app.models.vector_models import SemanticSummary, VectorRecord
from app.models.ai_models_simplified import AIDocumentAnalysisOutputDetail, AIDocumentKeyInformation

# Fixture for SemanticSummaryService instance
@pytest.fixture
def semantic_summary_service_instance():
    return SemanticSummaryService()

# Mock for database
@pytest.fixture
def mock_db():
    return AsyncMock()

# Mock for embedding_service
@pytest.fixture
def mock_embedding_service():
    mock = MagicMock()
    mock.encode_text = MagicMock(return_value=[0.1, 0.2, 0.3]) # Dummy vector
    mock.model_name = "test_embedding_model"
    return mock

# Mock for vector_db_service
@pytest.fixture
def mock_vector_db_service():
    mock = MagicMock()
    mock.delete_by_document_id = MagicMock()
    mock.insert_vectors = MagicMock(return_value=True)
    return mock

@pytest.mark.asyncio
async def test_text_to_embed_construction_all_fields(
    semantic_summary_service_instance: SemanticSummaryService,
    mock_db: AsyncMock,
    mock_embedding_service: MagicMock,
    mock_vector_db_service: MagicMock
):
    doc_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    key_info = AIDocumentKeyInformation(
        content_summary="This is the main summary.",
        searchable_keywords=["keyword1", "search term2"],
        semantic_tags=["tagA", "tagB"],
        knowledge_domains=["domainX", "domainY"],
        main_topics=["topic1", "topic2"],
        key_concepts=["concept Alpha", "concept Beta"]
    )
    doc_analysis = DocumentAnalysis(
        ai_analysis_output=AIDocumentAnalysisOutputDetail(key_information=key_info)
    )
    document = Document(id=doc_id, owner_id=owner_id, filename="test.txt", file_type="text/plain", analysis=doc_analysis, extracted_text="Some text.")

    # Mock generate_semantic_summary to return a summary with the full_ai_analysis
    mock_semantic_summary = SemanticSummary(
        document_id=str(doc_id),
        summary_text=key_info.content_summary, # or some other summary
        file_type=document.file_type,
        key_terms=key_info.semantic_tags, # or derived from it
        full_ai_analysis=doc_analysis.ai_analysis_output.model_dump() # Pass as dict
    )

    with patch('app.services.semantic_summary_service.embedding_service', mock_embedding_service), \
         patch('app.services.semantic_summary_service.vector_db_service', mock_vector_db_service), \
         patch('app.services.semantic_summary_service.update_document_vector_status', AsyncMock()) as mock_update_status, \
         patch.object(semantic_summary_service_instance, 'generate_semantic_summary', AsyncMock(return_value=mock_semantic_summary)) as mock_gen_summary:

        await semantic_summary_service_instance.process_document_for_vector_db(mock_db, document)

        mock_gen_summary.assert_called_once_with(mock_db, document)
        mock_vector_db_service.insert_vectors.assert_called_once()

        # Capture the VectorRecord passed to insert_vectors
        inserted_vector_record: VectorRecord = mock_vector_db_service.insert_vectors.call_args[0][0][0]
        text_to_embed = inserted_vector_record.chunk_text

        expected_parts = [
            "This is the main summary.",
            "keyword1 search term2",
            "tagA tagB",
            "domainX domainY",
            "topic1 topic2",
            "concept Alpha concept Beta"
        ]
        expected_text_to_embed = "\n".join(expected_parts)
        assert text_to_embed == expected_text_to_embed
        mock_update_status.assert_any_call(mock_db, doc_id, VectorStatus.VECTORIZED)

@pytest.mark.asyncio
async def test_text_to_embed_construction_some_fields(
    semantic_summary_service_instance: SemanticSummaryService,
    mock_db: AsyncMock,
    mock_embedding_service: MagicMock,
    mock_vector_db_service: MagicMock
):
    doc_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    key_info = AIDocumentKeyInformation(
        content_summary="Partial summary here.",
        searchable_keywords=["keyword_only"],
        # semantic_tags is missing
        knowledge_domains=[], # empty list
        main_topics=["main topic only"],
        # key_concepts is missing
    )
    doc_analysis = DocumentAnalysis(
        ai_analysis_output=AIDocumentAnalysisOutputDetail(key_information=key_info)
    )
    document = Document(id=doc_id, owner_id=owner_id, filename="partial.txt", file_type="text/plain", analysis=doc_analysis, extracted_text="Some text.")

    mock_semantic_summary = SemanticSummary(
        document_id=str(doc_id),
        summary_text=key_info.content_summary,
        file_type=document.file_type,
        full_ai_analysis=doc_analysis.ai_analysis_output.model_dump()
    )

    with patch('app.services.semantic_summary_service.embedding_service', mock_embedding_service), \
         patch('app.services.semantic_summary_service.vector_db_service', mock_vector_db_service), \
         patch('app.services.semantic_summary_service.update_document_vector_status', AsyncMock()), \
         patch.object(semantic_summary_service_instance, 'generate_semantic_summary', AsyncMock(return_value=mock_semantic_summary)):

        await semantic_summary_service_instance.process_document_for_vector_db(mock_db, document)

        inserted_vector_record: VectorRecord = mock_vector_db_service.insert_vectors.call_args[0][0][0]
        text_to_embed = inserted_vector_record.chunk_text

        expected_parts = [
            "Partial summary here.",
            "keyword_only",
            "main topic only"
        ]
        expected_text_to_embed = "\n".join(expected_parts)
        assert text_to_embed == expected_text_to_embed

@pytest.mark.asyncio
async def test_text_to_embed_fallback_to_semantic_summary_text(
    semantic_summary_service_instance: SemanticSummaryService,
    mock_db: AsyncMock,
    mock_embedding_service: MagicMock,
    mock_vector_db_service: MagicMock
):
    doc_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    # key_information in full_ai_analysis is empty or not present
    doc_analysis = DocumentAnalysis(
        ai_analysis_output=AIDocumentAnalysisOutputDetail(key_information=None) # No key_information
    )
    document = Document(id=doc_id, owner_id=owner_id, filename="fallback.txt", file_type="text/plain", analysis=doc_analysis, extracted_text="Some text.")

    # SemanticSummary.summary_text is present (e.g., from an older analysis or basic summary)
    mock_semantic_summary = SemanticSummary(
        document_id=str(doc_id),
        summary_text="This is the fallback summary text from SemanticSummary object.",
        file_type=document.file_type,
        full_ai_analysis=doc_analysis.ai_analysis_output.model_dump() # key_information is None here
    )

    with patch('app.services.semantic_summary_service.embedding_service', mock_embedding_service), \
         patch('app.services.semantic_summary_service.vector_db_service', mock_vector_db_service), \
         patch('app.services.semantic_summary_service.update_document_vector_status', AsyncMock()), \
         patch.object(semantic_summary_service_instance, 'generate_semantic_summary', AsyncMock(return_value=mock_semantic_summary)):

        await semantic_summary_service_instance.process_document_for_vector_db(mock_db, document)

        inserted_vector_record: VectorRecord = mock_vector_db_service.insert_vectors.call_args[0][0][0]
        text_to_embed = inserted_vector_record.chunk_text

        # Expected: uses semantic_summary.summary_text because key_information was empty
        expected_text_to_embed = "This is the fallback summary text from SemanticSummary object."
        assert text_to_embed == expected_text_to_embed

@pytest.mark.asyncio
async def test_text_to_embed_fallback_to_filename(
    semantic_summary_service_instance: SemanticSummaryService,
    mock_db: AsyncMock,
    mock_embedding_service: MagicMock,
    mock_vector_db_service: MagicMock
):
    doc_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    # All ai_analysis_output fields that contribute to text_parts are empty
    doc_analysis = DocumentAnalysis(
         ai_analysis_output=AIDocumentAnalysisOutputDetail(key_information=None)
    )
    # document.filename will be the only source
    document = Document(id=doc_id, owner_id=owner_id, filename="only_filename.doc", file_type="application/msword", analysis=doc_analysis, extracted_text="Text")

    # SemanticSummary also has no text
    mock_semantic_summary = SemanticSummary(
        document_id=str(doc_id),
        summary_text="", # Empty summary text
        file_type=document.file_type,
        full_ai_analysis=doc_analysis.ai_analysis_output.model_dump() # key_information is None
    )

    with patch('app.services.semantic_summary_service.embedding_service', mock_embedding_service), \
         patch('app.services.semantic_summary_service.vector_db_service', mock_vector_db_service), \
         patch('app.services.semantic_summary_service.update_document_vector_status', AsyncMock()), \
         patch.object(semantic_summary_service_instance, 'generate_semantic_summary', AsyncMock(return_value=mock_semantic_summary)):

        await semantic_summary_service_instance.process_document_for_vector_db(mock_db, document)

        inserted_vector_record: VectorRecord = mock_vector_db_service.insert_vectors.call_args[0][0][0]
        text_to_embed = inserted_vector_record.chunk_text

        # Expected: uses document.filename as the last resort
        expected_text_to_embed = "only_filename.doc"
        assert text_to_embed == expected_text_to_embed

@pytest.mark.asyncio
async def test_process_document_fails_if_summary_fails(
    semantic_summary_service_instance: SemanticSummaryService,
    mock_db: AsyncMock
):
    doc_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    document = Document(id=doc_id, owner_id=owner_id, filename="test.txt", file_type="text/plain")

    with patch('app.services.semantic_summary_service.update_document_vector_status', AsyncMock()) as mock_update_status, \
         patch.object(semantic_summary_service_instance, 'generate_semantic_summary', AsyncMock(return_value=None)) as mock_gen_summary: # Summary generation fails

        result = await semantic_summary_service_instance.process_document_for_vector_db(mock_db, document)

        assert result is False
        mock_gen_summary.assert_called_once_with(mock_db, document)
        mock_update_status.assert_any_call(mock_db, doc_id, VectorStatus.PROCESSING) # Initial status
        mock_update_status.assert_any_call(mock_db, doc_id, VectorStatus.FAILED, "語義摘要生成失敗") # Failure status
        # Ensure insert_vectors was NOT called
        # This requires mock_vector_db_service to be available or check its mock if it were patched globally
        # For this test, we are checking the early exit, so vector_db_service might not even be patched.

@pytest.mark.asyncio
async def test_process_document_fails_if_vector_insertion_fails(
    semantic_summary_service_instance: SemanticSummaryService,
    mock_db: AsyncMock,
    mock_embedding_service: MagicMock,
    # mock_vector_db_service is deliberately not used directly here to patch its method
):
    doc_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    key_info = AIDocumentKeyInformation(content_summary="Summary")
    doc_analysis = DocumentAnalysis(ai_analysis_output=AIDocumentAnalysisOutputDetail(key_information=key_info))
    document = Document(id=doc_id, owner_id=owner_id, filename="test.txt", file_type="text/plain", analysis=doc_analysis, extracted_text="Text")

    mock_semantic_summary = SemanticSummary(
        document_id=str(doc_id), summary_text="Summary", file_type=document.file_type,
        full_ai_analysis=doc_analysis.ai_analysis_output.model_dump()
    )

    # Patch vector_db_service.insert_vectors to return False (failure)
    with patch('app.services.semantic_summary_service.embedding_service', mock_embedding_service), \
         patch('app.services.semantic_summary_service.vector_db_service.insert_vectors', MagicMock(return_value=False)) as mock_insert_fail, \
         patch('app.services.semantic_summary_service.vector_db_service.delete_by_document_id', MagicMock()), \
         patch('app.services.semantic_summary_service.update_document_vector_status', AsyncMock()) as mock_update_status, \
         patch.object(semantic_summary_service_instance, 'generate_semantic_summary', AsyncMock(return_value=mock_semantic_summary)):

        result = await semantic_summary_service_instance.process_document_for_vector_db(mock_db, document)

        assert result is False
        mock_insert_fail.assert_called_once()
        mock_update_status.assert_any_call(mock_db, doc_id, VectorStatus.FAILED, "向量存儲失敗")
