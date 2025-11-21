import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Input, Spin, Empty } from 'antd';
import { SearchOutlined, FileTextOutlined, CloseOutlined } from '@ant-design/icons';
import { getDocuments } from '../../services/documentService';
import { performSemanticSearch } from '../../services/vectorDBService';
import type { Document } from '../../types/apiTypes';

interface FileSearchModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelect: (file: Document) => void;
  showOnlyVectorized?: boolean;
}

/**
 * 文件搜索弹出框
 * 类似 VSCode 的 Ctrl+P 搜索界面
 */
const FileSearchModal: React.FC<FileSearchModalProps> = ({
  isOpen,
  onClose,
  onSelect,
  showOnlyVectorized = true,
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [files, setFiles] = useState<Document[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const searchInputRef = useRef<any>(null);

  // 🔥 混合搜索：文件名 + 语义搜索
  const loadFiles = useCallback(async (query: string = '') => {
    setIsLoading(true);
    try {
      let allDocs: Document[] = [];
      
      if (query.trim()) {
        // 有搜索关键词：同时使用文件名搜索 + 语义搜索
        const [filenameResults, semanticResults] = await Promise.allSettled([
          // 1. 文件名搜索
          getDocuments(query, 'all', undefined, 'created_at', 'desc', 0, 20),
          
          // 2. 语义搜索（只搜索已向量化的文档）
          performSemanticSearch(query, 20, 0.3)
        ]);
        
        // 合并文件名搜索结果
        if (filenameResults.status === 'fulfilled') {
          allDocs = [...filenameResults.value.documents];
        }
        
        // 合并语义搜索结果
        if (semanticResults.status === 'fulfilled') {
          const semanticDocs = semanticResults.value;
          
          // 去重：只添加文件名搜索中没有的文档
          const existingIds = new Set(allDocs.map(d => d.id));
          
          for (const result of semanticDocs) {
            if (!existingIds.has(result.document_id)) {
              // 将语义搜索结果转换为 Document 对象
              // 注意：SemanticSearchResult 只有基本信息，需要获取完整文档
              const doc = {
                id: result.document_id,
                filename: (result.metadata as any)?.filename || result.document_id,
                file_type: result.metadata?.file_type || null,
                status: 'processed' as any,
                vector_status: 'vectorized' as any,
                owner_id: '', // 语义搜索结果不包含owner_id，使用空字符串占位
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString(),
                enriched_data: {
                  summary: result.summary_text
                },
                analysis: result.metadata?.analysis,
                // 添加搜索相关性分数（用于排序）
                _searchScore: result.similarity_score
              } as any as Document;
              
              allDocs.push(doc);
              existingIds.add(result.document_id);
            }
          }
        }
        
        console.log(`🔍 混合搜索结果: 文件名 ${filenameResults.status === 'fulfilled' ? filenameResults.value.documents.length : 0} 个, 语义 ${semanticResults.status === 'fulfilled' ? semanticResults.value.length : 0} 个, 总计 ${allDocs.length} 个`);
        
      } else {
        // 无搜索关键词：只显示最近的文档
        const response = await getDocuments('', 'all', undefined, 'created_at', 'desc', 0, 50);
        allDocs = response.documents;
      }

      // 过滤：只显示已向量化的文档
      if (showOnlyVectorized) {
        allDocs = allDocs.filter((doc: Document) => doc.vector_status === 'vectorized');
      }
      
      // 排序：优先显示高相关性的结果
      if (query.trim()) {
        allDocs.sort((a, b) => {
          const scoreA = (a as any)._searchScore || 0;
          const scoreB = (b as any)._searchScore || 0;
          return scoreB - scoreA;
        });
      }

      setFiles(allDocs);
      setSelectedIndex(0);
    } catch (error) {
      console.error('加载文档失败:', error);
      setFiles([]);
    } finally {
      setIsLoading(false);
    }
  }, [showOnlyVectorized]);

  // 防抖搜索
  useEffect(() => {
    if (!isOpen) return;

    const timer = setTimeout(() => {
      loadFiles(searchQuery);
    }, 300);

    return () => clearTimeout(timer);
  }, [searchQuery, isOpen, loadFiles]);

  // 打开时聚焦搜索框
  useEffect(() => {
    if (isOpen && searchInputRef.current) {
      setTimeout(() => {
        searchInputRef.current?.focus();
      }, 100);
    }
  }, [isOpen]);

  // 键盘导航
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setSelectedIndex(prev => (prev < files.length - 1 ? prev + 1 : prev));
        break;
      case 'ArrowUp':
        e.preventDefault();
        setSelectedIndex(prev => (prev > 0 ? prev - 1 : 0));
        break;
      case 'Enter':
        e.preventDefault();
        if (files[selectedIndex]) {
          onSelect(files[selectedIndex]);
          onClose();
        }
        break;
      case 'Escape':
        e.preventDefault();
        onClose();
        break;
    }
  }, [files, selectedIndex, onSelect, onClose]);

  // 滚动到选中项
  useEffect(() => {
    const selectedElement = document.querySelector(`[data-file-index="${selectedIndex}"]`);
    if (selectedElement) {
      selectedElement.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  }, [selectedIndex]);

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-start justify-center pt-[10vh] z-[9999]"
      onClick={onClose}
    >
      <div
        className="w-full max-w-3xl bg-white border-3 border-neo-black shadow-[12px_12px_0px_0px_black] overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header - 搜索框 */}
        <div className="bg-neo-primary border-b-3 border-neo-black p-4">
          <div className="flex items-center gap-3">
            <SearchOutlined className="text-white text-xl" />
            <Input
              ref={searchInputRef}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="搜索文件名..."
              className="flex-1 text-lg font-bold border-2 border-neo-black focus:ring-2 focus:ring-white"
              style={{ 
                height: '48px',
                fontSize: '16px'
              }}
              suffix={
                searchQuery && (
                  <button
                    onClick={() => setSearchQuery('')}
                    className="text-gray-400 hover:text-gray-600"
                  >
                    <CloseOutlined />
                  </button>
                )
              }
            />
          </div>
          
          {/* 快捷键提示 + 搜索模式 */}
          <div className="mt-2 flex items-center justify-between text-xs text-white/80">
            <div className="flex items-center gap-4">
              <span className="flex items-center gap-1">
                <kbd className="px-2 py-1 bg-white/20 border border-white/30 rounded font-mono">↑↓</kbd>
                導航
              </span>
              <span className="flex items-center gap-1">
                <kbd className="px-2 py-1 bg-white/20 border border-white/30 rounded font-mono">Enter</kbd>
                選擇
              </span>
              <span className="flex items-center gap-1">
                <kbd className="px-2 py-1 bg-white/20 border border-white/30 rounded font-mono">Esc</kbd>
                關閉
              </span>
            </div>
            {searchQuery && (
              <div className="flex items-center gap-1 text-[10px] bg-white/10 px-2 py-1 rounded border border-white/20">
                <i className="ph-bold ph-lightning text-yellow-300" />
                <span>混合搜索</span>
              </div>
            )}
          </div>
        </div>

        {/* Body - 文件列表 */}
        <div className="max-h-[60vh] overflow-y-auto bg-white">
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <Spin size="large" />
              <span className="ml-3 text-gray-600">載入中...</span>
            </div>
          ) : files.length === 0 ? (
            <div className="py-12">
              <Empty
                description={
                  searchQuery
                    ? `未找到匹配 "${searchQuery}" 的文件`
                    : showOnlyVectorized
                    ? '沒有已向量化的文檔'
                    : '沒有文檔'
                }
              />
            </div>
          ) : (
            <div>
              {files.map((file, index) => (
                <div
                  key={file.id}
                  data-file-index={index}
                  onClick={() => {
                    onSelect(file);
                    onClose();
                  }}
                  className={`
                    px-6 py-4 cursor-pointer transition-all border-b-2 border-gray-100
                    ${index === selectedIndex
                      ? 'bg-neo-primary/20 border-l-4 border-l-neo-primary'
                      : 'hover:bg-gray-50 border-l-4 border-l-transparent'
                    }
                  `}
                >
                  {/* 文件信息 */}
                  <div className="flex items-start gap-3">
                    {/* 图标 */}
                    <div className={`
                      mt-1 flex-shrink-0 w-10 h-10 flex items-center justify-center rounded-lg border-2 border-neo-black
                      ${index === selectedIndex ? 'bg-neo-primary text-white' : 'bg-gray-100 text-gray-600'}
                    `}>
                      <FileTextOutlined className="text-lg" />
                    </div>

                    {/* 内容 */}
                    <div className="flex-1 min-w-0">
                      {/* 文件名 */}
                      <div className="flex items-center gap-2 mb-1">
                        <span className="font-bold text-base text-neo-black truncate">
                          {file.filename}
                        </span>
                        {file.file_type && (
                          <span className="flex-shrink-0 text-[10px] px-2 py-0.5 bg-neo-black text-white rounded font-bold uppercase">
                            {file.file_type}
                          </span>
                        )}
                        {file.vector_status === 'vectorized' && (
                          <span className="flex-shrink-0 text-[10px] px-2 py-0.5 bg-green-600 text-white rounded font-bold">
                            已向量化
                          </span>
                        )}
                      </div>

                      {/* 摘要 */}
                      {(file.enriched_data?.summary || file.analysis?.ai_analysis_output?.key_information?.content_summary) && (
                        <p className="text-sm text-gray-600 line-clamp-2 mb-2">
                          {file.enriched_data?.summary || file.analysis?.ai_analysis_output?.key_information?.content_summary}
                        </p>
                      )}

                      {/* 关键概念 */}
                      {(() => {
                        const keyConcepts = (file.enriched_data as any)?.key_concepts || file.analysis?.ai_analysis_output?.key_information?.key_concepts || [];
                        return keyConcepts.length > 0 && (
                          <div className="flex gap-1.5 flex-wrap">
                            {keyConcepts
                              .slice(0, 4)
                              .map((concept: string, i: number) => (
                                <span
                                  key={i}
                                  className="text-[11px] px-2 py-0.5 bg-gray-100 text-gray-700 rounded-md font-medium"
                                >
                                  {concept}
                                </span>
                              ))}
                          </div>
                        );
                      })()}

                      {/* 元数据 */}
                      <div className="mt-2 flex items-center gap-3 text-xs text-gray-500">
                        <span>狀態: {file.status}</span>
                        {file.created_at && (
                          <span>創建: {new Date(file.created_at).toLocaleDateString('zh-TW')}</span>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer - 统计信息 */}
        {files.length > 0 && (
          <div className="bg-gray-50 border-t-3 border-neo-black px-6 py-3 flex items-center justify-between text-sm">
            <span className="text-gray-600">
              共找到 <span className="font-bold text-neo-black">{files.length}</span> 個文件
              {showOnlyVectorized && <span className="ml-1">(已向量化)</span>}
            </span>
            <span className="text-gray-500">
              第 {selectedIndex + 1} / {files.length} 項
            </span>
          </div>
        )}
      </div>
    </div>
  );
};

export default FileSearchModal;
