[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/xu5546223/sortify)

# Sortify AI Assistant / Sortify AI 智能助手

[English](#english-version) | [中文](#chinese-version)

---

<a id="chinese-version"></a>

## 📖 項目概述

Sortify AI Assistant 是一個功能強大的智能文件分析和問答系統，基於先進的向量資料庫和大型語言模型技術。系統能夠自動提取、分析文檔內容，並提供基於文件內容的智能問答服務，為使用者提供高效且精確的文檔理解和交互體驗。

## ✨ 主要功能

### 📄 文件管理
- **多格式支援**：PDF、Word、Excel、圖片、Markdown 等多種格式
- **智能分類**：AI 自動分析文件內容並動態生成分類（可重置重新分類）
- **批量操作**：支援批量上傳、刪除、向量化
- **Gmail 導入**：直接從 Gmail 導入郵件作為文檔

### 🤖 AI 智能分析
- **自動文本提取**：從各種格式文件中提取文本內容
- **結構化分析**：提取關鍵信息（金額、日期、人名、地點等）
- **動態欄位識別**：AI 自動識別文檔特有的欄位
- **智能摘要**：生成準確的文檔摘要和關鍵詞

### 💬 智能問答系統
- **意圖分類**：自動識別問題類型（寒暄、搜索、詳細查詢、複雜分析等）
- **對話記憶**：支援多輪對話，記住上下文和已查詢的文檔
- **MongoDB 詳細查詢**：針對已知文檔執行精確數據提取
- **智能文檔識別**：
  - 支援編號引用（"文檔五"、"第3個文檔"）
  - 支援內容匹配（"南投的罰單"、"2024年的發票"）
  - 支援對話引用（"那張發票"、"這個合約"）
- **工作流批准**：需要搜索或詳細查詢時請求用戶批准

### 🔍 向量搜索
- **混合檢索**：結合摘要向量和文本塊向量的 RRF 融合搜索
- **智能觸發**：根據相似度自動決定是否需要查詢重寫
- **查詢優化**：AI 自動重寫查詢以提高檢索準確度
- **語義理解**：支援自然語言查詢和概念匹配

### 📊 數據可視化
- **儀表板**：系統狀態、文檔統計、活動記錄
- **問答分析**：查看 AI 處理過程、向量搜索結果、上下文數據
- **聚類統計**：分類分布、文檔數量、覆蓋率

### 🔐 安全與權限
- **用戶認證**：JWT Token 認證
- **文檔隔離**：每個用戶只能訪問自己的文檔
- **安全日誌**：記錄所有操作和錯誤

## 🏗️ 系統架構

**技術棧:**

| 組件     | 技術                                           | 描述                       |
| -------- | ---------------------------------------------- | -------------------------- |
| 前端     | React.js + TypeScript + Ant Design + TailwindCSS | 現代化響應式用戶界面       |
| 後端     | FastAPI + UV (Python)                          | 高性能異步 API 服務        |
| 資料庫   | MongoDB + ChromaDB                             | 文檔存儲 + 向量搜索        |
| AI 服務  | Google Gemini / OpenAI API                     | 大型語言模型集成           |

以下是我們系統的架構圖：

![系統架構圖](images/SystemArchitecture.jpg)

## 🎯 智能問答系統亮點

### 智能意圖識別
系統能自動識別7種問題類型，並採用最優策略處理：

1. **寒暄問候** → 直接友好回答
2. **需要澄清** → 生成澄清問題，提供選項
3. **簡單事實** → 從對話歷史或通用知識快速回答
4. **文檔搜索** → 向量搜索相關文檔
5. **文檔詳細查詢** ⭐ → 對已知文檔執行 MongoDB 精確查詢
6. **複雜分析** → 完整 RAG 流程，多文檔整合分析

### 智能文檔識別示例

**支援多種引用方式：**
```
用戶: "文檔五的詳細內容"
→ AI 識別：reference_number=5，查詢文檔5

用戶: "南投的罰單詳細資訊"  
→ AI 識別：從摘要匹配"南投"關鍵詞，查詢對應文檔

用戶: "那張發票花了多少錢"
→ AI 識別：從對話歷史找到提到的發票文檔
```

### 工作流批准機制
需要執行耗時操作時，系統會先請求批准：
- 📝 顯示將要查詢的文檔
- ⏱️ 預估處理時間
- ✅ 用戶可選擇批准或跳過

## 🚀 快速開始

### 📋 環境要求

- Node.js 18+
- Python 3.11+
- MongoDB
- **UV** (推薦) - 極速 Python 包管理器
- **NVIDIA GPU** (可選) - 用於 PyTorch GPU 加速

### 💻 本地開發

**前端開發:**
```bash
# 進入前端目錄
cd frontend

# 安裝依賴
npm install

# 啟動開發伺服器
npm start
```

**後端開發 (使用 UV - 推薦):**
```bash
# 進入後端目錄
cd backend

# 安裝 UV (如果尚未安裝)
# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
# 或使用 pip
pip install uv

# 使用 UV 同步依賴 (自動創建虛擬環境並安裝所有依賴)
uv sync

# 複製環境變數範本
cp example.env .env
# 編輯 .env 檔案，填入您的配置

# 啟動開發伺服器 (使用 UV)
uv run uvicorn app.main:app --reload

# 或直接使用虛擬環境
.venv\\Scripts\\uvicorn.exe app.main:app --reload
```

**後端開發 (傳統方式):**
```bash
# 進入後端目錄
cd backend

# 創建虛擬環境
python -m venv .venv

# 啟動虛擬環境
# Windows
.venv\\Scripts\\activate
# Linux/Mac
source .venv/bin/activate

# 安裝依賴
pip install -r requirements.txt

# ⚠️ 重要：手動安裝 PyTorch GPU 版本
pip uninstall -y torch torchvision torchaudio
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124

# 複製環境變數範本
cp example.env .env
# 編輯 .env 檔案，填入您的配置

# 啟動開發伺服器
uvicorn app.main:app --reload
```

## 📁 項目結構

```
sortify/
├── frontend/                 # 前端項目
│   ├── public/              # 靜態資源
│   ├── src/                 # 源代碼
│   │   ├── components/      # UI 組件
│   │   ├── pages/           # 頁面組件
│   │   │   ├── auth/        # 認證頁面
│   │   │   ├── DashboardPage.tsx    # 儀表板
│   │   │   ├── DocumentsPage.tsx    # 文件管理
│   │   │   ├── AIQAPage.tsx         # AI問答
│   │   │   └── VectorDatabasePage.tsx # 向量數據庫管理
│   │   ├── services/        # API 服務
│   │   └── contexts/        # React 上下文
│   ├── package.json         # 依賴配置
├── backend/                 # 後端項目
│   ├── app/                 # 應用程式
│   │   ├── apis/           # API 路由
│   │   │   └── v1/         # V1 API 版本
│   │   ├── core/           # 核心功能
│   │   ├── models/         # 資料模型
│   │   ├── services/       # 業務邏輯
│   │   └── main.py         # 應用入口
│   ├── tests/              # 測試文件
│   └── pyproject.toml      # Python 項目配置
```

## 🔧 配置說明

### 包管理器 - UV

本項目使用 **UV** 作為 Python 包管理器，相比傳統 pip：
- ⚡ **速度提升 10-100 倍**
- 🔒 **自動鎖定依賴版本** (uv.lock)
- 🎯 **自動管理虛擬環境**
- 🚀 **統一的工具鏈** (替代 pip, poetry, pyenv)

**常用命令:**
```bash
# 同步依賴
uv sync

# 添加新包
uv add package-name

# 移除包
uv remove package-name

# 運行命令
uv run python script.py
uv run pytest tests/ -v
```

### GPU 加速配置

本項目默認使用 **PyTorch GPU 版本 (CUDA 12.4)**：
- ✅ 自動從 PyTorch GPU 索引安裝
- ✅ 支援 CUDA 12.x
- ✅ Embedding 生成速度提升 **5-10 倍**
- ✅ 向量搜索速度提升 **3-5 倍**

**驗證 GPU 可用:**
```bash
uv run python -c "import torch; print('GPU:', torch.cuda.is_available())"
```

**預期輸出:** `GPU: True`

### 環境變數

**後端配置:**
- `MONGODB_URL`: MongoDB 連接字串
- `DB_NAME`: 資料庫名稱
- `OPENAI_API_KEY`: OpenAI API 密鑰 (可選)
- `GEMINI_API_KEY`: Google Gemini API 密鑰

## 📊 API 文檔

系統啟動後，您可以通過以下地址訪問 API 文檔：
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

**主要 API 端點:**
- `/api/v1/auth/` - 用戶認證（登入、註冊、Token 刷新）
- `/api/v1/documents/` - 文檔管理（上傳、刪除、更新、查詢）
- `/api/v1/dashboard/` - 儀表板數據（統計、活動記錄）
- `/api/v1/logs/` - 系統日誌查詢
- `/api/v1/vector-db/` - 向量資料庫操作（向量化、搜索、統計）
- `/api/v1/unified-ai/` - 統一 AI 服務（問答、分析、查詢重寫）
- `/api/v1/embedding/` - 嵌入模型服務（模型管理、設備配置）
- `/api/v1/clustering/` - 智能分類（觸發聚類、查詢分類、刪除分類）
- `/api/v1/conversations/` - 對話管理（創建、查詢、刪除對話）
- `/api/v1/settings/` - 系統設定（AI 模型配置、參數調整）

## 🧪 測試

**後端測試 (使用 UV):**
```bash
cd backend
uv run pytest tests/ -v
```

**後端測試 (傳統方式):**
```bash
cd backend
.venv\\Scripts\\activate
pytest tests/ -v
```

**資料庫連接測試:**
訪問 `http://localhost:8000/test-db-connection` 來測試 MongoDB 連接狀態。

## 🤝 貢獻指南

歡迎提交 Pull Request 和 Issue！請確保您的代碼符合項目的編碼標準。

## 📄 授權協議

本項目採用 MIT 授權協議。詳見 LICENSE 文件。

## 📞 聯繫方式

如有問題或建議，請通過 GitHub Issues 聯繫我們。

---

<a id="english-version"></a>

## 📖 Project Overview

Sortify AI Assistant is a powerful intelligent document analysis and Q&A system based on advanced vector database and large language model technologies. The system can automatically extract and analyze document content, providing intelligent Q&A services based on file content, offering users efficient and accurate document understanding and interaction experiences.

## ✨ Key Features

### 📄 Document Management
- **Multi-format Support**: PDF, Word, Excel, Images, Markdown, and more
- **Intelligent Clustering**: AI automatically analyzes and dynamically generates document categories (can reset and recluster)
- **Batch Operations**: Support for batch upload, delete, and vectorization
- **Gmail Import**: Direct import of emails from Gmail as documents

### 🤖 AI Intelligent Analysis
- **Automatic Text Extraction**: Extract text content from various file formats
- **Structured Analysis**: Extract key information (amounts, dates, names, locations, etc.)
- **Dynamic Field Recognition**: AI automatically identifies document-specific fields
- **Smart Summarization**: Generate accurate document summaries and keywords

### 💬 Intelligent Q&A System
- **Intent Classification**: Automatically identify question types (greeting, search, detail query, complex analysis, etc.)
- **Conversation Memory**: Support multi-turn dialogue, remember context and queried documents
- **MongoDB Detail Query**: Execute precise data extraction for known documents
- **Smart Document Identification**:
  - Number references ("document five", "3rd document")
  - Content matching ("Nantou ticket", "2024 invoice")
  - Conversation references ("that invoice", "this contract")
- **Workflow Approval**: Request user approval when search or detail query is needed

### 🔍 Vector Search
- **Hybrid Retrieval**: RRF fusion search combining summary and chunk vectors
- **Smart Triggering**: Automatically decide if query rewrite is needed based on similarity scores
- **Query Optimization**: AI automatically rewrites queries to improve retrieval accuracy
- **Semantic Understanding**: Support natural language queries and concept matching

### 📊 Data Visualization
- **Dashboard**: System status, document statistics, activity logs
- **Q&A Analytics**: View AI processing steps, vector search results, context data
- **Clustering Statistics**: Category distribution, document counts, coverage rates

### 🔐 Security & Permissions
- **User Authentication**: JWT Token authentication
- **Document Isolation**: Users can only access their own documents
- **Security Logging**: Record all operations and errors

## 🏗️ System Architecture

**Tech Stack:**

| Component  | Technology                                     | Description                        |
| ---------- | ---------------------------------------------- | ---------------------------------- |
| Frontend   | React.js + TypeScript + Ant Design + TailwindCSS | Modern responsive UI               |
| Backend    | FastAPI + UV (Python)                          | High-performance async API service |
| Database   | MongoDB + ChromaDB                             | Document storage + Vector search   |
| AI Service | Google Gemini / OpenAI API                     | LLM integration                    |

"Here is our system's architecture diagram:"

![System Architecture Diagram](images/SystemArchitecture.jpg)

## 🎯 Intelligent Q&A System Highlights

### Smart Intent Recognition
The system automatically identifies 7 question types and applies optimal strategies:

1. **Greeting** → Direct friendly response
2. **Clarification Needed** → Generate clarification questions with options
3. **Simple Factual** → Quick answer from conversation history or general knowledge
4. **Document Search** → Vector search for relevant documents
5. **Document Detail Query** ⭐ → Execute precise MongoDB query on known documents
6. **Complex Analysis** → Full RAG process with multi-document integration

### Smart Document Identification Examples

**Supports multiple reference methods:**
```
User: "Detail content of document five"
→ AI identifies: reference_number=5, queries document 5

User: "Detailed info about Nantou traffic ticket"  
→ AI identifies: Matches "Nantou" keyword from summary, queries corresponding document

User: "How much did that invoice cost"
→ AI identifies: Finds invoice document mentioned in conversation history
```

### Workflow Approval Mechanism
When time-consuming operations are needed, the system requests approval:
- 📝 Shows documents to be queried
- ⏱️ Estimates processing time
- ✅ Users can approve or skip

## 🚀 Quick Start

### 📋 Prerequisites

- Node.js 18+
- Python 3.11+
- MongoDB
- **UV** (Recommended) - Ultra-fast Python package manager
- **NVIDIA GPU** (Optional) - For PyTorch GPU acceleration

### 💻 Local Development

**Frontend Development:**
```bash
# Enter frontend directory
cd frontend

# Install dependencies
npm install

# Start development server
npm start
```

**Backend Development (Using UV - Recommended):**
```bash
# Enter backend directory
cd backend

# Install UV (if not already installed)
# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
# Or using pip
pip install uv

# Sync dependencies using UV (auto-creates venv and installs all deps)
uv sync

# Copy environment variable template
cp example.env .env
# Edit .env file and fill in your configuration

# Start development server (using UV)
uv run uvicorn app.main:app --reload

# Or use virtual environment directly
.venv\\Scripts\\uvicorn.exe app.main:app --reload
```

**Backend Development (Traditional Way):**
```bash
# Enter backend directory
cd backend

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows
.venv\\Scripts\\activate
# Linux/Mac
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# ⚠️ Important: Manually install PyTorch GPU version
pip uninstall -y torch torchvision torchaudio
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124

# Copy environment variable template
cp example.env .env
# Edit .env file and fill in your configuration

# Start development server
uvicorn app.main:app --reload
```

## 📁 Project Structure

```
sortify/
├── frontend/                 # Frontend project
│   ├── public/              # Static assets
│   ├── src/                 # Source code
│   │   ├── components/      # UI components
│   │   ├── pages/           # Page components
│   │   │   ├── auth/        # Authentication pages
│   │   │   ├── DashboardPage.tsx    # Dashboard
│   │   │   ├── DocumentsPage.tsx    # Document management
│   │   │   ├── AIQAPage.tsx         # AI Q&A
│   │   │   └── VectorDatabasePage.tsx # Vector DB management
│   │   ├── services/        # API services
│   │   └── contexts/        # React contexts
│   ├── package.json         # Dependencies
├── backend/                 # Backend project
│   ├── app/                 # Application
│   │   ├── apis/           # API routes
│   │   │   └── v1/         # V1 API version
│   │   ├── core/           # Core functionality
│   │   ├── models/         # Data models
│   │   ├── services/       # Business logic
│   │   └── main.py         # Application entry point
│   ├── tests/              # Test files
│   └── pyproject.toml      # Python project config
```

## 🔧 Configuration

### Package Manager - UV

This project uses **UV** as the Python package manager, compared to traditional pip:
- ⚡ **10-100x faster**
- 🔒 **Automatic dependency locking** (uv.lock)
- 🎯 **Auto-managed virtual environments**
- 🚀 **Unified toolchain** (replaces pip, poetry, pyenv)

**Common Commands:**
```bash
# Sync dependencies
uv sync

# Add new package
uv add package-name

# Remove package
uv remove package-name

# Run commands
uv run python script.py
uv run pytest tests/ -v
```

### GPU Acceleration

This project uses **PyTorch GPU version (CUDA 12.4)** by default:
- ✅ Auto-installs from PyTorch GPU index
- ✅ Supports CUDA 12.x
- ✅ Embedding generation **5-10x faster**
- ✅ Vector search **3-5x faster**

**Verify GPU availability:**
```bash
uv run python -c "import torch; print('GPU:', torch.cuda.is_available())"
```

**Expected output:** `GPU: True`

### Environment Variables

**Backend Configuration:**
- `MONGODB_URL`: MongoDB connection string
- `DB_NAME`: Database name
- `OPENAI_API_KEY`: OpenAI API key (optional)
- `GEMINI_API_KEY`: Google Gemini API key

## 📊 API Documentation

After starting the system, you can access the API documentation at:
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

**Main API Endpoints:**
- `/api/v1/auth/` - User authentication (login, register, token refresh)
- `/api/v1/documents/` - Document management (upload, delete, update, query)
- `/api/v1/dashboard/` - Dashboard data (statistics, activity logs)
- `/api/v1/logs/` - System log queries
- `/api/v1/vector-db/` - Vector database operations (vectorization, search, statistics)
- `/api/v1/unified-ai/` - Unified AI services (Q&A, analysis, query rewriting)
- `/api/v1/embedding/` - Embedding model services (model management, device configuration)
- `/api/v1/clustering/` - Intelligent clustering (trigger clustering, query clusters, delete clusters)
- `/api/v1/conversations/` - Conversation management (create, query, delete conversations)
- `/api/v1/settings/` - System settings (AI model configuration, parameter tuning)

## 🧪 Testing

**Backend Testing (Using UV):**
```bash
cd backend
uv run pytest tests/ -v
```

**Backend Testing (Traditional):**
```bash
cd backend
.venv\\Scripts\\activate
pytest tests/ -v
```

**Database Connection Test:**
Visit `http://localhost:8000/test-db-connection` to test MongoDB connection status.

## 🤝 Contributing

Welcome to submit Pull Requests and Issues! Please ensure your code follows the project\'s coding standards.

## 📄 License

This project is licensed under the MIT License. See the LICENSE file for details.

## 📞 Contact

For questions or suggestions, please contact us through GitHub Issues.

---
