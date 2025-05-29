import React, { useState, useEffect, useMemo, useCallback, useRef, useContext } from 'react';
import {
  PageHeader,
  Button,
  Input,
  Select,
  Table,
  TableRow,
  TableCell,
  Checkbox,
  Card,
  DocumentDetailsModal,
  DocumentStatusTag,
  DocumentTableActions,
  UploadAndFilterControls
} from '../components';
import { HeaderConfig } from '../components/Table';
import type {
  Document,
  DocumentStatus,
  TriggerDocumentProcessingOptions
} from '../types/apiTypes';
import {
  getDocuments,
  deleteDocuments,
  uploadDocument,
  triggerDocumentProcessing,
  getDocumentsByIds,
  deleteDocument
} from '../services/documentService';
import { formatBytes, formatDate, mapMimeTypeToSimpleType, canPreview } from '../utils/documentUtils';
import PreviewModal from '../components/PreviewModal';
import { SettingsContext, SettingsContextType } from '../contexts/SettingsContext';

// Define API_BASE_URL - User should configure this via .env ideally
// No longer needed here as PreviewModal handles its own API_BASE_URL or it's passed
// const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || 'http://localhost:8000';

// Define quick filter options
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

// 防抖函數
function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);

    return () => {
      clearTimeout(timer);
    };
  }, [value, delay]);

  return debouncedValue;
}

interface DocumentsPageProps {
  showPCMessage: (message: string, type?: 'success' | 'error' | 'info') => void;
}

// PaginationControls sub-component
interface PaginationControlsProps {
  currentPage: number;
  totalItems: number;
  itemsPerPage: number;
  onPageChange: (page: number) => void;
  isLoading: boolean;
}

const PaginationControls: React.FC<PaginationControlsProps> = ({ 
  currentPage, 
  totalItems, 
  itemsPerPage, 
  onPageChange,
  isLoading
}) => {
  const totalPages = Math.ceil(totalItems / itemsPerPage);

  if (totalPages <= 1) {
    return null; // Don't show pagination if only one page or no items
  }

  const handlePrevious = () => {
    if (currentPage > 1) {
      onPageChange(currentPage - 1);
    }
  };

  const handleNext = () => {
    if (currentPage < totalPages) {
      onPageChange(currentPage + 1);
    }
  };

  return (
    <div className="mt-6 flex items-center justify-between">
      <div>
        <p className="text-sm text-gray-700">
          顯示第 <span className="font-medium">{(currentPage - 1) * itemsPerPage + 1}</span> 到 <span className="font-medium">{Math.min(currentPage * itemsPerPage, totalItems)}</span> 筆，共 <span className="font-medium">{totalItems}</span> 筆結果
        </p>
      </div>
      <div className="space-x-2">
        <Button 
          onClick={handlePrevious} 
          disabled={currentPage === 1 || isLoading}
          variant="outline"
        >
          上一頁
        </Button>
        <Button 
          onClick={handleNext} 
          disabled={currentPage === totalPages || isLoading}
          variant="outline"
        >
          下一頁
        </Button>
      </div>
    </div>
  );
};

