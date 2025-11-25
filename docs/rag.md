這是一份完整的技術架構規格書（Technical Specification），專為你們團隊的 **Meta-Chunking + Gemini 2.5 + Parent-Child RAG** 系統設計。

你可以將這份文檔直接存為 `SYSTEM_ARCHITECTURE.md`，並分發給後端工程師、AI 工程師與數據庫架構師參考。

***

# 系統架構規格書：基於 Meta-Chunking 與父子索引的智能文檔處理

**版本**：1.0
**核心模型**：Google Gemini 2.5 Flash
**關鍵技術**：Meta-Chunking (邏輯分塊)、Parent-Child Indexing (父子索引)、Multimodal Analysis (多模態分析)

---

## 1. 系統概述 (Overview)

本系統旨在解決傳統 RAG 系統中「固定長度切分 (Fixed-size Chunking)」導致的語義斷裂與上下文丟失問題。透過引入 LLM 的邏輯感知能力，我們實現「按語義邊界切分」；並透過父子索引策略，確保在召回精準片段的同時，能為生成模型提供完整的上下文資訊。

### 適用場景
1.  **結構化圖片 (Type A)**：發票、收據、表格掃描件（依賴視覺排版邏輯）。
2.  **非結構化文檔 (Type B)**：Word、PDF、合約、規章（依賴語義段落邏輯）。

---

## 2. 系統處理流程 (Processing Pipeline)

資料流分為四個階段：**前處理 (Pre-processing)** $\rightarrow$ **AI 分析 (AI Analysis)** $\rightarrow$ **入庫 (Indexing)** $\rightarrow$ **召回生成 (Retrieval & Generation)**。

### 階段一：前處理與標註 (Pre-processing)

目標：為非結構化內容建立座標系統，使模型能精確參照。

#### 策略 A：圖片/發票 (Image Input)
*   **輸入**：原始圖片 (JPG/PNG)。
*   **處理**：
    1.  **OCR 預處理 (可選)**：獲取文字 Bounding Box。
    2.  **行號注入**：在圖片文字左側視覺上疊加紅色行號 `[L01]`, `[L02]`... 或在 Prompt 中指示模型將每一行視為一個 ID。
*   **優勢**：保留發票的左右欄位、表格對齊等視覺資訊。

#### 策略 B：文檔/PDF (Text Input)
*   **輸入**：PDF 或 Word 解析後的文字流。
*   **處理**：
    1.  **序列化**：按換行符分割文本。
    2.  **ID 標記**：程式自動在每行行首插入唯一 ID。
        ```text
        [L01] 員工請假規則
        [L02] 1. 病假：需附醫生證明...
        ```
*   **優勢**：低 Token 消耗，適合純文字密集型文檔。

---

### 階段二：Meta-Chunking 分析 (AI Analysis)

目標：利用 Gemini 2.5 Flash 進行邏輯判斷，而非內容重寫。

*   **模型輸入**：帶有 `[Lxx]` 標記的內容（圖片或文字）。
*   **Prompt 核心邏輯**：
    > "請參考行號，依據語義完整性與視覺排版進行分組。不要切斷列表、表格或跨行句子。回傳 JSON 格式的切分座標與摘要。"
*   **模型輸出規範 (Expected Output)**：

```json
{
  "document_summary": "文檔整體摘要，用於粗篩選",
  "logical_chunks": [
    {
      "chunk_id": 1,
      "start_id": "L01",
      "end_id": "L04",
      "type": "header",
      "summary": "發票抬頭：星巴克台北店及日期資訊",
      "reasoning": "這是發票的基礎資訊區塊"
    },
    {
      "chunk_id": 2,
      "start_id": "L05",
      "end_id": "L12",
      "type": "items_list",
      "summary": "消費明細：包含拿鐵、蛋糕等三個品項及其單價",
      "reasoning": "這是連續的商品列表，不可切斷"
    }
  ]
}
```

---

### 階段三：父子索引與入庫 (Parent-Child Indexing)

目標：解決「搜尋要精準 (小片段)」與「回答要全面 (大上下文)」的矛盾。

#### 1. 資料庫結構設計

我們需要兩個儲存層級：**Parent Storage (全量庫)** 與 **Child Storage (向量庫)**。

