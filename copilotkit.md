# 將 CopilotKit 導入 Sortify 專案指南

## 1. 簡介

本文件旨在引導您將 CopilotKit 整合到現有的 Sortify 專案中。CopilotKit 能夠讓您在應用程式中輕鬆建構 AI Copilots、聊天機器人和應用程式內 AI 代理，從而提升使用者體驗和專案管理效率。

我們將分別介紹後端 (Python/FastAPI) 和前端 (TypeScript/Create React App) 的整合步驟。

## 2. 先決條件

*   **Node.js 和 npm/yarn**: 用於前端開發。
*   **Python 和 pip/Poetry**: 用於後端開發。
*   **Docker**: 您的專案已包含 Dockerfile，建議使用 Docker 進行開發和部署。
*   **LLM API 金鑰 (例如 OpenAI 或 Google AI)**: 如果您的後端 Python Actions 需要直接與大型語言模型互動，則後端環境需要配置此金鑰。

## 3. 後端整合 (Python & FastAPI)

後端整合的核心是建立一個 API 端點，讓前端的 CopilotKit 元件可以呼叫 Python 中定義的 Actions。

### 步驟 3.1: 安裝後端依賴套件

在您的 `backend/` 目錄中，確保 `requirements.txt` (或 `pyproject.toml` 若使用 Poetry) 包含以下套件：

```txt
# requirements.txt
fastapi
uvicorn[standard]
copilotkit
# ... 其他現有依賴
```

然後安裝它們：

```bash
# 進入後端目錄
cd backend

# (如果使用 pip 和 requirements.txt)
# 激活您的虛擬環境 (例如 .venv/Scripts/activate)
pip install -r requirements.txt

# (如果使用 Poetry)
# poetry add fastapi uvicorn copilotkit
```
**注意:** `copilotkit` Python SDK 可能需要從特定索引安裝，請參考官方文件確認最新安裝指令。

### 步驟 3.2: 在 FastAPI 中定義 CopilotKit Actions

在您的 `backend/app/` 目錄下，例如 `copilot_setup.py` (如您專案中已設定) 或 FastAPI 主應用檔案 (例如 `main.py`) 中加入以下內容：

```python
# backend/app/copilot_setup.py (或類似檔案)

from copilotkit import CopilotKitRemoteEndpoint, Action as CopilotAction
from typing import Dict, Any # 用於類型提示
# 根據您的專案結構導入 settings
# from .core.config import settings # 範例

# --- 範例 Action: 從後端獲取專案資訊 ---
async def get_sortify_project_details(category: str) -> Dict[str, Any]:
    """
    一個範例 Action，根據分類從 Sortify 後端獲取專案細節。
    在實際應用中，這裡會包含您的業務邏輯，例如查詢資料庫或從配置讀取。
    如果此 Action 需要呼叫 LLM，則應在此處使用後端配置的 API 金鑰。
    """
    print(f"Python 後端收到對 '{category}' 的查詢")
    if category.lower() == "status":
        return {"projectName": "Sortify", "status": "進行中", "progress": "75%", "nextMilestone": "使用者身份驗證模組完成"}
    elif category.lower() == "team":
        return {"projectName": "Sortify", "teamSize": 5, "lead": "AI Assistant", "members": ["Dev A", "Dev B"]}
    elif category.lower() == "version":
        # 假設從 settings 獲取版本信息
        # app_version = getattr(settings, 'APP_VERSION', 'N/A')
        app_version = "0.1.0" # 簡化範例
        return {"projectName": "Sortify", "version": app_version}
    else:
        return {"error": f"未知的查詢分類: {category}"}

# 將函式包裝成 CopilotKit Action
sortify_project_action = CopilotAction(
    name="getSortifyProjectInfo", # Action 的唯一名稱
    description="從 Sortify 後端獲取特定分類的專案資訊 (例如 'status', 'team', 'version')。",
    parameters=[
        {
            "name": "category",
            "type": "string",
            "description": "要查詢的資訊分類 (例如 'status', 'team', 'version')",
            "required": True,
        }
    ],
    handler=get_sortify_project_details
)

# --- 設定 CopilotKit 遠端端點 ---
# 您可以將多個 Actions 加入到 actions 列表中
python_backend_sdk = CopilotKitRemoteEndpoint(actions=[sortify_project_action])

# --- 在 FastAPI 主應用中註冊 CopilotKit 端點 ---
# 在您的 backend/app/main.py 或 backend/app/apis/v1/__init__.py 中:
# from fastapi import FastAPI
# from copilotkit.integrations.fastapi import add_fastapi_endpoint
# from ...copilot_setup import python_backend_sdk # 調整導入路徑
# app = FastAPI() # 或您的 APIRouter 實例

# # 假設您的 FastAPI app 實例是 `app` 或 router 實例是 `api_v1_router`
# # 路徑將是相對於您註冊此 router 的前綴
# # 例如，如果 api_v1_router 在 main.py 中以 prefix="/api/v1" 註冊，
# # 則完整路徑為 /api/v1/copilotkit_actions
# if python_backend_sdk:
#   add_fastapi_endpoint(api_v1_router, python_backend_sdk, "/copilotkit_actions")
#   print("Sortify Python 後端已設定 CopilotKit 端點於 /copilotkit_actions (相對於 API v1)")
```
**重點**: 確保您的 FastAPI 應用 (`main.py`) 正確導入 `python_backend_sdk` 並使用 `add_fastapi_endpoint` 將其註冊到一個可訪問的路由 (例如，在您的專案中是 `/api/v1/copilotkit_actions`)。

