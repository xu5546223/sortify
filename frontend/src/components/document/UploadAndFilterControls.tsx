import React from 'react';
import { Input, Select, Button, Card } from '../ui'; // Updated import path
import type { DocumentStatus } from '../../types/apiTypes'; // Updated import path

interface QuickFilterOption {
  id: string;
  label: string;
  statusValue: DocumentStatus | 'all' | 'pending_group' | 'completed_group';
}

const quickFilterOptions: QuickFilterOption[] = [
  { id: 'all', label: '全部文件', statusValue: 'all' },
  { id: 'pending', label: '待處理', statusValue: 'pending_group' },
  { id: 'analyzed', label: '分析完成', statusValue: 'completed_group' },
  { id: 'error', label: '處理錯誤', statusValue: 'processing_error' },
];

const documentStatusOptions: { value: DocumentStatus | 'all'; label: string }[] = [
  { value: 'all', label: '全部狀態' },
  { value: 'uploaded', label: '已上傳' },
  { value: 'pending_extraction', label: '等待提取' },
  { value: 'text_extracted', label: '文本已提取' },
  { value: 'extraction_failed', label: '提取失敗' },
  { value: 'pending_analysis', label: '等待分析' },
  { value: 'analyzing', label: '分析中' },
  { value: 'analysis_completed', label: '分析完成' },
  { value: 'analysis_failed', label: '分析失敗' },
  { value: 'processing_error', label: '處理錯誤' },
  { value: 'completed', label: '已完成' },
];

interface UploadAndFilterControlsProps {
  searchTerm: string;
  onSearchChange: (value: string) => void;
  filterStatus: DocumentStatus | 'all';
  onFilterStatusChange: (value: DocumentStatus | 'all') => void;
  activeQuickFilter: string;
  onQuickFilterChange: (filterId: string) => void;
  selectedDocumentsCount: number;
  isUploading: boolean;
  isDeleting: boolean;
  onUploadClick: () => void;
  onDeleteSelected: () => void;
  onGmailImport?: () => void;
}

const UploadAndFilterControls: React.FC<UploadAndFilterControlsProps> = ({
  searchTerm,
  onSearchChange,
  filterStatus,
  onFilterStatusChange,
  activeQuickFilter,
  onQuickFilterChange,
  selectedDocumentsCount,
  isUploading,
  isDeleting,
  onUploadClick,
  onDeleteSelected,
  onGmailImport,
}) => {
  return (
    <header className="bg-neo-white border-3 border-neo-black shadow-neo-lg p-5 mb-6 flex flex-col gap-4">
      {/* 標題與核心動作區 */}
      <div className="flex justify-between items-end">
        <div>
          <h1 className="font-display text-3xl font-bold uppercase tracking-tight text-neo-black">
            File Manager
          </h1>
          <p className="font-bold text-gray-500 text-sm mt-1">文件管理 / 雲端整理</p>
        </div>
        
        {/* 核心動作按鈕組 */}
        <div className="flex gap-3">
          {onGmailImport && (
            <button
              onClick={onGmailImport}
              className="bg-neo-white text-neo-black border-3 border-neo-black px-4 py-2 text-sm font-display font-bold uppercase shadow-neo-md hover:shadow-neo-hover hover:-translate-x-0.5 hover:-translate-y-0.5 active:shadow-none active:translate-x-1 active:translate-y-1 transition-all duration-100 flex items-center gap-2"
            >
              <span className="text-lg">📧</span> 讀取 Gmail
            </button>
          )}
          <button
            onClick={onDeleteSelected}
            disabled={selectedDocumentsCount === 0 || isDeleting}
            className="bg-neo-error text-neo-white border-3 border-neo-black px-4 py-2 text-sm font-display font-bold uppercase shadow-neo-md hover:shadow-neo-hover hover:-translate-x-0.5 hover:-translate-y-0.5 active:shadow-none active:translate-x-1 active:translate-y-1 transition-all duration-100 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:translate-x-0 disabled:hover:translate-y-0 disabled:hover:shadow-neo-md flex items-center gap-2"
          >
            <span className="text-lg">🗑️</span>
            {isDeleting ? '刪除中...' : `刪除選中 (${selectedDocumentsCount})`}
          </button>
          <button
            onClick={onUploadClick}
            disabled={isUploading}
            className="bg-neo-primary text-neo-black border-3 border-neo-black px-6 py-2 text-sm font-display font-bold uppercase shadow-neo-md hover:bg-neo-hover hover:shadow-neo-hover hover:-translate-x-0.5 hover:-translate-y-0.5 active:shadow-none active:translate-x-1 active:translate-y-1 transition-all duration-100 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-neo-primary disabled:hover:translate-x-0 disabled:hover:translate-y-0 disabled:hover:shadow-neo-md flex items-center gap-2"
          >
            <span className="text-lg">⬆️</span>
            {isUploading ? '上傳中...' : '上傳文件'}
          </button>
        </div>
      </div>

      {/* 篩選與搜尋列 */}
      <div className="flex items-center gap-4 border-t-3 border-neo-black pt-4 mt-2">
        {/* 搜尋框 */}
        <div className="flex-1 relative">
          <span className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 text-lg">
            🔍
          </span>
          <input
            type="text"
            placeholder="搜索文件名稱、標籤..."
            value={searchTerm}
            onChange={(e) => onSearchChange(e.target.value)}
            className="w-full pl-10 pr-4 py-2.5 border-3 border-neo-black font-semibold outline-none transition-all focus:bg-green-50 focus:shadow-[3px_3px_0px_0px_#29bf12]"
          />
        </div>
        
        {/* 狀態篩選標籤 */}
        <div className="flex gap-2">
          {quickFilterOptions.map((filter) => (
            <button
              key={filter.id}
              onClick={() => onQuickFilterChange(filter.id)}
              className={`px-4 py-2 font-bold text-sm transition-all ${
                activeQuickFilter === filter.id
                  ? 'bg-neo-active text-neo-white border-3 border-neo-black shadow-[3px_3px_0px_0px_black]'
                  : 'bg-transparent text-neo-black hover:text-neo-active hover:underline hover:decoration-3'
              } ${
                filter.id === 'error' && activeQuickFilter !== filter.id
                  ? 'text-neo-error hover:text-neo-error'
                  : ''
              }`}
            >
              {filter.label}
            </button>
          ))}
        </div>
      </div>
    </header>
  );
};

export default UploadAndFilterControls;