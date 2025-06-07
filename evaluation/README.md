# RAG System Evaluation Suite

## 1. Overview

This directory contains a suite of Python scripts designed to evaluate the retrieval accuracy and effectiveness of the RAG (Retrieval Augmented Generation) system. The primary goal is to measure how well the system can retrieve relevant documents for a given user query.

The evaluation focuses on two main aspects:

*   **Baseline Semantic Search**: Assessing the performance of the direct semantic search capability without any query enhancements.
*   **Query Rewriting Effectiveness**: Evaluating how much the query rewriting process improves retrieval performance compared to the baseline.

## 2. Prerequisites

To run these evaluation scripts, the following prerequisites must be met:

*   **Python Libraries**:
    *   The scripts rely on libraries listed in `backend/requirements.txt`. Key libraries include:
        *   `pymongo` (via `motor`): For interacting with MongoDB.
        *   `openai`: If using OpenAI models for query rewriting or other LLM-dependent parts of the `EnhancedAIQAService`.
        *   `sentence-transformers`: For embedding generation.
        *   `chromadb-client` (or equivalent): For vector database interaction.
        *   `pydantic` and `pydantic-settings`: For configuration management.
        *   `python-dotenv`: For managing environment variables.
    *   Note: While `ragas` might be a common library for RAG evaluation, these specific scripts implement custom metric calculations (Hit Rate, MRR, nDCG) and do not directly use the `ragas` library.

*   **Running MongoDB Instance**:
    *   A MongoDB server must be running and accessible.
    *   It should contain the `documents` collection, where each document has at least a `filename` and an `_id` field.

*   **Populated Vector Store**:
    *   A vector database (e.g., ChromaDB) used by `VectorDatabaseService` must be populated with document embeddings. The path or connection details for this should be correctly configured.

*   **Required Environment Variables**:
    The system relies on several environment variables for configuration. These are typically loaded via `backend.app.core.config.settings`. Ensure these are set:
    *   `MONGODB_URL`: The connection URI for MongoDB (e.g., `mongodb://localhost:27017`).
    *   `DB_NAME`: The name of the MongoDB database (e.g., `rag_db`).
    *   `OPENAI_API_KEY`: Your OpenAI API key, if using OpenAI models for query rewriting or other LLM functionalities within the services.
    *   `EMBEDDING_MODEL_NAME`: Name or path of the sentence transformer model used for embeddings (e.g., `sentence-transformers/all-MiniLM-L6-v2`).
    *   `VECTOR_DB_PATH`: Filesystem path to the ChromaDB data, if applicable (e.g., `./chroma_db_store`).
    *   Other variables as required by the specific `Settings` class in `backend.app.core.config`.

## 3. Setup

1.  **Install Dependencies**:
    It's recommended to install dependencies from the main backend requirements file, ideally within a virtual environment:
    ```bash
    pip install -r ../backend/requirements.txt
    ```
    If there's a specific `evaluation/requirements.txt`, use that instead.

2.  **Configure Environment Variables**:
    Create a `.env` file in the root of the repository (e.g., alongside the `backend` and `evaluation` directories) and populate it with the necessary environment variables. Example:
    ```env
    MONGODB_URL="mongodb://localhost:27017"
    DB_NAME="rag_db"
    OPENAI_API_KEY="your_openai_api_key_here"
    EMBEDDING_MODEL_NAME="sentence-transformers/all-MiniLM-L6-v2"
    VECTOR_DB_PATH="./chroma_db_data"
    # Add other necessary variables for ChromaDB host/port if not using local path, etc.
    ```
    The scripts load these variables via the `settings` object.

## 4. Data Preparation (`prepare_data.py`)

The `prepare_data.py` script processes an initial question-answer dataset to prepare it for evaluation.

*   **Functionality**:
    *   Reads an input JSON file (e.g., `evaluation/QAdataset.json`) containing instructions (user queries) and outputs (original answers which might contain filename hints).
    *   Extracts the `user_query` from the "instruction" field.
    *   Extracts a `filename` from HTML comments (e.g., `<!-- 檔案名稱: example_document.txt -->`) in the "output" field.
    *   Connects to MongoDB to map this `filename` to its corresponding `_id` in the `documents` collection.
    *   Generates `evaluation/processed_qadataset.json`. Each record in this output file includes:
        *   `query_id`: A unique ID for the query.
        *   `user_query`: The original user question.
        *   `expected_relevant_doc_ids`: A list containing the `document_id`(s) retrieved from MongoDB based on the filename.
        *   `relevance_scores`: A dictionary mapping `document_id` to a relevance score. Currently, this defaults to `{document_id: 1.0}` for the expected document.
        *   `original_answer`: The original "output" field from the input.
        *   `original_filename`: The filename extracted from the output.

*   **How to Run**:
    Ensure your current working directory is the root of the repository.
    ```bash
    python evaluation/prepare_data.py
    ```

*   **Expected Input**:
    *   `evaluation/QAdataset.json`: A JSON file with records like:
        ```json
        [
          {
            "instruction": "What is the capital of France?",
            "output": "The capital of France is Paris. <!-- 檔案名稱: france_info.txt -->"
          }
        ]
        ```

