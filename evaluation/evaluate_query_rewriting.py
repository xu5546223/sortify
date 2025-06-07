import json
import asyncio
import logging
import uuid
import re
import math
import os
import sys
from typing import List, Dict, Optional, Any

# Ensure backend modules can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from backend.app.services.enhanced_ai_qa_service import EnhancedAIQAService
    from backend.app.models.vector_models import AIQARequest, QueryRewriteResult # QueryRewriteResult might not be directly used if _rewrite_query_unified's output is directly a list of strings or similar
    # VectorDatabaseService might not be directly used here but EnhancedAIQAService depends on it.
    from backend.app.core.logging_utils import AppLogger, LogLevel
    from backend.app.core.config import settings
    from backend.app.db.mongodb_utils import get_db_client, close_db_client
except ImportError as e:
    print(f"Critical Import Error: {e}. Please ensure backend modules and dependencies are correctly installed and paths are set.")
    sys.exit(1)

# --- Logging Setup ---
logger = AppLogger(__name__, level=LogLevel.INFO).get_logger()

# --- Metrics Calculation Functions ---
def calculate_hit_at_k(retrieved_doc_ids: List[str], expected_doc_ids: List[str], k: int) -> int:
    """Returns 1 if any expected ID is in the top k retrieved IDs, 0 otherwise."""
    top_k_retrieved = retrieved_doc_ids[:k]
    for doc_id in expected_doc_ids:
        if doc_id in top_k_retrieved:
            return 1
    return 0

def calculate_mrr(retrieved_doc_ids: List[str], expected_doc_ids: List[str]) -> float:
    """Calculates Reciprocal Rank for a single query. Returns 0.0 if no expected ID is found."""
    for i, doc_id in enumerate(retrieved_doc_ids):
        if doc_id in expected_doc_ids:
            return 1.0 / (i + 1)
    return 0.0

def calculate_ndcg_at_k(retrieved_doc_ids: List[str], expected_doc_ids: List[str],
                        relevance_map: Dict[str, float], k: int) -> float:
    """Calculates Normalized Discounted Cumulative Gain at K."""
    processed_relevance_map = {str(key): value for key, value in relevance_map.items()}

    dcg = 0.0
    for i, doc_id in enumerate(retrieved_doc_ids[:k]):
        relevance = processed_relevance_map.get(str(doc_id), 0.0)
        if str(doc_id) in expected_doc_ids and str(doc_id) not in processed_relevance_map:
             relevance = 1.0
        dcg += relevance / math.log2(i + 2)

    ideal_relevances = sorted(
        [processed_relevance_map.get(str(doc_id), 1.0) for doc_id in expected_doc_ids],
        reverse=True
    )

    idcg = 0.0
    for i, relevance in enumerate(ideal_relevances[:k]):
        idcg += relevance / math.log2(i + 2)

    return dcg / idcg if idcg > 0 else 0.0