### 步驟 3.3: 後端 API 金鑰配置

如果您的 Python Actions (例如上述 `get_sortify_project_details` 或未來更複雜的 Actions) 需要直接呼叫大型語言模型 (LLM)，則相關的 API 金鑰 (如 `GOOGLE_API_KEY` 或 `OPENAI_API_KEY`) **必須在後端環境中配置**。

*   通常透過環境變數 (例如在 `.env` 檔案中設定，由 `python-dotenv` 載入) 來管理。
*   您的專案 `backend/core/config.py` 和 `backend/services/unified_ai_config.py` 已包含處理這些金鑰的邏輯。
*   **前端不需要處理或儲存這些 LLM API 金鑰。**

### 步驟 3.4: 更新後端 Dockerfile

確保您的 `backend/Dockerfile` 能正確安裝依賴、複製 `.env` 檔案 (如果包含 API 金鑰等敏感配置) 並運行 FastAPI 應用程式。

```Dockerfile
# backend/Dockerfile (部分範例)
# ... (其他 Dockerfile 內容) ...

# 複製 requirements.txt 並安裝依賴
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製應用程式碼
COPY ./app /app/app
# 如果 .env 檔案包含運行時需要的配置 (如 API 金鑰)
COPY .env /app/.env 

WORKDIR /app

# 暴露連接埠 (與 uvicorn 命令中的 port 一致)
EXPOSE 8000

# 運行 FastAPI 應用
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
# 確保 "app.main:app" 指向您的 FastAPI app 實例
```

## 4. 前端整合 (TypeScript & Create React App)

前端整合涉及安裝 CopilotKit React 套件，並使用 `CopilotKit` Provider 包裹您的應用，使其指向後端 FastAPI 設定的 CopilotKit 端點。

### 步驟 4.1: 安裝前端依賴套件

在您的 `frontend/` 目錄中，執行：

```bash
cd frontend
npm install @copilotkit/react-core @copilotkit/react-ui
# 或
# yarn add @copilotkit/react-core @copilotkit/react-ui
```
**注意**: `openai` 套件在這種架構下前端不是必需的，因為 LLM 互動由後端處理。

### 步驟 4.2: 用 `CopilotKit` Provider 包裹您的應用

在您的前端應用程式入口檔案，例如 `frontend/src/index.tsx`：

```typescript
// frontend/src/index.tsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import { CopilotKit } from '@copilotkit/react-core';
import './styles/main.css'; // 您的全域樣式

const root = ReactDOM.createRoot(
  document.getElementById('root') as HTMLElement
);

// runtimeUrl 應指向您在後端 FastAPI 設定的 CopilotKit 端點的完整 URL
// 例如: http://localhost:8000/api/v1/copilotkit_actions (本地開發時)
// 或在 Docker 環境中指向後端服務的 URL
const copilotRuntimeUrl = process.env.REACT_APP_COPILOT_RUNTIME_URL || "http://localhost:8000/api/v1/copilotkit_actions";

root.render(
  <React.StrictMode> {/* 或移除 StrictMode，視您的專案需求 */}
    <CopilotKit runtimeUrl={copilotRuntimeUrl}>
      <App />
    </CopilotKit>
  </React.StrictMode>
);
```
**環境變數 (可選但建議)**:
您可以在 `frontend/.env` 檔案中設定 `REACT_APP_COPILOT_RUNTIME_URL` 以方便管理不同環境的 URL。
例如 `frontend/.env`:
`REACT_APP_COPILOT_RUNTIME_URL=http://localhost:8000/api/v1/copilotkit_actions`

