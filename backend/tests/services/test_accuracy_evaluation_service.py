import pytest
from unittest.mock import AsyncMock, MagicMock
import math

from app.services.accuracy_evaluation_service import AccuracyEvaluationService, QueryTestCase, EvaluationReport
from app.services.enhanced_ai_qa_service import EnhancedAIQAService # Actual service, but will be mocked
from app.models.vector_models import AIQAResponse, SemanticContextDocument, AIQARequest

# Mock for database
@pytest.fixture
def mock_db():
    return AsyncMock()

# Mock for EnhancedAIQAService
@pytest.fixture
def mock_qa_service():
    return AsyncMock(spec=EnhancedAIQAService)


@pytest.mark.asyncio
async def test_evaluate_accuracy_metrics(mock_qa_service: AsyncMock, mock_db: AsyncMock):
    eval_service = AccuracyEvaluationService(qa_service=mock_qa_service, db=mock_db)

    test_cases = [
        QueryTestCase(
            query_id="q1", user_query="Query 1",
            expected_relevant_doc_ids=["d1", "d2"],
            relevance_scores={"d1": 5.0, "d2": 3.0}
        ),
        QueryTestCase(
            query_id="q2", user_query="Query 2",
            expected_relevant_doc_ids=["d4"],
            relevance_scores={"d4": 5.0}
        ),
        QueryTestCase(
            query_id="q3", user_query="Query 3",
            expected_relevant_doc_ids=["d7"], # Relevant d7 not found in mock results
            relevance_scores={"d7": 5.0}
        ),
        QueryTestCase( # Test case for nDCG with no relevance_scores (default relevance 1)
            query_id="q4_no_scores", user_query="Query 4 no scores",
            expected_relevant_doc_ids=["d10", "d11"]
            # relevance_scores is None
        )
    ]

    # Define mock responses from qa_service.process_qa_request
    # Ensure AIQARequest is correctly typed if it's validated by the mock's spec
    async def mock_process_qa_request_side_effect(db: AsyncMock, request: AIQARequest, user_id: None, request_id: str):
        if request.question == "Query 1":
            return AIQAResponse(
                semantic_search_contexts=[ # retrieved contexts
                    SemanticContextDocument(document_id="d1", summary_or_chunk_text="text1", similarity_score=0.9),
                    SemanticContextDocument(document_id="d3", summary_or_chunk_text="text3", similarity_score=0.8), # Irrelevant
                    SemanticContextDocument(document_id="d2", summary_or_chunk_text="text2", similarity_score=0.7)
                ]
            )
        elif request.question == "Query 2":
            return AIQAResponse(
                semantic_search_contexts=[
                    SemanticContextDocument(document_id="d5", summary_or_chunk_text="text5", similarity_score=0.9), # Irrelevant
                    SemanticContextDocument(document_id="d6", summary_or_chunk_text="text6", similarity_score=0.8), # Irrelevant
                    SemanticContextDocument(document_id="d4", summary_or_chunk_text="text4", similarity_score=0.7)
                ]
            )
        elif request.question == "Query 3":
            return AIQAResponse( # Relevant d7 is NOT found
                semantic_search_contexts=[
                    SemanticContextDocument(document_id="d8", summary_or_chunk_text="text8", similarity_score=0.9),
                    SemanticContextDocument(document_id="d9", summary_or_chunk_text="text9", similarity_score=0.8)
                ]
            )
        elif request.question == "Query 4 no scores":
            return AIQAResponse(
                semantic_search_contexts=[ # d10 is relevant (implicit score 1), d12 is not
                    SemanticContextDocument(document_id="d10", summary_or_chunk_text="text10", similarity_score=0.9),
                    SemanticContextDocument(document_id="d12", summary_or_chunk_text="text12", similarity_score=0.8)
                ]
            )
        return AIQAResponse(semantic_search_contexts=[])

    mock_qa_service.process_qa_request.side_effect = mock_process_qa_request_side_effect

    top_k_values_to_test = [1, 3]
    report = await eval_service.evaluate_accuracy(test_cases, top_k_values=top_k_values_to_test)

    assert report.num_queries_evaluated == 4

    # --- Manually Calculate Expected Metrics ---
    # Query 1: expected=["d1", "d2"], relevance={"d1":5, "d2":3}, retrieved=["d1", "d3", "d2"]
    #   Hit@1: Yes (d1). Hit@3: Yes (d1, d2).
    #   RR: 1.0 (d1 at rank 1)
    #   nDCG@1: DCG@1 = 5/log2(2) = 5. IDCG@1 = 5/log2(2) = 5. nDCG@1 = 1.0
    #   nDCG@3: DCG@3 = 5/log2(2) + 0/log2(3) + 3/log2(4) = 5 + 0 + 3/2 = 6.5
    #           IDCG@3 = 5/log2(2) + 3/log2(3) = 5 + 3/1.585 = 5 + 1.8927 = 6.8927
    #           nDCG@3 = 6.5 / 6.8927 = 0.9430
    q1_ndcg1 = 1.0
    q1_ndcg3 = 6.5 / (5 / math.log2(2) + 3 / math.log2(3)) # approx 0.9430

    # Query 2: expected=["d4"], relevance={"d4":5}, retrieved=["d5", "d6", "d4"]
    #   Hit@1: No. Hit@3: Yes (d4).
    #   RR: 1/3 (d4 at rank 3)
    #   nDCG@1: DCG@1 = 0. IDCG@1 = 5/log2(2)=5. nDCG@1 = 0
    #   nDCG@3: DCG@3 = 0/log2(2) + 0/log2(3) + 5/log2(4) = 5/2 = 2.5
    #           IDCG@3 = 5/log2(2) = 5
    #           nDCG@3 = 2.5 / 5 = 0.5
    q2_ndcg1 = 0.0
    q2_ndcg3 = 2.5 / (5 / math.log2(2)) # 0.5

    # Query 3: expected=["d7"], relevance={"d7":5}, retrieved=["d8", "d9"]
    #   Hit@1: No. Hit@3: No.
    #   RR: 0.0
    #   nDCG@1: DCG@1 = 0. IDCG@1 = 5/log2(2)=5. nDCG@1 = 0
    #   nDCG@3: DCG@3 = 0. IDCG@3 = 5/log2(2)=5. nDCG@3 = 0
    q3_ndcg1 = 0.0
    q3_ndcg3 = 0.0

    # Query 4: expected=["d10", "d11"], no scores (relevance=1 for expected), retrieved=["d10", "d12"]
    #   Hit@1: Yes (d10). Hit@3: Yes (d10).
    #   RR: 1.0 (d10 at rank 1)
    #   nDCG@1: DCG@1 = 1/log2(2) = 1. IDCG@1 = 1/log2(2) = 1. nDCG@1 = 1.0
    #   nDCG@3: DCG@3 = 1/log2(2) + 0/log2(3) = 1. (d12 is not relevant)
    #           IDCG@3 = 1/log2(2) + 1/log2(3) = 1 + 1/1.585 = 1 + 0.6309 = 1.6309
    #           nDCG@3 = 1 / 1.6309 = 0.6131
    q4_ndcg1 = 1.0
    q4_ndcg3 = (1/math.log2(2)) / (1/math.log2(2) + 1/math.log2(3)) # approx 0.6131


    # Expected Hit Rates
    # HR@1: (q1 yes, q2 no, q3 no, q4 yes) = 2 hits / 4 queries = 0.5
    # HR@3: (q1 yes, q2 yes, q3 no, q4 yes) = 3 hits / 4 queries = 0.75
    expected_hit_rates = {1: 0.5, 3: 0.75}
    assert report.hit_rates == pytest.approx(expected_hit_rates)

    # Expected MRR
    # (1.0 (q1) + 1/3 (q2) + 0.0 (q3) + 1.0 (q4)) / 4 = (1 + 0.3333 + 0 + 1) / 4 = 2.3333 / 4 = 0.5833
    expected_mrr = (1.0 + (1/3) + 0.0 + 1.0) / 4.0
    assert report.mrr == pytest.approx(expected_mrr)

    # Expected nDCG Scores
    # nDCG@1: (q1_nDCG1 + q2_nDCG1 + q3_nDCG1 + q4_nDCG1) / 4 = (1.0 + 0.0 + 0.0 + 1.0) / 4 = 2.0 / 4 = 0.5
    # nDCG@3: (q1_nDCG3 + q2_nDCG3 + q3_nDCG3 + q4_nDCG3) / 4
    #         = (0.9430 + 0.5 + 0.0 + 0.6131) / 4 = 2.0561 / 4 = 0.5140
    expected_ndcg_scores = {
        1: (q1_ndcg1 + q2_ndcg1 + q3_ndcg1 + q4_ndcg1) / 4.0,
        3: (q1_ndcg3 + q2_ndcg3 + q3_ndcg3 + q4_ndcg3) / 4.0
    }
    assert report.ndcg_scores == pytest.approx(expected_ndcg_scores)

    # Check detailed results structure (optional, but good for sanity)
    assert len(report.detailed_results) == 4
    assert report.detailed_results[0]["query_id"] == "q1"
    assert report.detailed_results[0]["metrics"]["rr_for_query"] == pytest.approx(1.0)
    assert report.detailed_results[0]["metrics"]["ndcg_at_k"][1] == pytest.approx(q1_ndcg1)
    assert report.detailed_results[0]["metrics"]["ndcg_at_k"][3] == pytest.approx(q1_ndcg3)

    assert report.detailed_results[3]["query_id"] == "q4_no_scores"
    # For q4, relevance_map in detailed_results should be empty as it was not provided in test_case
    assert report.detailed_results[3]["relevance_scores_used"] == {}
    assert report.detailed_results[3]["metrics"]["ndcg_at_k"][1] == pytest.approx(q4_ndcg1)
    assert report.detailed_results[3]["metrics"]["ndcg_at_k"][3] == pytest.approx(q4_ndcg3)

    # Verify process_qa_request was called for each test case
    assert mock_qa_service.process_qa_request.call_count == 4
    # Example of checking one call's arguments (AIQARequest part)
    first_call_args = mock_qa_service.process_qa_request.call_args_list[0][1] # [1] for kwargs
    assert isinstance(first_call_args['request'], AIQARequest)
    assert first_call_args['request'].question == "Query 1"
    assert first_call_args['request'].context_limit == max(top_k_values_to_test) # max_k_for_retrieval
    assert first_call_args['user_id'] is None
    assert "eval-q1" in first_call_args['request_id']

    # Check max_k_for_retrieval in AIQARequest for one of the calls
    args, kwargs = mock_qa_service.process_qa_request.call_args_list[0] # First call
    sent_request_arg = kwargs['request'] # Assuming 'request' is a kwarg
    assert sent_request_arg.context_limit == max(top_k_values_to_test)

    # Test with empty top_k_values (should default)
    report_default_k = await eval_service.evaluate_accuracy(test_cases, top_k_values=[])
    assert report_default_k.hit_rates is not None and 1 in report_default_k.hit_rates # Check if default K=1,3,5 were used
    assert report_default_k.hit_rates is not None and 3 in report_default_k.hit_rates
    assert report_default_k.hit_rates is not None and 5 in report_default_k.hit_rates
    # Recalculating all metrics for default K values is too much here, just check structure.

    # Test with empty test_cases
    empty_report = await eval_service.evaluate_accuracy([], top_k_values=[1,3])
    assert empty_report.num_queries_evaluated == 0
    assert empty_report.mrr == 0.0
    assert empty_report.hit_rates == {1:0.0, 3:0.0} # Should be 0.0 for all specified K
    assert empty_report.ndcg_scores == {1:0.0, 3:0.0}
    assert empty_report.detailed_results == []
