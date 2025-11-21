import React from 'react';
import { useAuth } from '../contexts/AuthContext';
import { Link } from 'react-router-dom';

const DashboardPage: React.FC = () => {
  const { currentUser } = useAuth();

  if (!currentUser) {
    return (
      <div className="p-10 text-lg font-bold">
        載入中...
      </div>
    );
  }

  // 模擬統計數據（可以之後從 API 獲取）
  const stats = {
    totalFiles: 0,
    sortedPercentage: 0,
    errors: 0,
    aiStatus: currentUser.is_active ? 'ONLINE' : 'OFFLINE',
  };

  return (
    <div className="p-10 bg-bg min-h-screen">
      {/* Header */}
      <div className="flex justify-between items-center mb-10 flex-wrap gap-5">
        <h1 className="page-title">DASHBOARD // USER</h1>
        <Link to="/profile" className="neo-btn-primary">
          ⚙️ 設定
        </Link>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5 mb-10">
        <div className="stat-card stat-card-active">
          <div className="text-xs font-black uppercase tracking-wide mb-2 text-active">使用者名稱</div>
          <div className="text-4xl font-black leading-none text-active">
            {currentUser.username}
          </div>
        </div>

        <div className="stat-card stat-card-success">
          <div className="text-xs font-black uppercase tracking-wide mb-2 text-primary">註冊天數</div>
          <div className="text-5xl font-black leading-none text-primary">
            {Math.floor((Date.now() - new Date(currentUser.created_at).getTime()) / (1000 * 60 * 60 * 24))}
          </div>
        </div>

        <div className="stat-card stat-card-danger">
          <div className="text-xs font-black uppercase tracking-wide mb-2 text-error">檔案錯誤</div>
          <div className="text-5xl font-black leading-none text-error">{stats.errors}</div>
        </div>

        <div className="stat-card stat-card-dark">
          <div className="text-xs font-black uppercase tracking-wide mb-2 text-primary">帳號狀態</div>
          <div className="text-4xl font-black leading-none text-primary">
            ⚡ {stats.aiStatus}
          </div>
        </div>
      </div>

      {/* Account Info Section */}
      <div className="neo-card max-w-4xl">
        <div className="card-header">帳戶資訊</div>
        <div className="space-y-4">
          <div className="info-row">
            <span className="info-label">使用者名稱:</span>
            <span className="info-value">{currentUser.username}</span>
          </div>
          <div className="info-row">
            <span className="info-label">Email:</span>
            <span className="info-value">{currentUser.email || '未提供'}</span>
          </div>
          <div className="info-row">
            <span className="info-label">全名:</span>
            <span className="info-value">{currentUser.full_name || '未提供'}</span>
          </div>
          <div className="info-row">
            <span className="info-label">帳號狀態:</span>
            <span className="info-value">
              <span className={`neo-badge ${!currentUser.is_active && 'neo-badge-danger'}`}>
                {currentUser.is_active ? '✓ 已啟用' : '✗ 未啟用'}
              </span>
            </span>
          </div>
          <div className="info-row">
            <span className="info-label">註冊時間:</span>
            <span className="info-value">
              {new Date(currentUser.created_at).toLocaleDateString('zh-TW')} {new Date(currentUser.created_at).toLocaleTimeString('zh-TW')}
            </span>
          </div>
          <div className="info-row border-b-0">
            <span className="info-label">最後更新:</span>
            <span className="info-value">
              {new Date(currentUser.updated_at).toLocaleDateString('zh-TW')} {new Date(currentUser.updated_at).toLocaleTimeString('zh-TW')}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DashboardPage;