### 步驟 4.3: 在前端使用 CopilotKit UI 元件

現在您可以在任何頁面或元件中使用 CopilotKit 的 UI 元件，例如 `CopilotPopup`。

```tsx
// frontend/src/App.tsx (或任何您想放置聊天彈窗的元件)
import React from 'react';
// ... 其他導入 ...
import { CopilotPopup } from "@copilotkit/react-ui";
import "@copilotkit/react-ui/styles.css"; // 導入 UI 樣式

function App() {
  // ... 您的 App 邏輯 ...

  return (
    // 您的應用程式結構
    <>
      {/* ... 您的路由和頁面 ... */}
      
      <CopilotPopup
        instructions={
          "你是 Sortify 專案的 AI 助理。你可以使用 'getSortifyProjectInfo' action 並提供分類 (如 'status', 'team', 'version') 來查詢專案資訊。"
        }
        defaultOpen={false} // 是否預設開啟
        labels={{
          title: "Sortify AI 助理",
          initial: "嗨！我可以怎麼協助您管理 Sortify 專案？",
        }}
        // 您可以進一步自訂外觀和行為
      />
    </>
  );
}

export default App;
```
**注意**: `CopilotPopup` 的 `instructions` 應指導 AI 如何使用您在後端定義的 Actions。

### 步驟 4.4: 更新前端 Dockerfile

確保您的 `frontend/Dockerfile` 正確建置 Create React App 應用。如果您使用環境變數來設定 `runtimeUrl`，確保這些變數在建置或運行時可用。

```Dockerfile
# frontend/Dockerfile (部分範例)

# 建置階段
FROM node:18-alpine AS builder
WORKDIR /app
COPY package.json yarn.lock ./ 
# 或 copy package.json package-lock.json ./
RUN yarn install --frozen-lockfile 
# 或 npm ci
COPY . .
# 如果您有 .env 檔案且需要在建置時讀取 REACT_APP_ 變數
# COPY .env .env 
RUN npm run build

# 運行階段
FROM node:18-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production

# 如果您在 .env 中有 REACT_APP_ 變數並且它們需要在運行時被 serve 靜態檔案的伺服器使用
# (通常 CRA 建置時會將 REACT_APP_ 變數嵌入到靜態檔案中，除非您有特殊設定)
# COPY .env .env 

COPY --from=builder /app/build ./build

# 簡單的 serve 或 nginx 等用於提供靜態檔案
# RUN npm install -g serve
# EXPOSE 3000
# CMD ["serve", "-s", "build", "-l", "3000"]

# 或者使用 Nginx
# COPY nginx.conf /etc/nginx/nginx.conf
EXPOSE 3000
# CMD ["nginx", "-g", "daemon off;"] 
# (您需要提供一個 nginx.conf)

# 簡化範例：使用 Node.js 來 serve (不建議用於生產)
RUN npm install express
COPY <<EOF server.js
const express = require('express');
const path = require('path');
const app = express();
const port = process.env.PORT || 3000;
app.use(express.static(path.join(__dirname, 'build')));
app.get('/*', function (req, res) {
  res.sendFile(path.join(__dirname, 'build', 'index.html'));
});
app.listen(port, () => console.log(\`App listening on port \${port}\`));
EOF
CMD ["node", "server.js"]
```

## 5. 運行整合後的應用程式

### 5.1 使用 Docker Compose (推薦)

如果您的專案 (`sortify/docker-compose.yml`) 設定了前後端服務，請確保：

1.  **後端服務 (`backend`)**:
    *   正確建置 Docker 映像。
    *   將容器的 8000 連接埠映射到主機。
    *   確保後端環境變數 (例如 `.env` 中的 `GOOGLE_API_KEY`) 在容器中可用。
