# 後端專案重構 Todo

## 已完成工作 (Done)

1.  **初步結構分析**:
    *   了解了專案的整體目錄結構 (`app`, `data`, `tests`) 及其主要模組。
    *   分析了 `main.py`，包括應用程式啟動流程、中介軟體配置 (CORS, RequestContextLogMiddleware)、全域例外處理機制以及主要 API 路由的註冊方式。
    *   梳理了 `apis/v1/` 目錄下的 API 路由組織結構，包括 `generic_v1_router` 的聚合以及各獨立功能模組 (auth, logs, system, vector_db, embedding, unified_ai 等) 的路由。

2.  **配置檢查 (`core/config.py`)**:
    *   審查了專案的環境變數和 Pydantic 配置模型。
    *   發現了 JWT `SECRET_KEY` 使用預設弱金鑰的問題。
    *   指出了 CORS `allow_origins` 配置為 `["*"]` 存在安全風險。

3.  **認證與授權檢查 (`apis/v1/auth.py`, `core/security.py`, `core/password_utils.py`)**:
    *   確認密碼儲存使用了 `passlib` 和 `bcrypt` 進行安全雜湊。
    *   分析了 JWT 的生成 (`create_access_token`) 和驗證 (`get_current_user`, `get_current_active_user`) 流程。
    *   為 `core/security.py` 中的 JWT 驗證失敗情況 (如 `JWTError`, `ValidationError`) 補充了使用 `log_event` 進行日誌記錄的邏輯，以增強問題追蹤能力。

4.  **CRUD 操作檢查 (`crud/crud_users.py`)**:
    *   評估了使用者資料庫操作，認為 NoSQL 注入的直接風險較低，因其使用了 Motor 驅動程式的標準參數化查詢方法。
    *   將使用者更新時 Email 唯一性檢查的業務邏輯從 CRUD 層 (`crud_users.py`) 移至 API 層 (`apis/v1/auth.py` 的 `update_current_user_profile` 端點)，使職責更清晰。

5.  **修復已知安全問題**:
    *   **`SECRET_KEY`**: 在 `core/config.py` 中為 `SECRET_KEY` 添加了更詳細的註釋，指導使用者如何生成並配置強金鑰。
    *   **CORS**: 在 `core/config.py` 中新增了 `ALLOWED_ORIGINS` 配置項，並在 `main.py` 中修改 `CORSMiddleware` 以使用此配置，取代了原先的 `["*"]`，提高了安全性。

6.  **文件上傳處理檢查 (`apis/v1/documents.py`)**:
    *   分析了文件上傳的完整流程，包括路徑準備 (`_prepare_upload_filepath`)、檔名清理 (`secure_filename`)、文件類型驗證 (`_validate_and_correct_file_type`) 和非同步文件儲存 (`_save_uploaded_file`)。
    *   修改了 `_prepare_upload_filepath` 函數，在儲存的檔名中加入一段 UUID，以確保即使上傳同名文件也能保證唯一性，防止意外覆蓋。

7.  **AI 服務 API 金鑰管理檢查 (`apis/v1/unified_ai.py`)**:
    *   發現 `/config/api-key` 端點允許任何已登錄使用者修改全域 `GOOGLE_API_KEY`，且修改方式非持久化，存在嚴重安全漏洞。
    *   **已移除此 `/config/api-key` 端點**。建議 `GOOGLE_API_KEY` 嚴格通過環境變數進行配置和管理。

8.  **AI 服務內部實現檢查 (部分) (`services/unified_ai_service_simplified.py`)**:
    *   確認 AI 服務在初始化時從環境變數 (`settings.GOOGLE_API_KEY`) 正確配置 Google Generative AI SDK。
    *   初步分析了其核心請求處理方法 `process_request`，包括模型選擇、提示詞獲取、以及對使用者輸入的直接拼接（存在提示注入風險）。
    *   注意到服務包含對 AI 模型輸出進行健壯解析和修復的嘗試。

9.  **提示注入防禦實施 (`services/prompt_manager_simplified.py`, `services/enhanced_ai_qa_service.py`)**:
    *   在 `services/prompt_manager_simplified.py` 中：
        *   為所有提示模板的系統提示添加了通用的安全指令。
        *   使用 XML 標籤包裹用戶輸入變數，並在系統提示中指明。
        *   新增 `_sanitize_input_value` 方法，在 `format_prompt` 中對傳入變數進行清理和長度截斷。
    *   在 `services/enhanced_ai_qa_service.py` 中：
        *   增強了 `_t2q_filter` 方法的安全性，對從查詢重寫中獲取的 `extracted_parameters` 進行嚴格驗證（白名單、防 `$` 字首、特定字段格式和內容驗證）。

