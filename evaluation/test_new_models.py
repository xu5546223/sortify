"""測試新的 Embedding 模型和 Reranker"""
import sys
import os

# 添加 backend 路徑
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

def test_embedding_model():
    """測試新的 Embedding 模型"""
    print("=" * 60)
    print("測試 Embedding 模型: intfloat/multilingual-e5-base")
    print("=" * 60)
    
    from sentence_transformers import SentenceTransformer
    import torch
    
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"使用設備: {device}")
    
    print("正在載入模型...")
    model = SentenceTransformer("intfloat/multilingual-e5-base", device=device)
    
    # 測試多語言
    test_texts = [
        "query: 這張發票的總金額是多少？",  # 中文
        "query: What is the total amount of this invoice?",  # 英文
        "query: この請求書の合計金額はいくらですか？",  # 日文
    ]
    
    print("\n測試向量化:")
    for text in test_texts:
        embedding = model.encode(text)
        print(f"  {text[:40]}... -> 維度: {len(embedding)}")
    
    # 測試相似度
    print("\n測試相似度計算:")
    query = "query: 發票金額"
    docs = [
        "passage: 本發票總金額為 NT$1,500",
        "passage: 今天天氣很好",
        "passage: 租賃契約的租金是每月 10,000 元",
    ]
    
    query_emb = model.encode(query)
    doc_embs = model.encode(docs)
    
    from sentence_transformers.util import cos_sim
    similarities = cos_sim(query_emb, doc_embs)[0]
    
    for doc, sim in zip(docs, similarities):
        print(f"  {doc[:40]}... -> 相似度: {sim:.4f}")
    
    print("\n✅ Embedding 模型測試通過！")
    return True

def test_reranker_model():
    """測試 Cross-Encoder Reranker"""
    print("\n" + "=" * 60)
    print("測試 Reranker 模型: BAAI/bge-reranker-v2-m3")
    print("=" * 60)
    
    from sentence_transformers import CrossEncoder
    import torch
    
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"使用設備: {device}")
    
    print("正在載入模型...")
    model = CrossEncoder("BAAI/bge-reranker-v2-m3", max_length=512, device=device)
    
    # 測試重排序
    query = "這張發票的總金額是多少？"
    passages = [
        "本發票總金額為 NT$1,500，付款方式為信用卡。",
        "今天天氣很好，適合出門散步。",
        "租賃契約規定每月租金為 10,000 元。",
        "發票號碼：AB-12345678，日期：2024/01/15",
    ]
    
    print(f"\n查詢: {query}")
    print("\n原始排序:")
    for i, p in enumerate(passages):
        print(f"  {i+1}. {p[:50]}...")
    
    # 計算 Cross-Encoder 分數
    pairs = [[query, p] for p in passages]
    scores = model.predict(pairs)
    
    # 按分數排序
    scored_passages = list(zip(passages, scores))
    scored_passages.sort(key=lambda x: x[1], reverse=True)
    
    print("\n重排序後:")
    for i, (p, score) in enumerate(scored_passages):
        print(f"  {i+1}. [分數: {score:.4f}] {p[:50]}...")
    
    print("\n✅ Reranker 模型測試通過！")
    return True

def test_memory_usage():
    """測試記憶體使用"""
    print("\n" + "=" * 60)
    print("記憶體使用統計")
    print("=" * 60)
    
    import psutil
    process = psutil.Process()
    memory_info = process.memory_info()
    
    print(f"  RSS (常駐記憶體): {memory_info.rss / 1024 / 1024:.1f} MB")
    print(f"  VMS (虛擬記憶體): {memory_info.vms / 1024 / 1024:.1f} MB")

if __name__ == "__main__":
    try:
        test_embedding_model()
        test_reranker_model()
        test_memory_usage()
        
        print("\n" + "=" * 60)
        print("🎉 所有測試通過！")
        print("=" * 60)
        print("\n⚠️  注意事項:")
        print("1. 由於更換了 Embedding 模型，需要重新向量化所有文檔")
        print("2. 需要清空並重建 ChromaDB 向量資料庫")
        print("3. 重啟後端服務以載入新配置")
        
    except Exception as e:
        print(f"\n❌ 測試失敗: {e}")
        import traceback
        traceback.print_exc()
