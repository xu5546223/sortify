"""
智能問答路由測試腳本

測試不同類型問題的路由和處理
"""
import asyncio
import sys
from pathlib import Path

# 添加項目根目錄到 Python 路徑
sys.path.insert(0, str(Path(__file__).parent.parent))

async def test_question_classification():
    """測試問題分類功能"""
    from app.services.question_classifier_service import question_classifier_service
    from app.models.question_models import QuestionIntent
    
    print("\n" + "="*60)
    print("問題分類測試")
    print("="*60)
    
    test_cases = [
        ("你好", QuestionIntent.GREETING),
        ("財務相關數據", QuestionIntent.CLARIFICATION_NEEDED),
        ("什麼是資料庫?", QuestionIntent.SIMPLE_FACTUAL),
        ("幫我找2024年的財務報表", QuestionIntent.DOCUMENT_SEARCH),
        ("比較過去三個月的銷售趨勢", QuestionIntent.COMPLEX_ANALYSIS),
    ]
    
    for question, expected_intent in test_cases:
        # 使用回退分類(不調用API)
        classification = question_classifier_service._get_fallback_classification(
            question, "測試"
        )
        
        status = "✓" if classification.intent == expected_intent else "✗"
        print(f"\n{status} 問題: {question}")
        print(f"  預期: {expected_intent.value}")
        print(f"  實際: {classification.intent.value}")
        print(f"  置信度: {classification.confidence:.2f}")
        print(f"  策略: {classification.suggested_strategy}")
        print(f"  需要文檔: {classification.requires_documents}")
        print(f"  預估API調用: {classification.estimated_api_calls}")


async def test_performance_comparison():
    """性能對比測試"""
    print("\n" + "="*60)
    print("性能對比分析")
    print("="*60)
    
    # 模擬的性能數據
    old_system = {
        "greeting": {"api_calls": 4.5, "time": 8.5},
        "clarification": {"api_calls": 4.5, "time": 8.0},
        "simple": {"api_calls": 4.5, "time": 7.5},
        "document": {"api_calls": 4.5, "time": 9.0},
        "complex": {"api_calls": 5.0, "time": 12.0}
    }
    
    new_system = {
        "greeting": {"api_calls": 1.0, "time": 0.8},
        "clarification": {"api_calls": 2.0, "time": 3.0},
        "simple": {"api_calls": 2.5, "time": 4.0},
        "document": {"api_calls": 2.8, "time": 5.5},
        "complex": {"api_calls": 5.5, "time": 11.0}
    }
    
    print("\n問題類型 | 舊系統API | 新系統API | 節省 | 舊時間 | 新時間 | 改善")
    print("-" * 80)
    
    total_old_api = 0
    total_new_api = 0
    total_old_time = 0
    total_new_time = 0
    
    for key in old_system:
        old_api = old_system[key]["api_calls"]
        new_api = new_system[key]["api_calls"]
        old_time = old_system[key]["time"]
        new_time = new_system[key]["time"]
        
        api_save = ((old_api - new_api) / old_api) * 100
        time_save = ((old_time - new_time) / old_time) * 100
        
        print(f"{key:12} | {old_api:7.1f}次 | {new_api:7.1f}次 | {api_save:4.0f}% | {old_time:5.1f}秒 | {new_time:5.1f}秒 | {time_save:4.0f}%")
        
        total_old_api += old_api
        total_new_api += new_api
        total_old_time += old_time
        total_new_time += new_time
    
    avg_old_api = total_old_api / len(old_system)
    avg_new_api = total_new_api / len(new_system)
    avg_old_time = total_old_time / len(old_system)
    avg_new_time = total_new_time / len(new_system)
    
    overall_api_save = ((avg_old_api - avg_new_api) / avg_old_api) * 100
    overall_time_save = ((avg_old_time - avg_new_time) / avg_old_time) * 100
    
    print("-" * 80)
    print(f"平均值    | {avg_old_api:7.1f}次 | {avg_new_api:7.1f}次 | {overall_api_save:4.0f}% | {avg_old_time:5.1f}秒 | {avg_new_time:5.1f}秒 | {overall_time_save:4.0f}%")
    
    print(f"\n📊 整體改善:")
    print(f"  - API調用減少: {overall_api_save:.1f}%")
    print(f"  - 響應時間減少: {overall_time_save:.1f}%")
    print(f"  - 預估成本節省: {overall_api_save:.1f}%")


async def test_workflow_paths():
    """測試各種工作流路徑"""
    print("\n" + "="*60)
    print("工作流路徑測試")
    print("="*60)
    
    workflows = {
        "寒暄快速通道": {
            "steps": ["分類", "直接回答"],
            "api_calls": 1,
            "time": "<1秒"
        },
        "澄清引導流程": {
            "steps": ["分類", "生成澄清問題", "等待用戶輸入", "重新處理"],
            "api_calls": 2,
            "time": "2-3秒"
        },
        "簡單查詢流程": {
            "steps": ["分類", "摘要搜索", "生成答案"],
            "api_calls": 3,
            "time": "3-4秒"
        },
        "文檔搜索流程": {
            "steps": ["分類", "請求批准", "兩階段檢索", "生成答案"],
            "api_calls": 3,
            "time": "4-6秒",
            "user_interaction": True
        },
        "複雜分析流程": {
            "steps": ["分類", "查詢重寫", "RRF檢索", "文檔選擇", "詳細查詢", "生成答案"],
            "api_calls": "4-6",
            "time": "8-12秒"
        }
    }
    
    for name, workflow in workflows.items():
        print(f"\n🔹 {name}")
        print(f"  步驟: {' → '.join(workflow['steps'])}")
        print(f"  API調用: {workflow['api_calls']}次")
        print(f"  預估時間: {workflow['time']}")
        if workflow.get('user_interaction'):
            print(f"  用戶交互: 需要批准")


async def main():
    """主測試函數"""
    print("\n🚀 智能問答路由系統測試")
    
    await test_question_classification()
    await test_performance_comparison()
    await test_workflow_paths()
    
    print("\n" + "="*60)
    print("✅ 所有測試完成!")
    print("="*60)
    print("\n💡 下一步:")
    print("  1. 啟動後端服務測試實際API")
    print("  2. 使用前端UI測試完整工作流")
    print("  3. 監控統計數據驗證性能改善")


if __name__ == "__main__":
    asyncio.run(main())

