import React, { useRef, useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { message } from 'antd';
import MobileHeader from '../components/MobileHeader';
import { CloseOutlined, SyncOutlined } from '@ant-design/icons';

const MobileCamera: React.FC = () => {
  const navigate = useNavigate();
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [facingMode, setFacingMode] = useState<'user' | 'environment'>('environment');
  const [isCapturing, setIsCapturing] = useState<boolean>(false);

  useEffect(() => {
    startCamera();

    return () => {
      stopCamera();
    };
  }, [facingMode]);

  const startCamera = async () => {
    try {
      // 設定高解析度約束，提升畫質
      const constraints: MediaStreamConstraints = {
        video: {
          facingMode: facingMode,
          width: { ideal: 1920, min: 1280 },
          height: { ideal: 1080, min: 720 },
          // 設定較高的幀率
          frameRate: { ideal: 30, min: 24 }
        },
        audio: false
      };

      const mediaStream = await navigator.mediaDevices.getUserMedia(constraints);

      if (videoRef.current) {
        videoRef.current.srcObject = mediaStream;
        setStream(mediaStream);

        // 記錄實際獲得的解析度
        const videoTrack = mediaStream.getVideoTracks()[0];
        const settings = videoTrack.getSettings();
        console.log('📷 相機設定:', {
          width: settings.width,
          height: settings.height,
          frameRate: settings.frameRate,
          facingMode: settings.facingMode
        });
      }
    } catch (error) {
      console.error('無法啟動相機:', error);
      message.error('無法啟動相機，請檢查權限設置');
    }
  };

  const stopCamera = () => {
    if (stream) {
      stream.getTracks().forEach(track => track.stop());
      setStream(null);
    }
  };

  const capturePhoto = () => {
    if (!videoRef.current || !canvasRef.current) return;

    setIsCapturing(true);

    const video = videoRef.current;
    const canvas = canvasRef.current;

    // 使用視頻的實際解析度
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;

    console.log('📸 拍照解析度:', canvas.width, 'x', canvas.height);

    const ctx = canvas.getContext('2d');
    if (ctx) {
      // 使用高品質渲染
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = 'high';
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

      // 使用 0.95 的品質來保留更多細節
      canvas.toBlob((blob) => {
        if (blob) {
          const file = new File([blob], `photo_${Date.now()}.jpg`, { type: 'image/jpeg' });

          console.log('📄 照片檔案大小:', (blob.size / 1024).toFixed(1), 'KB');

          // 停止相機
          stopCamera();

          // 導航到預覽頁面，傳遞文件
          navigate('/mobile/preview', { state: { file } });
        }
      }, 'image/jpeg', 0.95); // 提高畫質從 0.9 到 0.95
    }
  };

  const switchCamera = () => {
    setFacingMode(prev => prev === 'user' ? 'environment' : 'user');
  };

  return (
    <div style={{
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      backgroundColor: '#000',
      display: 'flex',
      flexDirection: 'column',
      overflow: 'hidden'
    }}>
      {/* 頂部控制欄 */}
      <div style={{
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        height: '56px',
        paddingTop: 'max(0px, env(safe-area-inset-top))',
        background: 'linear-gradient(180deg, rgba(0,0,0,0.5) 0%, transparent 100%)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 16px',
        zIndex: 1001,
        color: 'white'
      }}>
        <h1 style={{
          fontSize: '18px',
          fontWeight: 600,
          margin: 0,
          color: 'white'
        }}>
          拍照
        </h1>
        <CloseOutlined
          style={{
            fontSize: '24px',
            cursor: 'pointer',
            padding: '8px'
          }}
          onClick={() => {
            stopCamera();
            navigate('/mobile/home');
          }}
        />
      </div>

      {/* 相機預覽區域 */}
      <div style={{
        flex: 1,
        position: 'relative',
        width: '100%',
        height: '100%',
        overflow: 'hidden',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center'
      }}>
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            display: 'block'
          }}
        />

        <canvas ref={canvasRef} style={{ display: 'none' }} />

        {/* 底部控制欄 - 修復響應式設計 */}
        <div style={{
          position: 'absolute',
          bottom: 0,
          left: 0,
          right: 0,
          // 增加高度和底部 padding 以避開導航欄
          height: 'auto',
          minHeight: '160px',
          background: 'linear-gradient(0deg, rgba(0,0,0,0.7) 0%, rgba(0,0,0,0.3) 70%, transparent 100%)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '40px',
          // 增加底部 padding，確保不被導航欄擋住
          paddingTop: '20px',
          paddingBottom: 'calc(80px + max(20px, env(safe-area-inset-bottom)))',
          zIndex: 1001
        }}>
          {/* 切換鏡頭按鈕 */}
          <button
            onClick={switchCamera}
            style={{
              width: '56px',
              height: '56px',
              borderRadius: '50%',
              border: '2px solid rgba(255, 255, 255, 0.8)',
              backgroundColor: 'rgba(0, 0, 0, 0.3)',
              color: 'white',
              fontSize: '24px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: 'pointer',
              backdropFilter: 'blur(10px)',
              WebkitBackdropFilter: 'blur(10px)',
              transition: 'all 0.2s'
            }}
          >
            <SyncOutlined />
          </button>

          {/* 拍照按鈕 */}
          <button
            onClick={capturePhoto}
            disabled={isCapturing}
            style={{
              width: '80px',
              height: '80px',
              borderRadius: '50%',
              border: '4px solid white',
              backgroundColor: 'transparent',
              cursor: isCapturing ? 'not-allowed' : 'pointer',
              position: 'relative',
              transition: 'all 0.2s',
              opacity: isCapturing ? 0.5 : 1
            }}
          >
            <div style={{
              position: 'absolute',
              top: '50%',
              left: '50%',
              transform: 'translate(-50%, -50%)',
              width: '68px',
              height: '68px',
              borderRadius: '50%',
              backgroundColor: 'white',
              transition: 'all 0.1s'
            }} />
          </button>

          {/* 佔位符（保持對稱） */}
          <div style={{ width: '56px', height: '56px' }} />
        </div>
      </div>
    </div>
  );
};

export default MobileCamera;

