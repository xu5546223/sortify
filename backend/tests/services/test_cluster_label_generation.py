"""
測試聚類標籤生成功能

這個測試文件驗證 AI 標籤生成在聚類服務中的集成
"""

import pytest
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.clustering_service import ClusteringService
from app.services.unified_ai_service_simplified import AIResponse, AIRequest, TaskType
from app.models.ai_models_simplified import AIClusterLabelOutput


@pytest.fixture
def mock_db():
    """模擬數據庫連接"""
    db = MagicMock()
    
    # 模擬文檔查詢結果
    async def mock_find(*args, **kwargs):
        class MockCursor:
            def __init__(self):
                self.documents = [
                    {
                        "_id": uuid.uuid4(),
                        "filename": "invoice_001.pdf",
                        "enriched_data": {
                            "title": "7-11 發票",
                            "summary": "購買御飯糰和飲料的發票,總金額 80 元",
                            "keywords": ["發票", "7-11", "消費", "食品"]
                        }
                    },
                    {
                        "_id": uuid.uuid4(),
                        "filename": "receipt_002.jpg",
                        "enriched_data": {
                            "title": "全家便利商店收據",
                            "summary": "購買便當和零食,總計 120 元",
                            "keywords": ["收據", "全家", "消費", "便當"]
                        }
                    },
                    {
                        "_id": uuid.uuid4(),
                        "filename": "invoice_003.pdf",
                        "enriched_data": {
                            "title": "OK 超商發票",
                            "summary": "購買飲料和小吃,金額 65 元",
                            "keywords": ["發票", "OK", "消費", "零食"]
                        }
                    }
                ]
            
            def __aiter__(self):
                return self
            
            async def __anext__(self):
                if self.documents:
                    return self.documents.pop(0)
                raise StopAsyncIteration
        
        return MockCursor()
    
    db.__getitem__ = MagicMock(return_value=MagicMock(find=mock_find))
    return db


@pytest.fixture
def clustering_service():
    """創建聚類服務實例"""
    return ClusteringService()


class TestClusterLabelGeneration:
    """測試聚類標籤生成功能"""
    
    @pytest.mark.asyncio
    async def test_generate_cluster_label_success(self, clustering_service, mock_db):
        """測試成功生成聚類標籤"""
        
        # 模擬 AI 服務響應
        mock_ai_output = AIClusterLabelOutput(
            cluster_name="便利商店發票 · 消費記錄",
            cluster_description="包含各種便利商店的購物發票和收據,主要為小額日常消費",
            common_themes=["便利商店", "日常消費", "食品飲料"],
            suggested_keywords=["發票", "收據", "消費", "便利商店"],
            confidence=0.92,
            reasoning="所有文檔都是便利商店的消費記錄,內容高度一致"
        )
        
        mock_ai_response = AIResponse(
            success=True,
            task_type=TaskType.CLUSTER_LABEL_GENERATION,
            model_used="gemini-2.0-flash",
            output_data=mock_ai_output,
            processing_time_seconds=2.5
        )
        
        # 模擬文檔 ID
        document_ids = [str(uuid.uuid4()) for _ in range(3)]
        
        # Patch UnifiedAIService
        with patch('app.services.clustering_service.unified_ai_service_simplified') as mock_ai_service:
            mock_ai_service.process_request = AsyncMock(return_value=mock_ai_response)
            
            # 調用標籤生成
            cluster_name = await clustering_service._generate_cluster_label(
                db=mock_db,
                cluster_id="cluster_test_0",
                document_ids=document_ids
            )
            
            # 驗證結果
            assert cluster_name == "便利商店發票 · 消費記錄"
            assert mock_ai_service.process_request.called
            
            # 驗證 AI 請求參數
            call_args = mock_ai_service.process_request.call_args
            ai_request = call_args[0][0]
            assert ai_request.task_type == TaskType.CLUSTER_LABEL_GENERATION
            assert "sample_count" in ai_request.prompt_params
            assert "document_samples" in ai_request.prompt_params
    
    @pytest.mark.asyncio
    async def test_generate_cluster_label_fallback(self, clustering_service, mock_db):
        """測試 AI 失敗時的降級處理"""
        
        # 模擬 AI 服務失敗
        mock_ai_response = AIResponse(
            success=False,
            task_type=TaskType.CLUSTER_LABEL_GENERATION,
            error_message="API 配額耗盡",
            processing_time_seconds=1.0
        )
        
        document_ids = [str(uuid.uuid4()) for _ in range(3)]
        
        with patch('app.services.clustering_service.unified_ai_service_simplified') as mock_ai_service:
            mock_ai_service.process_request = AsyncMock(return_value=mock_ai_response)
            
            # 調用標籤生成
            cluster_name = await clustering_service._generate_cluster_label(
                db=mock_db,
                cluster_id="cluster_test_0",
                document_ids=document_ids
            )
            
            # 驗證降級到簡單方法
            assert cluster_name is not None
            assert len(cluster_name) > 0
            # 簡單方法應該返回關鍵詞組合
            assert any(kw in cluster_name for kw in ["發票", "收據", "消費"])
    
    @pytest.mark.asyncio
    async def test_generate_cluster_label_simple(self, clustering_service, mock_db):
        """測試簡單標籤生成方法"""
        
        document_ids = [str(uuid.uuid4()) for _ in range(3)]
        
        # 直接測試簡單方法
        cluster_name = await clustering_service._generate_cluster_label_simple(
            db=mock_db,
            sample_doc_ids=document_ids
        )
        
        # 驗證結果
        assert cluster_name is not None
        assert len(cluster_name) > 0
        # 應該包含最常見的關鍵詞
        assert any(kw in cluster_name for kw in ["發票", "收據", "消費"])
        # 檢查長度限制
        assert len(cluster_name) <= 30
    
    @pytest.mark.asyncio
    async def test_empty_documents(self, clustering_service, mock_db):
        """測試空文檔列表的情況"""
        
        # 模擬空的文檔查詢結果
        async def mock_empty_find(*args, **kwargs):
            class EmptyCursor:
                def __aiter__(self):
                    return self
                async def __anext__(self):
                    raise StopAsyncIteration
            return EmptyCursor()
        
        mock_db.__getitem__ = MagicMock(
            return_value=MagicMock(find=mock_empty_find)
        )
        
        document_ids = []
        
        # 調用標籤生成
        cluster_name = await clustering_service._generate_cluster_label(
            db=mock_db,
            cluster_id="cluster_test_0",
            document_ids=document_ids
        )
        
        # 應該返回默認標籤
        assert cluster_name in ["未分類文檔", "未命名分類"]


