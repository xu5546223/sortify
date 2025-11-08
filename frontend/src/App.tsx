import React, { useState, useCallback, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, Outlet, useNavigate, useLocation } from 'react-router-dom';
import { ConfigProvider } from 'antd';
import { GoogleOAuthProvider } from '@react-oauth/google';
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
import GmailCallback from './pages/auth/GmailCallback';
import { navItems } from './config/navConfig';
import MainLayoutWithSidebar from './components/layout/MainLayoutWithSidebar';
import MessageBoxPC from './components/common/MessageBoxPC';
import ProtectedRouteWrapper from './components/routes/ProtectedRouteWrapper';
import PublicRouteWrapper from './components/routes/PublicRouteWrapper';
import RootRedirect from './components/routes/RootRedirect';
// 手機端導入
import MobileLayout from './mobile/layouts/MobileLayout';
import MobileAuthGuard from './mobile/components/MobileAuthGuard';
import MobileHome from './mobile/pages/MobileHome';
import MobileScan from './mobile/pages/MobileScan';
import MobileCamera from './mobile/pages/MobileCamera';
import MobileUpload from './mobile/pages/MobileUpload';
import MobilePreview from './mobile/pages/MobilePreview';
import MobileDocuments from './mobile/pages/MobileDocuments';
import MobileDocumentsWithClusters from './mobile/pages/MobileDocumentsWithClusters';
import MobileDocumentDetail from './mobile/pages/MobileDocumentDetail';
import MobileQA from './mobile/pages/MobileAIQA';
import MobileProfile from './mobile/pages/MobileProfile';
import MobileSettings from './mobile/pages/MobileSettings';
import MobileStyleTest from './mobile/pages/MobileStyleTest';
import MobileQuestionBank from './mobile/pages/MobileQuestionBank';
import { isMobileDevice } from './utils/pwaUtils';
import { registerServiceWorker } from './utils/pwaUtils';

// 裝置檢測和自動導航組件
const DeviceRouter: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const isMobile = isMobileDevice();

  useEffect(() => {
    console.log('🔍 DeviceRouter 檢查:', { 
      isMobile, 
      currentPath: location.pathname,
      hasAuth: !!(localStorage.getItem('authToken') || localStorage.getItem('sortify_device_token'))
    });

    // 如果是手機裝置且不在手機端路由，自動導航到手機端
    if (isMobile && !location.pathname.startsWith('/mobile') && !location.pathname.startsWith('/auth')) {
      // 檢查是否已配對
      const hasAuth = localStorage.getItem('authToken') || localStorage.getItem('sortify_device_token');
      
      console.log('📱 手機裝置訪問電腦端頁面，自動導航到手機端');
      
      if (hasAuth) {
        console.log('✅ 已配對 → 導航到 /mobile/home');
        navigate('/mobile/home', { replace: true });
      } else {
        console.log('❌ 未配對 → 導航到 /mobile/scan');
        navigate('/mobile/scan', { replace: true });
      }
    }
    // 如果是電腦裝置且在手機端路由，導航到電腦端
    else if (!isMobile && location.pathname.startsWith('/mobile')) {
      console.log('💻 電腦裝置訪問手機端頁面，導航到電腦端');
      navigate('/dashboard', { replace: true });
    }
  }, [isMobile, location.pathname, navigate]);

  return null;
};

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
      <DeviceRouter />
      <Routes>
        {/* 認證路由 */}
        <Route path="/auth/login" element={<PublicRouteWrapper><LoginPage /></PublicRouteWrapper>} />
        <Route path="/auth/register" element={<PublicRouteWrapper><RegisterPage /></PublicRouteWrapper>} />
        <Route path="/auth/gmail-callback" element={<GmailCallback />} />
        
        {/* 根路由 */}
        <Route path="/" element={<RootRedirect />} />
        
        {/* 手機端路由 */}
        <Route path="/mobile" element={<MobileLayout />}>
          {/* 掃描頁面 - 無需配對即可訪問 */}
          <Route path="scan" element={<MobileScan />} />
          
          {/* 其他頁面 - 需要配對後才能訪問 */}
          <Route path="home" element={
            <MobileAuthGuard>
              <MobileHome />
            </MobileAuthGuard>
          } />
          <Route path="camera" element={
            <MobileAuthGuard>
              <MobileCamera />
            </MobileAuthGuard>
          } />
          <Route path="upload" element={
            <MobileAuthGuard>
              <MobileUpload />
            </MobileAuthGuard>
          } />
          <Route path="preview" element={
            <MobileAuthGuard>
              <MobilePreview />
            </MobileAuthGuard>
          } />
          <Route path="documents" element={
            <MobileAuthGuard>
              <MobileDocumentsWithClusters />
            </MobileAuthGuard>
          } />
          <Route path="documents/:id" element={
            <MobileAuthGuard>
              <MobileDocumentDetail />
            </MobileAuthGuard>
          } />
          <Route path="qa" element={
            <MobileAuthGuard>
              <MobileQA />
            </MobileAuthGuard>
          } />
          <Route path="question-bank" element={
            <MobileAuthGuard>
              <MobileQuestionBank />
            </MobileAuthGuard>
          } />
          <Route path="profile" element={
            <MobileAuthGuard>
              <MobileProfile />
            </MobileAuthGuard>
          } />
          <Route path="settings" element={
            <MobileAuthGuard>
              <MobileSettings />
            </MobileAuthGuard>
          } />
          <Route path="style-test" element={
            <MobileAuthGuard>
              <MobileStyleTest />
            </MobileAuthGuard>
          } />
        </Route>
        
        {/* 電腦端路由 */}
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
    </ConfigProvider>
  );
};

const App: React.FC = () => {
  const googleClientId = process.env.REACT_APP_GOOGLE_CLIENT_ID || '';

  // 註冊 Service Worker（PWA）
  useEffect(() => {
    registerServiceWorker();
  }, []);

  return (
    <GoogleOAuthProvider clientId={googleClientId}>
      <Router>
        <AuthProvider>
          <ThemeProvider>
            <SettingsProvider>
              <AppWithTheme />
            </SettingsProvider>
          </ThemeProvider>
        </AuthProvider>
      </Router>
    </GoogleOAuthProvider>
  );
};

export default App; 