| 層級 | 儲存內容 | 目的 | ID 範例 |
| :--- | :--- | :--- | :--- |
| **Parent (父)** | **完整文檔內容**<br>(發票全文 或 PDF 整頁/整章) | 提供生成答案時的完整上下文 (Context) | `doc_invoice_001` |
| **Child (子)** | **邏輯切片 + 摘要**<br>(Gemini 切分出的 logical_chunks) | 用於向量搜尋 (Search) | `chunk_inv_001_a` |

#### 2. 入庫邏輯
1.  將 Gemini 切分出的每個 `logical_chunk` 提取出來。
2.  **向量化內容 (Embedding Payload)** = `chunk.summary` + `chunk.raw_text` (混合增強)。
3.  **Metadata 寫入**：在 Child 的向量資料中，必須包含 `parent_id` 欄位指向對應的 Parent。

---

### 階段四：召回與生成 (Retrieval & Generation)

#### 1. 搜尋 (Search)
用戶提問：「我上個月買蛋糕花了多少錢？」
*   系統將問題向量化，在 **Child Vector Store** 中搜尋。
*   **命中**：找到了 `chunk_inv_001_b` (摘要：消費明細包含蛋糕...)。

#### 2. 回溯 (Mapping)
*   系統讀取 `chunk_inv_001_b` 的 Metadata，獲取 `parent_id: doc_invoice_001`。
*   系統從 **Parent Storage** 中取出 `doc_invoice_001` 的 **完整全文**。
    *   *注意：若命中多個 Chunk 屬於同一個 Parent，只需提取一次 Parent，避免重複。*

#### 3. 生成 (Generate)
*   將 **完整全文 (Parent Content)** 放入 Prompt 的 Context 區塊。
*   **Prompt**: "基於以下完整發票內容，回答用戶關於蛋糕價格的問題..."
*   **結果**：模型擁有完整資訊（包含這筆交易的日期、店名、總額），能生成精確且可信的答案。

---

## 3. 針對不同文件類型的策略範例

### 範例 A：發票/收據 (Structure Data)

*   **情境**：一張包含 20 個品項的長發票。
*   **前處理**：圖片輸入，視覺感知每一行。
*   **Meta-Chunking 結果**：
    *   Chunk 1 (L01-L05): 店家資訊、統編。
    *   Chunk 2 (L06-L25): **商品列表 (Items)**。 *<-- 重點：這裡不切分，保持列表完整*
    *   Chunk 3 (L26-L30): 總計、稅額、支付方式。
*   **Parent 策略**：Parent = **整張發票全文**。
*   **理由**：發票語意緊密，單獨看「價格」沒有意義，必須搭配「店名」與「日期」。

### 範例 B：員工手冊 PDF (Semi-structured Data)

*   **情境**：一份 50 頁的 PDF，第 5 頁是「請假規定」。
*   **前處理**：文字輸入，標註行號。
*   **Meta-Chunking 結果**：
    *   Chunk 1 (L50-L55): 病假規定條款。
    *   Chunk 2 (L56-L60): 事假規定條款。
*   **Parent 策略**：Parent = **擴展窗口 (Extended Window)**。
    *   例如：命中 Chunk 1 時，Parent 不是整本 50 頁的手冊，而是 **第 5 頁整頁內容** 或 **Chunk 1 + 前後 500 字**。
*   **理由**：PDF 過長，全量召回會超出 Token 限制或引入雜訊，局部擴展上下文即可。

---

## 4. 向量化策略細節 (Embedding Strategy)

為了最大化召回率，Child Chunk 的向量化內容應包含：

1.  **語意摘要 (Generated Summary)**：
    *   由 Gemini 生成。
    *   作用：匹配用戶的「意圖查詢」（例如搜 "出差報銷流程"，摘要能比生硬的法條文字更好匹配）。
2.  **原始文本 (Raw Text)**：
    *   根據 Start/End ID 切分的原文。
    *   作用：匹配用戶的「關鍵字查詢」（例如搜具體的 "表格 3-A"）。

**Embedding Input** = `"[Summary]: " + summary_text + " [Content]: " + raw_text`

---

## 5. 預期效益 (Expected Outcomes)

1.  **解決斷章取義**：透過 Meta-Chunking，不會把「品名」跟「價格」切斷，也不會把「條款前提」跟「罰則」切斷。
2.  **提升回答準確度**：透過 Parent-Child 策略，LLM 總是在「看得到全貌」的情況下回答問題，大幅減少幻覺。
3.  **降低 Token 成本**：
    *   搜尋時只比對短的 Child Chunk (省向量庫成本)。
    *   生成時只召回必要的 Parent Document (省推理成本，避免無效的全庫檢索)。