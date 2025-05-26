import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { updateCurrentUser } from '../services/authApi'; // 直接使用 authApi
import { UserUpdateRequest } from '../services/authApi';
import { Link, useNavigate } from 'react-router-dom';

const styles: { [key: string]: React.CSSProperties } = {
  pageContainer: {
    padding: '30px',
    maxWidth: '600px',
    margin: '0 auto',
    fontFamily: 'Arial, sans-serif',
  },
  title: {
    fontSize: '24px',
    color: '#333',
    marginBottom: '20px',
    textAlign: 'center',
  },
  form: {
    display: 'flex',
    flexDirection: 'column',
    gap: '15px',
  },
  inputGroup: {
    display: 'flex',
    flexDirection: 'column',
  },
  label: {
    marginBottom: '5px',
    color: '#555',
    fontSize: '14px',
  },
  input: {
    padding: '10px',
    border: '1px solid #ccc',
    borderRadius: '4px',
    fontSize: '16px',
  },
  button: {
    padding: '12px 20px',
    fontSize: '16px',
    color: 'white',
    backgroundColor: '#007bff',
    border: 'none',
    borderRadius: '5px',
    cursor: 'pointer',
    transition: 'background-color 0.3s',
    marginTop: '10px',
  },
  linkButton: {
    padding: '10px 15px',
    fontSize: '15px',
    color: 'white',
    backgroundColor: '#6c757d',
    border: 'none',
    borderRadius: '5px',
    cursor: 'pointer',
    textDecoration: 'none',
    textAlign: 'center',
    display: 'inline-block',
    marginTop: '20px',
    transition: 'background-color 0.3s',
  },
  message: {
    padding: '10px',
    borderRadius: '4px',
    marginBottom: '15px',
    textAlign: 'center',
  },
  successMessage: {
    backgroundColor: '#d4edda',
    color: '#155724',
  },
  errorMessage: {
    backgroundColor: '#f8d7da',
    color: '#721c24',
  },
  backLink: {
    display: 'inline-block',
    marginBottom: '20px',
    color: '#007bff',
    textDecoration: 'none',
  }
};

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
    return <p>載入使用者資訊...</p>;
  }

  return (
    <div style={styles.pageContainer}>
      <Link to="/dashboard" style={styles.backLink}>&larr; 返回儀表板</Link>
      <h1 style={styles.title}>管理個人資料</h1>

      {successMessage && (
        <div style={{...styles.message, ...styles.successMessage}}>
          {successMessage}
        </div>
      )}
      {errorMessage && (
        <div style={{...styles.message, ...styles.errorMessage}}>
          {errorMessage}
        </div>
      )}

      <form onSubmit={handleSubmit} style={styles.form}>
        <div style={styles.inputGroup}>
          <label htmlFor="username" style={styles.label}>使用者名稱 (無法更改)</label>
          <input 
            type="text" 
            id="username" 
            value={currentUser.username} 
            readOnly 
            style={{...styles.input, backgroundColor: '#e9ecef'}}
          />
        </div>
        <div style={styles.inputGroup}>
          <label htmlFor="email" style={styles.label}>Email</label>
          <input 
            type="email" 
            id="email" 
            value={email} 
            onChange={(e) => setEmail(e.target.value)} 
            style={styles.input}
          />
        </div>
        <div style={styles.inputGroup}>
          <label htmlFor="fullName" style={styles.label}>全名</label>
          <input 
            type="text" 
            id="fullName" 
            value={fullName} 
            onChange={(e) => setFullName(e.target.value)} 
            style={styles.input}
          />
        </div>
        <button 
          type="submit" 
          disabled={isLoading} 
          style={styles.button}
          onMouseOver={(e) => !isLoading && (e.currentTarget.style.backgroundColor = '#0056b3')}
          onMouseOut={(e) => !isLoading && (e.currentTarget.style.backgroundColor = '#007bff')}
        >
          {isLoading ? '更新中...' : '儲存變更'}
        </button>
      </form>
      <Link 
        to="/profile/change-password" 
        style={styles.linkButton}
        onMouseOver={(e) => (e.currentTarget.style.backgroundColor = '#5a6268')}
        onMouseOut={(e) => (e.currentTarget.style.backgroundColor = '#6c757d')}
      >
        更改密碼
      </Link>
    </div>
  );
};

export default UserProfilePage; 