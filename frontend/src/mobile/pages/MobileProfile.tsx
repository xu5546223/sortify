import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { message, Modal } from 'antd';
import MobileHeader from '../components/MobileHeader';
import { useDeviceToken } from '../../hooks/useDeviceToken';
import { apiClient } from '../../services/apiClient';
import { 
  UserOutlined, 
  LogoutOutlined, 
  SettingOutlined, 
  InfoCircleOutlined,
  MobileOutlined,
  FileTextOutlined,
  ExclamationCircleOutlined
} from '@ant-design/icons';

interface UserInfo {
  username: string;
  email: string;
  full_name?: string;
}

const MobileProfile: React.FC = () => {
  const navigate = useNavigate();
  const { clearDeviceToken, getDeviceInfo } = useDeviceToken();
  const [userInfo, setUserInfo] = useState<UserInfo | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // 獲取用戶信息
  useEffect(() => {
    const fetchUserInfo = async () => {
      try {
        const response = await apiClient.get('/auth/users/me');
        setUserInfo(response.data);
        console.log('✅ 用戶信息獲取成功:', response.data);
      } catch (error) {
        console.error('❌ 獲取用戶信息失敗:', error);
      } finally {
        setIsLoading(false);
      }
    };

    fetchUserInfo();
  }, []);

  const handleLogout = async () => {
    const { deviceId } = getDeviceInfo();
    
    Modal.confirm({
      title: '確認登出',
      icon: <ExclamationCircleOutlined />,
      content: '登出後將解除此設備的綁定，需要重新掃描 QR Code 配對。電腦端的設備列表也會移除此設備。確定要繼續嗎？',
      okText: '確認登出',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          console.log('🔓 手機端登出：撤銷設備授權');
          
          // 1. 調用後端 API 撤銷設備（這樣電腦端會同步更新）
          if (deviceId) {
            try {
              await apiClient.delete(`/device-auth/devices/${deviceId}?permanent=true`);
              console.log('✅ 設備已從後端撤銷');
            } catch (error) {
              console.warn('⚠️ 後端撤銷失敗（可能已被撤銷）:', error);
              // 繼續執行本地清除
            }
          }
          
          // 2. 清除本地 token
          clearDeviceToken(false); // 保留 device UUID，下次配對仍視為同一設備
          
          message.success('登出成功，請重新配對');
          
          // 3. 延遲導航，確保 message 顯示
          setTimeout(() => {
            navigate('/mobile/scan', { replace: true });
          }, 500);
        } catch (error) {
          console.error('❌ 登出失敗:', error);
          message.error('登出失敗');
        }
      }
    });
  };

  // 顯示設備信息
  const showDeviceInfo = () => {
    const { deviceId, deviceUUID } = getDeviceInfo();
    
    Modal.info({
      title: '設備信息',
      content: (
        <div>
          <p><strong>設備 UUID：</strong></p>
          <p style={{ fontSize: '12px', wordBreak: 'break-all', color: '#666' }}>
            {deviceUUID || '未知'}
          </p>
          <p style={{ marginTop: '12px' }}><strong>設備 ID：</strong></p>
          <p style={{ fontSize: '12px', wordBreak: 'break-all', color: '#666' }}>
            {deviceId || '未知'}
          </p>
          <p style={{ marginTop: '12px', fontSize: '13px', color: '#999' }}>
            💡 此設備已與您的帳號綁定。登出後需要重新掃描 QR Code 配對。
          </p>
        </div>
      ),
      okText: '知道了'
    });
  };

  // 顯示個人資料
  const showPersonalInfo = () => {
    Modal.info({
      title: '個人資料',
      content: (
        <div>
          <p><strong>用戶名：</strong> {userInfo?.username || '未知'}</p>
          <p><strong>郵箱：</strong> {userInfo?.email || '未知'}</p>
          {userInfo?.full_name && <p><strong>全名：</strong> {userInfo.full_name}</p>}
          <p style={{ marginTop: '16px', fontSize: '13px', color: '#999' }}>
            💡 如需修改個人資料，請在電腦端進行操作。
          </p>
        </div>
      ),
      okText: '關閉'
    });
  };

  // 顯示設置
  const showSettings = () => {
    navigate('/mobile/settings');
  };

  // 顯示關於
  const showAbout = () => {
    Modal.info({
      title: 'Sortify AI Assistant',
      content: (
        <div>
          <p><strong>版本：</strong> v1.0.0</p>
          <p><strong>設備類型：</strong> PWA 移動端</p>
          <p style={{ marginTop: '12px', color: '#666', fontSize: '13px' }}>
            智能文件管理與問答助手
          </p>
          <p style={{ marginTop: '12px', fontSize: '13px', color: '#999' }}>
            🌟 支持拍照上傳、文件分析、智能問答等功能
          </p>
        </div>
      ),
      okText: '關閉'
    });
  };

  const menuItems = [
    {
      icon: <UserOutlined />,
      label: '個人資料',
      onClick: showPersonalInfo
    },
    {
      icon: <MobileOutlined />,
      label: '裝置管理',
      onClick: showDeviceInfo
    },
    {
      icon: <SettingOutlined />,
      label: '設置',
      onClick: showSettings
    },
    {
      icon: <InfoCircleOutlined />,
      label: '關於',
      onClick: showAbout
    }
  ];

  return (
    <>
      <MobileHeader title="我的" />
      
      <div style={{ padding: '16px' }}>
        <div className="mobile-card">
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '16px',
            paddingBottom: '16px',
            borderBottom: '1px solid #e0e0e0'
          }}>
            <div style={{
              width: '64px',
              height: '64px',
              borderRadius: '50%',
              background: 'linear-gradient(135deg, #29bf12 0%, #abff4fff 100%)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '32px',
              color: 'white'
            }}>
              {isLoading ? '...' : (userInfo?.username?.charAt(0).toUpperCase() || 'X')}
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: '18px', fontWeight: '600', marginBottom: '4px' }}>
                {isLoading ? '載入中...' : (userInfo?.full_name || userInfo?.username || '未知用戶')}
              </div>
              <div style={{ fontSize: '13px', color: '#666' }}>
                {isLoading ? '' : (userInfo?.email || '')}
              </div>
            </div>
          </div>

          <div style={{ marginTop: '16px' }}>
            {menuItems.map((item, index) => (
              <div
                key={index}
                onClick={item.onClick}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '16px',
                  padding: '16px 8px',
                  borderBottom: index < menuItems.length - 1 ? '1px solid #f0f0f0' : 'none',
                  cursor: 'pointer',
                  transition: 'background-color 0.2s'
                }}
                onTouchStart={(e) => {
                  (e.currentTarget as HTMLDivElement).style.backgroundColor = '#f5f5f5';
                }}
                onTouchEnd={(e) => {
                  (e.currentTarget as HTMLDivElement).style.backgroundColor = 'transparent';
                }}
              >
                <div style={{ fontSize: '20px', color: '#29bf12' }}>
                  {item.icon}
                </div>
                <div style={{ flex: 1, fontSize: '15px' }}>
                  {item.label}
                </div>
                <div style={{ fontSize: '16px', color: '#999' }}>
                  ›
                </div>
              </div>
            ))}
          </div>
        </div>

        <button
          onClick={handleLogout}
          className="mobile-btn mobile-btn-danger"
          style={{ marginTop: '24px' }}
        >
          <LogoutOutlined /> 登出
        </button>

        <div style={{ marginTop: '24px', textAlign: 'center', fontSize: '12px', color: '#999' }}>
          Sortify AI Assistant v1.0.0
        </div>
      </div>
    </>
  );
};

export default MobileProfile;

