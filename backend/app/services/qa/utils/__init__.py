"""
QA 工具模塊

包含 QA 系統使用的工具類和函數：
- 搜索權重配置
- MongoDB 工具
- 搜索策略決策
- 多樣性優化算法
"""

from app.services.qa.utils.search_weight_config import SearchWeightConfig
from app.services.qa.utils.mongodb_utils import remove_projection_path_collisions
from app.services.qa.utils.search_strategy import (
    extract_search_strategy,
    apply_diversity_optimization
)

__all__ = [
    'SearchWeightConfig',
    'remove_projection_path_collisions',
    'extract_search_strategy',
    'apply_diversity_optimization'
]
