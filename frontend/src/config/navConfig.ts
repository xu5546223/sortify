import DashboardPage from '../pages/DashboardPage';
import ConnectionPage from '../pages/ConnectionPage';
import SettingsPage from '../pages/SettingsPage';
import DocumentsPage from '../pages/DocumentsPage';
import LogsPage from '../pages/LogsPage';
import VectorDatabasePage from '../pages/VectorDatabasePage';
import AIQAPage from '../pages/AIQAPage';
import { ThemeShowcasePage } from '../pages/ThemeShowcasePage';
import React from 'react'; // React 可能被 React.ComponentType<any> 需要

// 導航項目定義
export const navItems: Array<{
  path: string;
  name: string;
  icon: string; // class name for the icon, icon JSX will be handled in Sidebar
  component: React.ComponentType<any>; 
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