import React, { useState, useEffect, useCallback } from 'react';
import apiClient, { 
  // ConnectionInfo, // Removed unused type
  TunnelStatus,
  ConnectedUser as ApiConnectedUser,
  ConnectionAPI
} from '../services/api';

import { PageHeader, Card, Button } from '../components';

interface ConnectionPageProps {
  showPCMessage: (message: string, type?: 'success' | 'error' | 'info') => void;
}

const ConnectionPage: React.FC<ConnectionPageProps> = ({ showPCMessage }) => {
  const [qrCode, setQrCode] = useState<string>('');
  const [connectionCode, setConnectionCode] = useState<string>('------');
  const [tunnelStatus, setTunnelStatus] = useState<TunnelStatus>('disconnected');
  const [connectedUsers, setConnectedUsers] = useState<ApiConnectedUser[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [disconnectingUser, setDisconnectingUser] = useState<string | null>(null);

  const fetchAllConnectionData = useCallback(async (isInitialLoad = false) => {
    if (isInitialLoad) setIsLoading(true);
    showPCMessage('正在獲取連線資訊...', 'info');
    try {
      const [info, status, users] = await Promise.all([
        ConnectionAPI.getConnectionInfo(),
        ConnectionAPI.getTunnelStatus(),
        ConnectionAPI.getConnectedUsersList(),
      ]);
      setQrCode(info.qrCode);
      setConnectionCode(info.connectionCode);
      setTunnelStatus(status);
      setConnectedUsers(users);
      showPCMessage('連線資訊已更新。', 'success');
    } catch (error) {
      console.error("Failed to fetch connection data:", error);
      showPCMessage('獲取連線資訊失敗。', 'error');
      // Set defaults or error states
      setQrCode(''); // Clear QR on error to show placeholder
      setConnectionCode('ERROR!');
      setTunnelStatus('error');
    }
    if (isInitialLoad) setIsLoading(false);
  }, [showPCMessage]);

  useEffect(() => {
    fetchAllConnectionData(true);
  }, [fetchAllConnectionData]);

  const handleDisconnectUser = async (userId: string) => {
    setDisconnectingUser(userId);
    showPCMessage(`正在中斷用戶 ${userId} 的連線...`, 'info');
    try {
      const result = await ConnectionAPI.disconnectUser(userId);
      if (result.success) {
        setConnectedUsers(prevUsers => prevUsers.filter(user => user.id !== userId));
        showPCMessage(`用戶 ${userId} 已成功斷線。`, 'success');
      } else {
        showPCMessage(`中斷用戶 ${userId} 連線失敗或用戶不存在。`, 'error');
      }
    } catch (error) {
      console.error(`Failed to disconnect user ${userId}:`, error);
      showPCMessage(`中斷用戶 ${userId} 連線時發生錯誤。`, 'error');
    }
    setDisconnectingUser(null);
  };

  const handleRefreshConnection = async () => {
    setIsRefreshing(true);
    showPCMessage('正在刷新連線資訊...', 'info');
    setQrCode(''); // Show loading placeholder for QR
    setConnectionCode('刷新中...');
    setTunnelStatus('connecting'); // Optimistic update
    try {
      const info = await ConnectionAPI.refreshConnectionInfo();
      setQrCode(info.qrCode);
      setConnectionCode(info.connectionCode);
      // Optionally, re-fetch tunnel status and users if refresh implies a full reset
      const status = await ConnectionAPI.getTunnelStatus();
      setTunnelStatus(status);
      showPCMessage('連線資訊已刷新。', 'success');
    } catch (error) {
      console.error("Failed to refresh connection info:", error);
      showPCMessage('刷新連線資訊失敗。', 'error');
      setConnectionCode('刷新失敗!');
      setTunnelStatus('error');
    }
    setIsRefreshing(false);
  };

  if (isLoading) {
    return (
      <div className="p-6 bg-gray-900 text-gray-100 min-h-screen flex flex-col items-center justify-center">
        <PageHeader title="電腦連線管理" className="text-teal-400 mb-8" />
        <Card className="bg-gray-800 w-full max-w-md text-center py-10">
          <i className="fas fa-spinner fa-spin text-4xl text-teal-400"></i>
          <p className="mt-4 text-xl">正在載入連線資訊...</p>
        </Card>
      </div>
    );
  }

  return (
    <div className="p-6 bg-gray-900 text-gray-100 min-h-screen">
      <PageHeader title="電腦連線管理" className="text-teal-400" />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
        <Card title="掃描 QR Code 或輸入連線碼" className="bg-gray-800" titleClassName="text-teal-300">
          <div className="flex flex-col items-center">
            {qrCode ? (
              <img src={qrCode} alt="QR Code" className="w-48 h-48 mb-4 border-2 border-teal-500 rounded" />
            ) : (
              <div className="w-48 h-48 mb-4 border-2 border-dashed border-gray-600 rounded flex items-center justify-center text-gray-500">
                {isRefreshing ? '刷新中...' : '載入中或無效'}
              </div>
            )}
            <p className="text-lg">或輸入連線碼：<span className="font-mono text-2xl text-yellow-400 tracking-wider">{connectionCode}</span></p>
            <Button 
              onClick={handleRefreshConnection}
              variant="primary"
              className="mt-4 bg-blue-600 hover:bg-blue-700 focus:ring-blue-500"
              disabled={isRefreshing}
            >
              {isRefreshing ? <><i className="fas fa-spinner fa-spin mr-2"></i>刷新中...</> : <><i className="fas fa-sync-alt mr-2"></i>刷新連線資訊</>}
            </Button>
          </div>
        </Card>

        <Card title="Tunnel 服務狀態" className="bg-gray-800" titleClassName="text-teal-300">
          <div className="flex items-center space-x-3">
            <span className={`px-3 py-1 rounded-full text-sm font-medium 
              ${tunnelStatus === 'connected' ? 'bg-green-500 text-green-50' : 
                tunnelStatus === 'connecting' ? 'bg-yellow-500 text-yellow-50' : 
                tunnelStatus === 'error' ? 'bg-red-500 text-red-50' : 
                'bg-gray-600 text-gray-200'}`}>
              {tunnelStatus === 'connected' && <><i className="fas fa-check-circle mr-1"></i>已連線</>}
              {tunnelStatus === 'connecting' && <><i className="fas fa-spinner fa-spin mr-1"></i>連線中...</>}
              {tunnelStatus === 'disconnected' && <><i className="fas fa-times-circle mr-1"></i>已斷線</>}
              {tunnelStatus === 'error' && <><i className="fas fa-exclamation-triangle mr-1"></i>連線錯誤</>}
            </span>
          </div>
          <p className="mt-3 text-gray-400 text-sm">
            {tunnelStatus === 'connected' && '您的電腦已成功透過安全通道連線，可以接收來自行動裝置的請求。'}
            {tunnelStatus === 'connecting' && '正在嘗試建立安全通道，請稍候...'}
            {tunnelStatus === 'disconnected' && 'Tunnel 服務目前未連線。請檢查您的網路設定或重試。'}
            {tunnelStatus === 'error' && '建立安全通道時發生錯誤。請檢查日誌以獲取更多資訊。'}
          </p>
        </Card>
      </div>

      <Card title="目前已連線的裝置" className="bg-gray-800" titleClassName="text-teal-300">
        {connectedUsers.length > 0 ? (
          <ul className="space-y-3">
            {connectedUsers.map(user => (
              <li key={user.id} className="flex items-center justify-between p-3 bg-gray-700 rounded-md hover:bg-gray-600 transition-colors duration-150">
                <div>
                  <p className="font-medium text-teal-400"><i className="fas fa-mobile-alt mr-2"></i>{user.name} ({user.device})</p>
                  <p className="text-xs text-gray-400">連線時間：{user.connectionTime}</p>
                </div>
                <Button 
                  onClick={() => handleDisconnectUser(user.id)}
                  variant="danger"
                  size="sm"
                  className="text-xs bg-red-600 hover:bg-red-700 focus:ring-red-500"
                  disabled={disconnectingUser === user.id}
                >
                  {disconnectingUser === user.id ? <i className="fas fa-spinner fa-spin mr-1"></i> : <i className="fas fa-power-off mr-1"></i>}
                  強制斷線
                </Button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-gray-500 italic">目前沒有任何裝置連線。</p>
        )}
      </Card>

    </div>
  );
};

export default ConnectionPage; 