import React from 'react';
import { Button } from '../ui'; // Updated import path
import { Space } from 'antd';
import type { Document, DocumentStatus } from '../../types/apiTypes'; // Updated import path

interface DocumentTableActionsProps {
  document: Document;
  isProcessing: boolean;
  isDeleting: boolean;
  isLoading: boolean;
  canPreview: boolean;
  canRetryAnalysis?: boolean;
  onViewDetails: (doc: Document) => void;
  onPreview: (doc: Document) => void;
  onTriggerProcessing: (docId: string) => void;
  onRetryAnalysis?: (doc: Document) => void;
  onDelete: (doc: Document) => void;
}

const DocumentTableActions: React.FC<DocumentTableActionsProps> = ({
  document,
  isProcessing,
  isDeleting,
  isLoading,
  canPreview,
  canRetryAnalysis = false,
  onViewDetails,
  onPreview,
  onTriggerProcessing,
  onRetryAnalysis,
  onDelete,
}) => {
  const canStartProcessing = (status: DocumentStatus): boolean => {
    return status === 'uploaded' || 
           status === 'processing_error';
  };

  const handleDelete = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (window.confirm(`確定要刪除文件 "${document.filename}" 嗎？`)) {
      onDelete(document);
    }
  };

  const handleRetryAnalysis = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (onRetryAnalysis) {
      onRetryAnalysis(document);
    }
  };

  return (
    <Space size="small">
      {/* 詳情按鈕 */}
      <Button 
        onClick={() => onViewDetails(document)} 
        variant="outline" 
        size="sm"
        disabled={isLoading || isDeleting}
      >
        <i className="fas fa-eye mr-1"></i>詳情
      </Button>

      {/* 預覽按鈕 */}
      {canPreview && (
        <Button 
          onClick={() => onPreview(document)} 
          variant="outline" 
          size="sm"
          disabled={isLoading || isDeleting}
        >
          <i className="fas fa-search-plus mr-1"></i>預覽
        </Button>
      )}

      {/* 重新分析按鈕 - 僅對失敗狀態顯示 */}
      {canRetryAnalysis && onRetryAnalysis && (
        <Button 
          onClick={handleRetryAnalysis}
          variant="outline" 
          size="sm"
          disabled={isProcessing || isLoading || isDeleting}
          className="border-yellow-500 text-yellow-600 hover:bg-yellow-50"
        >
          {isProcessing ? (
            <>
              <i className="fas fa-spinner fa-spin mr-1"></i>分析中...
            </>
          ) : (
            <>
              <i className="fas fa-redo mr-1"></i>重新分析
            </>
          )}
        </Button>
      )}

      {/* 處理/重試按鈕 - 對初始狀態和一般錯誤顯示 */}
      {canStartProcessing(document.status) && !canRetryAnalysis && (
        <Button 
          onClick={() => onTriggerProcessing(document.id)} 
          variant="secondary" 
          size="sm"
          disabled={isProcessing || isLoading || isDeleting}
        >
          {isProcessing ? (
            <>
              <i className="fas fa-spinner fa-spin mr-1"></i>處理中...
            </>
          ) : document.status === 'processing_error' ? (
            <>
              <i className="fas fa-redo mr-1"></i>重試處理
            </>
          ) : (
            <>
              <i className="fas fa-brain mr-1"></i>開始分析
            </>
          )}
        </Button>
      )}

      {/* 刪除按鈕 */}
      <Button 
        onClick={handleDelete}
        variant="danger" 
        size="sm"
        disabled={isDeleting || isLoading}
      >
        <i className="fas fa-trash-alt mr-1"></i>刪除
      </Button>
    </Space>
  );
};

export default DocumentTableActions; 