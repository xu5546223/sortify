import React, { useState, useEffect } from 'react';
import type { Document, DocumentStatus, AITextAnalysisOutput } from '../../types/apiTypes';
import { formatBytes, formatDate, mapMimeTypeToSimpleType } from '../../utils/documentFormatters';
import { apiClient } from '../../services/apiClient';
import PreviewModal from './PreviewModal';

interface DocumentDetailsModalProps {
  document: Document | null;
  isOpen: boolean;
  onClose: () => void;
}

// 狀態標籤組件
const StatusBadge: React.FC<{ status: DocumentStatus }> = ({ status }) => {
  let config;
  switch (status) {
    case 'completed':
    case 'analysis_completed':
      config = { label: '✓ 分析完成', color: 'bg-neo-primary text-neo-white' };
      break;
    case 'uploaded':
    case 'pending_extraction':
    case 'text_extracted':
    case 'pending_analysis':
      config = { label: '⏳ 待處理', color: 'bg-gray-300 text-gray-700' };
      break;
    case 'analyzing':
      config = { label: '🔄 分析中', color: 'bg-neo-warn text-neo-black' };
      break;
    case 'processing_error':
    case 'analysis_failed':
    case 'extraction_failed':
      config = { label: '✕ 失敗', color: 'bg-neo-error text-neo-white' };
      break;
    default:
      config = { label: '⚠ 檢查', color: 'bg-neo-warn text-neo-black' };
  }
  return (
    <span className={`inline-block px-2 py-1 text-[10px] font-black border-2 border-neo-black ${config.color}`}>
      {config.label}
    </span>
  );
};

// 文件預覽組件
const DocumentPreview: React.FC<{ document: Document }> = ({ document }) => {
  const [imageSrc, setImageSrc] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let objectUrl: string | null = null;

    if (document.file_type?.startsWith('image/')) {
      apiClient.get(`/documents/${document.id}/file`, { responseType: 'blob' })
        .then(response => {
          objectUrl = URL.createObjectURL(response.data);
          setImageSrc(objectUrl);
          setLoading(false);
        })
        .catch(() => setLoading(false));
    } else {
      setLoading(false);
    }

    // 清理函數：釋放 Object URL
    return () => {
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [document.id, document.file_type]);

  if (loading) {
    return (
      <div className="w-full h-full flex items-center justify-center bg-gray-100 border-2 border-neo-black">
        <div className="animate-spin rounded-full h-12 w-12 border-4 border-neo-black border-t-transparent"></div>
      </div>
    );
  }

  if (imageSrc) {
    return (
      <img
        src={imageSrc}
        alt={document.filename}
        className="w-full h-full object-contain border-2 border-neo-black bg-white"
      />
    );
  }

  // 非圖片文件顯示圖標
  return (
    <div className="w-full h-full flex flex-col items-center justify-center bg-orange-100 border-2 border-neo-black">
      <div className="text-6xl mb-4">📄</div>
      <div className="text-sm font-bold text-gray-600">{mapMimeTypeToSimpleType(document.file_type)}</div>
    </div>
  );
};

// 放大預覽按鈕
const ImageZoomButton: React.FC<{ onClick: () => void }> = ({ onClick }) => (
  <button
    onClick={(e) => { e.stopPropagation(); onClick(); }}
    className="absolute bottom-3 right-3 w-10 h-10 bg-white border-2 border-neo-black shadow-neo-sm flex items-center justify-center hover:bg-gray-100 transition-colors z-10"
    aria-label="放大預覽"
  >
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0zM10 7v3m0 0v3m0-3h3m-3 0H7" />
    </svg>
  </button>
);

