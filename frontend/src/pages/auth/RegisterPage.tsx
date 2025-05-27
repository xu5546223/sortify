import React, { useState, FormEvent } from 'react';
import { useNavigate } from 'react-router-dom'; // 假設您使用 React Router
import { useAuth } from '../../contexts/AuthContext';
import * as authApi from '../../services/authApi'; // 引入類型
import { AxiosError } from 'axios';

// 簡易的樣式物件 (與 LoginPage 相似，可以提取為共用樣式或使用您的樣式系統)
const styles: { [key: string]: React.CSSProperties } = {
  pageContainer: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: '80vh',
    padding: '20px',
    backgroundColor: '#f4f7f6', // 輕微調整背景色以區分
  },
  formContainer: {
    padding: '30px',
    borderRadius: '8px',
    boxShadow: '0 4px 12px rgba(0, 0, 0, 0.1)',
    backgroundColor: '#ffffff',
    width: '100%',
    maxWidth: '450px', // 註冊表單可能稍寬
  },
  title: {
    textAlign: 'center',
    marginBottom: '25px',
    fontSize: '24px',
    color: '#333',
  },
  inputGroup: {
    marginBottom: '15px', // 減少一點間距
  },
  label: {
    display: 'block',
    marginBottom: '6px',
    fontSize: '14px',
    color: '#555',
  },
  input: {
    width: '100%',
    padding: '10px',
    border: '1px solid #ddd',
    borderRadius: '4px',
    fontSize: '15px',
    boxSizing: 'border-box',
  },
  button: {
    width: '100%',
    padding: '12px',
    marginTop: '10px', // 與上方欄位間距
    backgroundColor: '#28a745', // 綠色系按鈕
    color: 'white',
    border: 'none',
    borderRadius: '4px',
    fontSize: '16px',
    cursor: 'pointer',
    transition: 'background-color 0.2s',
  },
  buttonHover: {
    backgroundColor: '#218838',
  },
  error: {
    color: 'red',
    marginBottom: '15px',
    textAlign: 'center',
    fontSize: '14px',
  },
  success: {
    color: 'green',
    marginBottom: '15px',
    textAlign: 'center',
    fontSize: '14px',
  },
  linkText: {
    textAlign: 'center',
    marginTop: '20px',
    fontSize: '14px',
  },
  link: {
    color: '#007bff',
    textDecoration: 'none',
  }
};

const RegisterPage: React.FC = () => {
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [fullName, setFullName] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [isButtonHovered, setIsButtonHovered] = useState(false);

  const auth = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setSuccessMessage(null);

    if (!username || !password || !email) {
      setError('帳號、Email 和密碼為必填欄位。');
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
      username,
      email,
      password,
      full_name: fullName || undefined, // 如果為空則不傳遞
    };

    try {
      await auth.register(userData);
      setSuccessMessage('註冊成功！您現在可以前往登入頁面登入。');
      // 清空表單
      setUsername('');
      setEmail('');
      setFullName('');
      setPassword('');
      setConfirmPassword('');
      // 可以在幾秒後自動導向，或讓使用者點擊連結
      // setTimeout(() => navigate('/auth/login'), 3000);
    } catch (err) {
      const axiosError = err as AxiosError<{ detail?: any }>; // 後端可能回傳物件或字串
      if (axiosError.response && axiosError.response.data && axiosError.response.data.detail) {
        if (typeof axiosError.response.data.detail === 'string') {
            setError(axiosError.response.data.detail);
        } else if (Array.isArray(axiosError.response.data.detail)) {
            // 處理 FastAPI validation errors (通常是 Pydantic 錯誤陣列)
            const messages = axiosError.response.data.detail.map((e: any) => `${e.loc.join(' -> ')}: ${e.msg}`).join('\n');
            setError(messages || '註冊資訊有誤，請檢查。');
        } else {
            setError('註冊失敗，請稍後再試。');
        }
      } else {
        setError('註冊失敗，請稍後再試。');
      }
      console.error('Register page error:', err);
    }
  };

  return (
    <div style={styles.pageContainer}>
      <div style={styles.formContainer}>
        <h2 style={styles.title}>建立 Sortify 帳號</h2>
        <form onSubmit={handleSubmit}>
          {error && (
            <div style={styles.error}>
              {error.split('\n').map((line, index) => (
                <span key={index}>{line}<br/></span>
              ))}
            </div>
          )}
          {successMessage && <p style={styles.success}>{successMessage}</p>}
          
          <div style={styles.inputGroup}>
            <label htmlFor="username" style={styles.label}>帳號*:</label>
            <input
              type="text"
              id="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              style={styles.input}
              required
            />
          </div>

          <div style={styles.inputGroup}>
            <label htmlFor="email" style={styles.label}>Email*:</label>
            <input
              type="email"
              id="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              style={styles.input}
              required
            />
          </div>

          <div style={styles.inputGroup}>
            <label htmlFor="fullName" style={styles.label}>全名 (選填):</label>
            <input
              type="text"
              id="fullName"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              style={styles.input}
            />
          </div>

          <div style={styles.inputGroup}>
            <label htmlFor="password" style={styles.label}>密碼* (至少8位):</label>
            <input
              type="password"
              id="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              style={styles.input}
              required
              minLength={8}
            />
          </div>

          <div style={styles.inputGroup}>
            <label htmlFor="confirmPassword" style={styles.label}>確認密碼*:</label>
            <input
              type="password"
              id="confirmPassword"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              style={styles.input}
              required
              minLength={8}
            />
          </div>
          
          <button 
            type="submit" 
            style={isButtonHovered ? {...styles.button, ...styles.buttonHover} : styles.button}
            disabled={auth.isLoading}
            onMouseEnter={() => setIsButtonHovered(true)}
            onMouseLeave={() => setIsButtonHovered(false)}
          >
            {auth.isLoading ? '註冊中...' : '註冊'}
          </button>
        </form>
        <p style={styles.linkText}>
          已經有帳號了？ <a href="/auth/login" style={styles.link}>點此登入</a>
        </p>
      </div>
    </div>
  );
};

export default RegisterPage; 