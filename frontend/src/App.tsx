import React, { useState, useCallback } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, Outlet } from 'react-router-dom';
import { ConfigProvider } from 'antd';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { ThemeProvider, useTheme } from './contexts/ThemeContext';
import { SettingsProvider } from './contexts/SettingsContext';
import { getAntdTheme } from './styles/antdTheme';
import LoginPage from './pages/auth/LoginPage';
import RegisterPage from './pages/auth/RegisterPage';
import DashboardPage from './pages/DashboardPage';
import NotFoundPage from './pages/NotFoundPage';
import UserProfilePage from './pages/UserProfilePage';
import PasswordUpdatePage from './pages/auth/PasswordUpdatePage';
import { CopilotPopup } from '@copilotkit/react-ui';
import "@copilotkit/react-ui/styles.css";
import { navItems } from './config/navConfig';
import MainLayoutWithSidebar from './components/layout/MainLayoutWithSidebar';
import MessageBoxPC from './components/common/MessageBoxPC';
import ProtectedRouteWrapper from './components/routes/ProtectedRouteWrapper';
import PublicRouteWrapper from './components/routes/PublicRouteWrapper';
import RootRedirect from './components/routes/RootRedirect';

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
        <Route path="/auth/login" element={<PublicRouteWrapper><LoginPage /></PublicRouteWrapper>} />
        <Route path="/auth/register" element={<PublicRouteWrapper><RegisterPage /></PublicRouteWrapper>} />
        <Route path="/" element={<RootRedirect />} />
        <Route 
          element={
            <ProtectedRouteWrapper>
              <MainLayoutWithSidebar />
            </ProtectedRouteWrapper>
          }
        >
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/profile" element={<UserProfilePage />} />
          <Route path="/profile/change-password" element={<PasswordUpdatePage />} />
          {navItems.filter(item => item.path !== "/dashboard").map(item => {
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
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
      <MessageBoxPC message={messageBox.message} type={messageBox.type} visible={messageBox.visible} />
      <CopilotPopup />
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