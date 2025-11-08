import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Html5Qrcode, Html5QrcodeScannerState } from 'html5-qrcode';
import { message } from 'antd';
import MobileHeader from '../components/MobileHeader';
import { useDeviceToken } from '../../hooks/useDeviceToken';

// 擴展 Window 接口
declare global {
  interface Window {
    lastScanLog?: number;
  }
}

const MobileScan: React.FC = () => {
  const navigate = useNavigate();
  const { pairDevice } = useDeviceToken();
  const [isScanning, setIsScanning] = useState<boolean>(false);
  const [scannedData, setScannedData] = useState<string>('');
  const [error, setError] = useState<string>('');
  const scannerRef = useRef<Html5Qrcode | null>(null);
  const [cameraId, setCameraId] = useState<string>('');
  const [showManualInput, setShowManualInput] = useState<boolean>(false);
  const [manualQrData, setManualQrData] = useState<string>('');

  useEffect(() => {
    // 獲取可用的相機
    Html5Qrcode.getCameras().then(cameras => {
      if (cameras && cameras.length) {
        // 優先使用後置相機
        const backCamera = cameras.find(camera => 
          camera.label.toLowerCase().includes('back') || 
          camera.label.toLowerCase().includes('rear') ||
          camera.label.toLowerCase().includes('後')
        );
        setCameraId(backCamera?.id || cameras[0].id);
        console.log('找到相機:', cameras.length, '個');
        console.log('使用相機:', backCamera?.label || cameras[0].label);
      }
    }).catch(err => {
      console.error('無法獲取相機列表:', err);
      setError('無法訪問相機，請確保已授予相機權限');
    });

    return () => {
      stopScanning();
    };
  }, []);

  const startScanning = async () => {
    if (!cameraId) {
      message.error('未找到可用相機');
      return;
    }

    try {
      setError('');
      setIsScanning(true);
      
      const scanner = new Html5Qrcode('qr-reader');
      scannerRef.current = scanner;

      // 獲取視窗尺寸
      const viewportWidth = window.innerWidth;
      const viewportHeight = window.innerHeight;
      const scanBoxSize = Math.min(viewportWidth, viewportHeight) * 0.7;
      
      console.log('📐 掃描器配置:', {
        viewportWidth,
        viewportHeight,
        scanBoxSize,
        cameraId
      });

      await scanner.start(
        cameraId,
        {
          fps: 10,  // 降低 FPS 提高穩定性和識別率
          qrbox: {
            width: Math.floor(scanBoxSize),
            height: Math.floor(scanBoxSize)
          },
          aspectRatio: 1.0,
          // 使用寬鬆的掃描配置
          disableFlip: false,  // 允許翻轉掃描
          // 優化相機設置 - 提高解析度以掃描高密度 QR Code
          videoConstraints: {
            facingMode: { ideal: "environment" },  // 優先使用後置相機
            width: { ideal: 1920 },  // 增加解析度
            height: { ideal: 1080 }
          }
        },
        async (decodedText) => {
          console.log('✅ 掃描到 QR Code!');
          console.log('📦 原始數據:', decodedText);
          console.log('📏 數據長度:', decodedText.length, '字符');
          
          setScannedData(decodedText);
          
          // 停止掃描
          await stopScanning();
          
          try {
            // 解析 QR Code 數據
            console.log('🔍 開始解析 JSON...');
            const qrData = JSON.parse(decodedText);
            console.log('✅ JSON 解析成功:', qrData);
            
            if (qrData.type !== 'sortify_mobile_pairing') {
              message.error('無效的 QR Code 格式');
              setScannedData('');
              // 重新開始掃描
              setTimeout(() => startScanning(), 1000);
              return;
            }

            console.log('開始配對裝置...');
            // 配對裝置
            const success = await pairDevice(qrData.pairing_token);
            
            if (success) {
              message.success('配對成功！正在進入應用...');
              
              // 觸發 storage 事件通知其他組件
              window.dispatchEvent(new Event('storage'));
              window.dispatchEvent(new Event('pairing-status-changed'));
              
              console.log('✅ 配對成功，觸發事件並導航到首頁');
              
              // 延遲導航，確保 token 已保存和事件已處理
              setTimeout(() => {
                navigate('/mobile/home', { replace: true });
              }, 1500);
            } else {
              message.error('配對失敗，請重試');
              setScannedData('');
              setTimeout(() => startScanning(), 1000);
            }
            
          } catch (error) {
            console.error('掃描處理失敗:', error);
            message.error('處理 QR Code 失敗，請重試');
            setScannedData('');
            setTimeout(() => startScanning(), 1000);
          }
        },
        (errorMessage) => {
          // 掃描失敗的回調（正常，表示還沒掃到）
          // 每 5 秒顯示一次掃描狀態
          const now = Date.now();
          if (!window.lastScanLog || now - window.lastScanLog > 5000) {
            console.log('🔍 掃描中...持續尋找 QR Code');
            window.lastScanLog = now;
          }
        }
      );
      
      console.log('✅ 掃描器已成功啟動！');
      console.log('📷 相機視圖應該已顯示');
      console.log('🎯 請將 QR Code 對準掃描框中央');
      
      // 添加延遲日誌幫助用戶
      setTimeout(() => {
        if (isScanning) {
          console.log('💡 掃描提示：');
          console.log('   • 保持 QR Code 在掃描框內');
          console.log('   • 距離 20-30 公分');
          console.log('   • 確保光線充足');
          console.log('   • 避免手震');
        }
      }, 2000);
    } catch (err) {
      console.error('❌ 啟動掃描器失敗:', err);
      setError(`啟動相機失敗：${err instanceof Error ? err.message : '未知錯誤'}`);
      setIsScanning(false);
      message.error('無法啟動相機，請檢查權限設置');
    }
  };

  const stopScanning = async () => {
    if (scannerRef.current) {
      try {
        const state = scannerRef.current.getState();
        if (state === Html5QrcodeScannerState.SCANNING) {
          await scannerRef.current.stop();
          console.log('掃描器已停止');
        }
        scannerRef.current.clear();
      } catch (error) {
        console.error('停止掃描器失敗:', error);
      }
      scannerRef.current = null;
    }
    setIsScanning(false);
  };

  const handleManualInput = async () => {
    if (!manualQrData.trim()) {
      message.error('請輸入 QR Code 數據');
      return;
    }

    console.log('📝 手動輸入數據:', manualQrData);
    setScannedData(manualQrData);

    try {
      const qrData = JSON.parse(manualQrData);
      console.log('✅ JSON 解析成功:', qrData);

      if (qrData.type !== 'sortify_mobile_pairing') {
        message.error('無效的 QR Code 格式');
        setScannedData('');
        return;
      }

      console.log('開始配對裝置...');
      const success = await pairDevice(qrData.pairing_token);

      if (success) {
        message.success('配對成功！正在進入應用...');
        window.dispatchEvent(new Event('storage'));
        window.dispatchEvent(new Event('pairing-status-changed'));
        setTimeout(() => {
          navigate('/mobile/home', { replace: true });
        }, 1500);
      } else {
        message.error('配對失敗，請重試');
        setScannedData('');
      }
    } catch (error) {
      console.error('手動輸入處理失敗:', error);
      message.error('處理 QR Code 失敗，請檢查數據格式');
      setScannedData('');
    }
  };

  return (
    <>
      <MobileHeader 
        title="掃描 QR Code" 
        showBack 
        onBack={async () => {
          await stopScanning();
          navigate('/mobile/home');
        }}
      />
      
      <div style={{ padding: '16px' }}>
        <div className="mobile-card">
          <p style={{ fontSize: '14px', color: '#666', margin: '0 0 16px 0', textAlign: 'center' }}>
            {isScanning 
              ? '請將相機對準電腦屏幕上的 QR Code' 
              : '點擊下方按鈕開始掃描'}
          </p>
          
          {error && (
            <p style={{ fontSize: '13px', color: '#f21b3fff', textAlign: 'center', marginTop: '8px' }}>
              ⚠️ {error}
            </p>
          )}
        </div>

        <div 
          id="qr-reader" 
          style={{ 
            width: '100%',
            borderRadius: '12px',
            overflow: 'hidden',
            minHeight: isScanning ? '300px' : '0',
            transition: 'min-height 0.3s'
          }}
        />

        {!isScanning && !scannedData && (
          <button
            onClick={startScanning}
            className="mobile-btn mobile-btn-primary mobile-btn-lg"
            style={{ marginTop: '16px' }}
          >
            <i className="fas fa-camera" style={{ marginRight: '8px' }}></i>
            開始掃描
          </button>
        )}

        {isScanning && (
          <button
            onClick={stopScanning}
            className="mobile-btn mobile-btn-warning"
            style={{ marginTop: '16px' }}
          >
            <i className="fas fa-stop" style={{ marginRight: '8px' }}></i>
            停止掃描
          </button>
        )}

        {scannedData && (
          <div className="mobile-card" style={{ marginTop: '16px' }}>
            <div className="mobile-loading">
              <div className="mobile-loading-spinner" />
            </div>
            <p style={{ textAlign: 'center', marginTop: '16px', color: '#666' }}>
              正在配對裝置...
            </p>
          </div>
        )}

        <div className="mobile-card" style={{ marginTop: '16px' }}>
          <h4 style={{ fontSize: '14px', fontWeight: '600', margin: '0 0 8px 0' }}>
            📱 配對步驟
          </h4>
          <ol style={{ fontSize: '13px', color: '#666', paddingLeft: '20px', margin: 0 }}>
            <li>在電腦端打開「連線管理」頁面</li>
            <li>點擊「生成手機連線 QR Code」</li>
            <li>點擊「開始掃描」按鈕</li>
            <li>將手機相機對準電腦屏幕上的 QR Code</li>
            <li>保持手機穩定，直到聽到提示音或看到成功消息</li>
            <li>等待配對完成</li>
          </ol>
          
          <div style={{ 
            marginTop: '12px', 
            padding: '12px', 
            backgroundColor: '#fff3cd', 
            borderRadius: '8px',
            fontSize: '12px',
            color: '#856404'
          }}>
            <strong>💡 提示：</strong>
            <ul style={{ margin: '4px 0 0 0', paddingLeft: '20px' }}>
              <li>確保 QR Code 在掃描框內</li>
              <li>避免反光，調整角度</li>
              <li>保持適當距離（20-30cm）</li>
              <li>確保光線充足</li>
            </ul>
          </div>
        </div>

        {/* 手動輸入區域（測試用） */}
        <div className="mobile-card" style={{ marginTop: '16px' }}>
          <button
            onClick={() => setShowManualInput(!showManualInput)}
            className="mobile-btn mobile-btn-outline"
            style={{ width: '100%', marginBottom: showManualInput ? '16px' : '0' }}
          >
            <i className="fas fa-keyboard" style={{ marginRight: '8px' }}></i>
            {showManualInput ? '隱藏手動輸入' : '手動輸入 QR Code 數據（測試）'}
          </button>

          {showManualInput && (
            <>
              <textarea
                value={manualQrData}
                onChange={(e) => setManualQrData(e.target.value)}
                placeholder='請貼上 QR Code 數據（JSON 格式）'
                className="mobile-input"
                style={{
                  width: '100%',
                  minHeight: '120px',
                  fontFamily: 'monospace',
                  fontSize: '12px',
                  marginBottom: '12px'
                }}
              />
              <button
                onClick={handleManualInput}
                className="mobile-btn mobile-btn-primary"
                style={{ width: '100%' }}
                disabled={!manualQrData.trim()}
              >
                <i className="fas fa-check" style={{ marginRight: '8px' }}></i>
                提交配對
              </button>
            </>
          )}
        </div>
      </div>
    </>
  );
};

export default MobileScan;

