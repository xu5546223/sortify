import json
import uuid
import re
import asyncio
import motor.motor_asyncio
import os
import logging
from typing import Optional, Dict, Any, List

import sys
# Add the parent directory of 'backend' and 'evaluation' to sys.path
# This assumes the script is in 'evaluation' and 'backend' is a sibling directory.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# --- MongoDB Connection Details ---
try:
    from backend.app.core.config import settings
    # The actual config.py uses MONGODB_URL and DB_NAME, ensure settings object exposes them as MONGO_URI and MONGO_DB_NAME
    # or adapt to use settings.MONGODB_URL and settings.DB_NAME directly.
    # For now, assuming the Settings class in config.py might map them or they are accessible.
    # We will use the names as per the original problem description for prepare_data.py's variables.
    MONGO_URI = settings.MONGODB_URL # Adapted to actual Pydantic model field
    MONGO_DB_NAME = settings.DB_NAME   # Adapted to actual Pydantic model field
    logging.info(f"Successfully imported MongoDB settings from backend.app.core.config. Using MONGODB_URL: {MONGO_URI}, DB_NAME: {MONGO_DB_NAME}")
except ImportError as e:
    logging.warning(f"ImportError for backend.app.core.config: {e}. Falling back to default MongoDB settings.")
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "rag_db")
except AttributeError as e:
    logging.warning(f"AttributeError accessing settings (e.g. MONGODB_URL or DB_NAME not found): {e}. Falling back to default MongoDB settings.")
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "rag_db")
except Exception as e: # Catch any other Pydantic validation or other errors during settings load
    logging.error(f"Failed to load settings from backend.app.core.config due to: {e}. Using default MongoDB settings.")
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "rag_db")

COLLECTION_NAME = "documents"

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Function to Extract Filename ---
def extract_filename(output_text: str) -> Optional[str]:
    """
    Extracts the filename from HTML comments like <!-- 檔案名稱: FILENAME_HERE -->.
    """
    match = re.search(r"<!--\s*檔案名稱:\s*(.*?)\s*-->", output_text)
    if match:
        return match.group(1)
    return None

# --- Function to Get Document ID from MongoDB ---
async def get_document_id(db: motor.motor_asyncio.AsyncIOMotorDatabase, filename: str) -> Optional[str]:
    """
    Queries the 'documents' collection for a document where the 'filename' field matches.
    Returns the _id as a string if found, otherwise None.
    """
    document = await db[COLLECTION_NAME].find_one({"filename": filename})
    if document and "_id" in document:
        return str(document["_id"])
    else:
        logging.warning(f"Document not found in MongoDB for filename: {filename}")
        return None

# --- Main Asynchronous Function process_data() ---
async def process_data():
    """
    Loads data from QAdataset.json, processes it to include document IDs from MongoDB,
    and saves the processed data to processed_qadataset.json.
    """
    input_filepath = "evaluation/QAdataset.json"
    output_filepath = "evaluation/processed_qadataset.json"
    processed_data: List[Dict[str, Any]] = []

    records_processed = 0
    records_successfully_mapped = 0
    records_missing_filename = 0
    records_missing_document_id = 0

    try:
        with open(input_filepath, 'r', encoding='utf-8') as f:
            dataset = json.load(f)
    except FileNotFoundError:
        logging.error(f"Input file not found: {input_filepath}")
        return
    except json.JSONDecodeError:
        logging.error(f"Error decoding JSON from file: {input_filepath}")
        return

    mongo_client = None
    try:
        logging.info(f"Connecting to MongoDB at {MONGO_URI} / Database: {MONGO_DB_NAME}")
        mongo_client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
        db = mongo_client[MONGO_DB_NAME]
        # Verify connection
        await db.command('ping')
        logging.info("Successfully connected to MongoDB.")
    except Exception as e:
        logging.error(f"Could not connect to MongoDB: {e}")
        if mongo_client:
            mongo_client.close()
        return

    for item in dataset:
        records_processed += 1
        query_id = str(uuid.uuid4())
        user_query = item.get("instruction")
        original_answer = item.get("output")

        if not user_query or not original_answer:
            logging.warning(f"Skipping item due to missing 'instruction' or 'output': {item}")
            continue

        filename = extract_filename(original_answer)

        if filename:
            document_id = await get_document_id(db, filename)
            if document_id:
                processed_item = {
                    "query_id": query_id,
                    "user_query": user_query,
                    "expected_relevant_doc_ids": [document_id],
                    "relevance_scores": {document_id: 1.0},
                    "original_answer": original_answer,
                    "original_filename": filename
                }
                processed_data.append(processed_item)
                records_successfully_mapped += 1
            else:
                records_missing_document_id += 1
                logging.warning(f"Could not find document_id for filename: {filename} in query: {user_query[:50]}...")
        else:
            records_missing_filename += 1
            logging.warning(f"Could not extract filename from output for query: {user_query[:50]}...")

    try:
        with open(output_filepath, 'w', encoding='utf-8') as f:
            json.dump(processed_data, f, ensure_ascii=False, indent=4)
        logging.info(f"Successfully wrote processed data to {output_filepath}")
    except IOError as e:
        logging.error(f"Could not write processed data to file {output_filepath}: {e}")


    logging.info("--- Processing Summary ---")
    logging.info(f"Total records processed: {records_processed}")
    logging.info(f"Records successfully mapped with document_id: {records_successfully_mapped}")
    logging.info(f"Records where filename could not be extracted: {records_missing_filename}")
    logging.info(f"Records where document_id could not be found in DB (for extracted filenames): {records_missing_document_id}")

    if mongo_client:
        mongo_client.close()
        logging.info("MongoDB connection closed.")

# --- Execution Block ---
if __name__ == "__main__":
    asyncio.run(process_data())
