import re
from typing import List
from app.core.config import settings

def create_text_chunks(text: str, chunk_size: int = None, chunk_overlap: int = 50) -> List[str]:
    """
    將長文本切分成帶有重疊的塊
    
    Args:
        text: 要分塊的文本
        chunk_size: 每個塊的字符數（如果為None，使用embedding模型的限制）
        chunk_overlap: 塊之間的重疊字符數
        
    Returns:
        文本塊列表
    """
    if not text or not text.strip():
        return []
    
    # 如果沒有指定chunk_size，使用embedding模型的限制，並預留一些空間
    if chunk_size is None:
        max_embedding_length = getattr(settings, 'EMBEDDING_MAX_LENGTH', 512)
        chunk_size = max_embedding_length - 50  # 預留50字符的安全邊界
    
    # 清理文本
    text = text.strip()
    
    # 如果文本長度小於分塊大小，直接返回
    if len(text) <= chunk_size:
        return [text]
    
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + chunk_size
        
        # 如果不是最後一塊，嘗試在句子邊界處切分
        if end < len(text):
            # 尋找句子結束符號（句號、問號、感嘆號）
            sentence_end_pattern = r'[。！？.!?]'
            
            # 在當前塊的後半部分尋找句子邊界
            search_start = max(start + chunk_size // 2, end - 100)
            search_text = text[search_start:end + 50]  # 稍微延展搜索範圍
            
            matches = list(re.finditer(sentence_end_pattern, search_text))
            if matches:
                # 使用最後一個句子邊界
                last_match = matches[-1]
                actual_end = search_start + last_match.end()
                if actual_end > start:  # 確保不會產生空塊
                    end = actual_end
        
        chunk = text[start:end].strip()
        if chunk:  # 只添加非空塊
            chunks.append(chunk)
        
        # 計算下一個開始位置，考慮重疊
        start = max(start + 1, end - chunk_overlap)
        
        # 防止無限循環
        if start >= len(text):
            break
    
    return chunks

def smart_truncate(text: str, max_length: int) -> str:
    """
    智能截斷文本，盡量在句子或詞語邊界截斷
    
    Args:
        text: 要截斷的文本
        max_length: 最大長度
        
    Returns:
        截斷後的文本
    """
    if not text or max_length <= 0:
        return ""
    
    if len(text) <= max_length:
        return text
    
    # 如果需要截斷，嘗試在較好的位置截斷
    truncated = text[:max_length-3]  # 預留 "..." 的空間
    
    # 嘗試在句子邊界截斷
    sentence_endings = ['。', '！', '？', '.', '!', '?']
    best_cut = -1
    for ending in sentence_endings:
        pos = truncated.rfind(ending)
        if pos > len(truncated) * 0.7:  # 至少保留70%的內容
            best_cut = pos + 1
            break
    
    # 如果沒找到句子邊界，嘗試在詞語邊界截斷
    if best_cut == -1:
        word_boundaries = [' ', '，', '、', ',', ';', '；']
        for boundary in word_boundaries:
            pos = truncated.rfind(boundary)
            if pos > len(truncated) * 0.8:  # 至少保留80%的內容
                best_cut = pos
                break
    
    if best_cut > 0:
        return text[:best_cut] + "..."
    else:
        return truncated + "..."

def smart_compress_list(items: List[str], max_length: int) -> str:
    """
    智能壓縮列表為字符串，優先保留更多項目
    
    Args:
        items: 要壓縮的字符串列表
        max_length: 最大長度
        
    Returns:
        壓縮後的字符串
    """
    if not items or max_length <= 0:
        return ""
    
    # 如果沒有長度限制問題，直接返回
    full_string = ', '.join(items)
    if len(full_string) <= max_length:
        return full_string
    
    # 需要壓縮：優先保留更多項目，必要時截短每個項目
    compressed_items = []
    current_length = 0
    separator_length = 2  # ", " 的長度
    
    # 計算平均每個項目可以分配的長度
    estimated_item_length = (max_length - (len(items) - 1) * separator_length) // len(items)
    estimated_item_length = max(estimated_item_length, 3)  # 至少保留3個字符
    
    for i, item in enumerate(items):
        if not item:
            continue
            
        # 如果是最後一個項目，使用剩餘的所有空間
        if i == len(items) - 1:
            remaining_space = max_length - current_length
            if remaining_space > 0:
                compressed_item = smart_truncate(item, remaining_space)
                if compressed_item:
                    compressed_items.append(compressed_item)
            break
        
        # 壓縮當前項目
        compressed_item = smart_truncate(item, estimated_item_length)
        if compressed_item:
            # 檢查添加這個項目是否會超長
            item_with_separator = compressed_item + (", " if compressed_items else "")
            if current_length + len(item_with_separator) <= max_length:
                compressed_items.append(compressed_item)
                current_length += len(item_with_separator)
            else:
                # 沒有空間了，停止添加
                break
    
    result = ', '.join(compressed_items)
    
    # 如果還有項目沒有包含，添加省略號提示
    if len(compressed_items) < len([item for item in items if item]):
        remaining_count = len([item for item in items if item]) - len(compressed_items)
        ellipsis = f"...+{remaining_count}項"
        if len(result) + len(ellipsis) <= max_length:
            result += ellipsis
        elif len(ellipsis) < max_length:
            # 縮短結果為省略號騰出空間
            result = result[:max_length - len(ellipsis)] + ellipsis
    
    return result
