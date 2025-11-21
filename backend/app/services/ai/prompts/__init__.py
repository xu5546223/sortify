"""
Prompts 模塊 - 提示詞管理系統

統一管理所有 AI 提示詞模板，支持模塊化組織和統一調度
"""

# 導出基礎定義
from .base import PromptType, PromptTemplate

# 導出統一調度器
from .registry import PromptRegistry, prompt_registry

# 導出各個模塊的 prompt getter 函數
from .document_prompts import (
    get_image_analysis_prompt,
    get_text_analysis_prompt
)
from .search_prompts import (
    get_query_rewrite_prompt,
    get_document_selection_prompt
)
from .qa_prompts import (
    get_answer_generation_prompt,
    get_answer_generation_stream_prompt
)
from .mongodb_prompts import (
    get_mongodb_detail_query_prompt
)
from .clustering_prompts import (
    get_cluster_label_generation_prompt,
    get_batch_cluster_label_generation_prompt
)
from .intent_prompts import (
    get_question_intent_classification_prompt,
    get_clarification_question_prompt
)
from .question_prompts import (
    get_question_generation_prompt
)

__all__ = [
    # 基礎類型
    'PromptType',
    'PromptTemplate',
    
    # 調度器
    'PromptRegistry',
    'prompt_registry',
    
    # 文檔分析
    'get_image_analysis_prompt',
    'get_text_analysis_prompt',
    
    # 搜索相關
    'get_query_rewrite_prompt',
    'get_document_selection_prompt',
    
    # 問答生成
    'get_answer_generation_prompt',
    'get_answer_generation_stream_prompt',
    
    # MongoDB 查詢
    'get_mongodb_detail_query_prompt',
    
    # 聚類標籤
    'get_cluster_label_generation_prompt',
    'get_batch_cluster_label_generation_prompt',
    
    # 意圖分類
    'get_question_intent_classification_prompt',
    'get_clarification_question_prompt',
    
    # 問題生成
    'get_question_generation_prompt',
]