const DocumentsPage: React.FC<DocumentsPageProps> = ({ showPCMessage }) => {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isDeleting, setIsDeleting] = useState<boolean>(false);
  const [isProcessing, setIsProcessing] = useState<{[docId: string]: boolean}>({});
  const [searchTerm, setSearchTerm] = useState('');
  const [filterStatus, setFilterStatus] = useState<DocumentStatus | 'all'>('all'); 
  const [sortConfig, setSortConfig] = useState<{ key: keyof Document; direction: 'asc' | 'desc' } | null>({ key: 'created_at', direction: 'desc' });
  const [selectedDocuments, setSelectedDocuments] = useState<Set<string>>(new Set());
  const [detailedDoc, setDetailedDoc] = useState<Document | null>(null);
  const [totalDocuments, setTotalDocuments] = useState<number>(0);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const itemsPerPage = 20;
  const [activeQuickFilter, setActiveQuickFilter] = useState<string>('all');
  
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isUploading, setIsUploading] = useState<boolean>(false);
  
  const [isPreviewModalOpen, setIsPreviewModalOpen] = useState<boolean>(false);
  const [previewDoc, setPreviewDoc] = useState<Document | null>(null);

  const { settings: globalSettings } = useContext(SettingsContext) as SettingsContextType;

  const isMounted = useRef(true);
  const hasLoadedInitialData = useRef(false);
  const debouncedSearchTerm = useDebounce(searchTerm, 500);
  const isRequestPending = useRef(false);

  const statusPollingInterval = useRef<NodeJS.Timeout | null>(null);
  const [processingDocuments, setProcessingDocuments] = useState<Set<string>>(new Set());

  const shouldPollStatus = useMemo(() => {
    return documents.some(doc => 
      ['pending_extraction', 'text_extracted', 'pending_analysis', 'analyzing'].includes(doc.status)
    );
  }, [documents]);

  const pollDocumentStatus = useCallback(async () => {
    if (isRequestPending.current || !isMounted.current || processingDocuments.size === 0) return;
    
    try {
      const processingDocIds = Array.from(processingDocuments);
      console.log(`Polling status for ${processingDocIds.length} processing documents:`, processingDocIds);
      const updatedDocs = await getDocumentsByIds(processingDocIds);
      
      if (isMounted.current && updatedDocs.length > 0) {
        const stillProcessingDocs = updatedDocs.filter(doc => 
          ['pending_extraction', 'text_extracted', 'pending_analysis', 'analyzing'].includes(doc.status)
        );
        const completedDocs = updatedDocs.filter(doc => 
          ['analysis_completed', 'completed', 'analysis_failed', 'processing_error', 'extraction_failed'].includes(doc.status)
        );
        
        setDocuments(prevDocs => 
          prevDocs.map(prevDoc => {
            const updatedDoc = updatedDocs.find(updated => updated.id === prevDoc.id);
            return updatedDoc || prevDoc;
          })
        );
        
        if (completedDocs.length > 0) {
          const successCount = completedDocs.filter(doc => 
            ['analysis_completed', 'completed'].includes(doc.status)
          ).length;
          const failedCount = completedDocs.length - successCount;
          
          if (successCount > 0) showPCMessage(`${successCount} 個文件分析完成`, 'success');
          if (failedCount > 0) showPCMessage(`${failedCount} 個文件分析失敗`, 'error');
          
          if (detailedDoc && completedDocs.some(doc => doc.id === detailedDoc.id)) {
            const updatedDetailDoc = completedDocs.find(doc => doc.id === detailedDoc.id);
            if (updatedDetailDoc) setDetailedDoc(updatedDetailDoc);
          }
        }
        setProcessingDocuments(new Set(stillProcessingDocs.map(doc => doc.id)));
        console.log(`Status polling completed: ${stillProcessingDocs.length} still processing, ${completedDocs.length} completed`);
      }
    } catch (error) {
      console.error('Status polling failed:', error);
    }
  }, [processingDocuments, showPCMessage, detailedDoc, documents]);

  useEffect(() => {
    if (shouldPollStatus && hasLoadedInitialData.current) {
      statusPollingInterval.current = setInterval(pollDocumentStatus, 3000);
      console.log('Started status polling for processing documents');
    } else {
      if (statusPollingInterval.current) {
        clearInterval(statusPollingInterval.current);
        statusPollingInterval.current = null;
        console.log('Stopped status polling');
      }
    }
    return () => {
      if (statusPollingInterval.current) clearInterval(statusPollingInterval.current);
    };
  }, [shouldPollStatus, pollDocumentStatus]);

  useEffect(() => {
    return () => {
      if (statusPollingInterval.current) clearInterval(statusPollingInterval.current);
    };
  }, []);

  const handleQuickFilterChange = (filterId: string) => {
    setActiveQuickFilter(filterId);
    setCurrentPage(1);
    const selectedFilter = quickFilterOptions.find(f => f.id === filterId);
    if (selectedFilter) {
      if (selectedFilter.statusValue === 'pending_group' || selectedFilter.statusValue === 'completed_group') {
        setFilterStatus('all');
      } else {
        setFilterStatus(selectedFilter.statusValue as DocumentStatus | 'all');
      }
    }
  };

  const handleSort = useCallback((key: string) => {
    const sortableKeys = ['filename', 'file_type', 'size', 'created_at', 'updated_at', 'status'] as const;
    type SortableKey = typeof sortableKeys[number];
    if (!(sortableKeys as readonly string[]).includes(key)) {
      if (key === 'selector' || key === 'actions') {
        console.warn(`Attempted to sort by non-sortable key: ${key}`);
      } else {
        console.warn(`Attempted to sort by unknown or non-sortable key: ${key}`);
      }
      return;
    }
    const docKey = key as SortableKey;
    let direction: 'asc' | 'desc' = 'asc';
    if (sortConfig && sortConfig.key === docKey && sortConfig.direction === 'asc') {
      direction = 'desc';
    }
    setSortConfig({ key: docKey, direction });
    setCurrentPage(1);
  }, [sortConfig]);

  const tableHeadersForTableComponent: HeaderConfig[] = useMemo(() => {
    const columnDefinitions: { 
      key: keyof Document | 'actions' | 'selector'; 
      label: string | React.ReactNode;
      sortable?: boolean; 
      className?: string;
      cellClassName?: string;
      render?: (doc: Document) => React.ReactNode; 
    }[] = [
      { key: 'selector', label: '' , sortable: false, className: 'w-10 px-4 py-3' }, 
      { key: 'filename', label: '名稱', sortable: true, cellClassName: 'truncate max-w-xs'},
      { key: 'file_type', label: '類型', sortable: true },
      { key: 'size', label: '大小', sortable: true },
      { key: 'created_at', label: '上傳時間', sortable: true },
      { key: 'updated_at', label: '最後修改', sortable: true },
      { key: 'status', label: '狀態', sortable: true },
      { key: 'actions', label: '操作', sortable: false, className: 'w-20' },
    ];
    return columnDefinitions.map(colDef => ({
      key: colDef.key as string,
      label: colDef.label,
      sortable: colDef.sortable,
      onSort: colDef.sortable ? handleSort : undefined,
      className: colDef.className,
    }));
  }, [handleSort]);

 const tableCellRenderers = useMemo(() => {
    const definitions: { 
        key: keyof Document | 'actions' | 'selector';
        cellClassName?: string;
        render: (doc: Document) => React.ReactNode;
    }[] = [
        { key: 'filename', cellClassName: 'truncate max-w-xs', render: (doc) => <span title={doc.filename}>{doc.filename}</span> },
        { key: 'file_type', render: (doc) => <span title={doc.file_type ?? undefined}>{mapMimeTypeToSimpleType(doc.file_type)}</span> },
        { key: 'size', render: (doc) => formatBytes(doc.size ?? undefined) },
        { key: 'created_at', render: (doc) => formatDate(doc.created_at) },
        { key: 'updated_at', render: (doc) => formatDate(doc.updated_at) },
        {
            key: 'status',
            render: (doc) => (
                <DocumentStatusTag 
                    status={doc.status} 
                    errorDetails={doc.error_details}
                />
            )
        },
    ];
    return definitions.reduce((acc, item) => {
        acc[item.key] = item;
        return acc;
    }, {} as Record<keyof Document | 'actions' | 'selector', typeof definitions[0]>);
}, []);

  const fetchDocumentsData = useCallback(async () => {
    if (isRequestPending.current || !isMounted.current) return;
    isRequestPending.current = true;
    setIsLoading(true);
    try {
      const skip = (currentPage - 1) * itemsPerPage;
      const sortKey = sortConfig?.key as keyof Document | undefined;
      let apiStatusParam: DocumentStatus | undefined = undefined;
      if (filterStatus !== 'all') {
        apiStatusParam = filterStatus;
      }
      console.log(`Fetching with activeQuickFilter: ${activeQuickFilter}, filterStatus: ${filterStatus}, apiStatusParam: ${apiStatusParam}`);
      const data = await getDocuments(debouncedSearchTerm, apiStatusParam, undefined, sortKey , sortConfig?.direction, skip, itemsPerPage);
      if (isMounted.current) {
        setDocuments(data.documents);
        setTotalDocuments(data.totalCount);
        if (!hasLoadedInitialData.current) { hasLoadedInitialData.current = true; }
        showPCMessage('文件列表已更新', 'info');
      }
    } catch (error) {
      console.error('Failed to fetch documents:', error);
      if (isMounted.current) {
        showPCMessage('獲取文件列表失敗', 'error');
        setDocuments([]); setTotalDocuments(0);
      }
    }
    if (isMounted.current) { setIsLoading(false); }
    setTimeout(() => { isRequestPending.current = false; }, 300);
  }, [debouncedSearchTerm, filterStatus, sortConfig, showPCMessage, currentPage, itemsPerPage, activeQuickFilter]);

  useEffect(() => {
    isMounted.current = true;
    fetchDocumentsData();
    return () => { isMounted.current = false; };
  }, [fetchDocumentsData]);

  const handleSelectAll = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.checked) {
      const allIds = new Set(filteredDocuments.map(doc => doc.id));
      setSelectedDocuments(allIds);
    } else {
      setSelectedDocuments(new Set());
    }
  };

  const handleSelectRow = (docId: string) => {
    setSelectedDocuments(prev => {
      const newSelection = new Set(prev);
      if (newSelection.has(docId)) {
        newSelection.delete(docId);
      } else {
        newSelection.add(docId);
      }
      return newSelection;
    });
  };

  const handleDeleteSelected = async () => {
    if (selectedDocuments.size === 0) {
      showPCMessage('請先選擇要刪除的文件', 'info');
      return;
    }
    if (window.confirm('確定要刪除選中的 ' + selectedDocuments.size + ' 個文件嗎？')) {
      setIsDeleting(true);
      try {
        const idsToDelete = Array.from(selectedDocuments);
        const result = await deleteDocuments(idsToDelete);

        showPCMessage(result.message, result.success ? 'success' : 'info'); 

        if (result.success || result.success_count > 0) {
          setSelectedDocuments(new Set());
          fetchDocumentsData(); // 重新獲取數據以反映更改
        }
        
        // 如果有部分失敗或詳細錯誤信息，可以考慮額外顯示
        if (!result.success && result.details && result.details.length > 0) {
          const errorDetails = result.details
            .filter(d => d.status !== 'deleted')
            .map(d => `文件ID ${d.id}: ${d.message || d.status}`)
            .join('\n');
          if (errorDetails) {
            showPCMessage('部分文件未能成功刪除。詳細信息：\n' + errorDetails, 'error');
          }
        }

      } catch (error: any) {
        console.error('Failed to delete documents:', error);
        const errorMessage = error.response?.data?.detail || error.response?.data?.message || error.message || '刪除文件時發生未知錯誤';
        showPCMessage(errorMessage, 'error');
      } finally {
        setIsDeleting(false);
      }
    }
  };

  const documentFilterOptions = useMemo(() => [ { value: 'all', label: '所有狀態' }, { value: 'uploaded', label: '已上傳' }, { value: 'pending_extraction', label: '待提取' }, { value: 'text_extracted', label: '已提取' }, { value: 'pending_analysis', label: '待分析' }, { value: 'analysis_completed', label: '分析完成' }, { value: 'completed', label: '已完成' }, { value: 'processing_error', label: '處理錯誤' }, ], []);

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) {
      showPCMessage('未選擇任何文件', 'info');
      return;
    }
    setIsUploading(true);
    showPCMessage(`正在上傳 ${file.name}...`, 'info');
    try {
      const uploadedDoc = await uploadDocument(file);
      showPCMessage(`文件 ${uploadedDoc.filename} 上傳成功!`, 'success');
      if (currentPage !== 1) {
        setCurrentPage(1);
      } else {
        fetchDocumentsData();
      }
    } catch (error: any) {
      console.error('Failed to upload document:', error);
      if (error.response) {
        console.error('API Error Response Data:', error.response.data);
        console.error('API Error Response Status:', error.response.status);
        console.error('API Error Response Headers:', error.response.headers);
        if (error.response.data && error.response.data.detail) {
          console.error('FastAPI Validation Error Detail:', error.response.data.detail);
        }
      } else if (error.request) {
        console.error('API Error Request Data:', error.request);
      } else {
        console.error('API Error Message:', error.message);
      }
      const errorDetail = error.response?.data?.detail || error.message || '上傳失敗，請稍後再試';
      let displayError = errorDetail;
      if (Array.isArray(errorDetail)) {
        displayError = errorDetail.map(err => `Field: ${err.loc.join(' -> ')}, Error: ${err.msg}`).join('\n');
      }
      showPCMessage(`上傳 ${file.name} 失敗: ${displayError}`, 'error');
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const triggerFileInput = () => {
    fileInputRef.current?.click();
  };

  const viewDocumentDetails = (doc: Document) => {
    setDetailedDoc(doc);
  };

  const closeDetailsModal = () => {
    setDetailedDoc(null);
  };

  const handleTriggerProcessing = async (docId: string) => {
    setIsProcessing(prev => ({ ...prev, [docId]: true }));
    try {
      // 從全局設定獲取 AI 選項
      const aiOptions: TriggerDocumentProcessingOptions = {};
      if (globalSettings.aiService?.force_stable_model !== null && globalSettings.aiService?.force_stable_model !== undefined) {
        aiOptions.ai_force_stable_model = globalSettings.aiService.force_stable_model;
      } else {
        aiOptions.ai_force_stable_model = undefined;
      }
      if (globalSettings.aiService?.ensure_chinese_output !== null && globalSettings.aiService?.ensure_chinese_output !== undefined) {
        aiOptions.ai_ensure_chinese_output = globalSettings.aiService.ensure_chinese_output;
      } else {
        aiOptions.ai_ensure_chinese_output = undefined;
      }
      
      const options: TriggerDocumentProcessingOptions = { 
        trigger_content_processing: true,
        ...aiOptions 
      };
      
      const updatedDoc = await triggerDocumentProcessing(docId, options);
      
      setDocuments(prevDocs => prevDocs.map(d => d.id === docId ? updatedDoc : d));
      if (detailedDoc && detailedDoc.id === docId) {
        setDetailedDoc(updatedDoc);
      }
      showPCMessage(`已觸發對文件 ${updatedDoc.filename} 的處理`, 'success');
      
      // 如果文件開始處理，將其加入監測列表
      if (['pending_extraction', 'text_extracted', 'pending_analysis', 'analyzing'].includes(updatedDoc.status)) {
        setProcessingDocuments(prev => new Set(prev).add(docId));
      }

    } catch (error: any) {
      showPCMessage(`觸發處理失敗: ${error.message || '未知錯誤'}`, 'error');
      console.error("Error triggering processing:", error);
    } finally {
      setIsProcessing(prev => ({ ...prev, [docId]: false }));
    }
  };

  const handleRetryAnalysis = async (doc: Document) => {
    setIsProcessing(prev => ({ ...prev, [doc.id]: true }));
    showPCMessage(`正在為文件 ${doc.filename} 重試AI分析...`, 'info');
    try {
      // 從全局設定獲取 AI 選項
      const aiOptions: TriggerDocumentProcessingOptions = {};
      if (globalSettings.aiService?.force_stable_model !== null && globalSettings.aiService?.force_stable_model !== undefined) {
        aiOptions.ai_force_stable_model = globalSettings.aiService.force_stable_model;
      } else {
        aiOptions.ai_force_stable_model = undefined;
      }
      if (globalSettings.aiService?.ensure_chinese_output !== null && globalSettings.aiService?.ensure_chinese_output !== undefined) {
        aiOptions.ai_ensure_chinese_output = globalSettings.aiService.ensure_chinese_output;
      } else {
        aiOptions.ai_ensure_chinese_output = undefined;
      }

      const options: TriggerDocumentProcessingOptions = {
        trigger_content_processing: true, // 確保觸發處理
        ...aiOptions
      };
      
      const updatedDoc = await triggerDocumentProcessing(doc.id, options);
      
      setDocuments(prevDocs => prevDocs.map(d => d.id === doc.id ? updatedDoc : d));
      if (detailedDoc && detailedDoc.id === doc.id) {
        setDetailedDoc(updatedDoc);
      }
      showPCMessage(`已重新觸發文件 ${doc.filename} 的AI分析。`, 'success');
      
      // 如果文件開始處理，將其加入監測列表
      if (['pending_extraction', 'text_extracted', 'pending_analysis', 'analyzing'].includes(updatedDoc.status)) {
        setProcessingDocuments(prev => new Set(prev).add(doc.id));
      }

    } catch (error: any) {
      const errorMessage = error.response?.data?.detail || error.message || '未知錯誤';
      showPCMessage(`重試AI分析失敗: ${errorMessage}`, 'error');
      console.error(`Error retrying analysis for doc ${doc.id}:`, error);
    } finally {
      setIsProcessing(prev => ({ ...prev, [doc.id]: false }));
    }
  };

  const canRetryAnalysis = useCallback((doc: Document): boolean => {
    return ['analysis_failed', 'processing_error', 'extraction_failed'].includes(doc.status);
  }, []);

  const handleOpenPreview = (doc: Document) => {
    console.log('Attempting to preview doc:', doc);
    if (canPreview(doc)) {
      setPreviewDoc(doc);
      setIsPreviewModalOpen(true);
    } else {
      let message = `文件 "${doc.filename}" (類型: ${doc.file_type || '未知'}) 不支持預覽。`;
      const fileType = doc.file_type?.toLowerCase() || '';
      const isImage = fileType.startsWith('image/');
      const isPdf = fileType === 'application/pdf';
      const hasExtractedText = !!doc.extracted_text;
      if (!isImage && !isPdf && !hasExtractedText) {
        message = `文件 "${doc.filename}" 沒有可預覽的內容 (非圖片/PDF，且無提取文本)。`;
      } else if ((fileType.startsWith('text/') || fileType === 'application/json' || !fileType) && !hasExtractedText) {
        message = `文件 "${doc.filename}" 雖然可能是文本類型，但沒有可供預覽的提取文本。`;
      }
      showPCMessage(message, 'info');
    }
  };

  const handleClosePreview = () => {
    setIsPreviewModalOpen(false);
    setPreviewDoc(null);
  };

  const handlePageChange = (newPage: number) => {
    setCurrentPage(newPage);
  };

  const handleSingleDocumentDelete = async (doc: Document) => {
    setIsDeleting(true);
    try {
      const result = await deleteDocument(doc.id);
      if (result.success) {
        showPCMessage(`文件 "${doc.filename}" 已成功刪除`, 'success');
        setSelectedDocuments(prev => {
          const newSelection = new Set(prev);
          newSelection.delete(doc.id);
          return newSelection;
        });
        if (filteredDocuments.length === 1 && currentPage > 1) {
          setCurrentPage(prev => prev - 1); 
        } else {
          fetchDocumentsData(); 
        }
      } else {
        showPCMessage(`刪除文件 "${doc.filename}" 失敗: ${result.message || '未知錯誤'}`, 'error');
      }
    } catch (error) {
      showPCMessage(`刪除文件 "${doc.filename}" 時發生錯誤`, 'error');
      console.error("Error deleting single document:", error);
    } finally {
      setIsDeleting(false);
    }
  };

  const filteredDocuments = useMemo(() => {
    if (activeQuickFilter === 'all') {
      return documents;
    }
    const selectedFilter = quickFilterOptions.find(f => f.id === activeQuickFilter);
    if (!selectedFilter) {
      return documents;
    }
    switch (selectedFilter.statusValue) {
      case 'pending_group':
        return documents.filter(doc => 
          ['uploaded', 'pending_extraction', 'text_extracted', 'pending_analysis', 'analyzing'].includes(doc.status)
        );
      case 'completed_group':
        return documents.filter(doc => 
          ['analysis_completed', 'completed'].includes(doc.status)
        );
      default:
        if (filterStatus !== 'all') {
          return documents.filter(doc => doc.status === filterStatus);
        }
        return documents;
    }
  }, [documents, activeQuickFilter, filterStatus]);

  if (isLoading && !hasLoadedInitialData.current) {
    return (
      <div className="p-6 bg-surface-100 min-h-screen flex flex-col items-center justify-center">
        <i className="fas fa-spinner fa-spin text-4xl text-blue-600"></i>
        <p className="mt-4 text-xl">正在載入文件...</p>
      </div>
    );
  }
  
  return (
    <div className="container mx-auto p-4">
      <PageHeader title="文件管理" />
      
      <UploadAndFilterControls 
        searchTerm={searchTerm}
        onSearchChange={(value) => { setSearchTerm(value); setCurrentPage(1); }}
        filterStatus={filterStatus}
        onFilterStatusChange={(value) => { setFilterStatus(value); setCurrentPage(1); }}
        activeQuickFilter={activeQuickFilter}
        onQuickFilterChange={handleQuickFilterChange}
        selectedDocumentsCount={selectedDocuments.size}
        isUploading={isUploading}
        isDeleting={isDeleting}
        onUploadClick={triggerFileInput}
        onDeleteSelected={handleDeleteSelected}
      />

      <input 
        type="file" 
        ref={fileInputRef} 
        onChange={handleFileUpload} 
        style={{ display: 'none' }} 
        multiple 
        accept=".txt,.pdf,.jpg,.jpeg,.png,.gif,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.md"
      />

      {isLoading && documents.length === 0 && !hasLoadedInitialData.current && (
        <div className="text-center py-10">
          <p className="text-xl text-gray-500">正在努力加載您的文件...</p>
        </div>
      )}

      {(!isLoading || filteredDocuments.length > 0 || hasLoadedInitialData.current) && filteredDocuments.length === 0 && (debouncedSearchTerm || activeQuickFilter !== 'all') && (
        <div className="text-center py-10">
          <p className="text-xl text-gray-500">
            {debouncedSearchTerm ? '找不到符合搜索條件的文件。' : '找不到符合篩選條件的文件。'}
          </p>
        </div>
      )}

      {(!isLoading || documents.length > 0 || hasLoadedInitialData.current) && (
      <Card>
        <Table 
          headers={tableHeadersForTableComponent}
          sortConfig={sortConfig} 
          isSelectAllChecked={filteredDocuments.length > 0 && selectedDocuments.size === filteredDocuments.filter(doc => doc.id).length}
          onSelectAllChange={handleSelectAll} 
          isSelectAllDisabled={filteredDocuments.length === 0 || isDeleting || isLoading} 
        >
          {filteredDocuments.map((doc) => (
            <TableRow key={doc.id} className={selectedDocuments.has(doc.id) ? 'bg-primary-50 hover:bg-primary-100' : 'hover:bg-surface-100'}>
              {tableHeadersForTableComponent.map(header => {
                if (header.key === 'selector') {
                  return (
                    <TableCell key={`${header.key}-${doc.id}`} className={header.className || tableCellRenderers.selector?.cellClassName}>
                      <Checkbox
                        id={`select-doc-${doc.id}`}
                        checked={selectedDocuments.has(doc.id)}
                        onChange={() => handleSelectRow(doc.id)}
                        disabled={isDeleting || isLoading}
                        aria-label={`Select document ${doc.filename}`}
                      />
                    </TableCell>
                  );
                }
                if (header.key === 'actions') {
                  return (
                    <TableCell key={`${header.key}-${doc.id}`} className={header.className || tableCellRenderers.actions?.cellClassName}>
                      <DocumentTableActions 
                        document={doc}
                        isProcessing={isProcessing[doc.id] || false}
                        isDeleting={isDeleting}
                        isLoading={isLoading}
                        canPreview={canPreview(doc)}
                        canRetryAnalysis={canRetryAnalysis(doc)}
                        onViewDetails={viewDocumentDetails}
                        onPreview={handleOpenPreview}
                        onTriggerProcessing={handleTriggerProcessing}
                        onRetryAnalysis={handleRetryAnalysis}
                        onDelete={handleSingleDocumentDelete}
                      />
                    </TableCell>
                  );
                }
                const cellRendererConfig = tableCellRenderers[header.key as keyof Document];
                return (
                  <TableCell key={`${header.key}-${doc.id}`} className={header.className || cellRendererConfig?.cellClassName}>
                    {cellRendererConfig 
                      ? cellRendererConfig.render(doc) 
                      : (doc[header.key as keyof Document] as React.ReactNode || 'N/A')}
                  </TableCell>
                );
              })}
            </TableRow>
          ))}
        </Table>
      </Card>
      )}
      
      <PaginationControls 
        currentPage={currentPage}
        totalItems={activeQuickFilter === 'all' ? totalDocuments : filteredDocuments.length}
        itemsPerPage={itemsPerPage}
        onPageChange={handlePageChange}
        isLoading={isLoading}
      />

      <DocumentDetailsModal 
        document={detailedDoc}
        isOpen={!!detailedDoc}
        onClose={closeDetailsModal}
      />

      <PreviewModal 
        isOpen={isPreviewModalOpen}
        onClose={handleClosePreview}
        doc={previewDoc}
      />
    </div>
  );
};

export default DocumentsPage; 