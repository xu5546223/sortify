"""
文檔數據助手函數
提供統一的方法來訪問文檔的AI分析數據,避免重複代碼
"""

from typing import Dict, Any, Optional, List


def get_document_title(document_dict: Dict[str, Any]) -> str:
    """
    獲取文檔標題
    優先從 AI 輸出的 auto_title 獲取,否則使用文件名
    
    Args:
        document_dict: 文檔字典 (從MongoDB獲取)
    
    Returns:
        文檔標題
    """
    ai_output = document_dict.get("analysis", {}).get("ai_analysis_output", {})
    key_info = ai_output.get("key_information", {})
    
    return key_info.get("auto_title") or document_dict.get("filename", "未命名文檔")


def get_document_summary(document_dict: Dict[str, Any]) -> str:
    """
    獲取文檔摘要
    從 AI 輸出的 content_summary 獲取
    
    Args:
        document_dict: 文檔字典
    
    Returns:
        文檔摘要
    """
    ai_output = document_dict.get("analysis", {}).get("ai_analysis_output", {})
    key_info = ai_output.get("key_information", {})
    
    return key_info.get("content_summary", "")


def get_document_keywords(document_dict: Dict[str, Any]) -> List[str]:
    """
    獲取文檔關鍵詞
    從 AI 輸出的 searchable_keywords 獲取
    
    Args:
        document_dict: 文檔字典
    
    Returns:
        關鍵詞列表
    """
    ai_output = document_dict.get("analysis", {}).get("ai_analysis_output", {})
    key_info = ai_output.get("key_information", {})
    
    keywords = key_info.get("searchable_keywords", [])
    return keywords if isinstance(keywords, list) else []


def get_document_entities(document_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    獲取文檔實體
    從 AI 輸出的 structured_entities 獲取
    
    Args:
        document_dict: 文檔字典
    
    Returns:
        實體字典
    """
    ai_output = document_dict.get("analysis", {}).get("ai_analysis_output", {})
    key_info = ai_output.get("key_information", {})
    
    return key_info.get("structured_entities", {})


def get_document_content_type(document_dict: Dict[str, Any]) -> str:
    """
    獲取文檔內容類型
    從 AI 輸出獲取
    
    Args:
        document_dict: 文檔字典
    
    Returns:
        內容類型
    """
    ai_output = document_dict.get("analysis", {}).get("ai_analysis_output", {})
    return ai_output.get("content_type", "unknown")


def get_document_ai_data(document_dict: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    獲取完整的 AI 分析數據
    
    Args:
        document_dict: 文檔字典
    
    Returns:
        完整的 key_information 數據,如果不存在返回 None
    """
    ai_output = document_dict.get("analysis", {}).get("ai_analysis_output", {})
    return ai_output.get("key_information")


def format_document_for_display(document_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    格式化文檔數據用於顯示
    從AI輸出提取所有需要的字段
    
    Args:
        document_dict: 文檔字典
    
    Returns:
        格式化後的顯示數據
    """
    return {
        "id": str(document_dict.get("_id", "")),
        "filename": document_dict.get("filename", ""),
        "title": get_document_title(document_dict),
        "summary": get_document_summary(document_dict),
        "keywords": get_document_keywords(document_dict),
        "entities": get_document_entities(document_dict),
        "content_type": get_document_content_type(document_dict),
        "status": document_dict.get("status", ""),
        "created_at": document_dict.get("created_at"),
        "updated_at": document_dict.get("updated_at")
    }


def has_ai_analysis(document_dict: Dict[str, Any]) -> bool:
    """
    檢查文檔是否有 AI 分析數據
    
    Args:
        document_dict: 文檔字典
    
    Returns:
        是否有 AI 分析數據
    """
    ai_output = document_dict.get("analysis", {}).get("ai_analysis_output")
    return ai_output is not None and isinstance(ai_output, dict)

