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
  const [currentTime, setCurrentTime] = useState<Date>(new Date());
  const [editingDeviceId, setEditingDeviceId] = useState<string | null>(null);
  const [editingDeviceName, setEditingDeviceName] = useState<string>('');

  useEffect(() => {
    fetchDevices();
    // 移除自動生成，改為用戶手動點擊
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

  const startEditingDevice = (device: MobileDevice) => {
    setEditingDeviceId(device.device_id);
    setEditingDeviceName(device.device_name);
  };

  const cancelEditing = () => {
    setEditingDeviceId(null);
    setEditingDeviceName('');
  };

  const saveDeviceName = async (deviceId: string) => {
    if (!editingDeviceName.trim()) {
      showPCMessage('裝置名稱不能為空', 'error');
      return;
    }

    try {
      showPCMessage('正在更新裝置名稱...', 'info');
      
      await apiClient.patch(`/device-auth/devices/${deviceId}`, {
        device_name: editingDeviceName.trim()
      });
      
      setDevices(devices.map(d => 
        d.device_id === deviceId 
          ? { ...d, device_name: editingDeviceName.trim() }
          : d
      ));
      
      showPCMessage('裝置名稱已更新', 'success');
      setEditingDeviceId(null);
      setEditingDeviceName('');
      
    } catch (error) {
      console.error('更新裝置名稱失敗:', error);
      showPCMessage('更新裝置名稱失敗', 'error');
    }
  };

  const formatDate = (dateString: string): string => {
    const date = new Date(dateString);
    return date.toLocaleString('zh-TW');
  };

  // 根據設備名稱判斷設備類型並返回對應圖標
  const getDeviceIcon = (deviceName: string): string => {
    const lowerName = deviceName.toLowerCase();
    
    // iPad 判斷
    if (lowerName.includes('ipad')) {
      return 'fas fa-tablet-alt'; // iPad 圖標
    }
    
    // iPhone 判斷
    if (lowerName.includes('iphone')) {
      return 'fab fa-apple'; // Apple 圖標
    }
    
    // Android 設備判斷
    if (lowerName.includes('android') || 
        lowerName.includes('samsung') || 
        lowerName.includes('xiaomi') || 
        lowerName.includes('huawei') || 
        lowerName.includes('oppo') || 
        lowerName.includes('vivo') || 
        lowerName.includes('pixel') ||
        lowerName.includes('oneplus') ||
        lowerName.includes('motorola') ||
        lowerName.includes('lg') ||
        lowerName.includes('sony')) {
      return 'fab fa-android'; // Android 圖標
    }
    
    // 默認使用通用手機圖標
    return 'fas fa-mobile-alt';
  };

  // 根據設備名稱判斷設備類型描述
  const getDeviceTypeLabel = (deviceName: string): string => {
    const lowerName = deviceName.toLowerCase();
    
    if (lowerName.includes('ipad')) {
      return 'Apple iPad';
    }
    
    if (lowerName.includes('iphone')) {
      return 'Apple iPhone';
    }
    
    if (lowerName.includes('android') || 
        lowerName.includes('samsung') || 
        lowerName.includes('xiaomi') || 
        lowerName.includes('huawei') || 
        lowerName.includes('oppo') || 
        lowerName.includes('vivo') || 
        lowerName.includes('pixel') ||
        lowerName.includes('oneplus') ||
        lowerName.includes('motorola') ||
        lowerName.includes('lg') ||
        lowerName.includes('sony')) {
      return 'Android 裝置';
    }
    
    return 'Sortify 手機版';
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
      setCurrentTime(now); // 更新當前時間以觸發重新渲染
      
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
      {/* 主內容區：QR Code + 說明 */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 mb-8">
        
        {/* 左側：QR Code 掃描區 (佔 5 份) */}
        <div className="lg:col-span-5">
          <div className="bg-neo-white border-3 border-neo-black shadow-neo-lg p-6 relative group h-full flex flex-col">
            {/* 裝飾釘子 */}
            <div className="absolute top-4 left-4 w-3 h-3 border-2 border-neo-black rounded-full bg-gray-300"></div>
            <div className="absolute top-4 right-4 w-3 h-3 border-2 border-neo-black rounded-full bg-gray-300"></div>

            <h2 className="font-display text-2xl font-bold uppercase text-center mb-1 text-neo-black">
              掃描以連接
            </h2>
            <p className="text-sm text-gray-500 font-bold text-center mb-6">
              使用手機上的 Sortify App
            </p>

            {qrData ? (
              <div className="flex-1 flex flex-col items-center justify-center">
                {/* QR Code 容器 */}
                <div className="relative border-3 border-neo-black p-6 bg-neo-white mb-6 group/qr cursor-pointer"
                     onClick={generateQRCode}>
                  <QRCodeSVG 
                    value={qrData} 
                    size={280}
                    level="L"
                    includeMargin={false}
                    bgColor="#FFFFFF"
                    fgColor="#000000"
                  />
                  
                  {/* Hover 刷新遮罩 */}
                  <div className="absolute inset-0 bg-black/10 opacity-0 group-hover/qr:opacity-100 transition-opacity flex items-center justify-center backdrop-blur-[2px]">
                    <div className="bg-neo-white border-2 border-neo-black shadow-neo-sm px-4 py-2 flex items-center gap-2 font-bold text-sm">
                      <i className="fas fa-sync-alt"></i>
                      刷新
                    </div>
                  </div>
                </div>

                {/* 倒數計時 */}
                <div className="flex items-center gap-2 bg-gray-100 border-2 border-neo-black px-4 py-2 rounded-full mb-4">
                  <i className="fas fa-clock text-lg"></i>
                  <span className="font-mono font-bold text-lg tracking-widest">{getTimeRemaining()}</span>
                </div>
                
                <div className="text-xs font-bold text-neo-warn flex items-center gap-1">
                  <i className="fas fa-exclamation-circle"></i>
                  5 分鐘後過期
                </div>
              </div>
            ) : (
              <div className="flex-1 flex flex-col items-center justify-center">
                <div className="w-48 h-48 mb-6 border-2 border-dashed border-gray-400 flex flex-col items-center justify-center text-gray-400">
                  <i className="fas fa-qrcode text-6xl mb-4"></i>
                  <p className="text-sm">點擊下方按鈕生成</p>
                </div>
                <button
                  onClick={generateQRCode}
                  disabled={isGenerating}
                  className="bg-neo-primary border-3 border-neo-black shadow-neo-md font-display font-bold uppercase px-6 py-3 hover:bg-neo-hover hover:shadow-neo-lg hover:-translate-x-1 hover:-translate-y-1 active:translate-x-1 active:translate-y-1 active:shadow-none transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                >
                  {isGenerating ? (
                    <><i className="fas fa-spinner fa-spin"></i>生成中...</>
                  ) : (
                    <><i className="fas fa-qrcode"></i>生成 QR 碼</>
                  )}
                </button>
              </div>
            )}
          </div>
        </div>

        {/* 右側：設置說明 (佔 7 份) */}
        <div className="lg:col-span-7 flex flex-col gap-6">
          <div className="bg-neo-white border-3 border-neo-black shadow-neo-lg p-6 md:p-8 flex-1">
            <h3 className="font-display text-xl font-bold uppercase mb-6 border-b-2 border-neo-black pb-2 inline-block">
              設置指引
            </h3>
            
            <div className="space-y-6">
              {/* 步驟 1 */}
              <div className="flex items-start gap-4">
                <div className="w-8 h-8 border-2 border-neo-black rounded-full bg-neo-hover flex items-center justify-center font-bold flex-shrink-0">
                  1
                </div>
                <div>
                  <h4 className="font-bold text-lg">打開 Sortify App</h4>
                  <p className="text-gray-600 text-sm font-medium mt-1">
                    啟動手機應用並點擊主頁上的 <span className="bg-neo-black text-neo-white px-1.5 py-0.5 text-xs font-bold">掃描</span> 按鈕。
                  </p>
                </div>
              </div>
              
              {/* 步驟 2 */}
              <div className="flex items-start gap-4">
                <div className="w-8 h-8 border-2 border-neo-black rounded-full bg-neo-hover flex items-center justify-center font-bold flex-shrink-0">
                  2
                </div>
                <div>
                  <h4 className="font-bold text-lg">對準鏡頭</h4>
                  <p className="text-gray-600 text-sm font-medium mt-1">
                    將 QR 碼對準在框架內，連接會自動完成。
                  </p>
                </div>
              </div>

              {/* 步驟 3 */}
              <div className="flex items-start gap-4">
                <div className="w-8 h-8 border-2 border-neo-black rounded-full bg-neo-primary flex items-center justify-center font-bold flex-shrink-0">
                  3
                </div>
                <div>
                  <h4 className="font-bold text-lg">開始上傳</h4>
                  <p className="text-gray-600 text-sm font-medium mt-1">
                    連接後，您可以立即將照片和文件傳送到此工作區。
                  </p>
                </div>
              </div>
            </div>

            {/* 提示框 */}
            <div className="mt-8 p-4 bg-neo-active border-2 border-neo-black text-neo-white relative">
              <i className="fas fa-info-circle absolute -top-3 -left-3 bg-neo-black text-neo-white p-1.5 border-2 border-neo-white text-xl"></i>
              <p className="text-sm font-bold ml-2">
                提示：裝置連接後可保持 30 天，除非手動撤銷，無需每次掃描。
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* 底部：已連接設備列表 */}
      <div className="mt-8">
        <h3 className="font-display text-xl font-bold uppercase mb-6 flex items-center gap-2">
          <i className="fas fa-plug text-neo-primary"></i>
          已連接裝置 ({devices.length})
        </h3>

        {isLoadingDevices ? (
          <div className="bg-neo-white border-3 border-neo-black shadow-neo-lg p-12 text-center">
            <i className="fas fa-spinner fa-spin text-4xl text-neo-primary"></i>
            <p className="mt-4 font-bold">載入裝置列表中...</p>
          </div>
        ) : devices.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {devices.map((device) => (
              <div key={device.id} className="bg-neo-white border-3 border-neo-black shadow-neo-lg p-5 flex flex-col relative overflow-hidden hover:shadow-neo-xl hover:-translate-x-1 hover:-translate-y-1 transition-all">
                {/* 頂部標籤 */}
                <div className="flex justify-between items-start mb-4">
                  <div className="w-12 h-12 bg-gray-100 border-2 border-neo-black flex items-center justify-center">
                    <i className={`${getDeviceIcon(device.device_name)} text-2xl text-neo-primary`}></i>
                  </div>
                  <span className="bg-neo-hover border-2 border-neo-black px-2 py-1 text-xs font-bold uppercase">
                    {device.is_active ? '線上' : '離線'}
                  </span>
                </div>
                
                {editingDeviceId === device.device_id ? (
                  <div className="flex items-center gap-2 mb-2">
                    <input
                      type="text"
                      value={editingDeviceName}
                      onChange={(e) => setEditingDeviceName(e.target.value)}
                      className="flex-1 px-2 py-1 border-2 border-neo-black font-bold text-sm focus:outline-none focus:shadow-neo-sm"
                      autoFocus
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          saveDeviceName(device.device_id);
                        } else if (e.key === 'Escape') {
                          cancelEditing();
                        }
                      }}
                    />
                    <button
                      onClick={() => saveDeviceName(device.device_id)}
                      className="p-1.5 bg-neo-primary border-2 border-neo-black hover:bg-neo-hover transition-colors"
                      title="保存"
                    >
                      <i className="fas fa-check text-sm"></i>
                    </button>
                    <button
                      onClick={cancelEditing}
                      className="p-1.5 bg-gray-300 border-2 border-neo-black hover:bg-gray-400 transition-colors"
                      title="取消"
                    >
                      <i className="fas fa-times text-sm"></i>
                    </button>
                  </div>
                ) : (
                  <div className="flex items-center gap-2 mb-1">
                    <h4 className="font-bold text-lg">{device.device_name}</h4>
                    <button
                      onClick={() => startEditingDevice(device)}
                      className="p-1 hover:bg-gray-100 rounded transition-colors group"
                      title="編輯裝置名稱"
                    >
                      <i className="fas fa-pencil-alt text-xs text-gray-400 group-hover:text-neo-primary"></i>
                    </button>
                  </div>
                )}
                <p className="font-mono text-xs text-gray-500 mt-1">{getDeviceTypeLabel(device.device_name)}</p>

                <div className="my-4 border-t-2 border-dashed border-gray-300"></div>

                <div className="space-y-2 text-sm font-medium">
                  <div className="flex justify-between">
                    <span className="text-gray-500">配對時間：</span>
                    <span className="font-mono font-bold text-xs">{formatDate(device.created_at)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">最後使用：</span>
                    <span className="font-mono font-bold text-xs">{formatDate(device.last_used)}</span>
                  </div>
                </div>

                <div className="mt-6">
                  <button
                    onClick={() => revokeDevice(device.device_id)}
                    className="w-full bg-neo-error border-2 border-neo-black shadow-neo-sm text-neo-white font-bold uppercase px-4 py-2 hover:shadow-neo-md hover:-translate-x-1 hover:-translate-y-1 active:translate-x-1 active:translate-y-1 active:shadow-none transition-all flex items-center justify-center gap-2"
                  >
                    <i className="fas fa-times-circle"></i>
                    撤銷授權
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="bg-neo-white border-3 border-neo-black shadow-neo-lg p-12 text-center">
            <div className="inline-flex items-center justify-center w-16 h-16 border-2 border-neo-black bg-gray-100 mb-4">
              <i className="fas fa-mobile-alt text-3xl text-gray-400"></i>
            </div>
            <p className="font-bold text-gray-600">尚未連線任何手機裝置</p>
            <p className="text-sm text-gray-500 mt-1">使用上方的 QR Code 開始配對您的手機</p>
          </div>
        )}
      </div>

    </>
  );
};

export default MobileConnectionCard;