# --- Main Asynchronous Function evaluate_query_rewriting() ---
async def evaluate_query_rewriting():
    TOP_K_VALUES = [1, 3, 5]
    dataset_filepath = "evaluation/processed_qadataset.json"
    results_filepath = "evaluation/query_rewriting_results.json"

    logger.info(f"Starting query rewriting evaluation. TOP_K_VALUES: {TOP_K_VALUES}")
    logger.info(f"Loading dataset from: {dataset_filepath}")

    try:
        with open(dataset_filepath, 'r', encoding='utf-8') as f:
            dataset = json.load(f)
        if not dataset:
            logger.warning("Dataset is empty. No evaluation will be performed.")
            return
    except FileNotFoundError:
        logger.error(f"Dataset file not found: {dataset_filepath}. Exiting.")
        return
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON from {dataset_filepath}: {e}. Exiting.")
        return

    db_client = None
    db = None
    qa_service = None

    try:
        logger.info(f"Attempting to connect to MongoDB using URI: {settings.MONGODB_URL} and DB: {settings.DB_NAME}")
        db_client = await get_db_client()
        db = db_client[settings.DB_NAME]
        await db.command('ping')
        logger.info("Successfully connected to MongoDB.")

        logger.info("Initializing EnhancedAIQAService...")
        qa_service = EnhancedAIQAService()
        logger.info("EnhancedAIQAService initialized successfully.")

    except Exception as e:
        logger.error(f"Failed to initialize database connection or QA service: {e}")
        if db_client:
            await close_db_client()
        return

    total_queries = 0
    total_hit_at_k_rewritten = {k: 0 for k in TOP_K_VALUES}
    sum_mrr_rewritten = 0.0
    sum_ndcg_at_k_rewritten = {k: 0.0 for k in TOP_K_VALUES}
    detailed_results: List[Dict[str, Any]] = []
    queries_successfully_rewritten = 0
    queries_failed_rewriting = 0
    queries_search_failed_after_rewrite = 0


    for test_case in dataset:
        total_queries += 1
        query_id = test_case.get('query_id', str(uuid.uuid4()))
        original_query = test_case.get('user_query')

        raw_expected_ids = test_case.get('expected_relevant_doc_ids', [])
        expected_ids = [str(eid) for eid in raw_expected_ids if eid is not None]

        raw_relevance_map = test_case.get('relevance_scores', {})
        relevance_map = {str(k): float(v) for k, v in raw_relevance_map.items() if k is not None}

        if not original_query or not expected_ids:
            logger.warning(f"Skipping test case with query_id {query_id} due to missing original_query or expected_ids.")
            # Store minimal info for skipped case
            detailed_results.append({
                "query_id": query_id, "original_query": original_query, "rewritten_query": None,
                "expected_doc_ids": expected_ids, "retrieved_doc_ids": [],
                "error": "Missing original_query or expected_ids",
                "metrics": {"hit_at_k": {k: 0 for k in TOP_K_VALUES}, "mrr": 0.0, "ndcg_at_k": {k: 0.0 for k in TOP_K_VALUES}}
            })
            continue

        logger.info(f"Processing query_id: {query_id} - Original Query: '{original_query[:100]}...'")

        rewritten_query: Optional[str] = None
        retrieved_doc_ids: List[str] = []
        query_metrics = {
            "hit_at_k": {k: 0 for k in TOP_K_VALUES},
            "mrr": 0.0,
            "ndcg_at_k": {k: 0.0 for k in TOP_K_VALUES}
        }
        rewrite_error_message: Optional[str] = None
        search_error_message: Optional[str] = None

        try:
            # Call the protected method for query rewriting
            # Assuming _rewrite_query_unified returns a QueryRewriteResult object or similar
            # that has a 'rewritten_queries' list.
            # The prompt implies query_rewrite_count=1, so we take the first.
            query_rewrite_result: Optional[QueryRewriteResult] = await qa_service._rewrite_query_unified(
                db=db,
                original_query=original_query,
                user_id=None, # Or a dummy user_id string
                request_id=str(uuid.uuid4()),
                query_rewrite_count=1
            )

            if query_rewrite_result and query_rewrite_result.rewritten_queries:
                rewritten_query = query_rewrite_result.rewritten_queries[0]
                logger.info(f"Query ID {query_id} - Rewritten Query: '{rewritten_query[:100]}...'")
                queries_successfully_rewritten +=1
            else:
                logger.warning(f"Query rewriting failed or returned no queries for query_id: {query_id}. Original query: '{original_query}'")
                rewrite_error_message = "Query rewriting failed or no rewritten queries produced."
                queries_failed_rewriting +=1

        except Exception as e:
            logger.error(f"Exception during query rewriting for query_id {query_id}: {e}", exc_info=True)
            rewrite_error_message = f"Exception during rewrite: {str(e)}"
            queries_failed_rewriting +=1

        if rewritten_query:
            ai_request_rewritten = AIQARequest(
                question=rewritten_query,
                context_limit=max(TOP_K_VALUES),
                use_semantic_search=True,
                use_structured_filter=False,
                session_id=str(uuid.uuid4())
            )
            try:
                response = await qa_service.process_qa_request(
                    db=db,
                    request=ai_request_rewritten,
                    user_id=None,
                    request_id=str(uuid.uuid4())
                )
                if response.semantic_search_contexts:
                    retrieved_doc_ids = [str(ctx.document_id) for ctx in response.semantic_search_contexts if ctx.document_id is not None][:max(TOP_K_VALUES)]
                else:
                    logger.warning(f"No semantic search contexts returned for rewritten query of query_id: {query_id}")

            except Exception as e:
                logger.error(f"Error processing QA request for rewritten query of query_id {query_id}: {e}", exc_info=True)
                search_error_message = f"Exception during search after rewrite: {str(e)}"
                queries_search_failed_after_rewrite +=1

            # Calculate metrics if search was attempted (even if it returned no docs)
            for k in TOP_K_VALUES:
                hit = calculate_hit_at_k(retrieved_doc_ids, expected_ids, k)
                query_metrics["hit_at_k"][k] = hit
                total_hit_at_k_rewritten[k] += hit

                ndcg = calculate_ndcg_at_k(retrieved_doc_ids, expected_ids, relevance_map, k)
                query_metrics["ndcg_at_k"][k] = ndcg
                sum_ndcg_at_k_rewritten[k] += ndcg

            rr_for_query = calculate_mrr(retrieved_doc_ids, expected_ids)
            query_metrics["mrr"] = rr_for_query
            sum_mrr_rewritten += rr_for_query
            logger.info(f"Results for rewritten query of ID {query_id}: MRR={rr_for_query:.4f}, Hits@K={query_metrics['hit_at_k']}")

        detailed_results.append({
            "query_id": query_id,
            "original_query": original_query,
            "rewritten_query": rewritten_query,
            "expected_doc_ids": expected_ids,
            "retrieved_doc_ids_after_rewrite": retrieved_doc_ids,
            "metrics_after_rewrite": query_metrics,
            "rewrite_error": rewrite_error_message,
            "search_error_after_rewrite": search_error_message
        })

    # Calculate average metrics for rewritten queries
    # Averages are calculated based on queries that were successfully rewritten and then searched
    # num_evaluable_queries = queries_successfully_rewritten - queries_search_failed_after_rewrite
    # Better: calculate based on total_queries, so performance drop due to errors is reflected.
    # Or, based on queries_successfully_rewritten. Let's use total_queries for now for overall system performance.

    avg_hit_rates_rewritten = {k: (total_hit_at_k_rewritten[k] / total_queries if total_queries else 0.0) for k in TOP_K_VALUES}
    overall_mrr_rewritten = sum_mrr_rewritten / total_queries if total_queries else 0.0
    avg_ndcg_scores_rewritten = {k: (sum_ndcg_at_k_rewritten[k] / total_queries if total_queries else 0.0) for k in TOP_K_VALUES}

    # --- Summary Report ---
    logger.info("\n--- Query Rewriting Evaluation Summary ---")
    logger.info(f"Total Queries Processed: {total_queries}")
    logger.info(f"Queries Successfully Rewritten: {queries_successfully_rewritten}")
    logger.info(f"Queries Failed During Rewriting: {queries_failed_rewriting}")
    logger.info(f"Queries Search Failed After Successful Rewrite: {queries_search_failed_after_rewrite}")

    if total_queries > 0 : # Or use a more specific denominator like successfully rewritten & searched queries
        logger.info("Metrics below are for REWRITTEN queries (averaged over all initial queries):")
        for k in TOP_K_VALUES:
            logger.info(f"Average Hit Rate@{k} (Rewritten): {avg_hit_rates_rewritten[k]:.4f}")
        logger.info(f"Overall MRR (Rewritten): {overall_mrr_rewritten:.4f}")
        for k in TOP_K_VALUES:
            logger.info(f"Average nDCG@{k} (Rewritten): {avg_ndcg_scores_rewritten[k]:.4f}")
    else:
        logger.info("No queries were processed to generate metrics.")
    logger.info("------------------------------------------")

    try:
        with open(results_filepath, 'w', encoding='utf-8') as f:
            json.dump(detailed_results, f, ensure_ascii=False, indent=4)
        logger.info(f"Detailed results for query rewriting saved to {results_filepath}")
    except IOError as e:
        logger.error(f"Failed to save detailed results to {results_filepath}: {e}")

    if db_client:
        await close_db_client()
        logger.info("MongoDB connection closed.")

# --- Execution Block ---
if __name__ == "__main__":
    required_env_vars = ['MONGODB_URL', 'DB_NAME', 'VECTOR_DB_PATH', 'EMBEDDING_MODEL_NAME', 'OPENAI_API_KEY'] # Query rewrite might need LLM
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    if missing_vars:
        logger.warning(f"Missing critical environment variables: {', '.join(missing_vars)}. Service initialization or query rewriting might fail.")

    asyncio.run(evaluate_query_rewriting())
