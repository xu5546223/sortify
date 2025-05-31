import React, { useState, useCallback } from 'react';
import { BrowserRouter as Router, Routes, Route, NavLink, Navigate, Outlet } from 'react-router-dom';
import { ConfigProvider } from 'antd';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { ThemeProvider, useTheme } from './contexts/ThemeContext';
import { SettingsProvider } from './contexts/SettingsContext';
import { getAntdTheme } from './styles/antdTheme';
import LoginPage from './pages/auth/LoginPage';
import RegisterPage from './pages/auth/RegisterPage';
import DashboardPage from './pages/DashboardPage';
import ConnectionPage from './pages/ConnectionPage';
import SettingsPage from './pages/SettingsPage';
import DocumentsPage from './pages/DocumentsPage';
import LogsPage from './pages/LogsPage';
import NotFoundPage from './pages/NotFoundPage'; // For 404
import UserProfilePage from './pages/UserProfilePage'; // 新增
import PasswordUpdatePage from './pages/auth/PasswordUpdatePage'; // 新增
import VectorDatabasePage from './pages/VectorDatabasePage'; // 新增
import AIQAPage from './pages/AIQAPage'; // 新增
import { ThemeShowcasePage } from './pages/ThemeShowcasePage'; // 主題展示頁面

import { CopilotPopup } from '@copilotkit/react-ui'; // 新增導入
import "@copilotkit/react-ui/styles.css"; // 新增導入樣式

// Props 類型定義，用於期望 showPCMessage 的頁面組件
interface PageWithMessageHandlerProps {
  showPCMessage: (message: string, type?: string, duration?: number) => () => void;
}

// Icons (assuming Font Awesome is linked in index.html)
const icon = (className: string): JSX.Element => <i className={`fas ${className} fa-fw mr-2`}></i>;

// 導航項目定義
const navItems: Array<{
  path: string;
  name: string;
  icon: string;
  component: React.ComponentType<any>; // 允許任何 React 組件
}> = [
  { path: "/dashboard", name: "儀表板", icon: "fa-tachometer-alt", component: DashboardPage },
  { path: "/connection", name: "連線管理", icon: "fa-users", component: ConnectionPage },
  { path: "/documents", name: "文件管理", icon: "fa-folder-open", component: DocumentsPage },
  { path: "/vector-database", name: "向量數據庫", icon: "fa-database", component: VectorDatabasePage },
  { path: "/ai-qa", name: "AI 問答", icon: "fa-robot", component: AIQAPage },
  { path: "/settings", name: "系統設定", icon: "fa-sliders-h", component: SettingsPage },
  { path: "/logs", name: "系統日誌", icon: "fa-clipboard-list", component: LogsPage },
  { path: "/theme", name: "主題管理", icon: "fa-palette", component: ThemeShowcasePage },
];

// 使用 React.memo 優化 Sidebar 性能
const Sidebar = React.memo(() => {
  return (
    <div className="sidebar fixed top-0 left-0 h-full overflow-y-auto bg-surface-900 text-surface-100 w-64">
      <div className="logo p-5 text-center text-xl font-semibold border-b border-surface-700">
        {icon("fa-cogs")}AI 文件助理
      </div>
      <nav>
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            className={({ isActive }) =>
              `block py-3 px-5 text-surface-300 hover:bg-surface-800 hover:text-white transition-colors duration-200 border-l-4 border-transparent ${
                isActive ? "bg-surface-800 text-white border-primary-500" : ""
              }`
            }
          >
            {icon(item.icon)}{item.name}
          </NavLink>
        ))}
      </nav>
    </div>
  );
});

// 使用 React.memo 優化 MessageBoxPC 性能
const MessageBoxPC = React.memo<{ message: string; type: string; visible: boolean }>(({ message, type, visible }) => {
  if (!visible) return null;

  let bgColor = 'bg-surface-800'; // Default for info
  if (type === 'error') bgColor = 'bg-red-600';
  else if (type === 'success') bgColor = 'bg-green-600';

  return (
    <div className={`message-box-pc fixed bottom-5 right-5 text-white py-3 px-6 rounded-md shadow-lg z-50 ${bgColor}`}>
      {message}
    </div>
  );
});

