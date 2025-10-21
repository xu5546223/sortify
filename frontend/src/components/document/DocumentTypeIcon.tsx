/**
 * 文檔類型圖標組件
 * 根據文件類型顯示對應的圖標
 */

import React from 'react';
import { FileOutlined } from '@ant-design/icons';

interface DocumentTypeIconProps {
  fileType?: string | null;
  fileName?: string;
  className?: string;
}

const DocumentTypeIcon: React.FC<DocumentTypeIconProps> = ({ 
  fileType, 
  fileName, 
  className = 'w-8 h-8' 
}) => {
  // 獲取文件類型圖標
  const getFileIcon = (): string | null => {
    if (!fileType && !fileName) {
      return null;
    }

    // 從 MIME type 判斷
    const mimeType = fileType?.toLowerCase() || '';
    
    // PDF
    if (mimeType === 'application/pdf' || fileName?.toLowerCase().endsWith('.pdf')) {
      return '/images/pdflogo.png';
    }
    
    // Word 文檔
    if (
      mimeType === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' ||
      mimeType === 'application/msword' ||
      fileName?.toLowerCase().endsWith('.docx') ||
      fileName?.toLowerCase().endsWith('.doc')
    ) {
      return '/images/wordlogo.png';
    }
    
    // Excel 文檔
    if (
      mimeType === 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' ||
      mimeType === 'application/vnd.ms-excel' ||
      fileName?.toLowerCase().endsWith('.xlsx') ||
      fileName?.toLowerCase().endsWith('.xls')
    ) {
      return '/images/excellogo.png';
    }
    
    // 圖片
    if (
      mimeType.startsWith('image/') ||
      fileName?.toLowerCase().match(/\.(jpg|jpeg|png|gif|bmp|webp|svg)$/)
    ) {
      return '/images/picturelogo.png';
    }
    
    // 文本文件
    if (
      mimeType === 'text/plain' ||
      fileName?.toLowerCase().endsWith('.txt')
    ) {
      return '/images/txtlogo.png';
    }
    
    return null;
  };

  const iconPath = getFileIcon();

  // 如果有對應的圖標，顯示圖片
  if (iconPath) {
    return (
      <img 
        src={iconPath} 
        alt={fileType || 'file'} 
        className={className}
        style={{ objectFit: 'contain' }}
      />
    );
  }

  // 否則顯示默認的文件圖標
  return (
    <div className={`${className} flex items-center justify-center`}>
      <FileOutlined className="text-2xl text-gray-400" />
    </div>
  );
};

export default DocumentTypeIcon;

