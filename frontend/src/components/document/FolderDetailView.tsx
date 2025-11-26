import React, { useState, useEffect, useRef } from 'react';
import { Document } from '../../types/apiTypes';
import { DocumentTypeIcon } from './index';
import { formatBytes, formatDate } from '../../utils/documentFormatters';
import { apiClient } from '../../services/apiClient';
import DocumentDetailsModal from './DocumentDetailsModal';

interface FolderDetailViewProps {
  folderName: string;
  clusterId: string;
  documents: Document[];
  onBack: () => void;
  onSelectDocuments: (docIds: Set<string>) => void;
  onDeleteSelected: () => void;
  selectedDocuments: Set<string>;
  isDeleting: boolean;
}

// 全局圖片緩存（整個應用共享）- LRU 策略
class ImageCache {
  private cache = new Map<string, string>();
  private maxSize: number;

  constructor(maxSize: number = 50) {
    this.maxSize = maxSize; // 預設最多緩存 50 張圖片
  }

  get(key: string): string | undefined {
    const value = this.cache.get(key);
    if (value) {
      // LRU: 重新插入到末尾（表示最近使用）
      this.cache.delete(key);
      this.cache.set(key, value);
    }
    return value;
  }

  set(key: string, value: string): void {
    // 如果已存在，先刪除（會重新插入到末尾）
    if (this.cache.has(key)) {
      this.cache.delete(key);
    }
    
    // 檢查是否超過上限
    if (this.cache.size >= this.maxSize) {
      // 刪除最舊的項目（Map 的第一個）
      const firstKey = this.cache.keys().next().value;
      if (firstKey) {
        const oldUrl = this.cache.get(firstKey);
        if (oldUrl) {
          URL.revokeObjectURL(oldUrl); // 釋放記憶體
        }
        this.cache.delete(firstKey);
      }
    }
    
    this.cache.set(key, value);
  }

  clear(): void {
    // 清空所有緩存並釋放記憶體
    this.cache.forEach(url => URL.revokeObjectURL(url));
    this.cache.clear();
  }

  size(): number {
    return this.cache.size;
  }
}

const imageCache = new ImageCache(50); // 最多緩存 50 張圖片

// 圖片縮略圖組件
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
          imageCache.set(doc.id, objectUrl); // 存入緩存
          setImageSrc(objectUrl);
          setLoading(false);
        }
      })
      .catch(err => {
        if (isMounted) {
          console.error('Error loading thumbnail:', err);
          setError(true);
          setLoading(false);
        }
      });

    return () => {
      isMounted = false;
      // 注意：不再立即清理 URL，讓緩存持續有效
    };
  }, [doc.id, doc.file_type]);

  if (error || !doc.file_type?.startsWith('image/')) {
    return (
      <DocumentTypeIcon
        fileType={doc.file_type || null}
        fileName={doc.filename}
        className="text-5xl text-gray-300"
      />
    );
  }

  if (loading || !imageSrc) {
    return (
      <div className="w-full h-full flex items-center justify-center bg-gray-100">
        <div className="animate-spin rounded-full h-8 w-8 border-3 border-neo-black border-t-transparent"></div>
      </div>
    );
  }

  return (
    <img
      src={imageSrc}
      alt={doc.filename}
      className="w-full h-full object-cover group-hover:scale-105 transition-transform"
    />
  );
};

