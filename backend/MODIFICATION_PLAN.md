# Sortify 後端系統優化計畫書

## 1. 總體分析

經詳細分析，您目前的後端系統 (`EnhancedAIQAService`) 已經是一個非常先進的 RAG (檢索增強生成) 應用，其核心邏輯與您提出的優化方向高度契合，甚至在某些方面（如 AI 驅動的資料庫查詢）採取了更前沿的設計。

**現有架構亮點：**

*   **智能觸發 (Smart Trigger):** 已有名為 `_perform_probe_search` 的探針搜索，對文檔摘要進行初步判斷，符合您「專家優先」的策略。
*   **查詢重寫:** 已有 `_rewrite_query_unified` 函式，用於在初步搜索信心不足時優化用戶問題。
*   **混合檢索:** 已有 `_semantic_search_with_hybrid_retrieval` 概念，能夠結合多種方式進行搜索。
*   **AI 驅動的上下文精煉:** 已有 `_select_documents_for_detailed_query` 和 `_batch_detailed_query` 兩個階段，實現了「AI篩選文檔」和「AI生成MongoDB查詢」來提取精準上下文。

**優化核心目標：**

本次修改計畫的核心目標不是推翻重寫，而是一次**「演進式重構」**。我們將基於您現有的強大基礎，按照您提出的六點策略，對流程進行**重新組織、強化和風險控制**，使其更加穩健、高效且可控。

---

## 2. 修改計畫 (Step-by-Step)

以下是根據您提出的六點策略，制定的詳細修改步驟。我們將主要修改 `enhanced_ai_qa_service.py` 中的 `process_qa_request` 函式及其輔助函式。

### **第 1 步：確認並強化「智能觸發」**

*   **現狀:** `process_qa_request` 中已存在基於 `_perform_probe_search` 的智能觸發邏輯。
*   **修改建議:**
    1.  **保持現有邏輯:** 維持使用「探針搜索」作為第一道防線的策略。
    2.  **提升可配置性:** 將 `confidence_threshold` (目前為 `0.75`) 提取到設定檔 (`config.py`) 或作為 `AIQARequest` 的可選參數，方便未來根據實際運行效果進行動態調整。
    3.  **明確化職責:** 確保此階段的搜索目標是**快速、低成本地解決高信號問題**。可以考慮僅對文檔的 `summary` 或 `title` 欄位進行向量搜索。

### **第 2 步：優化 AI 查詢重寫為「HyDE 策略」**

*   **現狀:** `_rewrite_query_unified` 負責查詢重寫。
*   **修改建議:**
    1.  **修改重寫 Prompt:** 在 `services/prompt_manager_simplified.py` 或相關的 Prompt 管理模組中，修改查詢重寫的 Prompt，使其遵循 **HyDE (Hypothetical Document Embeddings)** 策略。
        *   **新 Prompt 示例:** `"請針對以下問題，生成一份假設性的、詳盡的、包含可能答案的文檔。不要以'這是一份假設性文檔'開頭，直接生成內容即可。問題：'{query}'"`
    2.  **調整服務邏輯:** 在 `_rewrite_query_unified` 中，調用 AI 生成上述假設性文檔。
    3.  **生成用於檢索的向量:** 對 AI 生成的**假設性文檔全文**進行 Embedding，得到一個在語義上更豐富、意圖上更精確的查詢向量。後續的檢索將使用這個新向量。
    4.  **保留原始查詢:** 原始查詢和重寫後的查詢（或其生成的假設性文檔）都應保留，以傳遞給後續步驟。

### **第 3 步：實現並應用「RRF 融合檢索」**

*   **現狀:** `_semantic_search_with_hybrid_retrieval` 提供了混合檢索的基礎。
*   **修改建議:**
    1.  **明確 RRF 實作:** 在 `enhanced_search_service.py` 或 `vector_db_service.py` 中，建立一個明確的 `reciprocal_rank_fusion` 函式。
    2.  **執行多路檢索:** 當需要執行 RRF 時，應並行執行至少兩路檢索：
        *   **一路 (廣度):** 使用第 2 步中由 HyDE 生成的向量，進行廣泛的向量搜索。
        *   **二路 (深度):** 使用傳統的稀疏檢索 (如 BM25) 或對原始查詢進行關鍵字提取後的向量搜索，以確保關鍵字匹配的精準度。
    3.  **融合與排序:** 將兩路檢索的結果（`doc_id` 列表）傳入 `reciprocal_rank_fusion` 函式，它會根據倒數排名演算法，生成一個全新的、更穩健的文檔排序列表。後續流程將使用這個 RRF 排序後的結果。

### **第 4 步：引入「AI 文本片段重排 (Re-ranking)」**

