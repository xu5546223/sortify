"""
MongoDB 工具函數模塊

提供 MongoDB 相關的工具函數。
遷移自 enhanced_ai_qa_service.py
"""


def remove_projection_path_collisions(projection: dict) -> dict:
    """
    移除 MongoDB projection 中的父子欄位衝突，只保留最底層欄位。
    
    Args:
        projection: MongoDB projection 字典
        
    Returns:
        dict: 清理後的 projection 字典
        
    Example:
        >>> projection = {"metadata": 1, "metadata.tags": 1}
        >>> remove_projection_path_collisions(projection)
        {"metadata.tags": 1}  # 移除了父欄位 "metadata"
    """
    if not projection or not isinstance(projection, dict):
        return projection
    
    keys = list(projection.keys())
    keys_to_remove = set()
    
    for k in keys:
        for other in keys:
            if k == other:
                continue
            # k 是 other 的子欄位，則移除父欄位 other
            if k.startswith(other + "."):
                keys_to_remove.add(other)
            # other 是 k 的子欄位，則移除父欄位 k
            elif other.startswith(k + "."):
                keys_to_remove.add(k)
    
    for k in keys_to_remove:
        projection.pop(k, None)
    
    return projection
