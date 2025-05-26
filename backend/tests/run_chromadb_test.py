#!/usr/bin/env python3
"""
獨立的 ChromaDB 測試腳本 - 不依賴完整應用配置
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
import numpy as np

# 添加項目根目錄到 Python 路徑
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 設置環境變數（避免配置錯誤）
os.environ['MONGODB_URL'] = 'mongodb://localhost:27017'
os.environ['DB_NAME'] = 'test_db'

try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    
    class SimpleVectorRecord:
        """簡化的向量記錄類"""
        def __init__(self, document_id: str, embedding_vector: list, **kwargs):
            self.document_id = document_id
            self.embedding_vector = embedding_vector
            self.metadata = kwargs
    
    class SimpleVectorDatabaseService:
        """簡化的向量資料庫服務"""
        
        def __init__(self, data_path: str = "./test_chromadb"):
            self.data_path = data_path
            self.collection_name = "test_documents"
            self.client = None
            self.collection = None
        
        def create_collection(self, vector_dimension: int):
            """創建集合"""
            try:
                # 確保目錄存在
                os.makedirs(self.data_path, exist_ok=True)
                
                # 初始化ChromaDB客戶端
                self.client = chromadb.PersistentClient(
                    path=self.data_path,
                    settings=ChromaSettings(anonymized_telemetry=False)
                )
                
                # 創建或獲取集合
                self.collection = self.client.get_or_create_collection(
                    name=self.collection_name,
                    metadata={"dimension": vector_dimension}
                )
                
                print(f"✅ 集合創建成功: {self.collection_name}")
                return True
                
            except Exception as e:
                print(f"❌ 集合創建失敗: {e}")
                return False
        
        def insert_vectors(self, vector_records: list) -> bool:
            """插入向量"""
            try:
                if not self.collection:
                    print("❌ 集合未初始化")
                    return False
                
                # 準備數據
                ids = [record.document_id for record in vector_records]
                embeddings = [record.embedding_vector for record in vector_records]
                metadatas = [{"created_at": str(datetime.now())} for _ in vector_records]
                
                # 插入數據
                self.collection.add(
                    ids=ids,
                    embeddings=embeddings,
                    metadatas=metadatas
                )
                
                print(f"✅ 成功插入 {len(vector_records)} 個向量")
                return True
                
            except Exception as e:
                print(f"❌ 向量插入失敗: {e}")
                return False
        
        def search_similar_vectors(self, query_vector: list, top_k: int = 5):
            """搜索相似向量"""
            try:
                if not self.collection:
                    print("❌ 集合未初始化")
                    return []
                
                results = self.collection.query(
                    query_embeddings=[query_vector],
                    n_results=top_k
                )
                
                print(f"✅ 搜索完成，找到 {len(results['ids'][0])} 個結果")
                return results['ids'][0]
                
            except Exception as e:
                print(f"❌ 向量搜索失敗: {e}")
                return []
        
        def get_collection_stats(self):
            """獲取集合統計"""
            try:
                if not self.collection:
                    return {"count": 0, "error": "集合未初始化"}
                
                count = self.collection.count()
                return {"count": count}
                
            except Exception as e:
                return {"count": 0, "error": str(e)}
        
        def delete_by_document_id(self, document_id: str) -> bool:
            """刪除特定文檔的向量"""
            try:
                if not self.collection:
                    return False
                
                self.collection.delete(ids=[document_id])
                print(f"✅ 成功刪除文檔 {document_id} 的向量")
                return True
                
            except Exception as e:
                print(f"❌ 刪除向量失敗: {e}")
                return False
        
        def close_connection(self):
            """關閉連接"""
            if self.client:
                # ChromaDB 會自動持久化數據
                print("✅ 連接關閉成功")

    def test_chromadb_service():
        """測試 ChromaDB 向量資料庫服務的基本功能"""
        
        print("=" * 60)
        print("🧪 開始測試 ChromaDB 向量資料庫服務")
        print("=" * 60)
        
        # 使用臨時目錄進行測試
        test_dir = tempfile.mkdtemp(prefix="chromadb_test_")
        
        try:
            # 初始化服務
            service = SimpleVectorDatabaseService(test_dir)
            print("✅ 服務初始化成功")
            
            # 創建集合
            if not service.create_collection(384):
                print("❌ 測試失敗：無法創建集合")
                return False
            
            # 獲取統計信息
            stats = service.get_collection_stats()
            print(f"✅ 集合統計: {stats}")
            
            # 測試插入向量
            test_vectors = []
            for i in range(3):
                vector = SimpleVectorRecord(
                    document_id=f"test_doc_{i}",
                    embedding_vector=np.random.random(384).tolist()
                )
                test_vectors.append(vector)
            
            if not service.insert_vectors(test_vectors):
                print("❌ 測試失敗：向量插入失敗")
                return False
            
            # 測試搜索
            query_vector = np.random.random(384).tolist()
            search_results = service.search_similar_vectors(query_vector, top_k=5)
            print(f"✅ 搜索結果數量: {len(search_results)}")
            
            # 更新統計信息
            stats = service.get_collection_stats()
            print(f"✅ 更新後的集合統計: {stats}")
            
            # 測試刪除
            if service.delete_by_document_id("test_doc_0"):
                print("✅ 刪除測試成功")
            
            # 關閉連接
            service.close_connection()
            
            print("\n🎉 所有測試通過！ChromaDB 向量資料庫服務運行正常")
            return True
            
        except Exception as e:
            print(f"❌ 測試失敗: {e}")
            import traceback
            traceback.print_exc()
            return False
            
        finally:
            # 清理測試目錄
            try:
                shutil.rmtree(test_dir)
                print(f"🧹 測試目錄已清理: {test_dir}")
            except:
                pass

    if __name__ == "__main__":
        test_chromadb_service()

except ImportError as e:
    print(f"❌ ChromaDB 未安裝或導入失敗: {e}")
    print("請安裝 ChromaDB：pip install chromadb") 