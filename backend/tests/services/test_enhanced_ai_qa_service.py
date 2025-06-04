import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from cachetools import LRUCache
import uuid

from app.services.enhanced_ai_qa_service import EnhancedAIQAService
from app.models.vector_models import QueryRewriteResult, SemanticSearchResult, AIQARequest
from app.services.embedding_service import embedding_service # Direct import for patching its methods
from app.services.vector_db_service import vector_db_service # Direct import for patching its methods

# Mock for database
@pytest.fixture
def mock_db_for_qa(): # Renamed to avoid conflict if other db mocks exist
    return AsyncMock()

# Fixture to provide an instance of EnhancedAIQAService
# This ensures each test gets a fresh instance with an empty cache
@pytest.fixture
def qa_service_instance():
    return EnhancedAIQAService()

@pytest.mark.asyncio
async def test_semantic_search_multiple_queries_deduplication_and_sorting(
    qa_service_instance: EnhancedAIQAService,
    mock_db_for_qa: AsyncMock
):
    queries = ["query1", "query2"]
    mock_qrr = QueryRewriteResult(original_query="test", rewritten_queries=queries, extracted_parameters={})

    # Mock embedding_service.encode_text
    # encode_text needs to be a sync function based on its usage in the service
    mock_encode_text = MagicMock()
    def encode_text_side_effect(query_text):
        if query_text == "query1": return [0.1, 0.1, 0.1]
        if query_text == "query2": return [0.2, 0.2, 0.2]
        return [0.0, 0.0, 0.0]
    mock_encode_text.side_effect = encode_text_side_effect

    # Mock vector_db_service.search_similar_vectors
    # search_similar_vectors needs to be a sync function
    mock_search_vectors = MagicMock()
    results_q1 = [
        SemanticSearchResult(document_id="doc1", similarity_score=0.9, summary_text="text1", metadata={}),
        SemanticSearchResult(document_id="doc2", similarity_score=0.8, summary_text="text2", metadata={}),
    ]
    results_q2 = [
        SemanticSearchResult(document_id="doc2", similarity_score=0.85, summary_text="text2 new score", metadata={}), # Overlapping doc2 with higher score
        SemanticSearchResult(document_id="doc3", similarity_score=0.75, summary_text="text3", metadata={}),
    ]
    def search_vectors_side_effect(query_vector, top_k, similarity_threshold, owner_id_filter, metadata_filter):
        if query_vector == [0.1, 0.1, 0.1]: return results_q1
        if query_vector == [0.2, 0.2, 0.2]: return results_q2
        return []
    mock_search_vectors.side_effect = search_vectors_side_effect

    with patch('app.services.enhanced_ai_qa_service.embedding_service.encode_text', mock_encode_text), \
         patch('app.services.enhanced_ai_qa_service.vector_db_service.search_similar_vectors', mock_search_vectors):

        combined_results = await qa_service_instance._semantic_search(
            db=mock_db_for_qa,
            queries=queries,
            top_k=3,
            query_rewrite_result=mock_qrr # Passed for potential metadata filter, though not main focus here
        )

    mock_encode_text.assert_any_call("query1")
    mock_encode_text.assert_any_call("query2")
    assert mock_encode_text.call_count == 2 # Called for each unique query

    assert len(combined_results) == 3
    # Expected order: doc1 (0.9 from q1), doc2 (0.85 from q2), doc3 (0.75 from q2)
    assert combined_results[0].document_id == "doc1"
    assert combined_results[0].similarity_score == 0.9
    assert combined_results[1].document_id == "doc2"
    assert combined_results[1].similarity_score == 0.85 # Higher score from q2 kept
    assert combined_results[1].summary_text == "text2 new score" # Ensure metadata from higher score result is kept
    assert combined_results[2].document_id == "doc3"
    assert combined_results[2].similarity_score == 0.75


@pytest.mark.asyncio
async def test_semantic_search_embedding_cache(
    qa_service_instance: EnhancedAIQAService,
    mock_db_for_qa: AsyncMock
):
    test_query = "test query for cache"

    # Mock embedding_service.encode_text
    mock_encode_text = MagicMock(return_value=[0.5, 0.5, 0.5])
    # Mock vector_db_service.search_similar_vectors
    mock_search_vectors = MagicMock(return_value=[
        SemanticSearchResult(document_id="doc_cache", similarity_score=0.7, summary_text="cached_text", metadata={})
    ])

    with patch('app.services.enhanced_ai_qa_service.embedding_service.encode_text', mock_encode_text), \
         patch('app.services.enhanced_ai_qa_service.vector_db_service.search_similar_vectors', mock_search_vectors):

        # First call - should encode and cache
        await qa_service_instance._semantic_search(mock_db_for_qa, queries=[test_query, test_query], top_k=3)
        mock_encode_text.assert_called_once_with(test_query.strip()) # Called only once due to batch pre-check or first encounter
        assert mock_search_vectors.call_count == 2 # Search called for each query in the list

        # Reset call count for encode_text for the next assertion
        mock_encode_text.reset_mock()
        mock_search_vectors.reset_mock()

        # Second call with the same query - should use cache for "test query"
        await qa_service_instance._semantic_search(mock_db_for_qa, queries=["another query", test_query], top_k=3)
        # encode_text should only be called for "another query"
        mock_encode_text.assert_called_once_with("another query")
        assert mock_search_vectors.call_count == 2


