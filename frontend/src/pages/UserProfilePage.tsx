import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { updateCurrentUser } from '../services/authApi';
import { UserUpdateRequest } from '../services/authApi';
import { Link, useNavigate } from 'react-router-dom';

const UserProfilePage: React.FC = () => {
  const { currentUser, fetchCurrentUser } = useAuth();
  const navigate = useNavigate();

  const [email, setEmail] = useState(currentUser?.email || '');
  const [fullName, setFullName] = useState(currentUser?.full_name || '');
  const [isLoading, setIsLoading] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    if (currentUser) {
      setEmail(currentUser.email || '');
      setFullName(currentUser.full_name || '');
    } else {
      // 如果沒有 currentUser，可能需要導向到登入頁
      // navigate('/auth/login');
    }
  }, [currentUser, navigate]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setSuccessMessage(null);
    setErrorMessage(null);

    if (!currentUser) {
      setErrorMessage('使用者未登入');
      setIsLoading(false);
      return;
    }

    const updateData: UserUpdateRequest = {};
    if (email !== currentUser.email) {
      updateData.email = email;
    }
    if (fullName !== currentUser.full_name) {
      updateData.full_name = fullName;
    }

    if (Object.keys(updateData).length === 0) {
      setSuccessMessage('沒有需要更新的資訊。');
      setIsLoading(false);
      return;
    }

    try {
      await updateCurrentUser(updateData);
      await fetchCurrentUser(); // 從 AuthContext 更新 currentUser
      setSuccessMessage('個人資料已成功更新！');
    } catch (err: any) {
      const apiErrorMessage = err.response?.data?.detail || err.message || '更新失敗，請稍後再試';
      setErrorMessage(apiErrorMessage);
      // 如果是因為 email 衝突等，可以嘗試恢復原始值
      // setEmail(currentUser.email || '');
      // setFullName(currentUser.full_name || '');
    } finally {
      setIsLoading(false);
    }
  };

  if (!currentUser) {
    return (
      <div className="p-10 text-lg font-bold">
        載入使用者資訊...
      </div>
    );
  }

  return (
    <div className="p-10 bg-bg min-h-screen">
      {/* Header */}
      <div className="flex justify-between items-center mb-10 flex-wrap gap-5">
        <h1 className="page-title">PROFILE // SETTINGS</h1>
        <Link to="/dashboard" className="neo-btn-secondary">
          ← 返回儀表板
        </Link>
      </div>

      {/* Success/Error Messages */}
      {successMessage && (
        <div className="neo-message neo-message-success">
          ✓ {successMessage}
        </div>
      )}
      {errorMessage && (
        <div className="neo-message neo-message-error">
          ✗ {errorMessage}
        </div>
      )}

      <div className="grid grid-cols-1 gap-8 max-w-4xl">
        {/* Account Info Card - Read Only */}
        <div className="neo-card">
          <div className="card-header">📋 帳戶資訊 (唯讀)</div>
          <div className="space-y-4">
            <div className="info-row">
              <span className="info-label">使用者名稱:</span>
              <span className="info-value">{currentUser.username}</span>
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
                {new Date(currentUser.created_at).toLocaleDateString('zh-TW')}
              </span>
            </div>
            <div className="info-row border-b-0">
              <span className="info-label">最後更新:</span>
              <span className="info-value">
                {new Date(currentUser.updated_at).toLocaleDateString('zh-TW')}
              </span>
            </div>
          </div>
        </div>

        {/* Edit Profile Card */}
        <div className="neo-card">
          <div className="card-header card-header-success">
            ✏️ 編輯個人資料
          </div>
          <form onSubmit={handleSubmit} className="flex flex-col gap-5">
            <div className="flex flex-col gap-2">
              <label htmlFor="email" className="text-xs font-black uppercase tracking-wider">📧 Email</label>
              <input 
                type="email" 
                id="email" 
                value={email} 
                onChange={(e) => setEmail(e.target.value)} 
                className="neo-input px-4 py-3"
              />
            </div>
            <div className="flex flex-col gap-2">
              <label htmlFor="fullName" className="text-xs font-black uppercase tracking-wider">👤 全名</label>
              <input 
                type="text" 
                id="fullName" 
                value={fullName} 
                onChange={(e) => setFullName(e.target.value)} 
                className="neo-input px-4 py-3"
              />
            </div>
            <button 
              type="submit" 
              disabled={isLoading} 
              className="neo-btn-primary mt-2 py-4 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isLoading ? '⏳ 更新中...' : '💾 儲存變更'}
            </button>
          </form>
        </div>

        {/* Security Card */}
        <div className="neo-card">
          <div className="card-header card-header-warning">
            🔒 安全設定
          </div>
          <div className="pt-2">
            <p className="text-sm font-semibold mb-5">
              定期更改密碼以保護您的帳戶安全
            </p>
            <Link 
              to="/profile/change-password" 
              className="neo-btn-danger"
            >
              🔑 更改密碼
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
};

export default UserProfilePage;