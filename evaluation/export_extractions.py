import os

# --- Ensure output directories exist before logging setup ---
if not os.path.exists('evaluation'):
    os.makedirs('evaluation')
if not os.path.exists('evaluation/extractions'):
    os.makedirs('evaluation/extractions')

import requests
import logging
from dotenv import load_dotenv
from typing import List, Dict, Any, Optional
from tqdm import tqdm

# --- Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('evaluation/export.log')
    ]
)

# --- Environment Variable Check ---
if not os.path.exists('evaluation/.env'):
    logging.error("The '.env' file is missing in the 'evaluation' directory.")
    logging.error("Please create it with API_URL, USERNAME, and PASSWORD.")
    exit(1)

load_dotenv(dotenv_path='evaluation/.env', override=True)

API_URL = os.getenv("API_URL")
USERNAME = os.getenv("USERNAME")
PASSWORD = os.getenv("PASSWORD")

if not all([API_URL, USERNAME, PASSWORD]):
    logging.error("One or more required environment variables are missing from .env file.")
    exit(1)

# --- Constants ---
OUTPUT_DIR = "evaluation/extractions"

# --- API Interaction Functions ---

def login() -> Optional[str]:
    """Logs in to the API and returns the access token."""
    login_url = f"{API_URL}/api/v1/auth/token"
    login_data = {'username': USERNAME, 'password': PASSWORD}
    try:
        logging.info(f"Attempting to log in as user '{USERNAME}'...")
        response = requests.post(login_url, data=login_data)
        response.raise_for_status()
        token = response.json().get("access_token")
        if token:
            logging.info("Login successful.")
            return token
        logging.error("Login response did not contain an access token.")
        return None
    except requests.exceptions.RequestException as e:
        logging.error(f"Login failed: {e}")
        return None

def get_all_documents(token: str) -> List[Dict[str, Any]]:
    """Fetches all documents for the current user, handling pagination."""
    all_documents = []
    documents_url = f"{API_URL}/api/v1/documents/"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"limit": 100, "skip": 0}
    
    logging.info("Fetching all documents from the API...")
    with requests.Session() as session:
        session.headers.update(headers)
        while True:
            try:
                response = session.get(documents_url, params=params)
                response.raise_for_status()
                data = response.json()
                documents = data.get("items", [])
                if not documents:
                    break
                all_documents.extend(documents)
                params["skip"] += params["limit"]
            except requests.exceptions.RequestException as e:
                logging.error(f"Failed to fetch documents: {e}")
                return []
    logging.info(f"Successfully fetched {len(all_documents)} total document records.")
    return all_documents

def filter_documents_with_any_extracted_text(documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    過濾出有 extracted_text（頂層）、analysis.extracted_text、analysis.text_content.full_text、analysis.ai_analysis_output.extracted_text 的文件。
    匯出時會標記來源欄位。
    """
    result = []
    for doc in documents:
        text_to_export = None
        source = None
        # 1. 頂層 extracted_text
        if doc.get("extracted_text"):
            text_to_export = doc["extracted_text"]
            source = "extracted_text"
        # 2. analysis.extracted_text
        elif doc.get("analysis") and doc["analysis"].get("extracted_text"):
            text_to_export = doc["analysis"]["extracted_text"]
            source = "analysis.extracted_text"
        # 3. analysis.text_content.full_text
        elif doc.get("analysis") and doc["analysis"].get("text_content") and doc["analysis"]["text_content"].get("full_text"):
            text_to_export = doc["analysis"]["text_content"]["full_text"]
            source = "analysis.text_content.full_text"
        # 4. analysis.ai_analysis_output.extracted_text
        elif doc.get("analysis") and doc["analysis"].get("ai_analysis_output") and doc["analysis"]["ai_analysis_output"].get("extracted_text"):
            text_to_export = doc["analysis"]["ai_analysis_output"]["extracted_text"]
            source = "analysis.ai_analysis_output.extracted_text"
        if text_to_export:
            doc["_text_to_export"] = text_to_export
            doc["_text_source"] = source
            result.append(doc)
    logging.info(f"Found {len(result)} documents with any extracted text.")
    return result

def export_to_markdown(document: Dict[str, Any]):
    """Saves the extracted text of a document to a Markdown file, with filename info."""
    try:
        original_filename = document.get("filename", f"unknown_document_{document.get('id')}")
        safe_filename = original_filename.replace("/", "_").replace("\\", "_")
        output_filename = f"{safe_filename}.md"
        output_path = os.path.join(OUTPUT_DIR, output_filename)
        full_text = document.get("_text_to_export", "")
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(f"<!-- 檔案名稱: {original_filename} -->\n\n")
            f.write(full_text)
    except Exception as e:
        logging.error(f"Failed to export document ID {document.get('id')}: {e}")

# --- Main Execution Logic ---

def main():
    """Main function to run the export process."""
    logging.info("--- Starting Document Export Script ---")
    
    # Ensure output directory exists
    if not os.path.exists(OUTPUT_DIR):
        logging.info(f"Creating output directory: {OUTPUT_DIR}")
        os.makedirs(OUTPUT_DIR)
        
    access_token = login()
    if not access_token:
        logging.error("Could not obtain access token. Exiting.")
        return

    all_docs = get_all_documents(access_token)
    if not all_docs:
        logging.warning("No documents found for this user. Nothing to export.")
        return
        
    docs_to_export = filter_documents_with_any_extracted_text(all_docs)

    # === 新增：找出未匯出的文件 ===
    exported_ids = set(doc.get("id") for doc in docs_to_export)
    not_exported = [doc for doc in all_docs if doc.get("id") not in exported_ids]
    if not_exported:
        not_exported_path = os.path.join(OUTPUT_DIR, "not_exported.txt")
        with open(not_exported_path, "w", encoding="utf-8") as f:
            f.write("未匯出文件清單（沒有extracted_text）：\n\n")
            for doc in not_exported:
                f.write(f"檔名: {doc.get('filename', '無名')}\tID: {doc.get('id', '')}\t狀態: {doc.get('status', '')}\n")
        logging.info(f"未匯出清單已產生：{not_exported_path}")

    if not docs_to_export:
        logging.warning("No documents with extracted_text found. Nothing to export.")
        return

    logging.info(f"Exporting extracted_text from {len(docs_to_export)} documents to '{OUTPUT_DIR}'...")
    
    # Use tqdm for a progress bar
    for doc in tqdm(docs_to_export, desc="Exporting Documents"):
        export_to_markdown(doc)

    logging.info("="*50)
    logging.info("Export process finished successfully!")
    logging.info(f"Markdown files saved in: {os.path.abspath(OUTPUT_DIR)}")
    logging.info("="*50)

if __name__ == "__main__":
    main() 