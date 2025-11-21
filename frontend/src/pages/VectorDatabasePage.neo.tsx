import React, { useState, useEffect, useCallback } from 'react';
import {
  DatabaseOutlined,
  ThunderboltOutlined,
  SearchOutlined,
  SyncOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  InfoCircleOutlined,
  FileTextOutlined,
  ReloadOutlined,
  DesktopOutlined,
  SettingOutlined,
  EyeOutlined,
} from '@ant-design/icons';
import type {
  VectorDatabaseStats,
  DatabaseConnectionStatus,
  Document,
  BasicResponse
} from '../types/apiTypes';
import {
  getVectorDatabaseStats,
  getDatabaseConnectionStatus,
  batchProcessDocuments,
  initializeVectorDatabase,
  processDocumentToVector,
  deleteDocumentFromVectorDB,
  deleteDocumentsFromVectorDB,
  performHybridSearch,
} from '../services/vectorDBService';
import {
  getEmbeddingModelConfig,
  configureEmbeddingModel,
} from '../services/embeddingService';
import type { EmbeddingModelConfig } from '../types/apiTypes';
import {
  getDocuments,
} from '../services/documentService';
import ConfirmDialog from '../components/ConfirmDialog';

interface VectorDatabasePageNeoProps {
  showPCMessage: (message: string, type?: 'success' | 'error' | 'info') => void;
}

type TabView = 'data' | 'search' | 'config';

