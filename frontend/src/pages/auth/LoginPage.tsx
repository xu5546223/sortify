import React, { useState, FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { GoogleOAuthProvider, GoogleLogin } from '@react-oauth/google';
import { AxiosError } from 'axios';
import * as authApi from '../../services/authApi';
import './AuthPages.css';

const LoginPage: React.FC = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [rememberMe, setRememberMe] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  const auth = useAuth();
  const navigate = useNavigate();
  const googleClientId = process.env.REACT_APP_GOOGLE_CLIENT_ID || '';

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);

    if (!email || !password) {
      setError('請輸入電子郵件和密碼。');
      return;
    }

    try {
      await auth.login({ username: email, password });
      navigate('/dashboard');
    } catch (err) {
      const axiosError = err as AxiosError<{ detail?: string }>;
      if (axiosError.response?.data?.detail) {
        setError(axiosError.response.data.detail);
      } else {
        setError('登入失敗，請檢查您的電子郵件和密碼。');
      }
      console.error('Login page error:', err);
    }
  };

  const handleGoogleSuccess = async (credentialResponse: any) => {
    try {
      setError(null);
      // 調用後端 Google OAuth 回調端點
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
        {/* 品牌 Logo 和文字 */}
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

      {/* 右側登錄表單區域 */}
      <div className="auth-form-section">
        <div className="form-wrapper">
          <h2 className="form-title">登入系統</h2>

          <form onSubmit={handleSubmit}>
            {error && <div className="error-message">{error}</div>}

            {/* 電子郵件輸入框 */}
            <div className="form-group">
              <label htmlFor="email" className="form-label">電子郵件</label>
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
                  autoComplete="email"
                />
              </div>
            </div>

            {/* 密碼輸入框 */}
            <div className="form-group">
              <label htmlFor="password" className="form-label">密碼</label>
              <div className="input-wrapper">
                <span className="input-icon">🔐</span>
                <input
                  type={showPassword ? 'text' : 'password'}
                  id="password"
                  className="form-input"
                  placeholder="請輸入密碼"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  autoComplete="current-password"
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

            {/* 記住我和忘記密碼 */}
            <div className="form-options">
              <label className="remember-me">
                <input
                  type="checkbox"
                  checked={rememberMe}
                  onChange={(e) => setRememberMe(e.target.checked)}
                />
                <span>記住我</span>
              </label>
              <a href="#" className="forgot-password">忘記密碼？</a>
            </div>

            {/* 登入按鈕 */}
            <button
              type="submit"
              className="submit-button"
              disabled={auth.isLoading}
            >
              {auth.isLoading ? '登入中...' : '登入'}
            </button>
          </form>

          {/* 分割線 */}
          <div className="divider">
            <span>或使用下列方式登入</span>
          </div>

          {/* OAuth 按鈕 */}
          <div className="oauth-buttons">
            {googleClientId && (
              <GoogleOAuthProvider clientId={googleClientId}>
                <GoogleLogin
                  onSuccess={handleGoogleSuccess}
                  onError={handleGoogleError}
                  theme="outline"
                  size="large"
                  width="100%"
                />
              </GoogleOAuthProvider>
            )}
            {!googleClientId && (
              <div className="oauth-button-placeholder">
                <p>Google 登入功能已禁用</p>
                <small>請配置 REACT_APP_GOOGLE_CLIENT_ID 環境變數</small>
              </div>
            )}
          </div>

          {/* 註冊連結 */}
          <div className="auth-switch">
            <span>還沒有帳號嗎？</span>
            <a href="/auth/register" className="auth-link">立即註冊</a>
          </div>
        </div>
      </div>
    </div>
  );
};

export default LoginPage; 