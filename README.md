# Sortify AI Assistant

智能文件分析和問答系統，基於先進的向量資料庫和大型語言模型技術。

## 專案概述

Sortify AI Assistant 是一個功能強大的文件處理平台，能夠自動提取、分析文檔內容，並提供基於檔案內容的智能問答服務。系統採用最新的向量資料庫技術和大型語言模型，為使用者提供高效且精確的文檔理解和交互體驗。

### 主要功能

- **文件上傳與處理**：支援 PDF、Word、圖片等多種格式文件上傳和文字提取
- **AI 智能分析**：自動分析文件內容，生成摘要、關鍵詞和分類
- **語義搜索**：基於向量資料庫的高效語義搜索，快速找到相關文件
- **智能問答**：針對文件內容的 AI 輔助問答系統
- **多設備同步**：透過手機和電腦同步存取和管理文件

## 系統架構

- **前端**：React.js + TailwindCSS
- **後端**：FastAPI (Python)
- **資料庫**：MongoDB + ChromaDB (向量資料庫)
- **AI 服務**：Google Gemini / OpenAI API

## 快速開始

### 前端開發

```bash
# 進入前端目錄
cd frontend

# 安裝依賴
npm install

# 啟動開發伺服器
npm start
```

### 後端開發

```bash
# 進入後端目錄
cd backend

# 創建虛擬環境
python -m venv .venv

# 啟動虛擬環境
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate

# 安裝依賴
pip install -r requirements.txt

# 複製環境變數範本
cp example.env .env
# 編輯 .env 檔案，填入您的配置

# 啟動開發伺服器
uvicorn app.main:app --reload
```

### Docker 部署

```bash
# 構建並啟動所有服務
docker-compose up -d

# 查看日誌
docker-compose logs -f
```

詳細的部署指南請參閱 [部署文檔](doc/deployment_guide.md)。

## 文件結構

```
sortify/
├── frontend/            # 前端專案
│   ├── public/          # 靜態資源
│   └── src/             # 源代碼
│       ├── components/  # UI 組件
│       ├── pages/       # 頁面
│       ├── services/    # API 服務
│       └── ...
├── backend/             # 後端專案
│   ├── app/             # 應用程式
│   │   ├── apis/        # API 路由
│   │   ├── core/        # 核心功能
│   │   ├── crud/        # 資料庫操作
│   │   ├── models/      # 資料模型
│   │   └── services/    # 業務邏輯
│   ├── data/            # 資料存儲
│   └── tests/           # 測試
└── doc/                 # 文檔
```

## 開發指南

如果您想要貢獻代碼，請參閱我們的 [開發指南](doc/CONTRIBUTING.md)。

## 授權協議

本專案採用 [MIT 授權協議](LICENSE)。 