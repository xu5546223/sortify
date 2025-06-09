#!/usr/bin/env python3
"""
測試數據集生成 - 互動式執行腳本
基於Google API的1+N問題生成策略
"""

import os
import sys
import asyncio
from pathlib import Path
from datetime import datetime

def print_banner():
    """打印程式橫幅"""
    print("=" * 80)
    print("🤖 sortify 測試數據集生成器 - 1+N策略版本")
    print("   基於Google API，實現智能的主題級+細節級問題生成")
    print("   🌟 已針對Google免費API優化，支援AI質量驗證")
    print("=" * 80)

def print_strategy_explanation():
    """打印1+N策略說明"""
    print("\n📋 1+N問題生成策略說明:")
    print("   🎯 主題級問題（每個文檔1個）：")
    print("      - 基於文檔的語義摘要生成")
    print("      - 測試對文檔整體內容的理解")
    print("      - 適合摘要向量檢索")
    print()
    print("   🔍 細節級問題（每個文檔N個）：")
    print("      - 基於文檔的內容塊(chunks)生成")
    print("      - 測試對具體細節的精確理解")
    print("      - 適合內容塊向量檢索")
    print()
    print("   📊 預期效果：平衡測試不同檢索策略的性能")

def print_google_api_info():
    """打印Google API使用信息"""
    print("\n🔑 Google API使用提醒:")
    print("   📊 速率限制: 15次/分鐘")
    print("   ⚡ 每個問題: 1次生成調用")
    print("   🔍 AI驗證（可選）: 1次驗證調用")
    print("   ⏳ 預估時間: 無驗證約4秒/問題，有驗證約8秒/問題")
    print("   💡 建議: 從較小的文檔數量開始測試")

def check_prerequisites():
    """檢查運行前置條件"""
    print("\n🔍 檢查運行環境...")
    
    # 檢查Python版本
    if sys.version_info < (3, 8):
        print("❌ 錯誤: 需要 Python 3.8 或更高版本")
        return False
    
    # 檢查必要的套件
    required_packages = [
        ('aiohttp', 'aiohttp'),
        ('python-dotenv', 'dotenv'),
        ('google-generativeai', 'google.generativeai')
    ]
    missing_packages = []
    
    for package_name, import_name in required_packages:
        try:
            __import__(import_name)
        except ImportError:
            missing_packages.append(package_name)
    
    if missing_packages:
        print(f"❌ 缺少必要套件: {', '.join(missing_packages)}")
        print("請執行: pip install -r requirements.txt")
        return False
    
    # 動態導入並執行環境檢查
    try:
        from generate_test_dataset import load_environment_config, validate_required_env_vars
        print("🔄 正在從 generate_test_dataset.py 導入環境檢查程序...")
        load_environment_config()
        validate_required_env_vars()
    except ImportError:
        print("❌ 無法從 generate_test_dataset.py 導入，請確保文件存在且無誤。")
        return False
    except Exception as e:
        print(f"❌ 環境配置檢查失敗: {e}")
        return False
    
    print("✅ 運行環境檢查通過")
    return True

def estimate_time_and_cost(document_ratio, detail_questions, enable_validation):
    """估算生成時間和API調用"""
    # 假設用戶有200個文檔（可調整）
    estimated_total_docs = 200
    selected_docs = int(estimated_total_docs * document_ratio)
    
    questions_per_doc = 1 + detail_questions
    total_questions = selected_docs * questions_per_doc
    
    # API調用計算
    generation_calls = total_questions
    validation_calls = total_questions if enable_validation else 0
    total_api_calls = generation_calls + validation_calls
    
    # 時間估算（基於15次/分鐘）
    estimated_minutes = total_api_calls / 15
    
    return {
        'selected_docs': selected_docs,
        'total_questions': total_questions,
        'generation_calls': generation_calls,
        'validation_calls': validation_calls,
        'total_api_calls': total_api_calls,
        'estimated_minutes': estimated_minutes
    }

