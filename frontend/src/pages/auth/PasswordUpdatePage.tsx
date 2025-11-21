import React, { useState } from 'react';
import { updatePassword } from '../../services/authApi';
import { PasswordUpdateInRequest } from '../../services/authApi';
import { Link, useNavigate } from 'react-router-dom';

const PasswordUpdatePage: React.FC = () => {
  const navigate = useNavigate();
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmNewPassword, setConfirmNewPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setSuccessMessage(null);
    setErrorMessage(null);

    if (newPassword !== confirmNewPassword) {
      setErrorMessage('新密碼與確認密碼不符。');
      setIsLoading(false);
      return;
    }
    if (newPassword.length < 8) {
      setErrorMessage('新密碼長度至少需要8個字符。');
      setIsLoading(false);
      return;
    }

    const passwordData: PasswordUpdateInRequest = {
      current_password: currentPassword,
      new_password: newPassword,
    };

    try {
      const response = await updatePassword(passwordData);
      setSuccessMessage(response.message || '密碼已成功更新！');
      setCurrentPassword('');
      setNewPassword('');
      setConfirmNewPassword('');
      // Optionally navigate away or show success for a few seconds
      // setTimeout(() => navigate('/profile'), 2000);
    } catch (err: any) {
      const apiErrorMessage = err.response?.data?.detail || err.message || '密碼更新失敗，請檢查您的目前密碼是否正確。';
      setErrorMessage(apiErrorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="p-10 bg-bg min-h-screen">
      {/* Header */}
      <div className="flex justify-between items-center mb-10 flex-wrap gap-5">
        <h1 className="page-title text-error">🔒 CHANGE PASSWORD</h1>
        <Link to="/profile" className="neo-btn-secondary">
          ← 返回個人資料
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

      {/* Main Card */}
      <div className="neo-card max-w-2xl border-error shadow-xl">
        <div className="card-header card-header-danger">⚠️ 安全操作區域</div>
        
        {/* Warning Banner */}
        <div className="warning-banner">
          <strong>⚡ 注意事項：</strong>
          <ul className="list-none p-0 mt-4 space-y-2">
            <li className="text-sm font-semibold">• 密碼長度至少 8 個字符</li>
            <li className="text-sm font-semibold">• 建議使用字母、數字和符號組合</li>
            <li className="text-sm font-semibold">• 更改後將需要重新登入</li>
          </ul>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-6">
          <div className="flex flex-col gap-2">
            <label htmlFor="currentPassword" className="text-xs font-black uppercase tracking-wider">
              🔐 目前密碼
            </label>
            <input 
              type="password" 
              id="currentPassword" 
              value={currentPassword} 
              onChange={(e) => setCurrentPassword(e.target.value)} 
              required 
              className="neo-input neo-input-danger px-4 py-3"
            />
          </div>

          <div className="flex flex-col gap-2">
            <label htmlFor="newPassword" className="text-xs font-black uppercase tracking-wider">
              🆕 新密碼 (至少8個字符)
            </label>
            <input 
              type="password" 
              id="newPassword" 
              value={newPassword} 
              onChange={(e) => setNewPassword(e.target.value)} 
              required 
              minLength={8}
              className="neo-input px-4 py-3"
            />
          </div>

          <div className="flex flex-col gap-2">
            <label htmlFor="confirmNewPassword" className="text-xs font-black uppercase tracking-wider">
              ✅ 確認新密碼
            </label>
            <input 
              type="password" 
              id="confirmNewPassword" 
              value={confirmNewPassword} 
              onChange={(e) => setConfirmNewPassword(e.target.value)} 
              required 
              minLength={8}
              className="neo-input px-4 py-3"
            />
          </div>

          <button 
            type="submit" 
            disabled={isLoading} 
            className="neo-btn-danger mt-2 py-4 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isLoading ? '⏳ 更新中...' : '🔒 更新密碼'}
          </button>
        </form>
      </div>
    </div>
  );
};

export default PasswordUpdatePage;