class TestAIClusterLabelOutput:
    """測試 AIClusterLabelOutput 模型"""
    
    def test_model_validation_success(self):
        """測試模型驗證成功"""
        data = {
            "cluster_name": "技術文檔 · 規格書",
            "cluster_description": "包含各種技術文檔和系統規格書",
            "common_themes": ["API", "架構", "設計"],
            "suggested_keywords": ["技術", "文檔", "API", "架構"],
            "confidence": 0.88,
            "reasoning": "文檔都涉及技術規格和系統設計"
        }
        
        output = AIClusterLabelOutput(**data)
        
        assert output.cluster_name == "技術文檔 · 規格書"
        assert output.confidence == 0.88
        assert len(output.common_themes) == 3
        assert len(output.suggested_keywords) == 4
    
    def test_model_validation_minimal(self):
        """測試最小必需欄位"""
        data = {
            "cluster_name": "一般文檔"
        }
        
        output = AIClusterLabelOutput(**data)
        
        assert output.cluster_name == "一般文檔"
        assert output.cluster_description is None
        assert output.common_themes == []
        assert output.suggested_keywords == []
        assert output.confidence is None
    
    def test_model_json_parsing(self):
        """測試 JSON 解析"""
        json_str = '''
        {
            "cluster_name": "發票 · 收據 · 記帳",
            "cluster_description": "日常消費記錄",
            "common_themes": ["消費", "記帳"],
            "suggested_keywords": ["發票", "收據"],
            "confidence": 0.90,
            "reasoning": "都是消費相關文檔"
        }
        '''
        
        output = AIClusterLabelOutput.model_validate_json(json_str)
        
        assert output.cluster_name == "發票 · 收據 · 記帳"
        assert output.confidence == 0.90


class TestPromptFormatting:
    """測試提示詞格式化"""
    
    def test_document_samples_formatting(self):
        """測試文檔樣本格式化"""
        documents = [
            {
                "title": "7-11 發票",
                "summary": "購買御飯糰和飲料",
                "keywords": ["發票", "7-11", "消費"]
            },
            {
                "title": "全家收據",
                "summary": "購買便當",
                "keywords": ["收據", "全家"]
            }
        ]
        
        # 格式化樣本
        samples = []
        for doc in documents:
            keywords_str = ", ".join(doc["keywords"])
            sample = f"- 標題: {doc['title']}\n  摘要: {doc['summary']}\n  關鍵詞: {keywords_str}"
            samples.append(sample)
        
        samples_text = "\n\n".join(samples)
        
        # 驗證格式
        assert "標題: 7-11 發票" in samples_text
        assert "摘要: 購買御飯糰和飲料" in samples_text
        assert "關鍵詞: 發票, 7-11, 消費" in samples_text
        assert "標題: 全家收據" in samples_text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