const VectorDatabasePageNeo: React.FC<VectorDatabasePageNeoProps> = ({ showPCMessage }) => {
  // 狀態管理
  const [vectorStats, setVectorStats] = useState<VectorDatabaseStats | null>(null);
  const [connectionStatus, setConnectionStatus] = useState<DatabaseConnectionStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [activeTab, setActiveTab] = useState<TabView>('data');
  
  // 文檔向量化相關狀態
  const [documents, setDocuments] = useState<Document[]>([]);
  const [totalDocuments, setTotalDocuments] = useState(0);
  const [selectedDocIds, setSelectedDocIds] = useState<string[]>([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isBatchDeleting, setIsBatchDeleting] = useState(false);
  const [filterText, setFilterText] = useState('');
  
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 10,
  });
  
  const [isDeletingFromVectorDB, setIsDeletingFromVectorDB] = useState<string | null>(null);
  
  // 確認對話框狀態
  const [deleteSingleConfirmDialog, setDeleteSingleConfirmDialog] = useState<{
    isOpen: boolean;
    docId: string | null;
  }>({ isOpen: false, docId: null });
  
  const [deleteBatchConfirmDialog, setDeleteBatchConfirmDialog] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  // Search Playground 相關狀態
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [similarityThreshold, setSimilarityThreshold] = useState(0.4);
  const [topK, setTopK] = useState(10);
  const [searchStrategy, setSearchStrategy] = useState<'hybrid' | 'summary_only' | 'chunks_only'>('hybrid');
  const [searchTime, setSearchTime] = useState(0);
  const [selectedResult, setSelectedResult] = useState<any | null>(null);
  const [showDetailModal, setShowDetailModal] = useState(false);
  const [searchResultPage, setSearchResultPage] = useState(1);
  const searchResultsPerPage = 5;

  // Configuration 相關狀態
  const [modelConfig, setModelConfig] = useState<EmbeddingModelConfig | null>(null);
  const [selectedDevice, setSelectedDevice] = useState<'cpu' | 'cuda' | 'auto'>('auto');
  const [isConfiguringDevice, setIsConfiguringDevice] = useState(false);

  // 加載數據的函數
  const loadData = useCallback(async (page = pagination.current, pageSize = pagination.pageSize) => {
    try {
      setIsLoading(true);
      const [stats, connStatus, docsResponse] = await Promise.allSettled([
        getVectorDatabaseStats(),
        getDatabaseConnectionStatus(),
        getDocuments('', 'all', undefined, 'created_at', 'desc', (page - 1) * pageSize, pageSize)
      ]);

      if (stats.status === 'fulfilled') {
        console.log('✅ 向量數據庫統計:', stats.value);
        setVectorStats(stats.value);
      } else {
        console.error('❌ 獲取向量數據庫統計失敗:', stats.reason);
        setVectorStats(null);
        showPCMessage('獲取向量數據庫統計失敗', 'error');
      }

      if (connStatus.status === 'fulfilled') {
        console.log('✅ 數據庫連接狀態:', connStatus.value);
        setConnectionStatus(connStatus.value);
      } else {
        console.error('❌ 獲取數據庫連接狀態失敗:', connStatus.reason);
        showPCMessage('獲取數據庫連接狀態失敗', 'error');
      }

      if (docsResponse.status === 'fulfilled') {
        console.log('✅ 文檔列表加載:', {
          count: docsResponse.value.documents.length,
          total: docsResponse.value.totalCount,
          page: page
        });
        setDocuments(docsResponse.value.documents);
        setTotalDocuments(docsResponse.value.totalCount);
      } else {
        console.error('❌ 獲取文檔列表失敗:', docsResponse.reason);
        showPCMessage('獲取文檔列表失敗', 'error');
      }

    } catch (error) {
      console.error('加載向量數據庫頁面數據失敗:', error);
      showPCMessage('載入數據失敗', 'error');
    } finally {
      setIsLoading(false);
    }
  }, [showPCMessage, pagination]);

  // 刷新數據
  const refreshData = useCallback(async () => {
    setIsRefreshing(true);
    await loadData(1, pagination.pageSize);
    setIsRefreshing(false);
    showPCMessage('數據已刷新', 'success');
  }, [loadData, showPCMessage, pagination.pageSize]);

  // 批量向量化文檔
  const handleBatchVectorize = async () => {
    if (selectedDocIds.length === 0) {
      showPCMessage('請選擇要向量化的文檔', 'error');
      return;
    }

    try {
      setIsProcessing(true);
      await batchProcessDocuments(selectedDocIds);
      showPCMessage(`已開始向量化 ${selectedDocIds.length} 個文檔`, 'success');
      setSelectedDocIds([]);
      
      setTimeout(() => {
        refreshData();
      }, 2000);
    } catch (error) {
      console.error('批量向量化失敗:', error);
      showPCMessage('批量向量化失敗', 'error');
    } finally {
      setIsProcessing(false);
    }
  };

  // 單個文檔向量化
  const handleSingleVectorize = async (docId: string) => {
    try {
      await processDocumentToVector(docId);
      showPCMessage('文檔向量化已開始', 'success');
      setTimeout(() => {
        refreshData();
      }, 2000);
    } catch (error) {
      console.error('文檔向量化失敗:', error);
      showPCMessage('文檔向量化失敗', 'error');
    }
  };

  // 從向量數據庫刪除單個文檔
  const handleDeleteFromVectorDB = (docId: string) => {
    setDeleteSingleConfirmDialog({ isOpen: true, docId });
  };
  
  const confirmDeleteSingleFromVectorDB = async () => {
    if (!deleteSingleConfirmDialog.docId) return;
    
    setIsDeleting(true);
    try {
      setIsDeletingFromVectorDB(deleteSingleConfirmDialog.docId);
      await deleteDocumentFromVectorDB(deleteSingleConfirmDialog.docId);
      showPCMessage('已從向量數據庫刪除文檔向量', 'success');
      await refreshData(); 
    } catch (error) {
      console.error('從向量數據庫刪除失敗:', error);
      showPCMessage('從向量數據庫刪除失敗', 'error');
    } finally {
      setIsDeleting(false);
      setIsDeletingFromVectorDB(null);
      setDeleteSingleConfirmDialog({ isOpen: false, docId: null });
    }
  };

  // 從向量數據庫批量刪除選中文檔的向量
  const handleBatchDeleteFromVectorDB = () => {
    if (selectedDocIds.length === 0) {
      showPCMessage('請選擇要從向量數據庫刪除的文檔', 'info');
      return;
    }
    setDeleteBatchConfirmDialog(true);
  };
  
  const confirmBatchDeleteFromVectorDB = async () => {
    setIsBatchDeleting(true);
    setIsDeleting(true);
    try {
      const response: BasicResponse = await deleteDocumentsFromVectorDB(selectedDocIds);
      if (response.success) {
        showPCMessage(`成功刪除 ${selectedDocIds.length} 個文檔的向量`, 'success');
      } else {
        showPCMessage(response.message || '批量刪除向量時發生錯誤', 'error');
      }
      setSelectedDocIds([]);
      await refreshData();
    } catch (error) {
      console.error('批量刪除向量失敗:', error);
      showPCMessage('批量刪除向量操作失敗', 'error');
    } finally {
      setIsBatchDeleting(false);
      setIsDeleting(false);
      setDeleteBatchConfirmDialog(false);
    }
  };

  // 選中當前頁面所有文檔
  const selectCurrentPage = () => {
    const currentPageIds = documents.map(doc => doc.id);
    const combinedIds = [...selectedDocIds, ...currentPageIds];
    const newSelected = Array.from(new Set(combinedIds));
    setSelectedDocIds(newSelected);
  };

  // 取消選中當前頁面所有文檔
  const deselectCurrentPage = () => {
    const currentPageIds = documents.map(doc => doc.id);
    setSelectedDocIds(selectedDocIds.filter(id => !currentPageIds.includes(id)));
  };

  // 檢查當前頁面是否全選
  const isCurrentPageSelected = documents.length > 0 && documents.every(doc => selectedDocIds.includes(doc.id));

  // 加載模型配置
  const loadModelConfig = useCallback(async () => {
    try {
      const config = await getEmbeddingModelConfig();
      setModelConfig(config);
      setSelectedDevice(config.current_device as 'cpu' | 'cuda' | 'auto');
    } catch (error) {
      console.error('獲取模型配置失敗:', error);
      showPCMessage('獲取模型配置失敗', 'error');
    }
  }, [showPCMessage]);

  // 配置設備
  const handleConfigureDevice = async () => {
    try {
      setIsConfiguringDevice(true);
      await configureEmbeddingModel(selectedDevice);
      await loadModelConfig();
      await refreshData();
      showPCMessage(`成功切換到 ${selectedDevice.toUpperCase()} 設備`, 'success');
    } catch (error) {
      console.error('配置設備失敗:', error);
      showPCMessage('配置設備失敗', 'error');
    } finally {
      setIsConfiguringDevice(false);
    }
  };

  // 執行真實搜索
  const handleRunSearch = async () => {
    if (!searchQuery.trim()) {
      showPCMessage('請輸入搜索查詢', 'error');
      return;
    }
    
    try {
      setIsSearching(true);
      const startTime = performance.now();
      
      console.log('🔍 開始搜索:', {
        query: searchQuery.trim(),
        topK,
        similarityThreshold,
        strategy: searchStrategy
      });
      
      const results = await performHybridSearch(
        searchQuery,
        topK,
        similarityThreshold,
        searchStrategy
      );
      
      const endTime = performance.now();
      setSearchTime((endTime - startTime) / 1000);
      
      console.log('✅ 搜索完成:', {
        resultCount: results.length,
        time: `${((endTime - startTime) / 1000).toFixed(2)}s`,
        sampleResults: results.slice(0, 2).map(r => ({
          document_id: r.document_id,
          document_filename: r.document_filename,
          vector_type: r.vector_type,
          similarity_score: r.similarity_score,
          has_chunk_text: !!r.chunk_text,
          has_summary_text: !!r.summary_text,
          chunk_text_preview: r.chunk_text?.substring(0, 50),
          summary_text_preview: r.summary_text?.substring(0, 50)
        }))
      });
      
      setSearchResults(results);
      setSearchResultPage(1); // 重置到第一頁
      showPCMessage(`找到 ${results.length} 個結果`, 'success');
    } catch (error) {
      console.error('❌ 搜索失敗:', error);
      showPCMessage('搜索失敗', 'error');
      setSearchResults([]);
    } finally {
      setIsSearching(false);
    }
  };

  // 組件掛載時加載數據
  useEffect(() => {
    loadData();
    loadModelConfig();
  }, []);

  // 過濾文檔
  const filteredDocuments = documents.filter(doc => 
    doc.filename.toLowerCase().includes(filterText.toLowerCase())
  );

  if (isLoading) {
    return (
      <div className="min-h-screen bg-neo-bg flex items-center justify-center">
        <div className="border-3 border-neo-black bg-white p-8 shadow-neo-lg">
          <div className="animate-spin rounded-full h-12 w-12 border-3 border-neo-black border-t-transparent mx-auto mb-4"></div>
          <p className="font-bold text-neo-black">加載向量數據庫信息...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 min-h-screen bg-neo-bg flex flex-col gap-6">
      {/* Dashboard Header (狀態總覽) */}
      <header className="bg-white border-3 border-neo-black shadow-neo-lg p-6 flex flex-col md:flex-row justify-between items-start md:items-center gap-6">
        <div>
          <h1 className="font-display text-3xl font-bold uppercase flex items-center gap-3">
            <DatabaseOutlined className="text-neo-active" style={{ fontSize: '32px' }} />
            Vector Core
          </h1>
          <div className="flex gap-2 mt-3 flex-wrap">
            <div className={`border-2 border-neo-black px-3 py-1 text-xs font-bold rounded-full flex items-center gap-1 ${
              connectionStatus?.mongodb.connected ? 'bg-neo-hover text-neo-black' : 'bg-neo-critical text-white'
            }`}>
              {connectionStatus?.mongodb.connected ? <CheckCircleOutlined /> : <CloseCircleOutlined />}
              MONGO: {connectionStatus?.mongodb.connected ? 'CONNECTED' : 'DISCONNECTED'}
            </div>
            <div className={`border-2 border-neo-black px-3 py-1 text-xs font-bold rounded-full flex items-center gap-1 ${
              vectorStats?.embedding_model.device === 'cuda' ? 'bg-neo-hover text-neo-black' : 'bg-gray-300 text-neo-black'
            }`}>
              {vectorStats?.embedding_model.device === 'cuda' ? <CheckCircleOutlined /> : <DesktopOutlined />}
              {vectorStats?.embedding_model.device?.toUpperCase() || 'CPU'}: ACTIVE
            </div>
            <div className="border-2 border-neo-black px-3 py-1 text-xs font-bold rounded-full bg-neo-black text-white flex items-center gap-1">
              <ThunderboltOutlined />
              {vectorStats?.embedding_model.device === 'cuda' ? 'GPU ACCELERATED' : 'CPU MODE'}
            </div>
          </div>
        </div>

        {/* 核心指標 (KPI) - 真實 API 數據 */}
        <div className="flex gap-4 flex-wrap">
          <div className="border-2 border-neo-black p-3 bg-gray-50 min-w-[120px]">
            <div className="text-xs font-bold text-gray-500 uppercase">Vectors</div>
            <div className="text-2xl font-mono font-bold">
              {vectorStats?.total_vectors !== undefined ? vectorStats.total_vectors.toLocaleString() : '0'}
            </div>
            <div className="text-[10px] text-gray-400 font-bold mt-1">
              {vectorStats?.collection_name || 'N/A'}
            </div>
          </div>
          <div className="border-2 border-neo-black p-3 bg-gray-50 min-w-[120px]">
            <div className="text-xs font-bold text-gray-500 uppercase">Documents</div>
            <div className="text-2xl font-mono font-bold">
              {totalDocuments > 0 ? totalDocuments.toLocaleString() : '0'}
            </div>
            <div className="text-[10px] text-gray-400 font-bold mt-1">
              {documents.length > 0 ? `${documents.length} 加載中` : '無文檔'}
            </div>
          </div>
          <div className="border-2 border-neo-black p-3 bg-neo-active text-white min-w-[120px]">
            <div className="text-xs font-bold uppercase opacity-80">Dimension</div>
            <div className="text-2xl font-mono font-bold">
              {vectorStats?.vector_dimension || vectorStats?.embedding_model?.vector_dimension || '0'}
            </div>
            <div className="text-[10px] opacity-70 font-bold mt-1">
              {vectorStats?.embedding_model?.model_loaded ? 'ACTIVE' : 'IDLE'}
            </div>
          </div>
        </div>
      </header>

      {/* 主要操作區 (Tabs System) */}
      <div className="flex-1 flex flex-col">
        
        {/* Tab Navigation */}
        <div className="flex gap-2 px-4">
          <button
            className={`px-5 py-3 font-bold border-2 transition-all ${
              activeTab === 'data'
                ? 'bg-white border-neo-black border-b-white text-neo-black relative z-10 translate-y-[3px]'
                : 'border-transparent text-gray-600 hover:text-neo-black'
            }`}
            onClick={() => setActiveTab('data')}
          >
            <FileTextOutlined className="mr-2" />
            Data Management
          </button>
          <button
            className={`px-5 py-3 font-bold border-2 transition-all ${
              activeTab === 'search'
                ? 'bg-white border-neo-black border-b-white text-neo-black relative z-10 translate-y-[3px]'
                : 'border-transparent text-gray-600 hover:text-neo-black'
            }`}
            onClick={() => setActiveTab('search')}
          >
            <SearchOutlined className="mr-2" />
            Search Playground
          </button>
          <button
            className={`px-5 py-3 font-bold border-2 transition-all ${
              activeTab === 'config'
                ? 'bg-white border-neo-black border-b-white text-neo-black relative z-10 translate-y-[3px]'
                : 'border-transparent text-gray-600 hover:text-neo-black'
            }`}
            onClick={() => setActiveTab('config')}
          >
            <SettingOutlined className="mr-2" />
            Configuration
          </button>
        </div>

        {/* Tab Content Container */}
        <div className="bg-white border-3 border-neo-black shadow-neo-lg flex-1 relative z-0">
          
          {/* VIEW A: Data Management (數據管理列表) */}
          {activeTab === 'data' && (
            <div className="p-6">
              
              {/* Toolbar */}
              <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
                <div className="flex gap-2 flex-wrap">
                  <button
                    onClick={handleBatchVectorize}
                    disabled={selectedDocIds.length === 0 || isProcessing}
                    className="px-4 py-2 text-sm bg-neo-primary text-neo-black border-2 border-neo-black shadow-[3px_3px_0px_0px_black] hover:-translate-x-[2px] hover:-translate-y-[2px] hover:shadow-[5px_5px_0px_0px_black] active:translate-x-[2px] active:translate-y-[2px] active:shadow-none transition-all font-bold uppercase disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                  >
                    <SyncOutlined className={isProcessing ? 'animate-spin' : ''} />
                    {selectedDocIds.length > 0 ? `Re-Index Selected (${selectedDocIds.length})` : 'Re-Index All'}
                  </button>
                  <button
                    onClick={handleBatchDeleteFromVectorDB}
                    disabled={selectedDocIds.length === 0 || isBatchDeleting}
                    className="px-4 py-2 text-sm bg-neo-critical text-white border-2 border-neo-black shadow-[3px_3px_0px_0px_black] hover:-translate-x-[2px] hover:-translate-y-[2px] hover:shadow-[5px_5px_0px_0px_black] active:translate-x-[2px] active:translate-y-[2px] active:shadow-none transition-all font-bold uppercase disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                  >
                    <CloseCircleOutlined />
                    Prune Deleted
                  </button>
                </div>
                <div className="relative w-full md:w-64">
                  <SearchOutlined className="absolute left-3 top-1/2 -translate-y-1/2 text-neo-black" />
                  <input
                    type="text"
                    placeholder="Filter files..."
                    value={filterText}
                    onChange={(e) => setFilterText(e.target.value)}
                    className="w-full border-2 border-neo-black py-2 pl-9 pr-2 font-bold text-sm focus:outline-none focus:shadow-[4px_4px_0px_0px_#29bf12] transition-shadow"
                  />
                </div>
              </div>

              {/* Selection Controls */}
              <div className="mb-4 flex gap-2 flex-wrap items-center">
                <button
                  onClick={isCurrentPageSelected ? deselectCurrentPage : selectCurrentPage}
                  disabled={documents.length === 0}
                  className="px-3 py-1 text-xs bg-gray-100 border-2 border-neo-black font-bold hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isCurrentPageSelected ? '取消選中當前頁面' : '選中當前頁面'}
                </button>
                <span className="text-sm font-bold text-gray-600">
                  已選中 {selectedDocIds.length} 個文檔
                </span>
              </div>

              {/* Table */}
              <div className="border-2 border-neo-black overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="bg-neo-black text-white font-display uppercase">
                    <tr>
                      <th className="p-3 w-12">
                        <input
                          type="checkbox"
                          checked={isCurrentPageSelected}
                          onChange={(e) => {
                            if (e.target.checked) {
                              selectCurrentPage();
                            } else {
                              deselectCurrentPage();
                            }
                          }}
                          className="w-4 h-4 accent-neo-hover cursor-pointer"
                        />
                      </th>
                      <th className="p-3">Filename</th>
                      <th className="p-3 w-32">Vector Status</th>
                      <th className="p-3 w-24 text-center">Vectors</th>
                      <th className="p-3 w-32 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y-2 divide-neo-black font-bold">
                    {filteredDocuments.length === 0 ? (
                      <tr>
                        <td colSpan={5} className="p-8 text-center text-gray-500">
                          {filterText ? '沒有找到匹配的文檔' : '沒有文檔'}
                        </td>
                      </tr>
                    ) : (
                      filteredDocuments.map((doc) => {
                        const isCurrentDocDeleting = isDeletingFromVectorDB === doc.id;
                        const isSelected = selectedDocIds.includes(doc.id);

                        return (
                          <tr
                            key={doc.id}
                            className={`transition-colors ${
                              doc.vector_status === 'failed' ? 'bg-red-50' : 'hover:bg-neo-hover'
                            }`}
                          >
                            <td className="p-3">
                              <input
                                type="checkbox"
                                checked={isSelected}
                                onChange={(e) => {
                                  if (e.target.checked) {
                                    setSelectedDocIds(prev => [...prev, doc.id]);
                                  } else {
                                    setSelectedDocIds(prev => prev.filter(id => id !== doc.id));
                                  }
                                }}
                                className="w-4 h-4 accent-neo-black cursor-pointer"
                              />
                            </td>
                            <td className="p-3 font-mono text-sm">{doc.filename}</td>
                            <td className="p-3">
                              {doc.vector_status === 'vectorized' && (
                                <span className="border-2 border-neo-black px-2 py-1 text-xs font-bold rounded-full bg-neo-hover text-neo-black inline-flex items-center gap-1">
                                  COMPLETED
                                </span>
                              )}
                              {doc.vector_status === 'not_vectorized' && (
                                <span className="border-2 border-neo-black px-2 py-1 text-xs font-bold rounded-full bg-gray-200 text-neo-black inline-flex items-center gap-1">
                                  NOT VECTORIZED
                                </span>
                              )}
                              {doc.vector_status === 'processing' && (
                                <span className="border-2 border-neo-black px-2 py-1 text-xs font-bold rounded-full bg-neo-active text-white inline-flex items-center gap-1">
                                  <SyncOutlined className="animate-spin" />
                                  PROCESSING
                                </span>
                              )}
                              {doc.vector_status === 'failed' && (
                                <span className="border-2 border-neo-black px-2 py-1 text-xs font-bold rounded-full bg-neo-critical text-white inline-flex items-center gap-1">
                                  FAILED
                                </span>
                              )}
                              {!doc.vector_status && (
                                <span className="border-2 border-neo-black px-2 py-1 text-xs font-bold rounded-full bg-gray-300 text-neo-black inline-flex items-center gap-1">
                                  UNKNOWN
                                </span>
                              )}
                            </td>
                            <td className="p-3 text-center font-mono">
                              {doc.vector_status === 'vectorized' ? (
                                <span className="text-neo-black">
                                  {(doc as any).chunk_count || '—'}
                                </span>
                              ) : (
                                <span className="text-gray-400">0</span>
                              )}
                            </td>
                            <td className="p-3 text-right">
                              <div className="flex gap-1 justify-end">
                                {(doc.vector_status === 'not_vectorized' || doc.vector_status === 'failed' || !doc.vector_status) && (
                                  <button
                                    onClick={() => handleSingleVectorize(doc.id)}
                                    className="p-1 hover:text-neo-active transition-colors"
                                    title="向量化"
                                  >
                                    <ThunderboltOutlined />
                                  </button>
                                )}
                                {doc.vector_status === 'vectorized' && (
                                  <>
                                    <button
                                      onClick={() => handleSingleVectorize(doc.id)}
                                      className="p-1 hover:text-neo-active transition-colors"
                                      title="重新向量化"
                                    >
                                      <SyncOutlined />
                                    </button>
                                    <button
                                      onClick={() => handleDeleteFromVectorDB(doc.id)}
                                      className="p-1 hover:text-neo-critical transition-colors"
                                      title="移除向量"
                                      disabled={isCurrentDocDeleting}
                                    >
                                      {isCurrentDocDeleting ? (
                                        <SyncOutlined className="animate-spin" />
                                      ) : (
                                        <CloseCircleOutlined />
                                      )}
                                    </button>
                                  </>
                                )}
                              </div>
                            </td>
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>

              {/* Pagination */}
              <div className="flex flex-col sm:flex-row justify-between items-center mt-4 gap-4">
                <span className="text-xs font-bold text-gray-500 uppercase">
                  SHOWING {((pagination.current - 1) * pagination.pageSize) + 1}-{Math.min(pagination.current * pagination.pageSize, totalDocuments)} OF {totalDocuments}
                </span>
                <div className="flex gap-1 flex-wrap justify-center">
                  {/* Previous Button */}
                  <button
                    onClick={() => {
                      if (pagination.current > 1) {
                        const newPage = pagination.current - 1;
                        setPagination({ ...pagination, current: newPage });
                        loadData(newPage, pagination.pageSize);
                      }
                    }}
                    disabled={pagination.current === 1}
                    className="w-8 h-8 border-2 border-neo-black flex items-center justify-center hover:bg-neo-black hover:text-white transition-colors font-bold disabled:opacity-30 disabled:cursor-not-allowed"
                  >
                    &lt;
                  </button>
                  
                  {/* Page Numbers */}
                  {(() => {
                    const totalPages = Math.ceil(totalDocuments / pagination.pageSize);
                    const pages = [];
                    const maxVisible = 5;
                    
                    let startPage = Math.max(1, pagination.current - Math.floor(maxVisible / 2));
                    let endPage = Math.min(totalPages, startPage + maxVisible - 1);
                    
                    if (endPage - startPage < maxVisible - 1) {
                      startPage = Math.max(1, endPage - maxVisible + 1);
                    }
                    
                    for (let i = startPage; i <= endPage; i++) {
                      pages.push(
                        <button
                          key={i}
                          onClick={() => {
                            setPagination({ ...pagination, current: i });
                            loadData(i, pagination.pageSize);
                          }}
                          className={`w-8 h-8 border-2 border-neo-black font-bold flex items-center justify-center transition-colors ${
                            i === pagination.current
                              ? 'bg-neo-active text-white'
                              : 'bg-white hover:bg-neo-black hover:text-white'
                          }`}
                        >
                          {i}
                        </button>
                      );
                    }
                    
                    return pages;
                  })()}
                  
                  {/* Next Button */}
                  <button
                    onClick={() => {
                      const maxPage = Math.ceil(totalDocuments / pagination.pageSize);
                      if (pagination.current < maxPage) {
                        const newPage = pagination.current + 1;
                        setPagination({ ...pagination, current: newPage });
                        loadData(newPage, pagination.pageSize);
                      }
                    }}
                    disabled={pagination.current >= Math.ceil(totalDocuments / pagination.pageSize)}
                    className="w-8 h-8 border-2 border-neo-black flex items-center justify-center hover:bg-neo-black hover:text-white transition-colors font-bold disabled:opacity-30 disabled:cursor-not-allowed"
                  >
                    &gt;
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* VIEW B: Search Playground (搜尋實驗室) */}
          {activeTab === 'search' && (
            <div className="min-h-[600px] flex flex-col md:flex-row">
              
              {/* 左側：調參區 */}
              <div className="w-full md:w-1/3 border-r-0 md:border-r-3 border-neo-black p-6 bg-gray-50 flex flex-col gap-6 overflow-y-auto">
                <h3 className="font-display font-bold text-xl border-b-2 border-neo-black pb-2">Parameters</h3>
                
                {/* Search Input */}
                <div>
                  <label className="text-xs font-bold uppercase mb-2 block text-gray-700">Test Query</label>
                  <textarea
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full border-2 border-neo-black p-3 font-bold h-24 resize-none focus:outline-none focus:shadow-[4px_4px_0px_0px_#29bf12] transition-shadow"
                    placeholder="Enter semantic query..."
                  />
                </div>

                {/* Similarity Threshold Slider */}
                <div>
                  <div className="flex justify-between mb-2">
                    <label className="text-xs font-bold uppercase text-gray-700">Similarity Threshold</label>
                    <span className="font-mono font-bold text-sm">{similarityThreshold.toFixed(1)}</span>
                  </div>
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.1"
                    value={similarityThreshold}
                    onChange={(e) => setSimilarityThreshold(parseFloat(e.target.value))}
                    className="w-full h-1 bg-neo-black appearance-none cursor-pointer"
                    style={{
                      accentColor: '#08bdbd'
                    }}
                  />
                </div>
                
                {/* Top K Slider */}
                <div>
                  <div className="flex justify-between mb-2">
                    <label className="text-xs font-bold uppercase text-gray-700">Top K Results</label>
                    <span className="font-mono font-bold text-sm">{topK}</span>
                  </div>
                  <input
                    type="range"
                    min="1"
                    max="50"
                    step="1"
                    value={topK}
                    onChange={(e) => setTopK(parseInt(e.target.value))}
                    className="w-full h-1 bg-neo-black appearance-none cursor-pointer"
                    style={{
                      accentColor: '#08bdbd'
                    }}
                  />
                </div>

                {/* Strategy Toggles */}
                <div className="space-y-2">
                  <label className="text-xs font-bold uppercase block text-gray-700">Strategy</label>
                  <div className="flex flex-col gap-2">
                    <label className={`flex items-center gap-2 border-2 border-neo-black p-3 cursor-pointer transition-colors ${
                      searchStrategy === 'hybrid' ? 'bg-neo-hover' : 'bg-white hover:bg-gray-100'
                    }`}>
                      <input
                        type="radio"
                        name="strat"
                        checked={searchStrategy === 'hybrid'}
                        onChange={() => setSearchStrategy('hybrid')}
                        className="accent-neo-black w-4 h-4"
                      />
                      <span className="font-bold text-sm">Two-Stage Hybrid (Rec.)</span>
                    </label>
                    <label className={`flex items-center gap-2 border-2 border-neo-black p-3 cursor-pointer transition-colors ${
                      searchStrategy === 'summary_only' ? 'bg-neo-hover' : 'bg-white hover:bg-gray-100'
                    }`}>
                      <input
                        type="radio"
                        name="strat"
                        checked={searchStrategy === 'summary_only'}
                        onChange={() => setSearchStrategy('summary_only')}
                        className="accent-neo-black w-4 h-4"
                      />
                      <span className="font-bold text-sm">Summary Only</span>
                    </label>
                    <label className={`flex items-center gap-2 border-2 border-neo-black p-3 cursor-pointer transition-colors ${
                      searchStrategy === 'chunks_only' ? 'bg-neo-hover' : 'bg-white hover:bg-gray-100'
                    }`}>
                      <input
                        type="radio"
                        name="strat"
                        checked={searchStrategy === 'chunks_only'}
                        onChange={() => setSearchStrategy('chunks_only')}
                        className="accent-neo-black w-4 h-4"
                      />
                      <span className="font-bold text-sm">Chunks Only</span>
                    </label>
                  </div>
                </div>

                <button
                  onClick={handleRunSearch}
                  disabled={isSearching || !searchQuery.trim()}
                  className="w-full py-3 bg-neo-primary text-neo-black border-2 border-neo-black shadow-[3px_3px_0px_0px_black] hover:-translate-x-[2px] hover:-translate-y-[2px] hover:shadow-[5px_5px_0px_0px_black] active:translate-x-[2px] active:translate-y-[2px] active:shadow-none transition-all font-bold uppercase disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 mt-auto"
                >
                  {isSearching ? (
                    <>
                      <SyncOutlined className="animate-spin" />
                      搜索中...
                    </>
                  ) : (
                    <>
                      <SearchOutlined />
                      Run Test
                    </>
                  )}
                </button>
              </div>

              {/* 右側：結果預覽 */}
              <div className="flex-1 p-6 bg-white flex flex-col">
                <h3 className="font-display font-bold text-xl border-b-2 border-neo-black pb-2 mb-4 flex justify-between items-center shrink-0">
                  <span>Results</span>
                  {searchResults.length > 0 && (
                    <span className="text-sm font-mono bg-neo-black text-neo-hover px-3 py-1 border-2 border-neo-black">
                      {searchResults.length} Found ({searchTime.toFixed(2)}s)
                    </span>
                  )}
                </h3>

                {searchResults.length === 0 ? (
                  <div className="flex flex-col items-center justify-center flex-1 text-gray-400">
                    <SearchOutlined style={{ fontSize: '48px' }} className="mb-4" />
                    <p className="font-bold">運行測試查詢以查看結果</p>
                  </div>
                ) : (
                  <>
                    <div className="space-y-3 flex-1 overflow-y-auto mb-4">
                      {searchResults
                        .slice((searchResultPage - 1) * searchResultsPerPage, searchResultPage * searchResultsPerPage)
                        .map((result, index) => {
                          const actualIndex = (searchResultPage - 1) * searchResultsPerPage + index;
                      const isChunkResult = result.vector_type === 'chunk';
                      const isSummaryResult = result.vector_type === 'summary';
                      
                      return (
                        <div
                          key={`${result.document_id}-${result.chunk_index || index}`}
                          className="border-2 border-neo-black p-4 shadow-[4px_4px_0px_#e5e7eb] hover:shadow-[4px_4px_0px_#08bdbd] transition-shadow cursor-pointer"
                          onClick={() => {
                            setSelectedResult(result);
                            setShowDetailModal(true);
                          }}
                        >
                          {/* Header: Score & Rank */}
                          <div className="flex justify-between items-start mb-3">
                            <div className="flex gap-2 items-center">
                              <div className="font-mono text-xs bg-gray-200 px-2 py-1 border border-neo-black">
                                Score: {((result.similarity_score || 0) * 100).toFixed(1)}%
                              </div>
                              {result.ranking_score && result.ranking_score !== result.similarity_score && (
                                <div className="font-mono text-xs bg-neo-hover px-2 py-1 border border-neo-black">
                                  Rank: {((result.ranking_score || 0) * 100).toFixed(1)}%
                                </div>
                              )}
                            </div>
                            <div className="font-bold text-xs text-neo-active">#{actualIndex + 1}</div>
                          </div>

                          {/* Type Tags */}
                          <div className="mb-3 flex gap-2 flex-wrap">
                            <span className={`text-xs font-bold px-2 py-1 border-2 border-neo-black ${
                              isSummaryResult ? 'bg-neo-active text-white' : 
                              isChunkResult ? 'bg-neo-primary text-neo-black' : 
                              'bg-gray-200 text-neo-black'
                            }`}>
                              {isSummaryResult ? '摘要向量' : isChunkResult ? '文本塊' : '向量'}
                            </span>
                            {isChunkResult && result.chunk_index !== undefined && (
                              <span className="text-xs font-bold px-2 py-1 border-2 border-neo-black bg-gray-100 text-neo-black">
                                第 {result.chunk_index + 1} 塊
                              </span>
                            )}
                            {result.search_stage && (
                              <span className="text-xs font-bold px-2 py-1 border-2 border-neo-black bg-neo-hover text-neo-black">
                                {result.search_stage === 'stage1' ? '階段1' : 
                                 result.search_stage === 'stage2' ? '階段2' : '單階段'}
                              </span>
                            )}
                          </div>

                          {/* Content - 縮略顯示 */}
                          <div className="mb-3">
                            <p className="text-sm font-bold leading-relaxed line-clamp-3">
                              {(() => {
                                const content = isChunkResult && result.chunk_text 
                                  ? result.chunk_text 
                                  : isSummaryResult && result.summary_text 
                                    ? result.summary_text 
                                    : result.chunk_text || result.summary_text || '無內容';
                                
                                // 顯示前150個字符作為預覽
                                return content.length > 150 
                                  ? content.substring(0, 150) + '...' 
                                  : content;
                              })()}
                            </p>
                            <button className="text-xs font-bold text-neo-active hover:underline mt-1">
                              點擊查看完整內容 →
                            </button>
                          </div>

                          {/* Keywords - 縮略顯示 */}
                          {(result.key_terms && result.key_terms.length > 0) && (
                            <div className="mb-2">
                              <span className="text-xs font-bold text-gray-600 mr-2">關鍵詞:</span>
                              {result.key_terms.slice(0, 3).map((term: string, idx: number) => (
                                <span 
                                  key={idx} 
                                  className="inline-block text-xs font-bold px-2 py-1 border border-neo-black bg-gray-50 text-neo-black mr-1"
                                >
                                  {term}
                                </span>
                              ))}
                              {result.key_terms.length > 3 && (
                                <span className="text-xs text-gray-500 font-bold">+{result.key_terms.length - 3}個</span>
                              )}
                            </div>
                          )}

                          {/* Document Info - 精簡顯示 */}
                          <div className="text-xs text-gray-500 font-mono pt-2 border-t border-gray-200 flex items-center gap-2">
                            <FileTextOutlined className="text-gray-400" />
                            <span className="text-neo-black font-bold truncate flex-1">
                              {result.document_filename || `ID: ${result.document_id?.slice(0, 8)}...` || 'N/A'}
                            </span>
                          </div>
                        </div>
                      );
                    })}
                    </div>
                    
                    {/* 搜索結果分頁 */}
                    <div className="shrink-0 pt-4 border-t border-gray-200 flex justify-between items-center">
                      <span className="text-xs font-bold text-gray-500 uppercase">
                        顯示 {((searchResultPage - 1) * searchResultsPerPage) + 1}-{Math.min(searchResultPage * searchResultsPerPage, searchResults.length)} / {searchResults.length}
                      </span>
                      <div className="flex gap-1">
                        <button
                          onClick={() => setSearchResultPage(Math.max(1, searchResultPage - 1))}
                          disabled={searchResultPage === 1}
                          className="w-8 h-8 border-2 border-neo-black flex items-center justify-center hover:bg-neo-black hover:text-white transition-colors font-bold disabled:opacity-30 disabled:cursor-not-allowed"
                        >
                          &lt;
                        </button>
                        {(() => {
                          const totalPages = Math.ceil(searchResults.length / searchResultsPerPage);
                          const pages = [];
                          for (let i = 1; i <= totalPages; i++) {
                            pages.push(
                              <button
                                key={i}
                                onClick={() => setSearchResultPage(i)}
                                className={`w-8 h-8 border-2 border-neo-black font-bold flex items-center justify-center transition-colors ${
                                  i === searchResultPage
                                    ? 'bg-neo-active text-white'
                                    : 'bg-white hover:bg-neo-black hover:text-white'
                                }`}
                              >
                                {i}
                              </button>
                            );
                          }
                          return pages;
                        })()}
                        <button
                          onClick={() => setSearchResultPage(Math.min(Math.ceil(searchResults.length / searchResultsPerPage), searchResultPage + 1))}
                          disabled={searchResultPage >= Math.ceil(searchResults.length / searchResultsPerPage)}
                          className="w-8 h-8 border-2 border-neo-black flex items-center justify-center hover:bg-neo-black hover:text-white transition-colors font-bold disabled:opacity-30 disabled:cursor-not-allowed"
                        >
                          &gt;
                        </button>
                      </div>
                    </div>
                  </>
                )}
              </div>
            </div>
          )}

          {/* VIEW C: Configuration (配置) */}
          {activeTab === 'config' && (
            <div className="p-6 min-h-[600px]">
              <div className="space-y-6">
                {/* 當前模型信息 */}
                <div className="border-3 border-neo-black p-6 bg-white shadow-neo-md">
                  <h3 className="font-display font-bold text-xl mb-4 uppercase flex items-center gap-2">
                    <InfoCircleOutlined />
                    Current Model Configuration
                  </h3>
                  <div className="space-y-3">
                    <div>
                      <span className="text-xs font-bold text-gray-500 uppercase block mb-1">Model Name</span>
                      <div className="border-2 border-neo-black p-3 font-mono text-sm bg-gray-50">
                        {modelConfig?.current_model || vectorStats?.embedding_model.model_name || 'N/A'}
                      </div>
                    </div>
                    <div>
                      <span className="text-xs font-bold text-gray-500 uppercase block mb-1">Status</span>
                      <div className="flex items-center gap-2">
                        {modelConfig?.model_loaded || vectorStats?.embedding_model.model_loaded ? (
                          <span className="border-2 border-neo-black px-3 py-1 text-xs font-bold rounded-full bg-neo-hover text-neo-black inline-flex items-center gap-1">
                            <CheckCircleOutlined />
                            LOADED
                          </span>
                        ) : (
                          <span className="border-2 border-neo-black px-3 py-1 text-xs font-bold rounded-full bg-gray-300 text-neo-black inline-flex items-center gap-1">
                            NOT LOADED
                          </span>
                        )}
                      </div>
                    </div>
                    <div>
                      <span className="text-xs font-bold text-gray-500 uppercase block mb-1">Vector Dimension</span>
                      <div className="border-2 border-neo-black p-3 font-mono text-sm bg-gray-50">
                        {vectorStats?.vector_dimension || vectorStats?.embedding_model?.vector_dimension || 'N/A'}
                      </div>
                    </div>
                  </div>
                </div>

                {/* GPU 信息 */}
                {modelConfig?.gpu_info && (
                  <div className="border-3 border-neo-black p-6 bg-white shadow-neo-md">
                    <h3 className="font-display font-bold text-xl mb-4 uppercase flex items-center gap-2">
                      <ThunderboltOutlined className="text-neo-primary" />
                      GPU Information
                    </h3>
                    <div className="space-y-3">
                      <div>
                        <span className="text-xs font-bold text-gray-500 uppercase block mb-1">Device Name</span>
                        <div className="border-2 border-neo-black p-3 font-bold text-sm bg-gray-50">
                          {modelConfig.gpu_info.device_name}
                        </div>
                      </div>
                      <div>
                        <span className="text-xs font-bold text-gray-500 uppercase block mb-1">Memory Total</span>
                        <div className="border-2 border-neo-black p-3 font-bold text-sm bg-gray-50">
                          {modelConfig.gpu_info.memory_total}
                        </div>
                      </div>
                      <div>
                        <span className="text-xs font-bold text-gray-500 uppercase block mb-1">PyTorch Version</span>
                        <div className="border-2 border-neo-black p-3 font-mono text-sm bg-gray-50">
                          {modelConfig.gpu_info.pytorch_version}
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {/* 設備配置 */}
                <div className="border-3 border-neo-black p-6 bg-white shadow-neo-md">
                  <h3 className="font-display font-bold text-xl mb-4 uppercase flex items-center gap-2">
                    <SettingOutlined />
                    Compute Device
                  </h3>
                  <p className="text-sm text-gray-600 mb-4 font-bold">
                    當前設備: <span className="text-neo-active">{(modelConfig?.current_device || vectorStats?.embedding_model.device || 'N/A').toUpperCase()}</span>
                  </p>
                  
                  <div className="space-y-3 mb-6">
                    <label className={`flex items-center gap-3 border-2 border-neo-black p-4 cursor-pointer transition-all ${
                      selectedDevice === 'auto' ? 'bg-neo-hover' : 'bg-white hover:bg-gray-50'
                    }`}>
                      <input 
                        type="radio" 
                        checked={selectedDevice === 'auto'}
                        onChange={() => setSelectedDevice('auto')}
                        disabled={isConfiguringDevice}
                        className="accent-neo-black w-5 h-5 cursor-pointer" 
                      />
                      <div>
                        <div className="font-bold text-sm uppercase">Auto Select</div>
                        <div className="text-xs text-gray-600">系統自動選擇最佳設備</div>
                      </div>
                    </label>

                    {(modelConfig?.available_devices?.includes('cuda') || vectorStats?.embedding_model.device === 'cuda') && (
                      <label className={`flex items-center gap-3 border-2 border-neo-black p-4 cursor-pointer transition-all ${
                        selectedDevice === 'cuda' ? 'bg-neo-hover' : 'bg-white hover:bg-gray-50'
                      }`}>
                        <input 
                          type="radio" 
                          checked={selectedDevice === 'cuda'}
                          onChange={() => setSelectedDevice('cuda')}
                          disabled={isConfiguringDevice}
                          className="accent-neo-black w-5 h-5 cursor-pointer" 
                        />
                        <div>
                          <div className="font-bold text-sm uppercase flex items-center gap-2">
                            <ThunderboltOutlined className="text-neo-primary" />
                            CUDA (GPU)
                          </div>
                          <div className="text-xs text-gray-600">推薦，性能最佳</div>
                        </div>
                      </label>
                    )}

                    <label className={`flex items-center gap-3 border-2 border-neo-black p-4 cursor-pointer transition-all ${
                      selectedDevice === 'cpu' ? 'bg-neo-hover' : 'bg-white hover:bg-gray-50'
                    }`}>
                      <input 
                        type="radio" 
                        checked={selectedDevice === 'cpu'}
                        onChange={() => setSelectedDevice('cpu')}
                        disabled={isConfiguringDevice}
                        className="accent-neo-black w-5 h-5 cursor-pointer" 
                      />
                      <div>
                        <div className="font-bold text-sm uppercase flex items-center gap-2">
                          <DesktopOutlined />
                          CPU
                        </div>
                        <div className="text-xs text-gray-600">兼容性最佳，速度較慢</div>
                      </div>
                    </label>
                  </div>

                  <button
                    onClick={handleConfigureDevice}
                    disabled={isConfiguringDevice || selectedDevice === modelConfig?.current_device}
                    className="w-full py-3 bg-neo-primary text-neo-black border-2 border-neo-black shadow-[3px_3px_0px_0px_black] hover:-translate-x-[2px] hover:-translate-y-[2px] hover:shadow-[5px_5px_0px_0px_black] active:translate-x-[2px] active:translate-y-[2px] active:shadow-none transition-all font-bold uppercase disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                  >
                    {isConfiguringDevice ? (
                      <>
                        <SyncOutlined className="animate-spin" />
                        配置中...
                      </>
                    ) : selectedDevice === modelConfig?.current_device ? (
                      <>
                        <CheckCircleOutlined />
                        當前設備
                      </>
                    ) : (
                      <>
                        <CheckCircleOutlined />
                        應用設備配置
                      </>
                    )}
                  </button>
                </div>
              </div>
            </div>
          )}

        </div>
      </div>

      {/* 確認對話框 */}
      <ConfirmDialog
        isOpen={deleteSingleConfirmDialog.isOpen}
        onClose={() => setDeleteSingleConfirmDialog({ isOpen: false, docId: null })}
        onConfirm={confirmDeleteSingleFromVectorDB}
        title="確認刪除"
        content="您確定要從向量數據庫中刪除此文檔的向量嗎？這不會刪除原始文檔。"
        confirmText="確認刪除"
        cancelText="取消"
        isDanger
        isLoading={isDeleting}
      />

      <ConfirmDialog
        isOpen={deleteBatchConfirmDialog}
        onClose={() => setDeleteBatchConfirmDialog(false)}
        onConfirm={confirmBatchDeleteFromVectorDB}
        title={`確認批量刪除 ${selectedDocIds.length} 個文檔的向量`}
        content="您確定要從向量數據庫中刪除所選文檔的向量嗎？這不會刪除原始文檔。"
        confirmText="確認刪除"
        cancelText="取消"
        isDanger
        isLoading={isDeleting}
      />

      {/* 搜索結果詳細視圖模態框 */}
      {showDetailModal && selectedResult && (
        <div
          className="fixed inset-0 bg-black/80 flex items-center justify-center p-4 z-50"
          onClick={() => setShowDetailModal(false)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-4xl max-h-[90vh] bg-white border-3 border-neo-black shadow-[8px_8px_0px_0px_black] flex flex-col"
          >
            {/* Header */}
            <div className="bg-neo-active text-white px-6 py-4 border-b-3 border-neo-black flex items-center justify-between shrink-0">
              <div className="flex items-center gap-3">
                <EyeOutlined className="text-xl" />
                <h2 className="font-display font-bold text-lg uppercase">向量化詳細內容</h2>
              </div>
              <button
                onClick={() => setShowDetailModal(false)}
                className="w-10 h-10 flex items-center justify-center bg-neo-critical text-white border-2 border-neo-black shadow-neo-sm hover:bg-red-700 transition-colors font-bold text-xl"
              >
                ✕
              </button>
            </div>

            {/* Body */}
            <div className="flex-1 overflow-y-auto p-6 bg-neo-bg space-y-6">
              {/* 文檔基本信息 */}
              <div className="border-2 border-neo-black bg-white p-4">
                <h3 className="font-bold text-lg mb-3 pb-2 border-b-2 border-neo-black uppercase">文檔信息</h3>
                <div className="space-y-2">
                  <div className="flex items-start gap-3">
                    <span className="font-bold text-sm text-gray-600 min-w-[100px]">文件名:</span>
                    <span className="font-bold text-sm flex-1">{selectedResult.document_filename || 'N/A'}</span>
                  </div>
                  <div className="flex items-start gap-3">
                    <span className="font-bold text-sm text-gray-600 min-w-[100px]">文檔 ID:</span>
                    <span className="font-mono text-xs flex-1 bg-gray-50 p-2 border border-gray-300">{selectedResult.document_id}</span>
                  </div>
                  {selectedResult.content_type && (
                    <div className="flex items-start gap-3">
                      <span className="font-bold text-sm text-gray-600 min-w-[100px]">內容類型:</span>
                      <span className="font-bold text-sm">{selectedResult.content_type}</span>
                    </div>
                  )}
                </div>
              </div>

              {/* 向量類型和分數 */}
              <div className="border-2 border-neo-black bg-white p-4">
                <h3 className="font-bold text-lg mb-3 pb-2 border-b-2 border-neo-black uppercase">向量信息</h3>
                <div className="space-y-3">
                  <div className="flex items-center gap-3 flex-wrap">
                    <span className="font-bold text-sm text-gray-600">向量類型:</span>
                    <span className={`text-sm font-bold px-3 py-1 border-2 border-neo-black ${
                      selectedResult.vector_type === 'summary' ? 'bg-neo-active text-white' : 
                      selectedResult.vector_type === 'chunk' ? 'bg-neo-primary text-neo-black' : 
                      'bg-gray-200 text-neo-black'
                    }`}>
                      {selectedResult.vector_type === 'summary' ? '摘要向量' : 
                       selectedResult.vector_type === 'chunk' ? '文本塊向量' : '向量'}
                    </span>
                    {selectedResult.chunk_index !== undefined && (
                      <span className="text-sm font-bold px-3 py-1 border-2 border-neo-black bg-gray-100 text-neo-black">
                        第 {selectedResult.chunk_index + 1} 塊
                      </span>
                    )}
                    {selectedResult.search_stage && (
                      <span className="text-sm font-bold px-3 py-1 border-2 border-neo-black bg-neo-hover text-neo-black">
                        {selectedResult.search_stage === 'stage1' ? '階段1檢索' : 
                         selectedResult.search_stage === 'stage2' ? '階段2檢索' : '單階段檢索'}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="font-bold text-sm text-gray-600">相似度分數:</span>
                    <span className="font-mono font-bold text-lg text-neo-active">
                      {((selectedResult.similarity_score || 0) * 100).toFixed(2)}%
                    </span>
                  </div>
                  {selectedResult.ranking_score && selectedResult.ranking_score !== selectedResult.similarity_score && (
                    <div className="flex items-center gap-3">
                      <span className="font-bold text-sm text-gray-600">排序分數:</span>
                      <span className="font-mono font-bold text-lg text-neo-primary">
                        {((selectedResult.ranking_score || 0) * 100).toFixed(2)}%
                      </span>
                    </div>
                  )}
                </div>
              </div>

              {/* 向量化文本內容 */}
              <div className="border-2 border-neo-black bg-white p-4">
                <h3 className="font-bold text-lg mb-3 pb-2 border-b-2 border-neo-black uppercase">向量化內容</h3>
                <div className="bg-gray-50 p-4 border-2 border-gray-300 font-bold text-sm leading-relaxed whitespace-pre-wrap max-h-[300px] overflow-y-auto">
                  {selectedResult.vector_type === 'chunk' && selectedResult.chunk_text
                    ? selectedResult.chunk_text
                    : selectedResult.vector_type === 'summary' && selectedResult.summary_text
                      ? selectedResult.summary_text
                      : selectedResult.chunk_text || selectedResult.summary_text || '無內容'}
                </div>
              </div>

              {/* 關鍵詞 */}
              {selectedResult.key_terms && selectedResult.key_terms.length > 0 && (
                <div className="border-2 border-neo-black bg-white p-4">
                  <h3 className="font-bold text-lg mb-3 pb-2 border-b-2 border-neo-black uppercase">關鍵詞</h3>
                  <div className="flex flex-wrap gap-2">
                    {selectedResult.key_terms.map((term: string, idx: number) => (
                      <span
                        key={idx}
                        className="px-3 py-1 text-sm font-bold border-2 border-neo-black bg-neo-hover text-neo-black"
                      >
                        {term}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* 知識領域 */}
              {selectedResult.knowledge_domains && selectedResult.knowledge_domains.length > 0 && (
                <div className="border-2 border-neo-black bg-white p-4">
                  <h3 className="font-bold text-lg mb-3 pb-2 border-b-2 border-neo-black uppercase">知識領域</h3>
                  <div className="flex flex-wrap gap-2">
                    {selectedResult.knowledge_domains.map((domain: string, idx: number) => (
                      <span
                        key={idx}
                        className="px-3 py-1 text-sm font-bold border-2 border-neo-black bg-neo-active text-white"
                      >
                        {domain}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* 元數據 */}
              {selectedResult.metadata && Object.keys(selectedResult.metadata).length > 0 && (
                <div className="border-2 border-neo-black bg-white p-4">
                  <h3 className="font-bold text-lg mb-3 pb-2 border-b-2 border-neo-black uppercase">元數據</h3>
                  <div className="bg-gray-900 text-green-400 p-4 font-mono text-xs overflow-x-auto">
                    <pre>{JSON.stringify(selectedResult.metadata, null, 2)}</pre>
                  </div>
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="border-t-3 border-neo-black p-4 bg-white flex justify-end shrink-0">
              <button
                onClick={() => setShowDetailModal(false)}
                className="px-6 py-2 bg-neo-primary text-neo-black border-2 border-neo-black shadow-neo-sm hover:bg-neo-hover hover:shadow-none hover:translate-x-1 hover:translate-y-1 transition-all font-bold uppercase"
              >
                關閉
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default VectorDatabasePageNeo;
