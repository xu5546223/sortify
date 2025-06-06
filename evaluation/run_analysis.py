import os
import requests
import time
import logging
from dotenv import load_dotenv
from typing import List, Dict, Any, Optional

# --- Configuration ---
# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('evaluation/analysis.log')
    ]
)

# --- Environment Variable Check ---
# Check for .env file and provide instructions if missing
if not os.path.exists('evaluation/.env'):
    logging.error("The '.env' file is missing in the 'evaluation' directory.")
    logging.error("Please create a file named '.env' in the 'sortify/evaluation/' directory with the following content:")
    print("\n" + "="*50)
    print("API_URL=http://127.0.0.1:8000")
    print("USERNAME=your_username")
    print("PASSWORD=your_password")
    print("="*50 + "\n")
    exit(1)

load_dotenv(dotenv_path='evaluation/.env', override=True)

API_URL = os.getenv("API_URL")
USERNAME = os.getenv("USERNAME")
PASSWORD = os.getenv("PASSWORD")

if not all([API_URL, USERNAME, PASSWORD]):
    logging.error("One or more required environment variables (API_URL, USERNAME, PASSWORD) are missing.")
    exit(1)

# --- API Interaction Functions ---

def login() -> Optional[str]:
    """Logs in to the API and returns the access token."""
    login_url = f"{API_URL}/api/v1/auth/token"
    login_data = {
        'username': USERNAME,
        'password': PASSWORD
    }
    try:
        logging.info(f"Attempting to log in as user '{USERNAME}'...")
        response = requests.post(login_url, data=login_data)
        response.raise_for_status()
        token = response.json().get("access_token")
        if token:
            logging.info("Login successful. Token received.")
            return token
        else:
            logging.error("Login response did not contain an access token.")
            return None
    except requests.exceptions.RequestException as e:
        logging.error(f"Login failed. Error: {e}")
        if e.response:
            logging.error(f"Response status: {e.response.status_code}, body: {e.response.text}")
        return None

def get_all_documents(token: str) -> List[Dict[str, Any]]:
    """Fetches all documents for the current user, handling pagination."""
    all_documents = []
    documents_url = f"{API_URL}/api/v1/documents/"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"limit": 100, "skip": 0}
    
    logging.info("Fetching all documents from the API...")
    while True:
        try:
            response = requests.get(documents_url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            documents = data.get("items", [])
            all_documents.extend(documents)
            
            total = data.get("total", 0)
            if len(all_documents) >= total:
                break
            params["skip"] += params["limit"]
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to fetch documents. Error: {e}")
            return [] # Return empty list on failure
    logging.info(f"Successfully fetched {len(all_documents)} documents.")
    return all_documents

def get_documents_to_process(documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Filters documents to find those that are in a valid state to be processed.
    It selects new, pending, or failed documents, and ignores those already
    completed or currently in the process of analyzing.
    """
    to_process = []
    # States that are considered valid to start processing from.
    triggerable_states = [
        "PENDING", 
        "UPLOADED", 
        "EXTRACTION_FAILED", 
        "ANALYSIS_FAILED"
    ]
    
    for doc in documents:
        if doc.get("status") in triggerable_states:
            to_process.append(doc)
            
    logging.info(f"Found {len(to_process)} documents to process.")
    return to_process

def trigger_analysis(token: str, document_id: str) -> bool:
    """Triggers analysis for a single document."""
    analysis_url = f"{API_URL}/api/v1/documents/{document_id}"
    headers = {"Authorization": f"Bearer {token}"}
    # Using the PATCH endpoint with `trigger_content_processing`
    payload = {"trigger_content_processing": True}
    
    try:
        logging.info(f"Triggering analysis for document ID: {document_id}...")
        response = requests.patch(analysis_url, headers=headers, json=payload)
        response.raise_for_status()
        logging.info(f"Successfully triggered analysis for document ID: {document_id}. Status is now '{response.json().get('status')}'")
        return True
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to trigger analysis for document ID: {document_id}. Error: {e}")
        if e.response:
            logging.error(f"Response status: {e.response.status_code}, body: {e.response.text}")
        return False

# --- Main Execution Logic ---

def main():
    """Main function to run the analysis process."""
    logging.info("--- Starting Document Analysis Script ---")
    
    access_token = login()
    if not access_token:
        logging.error("Could not obtain access token. Exiting.")
        return

    while True:
        # Get the current state of all documents
        all_docs = get_all_documents(access_token)
        if not all_docs:
            logging.warning("No documents found for this user. The script will exit.")
            break
            
        docs_to_process = get_documents_to_process(all_docs)

        if not docs_to_process:
            logging.info("="*50)
            logging.info("All documents have been processed. Script finished successfully!")
            logging.info("="*50)
            break

        logging.info(f"--- Starting new batch of {len(docs_to_process)} documents ---")
        for doc in docs_to_process:
            doc_id = doc.get("id")
            doc_filename = doc.get("filename")
            if not doc_id:
                logging.warning(f"Found a document without an ID: {doc_filename}. Skipping.")
                continue
            
            success = trigger_analysis(access_token, doc_id)
            if success:
                # Rate limit: 10 requests per minute -> 1 request every 6 seconds
                logging.info("Waiting 6 seconds before next request...")
                time.sleep(6)
            else:
                logging.warning(f"Skipping wait for document {doc_id} due to trigger failure.")

        logging.info("--- Batch finished. Waiting 60 seconds before checking again... ---")
        time.sleep(60)

if __name__ == "__main__":
    main() 