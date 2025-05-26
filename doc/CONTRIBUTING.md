# 貢獻指南

感謝您對 Sortify AI Assistant 的貢獻興趣！這份文件將指導您如何參與專案開發。

## 開發環境設置

請參考 [README.md](../README.md) 中的「快速開始」部分進行開發環境設置。

## 分支管理

我們採用以下分支管理策略：

- `main`: 主分支，用於正式發布
- `develop`: 開發分支，所有功能開發完成後合併到此分支
- `feature/xxx`: 功能分支，用於開發新功能
- `bugfix/xxx`: 錯誤修復分支
- `hotfix/xxx`: 緊急修復分支，用於修復生產環境中的重大問題

## 提交規範

請遵循以下提交訊息格式：

```
<type>(<scope>): <subject>

<body>

<footer>
```

其中 `type` 可以是：

- `feat`: 新功能
- `fix`: 錯誤修復
- `docs`: 文檔變更
- `style`: 不影響代碼含義的變更（空格、格式化等）
- `refactor`: 重構（既不是新功能，也不是錯誤修復）
- `perf`: 性能優化
- `test`: 增加測試
- `chore`: 構建過程或輔助工具的變動

例如：

```
feat(document): 添加文件批量處理功能

添加了一個新的API端點，允許使用者批量上傳和處理多個文件。
實現了並行處理以提高效率。

Closes #123
```

## 開發流程

1. Fork 本專案
2. 從 `develop` 分支建立新的功能分支
3. 提交您的更改
4. 確保所有測試通過
5. 提交 Pull Request 到 `develop` 分支

## 代碼風格

### Python 後端

我們使用 [Black](https://github.com/psf/black) 和 [isort](https://github.com/PyCQA/isort) 進行代碼格式化，並使用 [flake8](https://github.com/PyCQA/flake8) 進行代碼質量檢查。

```bash
# 安裝工具
pip install black isort flake8

# 格式化代碼
black .
isort .

# 檢查代碼質量
flake8
```

### React 前端

我們使用 ESLint 和 Prettier 進行代碼風格檢查和格式化。

```bash
# 格式化代碼
npm run format

# 檢查代碼質量
npm run lint
```

## 測試

請確保您的更改包含適當的測試：

### 後端測試

```bash
# 運行所有測試
pytest

# 運行指定測試
pytest tests/test_document_service.py
```

### 前端測試

```bash
# 運行所有測試
npm test

# 運行指定測試
npm test -- MyComponent.test.js
```

## 文檔

如果您添加了新功能或更改了現有功能，請確保更新相關文檔。

## 問題和討論

如果您有任何問題或想討論某個功能，請在 GitHub Issues 中創建一個新問題。

再次感謝您的貢獻！ 