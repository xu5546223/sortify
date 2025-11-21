"""
Prompt Registry - 統一的提示詞調度器

負責管理和分發所有類型的提示詞模板
"""

from typing import Dict, Optional
from .base import PromptType, PromptTemplate
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


class PromptRegistry:
    """
    統一的提示詞注冊表
    
    負責：
    1. 初始化所有提示詞模板
    2. 提供統一的訪問接口
    3. 支持動態更新和覆蓋
    """
    
    def __init__(self):
        """初始化提示詞注冊表"""
        self._prompts: Dict[PromptType, PromptTemplate] = {}
        self._initialize_all_prompts()
    
    def _initialize_all_prompts(self):
        """從各個模塊初始化所有提示詞"""
        
        # 文檔分析類
        self._prompts[PromptType.IMAGE_ANALYSIS] = get_image_analysis_prompt()
        self._prompts[PromptType.TEXT_ANALYSIS] = get_text_analysis_prompt()
        
        # 搜索相關
        self._prompts[PromptType.QUERY_REWRITE] = get_query_rewrite_prompt()
        self._prompts[PromptType.DOCUMENT_SELECTION_FOR_QUERY] = get_document_selection_prompt()
        
        # 問答生成
        self._prompts[PromptType.ANSWER_GENERATION] = get_answer_generation_prompt()
        self._prompts[PromptType.ANSWER_GENERATION_STREAM] = get_answer_generation_stream_prompt()
        
        # MongoDB 查詢
        self._prompts[PromptType.MONGODB_DETAIL_QUERY_GENERATION] = get_mongodb_detail_query_prompt()
        
        # 聚類標籤
        self._prompts[PromptType.CLUSTER_LABEL_GENERATION] = get_cluster_label_generation_prompt()
        self._prompts[PromptType.BATCH_CLUSTER_LABEL_GENERATION] = get_batch_cluster_label_generation_prompt()
        
        # 意圖分類
        self._prompts[PromptType.QUESTION_INTENT_CLASSIFICATION] = get_question_intent_classification_prompt()
        self._prompts[PromptType.GENERATE_CLARIFICATION_QUESTION] = get_clarification_question_prompt()
        
        # 問題生成
        self._prompts[PromptType.QUESTION_GENERATION] = get_question_generation_prompt()
    
    def get_prompt(self, prompt_type: PromptType) -> Optional[PromptTemplate]:
        """
        獲取指定類型的提示詞模板
        
        Args:
            prompt_type: 提示詞類型
            
        Returns:
            對應的提示詞模板，如果不存在則返回 None
        """
        return self._prompts.get(prompt_type)
    
    def register_prompt(self, prompt_template: PromptTemplate):
        """
        註冊或更新提示詞模板
        
        Args:
            prompt_template: 要註冊的提示詞模板
        """
        self._prompts[prompt_template.prompt_type] = prompt_template
    
    def get_all_prompts(self) -> Dict[PromptType, PromptTemplate]:
        """獲取所有提示詞模板"""
        return self._prompts.copy()
    
    def get_prompt_types(self) -> list:
        """獲取所有已註冊的提示詞類型"""
        return list(self._prompts.keys())


# 創建全局實例
prompt_registry = PromptRegistry()