// 簡易的載入指示器樣式
const loadingStyles: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'center',
  alignItems: 'center',
  height: '100vh',
  fontSize: '20px',
  fontFamily: 'Arial, sans-serif',
};

const LoadingIndicator: React.FC = () => <div style={loadingStyles}>載入中...</div>;

// 受保護路由的元素封裝器 (之前命名為 ProtectedRoute)
const ProtectedRouteWrapper = ({ children }: { children: JSX.Element }) => {
  const { currentUser, isLoading } = useAuth();
  if (isLoading) return <LoadingIndicator />;
  return currentUser ? children : <Navigate to="/auth/login" replace />;
};

// 公開路由的元素封裝器 (之前命名為 PublicRoute)
const PublicRouteWrapper = ({ children }: { children: JSX.Element }) => {
  const { currentUser, isLoading } = useAuth();
  if (isLoading) return <LoadingIndicator />;
  return !currentUser ? children : <Navigate to="/dashboard" replace />;
};

// 根路徑重導向組件
const RootRedirect = () => {
  const { currentUser, isLoading } = useAuth();
  if (isLoading) return <LoadingIndicator />;
  return currentUser ? <Navigate to="/dashboard" replace /> : <Navigate to="/auth/login" replace />;
};

// 包含 Sidebar 和主要內容區域的佈局組件
const MainLayoutWithSidebar: React.FC = () => {
  return (
    <div className="flex h-screen bg-surface-100">
      <Sidebar />
      <main className="content flex-grow p-5 ml-64 overflow-y-auto">
        <Outlet /> {/* 子路由將在此渲染 */}
      </main>
    </div>
  );
};

// 內部組件，用於訪問主題 context
const AppWithTheme: React.FC = () => {
  const { actualTheme } = useTheme();
  const [messageBox, setMessageBox] = useState({ message: '', type: 'info', visible: false });

  const showPCMessage = useCallback((message: string, type = 'info', duration = 3000) => {
    setMessageBox({ message, type, visible: true });
    const timer = setTimeout(() => {
      setMessageBox(prev => ({ ...prev, visible: false }));
    }, duration);
    return () => clearTimeout(timer);
  }, []);

  return (
    <ConfigProvider theme={getAntdTheme(actualTheme === 'dark')}>
      <Routes>
        {/* 公開路由 (不含 Sidebar) */}
        <Route path="/auth/login" element={<PublicRouteWrapper><LoginPage /></PublicRouteWrapper>} />
        <Route path="/auth/register" element={<PublicRouteWrapper><RegisterPage /></PublicRouteWrapper>} />

        {/* 根路徑重導向 */}
        <Route path="/" element={<RootRedirect />} />

        {/* 受保護的路由 (使用 MainLayoutWithSidebar) */}
        <Route 
          element={ // 這個 Route 作為佈局容器
            <ProtectedRouteWrapper>
              <MainLayoutWithSidebar />
            </ProtectedRouteWrapper>
          }
        >
          {/* 以下是 MainLayoutWithSidebar 的子路由 */}
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/profile" element={<UserProfilePage />} />
          <Route path="/profile/change-password" element={<PasswordUpdatePage />} />
          
          {/* navItems 中的其他受保護路由 (Dashboard 已單獨處理) */}
          {navItems.filter(item => item.path !== "/dashboard").map(item => {
            // 檢查組件是否需要 showPCMessage 參數
            const needsShowPCMessage = ["/connection", "/settings", "/documents", "/logs", "/vector-database", "/ai-qa"].includes(item.path);
            
            return (
              <Route 
                key={item.path} 
                path={item.path} 
                element={
                  needsShowPCMessage 
                    ? <item.component showPCMessage={showPCMessage} />
                    : <item.component />
                }
              />
            );
          })}
        </Route>
        
        {/* 404 頁面 */}
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
      <MessageBoxPC message={messageBox.message} type={messageBox.type} visible={messageBox.visible} />
      <CopilotPopup /> {/* 新增 Copilot Popup */}
    </ConfigProvider>
  );
};

const App: React.FC = () => {
  return (
    <Router>
      <AuthProvider>
        <ThemeProvider>
          <SettingsProvider>
            <AppWithTheme />
          </SettingsProvider>
        </ThemeProvider>
      </AuthProvider>
    </Router>
  );
};

export default App; 