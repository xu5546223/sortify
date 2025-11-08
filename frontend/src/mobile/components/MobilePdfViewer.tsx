/**
 * 手機端 PDF 查看器組件
 * 使用瀏覽器原生能力 + 手勢控制
 */
import React, { useState, useEffect } from 'react';
import { CloseOutlined, DownloadOutlined, ReloadOutlined } from '@ant-design/icons';
import { message } from 'antd';

interface MobilePdfViewerProps {
  pdfUrl: string;
  fileName: string;
  onClose: () => void;
}

const MobilePdfViewer: React.FC<MobilePdfViewerProps> = ({ pdfUrl, fileName, onClose }) => {
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [renderMethod, setRenderMethod] = useState<'iframe' | 'object' | 'embed'>('iframe');

  // 為 PDF URL 添加 cache-busting 和預覽參數
  const enhancedPdfUrl = React.useMemo(() => {
    const url = new URL(pdfUrl, window.location.origin);
    // 添加時間戳防止緩存
    url.searchParams.set('_t', Date.now().toString());
    // 明確指定這是預覽請求
    url.searchParams.set('preview', '1');
    return url.toString();
  }, [pdfUrl]);

  useEffect(() => {
    // 重置狀態
    setIsLoading(true);
    setLoadError(false);

    // 設置超時
    const timeout = setTimeout(() => {
      setIsLoading(false);
    }, 10000);

    return () => clearTimeout(timeout);
  }, [pdfUrl]);

  const handleIframeLoad = () => {
    setIsLoading(false);
    setLoadError(false);
  };

  const handleIframeError = () => {
    setIsLoading(false);
    setLoadError(true);
    message.error('PDF 載入失敗');
  };

  const handleDownload = () => {
    const link = document.createElement('a');
    link.href = pdfUrl;
    link.download = fileName;
    link.target = '_blank';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    message.success('開始下載');
  };

  const handleOpenNewTab = () => {
    window.open(pdfUrl, '_blank');
    message.info('已在新標籤頁中打開');
  };

  const handleRetry = () => {
    setIsLoading(true);
    setLoadError(false);
    
    // 嘗試切換渲染方法
    if (renderMethod === 'iframe') {
      setRenderMethod('object');
    } else if (renderMethod === 'object') {
      setRenderMethod('embed');
    } else {
      setRenderMethod('iframe');
    }
    
    // 強制重新載入
    const iframe = document.getElementById('pdf-iframe') as HTMLIFrameElement;
    const object = document.getElementById('pdf-object') as HTMLObjectElement;
    const embed = document.getElementById('pdf-embed') as HTMLEmbedElement;
    
    if (iframe) iframe.src = enhancedPdfUrl;
    if (object) object.data = enhancedPdfUrl;
    if (embed) embed.src = enhancedPdfUrl;
  };

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: '#f5f5f5',
        zIndex: 9999,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden'
      }}
    >
      {/* 頂部工具欄 */}
      <div
        style={{
          backgroundColor: '#ffffff',
          borderBottom: '1px solid #e8e8e8',
          padding: '12px 16px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexShrink: 0,
          boxShadow: '0 2px 8px rgba(0,0,0,0.06)'
        }}
      >
        <div style={{ 
          fontSize: '14px', 
          fontWeight: 500,
          flex: 1, 
          overflow: 'hidden', 
          textOverflow: 'ellipsis', 
          whiteSpace: 'nowrap',
          color: '#262626'
        }}>
          {fileName}
        </div>
        <div style={{ display: 'flex', gap: '12px', marginLeft: '12px' }}>
          {loadError && (
            <button
              onClick={handleRetry}
              style={{
                background: 'none',
                border: 'none',
                color: '#1890ff',
                fontSize: '18px',
                cursor: 'pointer',
                padding: '4px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
              }}
              title="重試"
            >
              <ReloadOutlined />
            </button>
          )}
          <button
            onClick={handleDownload}
            style={{
              background: 'none',
              border: 'none',
              color: '#1890ff',
              fontSize: '18px',
              cursor: 'pointer',
              padding: '4px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}
            title="下載"
          >
            <DownloadOutlined />
          </button>
          <button
            onClick={onClose}
            style={{
              background: 'none',
              border: 'none',
              color: '#8c8c8c',
              fontSize: '18px',
              cursor: 'pointer',
              padding: '4px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}
            title="關閉"
          >
            <CloseOutlined />
          </button>
        </div>
      </div>

      {/* PDF 內容區域 */}
      <div
        style={{
          flex: 1,
          position: 'relative',
          overflow: 'hidden',
          backgroundColor: '#525252'
        }}
      >
        {/* 載入中提示 */}
        {isLoading && !loadError && (
          <div
            style={{
              position: 'absolute',
              top: '50%',
              left: '50%',
              transform: 'translate(-50%, -50%)',
              textAlign: 'center',
              color: '#ffffff',
              zIndex: 10
            }}
          >
            <div style={{ fontSize: '32px', marginBottom: '16px' }}>📄</div>
            <div style={{ fontSize: '14px' }}>正在載入 PDF...</div>
          </div>
        )}

        {/* 載入錯誤提示 */}
        {loadError && (
          <div
            style={{
              position: 'absolute',
              top: '50%',
              left: '50%',
              transform: 'translate(-50%, -50%)',
              textAlign: 'center',
              color: '#ffffff',
              zIndex: 10,
              padding: '0 20px'
            }}
          >
            <div style={{ fontSize: '32px', marginBottom: '16px' }}>❌</div>
            <div style={{ fontSize: '14px', marginBottom: '8px' }}>PDF 載入失敗</div>
            <div style={{ fontSize: '12px', color: '#bfbfbf', marginBottom: '20px' }}>
              您的瀏覽器可能不支持直接預覽 PDF
            </div>
            <div style={{ 
              display: 'flex', 
              flexDirection: 'column', 
              gap: '12px',
              width: '100%',
              maxWidth: '300px'
            }}>
              <button
                onClick={handleOpenNewTab}
                style={{
                  backgroundColor: '#1890ff',
                  color: 'white',
                  border: 'none',
                  borderRadius: '6px',
                  padding: '12px 20px',
                  fontSize: '14px',
                  cursor: 'pointer',
                  width: '100%'
                }}
              >
                📱 使用系統 PDF 查看器打開
              </button>
              <button
                onClick={handleDownload}
                style={{
                  backgroundColor: '#52c41a',
                  color: 'white',
                  border: 'none',
                  borderRadius: '6px',
                  padding: '12px 20px',
                  fontSize: '14px',
                  cursor: 'pointer',
                  width: '100%'
                }}
              >
                ⬇️ 下載到本地查看
              </button>
              <div style={{ 
                fontSize: '11px', 
                color: '#999', 
                textAlign: 'center',
                marginTop: '8px'
              }}>
                💡 建議使用系統內建的 PDF 查看器<br/>
                可獲得最佳閱讀體驗
              </div>
            </div>
          </div>
        )}

        {/* PDF 渲染 - 使用多種方法 */}
        {!loadError && (
          <>
            {renderMethod === 'iframe' && (
              <iframe
                id="pdf-iframe"
                src={enhancedPdfUrl}
                title={fileName}
                onLoad={handleIframeLoad}
                onError={handleIframeError}
                style={{
                  width: '100%',
                  height: '100%',
                  border: 'none',
                  display: isLoading ? 'none' : 'block'
                }}
              />
            )}
            
            {renderMethod === 'object' && (
              <object
                id="pdf-object"
                data={enhancedPdfUrl}
                type="application/pdf"
                onLoad={handleIframeLoad}
                onError={handleIframeError}
                style={{
                  width: '100%',
                  height: '100%',
                  border: 'none',
                  display: isLoading ? 'none' : 'block'
                }}
              >
                <p style={{ padding: '20px', color: 'white', textAlign: 'center' }}>
                  您的瀏覽器不支持 PDF 預覽
                </p>
              </object>
            )}
            
            {renderMethod === 'embed' && (
              <embed
                id="pdf-embed"
                src={enhancedPdfUrl}
                type="application/pdf"
                onLoad={handleIframeLoad}
                onError={handleIframeError}
                style={{
                  width: '100%',
                  height: '100%',
                  border: 'none',
                  display: isLoading ? 'none' : 'block'
                }}
              />
            )}
          </>
        )}
      </div>

      {/* 底部提示 */}
      <div
        style={{
          backgroundColor: '#ffffff',
          borderTop: '1px solid #e8e8e8',
          padding: '10px 16px',
          textAlign: 'center',
          fontSize: '12px',
          color: '#8c8c8c',
          flexShrink: 0
        }}
      >
        {loadError ? (
          <span>❌ 當前渲染方式失敗，請點擊重試切換其他方式</span>
        ) : (
          <span>💡 提示：使用雙指手勢可以縮放 PDF</span>
        )}
      </div>
    </div>
  );
};

export default MobilePdfViewer;
