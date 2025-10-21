"""
問題分類器測試

測試問題分類器的各種場景
"""
import pytest
from app.models.question_models import QuestionIntent, QuestionClassification


class TestQuestionClassifier:
    """問題分類器測試類"""
    
    @pytest.mark.asyncio
    async def test_greeting_classification(self):
        """測試寒暄問候分類"""
        from app.services.question_classifier_service import question_classifier_service
        
        test_questions = [
            "你好",
            "嗨",
            "Hello",
            "早安"
        ]
        
        for question in test_questions:
            # 使用回退分類測試(不調用API)
            classification = question_classifier_service._get_fallback_classification(
                question, "測試"
            )
            
            assert classification.intent == QuestionIntent.GREETING
            assert classification.confidence >= 0.7
            assert not classification.requires_documents
            print(f"✓ '{question}' → {classification.intent.value}")
    
    @pytest.mark.asyncio
    async def test_clarification_needed_classification(self):
        """測試需要澄清的問題"""
        from app.services.question_classifier_service import question_classifier_service
        
        test_questions = [
            "那個文檔",
            "之前說的",
            "剛才提到的"
        ]
        
        for question in test_questions:
            classification = question_classifier_service._get_fallback_classification(
                question, "測試"
            )
            
            assert classification.intent == QuestionIntent.CLARIFICATION_NEEDED
            assert classification.clarification_question is not None
            print(f"✓ '{question}' → {classification.intent.value}")
    
    @pytest.mark.asyncio
    async def test_document_search_fallback(self):
        """測試文檔搜索回退判斷"""
        from app.services.question_classifier_service import question_classifier_service
        
        question = "幫我找財務報表"
        
        classification = question_classifier_service._get_fallback_classification(
            question, "測試"
        )
        
        assert classification.intent == QuestionIntent.DOCUMENT_SEARCH
        assert classification.requires_documents
        print(f"✓ '{question}' → {classification.intent.value}")


if __name__ == "__main__":
    import asyncio
    
    async def run_tests():
        test_instance = TestQuestionClassifier()
        
        print("\n=== 測試寒暄問候 ===")
        await test_instance.test_greeting_classification()
        
        print("\n=== 測試需要澄清 ===")
        await test_instance.test_clarification_needed_classification()
        
        print("\n=== 測試文檔搜索 ===")
        await test_instance.test_document_search_fallback()
        
        print("\n✅ 所有測試通過!")
    
    asyncio.run(run_tests())