*   **現狀:** 目前的流程是「AI 選文檔 -> AI 查數據庫」，這與您的「AI 重排文本片段」策略不同。這也是本次修改的**核心**。
*   **修改建議:**
    1.  **停用或降級 Text-to-MongoDB:**
        *   **選項 A (推薦):** 暫時停用 `_batch_detailed_query` 和 `_select_documents_for_detailed_query`。將它們的程式碼保留，但標記為 `_experimental` 或 `_legacy`。
        *   **選項 B (保留):** 將其作為一個可選的、實驗性的增強功能，由 `AIQARequest` 中的一個 `bool` 參數控制，預設為 `False`。
    2.  **獲取文本片段 (Chunks):**
        *   從第 3 步 RRF 檢索出的 Top-K 文檔中，獲取它們的文本片段 (chunks)。這需要 `crud` 層提供一個函式，能夠根據 `document_ids` 高效地查詢其關聯的 `chunks`。
    3.  **實作 Re-ranker 服務:**
        *   在 `services` 目錄下新增 `reranking_service.py`。
        *   該服務的核心函式 `rerank_chunks` 會接收 `original_query` 和 `chunks_list`。
        *   它會將 `(query, chunk_text)` 對傳給一個輕量級的 AI 模型 (或專門的 Cross-Encoder 模型)，由模型為每個 chunk 的相關性打分。
    4.  **整合至主流程:** 在 `process_qa_request` 中，調用 `reranking_service.py`，用它來精煉 RRF 檢索到的文本片段，篩選出與問題最相關的 Top-N 個片段作為最終上下文。

### **第 5 步：將「AI 生成 MongoDB 查詢」轉為實驗性功能**

*   **現狀:** 此功能 (`_batch_detailed_query`) 目前是主流程的一環。
*   **修改建議:**
    1.  **明確標記為實驗性:** 如第 4 步所述，將此功能從主流程中分離。
    2.  **增加安全沙箱 (如果未來要啟用):** 如果決定在某些場景下重新啟用，必須為其設計一個嚴格的「安全沙箱」。該沙箱應：
        *   **語法校驗:** 驗證 AI 生成的查詢語法是否合法。
        *   **範圍限制:** 限制查詢只能訪問特定的欄位，禁止任何可能導致資料洩漏或效能問題的操作。
        *   **唯讀操作:** 確保生成的查詢絕對是唯讀的。

### **第 6 步：標準化最終「上下文與 Prompt」**

*   **現狀:** `_generate_answer_unified` 負責生成最終答案。
*   **修改建議:**
    1.  **調整輸入源:** 該函式的輸入，應從接收 `detailed_document_data` (來自 Text-to-Mongo 的結果) 改為接收**第 4 步中經過重排的文本片段列表** (`reranked_chunks`)。
    2.  **重構最終 Prompt:** 嚴格按照您建議的結構來組織最終發送給生成式 AI 的 Prompt。在 `prompt_manager` 中建立一個新模板：
        ```python
        FINAL_ANSWER_PROMPT = """
        用戶問題：{question}

        以下是從您的文檔庫中檢索到的、與問題最相關的文本片段：
        {formatted_chunks}
        ---
        請僅根據以上提供的文本片段，完整、準確地回答用戶的問題。
        請確保您的答案完全基於所提供的材料，並在適當時引用來源。
        """

        # formatted_chunks 的生成邏輯
        # for chunk in reranked_chunks:
        #     f" [文本片段 {i+1}]
        #       {chunk.text}
        #       (來源文件: {chunk.document_name}, 片段 ID: {chunk.id}) "
        ```
    3.  **傳遞來源資訊:** 確保每個 chunk 都帶有足夠的元數據（如 `document_id`, `document_name`），以便在生成答案時可以進行引用 (citation)。

---

## 3. 實施路線圖

1.  **第一階段 (基礎重構):**
    *   執行第 4 步中的**修改建議 1**，將 Text-to-Mongo 功能從主流程中分離。
    *   執行第 1、2、3 步，建立起「智能觸發 -> HyDE -> RRF」的檢索鏈。
    *   暫時跳過 Re-ranking，直接將 RRF 的結果（的 Chunks）送入第 6 步。
    *   完成第 6 步，確保最終答案生成流程已對接新的上下文格式。
    *   **目標:** 建立一個功能完整的、基於 RRF 的基礎 RAG 流程。

2.  **第二階段 (精煉與優化):**
    *   完成第 4 步，實作並整合 `reranking_service`，加入 AI 重排步驟。
    *   對各個環節的 Prompt、模型、參數（如 `confidence_threshold`, `top_k` 等）進行測試和調優。

3.  **第三階段 (實驗性功能探索):**
    *   在隔離的環境中，重新評估和測試第 5 步中的 Text-to-MongoDB 功能，並為其開發安全沙箱。

這個計畫旨在將您現有的先進功能，重組成一個更加模組化、穩健且符合業界最佳實踐的 RAG 流程。 