import React from 'react';
import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar'; // 導入 Sidebar 組件

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

export default MainLayoutWithSidebar; 