10. **向量資料庫安全性與資料隔離實施 (`models/vector_models.py`, `services/semantic_summary_service.py`, `services/vector_db_service.py`, `apis/v1/vector_db.py`)**:
    *   在 `models/vector_models.py` 的 `VectorRecord` 模型中添加 `owner_id` 字段。
    *   修改 `services/semantic_summary_service.py` 的 `process_document_for_vector_db` 方法，以在創建 `VectorRecord` 時從 `document.owner_id` 填充 `owner_id`。
    *   修改 `services/vector_db_service.py`：
        *   `insert_vectors` 方法將 `owner_id` 存儲到 ChromaDB 的元數據中。
        *   `search_similar_vectors` 方法添加 `owner_id_filter` 參數，並在查詢時應用此過濾。
    *   修改 `apis/v1/vector_db.py` 的 `semantic_search` 端點，使其在調用服務時傳遞當前用戶的 `owner_id` 作為過濾條件。

## 待辦事項 (To-Do)

1.  **深入評估和緩解提示注入風險**:
    *   **檢查提示詞模板 (`services/prompt_manager_simplified.py`)**: 仔細審查預定義的系統提示詞和使用者提示詞模板，評估其設計是否能有效引導模型行為，以及是否存在易被注入的缺陷。特別關注使用者輸入是如何被嵌入模板的。 (`已完成初步檢查`)
    *   **檢查 AI 配置 (`services/unified_ai_config.py`)**: 了解模型選擇邏輯、生成參數（如 temperature, top_p, top_k）和安全設定 (`safety_settings`) 是如何配置和應用的。確認是否存在可以被外部輸入影響的配置項。 (`已完成初步檢查，safety_settings 相對安全`)
    *   **檢查 RAG 流程 (`services/enhanced_ai_qa_service.py`)**: 詳細分析在問答流程中，使用者原始問題、查詢重寫結果以及從向量資料庫檢索到的上下文是如何組合並最終傳遞給語言模型生成答案的。評估各個環節的提示注入可能性。 (`已完成初步檢查`)
    *   **提出防禦策略**: 根據上述檢查結果，為 `prompt_manager_simplified.py`, `unified_ai_service_simplified.py` 和 `enhanced_ai_qa_service.py` 提出具體的提示工程改進建議，例如：
        *   研究並應用 Google Gemini 針對提示注入的最佳實踐。 (`待辦 - 持續性任務`)

2.  **檢查向量資料庫操作的安全性 (`apis/v1/vector_db.py`, `services/vector_db_service.py`)**:
    *   **API 權限**:
        *   確保向量資料庫的相關 API 端點（如創建/刪除集合、添加/刪除向量）有適當的權限控制，例如，基於使用者角色或資源擁有權。
        *   - [ ] 將 `/vector_db/initialize` 端點的權限限制為僅管理員可訪問。
        *   批量操作 (`/batch-process`, `/documents`) 已確認對每個文檔執行所有權檢查。 (`已完成`)
    *   **查詢安全性**:
        *   雖然 ChromaDB 客戶端通常能處理參數化，但仍需確認傳遞給搜索或查詢介面的參數是否有可能被操縱以執行非預期操作或洩露資訊。 (`已通過在服務層加入 owner_id 過濾增強`)
    *   **資料隔離**:
        *   如果專案需要多租戶或不同使用者數據的隔離，檢查向量資料庫的設計是否滿足這一需求（例如，通過不同的集合名稱或元數據過濾）。 (`已通過在向量元數據中添加 owner_id 並在搜索時過濾實現`)

3.  **全面的隱性 BUG 和其他安全問題排查**:
    *   **速率限制**: 為所有 API 端點，特別是文件上傳、AI 分析和資料庫密集型操作，設計並建議實施速率限制策略 (例如，基於 IP 或使用者 ID)，以防止濫用和 DoS 攻擊。可以考慮使用如 `fastapi-limiter` 之類的工具。
    *   **輸入驗證的徹底性**: 再次審查所有接收外部輸入的 Pydantic 模型，確保驗證規則足夠嚴格和全面，覆蓋邊界情況。
    *   **依賴項安全**: 強烈建議使用 `pip-audit` 或類似工具掃描專案的依賴項 (`requirements.txt`, `uv.lock`)，以及時發現並修復已知漏洞。
    *   **日誌審查**: 檢查所有日誌記錄點，確保：
        *   關鍵操作和錯誤都被充分記錄。
        *   日誌中沒有意外洩漏敏感資訊 (如密碼、完整 API 金鑰、PII)。考慮對日誌中的敏感字段進行遮蔽。
    *   **錯誤處理一致性**: 確保整個應用程式的錯誤處理邏輯一致，對使用者返回清晰且安全的錯誤訊息，避免洩漏過多內部錯誤細節。
    *   **背景任務的健壯性 (`documents.py` 中的 `_process_document_analysis_or_extraction`)**:
        *   審查背景任務的錯誤處理、重試機制和狀態更新是否足夠健壯。
        *   對於可能長時間運行或失敗率較高的 AI 分析任務，評估當前直接使用 `BackgroundTasks` 是否足夠，或是否應遷移到更專業的任務隊列系統 (如 Celery with Redis/RabbitMQ) 以獲得更好的監控、並行控制和持久性。

4.  **效能和可維護性考量**:
    *   **啟動預熱 (`core/startup.py`)**: 深入分析 `preload_on_startup` 函數的具體操作，評估其對應用啟動時間的影響以及是否有優化空間。
    *   **資料庫查詢優化**: 檢查 `