def get_user_input():
    """獲取用戶輸入參數"""
    print("\n📝 請輸入生成參數 (按 Enter 使用建議值):")
    
    # 文檔選擇比例
    while True:
        ratio_input = input("文檔選擇比例 (0.1-1.0) [預設: 0.5]: ").strip()
        if not ratio_input:
            document_ratio = 0.5
            break
        try:
            document_ratio = float(ratio_input)
            if 0.1 <= document_ratio <= 1.0:
                break
            else:
                print("❌ 請輸入 0.1 到 1.0 之間的數值")
        except ValueError:
            print("❌ 請輸入有效的數字")
    
    # 每個文檔的細節級問題數量
    while True:
        detail_input = input("每個文檔的細節級問題數量 (1-5) [預設: 2]: ").strip()
        if not detail_input:
            detail_questions = 2
            break
        try:
            detail_questions = int(detail_input)
            if 1 <= detail_questions <= 5:
                break
            else:
                print("❌ 請輸入 1 到 5 之間的整數")
        except ValueError:
            print("❌ 請輸入有效的整數")
    
    # AI驗證選項
    validation_input = input("啟用AI質量驗證? (會增加API調用數量) [y/N]: ").strip().lower()
    enable_validation = validation_input in ['y', 'yes', '是']
    
    # 估算時間和成本
    estimate = estimate_time_and_cost(document_ratio, detail_questions, enable_validation)
    
    print(f"\n📊 生成預估:")
    print(f"   - 預計選擇文檔數: {estimate['selected_docs']}")
    print(f"   - 預計生成問題數: {estimate['total_questions']}")
    print(f"   - 生成API調用: {estimate['generation_calls']}")
    print(f"   - 驗證API調用: {estimate['validation_calls']}")
    print(f"   - 總API調用: {estimate['total_api_calls']}")
    print(f"   - 預估時間: {estimate['estimated_minutes']:.1f} 分鐘")
    
    # 確認是否繼續
    continue_input = input("\n繼續生成? [Y/n]: ").strip().lower()
    if continue_input in ['n', 'no', '否']:
        return None
    
    # 輸出文件名
    default_filename = f"test_dataset_1plus{detail_questions}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    output_file = input(f"輸出文件名 [預設: {default_filename}]: ").strip()
    if not output_file:
        output_file = default_filename
    
    return {
        'document_ratio': document_ratio,
        'detail_questions': detail_questions,
        'enable_validation': enable_validation,
        'output_file': output_file,
        'estimate': estimate
    }

def print_configuration(params):
    """打印生成配置"""
    generation_model = os.getenv('GENERATION_MODEL', 'gemini-1.5-flash')
    validation_model = os.getenv('VALIDATION_MODEL', 'gemini-1.5-flash')

    print("\n⚙️  生成配置:")
    print(f"   📊 文檔選擇比例: {params['document_ratio']:.1%}")
    print(f"   📝 每文檔問題數: 1主題級 + {params['detail_questions']}細節級")
    print(f"   📁 輸出文件: {params['output_file']}")
    print(f"   🤖 AI驗證: {'啟用' if params['enable_validation'] else '禁用'}")
    print(f"   🧠 生成模型: {generation_model}")
    if params['enable_validation']:
        print(f"   🧐 驗證模型: {validation_model}")
    print(f"   ⏱️  預估時間: {params['estimate']['estimated_minutes']:.1f} 分鐘")

async def run_generation(params):
    """執行數據生成"""
    print(f"\n🚀 開始生成測試數據集...")
    
    # 動態導入生成器
    try:
        from generate_test_dataset import TestDatasetGenerator
    except ImportError as e:
        print(f"❌ 導入生成器失敗: {e}")
        return False
    
    generator = TestDatasetGenerator()
    
    try:
        # 初始化API連接
        print("🔐 初始化API連接...")
        await generator.initialize_api_connection()
        
        # 生成數據集
        result = await generator.generate_test_dataset(
            target_document_ratio=params['document_ratio'],
            output_path=params['output_file']
        )
        
        # 輸出結果
        stats = result['statistics']
        print("\n🎉 生成完成！")
        print(f"📊 統計信息:")
        print(f"   - 選擇文檔: {stats['documents_selected']}")
        print(f"   - 主題級問題: {stats['summary_questions_generated']}")
        print(f"   - 細節級問題: {stats['detail_questions_generated']}")
        print(f"   - 總問答對: {stats['total_qa_pairs']}")
        print(f"   - 生成成功率: {stats['generation_success_rate']:.2%}")
        if params['enable_validation']:
            print(f"   - 驗證成功率: {stats['validation_success_rate']:.2%}")
            print(f"   - 整體成功率: {stats['overall_success_rate']:.2%}")
        print(f"   - 總耗時: {stats['total_generation_time_seconds']/60:.1f} 分鐘")
        
        print(f"\n📁 生成的文件:")
        print(f"   - 評估用文件: {params['output_file']}")
        print(f"   - 詳細信息文件: {params['output_file'].replace('.json', '_detailed.json')}")
        
        return True
        
    except Exception as e:
        print(f"❌ 生成失敗: {e}")
        return False
    finally:
        await generator.close()

