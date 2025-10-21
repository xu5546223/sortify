import React from 'react';
import { useAuth } from '../contexts/AuthContext';
import { Link } from 'react-router-dom';

// 簡易樣式
const styles: { [key: string]: React.CSSProperties } = {
  pageContainer: {
    padding: '30px',
    fontFamily: 'Arial, sans-serif',
  },
  header: {
    marginBottom: '30px',
  },
  title: {
    fontSize: '28px',
    color: '#333',
  },
  card: {
    backgroundColor: '#f9f9f9',
    padding: '20px',
    borderRadius: '8px',
    boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
    marginBottom: '20px',
  },
  cardTitle: {
    fontSize: '20px',
    color: '#444',
    marginBottom: '15px',
  },
  infoRow: {
    display: 'flex',
    justifyContent: 'space-between',
    padding: '8px 0',
    borderBottom: '1px solid #eee',
  },
  infoLabel: {
    fontWeight: 'bold',
    color: '#555',
  },
  infoValue: {
    color: '#777',
  },
  linkButton: {
    display: 'inline-block',
    padding: '10px 15px',
    fontSize: '15px',
    color: 'white',
    backgroundColor: '#007bff',
    border: 'none',
    borderRadius: '5px',
    cursor: 'pointer',
    textDecoration: 'none',
    transition: 'background-color 0.3s',
    marginRight: '10px',
  }
};

const DashboardPage: React.FC = () => {
  const { currentUser } = useAuth();

  if (!currentUser) {
    return <p>載入中...</p>; // 或者重新導向到登入頁面
  }

  return (
    <div style={styles.pageContainer}>
      <div style={styles.header}>
        <h1 style={styles.title}>儀表板</h1>
      </div>

      <div style={styles.card}>
        <h2 style={styles.cardTitle}>歡迎回來, {currentUser.username}!</h2>
        <p style={{color: '#666'}}>這裡是您的帳戶概覽和相關設定。</p>
      </div>

      <div style={styles.card}>
        <h2 style={styles.cardTitle}>帳戶資訊</h2>
        <div style={styles.infoRow}>
          <span style={styles.infoLabel}>使用者名稱:</span>
          <span style={styles.infoValue}>{currentUser.username}</span>
        </div>
        <div style={styles.infoRow}>
          <span style={styles.infoLabel}>Email:</span>
          <span style={styles.infoValue}>{currentUser.email || '未提供'}</span>
        </div>
        <div style={styles.infoRow}>
          <span style={styles.infoLabel}>全名:</span>
          <span style={styles.infoValue}>{currentUser.full_name || '未提供'}</span>
        </div>
        <div style={styles.infoRow}>
          <span style={styles.infoLabel}>帳號狀態:</span>
          <span style={styles.infoValue}>{currentUser.is_active ? '已啟用' : '未啟用'}</span>
        </div>
        <div style={styles.infoRow}>
          <span style={styles.infoLabel}>註冊時間:</span>
          <span style={styles.infoValue}>{new Date(currentUser.created_at).toLocaleDateString()} {new Date(currentUser.created_at).toLocaleTimeString()}</span>
        </div>
        <div style={{...styles.infoRow, borderBottom: 'none', paddingTop: '8px'}}>
          <span style={styles.infoLabel}>最後更新:</span>
          <span style={styles.infoValue}>{new Date(currentUser.updated_at).toLocaleDateString()} {new Date(currentUser.updated_at).toLocaleTimeString()}</span>
        </div>
      </div>

      <div style={styles.card}>
        <h2 style={styles.cardTitle}>帳戶設定</h2>
        <Link to="/profile" style={styles.linkButton}
          onMouseOver={(e) => (e.currentTarget.style.backgroundColor = '#0056b3')}
          onMouseOut={(e) => (e.currentTarget.style.backgroundColor = '#007bff')}
        >
          管理個人資料
        </Link>
         {/* 之後可以加上更改密碼等連結 */}
      </div>

    </div>
  );
};

export default DashboardPage; 