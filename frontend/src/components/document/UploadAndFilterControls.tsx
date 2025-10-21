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
    <Card className="mb-6">
      <div className="p-4">
        <h3 className="text-lg font-semibold mb-3">上傳與篩選</h3>
        
        {/* 搜索和篩選控制項 */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end mb-4">
          <div className="md:col-span-1">
            <Input
              label="搜索文件"
              placeholder="按文件名搜索..."
              value={searchTerm}
              onChange={(e) => onSearchChange(e.target.value)}
              className="w-full"
            />
          </div>
          <div className="md:col-span-1">
            <Select
              label="篩選狀態"
              value={filterStatus}
              onChange={(e: React.ChangeEvent<HTMLSelectElement>) => onFilterStatusChange(e.target.value as DocumentStatus | 'all')}
              options={documentStatusOptions}
              className="w-full"
            />
          </div>
          <div className="md:col-span-1 flex justify-end space-x-2">
            <Button 
              onClick={onUploadClick} 
              variant="primary"
              disabled={isUploading} 
            >
              {isUploading ? '上傳中...' : '上傳文件'}
            </Button>
            <Button 
              onClick={onDeleteSelected} 
              variant="danger" 
              disabled={selectedDocumentsCount === 0 || isDeleting}
            >
              {isDeleting ? '刪除中...' : `刪除選中 (${selectedDocumentsCount})`}
            </Button>
            {onGmailImport && (
              <Button 
                onClick={onGmailImport} 
                variant="outline"
              >
                📧 讀取 Gmail
              </Button>
            )}
          </div>
        </div>

        {/* 快速篩選按鈕 */}
        <div className="mb-4 flex space-x-2 border-b pb-4">
          <span className="text-sm font-medium text-gray-700 self-center mr-2">快速檢視:</span>
          {quickFilterOptions.map((filter) => (
            <Button
              key={filter.id}
              variant={activeQuickFilter === filter.id ? 'primary' : 'outline'}
              size="sm"
              onClick={() => onQuickFilterChange(filter.id)}
            >
              {filter.label}
            </Button>
          ))}
        </div>
      </div>
    </Card>
  );
};

export default UploadAndFilterControls; 