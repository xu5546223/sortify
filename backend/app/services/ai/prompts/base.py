"""
提示詞管理基礎定義

包含 PromptType 枚舉和 PromptTemplate 數據類
"""

from typing import List
from enum import Enum
from dataclasses import dataclass


class PromptType(Enum):
    """提示詞類型枚舉"""
    # 文檔分析
    IMAGE_ANALYSIS = "image_analysis"
    TEXT_ANALYSIS = "text_analysis"
    
    # 搜索相關
    QUERY_REWRITE = "query_rewrite"
    DOCUMENT_SELECTION_FOR_QUERY = "document_selection_for_query"
    
    # 問答生成
    ANSWER_GENERATION = "answer_generation"  # JSON 格式輸出（非流式）
    ANSWER_GENERATION_STREAM = "answer_generation_stream"  # Markdown 格式輸出（流式）

    # 聚類標籤
    CLUSTER_LABEL_GENERATION = "cluster_label_generation"  # 單個聚類標籤生成
    BATCH_CLUSTER_LABEL_GENERATION = "batch_cluster_label_generation"  # 批量聚類標籤生成
    
    # 意圖分類
    QUESTION_INTENT_CLASSIFICATION = "question_intent_classification"  # 問題意圖分類
    GENERATE_CLARIFICATION_QUESTION = "generate_clarification_question"  # 生成澄清問題
    
    # 問題生成
    QUESTION_GENERATION = "question_generation"  # 生成建議問題


@dataclass
class PromptTemplate:
    """提示詞模板結構"""
    prompt_type: PromptType
    system_prompt: str
    user_prompt_template: str
    variables: List[str]
    description: str
    version: str = "2.0"
    is_active: bool = True