def print_next_steps(success, output_file):
    """打印後續步驟"""
    print("\n" + "=" * 80)
    if success:
        print("✅ 測試數據集生成成功！")
        print("\n📋 後續步驟:")
        print(f"   1. 檢查生成的數據集:")
        print(f"      cat {output_file}")
        print(f"   2. 使用評估腳本進行多模式對比測試:")
        print(f"      python evaluate_vector_retrieval.py --dataset {output_file} --mode compare")
        print(f"   3. 使用評估腳本進行RRF權重調優:")
        print(f"      python evaluate_vector_retrieval.py --dataset {output_file} --mode optimize_weights")
        print(f"   4. 使用評估腳本進行RRF權重+K值聯合調優:")
        print(f"      python evaluate_vector_retrieval.py --dataset {output_file} --mode optimize_weights_k")
        print(f"\n💡 提示:")
        print(f"   - 生成的 {output_file} 可直接用於 evaluate_vector_retrieval.py")
        print(f"   - 詳細版本包含生成元數據，用於分析和調試")
    else:
        print("❌ 測試數據集生成失敗")
        print("\n🔧 排錯建議:")
        print("   1. 檢查 .env 文件配置是否正確")
        print("   2. 確認Google API Key是否有效")
        print("   3. 確認後端服務正在運行")
        print("   4. 檢查用戶權限和文檔數據")
        print("   5. 查看日誌文件: generate_test_dataset.log")
        print("\n📖 參考文檔:")
        print("   - README_1plus_n_generator.md")
    print("=" * 80)

def print_env_example():
    """打印環境變數示例"""
    print("\n📝 .env 文件配置示例:")
    print("=" * 50)
    print("# API連接配置")
    print("API_URL=http://localhost:8000")
    print("USERNAME=your_username")
    print("PASSWORD=your_password")
    print()
    print("# Google AI配置")
    print("GOOGLE_API_KEY=your_google_api_key")
    print()
    print("# 生成配置（可選）")
    print("GENERATION_MODEL=gemini-1.5-flash")
    print("VALIDATION_MODEL=gemini-1.5-flash")
    print("API_RATE_LIMIT=15")
    print("ENABLE_AI_VALIDATION=true")
    print("DETAIL_QUESTIONS_PER_DOC=2")
    print("=" * 50)

async def main():
    """主函數"""
    print_banner()
    print_strategy_explanation()
    print_google_api_info()
    
    # 檢查前置條件
    if not check_prerequisites():
        print_env_example()
        return
    
    # 獲取用戶輸入
    params = get_user_input()
    if params is None:
        print("生成已取消")
        return
    
    # 顯示配置
    print_configuration(params)
    
    # 最終確認
    print("\n❓ 確認開始生成? [Y/n]: ", end="")
    confirm = input().strip().lower()
    if confirm in ['n', 'no', '否']:
        print("生成已取消")
        return
    
    # 執行生成
    success = await run_generation(params)
    
    # 顯示後續步驟
    print_next_steps(success, params['output_file'])

if __name__ == "__main__":
    # 設置事件循環策略 (Windows兼容性)
    if sys.platform.startswith('win'):
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n🛑 用戶中斷操作")
    except Exception as e:
        print(f"\n❌ 程式執行錯誤: {e}")
        sys.exit(1) 