*   **Expected Output**:
    *   `evaluation/processed_qadataset.json`: A JSON file structured for the evaluation scripts:
        ```json
        [
          {
            "query_id": "some-uuid-v4",
            "user_query": "What is the capital of France?",
            "expected_relevant_doc_ids": ["mongo_object_id_for_france_info_txt"],
            "relevance_scores": {"mongo_object_id_for_france_info_txt": 1.0},
            "original_answer": "The capital of France is Paris. <!-- 檔案名稱: france_info.txt -->",
            "original_filename": "france_info.txt"
          }
        ]
        ```

## 5. Semantic Search Evaluation (`evaluate_semantic_search.py`)

This script evaluates the performance of the baseline semantic search retrieval.

*   **Functionality**:
    *   Reads `evaluation/processed_qadataset.json`.
    *   For each test case, it takes the `user_query` and performs a semantic search using `EnhancedAIQAService`.
    *   It then compares the retrieved document IDs against `expected_relevant_doc_ids`.
    *   Calculates the following metrics:
        *   **Hit Rate@K**: Whether any of the expected documents are within the top K retrieved documents.
        *   **Mean Reciprocal Rank (MRR)**: The average of the reciprocal ranks of the first relevant document found for each query.
        *   **Normalized Discounted Cumulative Gain (nDCG@K)**: Measures the quality of ranking, considering the position and relevance of retrieved documents.

*   **How to Run**:
    Ensure your current working directory is the root of the repository.
    ```bash
    python evaluation/evaluate_semantic_search.py
    ```

*   **Expected Input**:
    *   `evaluation/processed_qadataset.json` (generated by `prepare_data.py`).

*   **Expected Output**:
    *   A summary report printed to the console, showing average Hit Rate@K, MRR, and nDCG@K scores.
    *   `evaluation/semantic_search_results.json`: A JSON file containing detailed results for each query, including the query, expected IDs, retrieved IDs, and calculated metrics.

## 6. Query Rewriting Evaluation (`evaluate_query_rewriting.py`)

This script evaluates the effectiveness of the query rewriting mechanism in improving retrieval performance.

*   **Functionality**:
    *   Reads `evaluation/processed_qadataset.json`.
    *   For each `user_query`:
        1.  The query is first rewritten using the `_rewrite_query_unified` method of `EnhancedAIQAService`.
        2.  A semantic search is then performed using the *rewritten* query.
        3.  The retrieved document IDs are compared against `expected_relevant_doc_ids`.
    *   Calculates Hit Rate@K, MRR, and nDCG@K based on the results from the rewritten query.

*   **How to Run**:
    Ensure your current working directory is the root of the repository.
    ```bash
    python evaluation/evaluate_query_rewriting.py
    ```

*   **Expected Input**:
    *   `evaluation/processed_qadataset.json`.

*   **Expected Output**:
    *   A summary report printed to the console for the performance of rewritten queries.
    *   `evaluation/query_rewriting_results.json`: Detailed results for each query, including the original query, the rewritten query, retrieved IDs, and metrics.

*   **Comparing Results**:
    The metrics from this script should be compared against those from `evaluate_semantic_search.py`. An effective query rewriting strategy should ideally lead to higher Hit Rates, MRR, and nDCG scores.

## 7. Troubleshooting/Notes

*   **MongoDB Connection**: Ensure MongoDB is running, accessible, and the `MONGODB_URL` and `DB_NAME` environment variables are correctly set.
*   **Environment Variables**: Double-check that all required environment variables (especially `OPENAI_API_KEY`, `VECTOR_DB_PATH`, `EMBEDDING_MODEL_NAME`) are correctly set and loaded by the application's settings. Missing variables can lead to initialization failures in `EnhancedAIQAService` or its sub-components.
*   **Python Path**: The scripts include a `sys.path` modification to help locate the `backend` modules. However, it's generally best to run these scripts from the root directory of the repository to ensure Python's import resolution works as expected.
    ```bash
    # From repository root
    python evaluation/script_name.py
    ```
*   **`relevance_scores` for nDCG**: The current `prepare_data.py` script assigns a binary relevance of `1.0` to expected documents. For a more nuanced nDCG calculation that can better differentiate between multiple relevant documents, the `relevance_scores` in `processed_qadataset.json` would need to be populated with varying levels of relevance (e.g., 1.0 for somewhat relevant, 2.0 for highly relevant). This would require manual annotation or a more sophisticated data preparation step.
*   **Disk Space for Dependencies**: Installing dependencies from `backend/requirements.txt` can consume significant disk space, especially due to packages like `torch` and CUDA-related libraries. Ensure sufficient disk space is available in your environment. If you encounter "No space left on device" errors during `pip install`, this is the likely cause.
*   **Protected Method Usage**: `evaluate_query_rewriting.py` calls a protected method `_rewrite_query_unified` of `EnhancedAIQAService`. This is generally discouraged as internal implementations can change. This was done based on specific requirements but might need adjustment if the service API evolves.

This README provides a guide to setting up and running the RAG evaluation scripts.
