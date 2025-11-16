"""
全局測試配置

定義全局的 pytest 配置和通用 fixtures。
"""

import pytest
from uuid import UUID
from unittest.mock import AsyncMock, patch


def pytest_addoption(parser):
    """
    添加自定義命令行選項
    """
    parser.addoption(
        "--run-real-api",
        action="store_true",
        default=False,
        help="運行需要真實 AI API 調用的測試（默認使用 Mock）"
    )
    parser.addoption(
        "--mock-ai",
        action="store_true",
        default=True,
        help="自動 Mock AI 服務（默認啟用）"
    )


def pytest_configure(config):
    """
    Pytest 配置鉤子 - 註冊自定義標記
    """
    # 註冊測試標記
    config.addinivalue_line(
        "markers",
        "unit: 單元測試，使用 mock，不依賴外部資源"
    )
    config.addinivalue_line(
        "markers",
        "integration: 整合測試，使用真實數據庫，測試完整流程"
    )
    config.addinivalue_line(
        "markers",
        "slow: 慢速測試，可能調用外部 API"
    )
    config.addinivalue_line(
        "markers",
        "real_api: 需要真實 AI API 的測試"
    )


# 通用 fixtures（所有測試都可用）

@pytest.fixture
def fixed_uuid():
    """固定的 UUID 用於測試（可預測）"""
    return UUID('12345678-1234-5678-1234-567812345678')


@pytest.fixture
def another_fixed_uuid():
    """另一個固定的 UUID 用於測試"""
    return UUID('87654321-4321-8765-4321-876543218765')


# ========== AI Mock Fixtures ==========

@pytest.fixture
def mock_ai_answer():
    """
    標準 Mock AI 答案
    
    Returns:
        dict: 模擬的 AI 生成答案
    """
    return {
        "answer": "這是一個模擬的 AI 回答。Python 是一種高級程式語言，廣泛應用於 Web 開發、數據分析、人工智能等領域。",
        "tokens_used": 120,
        "confidence_score": 0.85,
        "processing_time": 0.5
    }


@pytest.fixture
def auto_mock_ai(request, mock_ai_answer):
    """
    自動 Mock AI 服務（默認啟用）
    
    用法:
        @pytest.mark.usefixtures("auto_mock_ai")
        async def test_something(...):
            # AI 服務已被自動 Mock
    
    或在測試文件頂部:
        pytestmark = pytest.mark.usefixtures("auto_mock_ai")
    
    注意: 標記為 real_api 的測試不會自動 Mock
    """
    # 檢查測試是否標記為 real_api
    use_real_api = request.node.get_closest_marker('real_api') is not None
    
    if not use_real_api:
        # Mock AI 服務實例的方法
        with patch('app.services.ai.unified_ai_service_simplified.unified_ai_service_simplified.generate_answer',
                   new_callable=AsyncMock) as mock_generate, \
             patch('app.services.ai.unified_ai_service_simplified.unified_ai_service_simplified.rewrite_query',
                   new_callable=AsyncMock) as mock_rewrite, \
             patch('app.services.qa_workflow.question_classifier_service.question_classifier_service.classify_question',
                   new_callable=AsyncMock) as mock_classify:
            
            # 設置默認返回值
            mock_generate.return_value = mock_ai_answer
            
            mock_rewrite.return_value = {
                "original_query": "測試問題",
                "rewritten_queries": ["測試問題 1", "測試問題 2", "測試問題 3"],
                "intent_analysis": "informational",
                "extracted_parameters": {}
            }
            
            mock_classify.return_value = {
                "intent": "document_search",
                "confidence": 0.9,
                "needs_clarification": False
            }
            
            yield {
                'generate': mock_generate,
                'rewrite': mock_rewrite,
                'classify': mock_classify
            }
    else:
        # 使用真實 API
        yield None
