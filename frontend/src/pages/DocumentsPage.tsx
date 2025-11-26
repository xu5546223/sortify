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
  DocumentsWithClustering
} from '../components';
import { DocumentTypeIcon } from '../components/document';
import FileDropZone from '../components/document/FileDropZone';
import FolderDetailView from '../components/document/FolderDetailView';
import GmailImporter from '../components/GmailImporter';
import { HeaderConfig } from '../components/table/Table';
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
import { apiClient } from '../services/apiClient';
import { formatBytes, formatDate, formatCompactDate, mapMimeTypeToSimpleType } from '../utils/documentFormatters';
import { canPreview } from '../utils/documentUtils';
import PreviewModal from '../components/document/PreviewModal';
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

// 全局圖片緩存（與 FolderDetailView 共享）- LRU 策略
class ImageCache {
  private cache = new Map<string, string>();
  private maxSize: number;

  constructor(maxSize: number = 50) {
    this.maxSize = maxSize;
  }

  get(key: string): string | undefined {
    const value = this.cache.get(key);
    if (value) {
      // LRU: 重新插入到末尾
      this.cache.delete(key);
      this.cache.set(key, value);
    }
    return value;
  }

  set(key: string, value: string): void {
    if (this.cache.has(key)) {
      this.cache.delete(key);
    }
    
    if (this.cache.size >= this.maxSize) {
      const firstKey = this.cache.keys().next().value;
      if (firstKey) {
        const oldUrl = this.cache.get(firstKey);
        if (oldUrl) {
          URL.revokeObjectURL(oldUrl);
        }
        this.cache.delete(firstKey);
      }
    }
    
    this.cache.set(key, value);
  }
}

const imageCache = new ImageCache(50);

