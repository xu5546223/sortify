import React, { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  HomeOutlined,
  FileTextOutlined,
  MessageOutlined,
  UserOutlined
} from '@ant-design/icons';

const MobileBottomNav: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const [isPaired, setIsPaired] = useState(false);

  useEffect(() => {
    // 檢查配對狀態
    const checkPairing = () => {
      const hasAuth = localStorage.getItem('authToken') || localStorage.getItem('sortify_device_token');
      setIsPaired(!!hasAuth);
      console.log('📊 底部導航欄檢查配對狀態:', !!hasAuth);
    };

    checkPairing();
    
    // 監聽 storage 變化
    window.addEventListener('storage', checkPairing);
    window.addEventListener('pairing-status-changed', checkPairing);
    
    return () => {
      window.removeEventListener('storage', checkPairing);
      window.removeEventListener('pairing-status-changed', checkPairing);
    };
  }, []);

  // 如果在掃描頁面或未配對，不顯示底部導航
  if (location.pathname === '/mobile/scan' || !isPaired) {
    return null;
  }

  const navItems = [
    {
      key: 'home',
      path: '/mobile/home',
      icon: <HomeOutlined />,
      label: '首頁'
    },
    {
      key: 'documents',
      path: '/mobile/documents',
      icon: <FileTextOutlined />,
      label: '文件'
    },
    {
      key: 'qa',
      path: '/mobile/qa',
      icon: <MessageOutlined />,
      label: '問答'
    },
    {
      key: 'profile',
      path: '/mobile/profile',
      icon: <UserOutlined />,
      label: '我的'
    }
  ];

  return (
    <div className="mobile-bottom-nav">
      {navItems.map((item) => (
        <div
          key={item.key}
          className={`mobile-nav-item ${location.pathname === item.path ? 'active' : ''}`}
          onClick={() => navigate(item.path)}
        >
          <span className="mobile-nav-icon">{item.icon}</span>
          <span className="mobile-nav-label">{item.label}</span>
        </div>
      ))}
    </div>
  );
};

export default MobileBottomNav;

