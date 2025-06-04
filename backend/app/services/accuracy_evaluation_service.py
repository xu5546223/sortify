from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorDatabase
import logging
import math # Added for log2
import uuid # Added for potential dummy user ID, though aiming for None

from app.models.vector_models import AIQARequest # Added
from app.services.enhanced_ai_qa_service import EnhancedAIQAService # Added
# from app.models.user_models import User # Not strictly needed if user_id=None works

logger = logging.getLogger(__name__)

class QueryTestCase(BaseModel):
    query_id: str
    user_query: str
    expected_relevant_doc_ids: List[str]
    relevance_scores: Optional[Dict[str, float]] = None

class EvaluationReport(BaseModel):
    test_set_name: str = "default_test_set" # Changed default name slightly for clarity
    num_queries_evaluated: int = 0
    hit_rates: Optional[Dict[int, float]] = None # Changed to Dict
    mrr: Optional[float] = None
    ndcg_scores: Optional[Dict[int, float]] = None # Changed to Dict
    detailed_results: Optional[List[Dict[str, Any]]] = None

class AccuracyEvaluationService:
    def __init__(self, qa_service: EnhancedAIQAService, db: AsyncIOMotorDatabase): # Changed type hint
        self.qa_service = qa_service
        self.db = db
        logger.info("AccuracyEvaluationService initialized with EnhancedAIQAService.")

    async def evaluate_accuracy(
        self,
        test_cases: List[QueryTestCase],
        top_k_values: List[int] = [1, 3, 5]
    ) -> EvaluationReport:
        logger.info(f"Starting accuracy evaluation for {len(test_cases)} test cases. Top K values: {top_k_values}")

        if not top_k_values:
            logger.warning("top_k_values is empty. Defaulting to [1, 3, 5].")
            top_k_values = [1, 3, 5]

        max_k_for_retrieval = max(top_k_values) if top_k_values else 5 # Ensure there's a max_k for retrieval

        total_hit_at_k: Dict[int, int] = {k: 0 for k in top_k_values}
        sum_rr: float = 0.0
        sum_ndcg_at_k: Dict[int, float] = {k: 0.0 for k in top_k_values}
        num_queries_evaluated: int = 0
        detailed_results_list: List[Dict[str, Any]] = []

        for test_case in test_cases:
            num_queries_evaluated += 1

            # Prepare AIQARequest
            # Using context_limit = max_k_for_retrieval to fetch enough documents for all K evaluations
            ai_qa_request = AIQARequest(
                question=test_case.user_query,
                context_limit=max_k_for_retrieval,
                use_semantic_search=True,
                use_structured_filter=False # As per instruction, isolate retrieval
            )

            # Call QA service. Passing user_id=None as per correction.
            # The qa_service's process_qa_request should handle user_id=None gracefully.
            # If owner_id_filter is applied by default for None user, this might affect results
            # if test data is not globally accessible or owned by a specific eval user.
            # This is a design consideration for the QA service itself.
            try:
                response = await self.qa_service.process_qa_request(
                    db=self.db,
                    request=ai_qa_request,
                    user_id=None, # Attempting with None first
                    request_id=f"eval-{test_case.query_id}-{str(uuid.uuid4())[:8]}" # Unique request_id for eval
                )
            except Exception as e:
                logger.error(f"Error processing QA request for query_id '{test_case.query_id}': {e}", exc_info=True)
                detailed_results_list.append({
                    "query_id": test_case.query_id, "user_query": test_case.user_query,
                    "error": str(e), "retrieved_doc_ids": [], "metrics": {}
                })
                continue # Skip to next test case if QA request fails

            retrieved_contexts = response.semantic_search_contexts or []
            retrieved_doc_ids = [ctx.document_id for ctx in retrieved_contexts][:max_k_for_retrieval]

            expected_doc_ids_set = set(test_case.expected_relevant_doc_ids)
            # Ensure relevance_map keys are strings, matching doc_ids
            relevance_map = {str(doc_id): score for doc_id, score in (test_case.relevance_scores or {}).items()}

            query_metrics_details: Dict[str, Any] = {
                "hit_rate_at_k": {}, "rr_for_query": 0.0, "ndcg_at_k": {}
            }

            # Calculate Hit Rate@K
            for k_val in top_k_values:
                hits_in_top_k = [doc_id for doc_id in retrieved_doc_ids[:k_val] if doc_id in expected_doc_ids_set]
                if len(hits_in_top_k) > 0:
                    total_hit_at_k[k_val] += 1
                query_metrics_details["hit_rate_at_k"][k_val] = 1 if len(hits_in_top_k) > 0 else 0


            # Calculate Reciprocal Rank (RR)
            current_rr = 0.0
            for i, doc_id in enumerate(retrieved_doc_ids):
                if doc_id in expected_doc_ids_set:
                    current_rr = 1.0 / (i + 1)
                    break
            sum_rr += current_rr
            query_metrics_details["rr_for_query"] = current_rr

            # Calculate nDCG@K
            for k_val in top_k_values:
                dcg_k = 0.0
                for i, doc_id in enumerate(retrieved_doc_ids[:k_val]):
                    relevance_i = relevance_map.get(doc_id, 0.0) # Use 0 if not in expected or no score
                    dcg_k += relevance_i / math.log2(i + 2) # rank is i+1, so log2(rank+1) is log2(i+2)

                # Ideal DCG (IDCG)
                # Sort expected relevant documents by their scores (highest first)
                ideal_sorted_expected_ids = sorted(
                    [doc_id for doc_id in test_case.expected_relevant_doc_ids if doc_id in relevance_map], # Only consider those with scores
                    key=lambda x: relevance_map.get(x, 0.0),
                    reverse=True
                )
                # If no relevance_scores are provided, all expected docs have relevance 1 for IDCG calc
                if not relevance_map and test_case.expected_relevant_doc_ids:
                     ideal_sorted_expected_ids = list(test_case.expected_relevant_doc_ids) # Order doesn't matter if all are 1

                idcg_k = 0.0
                for i, doc_id in enumerate(ideal_sorted_expected_ids[:k_val]):
                    # If no relevance_map, assume relevance of 1 for expected docs, else use map.
                    relevance_i = relevance_map.get(doc_id, 1.0 if not relevance_map and doc_id in expected_doc_ids_set else 0.0)
                    idcg_k += relevance_i / math.log2(i + 2)

                ndcg_k = dcg_k / idcg_k if idcg_k > 0 else 0.0
                sum_ndcg_at_k[k_val] += ndcg_k
                query_metrics_details["ndcg_at_k"][k_val] = ndcg_k

            detailed_results_list.append({
                "query_id": test_case.query_id,
                "user_query": test_case.user_query,
                "expected_doc_ids": test_case.expected_relevant_doc_ids,
                "retrieved_doc_ids": retrieved_doc_ids,
                "relevance_scores_used": relevance_map,
                "metrics": query_metrics_details
            })

        # Calculate final average metrics
        final_hit_rates: Dict[int, float] = {
            k: (total_hit_at_k[k] / num_queries_evaluated if num_queries_evaluated > 0 else 0.0)
            for k in top_k_values
        }
        final_mrr = sum_rr / num_queries_evaluated if num_queries_evaluated > 0 else 0.0
        final_ndcg_scores: Dict[int, float] = {
            k: (sum_ndcg_at_k[k] / num_queries_evaluated if num_queries_evaluated > 0 else 0.0)
            for k in top_k_values
        }

        report = EvaluationReport(
            num_queries_evaluated=num_queries_evaluated,
            hit_rates=final_hit_rates,
            mrr=final_mrr,
            ndcg_scores=final_ndcg_scores,
            detailed_results=detailed_results_list
        )

        logger.info(f"Accuracy evaluation completed. Report: {report.model_dump_json(indent=2, exclude_none=True)}")
        return report