const ImageThumbnail: React.FC<{ doc: Document }> = ({ doc }) => {
  const [imageSrc, setImageSrc] = useState<string | null>(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;
    
    if (!doc.file_type?.startsWith('image/')) {
      setLoading(false);
      return;
    }

    // 檢查緩存
    const cached = imageCache.get(doc.id);
    if (cached) {
      setImageSrc(cached);
      setLoading(false);
      return;
    }

    // 從後端載入
    setLoading(true);
    apiClient.get(`/documents/${doc.id}/file`, { responseType: 'blob' })
      .then(response => {
        if (isMounted) {
          const objectUrl = URL.createObjectURL(response.data);
          imageCache.set(doc.id, objectUrl);
          setImageSrc(objectUrl);
          setLoading(false);
        }
      })
      .catch(err => {
        if (isMounted) {
          console.error(`[ImageThumbnail] Error loading thumbnail for ${doc.filename}:`, err);
          setError(true);
          setLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [doc.id, doc.file_type]);

  if (error || !doc.file_type?.startsWith('image/')) {
    return (
      <DocumentTypeIcon
        fileType={doc.file_type || null}
        fileName={doc.filename}
        className="w-10 h-10"
      />
    );
  }

  if (loading || !imageSrc) {
    return (
      <div className="w-10 h-10 flex items-center justify-center bg-gray-100 border border-gray-300">
        <div className="animate-spin rounded-full h-4 w-4 border-2 border-neo-black border-t-transparent"></div>
      </div>
    );
  }

  return (
    <img
      src={imageSrc}
      alt={doc.filename}
      className="w-10 h-10 object-cover border border-gray-300"
    />
  );
};

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
        <p className="text-sm font-bold text-neo-black">
          顯示第 <span className="font-black">{(currentPage - 1) * itemsPerPage + 1}</span> 到 <span className="font-black">{Math.min(currentPage * itemsPerPage, totalItems)}</span> 筆，共 <span className="font-black">{totalItems}</span> 筆結果
        </p>
      </div>
      <div className="flex gap-2">
        <button
          onClick={handlePrevious}
          disabled={currentPage === 1 || isLoading}
          className="bg-neo-white text-neo-black border-3 border-neo-black px-4 py-2 font-display font-bold uppercase shadow-neo-md hover:shadow-neo-hover hover:-translate-x-0.5 hover:-translate-y-0.5 active:shadow-none active:translate-x-1 active:translate-y-1 transition-all duration-100 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:translate-x-0 disabled:hover:translate-y-0 disabled:hover:shadow-neo-md"
        >
          上一頁
        </button>
        <button
          onClick={handleNext}
          disabled={currentPage === totalPages || isLoading}
          className="bg-neo-white text-neo-black border-3 border-neo-black px-4 py-2 font-display font-bold uppercase shadow-neo-md hover:shadow-neo-hover hover:-translate-x-0.5 hover:-translate-y-0.5 active:shadow-none active:translate-x-1 active:translate-y-1 transition-all duration-100 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:translate-x-0 disabled:hover:translate-y-0 disabled:hover:shadow-neo-md"
        >
          下一頁
        </button>
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

  // Gmail 導入對話框狀態
  const [isGmailImporterVisible, setIsGmailImporterVisible] = useState<boolean>(false);

  // 聚類功能狀態
  // undefined: 不過濾任何資料夾（顯示所有文件）
  // null: 過濾未分類文件
  // string: 過濾指定 cluster_id 的文件
  const [selectedClusterId, setSelectedClusterId] = useState<string | null | undefined>(undefined);
  const [selectedFolderName, setSelectedFolderName] = useState<string | null>(null);
  const [showFolderDetail, setShowFolderDetail] = useState<boolean>(false);
  const [folderDocuments, setFolderDocuments] = useState<Document[]>([]); // 資料夾視圖的所有文檔
  const [isLoadingFolderDocs, setIsLoadingFolderDocs] = useState<boolean>(false);

  const isMounted = useRef(true);
  const hasLoadedInitialData = useRef(false);
  const debouncedSearchTerm = useDebounce(searchTerm, 500);
  const isRequestPending = useRef(false);
  const isPollingPending = useRef(false); // 新增：轮询请求锁

  const statusPollingInterval = useRef<NodeJS.Timeout | null>(null);
  const [processingDocuments, setProcessingDocuments] = useState<Set<string>>(new Set());
  
  // 使用 ref 來追蹤處理中的文檔，避免 useCallback 依賴變化導致重複請求
  const processingDocumentsRef = useRef<Set<string>>(new Set());
  const documentsRef = useRef<Document[]>([]);
  const detailedDocRef = useRef<Document | null>(null);
  
  // 同步 ref 與 state
  useEffect(() => {
    processingDocumentsRef.current = processingDocuments;
  }, [processingDocuments]);
  
  useEffect(() => {
    documentsRef.current = documents;
  }, [documents]);
  
  useEffect(() => {
    detailedDocRef.current = detailedDoc;
  }, [detailedDoc]);

  const pollDocumentStatus = useCallback(async () => {
    // 使用 ref 來避免依賴變化導致的重複請求
    const currentProcessingDocs = processingDocumentsRef.current;

    // 新增：檢查是否已有輪詢請求在進行中
    if (isPollingPending.current || !isMounted.current || currentProcessingDocs.size === 0) return;

    isPollingPending.current = true; // 設置輪詢鎖

    try {
      const processingDocIds = Array.from(currentProcessingDocs);
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

          const currentDetailedDoc = detailedDocRef.current;
          if (currentDetailedDoc && completedDocs.some(doc => doc.id === currentDetailedDoc.id)) {
            const updatedDetailDoc = completedDocs.find(doc => doc.id === currentDetailedDoc.id);
            if (updatedDetailDoc) setDetailedDoc(updatedDetailDoc);
          }
        }

        // 優化：只有當處理中的文檔集合真正變化時才更新 state
        const newProcessingIds = stillProcessingDocs.map(doc => doc.id).sort();
        const currentIds = Array.from(processingDocumentsRef.current).sort();

        // 使用字符串比較避免 Set 比較的不穩定性
        const hasChanged = JSON.stringify(newProcessingIds) !== JSON.stringify(currentIds);

        if (hasChanged) {
          const newProcessingSet = new Set(newProcessingIds);
          setProcessingDocuments(newProcessingSet);
          console.log(`Processing documents updated: ${currentIds.length} -> ${newProcessingIds.length}`);
        }

        console.log(`Status polling completed: ${stillProcessingDocs.length} still processing, ${completedDocs.length} completed`);
      }
    } catch (error) {
      console.error('Status polling failed:', error);
    } finally {
      isPollingPending.current = false; // 釋放輪詢鎖
    }
  }, [showPCMessage]); // 移除不必要的依賴，使用 ref 來獲取最新值

  // 使用 ref 存储 pollDocumentStatus 以避免 useEffect 重新触发
  const pollDocumentStatusRef = useRef(pollDocumentStatus);
  useEffect(() => {
    pollDocumentStatusRef.current = pollDocumentStatus;
  }, [pollDocumentStatus]);

  // 計算是否需要輪詢 - 基於 processingDocuments 而非 documents
  const shouldPollStatus = processingDocuments.size > 0;

  useEffect(() => {
    // 清理之前的 interval
    if (statusPollingInterval.current) {
      clearInterval(statusPollingInterval.current);
      statusPollingInterval.current = null;
    }

    if (shouldPollStatus && hasLoadedInitialData.current) {
      // 使用 ref 調用以避免依賴變化導致 interval 重設
      statusPollingInterval.current = setInterval(() => {
        pollDocumentStatusRef.current();
      }, 3000);
      console.log('Started status polling for processing documents');
    } else {
      console.log('Stopped status polling - no processing documents');
    }

    // 清理函數
    return () => {
      if (statusPollingInterval.current) {
        clearInterval(statusPollingInterval.current);
        statusPollingInterval.current = null;
      }
    };
  }, [shouldPollStatus]); // 移除 pollDocumentStatus 依賴

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

  // 處理聚類過濾變更
  const handleClusterFilterChange = useCallback(async (clusterId: string | null, folderName?: string) => {
    setSelectedClusterId(clusterId);
    setSelectedFolderName(folderName || null);
    setShowFolderDetail(!!folderName); // 當有 folderName 時顯示詳細視圖（包括未分類資料夾）
    setCurrentPage(1); // 重置到第一頁
    
    // 如果進入資料夾視圖，獲取該資料夾的所有文檔
    if (folderName && clusterId !== undefined) {
      try {
        setIsLoadingFolderDocs(true);
        // 獲取該資料夾的所有文檔（使用很大的 limit 以獲取所有文件）
        const data = await getDocuments(
          '', // 不搜索
          'all', // 所有狀態
          undefined,
          'created_at',
          'desc',
          0,
          10000, // 獲取最多10000個文檔（實際上獲取所有）
          clusterId
        );
        setFolderDocuments(data.documents);
        console.log(`Loaded ${data.documents.length} documents for folder: ${folderName}`);
      } catch (error) {
        console.error('Failed to fetch folder documents:', error);
        showPCMessage('載入資料夾文件失敗', 'error');
        setFolderDocuments([]);
      } finally {
        setIsLoadingFolderDocs(false);
      }
    }
  }, [showPCMessage]);

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
      { key: 'filename', label: '名稱', sortable: true, cellClassName: 'truncate', className: 'w-[45%]'},
      { key: 'file_type', label: '類型 / 大小', sortable: true, className: 'w-[15%]' },
      { key: 'updated_at', label: '修改時間', sortable: true, className: 'w-[15%]' },
      { key: 'status', label: '狀態', sortable: true, className: 'w-[12%]' },
      { key: 'actions', label: '操作', sortable: false, className: 'w-[8%]' },
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
        { 
          key: 'filename', 
          cellClassName: 'max-w-0', 
          render: (doc) => {
            // 獲取文件類型標籤（與 FolderDetailView 一致）
            let typeTag;
            const fileType = doc.file_type || '';
            if (fileType.includes('pdf')) {
              typeTag = { label: 'PDF', bg: 'bg-red-100', text: 'text-red-600', border: 'border-red-600' };
            } else if (fileType.includes('image')) {
              typeTag = { label: 'IMG', bg: 'bg-purple-100', text: 'text-purple-600', border: 'border-purple-600' };
            } else if (fileType.includes('word') || fileType.includes('document')) {
              typeTag = { label: 'DOC', bg: 'bg-blue-100', text: 'text-blue-600', border: 'border-blue-600' };
            } else if (fileType.includes('excel') || fileType.includes('spreadsheet')) {
              typeTag = { label: 'XLS', bg: 'bg-green-100', text: 'text-green-600', border: 'border-green-600' };
            } else {
              typeTag = { label: 'FILE', bg: 'bg-gray-100', text: 'text-gray-600', border: 'border-gray-600' };
            }

            return (
              <div className="flex items-center gap-3 min-w-0">
                {/* 類型標籤 */}
                <span className={`flex-shrink-0 px-2 py-1 text-[10px] font-black border-2 ${typeTag.border} ${typeTag.bg} ${typeTag.text}`}>
                  {typeTag.label}
                </span>
                
                {/* 縮略圖或圖標 */}
                <div className="flex-shrink-0 w-10 h-10 border-2 border-neo-black flex items-center justify-center overflow-hidden bg-gray-50">
                  <ImageThumbnail doc={doc} />
                </div>
                
                {/* 檔名 */}
                <span 
                  title={doc.filename} 
                  className="truncate block min-w-0 flex-1 font-bold text-sm"
                >
                  {doc.filename}
                </span>
              </div>
            );
          } 
        },
        { 
          key: 'file_type', 
          render: (doc) => (
            <div className="flex flex-col">
              <span className="text-sm font-medium" title={doc.file_type ?? undefined}>
                {mapMimeTypeToSimpleType(doc.file_type)}
              </span>
              <span className="text-xs text-gray-500">
                {formatBytes(doc.size ?? undefined)}
              </span>
            </div>
          ) 
        },
        { 
          key: 'updated_at', 
          render: (doc) => (
            <div className="text-sm" title={formatDate(doc.updated_at)}>
              {formatCompactDate(doc.updated_at)}
            </div>
          ) 
        },
        {
            key: 'status',
            render: (doc) => {
                // 獲取狀態標籤（與 FolderDetailView 一致）
                let statusConfig;
                switch (doc.status) {
                    case 'completed':
                    case 'analysis_completed':
                        statusConfig = { label: '✓ 已完成', color: 'bg-neo-primary text-neo-white' };
                        break;
                    case 'uploaded':
                    case 'pending_extraction':
                    case 'text_extracted':
                    case 'pending_analysis':
                        statusConfig = { label: '⏳ 待處理', color: 'bg-gray-300 text-gray-700' };
                        break;
                    case 'analyzing':
                        statusConfig = { label: '🔄 分析中', color: 'bg-neo-warn text-neo-black' };
                        break;
                    case 'processing_error':
                    case 'analysis_failed':
                    case 'extraction_failed':
                        statusConfig = { label: '✕ 失敗', color: 'bg-neo-error text-neo-white' };
                        break;
                    default:
                        statusConfig = { label: '⚠ 檢查', color: 'bg-neo-warn text-neo-black' };
                }
                
                return (
                    <span className={`inline-block px-2 py-1 text-[10px] font-black border-2 border-neo-black ${statusConfig.color}`}>
                        {statusConfig.label}
                    </span>
                );
            }
        },
    ];
    return definitions.reduce((acc, item) => {
        acc[item.key] = item;
        return acc;
    }, {} as Record<keyof Document | 'actions' | 'selector', typeof definitions[0]>);
}, []);

  const fetchDocumentsData = useCallback(async (showMessage: boolean = false) => {
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
      console.log(`Fetching with activeQuickFilter: ${activeQuickFilter}, filterStatus: ${filterStatus}, apiStatusParam: ${apiStatusParam}, clusterId: ${selectedClusterId}`);
      const data = await getDocuments(debouncedSearchTerm, apiStatusParam, undefined, sortKey , sortConfig?.direction, skip, itemsPerPage, selectedClusterId);
      if (isMounted.current) {
        setDocuments(data.documents);
        setTotalDocuments(data.totalCount);

        // 自動將處理中的文檔加入監測列表
        const processingDocs = data.documents.filter(doc =>
          ['pending_extraction', 'text_extracted', 'pending_analysis', 'analyzing'].includes(doc.status)
        );
        if (processingDocs.length > 0) {
          setProcessingDocuments(prev => {
            const newSet = new Set(prev);
            processingDocs.forEach(doc => newSet.add(doc.id));
            return newSet;
          });
        }

        if (!hasLoadedInitialData.current) {
          hasLoadedInitialData.current = true;
          showPCMessage('文件列表已載入', 'info');
        } else if (showMessage) {
          // 只有明確要求時才顯示更新消息
          showPCMessage('文件列表已更新', 'info');
        }
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
  }, [debouncedSearchTerm, filterStatus, sortConfig, showPCMessage, currentPage, itemsPerPage, activeQuickFilter, selectedClusterId]);

  useEffect(() => {
    isMounted.current = true;
    fetchDocumentsData();
    return () => { isMounted.current = false; };
  }, [fetchDocumentsData]);

  // 監聽聚類完成事件，退出資料夾視圖並刷新數據
  useEffect(() => {
    const handleClusteringComplete = () => {
      console.log('📢 DocumentsPage: 收到聚類完成事件，重置資料夾視圖');
      // 退出資料夾視圖，因為重新分類後舊的 cluster_id 已經不存在了
      setShowFolderDetail(false);
      setSelectedClusterId(undefined);
      setSelectedFolderName(null);
      setFolderDocuments([]);
      // 刷新文檔列表
      fetchDocumentsData(true);
    };
    
    window.addEventListener('clustering-complete', handleClusteringComplete);
    return () => {
      window.removeEventListener('clustering-complete', handleClusteringComplete);
    };
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
    const files = event.target.files;
    if (!files || files.length === 0) {
      showPCMessage('未選擇任何文件', 'info');
      return;
    }

    setIsUploading(true);
    let successCount = 0;
    let errorCount = 0;

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      showPCMessage(`正在上傳第 ${i + 1}/${files.length} 個文件: ${file.name}...`, 'info');
      try {
        const uploadedDoc = await uploadDocument(file);
        showPCMessage(`文件 ${uploadedDoc.filename} 上傳成功!`, 'success');
        successCount++;
      } catch (error: any) {
        errorCount++;
        console.error('Failed to upload document:', file.name, error);
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
      }
    }

    setIsUploading(false);
    if (fileInputRef.current) {
      fileInputRef.current.value = ''; // 清空選擇，以便下次能觸發 change 事件
    }

    if (successCount > 0) {
      if (currentPage !== 1) {
        setCurrentPage(1); // 如果有成功上傳的，且不在第一頁，跳轉到第一頁
      } else {
        fetchDocumentsData(); // 否則，直接刷新當前頁數據
      }
    }
    
    if (files.length > 1) { // 如果上傳了多個檔案，給一個總結提示
        let summaryMessage = `批量上傳完成：${successCount} 個成功`;
        if (errorCount > 0) {
            summaryMessage += `，${errorCount} 個失敗。`;
        } else {
            summaryMessage += `。`;
        }
        showPCMessage(summaryMessage, errorCount > 0 ? 'info' : 'success');
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
    showPCMessage(`正在為文件 ${doc.filename} 重新分析...`, 'info');
    try {
      // 從全局設定獲取 AI 選項
      const aiOptions: TriggerDocumentProcessingOptions = {};
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
      showPCMessage(`已觸發文件 ${doc.filename} 的重新分析。`, 'success');

      // 如果文件開始處理，將其加入監測列表
      if (['pending_extraction', 'text_extracted', 'pending_analysis', 'analyzing'].includes(updatedDoc.status)) {
        setProcessingDocuments(prev => new Set(prev).add(doc.id));
      }

    } catch (error: any) {
      const errorMessage = error.response?.data?.detail || error.message || '未知錯誤';
      showPCMessage(`重新分析失敗: ${errorMessage}`, 'error');
      console.error(`Error retrying analysis for doc ${doc.id}:`, error);
    } finally {
      setIsProcessing(prev => ({ ...prev, [doc.id]: false }));
    }
  };

  const canRetryAnalysis = useCallback((doc: Document): boolean => {
    // 允許對已失敗和已完成的文檔進行重新分析
    return [
      'analysis_failed',
      'processing_error',
      'extraction_failed',
      'analysis_completed',
      'completed'
    ].includes(doc.status);
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
    <div className="h-screen flex overflow-hidden bg-neo-bg">
      {/* 左側：統計與資料夾面板 */}
      <DocumentsWithClustering
        onClusterFilterChange={handleClusterFilterChange}
        currentClusterId={selectedClusterId}
        onRefreshDocuments={fetchDocumentsData}
      />
      
      {/* 主內容區 */}
      <div className="flex-1 flex flex-col overflow-hidden relative">
        {/* 條件渲染：資料夾詳細視圖或列表視圖 */}
        {showFolderDetail && selectedFolderName ? (
          <FolderDetailView
            key={`folder-${selectedClusterId}-${folderDocuments.length}`}
            folderName={selectedFolderName}
            clusterId={selectedClusterId || ''}
            documents={folderDocuments}
            onBack={() => {
              setShowFolderDetail(false);
              setSelectedClusterId(undefined);
              setSelectedFolderName(null);
              setFolderDocuments([]);
            }}
            onSelectDocuments={setSelectedDocuments}
            onDeleteSelected={handleDeleteSelected}
            selectedDocuments={selectedDocuments}
            isDeleting={isDeleting || isLoadingFolderDocs}
          />
        ) : (
          <>
        {/* Header */}
        <header className="h-16 bg-neo-white border-b-3 border-neo-black flex items-center justify-between px-6 shrink-0">
          {/* 顯示當前路徑/篩選 */}
          <div className="flex items-center gap-2 font-bold text-sm">
            <span className="text-gray-400">🏠</span>
            <span className="text-gray-400">/</span>
            <span>{activeQuickFilter === 'all' ? 'Inbox' : quickFilterOptions.find(f => f.id === activeQuickFilter)?.label || 'All'}</span>
            {selectedClusterId && (
              <React.Fragment>
                <span className="text-gray-400">/</span>
                <span className="bg-neo-black text-neo-white px-2 py-0.5">Filtered</span>
              </React.Fragment>
            )}
          </div>
          
          {/* 操作按鈕 */}
          <div className="flex gap-3">
            <button
              onClick={() => setIsGmailImporterVisible(true)}
              className="bg-neo-white text-neo-black border-3 border-neo-black px-3 py-1 text-xs font-display font-bold uppercase shadow-neo-md hover:shadow-neo-hover hover:-translate-x-0.5 hover:-translate-y-0.5 active:shadow-none active:translate-x-1 active:translate-y-1 transition-all duration-100 flex items-center gap-2"
            >
              <span>📧</span> Import Gmail
            </button>
            <button
              onClick={triggerFileInput}
              disabled={isUploading}
              className="bg-neo-primary text-neo-black border-3 border-neo-black px-3 py-1 text-xs font-display font-bold uppercase shadow-neo-md hover:bg-neo-hover hover:shadow-neo-hover hover:-translate-x-0.5 hover:-translate-y-0.5 active:shadow-none active:translate-x-1 active:translate-y-1 transition-all duration-100 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              <span>⬆️</span> {isUploading ? 'Uploading...' : 'Upload New'}
            </button>
          </div>
        </header>

        {/* 內容捲動區 */}
        <div className="flex-1 overflow-y-auto">
          {/* 文件上傳拖放區域 */}
          <FileDropZone
            onFilesSelected={(files) => {
              const event = { target: { files } } as unknown as React.ChangeEvent<HTMLInputElement>;
              handleFileUpload(event);
            }}
            isUploading={isUploading}
            pendingCount={documents.filter(d => ['uploaded', 'pending_extraction', 'pending_analysis', 'analyzing'].includes(d.status)).length}
            onClusteringComplete={() => fetchDocumentsData(true)}
          />

          {/* 文件列表區域 */}
          <section className="px-6">
            <div className="flex items-center justify-between mb-4 pt-6">
              <h2 className="font-display font-bold text-xl flex items-center gap-2 text-neo-black uppercase">
                <span>🕐</span> Recent Activity
              </h2>
              {/* 列表專屬操作 */}
              <div className="flex gap-2">
                <input
                  type="text"
                  placeholder="Filter list..."
                  value={searchTerm}
                  onChange={(e) => {
                    setSearchTerm(e.target.value);
                    setCurrentPage(1);
                  }}
                  className="border-2 border-neo-black px-3 py-1 text-sm font-bold outline-none focus:bg-neo-hover focus:bg-opacity-20 transition-colors"
                />
                <button
                  onClick={handleDeleteSelected}
                  disabled={selectedDocuments.size === 0 || isDeleting}
                  className="bg-neo-error text-neo-white border-3 border-neo-black px-3 py-1 text-xs font-display font-bold uppercase shadow-neo-md hover:shadow-neo-hover hover:-translate-x-0.5 hover:-translate-y-0.5 active:shadow-none active:translate-x-1 active:translate-y-1 transition-all duration-100 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                >
                  <span>🗑️</span> Delete
                </button>
              </div>
            </div>

            {/* Loading 狀態 */}
            {isLoading && documents.length === 0 && !hasLoadedInitialData.current && (
              <div className="text-center py-10 bg-neo-white border-3 border-neo-black shadow-neo-lg">
                <div className="animate-spin rounded-full h-12 w-12 border-3 border-neo-black border-t-transparent mx-auto mb-4"></div>
                <p className="text-lg font-bold text-gray-500">正在努力加載您的文件...</p>
              </div>
            )}

            {/* 空狀態 */}
            {(!isLoading || filteredDocuments.length > 0 || hasLoadedInitialData.current) && filteredDocuments.length === 0 && (debouncedSearchTerm || activeQuickFilter !== 'all') && (
              <div className="text-center py-10 bg-neo-white border-3 border-neo-black shadow-neo-lg">
                <p className="text-xl font-bold text-gray-500">
                  {debouncedSearchTerm ? '找不到符合搜索條件的文件。' : '找不到符合篩選條件的文件。'}
                </p>
              </div>
            )}

            {/* 文件表格 */}
            {(!isLoading || documents.length > 0 || hasLoadedInitialData.current) && (
              <div className="bg-neo-white border-3 border-neo-black shadow-neo-lg overflow-hidden">
                <Table 
                  headers={tableHeadersForTableComponent}
                  sortConfig={sortConfig} 
                  isSelectAllChecked={filteredDocuments.length > 0 && selectedDocuments.size === filteredDocuments.filter(doc => doc.id).length}
                  onSelectAllChange={handleSelectAll} 
                  isSelectAllDisabled={filteredDocuments.length === 0 || isDeleting || isLoading} 
                >
                  {filteredDocuments.map((doc) => (
                    <TableRow key={doc.id} className={selectedDocuments.has(doc.id) ? 'bg-neo-hover bg-opacity-20 hover:bg-opacity-30' : 'hover:bg-neo-hover hover:bg-opacity-20 transition-colors'}>
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
                            <TableCell 
                              key={`${header.key}-${doc.id}`} 
                              className={`relative overflow-visible ${header.className || tableCellRenderers.actions?.cellClassName || ''}`}
                            >
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
              </div>
            )}
          </section>
        </div>

        {/* 隱藏的 file input */}
        <input
          ref={fileInputRef}
          type="file"
          onChange={handleFileUpload}
          style={{ display: 'none' }}
          multiple
          accept=".txt,.pdf,.jpg,.jpeg,.png,.gif,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.md"
        />

        {/* Gmail 導入對話框 */}
        <GmailImporter
          visible={isGmailImporterVisible}
          onClose={() => setIsGmailImporterVisible(false)}
          onSuccess={() => {
            setCurrentPage(1);
            fetchDocumentsData(true);
          }}
        />

        {/* Modals */}
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
        </>
        )}
      </div>
    </div>
  );
};

export default DocumentsPage;