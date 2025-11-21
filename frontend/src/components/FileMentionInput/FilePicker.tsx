import React, { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import type { FilePickerProps } from './types';

/**
 * Neo-Brutalism 文档选择器 - 显示在输入框左侧
 */
const FilePicker: React.FC<FilePickerProps & { 
  files: any[];
  isLoading: boolean;
  selectedIndex: number;
  onSelect: (file: any) => void;
}> = ({ 
  isOpen, 
  onClose, 
  onSelect, 
  position, 
  searchQuery,
  files, 
  isLoading, 
  selectedIndex 
}) => {
  const pickerRef = useRef<HTMLDivElement>(null);

  // 滚动到选中项
  useEffect(() => {
    if (pickerRef.current) {
      const selectedElement = pickerRef.current.querySelector(`[data-index="${selectedIndex}"]`);
      if (selectedElement) {
        selectedElement.scrollIntoView({ block: 'nearest' });
      }
    }
  }, [selectedIndex]);

  if (!isOpen) {
    return null;
  }

  // 📍 智能定位 - 確保完全可見
  const pickerWidth = 480;
  const pickerHeight = 450; // 包含 header + footer
  const gap = 48; // 與輸入框的間距
  
  const viewportWidth = window.innerWidth;
  const viewportHeight = window.innerHeight;
  
  let x: number;
  let y: number;
  
  // 檢查左側是否有足夠空間（需要 pickerWidth + gap + 安全邊距）
  const leftSpace = position.x - gap;
  const hasLeftSpace = leftSpace >= pickerWidth + 20;
  
  if (hasLeftSpace) {
    // 策略 A：顯示在輸入框左側
    x = position.x - pickerWidth - gap;
    y = position.y;
  } else {
    // 策略 B：顯示在輸入框下方（居中）
    x = Math.max(20, Math.min(position.x, viewportWidth - pickerWidth - 20));
    y = position.y + 140; // 輸入框高度 + 底部狀態欄 + gap
  }
  
  // 確保不超出螢幕底部
  if (y + pickerHeight > viewportHeight - 20) {
    y = Math.max(20, viewportHeight - pickerHeight - 20);
  }
  
  // 確保不超出螢幕右側
  if (x + pickerWidth > viewportWidth - 20) {
    x = viewportWidth - pickerWidth - 20;
  }
  
  const adjustedPosition = { x: Math.max(20, x), y: Math.max(20, y) };

  // 獲取文件圖標
  const getFileIcon = (filename: string) => {
    const ext = filename.split('.').pop()?.toLowerCase();
    if (['jpg', 'jpeg', 'png', 'gif', 'webp'].includes(ext || '')) {
      return { icon: 'ph-image', color: 'text-orange-500' };
    } else if (['pdf'].includes(ext || '')) {
      return { icon: 'ph-file-pdf', color: 'text-red-500' };
    } else if (['txt', 'md'].includes(ext || '')) {
      return { icon: 'ph-file-text', color: 'text-blue-500' };
    } else if (['doc', 'docx'].includes(ext || '')) {
      return { icon: 'ph-file-doc', color: 'text-blue-600' };
    } else if (['xls', 'xlsx'].includes(ext || '')) {
      return { icon: 'ph-file-xls', color: 'text-green-600' };
    } else if (['receipt', 'invoice'].includes(ext || '')) {
      return { icon: 'ph-receipt', color: 'text-orange-500' };
    }
    return { icon: 'ph-file', color: 'text-gray-500' };
  };

  // 高亮搜索關鍵字
  const highlightText = (text: string, query: string) => {
    if (!query || !text) return text;
    const parts = text.split(new RegExp(`(${query})`, 'gi'));
    return parts.map((part, i) => 
      part.toLowerCase() === query.toLowerCase() 
        ? <span key={i} className="bg-neo-hover px-0.5 font-bold rounded">{part}</span>
        : part
    );
  };

  // 🔥 使用 Portal 渲染到 body
  const pickerContent = (
    <div
      ref={pickerRef}
      className="fixed z-[99999] w-[480px] bg-white border-3 border-neo-black shadow-[6px_6px_0px_0px_black] overflow-hidden"
      style={{
        left: `${adjustedPosition.x}px`,
        top: `${adjustedPosition.y}px`,
        borderRadius: '8px',
        maxHeight: '450px'
      }}
    >
      {/* Header - 綠色標題欄 */}
      <div className="px-3 py-2 bg-neo-primary border-b-2 border-neo-black">
        <div className="flex items-center justify-between">
          <span className="font-bold text-sm text-neo-black">@ 選擇文件</span>
          <span className="text-xs bg-neo-black text-white px-2 py-0.5 font-mono font-bold">
            Semantic Search
          </span>
        </div>
      </div>

      {/* Content - 文件列表 */}
      <div className="overflow-y-auto max-h-[380px]">
        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <div className="animate-spin rounded-full h-6 w-6 border-2 border-neo-primary border-t-transparent"></div>
            <span className="ml-2 text-sm text-gray-600 font-bold">載入中...</span>
          </div>
        ) : files.length === 0 ? (
          <div className="py-8 text-center text-gray-500 text-sm">
            <i className="ph-bold ph-magnifying-glass text-3xl mb-2 block" />
            <p className="font-bold">未找到匹配的文檔</p>
            <p className="text-xs mt-1 text-gray-400">
              {searchQuery ? '嘗試其他搜索關鍵詞' : '請輸入搜索關鍵詞'}
            </p>
          </div>
        ) : (
          <div>
            {files.map((file, index) => {
              const { icon, color } = getFileIcon(file.filename);
              const isActive = index === selectedIndex;
              
              // 提取關鍵匹配片段（而不是完整摘要）
              const getSnippet = () => {
                if (!file.summary) return null;
                // 取摘要的前50個字符作為片段
                const snippet = file.summary.substring(0, 50);
                return `...${snippet}...`;
              };
              
              return (
                <div
                  key={file.id}
                  data-index={index}
                  onClick={() => onSelect(file)}
                  className={`
                    flex items-center gap-3 px-3 py-2.5 cursor-pointer transition-all border-b border-gray-200
                    ${isActive 
                      ? 'bg-green-50 border-l-4 border-l-neo-primary pl-[8px]' 
                      : 'border-l-4 border-l-transparent hover:bg-gray-50'
                    }
                  `}
                  style={{ height: '70px' }}
                >
                  {/* 左側：文件圖標框 */}
                  <div className="w-10 h-10 bg-white border-2 border-neo-black flex items-center justify-center flex-shrink-0 shadow-[2px_2px_0px_black]">
                    <i className={`ph-fill ${icon} ${color} text-xl`}></i>
                  </div>
                  
                  {/* 中間：文件信息（緊湊佈局） */}
                  <div className="flex-1 min-w-0">
                    {/* 第一行：文件名 + 日期 */}
                    <div className="flex justify-between items-center mb-0.5">
                      <span className="font-bold text-sm text-gray-900 truncate">
                        {file.filename.length > 30 ? file.filename.substring(0, 30) + '...' : file.filename}
                      </span>
                      {file.created_at && (
                        <span className="text-[10px] text-gray-400 font-mono flex-shrink-0 ml-2">
                          {new Date(file.created_at).toLocaleDateString('zh-TW', { 
                            month: '2-digit', 
                            day: '2-digit' 
                          })}
                        </span>
                      )}
                    </div>
                    
                    {/* 第二行：關鍵匹配片段（高亮搜索詞）*/}
                    {file.summary && (
                      <div className="text-xs text-gray-600 truncate">
                        {highlightText(getSnippet() || '', searchQuery)}
                      </div>
                    )}
                    
                    {/* 第三行：單個主要標籤（如果有）*/}
                    {file.key_concepts && file.key_concepts.length > 0 && (
                      <div className="mt-1">
                        <span className="text-[10px] px-1.5 py-0.5 border border-gray-200 bg-gray-50 text-gray-600 font-medium">
                          {file.key_concepts[0]}
                        </span>
                      </div>
                    )}
                  </div>
                  
                  {/* 右側：匹配分數 + Enter 提示 */}
                  <div className="flex flex-col items-end justify-center gap-1 pl-2">
                    {file.relevance_score && (
                      <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                        file.relevance_score > 0.8 
                          ? 'text-green-600 bg-green-100' 
                          : 'text-gray-400 bg-gray-100'
                      }`}>
                        {Math.round(file.relevance_score * 100)}%
                      </span>
                    )}
                    {isActive && (
                      <i className="ph-bold ph-arrow-return-left text-xs text-gray-300"></i>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Footer */}
      {files.length > 0 && (
        <div className="px-3 py-1.5 bg-gray-50 border-t-2 border-gray-200 text-xs text-gray-600">
          <div className="flex items-center justify-between">
            <span>
              <kbd className="px-1.5 py-0.5 bg-white border border-gray-300 rounded font-mono text-[10px]">↑</kbd>
              <kbd className="ml-1 px-1.5 py-0.5 bg-white border border-gray-300 rounded font-mono text-[10px]">↓</kbd>
              <span className="ml-1">導航</span>
            </span>
            <span>
              <kbd className="px-1.5 py-0.5 bg-white border border-gray-300 rounded font-mono text-[10px]">Enter</kbd>
              <span className="ml-1">選擇</span>
            </span>
            <span>
              <kbd className="px-1.5 py-0.5 bg-white border border-gray-300 rounded font-mono text-[10px]">Esc</kbd>
              <span className="ml-1">關閉</span>
            </span>
          </div>
        </div>
      )}
    </div>
  );

  // 🔥 使用 Portal 渲染到 body
  return createPortal(pickerContent, document.body);
};

export default FilePicker;
