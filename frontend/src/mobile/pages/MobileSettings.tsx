import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { message, Modal, Switch } from 'antd';
import MobileHeader from '../components/MobileHeader';
import { 
  CloudSyncOutlined,
  BellOutlined,
  BgColorsOutlined,
  QuestionCircleOutlined,
  ExclamationCircleOutlined,
  CheckCircleOutlined
} from '@ant-design/icons';
import { forceUpdateApp, getCacheInfo } from '../../utils/pwaUtils';

// 定義設置項目類型
interface SettingItemButton {
  icon: React.ReactElement;
  label: string;
  description: string;
  onClick: () => void;
  isSwitch?: false;
}

interface SettingItemSwitch {
  icon: React.ReactElement;
  label: string;
  description: string;
  isSwitch: true;
  checked: boolean;
  onChange: (checked: boolean) => void;
}

type SettingItem = SettingItemButton | SettingItemSwitch;

interface SettingGroup {
  title: string;
  items: SettingItem[];
}

const MobileSettings: React.FC = () => {
  const navigate = useNavigate();
  const [notificationsEnabled, setNotificationsEnabled] = useState(
    localStorage.getItem('notifications_enabled') === 'true'
  );
  const [darkMode, setDarkMode] = useState(
    localStorage.getItem('dark_mode') === 'true'
  );
  const [autoSync, setAutoSync] = useState(
    localStorage.getItem('auto_sync') === 'true'
  );

  // 強制更新應用（清除緩存 + 注銷 Service Worker）
  const handleForceUpdate = async () => {
    Modal.confirm({
      title: '強制更新',
      icon: <ExclamationCircleOutlined />,
      content: (
        <div>
          <p>這將執行以下操作：</p>
          <ul style={{ paddingLeft: '20px', fontSize: '13px', color: '#666', marginTop: '8px' }}>
            <li>清除所有應用緩存</li>
            <li>注銷 Service Worker</li>
            <li>重新加載最新版本</li>
          </ul>
          <p style={{ marginTop: '12px', color: '#ff9914ff', fontSize: '13px' }}>
            ⚠️ 此操作會確保應用更新到最新版本
          </p>
        </div>
      ),
      okText: '確認更新',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          message.loading('正在更新應用...', 0);
          await forceUpdateApp();
        } catch (error) {
          message.destroy();
          console.error('❌ 更新失敗:', error);
          message.error('更新失敗');
        }
      }
    });
  };


  // 切換通知（即將推出）
  const handleToggleNotifications = (checked: boolean) => {
    if (checked) {
      Modal.info({
        title: '通知功能即將推出',
        content: (
          <div>
            <p>推送通知功能需要：</p>
            <ul style={{ paddingLeft: '20px', fontSize: '13px', color: '#666', marginTop: '8px' }}>
              <li>瀏覽器通知權限</li>
              <li>VAPID 密鑰配置</li>
              <li>Service Worker 推送事件</li>
              <li>後端推送 API</li>
            </ul>
            <p style={{ marginTop: '12px', color: '#999', fontSize: '13px' }}>
              此功能將在未來版本中推出，屆時您可以接收文件處理完成、問答回覆等通知。
            </p>
          </div>
        ),
        okText: '知道了'
      });
    }
    setNotificationsEnabled(checked);
    localStorage.setItem('notifications_enabled', String(checked));
  };

  // 切換暗黑模式（即將推出）
  const handleToggleDarkMode = (checked: boolean) => {
    setDarkMode(checked);
    localStorage.setItem('dark_mode', String(checked));
    message.info('暗黑模式功能將在未來版本中完全支持');
  };

  // 切換自動同步（即將推出）
  const handleToggleAutoSync = (checked: boolean) => {
    if (checked) {
      Modal.info({
        title: '自動同步功能即將推出',
        content: (
          <div>
            <p>自動同步功能需要：</p>
            <ul style={{ paddingLeft: '20px', fontSize: '13px', color: '#666', marginTop: '8px' }}>
              <li>Background Sync API</li>
              <li>Service Worker sync 事件</li>
              <li>離線數據暫存機制</li>
              <li>衝突解決策略</li>
            </ul>
            <p style={{ marginTop: '12px', color: '#999', fontSize: '13px' }}>
              此功能將在未來版本中推出，屆時應用會在後台自動同步您的文件和數據。
            </p>
          </div>
        ),
        okText: '知道了'
      });
    }
    setAutoSync(checked);
    localStorage.setItem('auto_sync', String(checked));
  };

  // 查看緩存信息
  const handleViewCacheInfo = async () => {
    try {
      const cacheInfo = await getCacheInfo();
      
      Modal.info({
        title: '緩存信息',
        content: (
          <div>
            <p><strong>緩存數量：</strong> {cacheInfo.cacheNames.length}</p>
            <p><strong>總資源數：</strong> {cacheInfo.totalSize}</p>
            <div style={{ marginTop: '12px', maxHeight: '300px', overflowY: 'auto' }}>
              {cacheInfo.cacheDetails.length > 0 ? (
                cacheInfo.cacheDetails.map((cache, index) => (
                  <div key={index} style={{ 
                    marginBottom: '12px', 
                    padding: '8px', 
                    background: '#f5f5f5', 
                    borderRadius: '4px' 
                  }}>
                    <p style={{ fontSize: '12px', fontWeight: 'bold', marginBottom: '4px', wordBreak: 'break-all' }}>
                      {cache.name}
                    </p>
                    <p style={{ fontSize: '11px', color: '#666' }}>
                      {cache.urls.length} 個資源
                    </p>
                  </div>
                ))
              ) : (
                <p style={{ fontSize: '13px', color: '#999', textAlign: 'center', padding: '20px' }}>
                  暫無緩存數據
                </p>
              )}
            </div>
          </div>
        ),
        okText: '關閉',
        width: 400
      });
    } catch (error) {
      console.error('❌ 獲取緩存信息失敗:', error);
      message.error('獲取緩存信息失敗');
    }
  };

  // 幫助與反饋
  const handleHelp = () => {
    Modal.info({
      title: '幫助與反饋',
      content: (
        <div>
          <p><strong>常見問題：</strong></p>
          <ul style={{ paddingLeft: '20px', fontSize: '13px', color: '#666' }}>
            <li>如何上傳文件？點擊首頁的「拍照上傳」或「選擇文件」</li>
            <li>如何查看文件？點擊底部導航的「文件」</li>
            <li>如何提問？點擊底部導航的「問答」</li>
            <li>如何登出？點擊「我的」頁面底部的「登出」按鈕</li>
          </ul>
          <p style={{ marginTop: '16px', fontSize: '13px', color: '#999' }}>
            📧 如有其他問題，請聯繫：xu5546223@gmail.com
          </p>
        </div>
      ),
      okText: '關閉'
    });
  };

  const settingGroups: SettingGroup[] = [
    {
      title: '應用管理',
      items: [
        {
          icon: <CheckCircleOutlined style={{ color: '#29bf12' }} />,
          label: '強制更新',
          description: '清除緩存並重新加載最新版本',
          onClick: handleForceUpdate
        },
        {
          icon: <CloudSyncOutlined style={{ color: '#08bdbdff' }} />,
          label: '查看緩存信息',
          description: '查看當前緩存詳情',
          onClick: handleViewCacheInfo
        }
      ]
    },
    {
      title: '功能設置',
      items: [
        {
          icon: <BellOutlined style={{ color: '#ff9914ff' }} />,
          label: '通知（即將推出）',
          description: '接收文件處理完成通知',
          isSwitch: true,
          checked: notificationsEnabled,
          onChange: handleToggleNotifications
        },
        {
          icon: <BgColorsOutlined style={{ color: '#abff4fff' }} />,
          label: '暗黑模式（即將推出）',
          description: '切換應用主題',
          isSwitch: true,
          checked: darkMode,
          onChange: handleToggleDarkMode
        },
        {
          icon: <CloudSyncOutlined style={{ color: '#08bdbdff' }} />,
          label: '自動同步（即將推出）',
          description: '自動同步文件和數據',
          isSwitch: true,
          checked: autoSync,
          onChange: handleToggleAutoSync
        }
      ]
    },
    {
      title: '幫助',
      items: [
        {
          icon: <QuestionCircleOutlined style={{ color: '#29bf12' }} />,
          label: '幫助與反饋',
          description: '查看使用說明和反饋問題',
          onClick: handleHelp
        }
      ]
    }
  ];

  return (
    <>
      <MobileHeader 
        title="設置" 
        showBack={true}
        onBack={() => navigate(-1)}
      />
      
      <div style={{ 
        padding: '16px',
        paddingBottom: 'max(80px, calc(80px + env(safe-area-inset-bottom)))',
        maxWidth: '100vw',
        overflowX: 'hidden'
      }}>
        {settingGroups.map((group, groupIndex) => (
          <div key={groupIndex} style={{ marginBottom: '24px' }}>
            <h3 style={{ 
              fontSize: '14px', 
              color: '#999', 
              marginBottom: '12px',
              paddingLeft: '8px',
              fontWeight: '600'
            }}>
              {group.title}
            </h3>
            
            <div className="mobile-card">
            {group.items.map((item, itemIndex) => {
              const isSwitch = item.isSwitch === true;
              return (
                <div
                  key={itemIndex}
                  onClick={isSwitch ? undefined : (item as SettingItemButton).onClick}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '16px',
                    padding: '16px 8px',
                    borderBottom: itemIndex < group.items.length - 1 ? '1px solid #f0f0f0' : 'none',
                    cursor: isSwitch ? 'default' : 'pointer',
                    transition: 'background-color 0.2s'
                  }}
                  onTouchStart={(e) => {
                    if (!isSwitch) {
                      (e.currentTarget as HTMLDivElement).style.backgroundColor = '#f5f5f5';
                    }
                  }}
                  onTouchEnd={(e) => {
                    if (!isSwitch) {
                      (e.currentTarget as HTMLDivElement).style.backgroundColor = 'transparent';
                    }
                  }}
                >
                  <div style={{ fontSize: '20px' }}>
                    {item.icon}
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: '15px', marginBottom: '4px' }}>
                      {item.label}
                    </div>
                    <div style={{ fontSize: '12px', color: '#999' }}>
                      {item.description}
                    </div>
                  </div>
                  {isSwitch && (
                    <Switch 
                      checked={(item as SettingItemSwitch).checked}
                      onChange={(item as SettingItemSwitch).onChange}
                      style={{ 
                        backgroundColor: (item as SettingItemSwitch).checked ? '#29bf12' : '#d9d9d9' 
                      }}
                    />
                  )}
                  {!isSwitch && (
                    <div style={{ fontSize: '16px', color: '#999' }}>
                      ›
                    </div>
                  )}
                </div>
              );
            })}
            </div>
          </div>
        ))}
      </div>
    </>
  );
};

export default MobileSettings;

