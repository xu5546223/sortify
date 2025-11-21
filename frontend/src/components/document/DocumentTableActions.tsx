import React, { useState, useRef, useEffect } from 'react';
import { 
  MoreOutlined, 
  EyeOutlined, 
  SearchOutlined,
  RedoOutlined,
  ThunderboltOutlined,
  DeleteOutlined,
  LoadingOutlined
} from '@ant-design/icons';
import type { Document, DocumentStatus } from '../../types/apiTypes';

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
  const [isOpen, setIsOpen] = useState(false);
  const [dropdownPosition, setDropdownPosition] = useState<'bottom' | 'top'>('bottom');
  const dropdownRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  const canStartProcessing = (status: DocumentStatus): boolean => {
    return status === 'uploaded' || status === 'processing_error';
  };

  // 計算下拉菜單的位置（使用 fixed 定位）
  const [menuStyle, setMenuStyle] = useState<React.CSSProperties>({});
  
  // 計算菜單位置的函數
  const calculateMenuPosition = () => {
    if (buttonRef.current) {
      const buttonRect = buttonRef.current.getBoundingClientRect();
      const viewportHeight = window.innerHeight;
      const spaceBelow = viewportHeight - buttonRect.bottom;
      const dropdownHeight = 300; // 預估菜單高度

      // 計算菜單位置
      if (spaceBelow < dropdownHeight && buttonRect.top > dropdownHeight) {
        // 向上展開
        setDropdownPosition('top');
        setMenuStyle({
          position: 'fixed',
          bottom: (viewportHeight - buttonRect.top + 8) + 'px',
          left: (buttonRect.right - 192) + 'px', // 192px = w-48
          zIndex: 9999
        });
      } else {
        // 向下展開
        setDropdownPosition('bottom');
        setMenuStyle({
          position: 'fixed',
          top: buttonRect.bottom + 8 + 'px',
          left: (buttonRect.right - 192) + 'px', // 192px = w-48
          zIndex: 9999
        });
      }
    }
  };
  
  // 當菜單打開時計算位置（作為備用）
  useEffect(() => {
    if (isOpen) {
      calculateMenuPosition();
    }
  }, [isOpen]);

  // 關閉下拉菜單當點擊外部時
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      window.document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      window.document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  const handleDelete = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsOpen(false);
    if (window.confirm(`確定要刪除文件 "${document.filename}" 嗎？`)) {
      onDelete(document);
    }
  };

  const handleRetryAnalysis = (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsOpen(false);
    if (onRetryAnalysis) {
      onRetryAnalysis(document);
    }
  };

  const handleViewDetails = (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsOpen(false);
    onViewDetails(document);
  };

  const handlePreview = (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsOpen(false);
    onPreview(document);
  };

  const handleTriggerProcessing = (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsOpen(false);
    onTriggerProcessing(document.id);
  };

  return (
    <div className="relative">
      {/* 三個點按鈕 */}
      <button
        ref={buttonRef}
        onClick={(e) => {
          e.stopPropagation();
          if (!isOpen) {
            // 打開前先計算位置
            calculateMenuPosition();
          }
          setIsOpen(!isOpen);
        }}
        disabled={isLoading || isDeleting}
        className="p-2 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        aria-label="操作選單"
      >
        <MoreOutlined className="text-lg" />
      </button>

      {/* 下拉菜單 - 使用 fixed 定位確保不被裁剪 */}
      {isOpen && (
        <div 
          ref={dropdownRef}
          className="w-48 bg-white dark:bg-gray-800 rounded-lg shadow-xl border border-gray-200 dark:border-gray-700 py-1"
          style={menuStyle}
        >
          {/* 詳情 */}
          <button
            onClick={handleViewDetails}
            disabled={isLoading || isDeleting}
            className="w-full px-4 py-2 text-left text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2 transition-colors"
          >
            <EyeOutlined className="text-base" />
            <span>查看詳情</span>
          </button>

          {/* 預覽 */}
          {canPreview && (
            <button
              onClick={handlePreview}
              disabled={isLoading || isDeleting}
              className="w-full px-4 py-2 text-left text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2 transition-colors"
            >
              <SearchOutlined className="text-base" />
              <span>預覽文件</span>
            </button>
          )}

          {/* 分隔線 */}
          {(canPreview || canRetryAnalysis || canStartProcessing(document.status)) && (
            <div className="my-1 border-t border-gray-200 dark:border-gray-700"></div>
          )}

          {/* 重新分析 */}
          {canRetryAnalysis && onRetryAnalysis && (
            <button
              onClick={handleRetryAnalysis}
              disabled={isProcessing || isLoading || isDeleting}
              className="w-full px-4 py-2 text-left text-sm text-yellow-600 dark:text-yellow-400 hover:bg-yellow-50 dark:hover:bg-yellow-900/20 disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2 transition-colors"
            >
              {isProcessing ? (
                <>
                  <LoadingOutlined className="text-base" spin />
                  <span>分析中...</span>
                </>
              ) : (
                <>
                  <RedoOutlined className="text-base" />
                  <span>重新分析</span>
                </>
              )}
            </button>
          )}

          {/* 開始分析/重試處理 */}
          {canStartProcessing(document.status) && !canRetryAnalysis && (
            <button
              onClick={handleTriggerProcessing}
              disabled={isProcessing || isLoading || isDeleting}
              className="w-full px-4 py-2 text-left text-sm text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/20 disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2 transition-colors"
            >
              {isProcessing ? (
                <>
                  <LoadingOutlined className="text-base" spin />
                  <span>處理中...</span>
                </>
              ) : document.status === 'processing_error' ? (
                <>
                  <RedoOutlined className="text-base" />
                  <span>重試處理</span>
                </>
              ) : (
                <>
                  <ThunderboltOutlined className="text-base" />
                  <span>開始分析</span>
                </>
              )}
            </button>
          )}

          {/* 分隔線 */}
          <div className="my-1 border-t border-gray-200 dark:border-gray-700"></div>

          {/* 刪除 */}
          <button
            onClick={handleDelete}
            disabled={isDeleting || isLoading}
            className="w-full px-4 py-2 text-left text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2 transition-colors"
          >
            {isDeleting ? (
              <>
                <LoadingOutlined className="text-base" spin />
                <span>刪除中...</span>
              </>
            ) : (
              <>
                <DeleteOutlined className="text-base" />
                <span>刪除文件</span>
              </>
            )}
          </button>
        </div>
      )}
    </div>
  );
};

export default DocumentTableActions;
