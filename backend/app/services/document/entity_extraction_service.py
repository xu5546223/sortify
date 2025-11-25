"""
實體提取和語義豐富化服務
從AI分析結果中提取結構化實體並生成enriched_data
"""

import logging
from typing import Dict, Any, Optional, List
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime

from app.models.document_models import Document
from app.core.logging_utils import AppLogger, log_event, LogLevel

logger = AppLogger(__name__, level=logging.INFO).get_logger()


class EntityExtractionService:
    """實體提取和語義豐富化服務"""
    
    def __init__(self):
        pass  # 不需要 embedding_service,向量化在專門的向量化服務中處理
    
    async def enrich_document(
        self,
        db: AsyncIOMotorDatabase,
        document: Document,
        ai_analysis_output: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        從AI分析結果中提取並豐富化文檔數據
        
        Args:
            db: 數據庫連接
            document: 文檔對象
            ai_analysis_output: AI分析的完整輸出
        
        Returns:
            enriched_data 字典,包含 title, summary, entities, keywords, embedding_generated
        """
        try:
            await log_event(
                db=db,
                level=LogLevel.DEBUG,
                message=f"開始為文檔 {document.id} 提取實體和豐富化數據",
                source="service.entity_extraction.enrich_document",
                details={"document_id": str(document.id), "filename": document.filename}
            )
            
            # 優化後的enriched_data結構 - 只保存元數據,不重複存儲AI輸出
            # 標題、摘要、實體、關鍵詞都直接從 ai_analysis_output.key_information 讀取
            key_information = ai_analysis_output.get("key_information", {})
            
            # 預計算一些元數據用於快速過濾和統計
            structured_entities = key_information.get("structured_entities", {})
            searchable_keywords = key_information.get("searchable_keywords", [])
            
            enriched_data: Dict[str, Any] = {
                # 數據可用性標記
                "ai_data_available": True,
                "has_auto_title": bool(key_information.get("auto_title")),
                "has_structured_entities": bool(structured_entities),
                
                # 關鍵詞 (用於聚類關鍵詞提取)
                "keywords": searchable_keywords if isinstance(searchable_keywords, list) else [],
                
                # 預計算的統計元數據 (用於快速過濾,不重複存儲內容)
                "metadata": {
                    "entity_types": list(structured_entities.keys()) if structured_entities else [],
                    "entity_count": sum(
                        len(v) if isinstance(v, list) else 1 
                        for v in structured_entities.values()
                    ) if structured_entities else 0,
                    "keyword_count": len(searchable_keywords) if isinstance(searchable_keywords, list) else 0,
                    "content_length": len(key_information.get("content_summary") or ""),
                    "has_vendor": "vendor" in structured_entities if structured_entities else False,
                    "has_amounts": (structured_entities and "amounts" in structured_entities and structured_entities.get("amounts") and len(structured_entities.get("amounts", [])) > 0) if structured_entities else False,
                    "has_dates": (structured_entities and "dates" in structured_entities and structured_entities.get("dates") and len(structured_entities.get("dates", [])) > 0) if structured_entities else False,
                    "content_type": ai_analysis_output.get("content_type") or "unknown"
                }
            }
            
            # 5. 生成embedding (基於summary和keywords的組合)
            # 注意: 這裡不直接生成,而是標記需要生成
            # 實際的embedding生成會在向量化服務中處理
            enriched_data["embedding_generated"] = False
            
            await log_event(
                db=db,
                level=LogLevel.INFO,
                message=f"成功為文檔 {document.id} 生成enriched_data (優化版)",
                source="service.entity_extraction.enrich_document",
                details={
                    "document_id": str(document.id),
                    "has_auto_title": enriched_data["has_auto_title"],
                    "entity_count": enriched_data["metadata"]["entity_count"],
                    "keyword_count": enriched_data["metadata"]["keyword_count"]
                }
            )
            
            return enriched_data
            
        except Exception as e:
            logger.error(f"為文檔 {document.id} 提取實體時發生錯誤: {e}", exc_info=True)
            await log_event(
                db=db,
                level=LogLevel.ERROR,
                message=f"為文檔 {document.id} 提取實體失敗: {str(e)}",
                source="service.entity_extraction.enrich_document.error",
                details={"document_id": str(document.id), "error": str(e)}
            )
            # 返回最小化的enriched_data
            return {
                "ai_data_available": False,
                "has_auto_title": False,
                "has_structured_entities": False,
                "metadata": {},
                "embedding_generated": False
            }

    def get_document_text(self, document: Document) -> Optional[str]:
        """
        獲取文檔的文本內容
        使用現有的 extracted_text 欄位
        
        Args:
            document: 文檔對象
        
        Returns:
            文本字符串,如果無法獲取則返回None
        """
        try:
            # 直接使用 extracted_text 欄位
            if document.extracted_text:
                return document.extracted_text
            
            # 備用: 從AI分析結果中提取
            if document.analysis and document.analysis.ai_analysis_output:
                ai_output = document.analysis.ai_analysis_output
                
                # 對於圖片分析,提取extracted_text
                extracted_text = ai_output.get("extracted_text")
                if extracted_text:
                    return extracted_text
                
                # 對於文本分析,可能沒有單獨的extracted_text
                # 可以使用initial_summary作為備用
                initial_summary = ai_output.get("initial_summary")
                if initial_summary:
                    return initial_summary
            
            return None
            
        except Exception as e:
            logger.error(f"獲取文檔 {document.id} 文本時發生錯誤: {e}")
            return None

