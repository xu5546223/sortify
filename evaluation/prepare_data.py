import json
import logging
import uuid
import re
from typing import List, Dict, Any, Optional
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic_settings import BaseSettings
import os
from dotenv import load_dotenv
from bson import ObjectId
from bson.binary import Binary  # 添加Binary導入

# 載入 .env 文件
load_dotenv()

# 設定日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    mongodb_url: str = os.getenv("MONGODB_URL")
    db_name: str = os.getenv("DB_NAME", "sortify_db")

    class Config:
        env_file = ".env"
        extra = "allow"  # 允許額外的字段

settings = Settings()

async def get_document_filenames_with_ids() -> Dict[str, str]:
    """從資料庫獲取所有文件的檔案名稱和對應的文檔ID"""
    try:
        client = AsyncIOMotorClient(settings.mongodb_url)
        db = client[settings.db_name]
        documents = await db.documents.find({}, {"filename": 1, "_id": 1}).to_list(length=None)
        
        # 建立檔案名稱到文檔ID的映射
        filename_to_id = {}
        for doc in documents:
            if "filename" in doc and "_id" in doc:
                # 詳細處理不同類型的ID
                doc_id = doc["_id"]
                logging.debug(f"Processing document ID - Type: {type(doc_id)}, Value: {repr(doc_id)}")
                
                if isinstance(doc_id, Binary):
                    # 處理 bson.binary.Binary 類型 (您的系統使用的格式)
                    try:
                        uuid_obj = uuid.UUID(bytes=doc_id)
                        doc_id_str = str(uuid_obj)
                        logging.debug(f"Binary converted to UUID: {doc_id_str}")
                    except ValueError:
                        # 如果不是有效的UUID bytes，使用十六進制
                        doc_id_str = doc_id.hex()
                        logging.warning(f"Binary converted to hex: {doc_id_str}")
                elif isinstance(doc_id, ObjectId):
                    doc_id_str = str(doc_id)  # ObjectId 的正確字符串表示
                    logging.debug(f"ObjectId converted to: {doc_id_str}")
                elif isinstance(doc_id, uuid.UUID):
                    doc_id_str = str(doc_id)  # UUID轉字符串
                    logging.debug(f"UUID converted to: {doc_id_str}")
                elif isinstance(doc_id, (str, bytes)):
                    if isinstance(doc_id, bytes):
                        # 處理二進制格式 - 嘗試多種轉換方式
                        try:
                            # 嘗試作為UUID bytes
                            doc_id_uuid = uuid.UUID(bytes=doc_id) 
                            doc_id_str = str(doc_id_uuid)
                            logging.debug(f"Bytes converted to UUID: {doc_id_str}")
                        except ValueError:
                            # 如果不是UUID格式的bytes，使用十六進制表示
                            doc_id_str = doc_id.hex()
                            logging.debug(f"Bytes converted to hex: {doc_id_str}")
                    else:
                        # 已經是字符串
                        doc_id_str = doc_id
                        logging.debug(f"String ID: {doc_id_str}")
                else:
                    # 其他格式，直接轉換
                    doc_id_str = str(doc_id)
                    logging.warning(f"Unrecognized ID type {type(doc_id)}, converted to: {doc_id_str}")
                
                filename_to_id[doc["filename"]] = doc_id_str
                logging.debug(f"Mapped filename '{doc['filename']}' to ID '{doc_id_str}'")
        
        logging.info(f"Retrieved {len(filename_to_id)} filename-to-ID mappings from database")
        if filename_to_id:
            # 顯示前3個映射作為示例
            sample_items = list(filename_to_id.items())[:3]
            logging.info(f"Sample filename-to-ID mappings: {dict(sample_items)}")
        
        return filename_to_id
    except Exception as e:
        logging.error(f"Error connecting to MongoDB: {e}")
        return {}
    finally:
        client.close()

def extract_filename(output: str) -> Optional[str]:
    """從輸出中提取檔案名稱"""
    # 更強健的正則表達式，處理可能的換行和額外空格
    pattern = r'<!--\s*檔案名稱:\s*([^>]+?)\s*-->'
    match = re.search(pattern, output, re.MULTILINE | re.DOTALL)
    if match:
        filename = match.group(1).strip()
        logging.debug(f"Extracted filename: '{filename}'")
        return filename
    logging.debug(f"No filename found in output: {output[-100:]}")  # 只顯示最後100個字符
    return None