// 通用內容展示組件 - 使用排除法展示所有重要內容
const KeyInformationView: React.FC<{ keyInfo: any }> = ({ keyInfo }) => {
  if (!keyInfo || typeof keyInfo !== 'object') return null;

  // 排除不需要展示的欄位（只保留最核心的用戶價值內容）
  const excludeKeys = [
    // === 已在其他地方顯示 ===
    'semantic_tags',              // 已在左側標籤雲顯示
    'content_type',               // 已在 AI 摘要顯示
    'content_summary',            // 已在 AI 摘要顯示
    
    // === 技術性/內部欄位 ===
    'intermediate_analysis',      // AI 中間分析過程
    'confidence_level',           // 技術置信度指標
    'quality_assessment',         // 技術品質評估
    'processing_notes',           // 系統處理備註
    'dynamic_fields',             // 動態技術欄位（太多細節）
    'structured_entities',        // 結構化實體（太複雜）
    
    // === 次要資訊欄位 ===
    'searchable_keywords',        // 搜索關鍵詞（與 tags 重複）
    'knowledge_domains',          // 知識領域（分類用）
    'note_structure',             // 筆記結構描述
    'thinking_patterns',          // 思考模式分析
    'business_context',           // 商業背景（已在摘要中）
    'legal_context',              // 法律背景（較少使用）
    'target_audience',            // 目標受眾（較少使用）
    'urgency_level',              // 緊急程度（較少使用）
    'stakeholders',               // 利害關係人（較少使用）
    'compliance_requirements',    // 合規要求（較少使用）
    'document_purpose',           // 文件目的（已在摘要中）
    'auto_title'                  // 自動標題（可選）
  ];

  // 智能渲染文字，數字部分加粗
  const renderTextWithBoldNumbers = (text: any): React.ReactNode => {
    if (text === null || text === undefined) {
      return <span className="text-gray-400">-</span>;
    }

    if (typeof text === 'number') {
      return <strong className="font-bold text-gray-900">{text}</strong>;
    }
    
    const stringValue = String(text);
    const parts = stringValue.split(/(\d+(?:\.\d+)?)/g);
    
    if (parts.length > 1) {
      return (
        <>
          {parts.map((part, idx) => 
            /^\d+(?:\.\d+)?$/.test(part) ? (
              <strong key={idx} className="font-bold text-gray-900">{part}</strong>
            ) : (
              <span key={idx}>{part}</span>
            )
          )}
        </>
      );
    }
    
    return <span>{stringValue}</span>;
  };

  // 渲染單個欄位值
  const renderValue = (value: any): React.ReactNode => {
    if (value === null || value === undefined) {
      return <span className="text-gray-400">-</span>;
    }

    // 陣列類型
    if (Array.isArray(value)) {
      if (value.length === 0) return <span className="text-gray-400">無</span>;
      
      // 檢查是否包含物件（結構化數據）
      const hasObjects = value.some(item => typeof item === 'object' && item !== null);
      
      if (hasObjects) {
        // 格式化顯示結構化陣列
        return (
          <div className="space-y-2">
            {value.map((item, idx) => {
              if (typeof item === 'object' && item !== null) {
                return (
                  <div key={idx} className="bg-gray-50 border border-gray-300 rounded px-3 py-2 text-xs">
                    {Object.entries(item).map(([k, v]) => (
                      <div key={k} className="flex gap-2">
                        <span className="font-bold text-gray-600 min-w-[80px]">{k}:</span>
                        <span className="text-gray-800 flex-1">
                          {v === null ? <span className="text-gray-400 italic">null</span> : renderTextWithBoldNumbers(v)}
                        </span>
                      </div>
                    ))}
                  </div>
                );
              }
              // 陣列中的字串
              return (
                <span key={idx} className="px-2 py-1 bg-gray-100 border border-gray-300 text-xs rounded">
                  {renderTextWithBoldNumbers(item)}
                </span>
              );
            })}
          </div>
        );
      }
      
      // 純字串陣列（如 tags）
      return (
        <div className="flex flex-wrap gap-1">
          {value.map((item, idx) => (
            <span key={idx} className="px-2 py-1 bg-gray-100 border border-gray-300 text-xs rounded">
              {renderTextWithBoldNumbers(item)}
            </span>
          ))}
        </div>
      );
    }

    // 物件類型
    if (typeof value === 'object') {
      return (
        <div className="bg-gray-50 border border-gray-300 rounded px-3 py-2 text-xs space-y-1">
          {Object.entries(value).map(([k, v]) => (
            <div key={k} className="flex gap-2">
              <span className="font-bold text-gray-600 min-w-[100px]">{k}:</span>
              <span className="text-gray-800 flex-1">
                {v === null ? <span className="text-gray-400 italic">null</span> : 
                 typeof v === 'object' ? JSON.stringify(v) : renderTextWithBoldNumbers(v)}
              </span>
            </div>
          ))}
        </div>
      );
    }

    // 字串/數字類型
    return <span className="font-medium">{renderTextWithBoldNumbers(value)}</span>;
  };

  // 格式化欄位名稱
  const formatLabel = (key: string): string => {
    // 中文直接返回
    if (/[\u4e00-\u9fa5]/.test(key)) return key;
    
    // 英文：snake_case 轉 Title Case
    return key
      .replace(/_/g, ' ')
      .replace(/\b\w/g, char => char.toUpperCase());
  };

  // 檢查值是否為空
  const isEmpty = (value: any): boolean => {
    if (value === null || value === undefined) return true;
    if (typeof value === 'string' && value.trim() === '') return true;
    if (Array.isArray(value) && value.length === 0) return true;
    if (typeof value === 'object' && Object.keys(value).length === 0) return true;
    return false;
  };

  // 過濾出要顯示的欄位：排除黑名單 + 排除空值
  const displayFields = Object.entries(keyInfo).filter(
    ([key, value]) => !excludeKeys.includes(key) && !isEmpty(value)
  );

  // 沒有可顯示的欄位
  if (displayFields.length === 0) {
    return (
      <div className="border-2 border-neo-black bg-white px-4 py-8 text-center">
        <p className="text-gray-400 text-sm">無可顯示的內容數據</p>
      </div>
    );
  }

  // 計算卡片內容複雜度評分（0-100）
  const getContentComplexity = (value: any): number => {
    if (value === null || value === undefined) return 0;
    
    // 陣列包含物件 = 高複雜度
    if (Array.isArray(value) && value.some(item => typeof item === 'object' && item !== null)) {
      return 80 + Math.min(value.length * 5, 20);
    }
    
    // 物件類型
    if (typeof value === 'object' && !Array.isArray(value)) {
      const keyCount = Object.keys(value).length;
      return 40 + Math.min(keyCount * 15, 60);
    }
    
    // 陣列類型
    if (Array.isArray(value)) {
      return 20 + Math.min(value.length * 8, 60);
    }
    
    // 字串類型
    if (typeof value === 'string') {
      return Math.min(value.length / 3, 60);
    }
    
    return 10;
  };

  // 智能分組：將小卡片組合在一起
  const layoutCards = () => {
    const cards = displayFields.map(([key, value]) => ({
      key,
      value,
      complexity: getContentComplexity(value)
    }));

    const rows: Array<Array<typeof cards[0]>> = [];
    let currentRow: Array<typeof cards[0]> = [];
    let currentRowComplexity = 0;

    cards.forEach(card => {
      // 複雜度 > 60 = 獨立佔一行
      if (card.complexity > 60) {
        if (currentRow.length > 0) {
          rows.push([...currentRow]);
          currentRow = [];
          currentRowComplexity = 0;
        }
        rows.push([card]);
      }
      // 當前行空 或 加上新卡片不超過閾值 = 加入當前行
      else if (currentRow.length === 0 || currentRowComplexity + card.complexity <= 80) {
        currentRow.push(card);
        currentRowComplexity += card.complexity;
      }
      // 否則，開啟新行
      else {
        rows.push([...currentRow]);
        currentRow = [card];
        currentRowComplexity = card.complexity;
      }
    });

    // 處理最後一行
    if (currentRow.length > 0) {
      rows.push(currentRow);
    }

    return rows;
  };

  const cardRows = layoutCards();

  // 展示所有欄位 - 智能分組佈局
  return (
    <div className="space-y-4">
      {cardRows.map((row, rowIdx) => (
        <div 
          key={rowIdx} 
          className={`grid gap-4 ${row.length === 1 ? 'grid-cols-1' : 'grid-cols-1 md:grid-cols-2'}`}
        >
          {row.map(({ key, value }) => (
            <div key={key} className="border-3 border-neo-black bg-white shadow-neo-sm">
              {/* 卡片標題 */}
              <div className="bg-gray-100 border-b-3 border-neo-black px-4 py-2">
                <h3 className="text-sm font-black text-gray-700 uppercase">{formatLabel(key)}</h3>
              </div>
              
              {/* 卡片內容 */}
              <div className="px-4 py-3 text-sm text-gray-800">
                {renderValue(value)}
              </div>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
};

// 標籤雲組件
const TagCloud: React.FC<{ tags: string[] }> = ({ tags }) => {
  if (!tags || tags.length === 0) return null;

  const colors = [
    'bg-red-100 text-red-700 border-red-700',
    'bg-blue-100 text-blue-700 border-blue-700',
    'bg-green-100 text-green-700 border-green-700',
    'bg-purple-100 text-purple-700 border-purple-700',
    'bg-orange-100 text-orange-700 border-orange-700',
    'bg-pink-100 text-pink-700 border-pink-700',
  ];

  return (
    <div className="flex flex-wrap gap-2">
      {tags.map((tag, idx) => (
        <span
          key={idx}
          className={`px-3 py-1 text-xs font-black border-2 border-neo-black shadow-neo-sm cursor-pointer hover:shadow-none hover:translate-x-1 hover:translate-y-1 transition-all ${colors[idx % colors.length]}`}
        >
          {tag}
        </span>
      ))}
    </div>
  );
};

const DocumentDetailsModal: React.FC<DocumentDetailsModalProps> = ({ document, isOpen, onClose }) => {
  const [showPreview, setShowPreview] = useState(false);

  if (!isOpen || !document) {
    return null;
  }

  const aiOutput = document.analysis?.ai_analysis_output as AITextAnalysisOutput;
  const keyInfo = aiOutput?.key_information as any;
  const semanticTags = (keyInfo?.semantic_tags || keyInfo?.searchable_keywords || []) as string[];

  return (
    <div 
      className="fixed inset-0 bg-black/90 flex items-center justify-center p-4 z-50"
      onClick={onClose}
    >
      <div 
        onClick={(e: React.MouseEvent) => e.stopPropagation()} 
        className="w-full max-w-7xl max-h-[95vh] bg-white border-3 border-neo-black shadow-[8px_8px_0px_0px_black] flex flex-col"
      >
        {/* Header */}
        <div className="bg-white text-neo-black px-6 py-4 border-b-3 border-neo-black flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <StatusBadge status={document.status as DocumentStatus} />
            <h2 className="font-display font-bold text-lg truncate">
              {document.filename}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="flex-shrink-0 w-10 h-10 flex items-center justify-center bg-red-600 text-white border-2 border-neo-black shadow-neo-sm hover:bg-red-700 transition-colors font-bold text-xl"
            aria-label="關閉"
          >
            ✕
          </button>
        </div>

        {/* 左右分欄內容 */}
        <div className="flex-1 overflow-hidden flex">
          {/* 左側：預覽區 */}
          <div className="w-1/3 border-r-3 border-neo-black bg-neo-bg p-4 flex flex-col gap-4 overflow-y-auto">
            {/* 預覽圖 */}
            <div className="aspect-[3/4] bg-white relative">
              <DocumentPreview document={document} />
              {document.file_type?.startsWith('image/') && (
                <ImageZoomButton onClick={() => setShowPreview(true)} />
              )}
            </div>

            {/* 文件屬性 */}
            <div className="border-2 border-neo-black bg-white">
              <div className="bg-gray-100 border-b-2 border-neo-black px-3 py-2 text-xs font-bold text-gray-600">
                FILE PROPERTIES
              </div>
              <div className="divide-y-2 divide-gray-200 text-xs">
                <div className="px-3 py-2 flex justify-between">
                  <span className="text-gray-600">類型</span>
                  <span className="font-bold">{mapMimeTypeToSimpleType(document.file_type)}</span>
                </div>
                <div className="px-3 py-2 flex justify-between">
                  <span className="text-gray-600">大小</span>
                  <span className="font-bold">{formatBytes(document.size ?? undefined)}</span>
                </div>
                <div className="px-3 py-2 flex justify-between">
                  <span className="text-gray-600">上傳</span>
                  <span className="font-bold text-[10px]">{formatDate(document.created_at)}</span>
                </div>
              </div>
            </div>

            {/* 標籤雲 */}
            {semanticTags.length > 0 && (
              <div>
                <div className="text-xs font-bold text-gray-600 mb-2">TAGS</div>
                <TagCloud tags={semanticTags} />
              </div>
            )}
          </div>

          {/* 右側：智慧區 */}
          <div className="flex-1 overflow-y-auto p-6 space-y-4 bg-neo-bg">
            {/* AI 摘要 */}
            {aiOutput?.initial_summary && (
              <div className="border-2 border-neo-black bg-neo-black text-white p-4">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-2xl">✨</span>
                  <span className="font-display font-bold text-sm uppercase" style={{ color: '#29bf12' }}>AI ANALYSIS SUMMARY</span>
                </div>
                <p className="text-sm leading-relaxed">{aiOutput.initial_summary}</p>
                {aiOutput.content_type && (
                  <div className="mt-2 pt-2 border-t border-gray-700 text-xs text-gray-400">
                    Confidence Level: <span className="text-neo-lime font-bold">HIGH</span> • Content Type: {aiOutput.content_type}
                  </div>
                )}
              </div>
            )}

            {/* 結構化數據（通用展示） */}
            {keyInfo && Object.keys(keyInfo).length > 0 && (
              <div>
                <div className="text-xs font-bold text-gray-600 mb-2">📋 EXTRACTED DATA</div>
                <KeyInformationView keyInfo={keyInfo} />
              </div>
            )}

            {/* 提取文本 */}
            {document.extracted_text && (
              <div>
                <div className="text-xs font-bold text-gray-600 mb-2">📄 EXTRACTED TEXT</div>
                <div className="border-2 border-neo-black bg-white p-4 max-h-64 overflow-y-auto">
                  <pre className="text-xs whitespace-pre-wrap text-gray-700 leading-relaxed">
                    {document.extracted_text}
                  </pre>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
      
      {/* 預覽模態框 */}
      <PreviewModal 
        isOpen={showPreview} 
        onClose={() => setShowPreview(false)} 
        doc={document} 
      />
    </div>
  );
};

export default DocumentDetailsModal;