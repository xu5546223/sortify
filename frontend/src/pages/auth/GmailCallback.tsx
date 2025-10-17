import React, { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Spin, message, Result } from 'antd';
import { LoadingOutlined } from '@ant-design/icons';
import { apiClient } from '../../services/apiClient';

const GmailCallback: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const handleCallback = async () => {
      try {
        // 從 URL 查詢參數中提取 code 和 state
        const params = new URLSearchParams(location.search);
        const code = params.get('code');
        const state = params.get('state');
        const errorParam = params.get('error');

        if (errorParam) {
          throw new Error(`Gmail 授權失敗: ${errorParam}`);
        }

        if (!code) {
          throw new Error('未收到授權碼 (code)');
        }

        // 通知父窗口（如果是彈出窗口）授權已完成
        if (window.opener) {
          window.opener.postMessage(
            { type: 'gmail_auth_complete', success: true, code },
            window.location.origin
          );
          // 關閉彈出窗口
          window.close();
        } else {
          // 如果不是彈出窗口，重定向到主頁
          message.success('Gmail 授權成功！');
          setTimeout(() => {
            navigate('/');
          }, 2000);
        }
      } catch (err: any) {
        const errorMsg = err.message || 'OAuth 回調處理失敗';
        setError(errorMsg);
        
        // 通知父窗口出現錯誤
        if (window.opener) {
          window.opener.postMessage(
            { type: 'gmail_auth_error', error: errorMsg },
            window.location.origin
          );
        }
        
        message.error(errorMsg);
      } finally {
        setLoading(false);
      }
    };

    handleCallback();
  }, [location, navigate]);

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <div style={{ textAlign: 'center' }}>
          <Spin 
            indicator={<LoadingOutlined style={{ fontSize: 48 }} />} 
            tip="處理 Gmail 授權中..."
          />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <Result
          status="error"
          title="授權失敗"
          subTitle={error}
          extra={[
            <button 
              key="close"
              onClick={() => window.close()}
              style={{
                padding: '8px 16px',
                backgroundColor: '#1890ff',
                color: 'white',
                border: 'none',
                borderRadius: '4px',
                cursor: 'pointer'
              }}
            >
              關閉此窗口
            </button>
          ]}
        />
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
      <Result
        status="success"
        title="授權成功"
        subTitle="Gmail 授權已完成，窗口將自動關閉"
      />
    </div>
  );
};

export default GmailCallback;
