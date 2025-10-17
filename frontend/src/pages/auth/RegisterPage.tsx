import React, { useState, FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { GoogleOAuthProvider, GoogleLogin } from '@react-oauth/google';
import * as authApi from '../../services/authApi';
import { AxiosError } from 'axios';
import './AuthPages.css';

const RegisterPage: React.FC = () => {
  const [email, setEmail] = useState('');
  const [fullName, setFullName] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);

  const auth = useAuth();
  const navigate = useNavigate();
  const googleClientId = process.env.REACT_APP_GOOGLE_CLIENT_ID || '';

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setSuccessMessage(null);

    if (!email || !password) {
      setError('電子郵件和密碼為必填欄位。');
      return;
    }

    if (password !== confirmPassword) {
      setError('兩次輸入的密碼不一致。');
      return;
    }

    if (password.length < 8) {
      setError('密碼長度至少需要 8 個字元。');
      return;
    }

    const userData: authApi.UserRegistrationRequest = {
      username: email.split('@')[0], // 使用 email 本地部分作為用戶名
      email,
      password,
      full_name: fullName || undefined,
    };

    try {
      await auth.register(userData);
      setSuccessMessage('註冊成功！您現在可以前往登入頁面登入。');
      setEmail('');
      setFullName('');
      setPassword('');
      setConfirmPassword('');
      // 延遲後自動導向到登入頁面
      setTimeout(() => navigate('/auth/login'), 2000);
    } catch (err) {
      const axiosError = err as AxiosError<{ detail?: any }>;
      if (axiosError.response?.data?.detail) {
        if (typeof axiosError.response.data.detail === 'string') {
          setError(axiosError.response.data.detail);
        } else if (Array.isArray(axiosError.response.data.detail)) {
          const messages = axiosError.response.data.detail
            .map((e: any) => `${e.loc.join(' -> ')}: ${e.msg}`)
            .join('\n');
          setError(messages || '註冊資訊有誤，請檢查。');
        }
      } else {
        setError('註冊失敗，請稍後再試。');
      }
      console.error('Register page error:', err);
    }
  };

  const handleGoogleSuccess = async (credentialResponse: any) => {
    try {
      setError(null);
      const response = await authApi.googleLogin(credentialResponse.credential);
      if (response.access_token) {
        localStorage.setItem('authToken', response.access_token);
        await auth.fetchCurrentUser();
        navigate('/dashboard');
      }
    } catch (err) {
      const axiosError = err as AxiosError<{ detail?: string }>;
      if (axiosError.response?.data?.detail) {
        setError(axiosError.response.data.detail);
      } else {
        setError('Google 登入失敗，請稍後再試。');
      }
      console.error('Google login error:', err);
    }
  };

  const handleGoogleError = () => {
    setError('Google 登入已取消或發生錯誤。');
  };

  return (
    <div className="auth-container">
      {/* 左側品牌區域 */}
      <div className="auth-brand-section">
        <div className="brand-header">
          {/* Logo 圖片 */}
          <div className="brand-logo">
            <img 
              src="/images/logo.png" 
              alt="Sortify Logo" 
              className="brand-logo-image"
            />
          </div>
          <h1 className="brand-name">Sortify</h1>
          <p className="brand-description">智慧文件管理與AI問答系統</p>
          <p className="brand-subtitle">高效整理文件，智能解答問題</p>
        </div>

        {/* 品牌圖片 */}
        <div className="brand-image-container">
          <img 
            src="/images/logo.png" 
            alt="Sortify Logo" 
            className="brand-image"
            onError={(e) => {
              console.warn('Logo 圖片加載失敗');
              (e.target as HTMLImageElement).style.display = 'none';
            }}
          />
        </div>

        {/* 底部特性 */}
        <div className="brand-features">
          <div className="feature">
            <div className="feature-icon">📁</div>
            <span>智能文件分類</span>
          </div>
          <div className="feature">
            <div className="feature-icon">🔍</div>
            <span>快速搜索定位</span>
          </div>
          <div className="feature">
            <div className="feature-icon">🤖</div>
            <span>AI智能問答</span>
          </div>
        </div>
      </div>

      {/* 右側註冊表單區域 */}
      <div className="auth-form-section">
        <div className="form-wrapper">
          <h2 className="form-title">建立帳號</h2>

          <form onSubmit={handleSubmit}>
            {error && <div className="error-message">{error}</div>}
            {successMessage && <div className="success-message">{successMessage}</div>}

            {/* 全名輸入框 */}
            <div className="form-group">
              <label htmlFor="fullName" className="form-label">全名 (選填)</label>
              <div className="input-wrapper">
                <span className="input-icon">👤</span>
                <input
                  type="text"
                  id="fullName"
                  className="form-input"
                  placeholder="請輸入您的全名"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                />
              </div>
            </div>

            {/* 電子郵件輸入框 */}
            <div className="form-group">
              <label htmlFor="email" className="form-label">電子郵件 *</label>
              <div className="input-wrapper">
                <span className="input-icon">✉️</span>
                <input
                  type="email"
                  id="email"
                  className="form-input"
                  placeholder="請輸入電子郵件地址"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </div>
            </div>

            {/* 密碼輸入框 */}
            <div className="form-group">
              <label htmlFor="password" className="form-label">密碼 * (至少8位)</label>
              <div className="input-wrapper">
                <span className="input-icon">🔐</span>
                <input
                  type={showPassword ? 'text' : 'password'}
                  id="password"
                  className="form-input"
                  placeholder="請設定密碼"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  minLength={8}
                />
                <button
                  type="button"
                  className="password-toggle"
                  onClick={() => setShowPassword(!showPassword)}
                >
                  {showPassword ? '隱藏' : '顯示'}
                </button>
              </div>
            </div>

            {/* 確認密碼輸入框 */}
            <div className="form-group">
              <label htmlFor="confirmPassword" className="form-label">確認密碼 *</label>
              <div className="input-wrapper">
                <span className="input-icon">🔐</span>
                <input
                  type={showConfirmPassword ? 'text' : 'password'}
                  id="confirmPassword"
                  className="form-input"
                  placeholder="請再次輸入密碼"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  required
                  minLength={8}
                />
                <button
                  type="button"
                  className="password-toggle"
                  onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                >
                  {showConfirmPassword ? '隱藏' : '顯示'}
                </button>
              </div>
            </div>

            {/* 註冊按鈕 */}
            <button
              type="submit"
              className="submit-button"
              disabled={auth.isLoading}
            >
              {auth.isLoading ? '註冊中...' : '建立帳號'}
            </button>
          </form>

          {/* 分割線 */}
          <div className="divider">
            <span>或使用下列方式註冊</span>
          </div>

          {/* Google OAuth 按鈕 */}
          {googleClientId && (
            <GoogleOAuthProvider clientId={googleClientId}>
              <div className="oauth-buttons">
                <GoogleLogin
                  onSuccess={handleGoogleSuccess}
                  onError={handleGoogleError}
                  theme="outline"
                  size="large"
                  width="100%"
                />
              </div>
            </GoogleOAuthProvider>
          )}

          {/* 登入連結 */}
          <div className="auth-switch">
            <span>已經有帳號了？</span>
            <a href="/auth/login" className="auth-link">立即登入</a>
          </div>
        </div>
      </div>
    </div>
  );
};

export default RegisterPage; 