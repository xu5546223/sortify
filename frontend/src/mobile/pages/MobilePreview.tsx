import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { message, Modal } from 'antd';
import MobileHeader from '../components/MobileHeader';
import { useAuth } from '../../contexts/AuthContext';
import { apiClient } from '../../services/apiClient';

interface LocationState {
  file: File;
}

const MobilePreview: React.FC = () => {
  const navigate = useNavigate();
  const { currentUser } = useAuth();
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string>('');
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [progress, setProgress] = useState<number>(0);
  const [hasAuth, setHasAuth] = useState<boolean>(false);

  // 檢查認證狀態
  useEffect(() => {
    const checkAuth = () => {
      const authToken = localStorage.getItem('authToken');
      const deviceToken = localStorage.getItem('sortify_device_token');
      const hasToken = !!(authToken || deviceToken);
      setHasAuth(hasToken);
      console.log('MobilePreview: 認證狀態檢查', { hasToken, hasCurrentUser: !!currentUser });
    };

    checkAuth();

    // 監聽認證狀態變化
    const handleAuthChange = () => {
      console.log('MobilePreview: 檢測到認證狀態變化');
      checkAuth();
    };

    window.addEventListener('auth-status-changed', handleAuthChange);
    window.addEventListener('pairing-status-changed', handleAuthChange);

    return () => {
      window.removeEventListener('auth-status-changed', handleAuthChange);
      window.removeEventListener('pairing-status-changed', handleAuthChange);
    };
  }, [currentUser]);

  useEffect(() => {
    const state = (window.history.state as any)?.usr as LocationState | undefined;
    
    if (state?.file) {
      setFile(state.file);
      
      // 生成預覽
      if (state.file.type.startsWith('image/')) {
        const reader = new FileReader();
        reader.onload = (e) => {
          setPreview(e.target?.result as string);
        };
        reader.readAsDataURL(state.file);
      }
    } else {
      message.error('沒有選擇文件');
      navigate('/mobile/home');
    }
  }, [navigate]);

  const handleUpload = async () => {
    if (!file) {
      message.error('沒有選擇文件');
      return;
    }

    if (!hasAuth) {
      message.error('請先登錄或配對設備');
      navigate('/mobile/scan');
      return;
    }

    setIsUploading(true);
    setProgress(0);

    try {
      const formData = new FormData();
      formData.append('file', file);

      // 模擬進度
      const progressInterval = setInterval(() => {
        setProgress(prev => {
          if (prev >= 90) {
            clearInterval(progressInterval);
            return 90;
          }
          return prev + 10;
        });
      }, 200);

      const response = await apiClient.post('/documents/', formData, {
        headers: {
          'Content-Type': 'multipart/form-data'
        }
      });

      clearInterval(progressInterval);
      setProgress(100);

      console.log('✅ 文件上傳成功:', response.data.id);

      // 🎯 後台觸發分析和向量化（不等待完成）
      apiClient.patch(`/documents/${response.data.id}`, {
        trigger_content_processing: true
      }).then(() => {
        console.log('✅ 後台分析已觸發');
      }).catch((error) => {
        console.error('❌ 觸發分析失敗:', error);
        // 不影響用户体验，只记录错误
      });

      // 立即顯示成功並給用戶選擇
      message.success('文件已上傳！正在後台處理中...', 3);
      
      // 顯示成功狀態並給用戶選擇
      setIsUploading(false);
      setProgress(0);
      
      // 彈出選擇框
      showUploadSuccessOptions();

    } catch (error) {
      console.error('上傳失敗:', error);
      message.error('上傳失敗，請重試');
      setIsUploading(false);
      setProgress(0);
    }
  };

  const showUploadSuccessOptions = () => {
    Modal.info({
      title: null,
      icon: null,
      closable: false,
      maskClosable: false,
      okButtonProps: { style: { display: 'none' } },
      content: (
        <div style={{ textAlign: 'center', padding: '20px 0' }}>
          <div style={{ fontSize: '48px', marginBottom: '16px' }}>
            ✅
          </div>
          <div style={{ fontSize: '18px', fontWeight: '600', marginBottom: '12px' }}>
            文件上傳成功！
          </div>
          <div style={{ fontSize: '14px', color: '#666', marginBottom: '24px', lineHeight: '1.6' }}>
            系統正在後台進行：
            <br />
            📝 AI 分析 → 🔍 向量化 → 📁 智能分類
          </div>
          <div style={{ display: 'flex', gap: '12px', justifyContent: 'center', marginTop: '24px' }}>
            <button
              onClick={() => {
                Modal.destroyAll();
                navigate('/mobile/home');
              }}
              className="mobile-btn mobile-btn-secondary"
              style={{ flex: 1, maxWidth: '140px' }}
            >
              繼續上傳
            </button>
            <button
              onClick={() => {
                Modal.destroyAll();
                navigate('/mobile/documents');
              }}
              className="mobile-btn mobile-btn-primary"
              style={{ flex: 1, maxWidth: '140px' }}
            >
              查看文件
            </button>
          </div>
        </div>
      ),
      width: 360,
      centered: true
    });
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(2)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  const getFileIcon = (type: string): string => {
    if (type.startsWith('image/')) return '🖼️';
    if (type === 'application/pdf') return '📕';
    if (type.includes('word')) return '📘';
    if (type.includes('excel') || type.includes('spreadsheet')) return '📗';
    if (type.includes('text')) return '📄';
    return '📁';
  };

  if (!file) return null;

  return (
    <>
      <MobileHeader 
        title="預覽文件" 
        showBack={!isUploading}
        onBack={() => navigate('/mobile/home')}
      />
      
      <div style={{ 
        padding: '16px',
        paddingBottom: 'max(16px, env(safe-area-inset-bottom))',
        maxWidth: '100vw',
        overflowX: 'hidden'
      }}>
        {preview ? (
          <div className="mobile-card">
            <img 
              src={preview} 
              alt="預覽" 
              style={{
                width: '100%',
                height: 'auto',
                maxHeight: 'min(400px, 60vh)',
                objectFit: 'contain',
                borderRadius: '8px',
                display: 'block'
              }}
            />
          </div>
        ) : (
          <div className="mobile-card">
            <div style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              padding: 'min(48px, 10vw) min(24px, 5vw)',
              fontSize: 'min(64px, 15vw)'
            }}>
              {getFileIcon(file.type)}
            </div>
          </div>
        )}

        <div className="mobile-card" style={{ marginTop: '16px' }}>
          <h3 className="mobile-card-title">文件信息</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '14px' }}>
              <span style={{ color: '#666' }}>文件名：</span>
              <span style={{ fontWeight: '500', maxWidth: '60%', textAlign: 'right', wordBreak: 'break-all' }}>
                {file.name}
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '14px' }}>
              <span style={{ color: '#666' }}>大小：</span>
              <span style={{ fontWeight: '500' }}>{formatFileSize(file.size)}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '14px' }}>
              <span style={{ color: '#666' }}>類型：</span>
              <span style={{ fontWeight: '500' }}>{file.type || '未知'}</span>
            </div>
          </div>
        </div>

        {isUploading && (
          <div className="mobile-card" style={{ marginTop: '16px' }}>
            <div className="mobile-progress">
              <div 
                className="mobile-progress-bar" 
                style={{ width: `${progress}%` }}
              />
            </div>
            <p style={{ textAlign: 'center', marginTop: '12px', fontSize: '14px', color: '#666' }}>
              上傳中... {progress}%
            </p>
          </div>
        )}

        <div style={{ marginTop: '24px', display: 'flex', gap: '12px' }}>
          <button
            onClick={() => navigate('/mobile/home')}
            className="mobile-btn mobile-btn-outline"
            disabled={isUploading}
            style={{ flex: 1 }}
          >
            取消
          </button>
          <button
            onClick={handleUpload}
            className="mobile-btn mobile-btn-warning"
            disabled={isUploading}
            style={{ flex: 2 }}
          >
            {isUploading ? '上傳中...' : '上傳並處理'}
          </button>
        </div>

        <div className="mobile-card" style={{ marginTop: '16px' }}>
          <h4 style={{ fontSize: '14px', fontWeight: '600', margin: '0 0 8px 0' }}>
            🤖 後台自動處理流程
          </h4>
          <ol style={{ fontSize: '13px', color: '#666', paddingLeft: '20px', margin: 0, lineHeight: '1.8' }}>
            <li>📤 上傳文件到服務器</li>
            <li>📝 AI 提取文字和關鍵信息</li>
            <li>🔍 自動向量化以支援智能問答</li>
            <li>📁 智能分類到相關類別（可選）</li>
          </ol>
          <div style={{ 
            marginTop: '12px', 
            padding: '8px 12px', 
            backgroundColor: '#f0f9ff', 
            borderRadius: '6px',
            fontSize: '12px',
            color: '#0066cc'
          }}>
            💡 提示：處理過程在後台進行，您可以繼續上傳其他文件
          </div>
        </div>
      </div>
    </>
  );
};

export default MobilePreview;

