import React, { useEffect } from 'react';
import { Outlet } from 'react-router-dom';
import MobileBottomNav from '../components/MobileBottomNav';
import '../../styles/mobile.css';

const MobileLayout: React.FC = () => {
  useEffect(() => {
    // 設置視口高度（處理移動瀏覽器地址欄）
    const setViewportHeight = () => {
      const vh = window.innerHeight * 0.01;
      document.documentElement.style.setProperty('--vh', `${vh}px`);
    };

    setViewportHeight();
    window.addEventListener('resize', setViewportHeight);
    
    // 為手機端設置明亮背景色
    document.body.style.backgroundColor = '#f8f9fa';
    
    return () => {
      window.removeEventListener('resize', setViewportHeight);
      // 清理時恢復背景色
      document.body.style.backgroundColor = '';
    };
  }, []);

  return (
    <div className="mobile-container mobile-safe-area">
      <div className="mobile-content">
        <Outlet />
      </div>
      <MobileBottomNav />
    </div>
  );
};

export default MobileLayout;

