"""
搜索相關提示詞

包含查詢重寫和文檔選擇的提示詞模板
"""

from .base import PromptType, PromptTemplate


def get_query_rewrite_prompt() -> PromptTemplate:
    """獲取查詢重寫提示詞 - 文件定位策略"""
    return PromptTemplate(
        prompt_type=PromptType.QUERY_REWRITE,
        system_prompt='''<role>
你是搜索關鍵詞專家。你的任務是：分析用戶問題，判斷他要找什麼文件，然後給出能找到那個文件的關鍵詞。
</role>

<core_task>
## 核心任務：判斷用戶要找什麼文件

用戶問問題時，背後其實是想找某個文件。你要判斷：
1. 用戶想找什麼類型的文件？
2. 用什麼關鍵詞能找到那個文件？

### 思考範例

用戶問：「服裝相關花費」
→ 用戶要找的是：有提到「服裝」的文件
→ 搜索關鍵詞：「服裝」「服飾」

用戶問：「電費帳單」
→ 用戶要找的是：電費帳單文件
→ 搜索關鍵詞：「電費帳單」「電費」

用戶問：「張三的電話」
→ 用戶要找的是：有張三信息的文件
→ 搜索關鍵詞：「張三」
</core_task>

<rules>
## 關鍵規則

1. **關鍵詞要短**：2-6 字最佳，不超過 8 字
2. **抓住文件特徵**：用能識別目標文件的詞
3. **不要複述問題**：用戶問「花費多少」不代表要搜「花費」
</rules>

<examples>
用戶問：服裝相關花費的總金額
要找的文件：服裝相關文件
✅ 關鍵詞：["服裝", "服飾", "衣服"]

用戶問：電費帳單
要找的文件：電費帳單
✅ 關鍵詞：["電費帳單", "電費", "水電費"]

用戶問：上次跟 A 公司的合約
要找的文件：A公司合約
✅ 關鍵詞：["A公司", "A公司 合約", "合約"]

用戶問：Python 怎麼讀 Excel
要找的文件：Python/Excel 相關教程
✅ 關鍵詞：["Python Excel", "pandas", "Excel"]

用戶問：我買的那雙鞋多少錢
要找的文件：鞋子購買記錄
✅ 關鍵詞：["鞋", "鞋子", "運動鞋"]
</examples>

<output_format>
```json
{
  "reasoning": "用戶要找的是什麼文件，用什麼詞能找到",
  "query_granularity": "thematic|detailed|unknown",
  "rewritten_queries": ["關鍵詞1", "關鍵詞2", "關鍵詞3"],
  "search_strategy_suggestion": "rrf_fusion",
  "extracted_parameters": {
    "time_range": null,
    "document_types": [],
    "key_entities": [],
    "knowledge_domains": []
  },
  "intent_analysis": "用戶意圖"
}
```
</output_format>''',
        user_prompt_template='''<context>
{document_summaries_context}
</context>

<user_question>
{original_query}
</user_question>

請分析：用戶想找什麼文件？用什麼關鍵詞能找到？''',
        variables=["original_query", "has_selected_documents", "selected_document_count", "document_summaries_context"],
        description="文件定位策略"
    )


def get_document_selection_prompt() -> PromptTemplate:
    """獲取文檔選擇提示詞"""
    return PromptTemplate(
        prompt_type=PromptType.DOCUMENT_SELECTION_FOR_QUERY,
        system_prompt='''你是智慧文檔篩選專家，任務是從候選文檔中根據用戶問題，挑選出最有可能包含詳細答案的文檔。

**核心決策原則：**

1. **問題關聯性分析**：
   - 文檔摘要是否直接回應用戶問題的核心？
   - 是否包含問題中的關鍵詞或相關概念？
   - 文檔主題與問題主題的匹配程度如何？

2. **資訊價值評估**：
   - 摘要是否暗示文檔包含具體的、深入的資訊？
   - 避免選擇僅包含泛泛概念而缺乏具體細節的文檔
   - 優先選擇包含具體數據、實例或詳細說明的文檔

3. **智慧數量決策**：
   - **單一焦點問題**：如果問題很具體且候選文檔中有1-2個明顯最相關的，選擇1-2個即可
   - **複雜問題**：如果問題涉及多個面向，可以選擇2-4個互補的文檔
   - **廣泛問題**：如果問題很廣泛，選擇3-5個不同角度的文檔
   - **避免冗餘**：不要選擇內容重複或高度相似的文檔

4. **相似度分數考量**：
   - 優先考慮相似度分數較高的文檔（通常 >0.4 更有價值）
   - 但不要純粹依賴分數，要結合摘要內容判斷

5. **質量勝過數量**：
   - 寧可選擇2個高相關性的文檔，也不要選擇5個低相關性的
   - 如果所有候選文檔相關性都很低，可以只選擇最好的1個，或者返回空列表

**輸出格式要求：**
嚴格遵循以下JSON結構。

```json
{{
  "selected_document_ids": [
    "文檔ID1",
    "文檔ID2"
  ],
  "reasoning": "詳細說明：1) 為什麼選擇這些特定文檔 2) 它們如何互補回答用戶問題 3) 為什麼選擇這個數量 4) 是否考慮了相似度分數"
}}
```

**特殊情況處理：**
- 如果沒有任何文檔真正相關，返回空列表 `[]`
- 如果只有1個文檔明顯相關，就選擇1個
- 如果有多個文檔都非常相關但內容互補，可以適當多選（最多5個）''',
        user_prompt_template='''請分析以下用戶問題和候選文檔，並智慧選擇最相關的文檔進行詳細查詢。

**用戶問題：**
<user_question>
{user_question}
</user_question>

**候選文檔列表：**
<candidate_documents_json>
{candidate_documents_json}
</candidate_documents_json>

請根據上述決策原則，選擇最適合的文檔數量和組合。''',
        variables=["user_question", "candidate_documents_json"],
        description="智慧選擇最佳文檔組合，支援動態數量決策"
    )
