/**
 * Mobile Auth Guard
 * 保護手機端路由，確保用戶已完成配對才能訪問其他頁面
 */

import React, { useEffect, useState } from 'react';
import { Navigate, useLocation } from 'react-router-dom';

interface MobileAuthGuardProps {
  children: React.ReactNode;
}

const MobileAuthGuard: React.FC<MobileAuthGuardProps> = ({ children }) => {
  const location = useLocation();
  const [isChecking, setIsChecking] = useState(true);
  const [isPaired, setIsPaired] = useState(false);

  useEffect(() => {
    // 檢查配對狀態
    const checkPairing = () => {
      const authToken = localStorage.getItem('authToken');
      const deviceToken = localStorage.getItem('sortify_device_token');
      const hasPaired = !!(authToken || deviceToken);
      
      console.log('🔐 MobileAuthGuard 檢查配對狀態:', {
        hasPaired,
        hasAuthToken: !!authToken,
        hasDeviceToken: !!deviceToken,
        currentPath: location.pathname
      });
      
      setIsPaired(hasPaired);
      setIsChecking(false);
    };

    checkPairing();

    // 監聽 storage 變化（配對狀態改變時）
    const handleStorageChange = () => {
      console.log('📦 Storage 變化，重新檢查配對狀態');
      checkPairing();
    };

    window.addEventListener('storage', handleStorageChange);
    window.addEventListener('pairing-status-changed', handleStorageChange);

    return () => {
      window.removeEventListener('storage', handleStorageChange);
      window.removeEventListener('pairing-status-changed', handleStorageChange);
    };
  }, [location.pathname]);

  // 檢查中，顯示載入畫面
  if (isChecking) {
    return (
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '100vh',
        backgroundColor: '#f8f9fa',
        padding: '24px'
      }}>
        <div style={{
          width: '60px',
          height: '60px',
          border: '4px solid rgba(41, 191, 18, 0.2)',
          borderTopColor: '#29bf12',
          borderRadius: '50%',
          animation: 'spin 1s linear infinite'
        }} />
        <p style={{
          marginTop: '24px',
          fontSize: '16px',
          color: '#666',
          textAlign: 'center'
        }}>
          正在檢查配對狀態...
        </p>
        <style>{`
          @keyframes spin {
            to { transform: rotate(360deg); }
          }
        `}</style>
      </div>
    );
  }

  // 如果未配對，重定向到掃描頁面
  if (!isPaired) {
    console.warn('⚠️ 未配對裝置嘗試訪問:', location.pathname, '→ 重定向到 /mobile/scan');
    return <Navigate to="/mobile/scan" replace />;
  }

  // 已配對，允許訪問
  return <>{children}</>;
};

export default MobileAuthGuard;

