#!/usr/bin/env python3
"""
獨立的性能測試腳本 - 測試向量化和ChromaDB性能
"""

import os
import sys
import time
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
import numpy as np
from typing import List

# 添加項目根目錄到 Python 路徑
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 設置基本環境變數
os.environ['MONGODB_URL'] = 'mongodb://localhost:27017'
os.environ['DB_NAME'] = 'test_db'

class SimplePerformanceTest:
    """簡化的性能測試類"""
    
    def __init__(self):
        self.test_texts = [
            "這是一個測試文檔，包含中文和English混合內容。",
            "人工智能正在改變我們的生活方式，從智能手機到自動駕駛汽車。",
            "機器學習算法可以幫助我們分析大量數據並發現隱藏的模式。",
            "深度學習網絡模仿人腦神經元的工作方式來處理複雜問題。",
            "自然語言處理技術使計算機能夠理解和生成人類語言。",
            "This is a comprehensive document about artificial intelligence and machine learning applications.",
            "Vector databases are becoming increasingly important for semantic search systems.",
            "Large language models have revolutionized natural language processing capabilities.",
            "Embedding models convert text into high-dimensional vectors for semantic analysis.",
            "RAG systems combine vector search with generative AI for accurate responses."
        ]
        
        # 嘗試導入和初始化embedding服務
        self.embedding_service = None
        self.init_embedding_service()
        
        # 初始化ChromaDB服務
        self.vector_service = None
        self.init_vector_service()
    
    def init_embedding_service(self):
        """初始化Embedding服務"""
        try:
            # 嘗試導入Sentence Transformers
            from sentence_transformers import SentenceTransformer
            import torch
            
            print("🚀 初始化Embedding服務...")
            
            # 詳細的 GPU 檢測
            print("\n🔍 GPU 檢測詳情:")
            print(f"   PyTorch 版本: {torch.__version__}")
            print(f"   CUDA 可用: {torch.cuda.is_available()}")
            
            if torch.cuda.is_available():
                print(f"   CUDA 版本: {torch.version.cuda}")
                print(f"   GPU 數量: {torch.cuda.device_count()}")
                for i in range(torch.cuda.device_count()):
                    gpu_name = torch.cuda.get_device_name(i)
                    gpu_memory = torch.cuda.get_device_properties(i).total_memory / 1024**3
                    print(f"   GPU {i}: {gpu_name} ({gpu_memory:.1f}GB)")
                    
                device = "cuda"
                print("   ✅ 將使用 GPU 加速")
            else:
                device = "cpu"
                print("   ⚠️  CUDA 不可用，將使用 CPU")
                
                # 檢查是否安裝了 CPU 版本的 PyTorch
                if "cpu" in torch.__version__:
                    print("   📝 檢測到 CPU 版本的 PyTorch")
                    print("   💡 如要啟用 GPU，請安裝 CUDA 版本的 PyTorch:")
                    print("      pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121")
            
            model_name = "paraphrase-multilingual-mpnet-base-v2"
            
            # 檢查模型緩存
            cache_dir = os.path.expanduser("~/.cache/huggingface/hub")
            model_cache_path = Path(cache_dir) / f"models--sentence-transformers--{model_name.replace('/', '--')}"
            
            if model_cache_path.exists():
                print(f"\n✅ 檢測到模型緩存: {model_name}")
            else:
                print(f"\n⚠️  模型 {model_name} 尚未緩存，首次加載將下載模型文件")
            
            # 加載模型並測量時間
            print(f"\n⏳ 正在加載模型到 {device.upper()}...")
            start_time = time.time()
            
            self.embedding_service = SentenceTransformer(
                model_name,
                device=device
            )
            
            loading_time = time.time() - start_time
            
            # 獲取向量維度
            test_embedding = self.embedding_service.encode("test", convert_to_tensor=False)
            self.vector_dimension = len(test_embedding)
            
            print(f"✅ Embedding模型加載成功")
            print(f"   模型名稱: {model_name}")
            print(f"   加載時間: {loading_time:.2f}秒")
            print(f"   向量維度: {self.vector_dimension}")
            print(f"   運行設備: {device.upper()}")
            
            # 如果使用 GPU，顯示 GPU 使用情況
            if device == "cuda" and torch.cuda.is_available():
                # 強制進行一次編碼以確保模型完全加載到 GPU
                _ = self.embedding_service.encode("GPU測試", convert_to_tensor=False)
                
                # 檢查 GPU 記憶體使用
                gpu_memory_allocated = torch.cuda.memory_allocated(0) / 1024**3
                gpu_memory_cached = torch.cuda.memory_reserved(0) / 1024**3
                print(f"   GPU 記憶體已分配: {gpu_memory_allocated:.2f}GB")
                print(f"   GPU 記憶體已緩存: {gpu_memory_cached:.2f}GB")
            
        except ImportError as e:
            print(f"❌ 無法導入Sentence Transformers: {e}")
            print("請安裝：pip install sentence-transformers")
            self.embedding_service = None
        except Exception as e:
            print(f"❌ Embedding服務初始化失敗: {e}")
            self.embedding_service = None
    
    def init_vector_service(self):
        """初始化向量資料庫服務"""
        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings
            
            print("\n🗄️  初始化ChromaDB服務...")
            
            # 使用臨時目錄
            self.test_dir = tempfile.mkdtemp(prefix="perf_test_chromadb_")
            
            # 初始化ChromaDB客戶端
            self.vector_client = chromadb.PersistentClient(
                path=self.test_dir,
                settings=ChromaSettings(anonymized_telemetry=False)
            )
            
            print(f"✅ ChromaDB服務初始化成功")
            print(f"   數據目錄: {self.test_dir}")
            
        except ImportError as e:
            print(f"❌ 無法導入ChromaDB: {e}")
            print("請安裝：pip install chromadb")
            self.vector_service = None
        except Exception as e:
            print(f"❌ ChromaDB服務初始化失敗: {e}")
            self.vector_service = None
    
    def test_embedding_performance(self):
        """測試Embedding性能"""
        if not self.embedding_service:
            print("⚠️  跳過Embedding性能測試（服務未初始化）")
            return {}
        
        print("\n" + "=" * 50)
        print("📝 Embedding 性能測試")
        print("=" * 50)
        
        results = {}
        
        # 測試單文本編碼
        print("\n1. 單文本編碼性能測試...")
        encoding_times = []
        
        for i, text in enumerate(self.test_texts):
            start_time = time.time()
            vector = self.embedding_service.encode(text, convert_to_tensor=False)
            end_time = time.time()
            
            encoding_time = end_time - start_time
            encoding_times.append(encoding_time)
            
            print(f"   文本 {i+1}: {encoding_time*1000:.1f}ms (長度: {len(text)} 字符)")
        
        avg_single_time = sum(encoding_times) / len(encoding_times)
        results['avg_single_encoding_ms'] = avg_single_time * 1000
        print(f"\n   📊 平均單文本編碼時間: {avg_single_time*1000:.1f}ms")
        
        # 測試批量編碼
        print("\n2. 批量編碼性能測試...")
        batch_sizes = [1, 5, 10]
        
        for batch_size in batch_sizes:
            test_batch = self.test_texts[:batch_size]
            
            start_time = time.time()
            vectors = self.embedding_service.encode(
                test_batch, 
                batch_size=batch_size,
                convert_to_tensor=False,
                show_progress_bar=False
            )
            end_time = time.time()
            
            total_time = end_time - start_time
            avg_time_per_text = total_time / len(test_batch)
            
            print(f"   批次大小 {batch_size}: 總時間 {total_time:.2f}s, 平均每文本 {avg_time_per_text*1000:.1f}ms")
            
            if batch_size == 10:
                results['batch_encoding_ms_per_text'] = avg_time_per_text * 1000
        
        return results
    
    def test_chromadb_performance(self):
        """測試ChromaDB性能"""
        if not self.vector_client or not self.embedding_service:
            print("⚠️  跳過ChromaDB性能測試（服務未初始化）")
            return {}
        
        print("\n" + "=" * 50)
        print("🗄️  ChromaDB 性能測試")
        print("=" * 50)
        
        results = {}
        
        try:
            # 創建集合
            collection_name = "performance_test"
            collection = self.vector_client.get_or_create_collection(
                name=collection_name,
                metadata={"dimension": self.vector_dimension}
            )
            print(f"\n✅ 集合創建成功: {collection_name}")
            
            # 生成測試向量
            print("\n1. 生成測試向量...")
            start_time = time.time()
            test_vectors = self.embedding_service.encode(
                self.test_texts,
                convert_to_tensor=False,
                show_progress_bar=False
            )
            vectorization_time = time.time() - start_time
            results['vectorization_time_s'] = vectorization_time
            print(f"   向量生成耗時: {vectorization_time:.2f}s ({len(self.test_texts)} 個文本)")
            
            # 測試插入性能
            print("\n2. 向量插入性能測試...")
            ids = [f"test_doc_{i}" for i in range(len(test_vectors))]
            metadatas = [{"text_length": len(text)} for text in self.test_texts]
            
            start_time = time.time()
            collection.add(
                ids=ids,
                embeddings=test_vectors.tolist() if hasattr(test_vectors, 'tolist') else test_vectors,
                metadatas=metadatas
            )
            insert_time = time.time() - start_time
            results['insert_time_s'] = insert_time
            print(f"   插入 {len(test_vectors)} 個向量耗時: {insert_time:.2f}s")
            print(f"   平均每向量: {insert_time/len(test_vectors)*1000:.1f}ms")
            
            # 測試搜索性能
            print("\n3. 向量搜索性能測試...")
            query_vector = test_vectors[0] if hasattr(test_vectors, '__getitem__') else test_vectors[0]
            
            search_times = []
            for i in range(5):  # 執行5次搜索
                start_time = time.time()
                results_data = collection.query(
                    query_embeddings=[query_vector.tolist() if hasattr(query_vector, 'tolist') else query_vector],
                    n_results=5
                )
                search_time = time.time() - start_time
                search_times.append(search_time)
                
                if i == 0:
                    found_results = len(results_data['ids'][0]) if results_data['ids'] else 0
                    print(f"   搜索結果數量: {found_results}")
            
            avg_search_time = sum(search_times) / len(search_times)
            results['avg_search_time_ms'] = avg_search_time * 1000
            print(f"   平均搜索時間: {avg_search_time*1000:.1f}ms")
            
            # 獲取統計信息
            count = collection.count()
            print(f"\n📊 集合統計: {count} 個向量")
            
        except Exception as e:
            print(f"❌ ChromaDB測試失敗: {e}")
            import traceback
            traceback.print_exc()
        
        return results
    
    def test_end_to_end_workflow(self):
        """測試端到端工作流程"""
        if not self.embedding_service or not self.vector_client:
            print("⚠️  跳過端到端測試（服務未完全初始化）")
            return {}
        
        print("\n" + "=" * 50)
        print("🔄 端到端工作流程性能測試")
        print("=" * 50)
        
        results = {}
        total_start_time = time.time()
        
        # 模擬新文檔
        new_documents = [
            "新增文檔1：關於人工智能在醫療領域的應用研究報告。",
            "新增文檔2：區塊鏈技術在金融行業的創新應用案例分析。",
            "新增文檔3：可持續發展目標與企業社會責任的關係探討。"
        ]
        
        try:
            # 步驟1：向量化新文檔
            print("\n步驟1：向量化新文檔...")
            vectorization_start = time.time()
            new_vectors = self.embedding_service.encode(
                new_documents,
                convert_to_tensor=False,
                show_progress_bar=False
            )
            vectorization_time = time.time() - vectorization_start
            results['new_doc_vectorization_time_s'] = vectorization_time
            print(f"   向量化耗時: {vectorization_time:.2f}s")
            
            # 步驟2：插入到向量資料庫
            print("\n步驟2：插入到向量資料庫...")
            collection = self.vector_client.get_or_create_collection(
                name="workflow_test",
                metadata={"dimension": self.vector_dimension}
            )
            
            new_ids = [f"new_doc_{i}" for i in range(len(new_vectors))]
            new_metadatas = [{"type": "new_document"} for _ in new_documents]
            
            insert_start = time.time()
            collection.add(
                ids=new_ids,
                embeddings=new_vectors.tolist() if hasattr(new_vectors, 'tolist') else new_vectors,
                metadatas=new_metadatas
            )
            insert_time = time.time() - insert_start
            results['new_doc_insert_time_s'] = insert_time
            print(f"   插入耗時: {insert_time:.2f}s")
            
            # 步驟3：測試語義搜索
            print("\n步驟3：測試語義搜索...")
            query = "醫療人工智能應用"
            
            query_start = time.time()
            query_vector = self.embedding_service.encode(query, convert_to_tensor=False)
            search_results = collection.query(
                query_embeddings=[query_vector.tolist() if hasattr(query_vector, 'tolist') else query_vector],
                n_results=5
            )
            query_time = time.time() - query_start
            results['semantic_search_time_s'] = query_time
            
            found_count = len(search_results['ids'][0]) if search_results['ids'] else 0
            print(f"   查詢耗時: {query_time:.2f}s")
            print(f"   找到 {found_count} 個相關文檔")
            
            total_time = time.time() - total_start_time
            results['total_workflow_time_s'] = total_time
            results['documents_processed'] = len(new_documents)
            results['processing_rate_docs_per_sec'] = len(new_documents) / total_time
            
            print(f"\n📊 總工作流程耗時: {total_time:.2f}s")
            print(f"📊 文檔處理速度: {results['processing_rate_docs_per_sec']:.1f} 文檔/秒")
            
        except Exception as e:
            print(f"❌ 端到端測試失敗: {e}")
            import traceback
            traceback.print_exc()
        
        return results
    
    def generate_performance_report(self, embedding_results, chromadb_results, workflow_results):
        """生成性能報告"""
        print("\n" + "=" * 60)
        print("📊 Sortify AI 性能測試總結報告")
        print("=" * 60)
        
        # 硬件信息
        try:
            import torch
            print(f"\n💻 硬件配置:")
            print(f"   • PyTorch 版本: {torch.__version__}")
            print(f"   • 運行設備: {'GPU (CUDA)' if torch.cuda.is_available() else 'CPU'}")
            
            if torch.cuda.is_available():
                gpu_name = torch.cuda.get_device_name(0)
                gpu_memory = torch.cuda.get_device_properties(0).total_memory / 1024**3
                print(f"   • GPU 型號: {gpu_name}")
                print(f"   • GPU 記憶體: {gpu_memory:.1f}GB")
            else:
                print(f"   • CPU 模式: 適合測試和小規模使用")
                if "cpu" in torch.__version__:
                    print(f"   • 建議: 安裝 GPU 版本可提升 3-10倍 性能")
        except:
            pass
        
        # Embedding性能
        if embedding_results:
            print(f"\n🧠 Embedding 性能:")
            print(f"   • 平均單文本編碼: {embedding_results.get('avg_single_encoding_ms', 0):.1f}ms")
            print(f"   • 批量編碼平均: {embedding_results.get('batch_encoding_ms_per_text', 0):.1f}ms/文本")
            
            # 性能分析
            single_time = embedding_results.get('avg_single_encoding_ms', 0)
            batch_time = embedding_results.get('batch_encoding_ms_per_text', 0)
            if batch_time > 0:
                speedup = single_time / batch_time
                print(f"   • 批量處理加速: {speedup:.1f}x")
        
        # ChromaDB性能
        if chromadb_results:
            print(f"\n🗄️  ChromaDB 性能:")
            print(f"   • 向量生成時間: {chromadb_results.get('vectorization_time_s', 0):.2f}s")
            print(f"   • 向量插入時間: {chromadb_results.get('insert_time_s', 0):.2f}s")
            print(f"   • 平均搜索時間: {chromadb_results.get('avg_search_time_ms', 0):.1f}ms")
        
        # 工作流程性能
        if workflow_results:
            print(f"\n🔄 工作流程性能:")
            print(f"   • 新文檔處理速度: {workflow_results.get('processing_rate_docs_per_sec', 0):.1f} 文檔/秒")
            print(f"   • 語義搜索響應: {workflow_results.get('semantic_search_time_s', 0)*1000:.1f}ms")
        
        # 性能建議
        print(f"\n💡 性能優化建議:")
        
        # GPU 相關建議
        try:
            import torch
            if not torch.cuda.is_available():
                print("   🚀 GPU 加速建議:")
                print("      • 安裝 CUDA 版本的 PyTorch 可獲得 3-10倍 性能提升")
                print("      • 命令: pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121")
                print("      • 需要: NVIDIA GPU + CUDA 12.1 驅動")
        except:
            pass
        
        if embedding_results:
            avg_encoding = embedding_results.get('avg_single_encoding_ms', 0)
            if avg_encoding > 500:
                print("   • 編碼較慢，建議啟用GPU加速或使用較小的模型")
            elif avg_encoding < 100:
                print("   • 編碼性能良好！")
        
        if chromadb_results:
            search_time = chromadb_results.get('avg_search_time_ms', 0)
            if search_time > 100:
                print("   • 搜索較慢，考慮優化向量索引或減少數據量")
            elif search_time < 50:
                print("   • 搜索性能優秀！")
        
        if workflow_results:
            processing_rate = workflow_results.get('processing_rate_docs_per_sec', 0)
            if processing_rate > 2:
                print("   • 文檔處理速度很快，系統性能良好")
            elif processing_rate < 0.5:
                print("   • 處理速度較慢，建議批量處理或硬件升級")
        
        print("\n✅ 性能測試完成!")
    
    def run_all_tests(self):
        """執行所有性能測試"""
        print("=" * 60)
        print("🧪 Sortify AI 獨立性能測試")
        print("=" * 60)
        
        try:
            # 執行各項測試
            embedding_results = self.test_embedding_performance()
            chromadb_results = self.test_chromadb_performance()
            workflow_results = self.test_end_to_end_workflow()
            
            # 生成報告
            self.generate_performance_report(embedding_results, chromadb_results, workflow_results)
            
        except Exception as e:
            print(f"❌ 測試過程中發生錯誤: {e}")
            import traceback
            traceback.print_exc()
        
        finally:
            # 清理測試目錄
            if hasattr(self, 'test_dir') and self.test_dir:
                try:
                    shutil.rmtree(self.test_dir)
                    print(f"\n🧹 測試目錄已清理: {self.test_dir}")
                except:
                    pass

def main():
    """主函數"""
    test = SimplePerformanceTest()
    test.run_all_tests()

if __name__ == "__main__":
    main() 