const FolderDetailView: React.FC<FolderDetailViewProps> = ({
  folderName,
  clusterId,
  documents,
  onBack,
  onSelectDocuments,
  onDeleteSelected,
  selectedDocuments,
  isDeleting
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');
  const [currentPage, setCurrentPage] = useState(1);
  const [selectedDetail, setSelectedDetail] = useState<Document | null>(null);
  const [isDetailModalOpen, setIsDetailModalOpen] = useState(false);
  const [expandedDocId, setExpandedDocId] = useState<string | null>(null);
  const itemsPerPage = 15; // 統一每頁15個文件

  // 篩選文件
  const filteredDocs = documents.filter(doc =>
    doc.filename.toLowerCase().includes(searchTerm.toLowerCase())
  );

  // 分頁計算
  const totalPages = Math.ceil(filteredDocs.length / itemsPerPage);
  const startIndex = (currentPage - 1) * itemsPerPage;
  const endIndex = startIndex + itemsPerPage;
  const paginatedDocs = filteredDocs.slice(startIndex, endIndex);

  // 切換視圖、搜尋或文檔列表變化時重置頁碼
  useEffect(() => {
    setCurrentPage(1);
  }, [viewMode, searchTerm, documents]);

  // 打開文件詳情模態框
  const openDocumentDetail = (doc: Document, e: React.MouseEvent) => {
    e.stopPropagation(); // 防止觸發選擇
    setSelectedDetail(doc);
    setIsDetailModalOpen(true);
  };

  // 關閉文件詳情
  const closeDocumentDetail = () => {
    setIsDetailModalOpen(false);
    setSelectedDetail(null);
  };

  // 切換列表項展開
  const toggleExpandedDoc = (docId: string) => {
    setExpandedDocId(prev => prev === docId ? null : docId);
  };

  // 切換文件選擇
  const toggleDocumentSelection = (docId: string) => {
    const newSelection = new Set(selectedDocuments);
    if (newSelection.has(docId)) {
      newSelection.delete(docId);
    } else {
      newSelection.add(docId);
    }
    onSelectDocuments(newSelection);
  };

  // 獲取文件狀態標籤
  const getStatusTag = (doc: Document) => {
    switch (doc.status) {
      case 'completed':
      case 'analysis_completed':
        return { label: '✓ 已完成', color: 'bg-neo-primary text-neo-white' };
      case 'uploaded':
      case 'pending_extraction':
      case 'text_extracted':
      case 'pending_analysis':
        return { label: '⏳ 待處理', color: 'bg-gray-300 text-gray-700' };
      case 'analyzing':
        return { label: '🔄 分析中', color: 'bg-neo-warn text-neo-black' };
      case 'processing_error':
      case 'analysis_failed':
      case 'extraction_failed':
        return { label: '✕ 失敗', color: 'bg-neo-error text-neo-white' };
      default:
        return { label: '⚠ 檢查', color: 'bg-neo-warn text-neo-black' };
    }
  };

  // 獲取文件類型標籤樣式
  const getTypeTagStyle = (fileType: string | null | undefined) => {
    if (!fileType) return { label: 'FILE', bg: 'bg-gray-100', text: 'text-gray-600', border: 'border-gray-600' };
    
    if (fileType.includes('pdf')) {
      return { label: 'PDF', bg: 'bg-red-100', text: 'text-red-600', border: 'border-red-600' };
    } else if (fileType.includes('image')) {
      return { label: 'IMG', bg: 'bg-purple-100', text: 'text-purple-600', border: 'border-purple-600' };
    } else if (fileType.includes('word') || fileType.includes('document')) {
      return { label: 'DOC', bg: 'bg-blue-100', text: 'text-blue-600', border: 'border-blue-600' };
    } else if (fileType.includes('excel') || fileType.includes('spreadsheet')) {
      return { label: 'XLS', bg: 'bg-green-100', text: 'text-green-600', border: 'border-green-600' };
    } else {
      return { label: 'FILE', bg: 'bg-gray-100', text: 'text-gray-600', border: 'border-gray-600' };
    }
  };

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Header 與麵包屑 */}
      <header className="h-16 bg-neo-white border-b-3 border-neo-black flex items-center justify-between px-6 shrink-0">
        {/* 左側：麵包屑導航 */}
        <div className="flex items-center gap-3">
          <button
            onClick={onBack}
            className="bg-neo-white text-neo-black border-3 border-neo-black w-8 h-8 p-0 font-display font-bold shadow-neo-md hover:shadow-neo-hover hover:-translate-x-0.5 hover:-translate-y-0.5 active:shadow-none active:translate-x-1 active:translate-y-1 transition-all duration-100 flex items-center justify-center"
          >
            ←
          </button>
          <div className="flex items-center gap-2 text-sm font-bold text-gray-500">
            <span>Documents</span>
            <span>›</span>
            {/* 當前資料夾：醒目顯示 */}
            <div className="flex items-center gap-2 bg-neo-active text-white px-3 py-1 border-2 border-neo-black shadow-[2px_2px_0px_black]">
              <span>📁</span>
              <span className="font-display font-bold">{folderName}</span>
            </div>
          </div>
        </div>
      </header>

      {/* 主內容滾動區 */}
      <main className="flex-1 overflow-y-auto bg-neo-bg">
        
        {/* 工具列與批量操作 */}
        <div className="flex flex-col md:flex-row justify-between items-end md:items-center mb-6 gap-4 px-6 pt-6">
          {/* 左：搜尋 */}
          <div className="flex gap-2 w-full md:w-auto">
            <div className="relative flex-1 md:flex-none">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">🔍</span>
              <input
                type="text"
                placeholder="Filter files..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full md:w-64 border-3 border-neo-black px-4 pl-10 py-2 outline-none font-bold shadow-[4px_4px_0px_black] focus:bg-neo-hover focus:bg-opacity-20 transition-colors"
              />
            </div>
          </div>

          {/* 右：分頁、批量操作與視圖切換 */}
          <div className="flex items-center gap-3">
            {/* 分頁控制 */}
            {totalPages > 1 && (
              <div className="flex items-center gap-2 mr-4">
                <button
                  onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                  disabled={currentPage === 1}
                  className="bg-neo-white text-neo-black border-3 border-neo-black px-3 py-1.5 font-display font-bold shadow-neo-md hover:shadow-neo-hover hover:-translate-x-0.5 hover:-translate-y-0.5 active:shadow-none active:translate-x-1 active:translate-y-1 transition-all duration-100 disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:translate-x-0 disabled:hover:translate-y-0"
                >
                  ←
                </button>
                <div className="px-3 py-1.5 bg-neo-black text-neo-white border-3 border-neo-black font-display font-bold text-sm">
                  {currentPage}/{totalPages}
                </div>
                <button
                  onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                  disabled={currentPage === totalPages}
                  className="bg-neo-white text-neo-black border-3 border-neo-black px-3 py-1.5 font-display font-bold shadow-neo-md hover:shadow-neo-hover hover:-translate-x-0.5 hover:-translate-y-0.5 active:shadow-none active:translate-x-1 active:translate-y-1 transition-all duration-100 disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:translate-x-0 disabled:hover:translate-y-0"
                >
                  →
                </button>
              </div>
            )}

            {/* 批量操作提示 */}
            {selectedDocuments.size > 0 && (
              <div className="flex items-center gap-2 mr-4">
                <span className="text-xs font-bold bg-neo-black text-neo-white px-2 py-1">
                  {selectedDocuments.size} Selected
                </span>
                <button
                  onClick={onDeleteSelected}
                  disabled={isDeleting}
                  className="bg-neo-error text-neo-white border-3 border-neo-black px-3 py-1.5 text-xs font-display font-bold uppercase shadow-neo-md hover:shadow-neo-hover hover:-translate-x-0.5 hover:-translate-y-0.5 active:shadow-none active:translate-x-1 active:translate-y-1 transition-all duration-100 disabled:opacity-50 flex items-center gap-1"
                >
                  <span>🗑️</span> {isDeleting ? 'Deleting...' : 'Delete'}
                </button>
              </div>
            )}

            {/* 視圖切換 */}
            <div className="flex border-3 border-neo-black bg-neo-white shadow-[4px_4px_0px_black]">
              <button
                onClick={() => setViewMode('grid')}
                className={`p-2 transition-colors ${
                  viewMode === 'grid'
                    ? 'bg-neo-active text-neo-white'
                    : 'hover:bg-gray-100'
                } border-r-3 border-neo-black`}
              >
                <span className="text-lg">▦</span>
              </button>
              <button
                onClick={() => setViewMode('list')}
                className={`p-2 transition-colors ${
                  viewMode === 'list'
                    ? 'bg-neo-active text-neo-white'
                    : 'hover:bg-gray-100'
                }`}
              >
                <span className="text-lg">☰</span>
              </button>
            </div>
          </div>
        </div>

        {/* 文件網格 */}
        {viewMode === 'grid' ? (
          <>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4 px-6 pb-6">
            {paginatedDocs.map((doc) => {
              const isSelected = selectedDocuments.has(doc.id);
              const typeTag = getTypeTagStyle(doc.file_type);
              const statusTag = getStatusTag(doc);

              return (
                <div
                  key={doc.id}
                  onClick={() => toggleDocumentSelection(doc.id)}
                  className={`bg-neo-white border-3 border-neo-black shadow-neo-md p-4 cursor-pointer group flex flex-col gap-3 relative transition-all duration-200 hover:-translate-y-1 hover:shadow-neo-hover ${
                    isSelected
                      ? 'bg-green-50 border-neo-primary shadow-[8px_8px_0px_0px_#29bf12]'
                      : ''
                  }`}
                >
                  {/* 類型標籤 */}
                  <div
                    className={`absolute -top-2 left-2 ${typeTag.bg} ${typeTag.text} border-2 ${typeTag.border} px-2 py-0.5 text-[10px] font-black z-10`}
                  >
                    {typeTag.label}
                  </div>

                  {/* 操作按鈕 */}
                  <div className="absolute top-3 right-3 z-10 flex gap-2">
                    {/* 查看詳情按鈕 */}
                    <button
                      onClick={(e) => openDocumentDetail(doc, e)}
                      className="w-8 h-8 bg-neo-active text-white border-2 border-neo-black flex items-center justify-center hover:scale-110 transition-transform opacity-0 group-hover:opacity-100"
                      title="查看詳情"
                    >
                      <span className="text-sm">👁</span>
                    </button>
                    
                    {/* Checkbox */}
                    <div
                      className={`transition-opacity ${
                        isSelected ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => {}}
                        className="w-5 h-5 border-2 border-neo-black accent-neo-primary cursor-pointer"
                      />
                    </div>
                  </div>

                  {/* 文件預覽 */}
                  <div className="aspect-[4/3] bg-gray-50 border-2 border-neo-black flex items-center justify-center group-hover:bg-white relative overflow-hidden">
                    <ImageThumbnail doc={doc} />
                  </div>

                  {/* 文件信息 */}
                  <div>
                    <h3 className="font-bold text-sm truncate" title={doc.filename}>
                      {doc.filename}
                    </h3>
                    <div className="flex justify-between items-center mt-2">
                      <span className="text-xs font-bold text-gray-400">
                        {formatBytes(doc.size ?? undefined)}
                      </span>
                      <span className={`text-[10px] font-black px-2 py-0.5 border-2 border-neo-black ${statusTag.color}`}>
                        {statusTag.label}
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
          </>
        ) : (
          /* 列表視圖 - Neo-Brutalism 風格 */
          <div className="bg-neo-white border-3 border-neo-black shadow-neo-lg overflow-hidden">
            {/* 表頭 */}
            <div className="grid grid-cols-[auto_80px_2fr_120px_120px_120px] gap-4 p-4 bg-gray-100 border-b-3 border-neo-black font-display font-bold text-xs uppercase tracking-wide">
              <div className="flex items-center">
                <input
                  type="checkbox"
                  checked={paginatedDocs.length > 0 && paginatedDocs.every(doc => selectedDocuments.has(doc.id))}
                  onChange={() => {
                    const allSelected = paginatedDocs.every(doc => selectedDocuments.has(doc.id));
                    const newSelection = new Set(selectedDocuments);
                    if (allSelected) {
                      paginatedDocs.forEach(doc => newSelection.delete(doc.id));
                    } else {
                      paginatedDocs.forEach(doc => newSelection.add(doc.id));
                    }
                    onSelectDocuments(newSelection);
                  }}
                  className="w-5 h-5 border-2 border-neo-black accent-neo-primary"
                />
              </div>
              <div>類型</div>
              <div>檔案名稱</div>
              <div>大小</div>
              <div>修改時間</div>
              <div>狀態</div>
            </div>

            {/* 文件列表 */}
            {paginatedDocs.map(doc => {
              const isSelected = selectedDocuments.has(doc.id);
              const isExpanded = expandedDocId === doc.id;
              const typeTag = getTypeTagStyle(doc.file_type);
              const statusTag = getStatusTag(doc);
              const aiSummary = doc.analysis?.ai_analysis_output?.initial_summary;
              const keyInfo = doc.analysis?.ai_analysis_output?.key_information as any;
              const tags = (keyInfo?.semantic_tags || keyInfo?.searchable_keywords || []) as string[];

              return (
                <div key={doc.id} className="border-b-2 border-gray-200">
                  {/* 主要行 */}
                  <div
                    onClick={() => toggleExpandedDoc(doc.id)}
                    className={`grid grid-cols-[auto_80px_2fr_120px_120px_120px] gap-4 p-4 items-center cursor-pointer transition-all hover:bg-gray-50 ${
                      isSelected ? 'bg-green-50 border-l-4 border-l-neo-primary' : ''
                    } ${isExpanded ? 'border-l-4 border-l-neo-black' : ''}`}
                  >
                    {/* 操作按鈕 */}
                    <div className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={(e) => { e.stopPropagation(); toggleDocumentSelection(doc.id); }}
                        className="w-5 h-5 border-2 border-neo-black accent-neo-primary"
                      />
                      {/* 展開/收起箭頭按鈕 */}
                      <button
                        onClick={(e) => { e.stopPropagation(); toggleExpandedDoc(doc.id); }}
                        className="w-7 h-7 text-neo-black flex items-center justify-center hover:scale-110 transition-transform"
                        title={isExpanded ? "收起詳情" : "展開詳情"}
                      >
                        <span className={`text-xs transition-transform ${isExpanded ? 'rotate-90' : ''}`}>
                          ▶
                        </span>
                      </button>
                    </div>

                    {/* 類型標籤 */}
                    <div>
                      <span className={`inline-block px-2 py-1 text-[10px] font-black border-2 ${typeTag.border} ${typeTag.bg} ${typeTag.text}`}>
                        {typeTag.label}
                      </span>
                    </div>

                    {/* 檔名（含小縮圖） */}
                    <div className="flex items-center gap-3 min-w-0">
                      {/* 小縮圖 */}
                      <div className="w-12 h-12 flex-shrink-0 bg-gray-100 border-2 border-neo-black flex items-center justify-center overflow-hidden">
                        {doc.file_type?.startsWith('image/') ? (
                          <div className="w-full h-full">
                            <ImageThumbnail doc={doc} />
                          </div>
                        ) : (
                          <DocumentTypeIcon
                            fileType={doc.file_type || null}
                            fileName={doc.filename}
                            className="text-2xl text-gray-400"
                          />
                        )}
                      </div>
                      {/* 檔名 */}
                      <div className="flex-1 min-w-0">
                        <span className="font-bold text-sm truncate block" title={doc.filename}>
                          {doc.filename}
                        </span>
                        {aiSummary && !isExpanded && (
                          <p className="text-xs text-gray-500 truncate mt-0.5">
                            {aiSummary.substring(0, 50)}...
                          </p>
                        )}
                      </div>
                    </div>

                    {/* 大小 */}
                    <div className="text-sm text-gray-600 font-semibold">
                      {formatBytes(doc.size ?? undefined)}
                    </div>

                    {/* 時間 */}
                    <div className="text-sm text-gray-600 font-semibold">
                      {formatDate(doc.updated_at)}
                    </div>

                    {/* 狀態 */}
                    <div>
                      <span className={`inline-block px-2 py-1 text-[10px] font-black border-2 border-neo-black ${statusTag.color}`}>
                        {statusTag.label}
                      </span>
                    </div>
                  </div>

                  {/* 展開內容 */}
                  {isExpanded && (
                    <div className="bg-white border-t-2 border-gray-200 p-6">
                      <div className="flex gap-6">
                        {/* 左側：大預覽 */}
                        <div className="w-64 h-64 flex-shrink-0 bg-gray-100 border-3 border-neo-black flex items-center justify-center overflow-hidden">
                          {doc.file_type?.startsWith('image/') ? (
                            <div className="w-full h-full">
                              <ImageThumbnail doc={doc} />
                            </div>
                          ) : (
                            <DocumentTypeIcon
                              fileType={doc.file_type || null}
                              fileName={doc.filename}
                              className="text-6xl text-gray-300"
                            />
                          )}
                        </div>

                        {/* 右側：詳細信息 */}
                        <div className="flex-1 space-y-3">
                          {/* AI 摘要 */}
                          {aiSummary && (
                            <div className="bg-neo-black text-white p-3 border-2 border-neo-black">
                              <div className="text-xs font-bold mb-1" style={{ color: '#29bf12' }}>✨ AI SUMMARY</div>
                              <p className="text-sm leading-relaxed">{aiSummary}</p>
                            </div>
                          )}

                          {/* 標籤 */}
                          {tags.length > 0 && (
                            <div>
                              <div className="text-xs font-bold text-gray-600 mb-2">🏷️ TAGS</div>
                              <div className="flex flex-wrap gap-2">
                                {tags.map((tag, idx) => {
                                  const colors = [
                                    'bg-red-100 text-red-700 border-red-700',
                                    'bg-blue-100 text-blue-700 border-blue-700',
                                    'bg-green-100 text-green-700 border-green-700',
                                    'bg-purple-100 text-purple-700 border-purple-700',
                                    'bg-orange-100 text-orange-700 border-orange-700',
                                    'bg-pink-100 text-pink-700 border-pink-700',
                                  ];
                                  return (
                                    <span
                                      key={idx}
                                      className={`px-3 py-1 text-xs font-black border-2 border-neo-black shadow-neo-sm ${colors[idx % colors.length]}`}
                                    >
                                      {tag}
                                    </span>
                                  );
                                })}
                              </div>
                            </div>
                          )}

                          {/* 快速操作 */}
                          <div className="pt-2">
                            <button
                              onClick={(e) => openDocumentDetail(doc, e)}
                              className="bg-neo-primary text-white border-2 border-neo-black px-4 py-2 font-bold text-sm shadow-neo-sm hover:shadow-none hover:translate-x-1 hover:translate-y-1 transition-all"
                            >
                              查看完整詳情
                            </button>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}

            {/* 空狀態 */}
            {filteredDocs.length === 0 && (
              <div className="text-center py-20 text-gray-500">
                <p className="font-bold text-lg">找不到符合條件的文件</p>
              </div>
            )}
          </div>
        )}
      </main>

      {/* 文件詳情模態框 */}
      <DocumentDetailsModal
        document={selectedDetail}
        isOpen={isDetailModalOpen}
        onClose={closeDocumentDetail}
      />
    </div>
  );
};

export default FolderDetailView;
