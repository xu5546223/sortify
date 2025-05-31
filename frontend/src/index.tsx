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
const copilotRuntimeUrl = process.env.REACT_APP_COPILOT_RUNTIME_URL || "http://localhost:8000/api/v1/copilotkit_actions/"; // 移除結尾斜線，與後端新註冊路徑匹配

root.render(
  <CopilotKit runtimeUrl={copilotRuntimeUrl}>
    <App />
  </CopilotKit>
);

// If you want to start measuring performance in your app, pass a function
// to log results (for example: reportWebVitals(console.log))
// or send to an analytics endpoint. Learn more: https://bit.ly/CRA-vitals
reportWebVitals(); 