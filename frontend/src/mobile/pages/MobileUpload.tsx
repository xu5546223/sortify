import React, { useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { message } from 'antd';
import MobileHeader from '../components/MobileHeader';
import { FileTextOutlined, FilePdfOutlined, FileWordOutlined, FileExcelOutlined, FileImageOutlined } from '@ant-design/icons';

const MobileUpload: React.FC = () => {
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files || files.length === 0) return;

    const file = files[0];
    
    // 檢查文件大小（限制 50MB）
    const maxSize = 50 * 1024 * 1024;
    if (file.size > maxSize) {
      message.error('文件大小不能超過 50MB');
      return;
    }

    // 導航到預覽頁面
    navigate('/mobile/preview', { state: { file } });
  };

  const supportedFormats = [
    {
      icon: <FilePdfOutlined />,
      name: 'PDF',
      color: '#f21b3fff',
      accept: 'application/pdf'
    },
    {
      icon: <FileWordOutlined />,
      name: 'Word',
      color: '#08bdbdff',
      accept: '.doc,.docx,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    },
    {
      icon: <FileExcelOutlined />,
      name: 'Excel',
      color: '#29bf12',
      accept: '.xls,.xlsx,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    },
    {
      icon: <FileImageOutlined />,
      name: '圖片',
      color: '#ff9914ff',
      accept: 'image/*'
    },
    {
      icon: <FileTextOutlined />,
      name: '文字',
      color: '#abff4fff',
      accept: '.txt,text/plain'
    }
  ];

  return (
    <>
      <MobileHeader title="選擇文件" showBack />
      
      <div style={{ padding: '16px' }}>
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.doc,.docx,.xls,.xlsx,.txt,image/*"
          onChange={handleFileSelect}
          style={{ display: 'none' }}
        />

        <div className="mobile-card">
          <h3 className="mobile-card-title">支援的格式</h3>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(3, 1fr)',
            gap: '12px',
            marginTop: '16px'
          }}>
            {supportedFormats.map((format, index) => (
              <div
                key={index}
                onClick={() => {
                  if (fileInputRef.current) {
                    fileInputRef.current.accept = format.accept;
                    fileInputRef.current.click();
                  }
                }}
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '16px 8px',
                  borderRadius: '12px',
                  backgroundColor: '#f8f9fa',
                  cursor: 'pointer',
                  transition: 'all 0.2s'
                }}
                onTouchStart={(e) => {
                  (e.currentTarget as HTMLDivElement).style.transform = 'scale(0.95)';
                }}
                onTouchEnd={(e) => {
                  (e.currentTarget as HTMLDivElement).style.transform = 'scale(1)';
                }}
              >
                <div style={{
                  fontSize: '32px',
                  color: format.color
                }}>
                  {format.icon}
                </div>
                <span style={{ fontSize: '12px', fontWeight: '500' }}>
                  {format.name}
                </span>
              </div>
            ))}
          </div>
        </div>

        <button
          onClick={() => fileInputRef.current?.click()}
          className="mobile-btn mobile-btn-primary mobile-btn-lg"
          style={{ marginTop: '16px' }}
        >
          <FileTextOutlined /> 瀏覽文件
        </button>

        <div className="mobile-card" style={{ marginTop: '16px' }}>
          <h4 style={{ fontSize: '14px', fontWeight: '600', margin: '0 0 8px 0' }}>
            📝 注意事項
          </h4>
          <ul style={{ fontSize: '13px', color: '#666', paddingLeft: '20px', margin: 0 }}>
            <li>單個文件大小不超過 50MB</li>
            <li>支援多種文件格式</li>
            <li>上傳後將自動進行智能分析</li>
            <li>分析結果可在「文件」頁面查看</li>
          </ul>
        </div>
      </div>
    </>
  );
};

export default MobileUpload;

