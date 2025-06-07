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
    from backend.app.models.vector_models import AIQARequest
    # VectorDatabaseService might not be directly used here but EnhancedAIQAService depends on it.
    # from backend.app.services.vector_db_service import VectorDatabaseService
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
    # Ensure relevance_map keys are strings, default relevance for expected IDs is 1.0
    processed_relevance_map = {str(key): value for key, value in relevance_map.items()}

    dcg = 0.0
    for i, doc_id in enumerate(retrieved_doc_ids[:k]):
        relevance = processed_relevance_map.get(str(doc_id), 0.0) # Default to 0 if not in map
        if str(doc_id) in expected_doc_ids and str(doc_id) not in processed_relevance_map: # Expected and not in map
             relevance = 1.0
        dcg += relevance / math.log2(i + 2) # i+2 because ranks are 1-based, log is base 2

    # Calculate Ideal DCG (IDCG)
    # Sort expected_doc_ids by their relevance scores in descending order
    # If an expected ID is not in relevance_map, assume relevance of 1.0
    ideal_relevances = sorted(
        [processed_relevance_map.get(str(doc_id), 1.0) for doc_id in expected_doc_ids],
        reverse=True
    )

    idcg = 0.0
    for i, relevance in enumerate(ideal_relevances[:k]):
        idcg += relevance / math.log2(i + 2)

    return dcg / idcg if idcg > 0 else 0.0

