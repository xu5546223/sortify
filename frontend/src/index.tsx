import React from 'react';
import ReactDOM from 'react-dom/client';
import './styles/main.css'; // 引入全局樣式
import App from './App';
import reportWebVitals from './reportWebVitals';
import { CopilotKit } from '@copilotkit/react-core';

const root = ReactDOM.createRoot(
  document.getElementById('root') as HTMLElement
);

// 移除 StrictMode 以避免開發環境中 useEffect 被執行兩次
// runtimeUrl 應指向您在後端 FastAPI 設定的 CopilotKit 端點的完整 URL
// 例如: http://localhost:8000/api/v1/copilotkit_actions (本地開發時)
// 或在 Docker 環境中指向後端服務的 URL
// 更新 runtimeUrl 指向新的 Node.js CopilotKit Runtime
// 假設新的 Node.js Runtime 運行在 http://localhost:3001 (端口可自訂)
// 並且其 API 端點是 /api/copilotkit
const copilotRuntimeUrl = "http://localhost:3001/api/copilotkit";

console.log("Copilot Runtime URL (pointing to Main Node.js Runtime):", copilotRuntimeUrl);

root.render(
  <CopilotKit runtimeUrl={copilotRuntimeUrl}>
    <App />
  </CopilotKit>
);

// If you want to start measuring performance in your app, pass a function
// to log results (for example: reportWebVitals(console.log))
// or send to an analytics endpoint. Learn more: https://bit.ly/CRA-vitals
reportWebVitals(); 