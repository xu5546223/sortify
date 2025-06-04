from typing import List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException, Body, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.user_models import User
from app.core.security import get_current_admin_user
from app.db.mongodb_utils import get_db
# Assuming EnhancedAIQAService is in the specified path.
# If its constructor needs db, Depends(get_db) will handle it if EnhancedAIQAService is also a dependency.
from app.services.enhanced_ai_qa_service import enhanced_ai_qa_service as global_qa_service # Assuming a global instance
from app.services.accuracy_evaluation_service import (
    AccuracyEvaluationService,
    QueryTestCase,
    EvaluationReport
)

router = APIRouter(prefix="/evaluation", tags=["Evaluation"])

# Dependency to get the QA service instance
# This assumes enhanced_ai_qa_service is a singleton instance or has a dependency setup for FastAPI
# If EnhancedAIQAService requires db for its __init__, FastAPI's dependency injection
# should handle it if it's also registered as a dependency.
# For now, let's assume a global instance or a simple constructor.
# A more robust way would be to have EnhancedAIQAService also as a dependency.
def get_qa_service() -> Any: # Using Any for now, should be EnhancedAIQAService
    # This is a placeholder if enhanced_ai_qa_service is a direct import of an instance.
    # If EnhancedAIQAService needs to be instantiated per request or with dependencies:
    # from app.services.enhanced_ai_qa_service import EnhancedAIQAService
    # return EnhancedAIQAService(...) # Potentially with its own dependencies
    return global_qa_service


def get_accuracy_evaluation_service(
    qa_service: Any = Depends(get_qa_service), # Using placeholder get_qa_service
    db: AsyncIOMotorDatabase = Depends(get_db)
) -> AccuracyEvaluationService:
    # Pass the actual qa_service instance to AccuracyEvaluationService
    return AccuracyEvaluationService(qa_service=qa_service, db=db)

@router.post(
    "/accuracy",
    response_model=EvaluationReport,
    summary="Run Accuracy Evaluation for QA Service"
)
async def run_accuracy_evaluation(
    test_cases: List[QueryTestCase] = Body(...),
    top_k_values_str: Optional[str] = Query(
        "1,3,5",
        description="Comma-separated list of K values for HitRate@K and nDCG@K (e.g., '1,3,5')"
    ),
    eval_service: AccuracyEvaluationService = Depends(get_accuracy_evaluation_service),
    current_user: User = Depends(get_current_admin_user) # Protect the endpoint
):
    """
    Runs an accuracy evaluation test for the Question Answering service.

    Requires admin privileges.
    The `test_cases` should be a list of queries, their expected relevant document IDs,
    and optionally, the relevance scores for each document.
    """
    parsed_top_k_values: List[int] = []
    if top_k_values_str:
        try:
            parsed_top_k_values = [int(k.strip()) for k in top_k_values_str.split(',') if k.strip()]
            if not parsed_top_k_values: # handle empty string or only commas
                raise ValueError("No valid K values provided.")
            if any(k <= 0 for k in parsed_top_k_values):
                raise ValueError("K values must be positive integers.")
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid top_k_values_str: {str(e)}. Must be comma-separated positive integers."
            )
    else: # Default if string is empty, though Query provides a default value
        parsed_top_k_values = [1, 3, 5]

    if not test_cases:
        raise HTTPException(status_code=400, detail="No test cases provided.")

    try:
        report = await eval_service.evaluate_accuracy(
            test_cases=test_cases,
            top_k_values=parsed_top_k_values
        )
        return report
    except Exception as e:
        # Log the exception details here if possible
        # logger.error(f"Error during accuracy evaluation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An error occurred during evaluation: {str(e)}")
