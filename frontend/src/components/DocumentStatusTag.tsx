import React from 'react';
import { Tag, Tooltip } from 'antd';
import { DocumentStatus } from '../services/api';
import {
  InfoCircleOutlined,
  CloudUploadOutlined,
  ClockCircleOutlined,
  FileTextOutlined,
  ExclamationCircleOutlined,
  ExperimentOutlined,
  CheckCircleOutlined,
  WarningOutlined,
  CloseCircleOutlined,
  QuestionCircleOutlined,
  SyncOutlined,
  FileProtectOutlined
} from '@ant-design/icons';

interface DocumentStatusTagProps {
  status: DocumentStatus;
  errorDetails?: string | null;
  showTooltip?: boolean;
  size?: 'small' | 'default';
}

// 獲取狀態顯示文本的輔助函數
const getStatusText = (status: DocumentStatus): string => {
  switch (status) {
    case 'uploaded': return '已上傳';
    case 'pending_extraction': return '等待提取';
    case 'text_extracted': return '文本已提取';
    case 'extraction_failed': return '提取失敗';
    case 'pending_analysis': return '等待分析';
    case 'analyzing': return '分析中';
    case 'analysis_completed': return '分析完成';
    case 'analysis_failed': return '分析失敗';
    case 'processing_error': return '處理錯誤';
    case 'completed': return '已完成';
    default: return status;
  }
};

const DocumentStatusTag: React.FC<DocumentStatusTagProps> = ({ 
  status, 
  errorDetails, 
  showTooltip = true,
  size = 'default'
}) => {
  let color = 'default';
  let icon = <InfoCircleOutlined />;

  switch (status) {
    case 'uploaded': 
      color = 'blue'; 
      icon = <CloudUploadOutlined />; 
      break;
    case 'pending_extraction': 
      color = 'gold'; 
      icon = <ClockCircleOutlined />; 
      break;
    case 'text_extracted': 
      color = 'geekblue'; 
      icon = <FileTextOutlined />; 
      break;
    case 'extraction_failed': 
      color = 'volcano'; 
      icon = <ExclamationCircleOutlined />; 
      break;
    case 'pending_analysis': 
      color = 'orange'; 
      icon = <ExperimentOutlined />; 
      break;
    case 'analyzing': 
      color = 'purple'; 
      icon = <SyncOutlined spin />; 
      break;
    case 'analysis_completed': 
      color = 'green'; 
      icon = <CheckCircleOutlined />; 
      break;
    case 'analysis_failed': 
      color = 'red'; 
      icon = <CloseCircleOutlined />; 
      break;
    case 'processing_error': 
      color = 'magenta'; 
      icon = <WarningOutlined />; 
      break;
    case 'completed': 
      color = 'cyan'; 
      icon = <FileProtectOutlined />; 
      break;
    default: 
      break;
  }

  const hasError = errorDetails && (
    status === 'processing_error' || 
    status === 'extraction_failed' || 
    status === 'analysis_failed'
  );

  return (
    <Tag icon={icon} color={color} key={status}>
      {getStatusText(status)}
      {hasError && showTooltip && (
        <Tooltip title={errorDetails}>
          <QuestionCircleOutlined 
            style={{ 
              marginLeft: 4, 
              color: 'red',
              fontSize: size === 'small' ? '12px' : '14px'
            }} 
          />
        </Tooltip>
      )}
    </Tag>
  );
};

export default DocumentStatusTag; 