# --- Main Asynchronous Function evaluate_semantic_search() ---
async def evaluate_semantic_search():
    TOP_K_VALUES = [1, 3, 5]
    dataset_filepath = "evaluation/processed_qadataset.json"
    results_filepath = "evaluation/semantic_search_results.json"

    logger.info(f"Starting semantic search evaluation. TOP_K_VALUES: {TOP_K_VALUES}")
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
        await db.command('ping') # Verify connection
        logger.info("Successfully connected to MongoDB.")

        # It's crucial that settings for VectorDB (ChromaDB path/host, etc.) and Embedding models are correctly set in environment
        # for EnhancedAIQAService to initialize properly.
        logger.info("Initializing EnhancedAIQAService...")
        qa_service = EnhancedAIQAService() # This might raise errors if config is missing
        logger.info("EnhancedAIQAService initialized successfully.")

    except Exception as e:
        logger.error(f"Failed to initialize database connection or QA service: {e}")
        if db_client:
            await close_db_client()
        return

    total_queries = 0
    total_hit_at_k = {k: 0 for k in TOP_K_VALUES}
    sum_mrr = 0.0
    sum_ndcg_at_k = {k: 0.0 for k in TOP_K_VALUES}
    detailed_results: List[Dict[str, Any]] = []

    for test_case in dataset:
        total_queries += 1
        query_id = test_case.get('query_id', str(uuid.uuid4()))
        user_query = test_case.get('user_query')

        # Ensure expected_ids are strings
        raw_expected_ids = test_case.get('expected_relevant_doc_ids', [])
        expected_ids = [str(eid) for eid in raw_expected_ids if eid is not None]

        # Ensure relevance_map keys are strings
        raw_relevance_map = test_case.get('relevance_scores', {})
        relevance_map = {str(k): float(v) for k, v in raw_relevance_map.items() if k is not None}

        if not user_query or not expected_ids:
            logger.warning(f"Skipping test case with query_id {query_id} due to missing user_query or expected_ids.")
            detailed_results.append({
                "query_id": query_id, "user_query": user_query, "expected_doc_ids": expected_ids,
                "retrieved_doc_ids": [], "error": "Missing user_query or expected_ids",
                "hit_at_k": {k: 0 for k in TOP_K_VALUES}, "mrr": 0.0,
                "ndcg_at_k": {k: 0.0 for k in TOP_K_VALUES}
            })
            continue

        logger.info(f"Processing query_id: {query_id} - Query: '{user_query[:100]}...'")

        ai_request = AIQARequest(
            question=user_query,
            context_limit=max(TOP_K_VALUES),
            use_semantic_search=True,
            use_structured_filter=False, # As per problem spec
            session_id=str(uuid.uuid4()) # Each query is a new session for this eval
        )

        retrieved_doc_ids: List[str] = []
        query_metrics = {
            "hit_at_k": {k: 0 for k in TOP_K_VALUES},
            "mrr": 0.0,
            "ndcg_at_k": {k: 0.0 for k in TOP_K_VALUES}
        }
        error_message: Optional[str] = None

        try:
            # The user_id and request_id are optional or can be generated
            response = await qa_service.process_qa_request(
                db=db,
                request=ai_request,
                user_id=None, # Or a dummy user_id string
                request_id=str(uuid.uuid4())
            )
            if response.semantic_search_contexts:
                retrieved_doc_ids = [str(ctx.document_id) for ctx in response.semantic_search_contexts if ctx.document_id is not None][:max(TOP_K_VALUES)]
            else:
                logger.warning(f"No semantic search contexts returned for query_id: {query_id}")

        except Exception as e:
            logger.error(f"Error processing QA request for query_id {query_id}: {e}", exc_info=True)
            error_message = str(e)
            # For errors, metrics will remain 0 / default

        # Calculate metrics for this query
        for k in TOP_K_VALUES:
            hit = calculate_hit_at_k(retrieved_doc_ids, expected_ids, k)
            query_metrics["hit_at_k"][k] = hit
            total_hit_at_k[k] += hit

            ndcg = calculate_ndcg_at_k(retrieved_doc_ids, expected_ids, relevance_map, k)
            query_metrics["ndcg_at_k"][k] = ndcg
            sum_ndcg_at_k[k] += ndcg

        rr_for_query = calculate_mrr(retrieved_doc_ids, expected_ids)
        query_metrics["mrr"] = rr_for_query
        sum_mrr += rr_for_query

        detailed_results.append({
            "query_id": query_id,
            "user_query": user_query,
            "expected_doc_ids": expected_ids,
            "retrieved_doc_ids": retrieved_doc_ids,
            "metrics": query_metrics,
            "error": error_message
        })
        logger.info(f"Results for query_id {query_id}: MRR={rr_for_query:.4f}, Hits@K={query_metrics['hit_at_k']}")


    # Calculate average metrics
    avg_hit_rates = {k: (total_hit_at_k[k] / total_queries if total_queries else 0.0) for k in TOP_K_VALUES}
    overall_mrr = sum_mrr / total_queries if total_queries else 0.0
    avg_ndcg_scores = {k: (sum_ndcg_at_k[k] / total_queries if total_queries else 0.0) for k in TOP_K_VALUES}

    # --- Summary Report ---
    logger.info("\n--- Semantic Search Evaluation Summary ---")
    logger.info(f"Total Queries Evaluated: {total_queries}")
    if total_queries > 0:
        for k in TOP_K_VALUES:
            logger.info(f"Average Hit Rate@{k}: {avg_hit_rates[k]:.4f}")
        logger.info(f"Overall MRR: {overall_mrr:.4f}")
        for k in TOP_K_VALUES:
            logger.info(f"Average nDCG@{k}: {avg_ndcg_scores[k]:.4f}")
    else:
        logger.info("No queries were processed to generate metrics.")
    logger.info("----------------------------------------")

    try:
        with open(results_filepath, 'w', encoding='utf-8') as f:
            json.dump(detailed_results, f, ensure_ascii=False, indent=4)
        logger.info(f"Detailed results saved to {results_filepath}")
    except IOError as e:
        logger.error(f"Failed to save detailed results to {results_filepath}: {e}")

    if db_client:
        await close_db_client()
        logger.info("MongoDB connection closed.")

# --- Execution Block ---
if __name__ == "__main__":
    # Setup required environment variables for 'settings' to load correctly
    # These would typically be in a .env file or set in the execution environment
    # For example:
    # os.environ['MONGODB_URL'] = 'mongodb://localhost:27017'
    # os.environ['DB_NAME'] = 'rag_db'
    # os.environ['VECTOR_DB_PATH'] = '/path/to/chroma_db'
    # os.environ['EMBEDDING_MODEL_NAME'] = 'sentence-transformers/all-MiniLM-L6-v2'

    # Check if critical env vars are set, otherwise EnhancedAIQAService might fail to init
    required_env_vars = ['MONGODB_URL', 'DB_NAME', 'VECTOR_DB_PATH', 'EMBEDDING_MODEL_NAME']
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    if missing_vars:
        logger.warning(f"Missing critical environment variables: {', '.join(missing_vars)}. Service initialization might fail.")
        # For a real run, you might want to sys.exit(1) here or ensure they are set.
        # For this tool, we'll let it try and fail if they are not present from the environment.

    asyncio.run(evaluate_semantic_search())