@pytest.mark.asyncio
async def test_semantic_search_batch_embedding_attempt(
    qa_service_instance: EnhancedAIQAService,
    mock_db_for_qa: AsyncMock
):
    queries_to_test = ["unique_query1", "unique_query2", "unique_query1"] # Contains duplicate

    # Mock embedding_service methods
    mock_encode_batch = MagicMock(return_value=[[0.1,0.1],[0.2,0.2]]) # For "unique_query1", "unique_query2"
    mock_encode_text = MagicMock() # Should not be called if batching works for all new queries

    # Mock vector_db_service.search_similar_vectors
    mock_search_vectors = MagicMock(return_value=[]) # Return empty for simplicity

    with patch('app.services.enhanced_ai_qa_service.embedding_service.encode_batch', mock_encode_batch), \
         patch('app.services.enhanced_ai_qa_service.embedding_service.encode_text', mock_encode_text), \
         patch('app.services.enhanced_ai_qa_service.vector_db_service.search_similar_vectors', mock_search_vectors):

        await qa_service_instance._semantic_search(mock_db_for_qa, queries=queries_to_test, top_k=3)

        # Assert encode_batch was called with unique queries not initially in cache
        # Since cache is empty, it should be called with ["unique_query1", "unique_query2"]
        mock_encode_batch.assert_called_once_with(["unique_query1", "unique_query2"])

        # Assert encode_text was not called because all unique queries were handled by batch
        mock_encode_text.assert_not_called()

        # Check cache population
        assert "unique_query1" in qa_service_instance.query_embedding_cache
        assert qa_service_instance.query_embedding_cache["unique_query1"] == [0.1,0.1]
        assert "unique_query2" in qa_service_instance.query_embedding_cache
        assert qa_service_instance.query_embedding_cache["unique_query2"] == [0.2,0.2]

@pytest.mark.asyncio
async def test_semantic_search_batch_embedding_fallback_if_no_encode_batch(
    qa_service_instance: EnhancedAIQAService,
    mock_db_for_qa: AsyncMock
):
    queries_to_test = ["q_fallback1", "q_fallback2"]

    # Mock embedding_service: remove encode_batch, keep encode_text
    mock_embedding_service_no_batch = MagicMock()
    mock_embedding_service_no_batch.encode_text = MagicMock(side_effect=lambda q: {
        "q_fallback1": [0.3, 0.3], "q_fallback2": [0.4, 0.4]
    }.get(q))
    # del mock_embedding_service_no_batch.encode_batch # Ensure it's not there

    mock_search_vectors = MagicMock(return_value=[])

    with patch('app.services.enhanced_ai_qa_service.embedding_service', mock_embedding_service_no_batch), \
         patch('app.services.enhanced_ai_qa_service.vector_db_service.search_similar_vectors', mock_search_vectors):

        # Remove encode_batch if it was added by a previous test's patch globally on the module
        if hasattr(embedding_service, 'encode_batch'):
            original_encode_batch = embedding_service.encode_batch
            delattr(embedding_service, 'encode_batch')
        else:
            original_encode_batch = None

        await qa_service_instance._semantic_search(mock_db_for_qa, queries=queries_to_test, top_k=3)

        # Assert encode_text was called for each query as encode_batch is absent
        mock_embedding_service_no_batch.encode_text.assert_any_call("q_fallback1")
        mock_embedding_service_no_batch.encode_text.assert_any_call("q_fallback2")
        assert mock_embedding_service_no_batch.encode_text.call_count == 2

        # Restore encode_batch if it was originally there, for other tests
        if original_encode_batch:
            embedding_service.encode_batch = original_encode_batch


@pytest.mark.asyncio
async def test_semantic_search_metadata_filter_passed(
    qa_service_instance: EnhancedAIQAService,
    mock_db_for_qa: AsyncMock
):
    test_query = "query with metadata"
    qrr_mock = QueryRewriteResult(
        original_query=test_query,
        rewritten_queries=[test_query],
        extracted_parameters={"file_type": "application/pdf"}
    )

    mock_encode_text = MagicMock(return_value=[0.6, 0.6, 0.6])
    mock_search_vectors = MagicMock(return_value=[]) # Result content doesn't matter for this test

    with patch('app.services.enhanced_ai_qa_service.embedding_service.encode_text', mock_encode_text), \
         patch('app.services.enhanced_ai_qa_service.vector_db_service.search_similar_vectors', mock_search_vectors):

        await qa_service_instance._semantic_search(
            db=mock_db_for_qa,
            queries=[test_query],
            top_k=3,
            query_rewrite_result=qrr_mock # Pass the QRR with extracted_parameters
        )

    mock_search_vectors.assert_called_once()
    # Check the metadata_filter argument in the call to search_similar_vectors
    args, kwargs = mock_search_vectors.call_args
    assert kwargs.get("metadata_filter") == {"file_type": "application/pdf"}
    assert kwargs.get("owner_id_filter") is None # user_id was None in _semantic_search call