async def process_data():
    """
    Loads data from datasets2.json and processes it into two datasets:
    1. RAG evaluation dataset (with filename that exists in database) - ragas格式
    2. QA evaluation dataset (ALL data, regardless of filename) - 標準格式
    """
    input_filepath = "QAdataset.json"
    rag_output_filepath = "evaluation/processed_rag_dataset.json"
    qa_output_filepath = "evaluation/processed_qa_dataset.json"
    
    rag_data: List[Dict[str, Any]] = []
    qa_data: List[Dict[str, Any]] = []

    records_processed = 0
    records_with_valid_filename = 0
    records_without_valid_filename = 0

    # 獲取資料庫中所有檔案的檔案名稱和ID映射
    filename_to_id = await get_document_filenames_with_ids()
    valid_filenames = list(filename_to_id.keys())
    logging.info(f"Found {len(valid_filenames)} valid filenames in database")
    logging.info(f"Sample filename-to-ID mappings: {dict(list(filename_to_id.items())[:3]) if filename_to_id else 'None'}")

    try:
        with open(input_filepath, 'r', encoding='utf-8') as f:
            dataset = json.load(f)
    except FileNotFoundError:
        logging.error(f"Input file not found: {input_filepath}")
        return
    except json.JSONDecodeError:
        logging.error(f"Error decoding JSON from file: {input_filepath}")
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
        
        # 清理答案，移除檔案名稱註釋
        clean_answer = re.sub(r'<!--\s*檔案名稱:.*?-->', '', original_answer).strip()

        # 所有資料都加入 QA 評估資料集
        qa_item = {
            "query_id": query_id,
            "question": user_query,
            "ground_truth": clean_answer,
            "original_answer": original_answer,
            "dataset_type": "qa_evaluation"
        }
        qa_data.append(qa_item)

        # 只有有效檔案名稱的資料加入 RAG 評估
        if filename and filename in valid_filenames:
            # 使用檔案名稱獲取對應的MongoDB文檔ID
            document_id = filename_to_id[filename]
            
            rag_item = {
                "query_id": query_id,
                "question": user_query,  # ragas 使用 question 而不是 user_query
                "ground_truth": clean_answer,  # ragas 使用 ground_truth
                "expected_relevant_doc_ids": [document_id],  # 使用MongoDB UUID而非檔案名稱
                "relevance_scores": {document_id: 1.0},
                "original_answer": original_answer,
                "original_filename": filename,
                "dataset_type": "rag_evaluation"  # 標記資料集類型
            }
            rag_data.append(rag_item)
            records_with_valid_filename += 1
            logging.info(f"Added to both RAG and QA datasets: {filename} -> {document_id}")
        else:
            records_without_valid_filename += 1
            if filename:
                logging.warning(f"Filename '{filename}' not found in database, added to QA only: {user_query[:50]}...")
            else:
                logging.debug(f"No filename extracted, added to QA only: {user_query[:50]}...")

    # 儲存 RAG 評估資料集
    try:
        with open(rag_output_filepath, 'w', encoding='utf-8') as f:
            json.dump(rag_data, f, ensure_ascii=False, indent=4)
        logging.info(f"Successfully wrote RAG evaluation data to {rag_output_filepath}")
    except IOError as e:
        logging.error(f"Could not write RAG evaluation data to file {rag_output_filepath}: {e}")

    # 儲存 QA 評估資料集
    try:
        with open(qa_output_filepath, 'w', encoding='utf-8') as f:
            json.dump(qa_data, f, ensure_ascii=False, indent=4)
        logging.info(f"Successfully wrote QA evaluation data to {qa_output_filepath}")
    except IOError as e:
        logging.error(f"Could not write QA evaluation data to file {qa_output_filepath}: {e}")

    logging.info("--- Processing Summary ---")
    logging.info(f"Total records processed: {records_processed}")
    logging.info(f"Records added to QA evaluation: {len(qa_data)} (ALL records)")
    logging.info(f"Records added to RAG evaluation: {records_with_valid_filename} (only with valid filenames)")
    logging.info(f"Records without valid filename: {records_without_valid_filename}")

if __name__ == "__main__":
    asyncio.run(process_data())
