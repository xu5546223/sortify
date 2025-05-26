import React, { useState } from 'react';
import { updatePassword } from '../../services/authApi';
import { PasswordUpdateInRequest } from '../../services/authApi';
import { Link, useNavigate } from 'react-router-dom';

const styles: { [key: string]: React.CSSProperties } = {
  pageContainer: {
    padding: '30px',
    maxWidth: '500px',
    margin: '40px auto',
    fontFamily: 'Arial, sans-serif',
    border: '1px solid #ddd',
    borderRadius: '8px',
    boxShadow: '0 4px 8px rgba(0,0,0,0.1)',
  },
  title: {
    fontSize: '22px',
    color: '#333',
    marginBottom: '25px',
    textAlign: 'center',
  },
  form: {
    display: 'flex',
    flexDirection: 'column',
    gap: '18px',
  },
  inputGroup: {
    display: 'flex',
    flexDirection: 'column',
  },
  label: {
    marginBottom: '6px',
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
    backgroundColor: '#28a745', // Green color for update
    border: 'none',
    borderRadius: '5px',
    cursor: 'pointer',
    transition: 'background-color 0.3s',
    marginTop: '10px',
  },
  message: {
    padding: '12px',
    borderRadius: '4px',
    marginBottom: '20px',
    textAlign: 'center',
    fontSize: '15px',
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
    marginBottom: '25px',
    color: '#007bff',
    textDecoration: 'none',
    fontSize: '15px',
  }
};

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
    <div style={styles.pageContainer}>
      <Link to="/profile" style={styles.backLink}>&larr; 返回個人資料</Link>
      <h1 style={styles.title}>更改密碼</h1>

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
          <label htmlFor="currentPassword" style={styles.label}>目前密碼</label>
          <input 
            type="password" 
            id="currentPassword" 
            value={currentPassword} 
            onChange={(e) => setCurrentPassword(e.target.value)} 
            required 
            style={styles.input}
          />
        </div>
        <div style={styles.inputGroup}>
          <label htmlFor="newPassword" style={styles.label}>新密碼 (至少8個字符)</label>
          <input 
            type="password" 
            id="newPassword" 
            value={newPassword} 
            onChange={(e) => setNewPassword(e.target.value)} 
            required 
            minLength={8}
            style={styles.input}
          />
        </div>
        <div style={styles.inputGroup}>
          <label htmlFor="confirmNewPassword" style={styles.label}>確認新密碼</label>
          <input 
            type="password" 
            id="confirmNewPassword" 
            value={confirmNewPassword} 
            onChange={(e) => setConfirmNewPassword(e.target.value)} 
            required 
            minLength={8}
            style={styles.input}
          />
        </div>
        <button 
          type="submit" 
          disabled={isLoading} 
          style={styles.button}
          onMouseOver={(e) => !isLoading && (e.currentTarget.style.backgroundColor = '#218838')}
          onMouseOut={(e) => !isLoading && (e.currentTarget.style.backgroundColor = '#28a745')}
        >
          {isLoading ? '更新中...' : '更新密碼'}
        </button>
      </form>
    </div>
  );
};

export default PasswordUpdatePage; 