2.  **前端服務 (`frontend`)**:
    *   正確建置 Docker 映像。
    *   將容器的 3000 連接埠映射到主機。
    *   透過 Docker Compose 的 `environment` 設定將 `REACT_APP_COPILOT_RUNTIME_URL` (設定為 `http://backend:8000/api/v1/copilotkit_actions`，其中 `backend` 是您在 `docker-compose.yml` 中定義的後端服務名稱) 傳遞給前端容器。

**`docker-compose.yml` 範例片段:**

```yaml
version: '3.8'
services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    volumes:
      - ./backend:/app # 開發時掛載程式碼
    env_file:
      - ./backend/.env # 確保後端可以讀取其 .env 檔案
    # 如果後端 .env 由 Docker Compose 的 .env 檔案提供，則使用 environment:
    # environment:
    #   - GOOGLE_API_KEY=${GOOGLE_API_KEY} # 從主機 .env 讀取

  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    depends_on:
      - backend
    environment:
      # 將後端 CopilotKit 端點的 URL 傳遞給前端
      - REACT_APP_COPILOT_RUNTIME_URL=http://backend:8000/api/v1/copilotkit_actions
    volumes:
      - ./frontend:/app
      - /app/node_modules
```
在 `sortify/` 根目錄下建立一個 `.env` 檔案，用於存放共享的環境變數，例如 `GOOGLE_API_KEY` (如果後端服務的 `env_file` 指向它，或者您在 backend service 中使用 `environment` 來傳遞它)。

然後運行：
`docker-compose up --build`

### 5.2 分別運行 (開發時)

1.  **啟動 Python 後端**:
    ```bash
    cd backend
    # source .venv/Scripts/activate (或您的虛擬環境啟動指令)
    # 確保後端 .env 檔案已配置 (例如 GOOGLE_API_KEY)
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    ```
2.  **啟動 Create React App 前端**:
    ```bash
    cd frontend
    # 確保 frontend/.env 已配置 REACT_APP_COPILOT_RUNTIME_URL=http://localhost:8000/api/v1/copilotkit_actions
    npm start # 或 yarn start
    ```

## 6. 關鍵考量與最佳實踐

*   **Action 設計**: 保持 Action 的功能單一且明確。良好的描述和參數定義有助於 AI 更準確地使用它們。
*   **API 金鑰管理**: LLM API 金鑰應始終在後端安全管理，不要洩漏到前端。
*   **錯誤處理**: 在 Python Action 處理函式中實施健壯的錯誤處理。
*   **`useCopilotReadable`**: 在前端使用此 Hook 可以讓 AI 理解應用程式的當前狀態，提供更具上下文的協助 (需要前端有 CopilotKit Runtime 或與後端 Action 協同工作)。
*   **日誌**: 在後端 FastAPI 中加入詳細的日誌，方便偵錯。
*   **URL 配置**: 特別注意 `runtimeUrl` (前端) 和 FastAPI 端點路徑 (後端) 在不同環境 (本地開發 vs Docker Compose) 中的正確性。

## 7. 測試

1.  打開您的前端應用 (例如 `http://localhost:3000`)。
2.  打開 CopilotPopup 聊天視窗。
3.  嘗試用自然語言觸發您在 Python 後端定義的 Action，例如：
    *   "使用 getSortifyProjectInfo 查詢 status"
    *   "Sortify 專案的團隊資訊是什麼？" (AI 應能理解並呼叫 `getSortifyProjectInfo` 並傳入 `team` 作為 category)

## 8. 疑難排解

*   **檢查瀏覽器開發者控制台**: 查看前端是否有網路錯誤或 console 錯誤。
*   **檢查 FastAPI 後端的終端輸出**: 查看是否有請求到達以及是否有錯誤，特別是關於 Action 執行和 API 金鑰使用的日誌。
*   **網路問題**:
    *   確保前端可以訪問後端設定的 `runtimeUrl`。
    *   在 Docker 環境中，確保服務名稱解析正確，且連接埠已正確映射和暴露。
*   **Action 名稱/參數匹配**: 確保 AI 嘗試呼叫的 Action 名稱及參數與您在 Python 中定義的一致。

希望這份文件能幫助您順利將 CopilotKit 整合到 Sortify 專案中！