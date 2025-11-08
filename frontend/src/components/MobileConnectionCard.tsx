import React, { useState, useEffect } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import { Button, Card } from './index';
import { apiClient } from '../services/apiClient';

interface MobileDevice {
  id: string;
  device_id: string;
  device_name: string;
  created_at: string;
  last_used: string;
  is_active: boolean;
}

interface MobileConnectionCardProps {
  showPCMessage: (message: string, type?: 'success' | 'error' | 'info') => void;
}

const MobileConnectionCard: React.FC<MobileConnectionCardProps> = ({ showPCMessage }) => {
  const [qrData, setQrData] = useState<string>('');
  const [pairingToken, setPairingToken] = useState<string>('');
  const [expiresAt, setExpiresAt] = useState<Date | null>(null);
  const [devices, setDevices] = useState<MobileDevice[]>([]);
  const [isGenerating, setIsGenerating] = useState<boolean>(false);
  const [isLoadingDevices, setIsLoadingDevices] = useState<boolean>(true);

  useEffect(() => {
    fetchDevices();
  }, []);

  const fetchDevices = async () => {
    try {
      setIsLoadingDevices(true);
      const response = await apiClient.get('/device-auth/devices');
      setDevices(response.data.devices || []);
    } catch (error) {
      console.error('獲取裝置列表失敗:', error);
      showPCMessage('獲取裝置列表失敗', 'error');
    } finally {
      setIsLoadingDevices(false);
    }
  };

  const generateQRCode = async () => {
    try {
      setIsGenerating(true);
      showPCMessage('正在生成手機連線 QR Code...', 'info');
      
      const response = await apiClient.post('/device-auth/generate-qr');
      
      setQrData(response.data.qr_data);
      setPairingToken(response.data.pairing_token);
      setExpiresAt(new Date(response.data.expires_at));
      
      showPCMessage('QR Code 已生成，請使用手機掃描', 'success');
      
      // 5 分鐘後清除 QR Code
      setTimeout(() => {
        setQrData('');
        setPairingToken('');
        setExpiresAt(null);
        showPCMessage('QR Code 已過期，請重新生成', 'info');
      }, 5 * 60 * 1000);
      
    } catch (error) {
      console.error('生成 QR Code 失敗:', error);
      showPCMessage('生成 QR Code 失敗', 'error');
    } finally {
      setIsGenerating(false);
    }
  };

  const revokeDevice = async (deviceId: string) => {
    try {
      showPCMessage('正在撤銷裝置授權...', 'info');
      
      await apiClient.delete(`/device-auth/devices/${deviceId}`);
      
      setDevices(devices.filter(d => d.device_id !== deviceId));
      showPCMessage('裝置授權已撤銷', 'success');
      
    } catch (error) {
      console.error('撤銷裝置失敗:', error);
      showPCMessage('撤銷裝置失敗', 'error');
    }
  };

  const formatDate = (dateString: string): string => {
    const date = new Date(dateString);
    return date.toLocaleString('zh-TW');
  };

  const getTimeRemaining = (): string => {
    if (!expiresAt) return '';
    
    const now = new Date();
    const diff = expiresAt.getTime() - now.getTime();
    
    if (diff <= 0) return '已過期';
    
    const minutes = Math.floor(diff / 60000);
    const seconds = Math.floor((diff % 60000) / 1000);
    
    return `${minutes}:${seconds.toString().padStart(2, '0')}`;
  };

  // 每秒更新倒計時
  useEffect(() => {
    if (!expiresAt) return;
    
    const timer = setInterval(() => {
      const now = new Date();
      if (now >= expiresAt) {
        setQrData('');
        setPairingToken('');
        setExpiresAt(null);
      }
    }, 1000);
    
    return () => clearInterval(timer);
  }, [expiresAt]);

  return (
    <>
      <div className="card mb-6">
        <div className="flex flex-col md:flex-row gap-6">
          {/* QR Code 區域 */}
          <div className="flex-1 flex flex-col items-center justify-center">
            {qrData ? (
              <>
                <div className="bg-white p-6 rounded-xl mb-4 shadow-lg">
                  <QRCodeSVG 
                    value={qrData} 
                    size={320}
                    level="L"
                    includeMargin={true}
                    bgColor="#FFFFFF"
                    fgColor="#000000"
                  />
                </div>
                <div className="text-xs text-gray-500 mb-2">
                  <button
                    onClick={() => {
                      console.log('QR Code 數據:', qrData);
                      console.log('QR Code 長度:', qrData.length, '字符');
                      alert(`QR Code 數據長度: ${qrData.length} 字符\n請查看控制台獲取完整數據`);
                    }}
                    className="text-teal-400 hover:text-teal-300 underline"
                  >
                    查看 QR Code 數據
                  </button>
                </div>
                <p className="text-sm text-color-secondary text-center">
                  有效時間：<span className="text-warning-500 font-mono font-semibold">{getTimeRemaining()}</span>
                </p>
                <p className="text-xs text-color-tertiary text-center mt-2">
                  請使用 Sortify 手機掃描此 QR Code
                </p>
              </>
            ) : (
              <div className="w-full max-w-xs">
                <div className="w-full aspect-square mb-4 border-2 border-dashed border-gray-600 rounded-lg flex flex-col items-center justify-center text-gray-500">
                  <i className="fas fa-qrcode text-6xl mb-4"></i>
                  <p className="text-sm">點擊下方按鈕生成 QR Code</p>
                </div>
                <Button 
                  onClick={generateQRCode}
                  variant="primary"
                  className="w-full bg-green-600 hover:bg-green-700 focus:ring-green-500"
                  disabled={isGenerating}
                >
                  {isGenerating ? (
                    <><i className="fas fa-spinner fa-spin mr-2"></i>生成中...</>
                  ) : (
                    <><i className="fas fa-qrcode mr-2"></i>生成手機連線 QR Code</>
                  )}
                </Button>
              </div>
            )}
          </div>

          {/* 使用說明 */}
          <div className="flex-1">
            <h4 className="font-semibold text-color-primary mb-4 flex items-center gap-2">
              <i className="fas fa-list-ol text-primary-500"></i>
              配對步驟
            </h4>
            <ol className="space-y-3 text-sm text-color-secondary">
              <li className="flex items-start gap-3">
                <span className="inline-flex items-center justify-center w-7 h-7 bg-primary-500 text-white rounded-full text-sm font-semibold flex-shrink-0">
                  1
                </span>
                <span className="pt-0.5">點擊「生成手機連線 QR Code」按鈕</span>
              </li>
              <li className="flex items-start gap-3">
                <span className="inline-flex items-center justify-center w-7 h-7 bg-primary-500 text-white rounded-full text-sm font-semibold flex-shrink-0">
                  2
                </span>
                <span className="pt-0.5">打開 Sortify 手機網頁</span>
              </li>
              <li className="flex items-start gap-3">
                <span className="inline-flex items-center justify-center w-7 h-7 bg-primary-500 text-white rounded-full text-sm font-semibold flex-shrink-0">
                  3
                </span>
                <span className="pt-0.5">點擊「掃描連線」或首頁的掃描圖標</span>
              </li>
              <li className="flex items-start gap-3">
                <span className="inline-flex items-center justify-center w-7 h-7 bg-primary-500 text-white rounded-full text-sm font-semibold flex-shrink-0">
                  4
                </span>
                <span className="pt-0.5">對準電腦屏幕上的 QR Code 進行掃描</span>
              </li>
              <li className="flex items-start gap-3">
                <span className="inline-flex items-center justify-center w-7 h-7 bg-primary-500 text-white rounded-full text-sm font-semibold flex-shrink-0">
                  5
                </span>
                <span className="pt-0.5">等待配對完成，手機端即可開始使用</span>
              </li>
            </ol>
            <div className="mt-4 p-3 bg-warning-500/10 border border-warning-500/30 rounded-lg">
              <p className="text-xs text-warning-700 dark:text-warning-400">
                <i className="fas fa-exclamation-triangle mr-2"></i>
                <strong>注意：</strong>QR Code 有效期為 5 分鐘，過期後需要重新生成
              </p>
            </div>
          </div>
        </div>
      </div>

      <div className="card">
        <h3 className="section-title mb-6">
          <i className="fas fa-mobile-alt mr-2 text-success-500"></i>
          已連線的手機裝置
        </h3>
        {isLoadingDevices ? (
          <div className="text-center py-12">
            <i className="fas fa-spinner fa-spin text-4xl text-primary-500"></i>
            <p className="mt-4 text-color-secondary">載入裝置列表中...</p>
          </div>
        ) : devices.length > 0 ? (
          <div className="table-container">
            <table className="table-base">
              <thead>
                <tr className="table-header">
                  <th className="text-left py-4 px-4">裝置名稱</th>
                  <th className="text-left py-4 px-4">配對時間</th>
                  <th className="text-left py-4 px-4">最後使用</th>
                  <th className="text-left py-4 px-4">狀態</th>
                  <th className="text-center py-4 px-4">操作</th>
                </tr>
              </thead>
              <tbody>
                {devices.map((device) => (
                  <tr key={device.id} className="table-row">
                    <td className="table-cell">
                      <div className="flex items-center gap-3">
                        <i className="fas fa-mobile-alt text-primary-500 text-lg"></i>
                        <span className="font-medium text-color-primary">{device.device_name}</span>
                      </div>
                    </td>
                    <td className="table-cell text-sm text-color-secondary">
                      {formatDate(device.created_at)}
                    </td>
                    <td className="table-cell text-sm text-color-secondary">
                      {formatDate(device.last_used)}
                    </td>
                    <td className="table-cell">
                      <span className={`status-tag ${
                        device.is_active 
                          ? 'status-success' 
                          : 'status-error'
                      }`}>
                        {device.is_active ? '啟用中' : '已停用'}
                      </span>
                    </td>
                    <td className="table-cell text-center">
                      <Button
                        onClick={() => revokeDevice(device.device_id)}
                        variant="danger"
                        size="sm"
                      >
                        <i className="fas fa-ban mr-2"></i>
                        撤銷授權
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-center py-12">
            <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-surface-100 dark:bg-surface-700 mb-4">
              <i className="fas fa-mobile-alt text-3xl text-color-tertiary"></i>
            </div>
            <p className="text-color-secondary">尚未連線任何手機裝置</p>
            <p className="text-sm text-color-tertiary mt-1">使用上方的 QR Code 開始配對您的手機</p>
          </div>
        )}
      </div>
    </>
  );
};

export default MobileConnectionCard;

